"""FastAPI application: REST API, SSE streams and the built SPA."""
from __future__ import annotations

import asyncio
import csv
import io
import ipaddress
import json
import re
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import alerts, audit, auth_api, collector, config_editor, db, devices, diagnostics, dockerctl, helper_client, keys, netns, ops, security, settings, storage
from .mask import mask_text

COLLECTOR: collector.Collector | None = None
DIAG_WORKER: diagnostics.Worker | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global COLLECTOR, DIAG_WORKER
    db.conn()
    settings.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        settings.CONFIG_DIR.chmod(0o700)
    except OSError:
        pass
    security.ensure_setup_state()
    security.cleanup()
    security.harden_permissions()
    COLLECTOR = collector.Collector()
    COLLECTOR.start()
    DIAG_WORKER = diagnostics.Worker()
    DIAG_WORKER.start()
    yield
    if COLLECTOR:
        COLLECTOR.stop()
    if DIAG_WORKER:
        DIAG_WORKER.stop()


app = FastAPI(title="TGWSProxy Admin Panel", version="1.1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(auth_api.router)


@app.exception_handler(helper_client.HelperUnavailable)
async def _helper_unavailable(_request: Request, exc: helper_client.HelperUnavailable):
    return JSONResponse({"detail": str(exc)}, status_code=503)


@app.exception_handler(helper_client.HelperError)
async def _helper_error(_request: Request, exc: helper_client.HelperError):
    return JSONResponse({"detail": str(exc)}, status_code=502)

PUBLIC_API = {"/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/setup"}
PUBLIC_POST = {"/api/auth/login", "/api/auth/setup"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    """Require a server-side session for every /api route except the login/setup flow."""
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)

    if path in PUBLIC_POST:
        if not security.origin_allowed(request) or not security.pre_csrf_matches(request):
            security.log_event("csrf_failed", request, detail=f"{request.method} {path}")
            return JSONResponse({"detail": "CSRF check failed"}, status_code=403)
        return await call_next(request)

    if path in PUBLIC_API:
        return await call_next(request)

    session = security.load_session(request)
    if not session:
        security.log_unauthorized(request)
        return JSONResponse({"detail": "Требуется авторизация"}, status_code=401)

    if session["must_change_password"] and not security.must_change_allowed(path):
        return JSONResponse(
            {"detail": "Требуется сменить пароль", "code": "password_change_required"},
            status_code=403,
        )

    if request.method not in SAFE_METHODS:
        if not security.origin_allowed(request) or not security.csrf_matches(request, session["csrf"]):
            security.log_event("csrf_failed", request, username=session["username"], detail=f"{request.method} {path}")
            return JSONResponse({"detail": "CSRF check failed"}, status_code=403)

    request.state.session = session
    response = await call_next(request)
    if request.method not in SAFE_METHODS and not path.startswith("/api/auth/") and not path.startswith("/api/security/"):
        security.log_event(
            "admin_action",
            request,
            username=session["username"],
            detail=f"{request.method} {path} -> {response.status_code}",
        )
    return response


# ── helpers ──────────────────────────────────────────────────────────────────

RANGES = {
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}
CLIENT_RANGES = {"1h", "6h", "24h", "7d", "container"}
CLIENT_SORTS = {
    "client_ip": "client_ip",
    "sessions": "sessions",
    "bytes_up": "bytes_up",
    "bytes_down": "bytes_down",
    "bytes_total": "bytes_total",
    "first_seen": "first_seen",
    "last_seen": "last_seen",
}
METRIC_FIELDS = {
    "cpu_host",
    "cpu_proxy",
    "mem_used",
    "mem_proxy",
    "speed_in",
    "speed_out",
    "conns",
    "rx",
    "tx",
}
METRIC_STEPS = {"30m": 60, "1h": 60, "6h": 300, "24h": 600, "7d": 3600}

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, dict[tuple, tuple[float, dict]]] = {"clients": {}, "client": {}, "metrics": {}}


def _cache_get(kind: str, key: tuple, ttl: float) -> dict | None:
    now = time.time()
    with _CACHE_LOCK:
        item = _CACHE[kind].get(key)
        if item and now - item[0] <= ttl:
            return item[1]
        if item:
            _CACHE[kind].pop(key, None)
    return None


def _cache_put(kind: str, key: tuple, value: dict, max_items: int = 64) -> dict:
    with _CACHE_LOCK:
        bucket = _CACHE[kind]
        bucket[key] = (time.time(), value)
        if len(bucket) > max_items:
            for old in sorted(bucket, key=lambda k: bucket[k][0])[: len(bucket) - max_items]:
                bucket.pop(old, None)
    return value


def _start_for(range_key: str, since: str | None = None) -> str:
    if range_key == "container":
        return range_start_iso()
    return db.iso(cutoff(range_key, since))


def cutoff(range_key: str | None, since: str | None = None) -> datetime:
    if since:
        dt = db.parse_iso(since)
        if dt:
            return dt
    delta = RANGES.get(range_key or "1h", RANGES["1h"])
    return datetime.now(timezone.utc) - delta


def range_start_iso() -> str:
    snap = collector.snapshot()
    started = snap["proxy"].get("started_at")
    dt = db.parse_iso(started) if started else None
    if dt is None:
        dt = datetime.now(timezone.utc) - timedelta(hours=24)
    return db.iso(dt)


def row_dict(row) -> dict:
    return {k: row[k] for k in row.keys()}


def bucket_seconds(range_key: str) -> int:
    return {"30m": 60, "1h": 60, "6h": 300, "24h": 600, "7d": 3600}.get(range_key, 60)


def build_series(range_key: str) -> dict:
    start = cutoff(range_key)
    start_iso = db.iso(start)
    step = bucket_seconds(range_key)
    rows = db.query(
        "SELECT ended_at, bytes_up, bytes_down FROM sessions WHERE ended_at >= ? ORDER BY ended_at",
        (start_iso,),
    )
    buckets: dict[int, dict] = {}
    for r in rows:
        dt = db.parse_iso(r["ended_at"])
        if not dt:
            continue
        ts = int(dt.timestamp()) // step * step
        b = buckets.setdefault(ts, {"up": 0, "down": 0})
        b["up"] += int(r["bytes_up"] or 0)
        b["down"] += int(r["bytes_down"] or 0)
    now_ts = int(datetime.now(timezone.utc).timestamp()) // step * step
    first_ts = int(start.timestamp()) // step * step
    traffic = []
    ts = first_ts
    while ts <= now_ts:
        b = buckets.get(ts, {"up": 0, "down": 0})
        traffic.append(
            {
                "t": datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z"),
                "up": b["up"],
                "down": b["down"],
            }
        )
        ts += step
    if len(traffic) > 400:
        traffic = traffic[-400:]

    sample_rows = db.query("SELECT ts, conns, speed_in, speed_out FROM samples WHERE ts >= ? ORDER BY ts", (start_iso,))
    conn_points = []
    for r in sample_rows:
        conn_points.append({"t": r["ts"], "conns": r["conns"], "up": r["speed_in"], "down": r["speed_out"]})
    if len(conn_points) > 240:
        stride = max(1, len(conn_points) // 240)
        conn_points = conn_points[::stride]
    return {"traffic": traffic, "connections": conn_points}


def build_overview(range_key: str = "1h") -> dict:
    snap = collector.snapshot()
    proxy = snap["proxy"]
    start_iso = range_start_iso()
    now = datetime.now(timezone.utc)

    totals = db.query_one(
        "SELECT COUNT(*) AS sessions, COUNT(DISTINCT client_ip) AS clients, "
        "COALESCE(SUM(bytes_up),0) AS up, COALESCE(SUM(bytes_down),0) AS down "
        "FROM sessions WHERE ended_at >= ?",
        (start_iso,),
    )
    since24 = db.iso(now - timedelta(hours=24))
    totals24 = db.query_one(
        "SELECT COUNT(*) AS sessions, COUNT(DISTINCT client_ip) AS clients, "
        "COALESCE(SUM(bytes_up),0) AS up, COALESCE(SUM(bytes_down),0) AS down "
        "FROM sessions WHERE ended_at >= ?",
        (since24,),
    )
    s24 = db.query_one("SELECT COUNT(*) AS n FROM sessions WHERE ended_at >= ?", (since24,))
    if totals24 is None:
        totals24 = {"sessions": 0, "clients": 0, "up": 0, "down": 0}
    errors_total = db.query_one("SELECT COUNT(*) AS n FROM events WHERE level='ERROR'")
    errors_24h = db.query_one("SELECT COUNT(*) AS n FROM events WHERE ts >= ? AND level='ERROR'", (since24,))
    warn_total = db.query_one("SELECT COUNT(*) AS n FROM events WHERE level='WARN'")
    warn_24h = db.query_one("SELECT COUNT(*) AS n FROM events WHERE ts >= ? AND level='WARN'", (since24,))
    dc_rows = db.query(
        "SELECT dc, COUNT(*) AS sessions, COUNT(DISTINCT client_ip) AS clients, "
        "COALESCE(SUM(bytes_up+bytes_down),0) AS bytes "
        "FROM sessions WHERE ended_at >= ? GROUP BY dc ORDER BY bytes DESC",
        (db.iso(cutoff(range_key)),),
    )
    recent_errors = db.query(
        "SELECT id, ts, level, category, ip, message FROM events WHERE level IN ('WARN','ERROR') "
        "ORDER BY id DESC LIMIT 6"
    )
    series = build_series(range_key)
    metrics = dict(snap["metrics"])
    return {
        "proxy": proxy,
        "metrics": metrics,
        "totals": {
            "sessions": totals["sessions"] if totals else 0,
            "clients": totals["clients"] if totals else 0,
            "bytes_up": totals["up"] if totals else 0,
            "bytes_down": totals["down"] if totals else 0,
            "bytes_total": (totals["up"] + totals["down"]) if totals else 0,
            "sessions_24h": totals24["sessions"],
            "clients_24h": totals24["clients"],
            "bytes_up_24h": totals24["up"],
            "bytes_down_24h": totals24["down"],
            "bytes_total_24h": totals24["up"] + totals24["down"],
        },
        "errors": {"total": errors_total["n"] if errors_total else 0, "last_24h": errors_24h["n"] if errors_24h else 0},
        "warnings": {"total": warn_total["n"] if warn_total else 0, "last_24h": warn_24h["n"] if warn_24h else 0},
        "active": snap["active"],
        "active_error": snap.get("active_error"),
        "series": series,
        "dc": [row_dict(r) for r in dc_rows],
        "recent_errors": [dict(row_dict(r), message=mask_text(r["message"])) for r in recent_errors],
        "range": range_key,
        "generated_at": db.now_iso(),
    }


def _client_ip(request: Request) -> str:
    return security.client_ip(request)


# ── health/overview ──────────────────────────────────────────────────────────

@app.get("/api/health")
def api_health():
    return {"ok": True, "ts": db.now_iso()}


@app.get("/api/overview")
def api_overview(range_key: str = Query("1h", alias="range")):
    if range_key not in RANGES:
        range_key = "1h"
    return build_overview(range_key)


# ── clients ──────────────────────────────────────────────────────────────────

def _active_map() -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in collector.snapshot().get("active", []):
        ip = str(item.get("ip") or "")
        if ip:
            counts[ip] = counts.get(ip, 0) + 1
    return counts


@app.get("/api/clients")
def api_clients(
    range_key: str = Query("24h", alias="range"),
    since: str | None = None,
    q: str | None = Query(None, max_length=64),
    active: bool = False,
    sort: str = "last_seen",
    order: str = "desc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100000),
):
    if range_key not in CLIENT_RANGES:
        raise HTTPException(400, "Некорректный диапазон")
    start = _start_for(range_key, since)
    query = (q or "").strip() or None
    sort_sql = CLIENT_SORTS.get(sort, "last_seen")
    order_sql = "ASC" if str(order).lower() == "asc" else "DESC"
    active_map = _active_map() if active else {}

    where = ["ended_at >= ?"]
    params: list = [start]
    if query:
        where.append("client_ip LIKE ?")
        params.append(f"%{query}%")
    if active:
        if not active_map:
            return {
                "items": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "range": range_key,
                "generated_at": db.now_iso(),
                "note": "Активных TCP-соединений сейчас нет",
            }
        placeholders = ",".join("?" for _ in active_map)
        where.append(f"client_ip IN ({placeholders})")
        params.extend(active_map.keys())

    cache_key = (start, query or "", bool(active), tuple(sorted(active_map)), sort_sql, order_sql, limit, offset)
    if not active:
        cached = _cache_get("clients", cache_key, 15)
        if cached is not None:
            return cached

    from_where = "FROM sessions WHERE " + " AND ".join(where)
    total_row = db.query_one(f"SELECT COUNT(*) AS n FROM (SELECT client_ip {from_where} GROUP BY client_ip)", tuple(params))
    total = int(total_row["n"]) if total_row else 0
    rows = db.query(
        f"SELECT client_ip, COUNT(*) AS sessions, COALESCE(SUM(bytes_up),0) AS bytes_up, "
        f"COALESCE(SUM(bytes_down),0) AS bytes_down, "
        f"COALESCE(SUM(bytes_up),0)+COALESCE(SUM(bytes_down),0) AS bytes_total, "
        f"MIN(COALESCE(started_at, ended_at)) AS first_seen, MAX(ended_at) AS last_seen "
        f"{from_where} GROUP BY client_ip ORDER BY {sort_sql} {order_sql} LIMIT ? OFFSET ?",
        tuple(params + [limit, offset]),
    )
    items = []
    for row in rows:
        ip = row["client_ip"]
        items.append(
            {
                "client_ip": ip,
                "sessions": int(row["sessions"] or 0),
                "bytes_up": int(row["bytes_up"] or 0),
                "bytes_down": int(row["bytes_down"] or 0),
                "bytes_total": int(row["bytes_total"] or 0),
                "first_seen": row["first_seen"],
                "last_seen": row["last_seen"],
                "active": ip in active_map,
                "active_connections": int(active_map.get(ip, 0)),
                "device": devices.lookup(ip),
                "key": None,
                "key_note": "Прокси не указывает MTProto-ключ в логе сессии",
            }
        )
    result = {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "range": range_key,
        "generated_at": db.now_iso(),
        "note": (
            "Агрегация по завершённым сессиям; активные TCP-соединения учитываются отдельно. "
            "Ключ и DC активной сессии прокси не сообщает; устройство определяется приблизительно."
        ),
    }
    if not active:
        _cache_put("clients", cache_key, result)
    return result


@app.get("/api/clients/{ip}")
def api_client_detail(
    ip: str,
    range_key: str = Query("7d", alias="range"),
    since: str | None = None,
):
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise HTTPException(400, "Некорректный IP-адрес")
    if range_key not in CLIENT_RANGES:
        raise HTTPException(400, "Некорректный диапазон")
    start = _start_for(range_key, since)
    cache_key = (ip, start)
    cached = _cache_get("client", cache_key, 10)
    if cached is not None:
        return cached

    summary = db.query_one(
        "SELECT COUNT(*) AS sessions, COALESCE(SUM(bytes_up),0) AS bytes_up, "
        "COALESCE(SUM(bytes_down),0) AS bytes_down, "
        "MIN(COALESCE(started_at, ended_at)) AS first_seen, MAX(ended_at) AS last_seen "
        "FROM sessions WHERE client_ip=? AND ended_at>=?",
        (ip, start),
    )
    active_items = [
        dict(item, device=devices.lookup(ip))
        for item in collector.snapshot().get("active", [])
        if item.get("ip") == ip
    ]
    sessions = int(summary["sessions"] or 0) if summary else 0
    if sessions == 0 and not active_items:
        raise HTTPException(404, "Клиент не найден за выбранный период")
    dcs = db.query(
        "SELECT dc, COUNT(*) AS sessions, COALESCE(SUM(bytes_up+bytes_down),0) AS bytes "
        "FROM sessions WHERE client_ip=? AND ended_at>=? GROUP BY dc ORDER BY bytes DESC",
        (ip, start),
    )
    recent_rows = db.query(
        "SELECT id, client_ip, client_port, dc, media, kind, closed_by, bytes_up, bytes_down, "
        "duration, started_at, ended_at, line FROM sessions WHERE client_ip=? AND ended_at>=? "
        "ORDER BY ended_at DESC LIMIT 50",
        (ip, start),
    )
    recent = []
    for row in recent_rows:
        item = row_dict(row)
        item["device"] = devices.lookup(ip)
        recent.append(item)
    result = {
        "client_ip": ip,
        "sessions": sessions,
        "bytes_up": int(summary["bytes_up"] or 0) if summary else 0,
        "bytes_down": int(summary["bytes_down"] or 0) if summary else 0,
        "bytes_total": (int(summary["bytes_up"] or 0) + int(summary["bytes_down"] or 0)) if summary else 0,
        "first_seen": summary["first_seen"] if summary else None,
        "last_seen": summary["last_seen"] if summary else None,
        "active": bool(active_items),
        "active_connections": len(active_items),
        "active_items": active_items,
        "device": devices.lookup(ip),
        "dcs": [row_dict(r) for r in dcs],
        "recent": recent,
        "key": None,
        "key_supported": False,
        "key_note": "Прокси не указывает MTProto-ключ в логе сессии; привязка клиента к ключу невозможна.",
        "range": range_key,
        "generated_at": db.now_iso(),
        "note": "Сессии — только завершённые. Активные TCP-соединения показаны отдельно.",
    }
    _cache_put("client", cache_key, result)
    return result


# ── metrics history ──────────────────────────────────────────────────────────

@app.get("/api/metrics/history")
def api_metrics_history(
    range_key: str = Query("1h", alias="range"),
    since: str | None = None,
    fields: str = "cpu_host,cpu_proxy",
    step: int | None = Query(None, ge=5, le=3600),
):
    if range_key not in ("30m", "1h", "6h", "24h", "7d"):
        raise HTTPException(400, "Некорректный диапазон")
    selected = []
    for part in str(fields or "").split(","):
        name = part.strip()
        if not name:
            continue
        if name not in METRIC_FIELDS:
            raise HTTPException(400, f"Недопустимое поле метрики: {name}")
        if name not in selected:
            selected.append(name)
    if not selected:
        raise HTTPException(400, "Не выбраны поля метрики")
    if len(selected) > 8:
        raise HTTPException(400, "Слишком много полей метрики")
    bucket = int(step or METRIC_STEPS[range_key])
    if not 5 <= bucket <= 3600:
        raise HTTPException(400, "Некорректный шаг")
    start = db.iso(cutoff(range_key, since))
    cache_key = (range_key, start, tuple(selected), bucket)
    cached = _cache_get("metrics", cache_key, 20)
    if cached is not None:
        return cached

    columns = ", ".join(selected)
    rows = db.query(f"SELECT ts, {columns} FROM samples WHERE ts>=? ORDER BY ts", (start,))
    buckets: dict[int, dict[str, list[float]]] = {}
    raw: dict[str, list[float]] = {name: [] for name in selected}
    for row in rows:
        dt = db.parse_iso(row["ts"])
        if not dt:
            continue
        ts = int(dt.timestamp()) // bucket * bucket
        target = buckets.setdefault(ts, {name: [] for name in selected})
        for name in selected:
            value = row[name]
            if value is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            target[name].append(number)
            raw[name].append(number)
    points = []
    for ts in sorted(buckets):
        point = {"t": datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")}
        for name in selected:
            values = buckets[ts].get(name) or []
            if values:
                point[name] = round(sum(values) / len(values), 3)
        if len(point) > 1:
            points.append(point)
    if len(points) > 300:
        stride = max(1, len(points) // 300)
        points = points[::stride]
    stats = {}
    for name in selected:
        values = raw[name]
        if values:
            stats[name] = {
                "min": round(min(values), 3),
                "avg": round(sum(values) / len(values), 3),
                "max": round(max(values), 3),
                "last": round(values[-1], 3),
            }
        else:
            stats[name] = {"min": None, "avg": None, "max": None, "last": None}
    min_ts = db.query_one("SELECT MIN(ts) AS t FROM samples")
    result = {
        "points": points,
        "stats": stats,
        "fields": selected,
        "range": range_key,
        "step": bucket,
        "history_start": min_ts["t"] if min_ts else None,
        "generated_at": db.now_iso(),
        "source": "samples",
    }
    _cache_put("metrics", cache_key, result)
    return result


# ── active connections ───────────────────────────────────────────────────────

@app.get("/api/connections/active")
def api_connections_active():
    snap = collector.snapshot()
    if snap.get("active_error"):
        raise HTTPException(503, f"Не удалось получить активные подключения: {snap['active_error']}")
    proxy_port = int(snap["proxy"].get("proxy_port") or settings.PROXY_PORT)
    items = sorted(snap["active"], key=lambda c: c.get("first_seen") or "")
    for c in items:
        c["device"] = devices.lookup(c["ip"])
        c["client_id"] = f"{c['ip']}:{c['port']}"
        c["server_id"] = f"{c.get('local_ip', '')}:{c.get('local_port', '')}"
        c["host_ip"] = settings.PUBLIC_HOST
        c["host_port"] = proxy_port
    return {
        "items": items,
        "count": len(items),
        "note": (
            "Активные TCP-сессии клиентов, обнаруженные панелью в сетевом namespace контейнера. "
            "Время «с» — момент первого обнаружения панелью. Ключ и DC для активной сессии прокси не сообщает."
        ),
        "updated_at": snap["updated_at"],
    }


@app.post("/api/connections/kill")
def api_connection_kill(request: Request, payload: dict = Body(...)):
    ip = str(payload.get("ip") or "").strip()
    port = payload.get("port")
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise HTTPException(400, "Некорректный порт")
    started = time.time()
    try:
        with ops.operation("разрыв соединения"):
            ok, msg = netns.kill_connection(ip, port)
            if not ok:
                raise HTTPException(400, msg)
            # give the kernel a moment, then verify
            time.sleep(0.3)
            snap = collector.snapshot()
            still = any(c["ip"] == ip and c["port"] == port for c in snap["active"])
    except ops.Busy as exc:
        raise HTTPException(409, str(exc))
    audit.record(
        "connection.kill",
        f"{ip}:{port}",
        True,
        {"still_present": still},
        _client_ip(request),
        int((time.time() - started) * 1000),
    )
    return {"ok": True, "message": msg, "still_present": still}


# ── connection history ───────────────────────────────────────────────────────

HISTORY_SORT = {"ended_at", "bytes_up", "bytes_down", "duration", "client_ip", "dc"}


@app.get("/api/connections/history")
def api_history(
    ip: str | None = None,
    dc: int | None = None,
    closed_by: str | None = None,
    kind: str | None = None,
    range_key: str = Query("24h", alias="range"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("ended_at"),
    order: str = Query("desc"),
):
    where = ["ended_at >= ?"]
    params: list = [db.iso(cutoff(range_key))]
    if ip:
        where.append("client_ip LIKE ?")
        params.append(f"%{ip}%")
    if dc:
        where.append("dc = ?")
        params.append(int(dc))
    if closed_by in ("client", "upstream"):
        where.append("closed_by = ?")
        params.append(closed_by)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    clause = " AND ".join(where)
    total = db.query_one(f"SELECT COUNT(*) AS n FROM sessions WHERE {clause}", tuple(params))["n"]
    if sort not in HISTORY_SORT:
        sort = "ended_at"
    order_sql = "ASC" if str(order).lower() == "asc" else "DESC"
    rows = db.query(
        f"SELECT * FROM sessions WHERE {clause} ORDER BY {sort} {order_sql}, id DESC LIMIT ? OFFSET ?",
        tuple(params + [limit, offset]),
    )
    items = []
    for r in rows:
        d = row_dict(r)
        d.pop("line_hash", None)
        items.append(d)
    devs = devices.lookup_many([d["client_ip"] for d in items])
    for d in items:
        d["device"] = devs.get(d["client_ip"], devices.lookup(d["client_ip"]))
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/connections/history/{sid}")
def api_history_item(sid: int):
    row = db.query_one("SELECT * FROM sessions WHERE id=?", (sid,))
    if not row:
        raise HTTPException(404, "Сессия не найдена")
    d = row_dict(row)
    d["device"] = devices.lookup(d["client_ip"])
    return d


@app.get("/api/devices/{ip}")
def api_device_get(ip: str):
    return devices.lookup(ip)


@app.put("/api/devices/{ip}")
def api_device_set(ip: str, request: Request, payload: dict = Body(...)):
    family = str(payload.get("family") or "").lower()
    try:
        result = devices.set_label(ip, family)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    audit.record("device.label", ip, True, {"family": family}, _client_ip(request))
    return {"ok": True, "device": result}


@app.delete("/api/devices/{ip}")
def api_device_reset(ip: str, request: Request):
    try:
        result = devices.clear_label(ip)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    audit.record("device.reset", ip, True, None, _client_ip(request))
    return {"ok": True, "device": result}


# ── logs ─────────────────────────────────────────────────────────────────────

def _logs_where(
    level: str | None,
    category: str | None,
    ip: str | None,
    q: str | None,
    range_key: str | None,
    since: str | None,
    until: str | None,
) -> tuple[str, list]:
    where = ["1=1"]
    params: list = []
    if since or range_key:
        where.append("ts >= ?")
        params.append(db.iso(cutoff(range_key, since)))
    if until:
        dt = db.parse_iso(until)
        if dt:
            where.append("ts <= ?")
            params.append(db.iso(dt))
    if level and level != "ALL":
        levels = [x.strip().upper() for x in level.split(",") if x.strip()]
        if levels:
            where.append("level IN (" + ",".join("?" for _ in levels) + ")")
            params.extend(levels)
    if category and category != "ALL":
        where.append("category = ?")
        params.append(category)
    if ip:
        where.append("ip LIKE ?")
        params.append(f"%{ip}%")
    if q:
        where.append("message LIKE ?")
        params.append(f"%{q}%")
    return " AND ".join(where), params


@app.get("/api/logs")
def api_logs(
    level: str | None = None,
    category: str | None = None,
    ip: str | None = None,
    q: str | None = None,
    range_key: str = Query("1h", alias="range"),
    since: str | None = None,
    until: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    clause, params = _logs_where(level, category, ip, q, range_key, since, until)
    total = db.query_one(f"SELECT COUNT(*) AS n FROM events WHERE {clause}", tuple(params))["n"]
    rows = db.query(
        f"SELECT id, ts, level, category, module, ip, message FROM events WHERE {clause} "
        f"ORDER BY id DESC LIMIT ? OFFSET ?",
        tuple(params + [limit, offset]),
    )
    items = []
    for r in rows:
        d = row_dict(r)
        d["message"] = mask_text(d["message"])
        items.append(d)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/logs/export")
def api_logs_export(
    format: str = Query("txt"),
    level: str | None = None,
    category: str | None = None,
    ip: str | None = None,
    q: str | None = None,
    range_key: str = Query("24h", alias="range"),
    since: str | None = None,
    until: str | None = None,
):
    clause, params = _logs_where(level, category, ip, q, range_key, since, until)
    rows = db.query(
        f"SELECT ts, level, category, module, ip, message FROM events WHERE {clause} ORDER BY id ASC LIMIT 50000",
        tuple(params),
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";")
        writer.writerow(["time", "level", "category", "module", "ip", "message"])
        for r in rows:
            writer.writerow([r["ts"], r["level"], r["category"], r["module"] or "", r["ip"] or "", mask_text(r["message"])])
        data = "\ufeff" + buf.getvalue()
        return Response(
            content=data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="tgwsproxy-logs-{stamp}.csv"'},
        )
    lines = [f"[{r['ts']}] {r['level']:<5} {r['category']:<8} {r['ip'] or '-':<18} {mask_text(r['message'])}" for r in rows]
    return PlainTextResponse(
        "\n".join(lines) + "\n",
        headers={"Content-Disposition": f'attachment; filename="tgwsproxy-logs-{stamp}.txt"'},
    )


@app.get("/api/logs/stream")
async def api_logs_stream(
    request: Request,
    after_id: int = 0,
    level: str | None = None,
    q: str | None = None,
):
    async def gen():
        cursor = int(after_id)
        if cursor <= 0:
            row = db.query_one("SELECT COALESCE(MAX(id),0) AS m FROM events")
            cursor = int(row["m"]) if row else 0
        last_ping = asyncio.get_event_loop().time()
        last_auth = last_ping
        levels = [x.strip().upper() for x in (level or "").split(",") if x.strip() and x != "ALL"]
        while True:
            if await request.is_disconnected():
                break
            now = asyncio.get_event_loop().time()
            if now - last_auth > 5:
                if not security.load_session(request):
                    break
                last_auth = now
            rows = db.query("SELECT id, ts, level, category, ip, message FROM events WHERE id > ? ORDER BY id ASC LIMIT 300", (cursor,))
            for r in rows:
                cursor = max(cursor, r["id"])
                if levels and r["level"] not in levels:
                    continue
                if q and q.lower() not in (r["message"] or "").lower():
                    continue
                payload = row_dict(r)
                payload["message"] = mask_text(payload["message"])
                yield f"event: log\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            now = asyncio.get_event_loop().time()
            if now - last_ping > 15:
                last_ping = now
                yield "event: ping\ndata: {}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/stream")
async def api_stream(request: Request, range_key: str = Query("1h", alias="range")):
    if range_key not in RANGES:
        range_key = "1h"

    async def gen():
        last_auth = asyncio.get_event_loop().time()
        while True:
            if await request.is_disconnected():
                break
            now = asyncio.get_event_loop().time()
            if now - last_auth > 5:
                if not security.load_session(request):
                    break
                last_auth = now
            try:
                payload = build_overview(range_key)
            except Exception as exc:  # noqa: BLE001
                payload = {"error": str(exc)}
            yield f"event: overview\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            await asyncio.sleep(3.0)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ── keys ─────────────────────────────────────────────────────────────────────

KEY_RE = re.compile(r"^[0-9a-f]{32}$")


def _check_key(key: str) -> str:
    key = key.lower()
    if not KEY_RE.match(key):
        raise HTTPException(400, "Некорректный ключ")
    return key


def _key_by_id(identifier: str) -> str:
    key = keys.resolve_key(identifier)
    if not key:
        raise HTTPException(404, "Ключ не найден")
    return key


def _mask_key(key: str) -> str:
    return key[:4] + "…" + key[-4:] if len(key) > 8 else "***"


@app.get("/api/keys")
def api_keys():
    return keys.list_keys()


@app.post("/api/keys")
def api_keys_add(request: Request, payload: dict = Body(default={})):
    started = time.time()
    comment = str(payload.get("comment") or "")
    try:
        with ops.operation("создание ключа"):
            result = keys.add_key(comment)
    except ops.Busy as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        audit.record("key.add", None, False, {"error": str(exc), "comment": comment}, _client_ip(request), int((time.time() - started) * 1000))
        raise HTTPException(400, str(exc))
    if not result.get("ok"):
        audit.record("key.add", None, False, {"error": result.get("error"), "comment": comment}, _client_ip(request), int((time.time() - started) * 1000))
        raise HTTPException(400, result.get("error") or "Не удалось добавить ключ")
    audit.record(
        "key.add",
        _mask_key(result.get("key") or ""),
        True,
        {"comment": comment, "backup": result.get("backup")},
        _client_ip(request),
        int((time.time() - started) * 1000),
    )
    return result


@app.patch("/api/keys/{key_id}")
def api_keys_comment(key_id: str, request: Request, payload: dict = Body(...)):
    key = _key_by_id(key_id)
    result = keys.set_comment(key, str(payload.get("comment") or ""))
    audit.record("key.comment", _mask_key(key), True, {"comment": result.get("comment")}, _client_ip(request))
    return result


@app.post("/api/keys/{key_id}/reveal")
def api_keys_reveal(key_id: str, request: Request, payload: dict = Body(...)):
    sess = getattr(request.state, "session", None)
    user = security.get_user_by_id(sess["user_id"]) if sess else None
    if not user or not security.verify_password(user["password_hash"], str(payload.get("password") or "")):
        security.log_event("secret_reveal_failed", request, username=user["username"] if user else None, detail=key_id[:8])
        time.sleep(0.5)
        raise HTTPException(400, "Пароль неверен")
    key = _key_by_id(key_id)
    links = keys.links_for(key, config_editor.effective_env())
    security.log_event("secret_revealed", request, username=user["username"], detail=f"key={key_id[:8]}")
    return {
        "id": key_id,
        "key": key,
        "masked": key[:4] + "…" + key[-4:],
        "link_lan": links.get("link_lan"),
        "link_external": links.get("link_external"),
    }


@app.post("/api/keys/{key_id}/disable")
def api_keys_disable(key_id: str, request: Request):
    key = _key_by_id(key_id)
    started = time.time()
    try:
        with ops.operation("отключение ключа"):
            result = keys.disable_key(key)
    except ops.Busy as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        audit.record("key.disable", _mask_key(key), False, {"error": str(exc)}, _client_ip(request), int((time.time() - started) * 1000))
        raise HTTPException(400, str(exc))
    if not result.get("ok"):
        audit.record("key.disable", _mask_key(key), False, {"error": result.get("error")}, _client_ip(request), int((time.time() - started) * 1000))
        raise HTTPException(400, result.get("error") or "Не удалось отключить ключ")
    audit.record("key.disable", _mask_key(key), True, {"backup": result.get("backup")}, _client_ip(request), int((time.time() - started) * 1000))
    return result


@app.post("/api/keys/{key_id}/enable")
def api_keys_enable(key_id: str, request: Request):
    key = _key_by_id(key_id)
    started = time.time()
    try:
        with ops.operation("включение ключа"):
            result = keys.enable_key(key)
    except ops.Busy as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        audit.record("key.enable", _mask_key(key), False, {"error": str(exc)}, _client_ip(request), int((time.time() - started) * 1000))
        raise HTTPException(400, str(exc))
    if not result.get("ok"):
        audit.record("key.enable", _mask_key(key), False, {"error": result.get("error")}, _client_ip(request), int((time.time() - started) * 1000))
        raise HTTPException(400, result.get("error") or "Не удалось включить ключ")
    audit.record("key.enable", _mask_key(key), True, {"backup": result.get("backup")}, _client_ip(request), int((time.time() - started) * 1000))
    return result


@app.delete("/api/keys/{key_id}")
def api_keys_delete(key_id: str, request: Request):
    key = _key_by_id(key_id)
    started = time.time()
    try:
        with ops.operation("удаление ключа"):
            result = keys.delete_key(key)
    except ops.Busy as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        audit.record("key.delete", _mask_key(key), False, {"error": str(exc)}, _client_ip(request), int((time.time() - started) * 1000))
        raise HTTPException(400, str(exc))
    if not result.get("ok"):
        audit.record("key.delete", _mask_key(key), False, {"error": result.get("error")}, _client_ip(request), int((time.time() - started) * 1000))
        raise HTTPException(400, result.get("error") or "Не удалось удалить ключ")
    audit.record("key.delete", _mask_key(key), True, {"backup": result.get("backup")}, _client_ip(request), int((time.time() - started) * 1000))
    return result


@app.get("/api/keys/{key_id}/stats")
def api_keys_stats(key_id: str):
    return keys.key_stats(_key_by_id(key_id))


# ── service ──────────────────────────────────────────────────────────────────

@app.get("/api/service")
def api_service():
    snap = collector.snapshot()
    try:
        st = dockerctl.status()
    except helper_client.HelperUnavailable as exc:
        raise HTTPException(503, str(exc))
    ok, msg = (False, "не проверено")
    if st.get("running"):
        try:
            env = config_editor.effective_env()
            ok, msg = dockerctl.tcp_check(settings.PUBLIC_HOST, int(env.get("TG_PORT", 1443)))
        except (helper_client.HelperUnavailable, helper_client.HelperError) as exc:
            msg = str(exc)
    return {"state": st, "version": snap["proxy"].get("version"), "port_check": {"ok": ok, "message": msg}, "updated_at": snap["updated_at"]}


def _do_action(action: str) -> dict:
    started = time.time()
    if action == "check":
        st = dockerctl.status()
        env = config_editor.effective_env()
        port = int(env.get("TG_PORT", 1443))
        ok, msg = dockerctl.tcp_check(settings.PUBLIC_HOST, port)
        lines = [
            f"Контейнер: {st.get('state')}",
            f"Health: {st.get('health')}",
            f"Uptime: {st.get('uptime')} c",
            f"Образ: {st.get('image')}",
            f"Порт {port}: {'OK' if ok else 'FAIL'} ({msg})",
            f"Restart policy: {st.get('restart_policy')}",
            f"Версия: {dockerctl.version() or 'н/д'}",
        ]
        return {
            "ok": ok,
            "action": action,
            "duration_ms": int((time.time() - started) * 1000),
            "output": "\n".join(lines),
            "error": None if ok else msg,
            "state": st,
        }
    if action not in ("start", "stop", "restart"):
        raise HTTPException(400, "Неизвестное действие")
    result = helper_client.call("docker.service", timeout=180, action=action)
    result["duration_ms"] = int((time.time() - started) * 1000)
    return result


@app.post("/api/service/action")
async def api_service_action(request: Request, payload: dict = Body(...)):
    action = str(payload.get("action") or "").lower()
    if action not in ("start", "stop", "restart", "check"):
        raise HTTPException(400, "Недопустимое действие")
    started = time.time()
    if action == "check":
        try:
            result = await asyncio.to_thread(_do_action, action)
        except helper_client.HelperUnavailable as exc:
            raise HTTPException(503, str(exc))
        except helper_client.HelperError as exc:
            raise HTTPException(502, str(exc))
        audit.record("service.check", "tgwsproxy", bool(result.get("ok")), {"output": result.get("output")}, _client_ip(request), int((time.time() - started) * 1000))
        return result
    try:
        with ops.operation(f"service.{action}"):
            result = await asyncio.to_thread(_do_action, action)
    except ops.Busy as exc:
        raise HTTPException(409, str(exc))
    except helper_client.HelperUnavailable as exc:
        raise HTTPException(503, str(exc))
    except helper_client.HelperError as exc:
        raise HTTPException(502, str(exc))
    audit.record(
        f"service.{action}",
        "tgwsproxy",
        bool(result.get("ok")),
        {"error": result.get("error"), "state": (result.get("state") or {}).get("state")},
        _client_ip(request),
        int((time.time() - started) * 1000),
    )
    if not result.get("ok"):
        alerts.notify("service_action", f"Операция {action} завершилась ошибкой: {result.get('error')}", "error")
    return result


@app.get("/api/service/logs")
def api_service_logs(lines: int = Query(100, ge=1, le=2000)):
    try:
        result = helper_client.call("docker.logs", timeout=35, lines=lines)
    except helper_client.HelperUnavailable as exc:
        raise HTTPException(503, str(exc))
    except helper_client.HelperError as exc:
        raise HTTPException(502, str(exc))
    return {"ok": bool(result.get("ok")), "text": mask_text(str(result.get("text") or "")), "lines": lines}


@app.get("/api/service/config")
def api_service_config():
    return config_editor.snapshot()


# ── config ───────────────────────────────────────────────────────────────────

@app.get("/api/config")
def api_config():
    return config_editor.snapshot()


@app.put("/api/config")
async def api_config_put(request: Request, payload: dict = Body(...)):
    env_updates = payload.get("environment") or {}
    if not isinstance(env_updates, dict):
        raise HTTPException(400, "environment должен быть объектом")
    dc_targets = payload.get("dc_targets")
    if dc_targets is not None and not isinstance(dc_targets, list):
        raise HTTPException(400, "dc_targets должен быть массивом")
    started = time.time()
    try:
        with ops.operation("применение конфигурации"):
            result = await asyncio.to_thread(
                config_editor.apply,
                env_updates={str(k): str(v) for k, v in env_updates.items()},
                dc_targets=dc_targets,
                tag=str(payload.get("tag") or "config"),
            )
    except ops.Busy as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        audit.record(
            "config.apply",
            "docker-compose.yml",
            False,
            {"error": str(exc), "keys": sorted(env_updates.keys())},
            _client_ip(request),
            int((time.time() - started) * 1000),
        )
        raise HTTPException(400, str(exc))
    audit.record(
        "config.apply",
        "docker-compose.yml",
        bool(result.get("ok")),
        {
            "changed": sorted(env_updates.keys()),
            "dc_targets": dc_targets,
            "backup": result.get("backup"),
            "noop": result.get("noop"),
            "error": result.get("error"),
        },
        _client_ip(request),
        int((time.time() - started) * 1000),
    )
    if not result.get("ok"):
        alerts.notify("config_apply", f"Ошибка применения конфигурации: {result.get('error')}", "error")
    return result


@app.get("/api/config/backups")
def api_backups():
    return {"items": config_editor.list_backups()}


@app.post("/api/config/restore")
async def api_restore(request: Request, payload: dict = Body(...)):
    name = str(payload.get("name") or "")
    started = time.time()
    try:
        with ops.operation("восстановление конфигурации"):
            result = await asyncio.to_thread(config_editor.restore_backup, name)
    except ops.Busy as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        audit.record("config.restore", name, False, {"error": str(exc)}, _client_ip(request), int((time.time() - started) * 1000))
        raise HTTPException(400, str(exc))
    audit.record(
        "config.restore",
        name,
        bool(result.get("ok")),
        {"error": result.get("error"), "backup_before_restore": result.get("backup_before_restore")},
        _client_ip(request),
        int((time.time() - started) * 1000),
    )
    if not result.get("ok"):
        alerts.notify("config_restore", f"Ошибка восстановления конфигурации: {result.get('error')}", "error")
    return result


@app.post("/api/config/backups/{name}/download")
def api_backup_download(name: str, request: Request, payload: dict = Body(...)):
    sess = getattr(request.state, "session", None)
    user = security.get_user_by_id(sess["user_id"]) if sess else None
    if not user or not security.verify_password(user["password_hash"], str(payload.get("password") or "")):
        security.log_event("backup_download_failed", request, username=user["username"] if user else None, detail=name)
        time.sleep(0.5)
        raise HTTPException(400, "Пароль неверен")
    try:
        content = config_editor.read_backup(name)
    except helper_client.HelperUnavailable as exc:
        raise HTTPException(503, str(exc))
    except helper_client.HelperError as exc:
        raise HTTPException(400, str(exc))
    security.log_event("backup_downloaded", request, username=user["username"], detail=name)
    return Response(
        content=content,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{name}.tar.gz"'},
    )


# ── diagnostics ──────────────────────────────────────────────────────────────

@app.get("/api/diagnostics")
def api_diagnostics():
    return {
        "quick": diagnostics.latest("quick"),
        "probe": diagnostics.latest("probe"),
        "history": diagnostics.history(15),
        "ops": ops.status(),
    }


@app.post("/api/diagnostics/check")
async def api_diagnostics_check(request: Request):
    started = time.time()
    try:
        result = await asyncio.to_thread(diagnostics.quick_check)
    except helper_client.HelperUnavailable as exc:
        raise HTTPException(503, str(exc))
    audit.record(
        "diagnostics.check",
        "channel",
        bool(result.get("ok")),
        {"status": result.get("status"), "summary": result.get("summary")},
        _client_ip(request),
        int((time.time() - started) * 1000),
    )
    if result.get("status") == "fail":
        alerts.notify("diagnostics", f"Диагностика: {result.get('summary')}", "error")
    return result


@app.post("/api/diagnostics/probe")
async def api_diagnostics_probe(request: Request):
    raise HTTPException(403, "Сквозная проверка отключена: временные контейнеры запрещены")


@app.get("/api/ops")
def api_ops():
    return ops.status()


@app.get("/api/storage")
def api_storage():
    return storage.snapshot()


# ── alerts ───────────────────────────────────────────────────────────────────

@app.get("/api/alerts")
def api_alerts():
    return {"settings": alerts.public(), "history": alerts.history(50)}


@app.put("/api/alerts")
def api_alerts_put(request: Request, payload: dict = Body(...)):
    try:
        settings_public = alerts.save(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    audit.record(
        "alerts.settings",
        "notifications",
        True,
        {"enabled": settings_public.get("enabled"), "configured": settings_public.get("configured")},
        _client_ip(request),
    )
    return {"ok": True, "settings": settings_public}


@app.post("/api/alerts/test")
def api_alerts_test(request: Request):
    result = alerts.send_test()
    audit.record("alerts.test", "notifications", bool(result.get("ok")), {"error": result.get("error")}, _client_ip(request))
    return result


# ── audit ────────────────────────────────────────────────────────────────────

@app.get("/api/audit")
def api_audit(limit: int = Query(100, ge=1, le=500), action: str | None = None, ok: bool | None = None):
    return audit.list_entries(limit=limit, action=action, ok=ok)


# ── static SPA ───────────────────────────────────────────────────────────────

ASSETS = settings.FRONTEND_DIR / "assets"
if ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS)), name="assets")


@app.get("/{full_path:path}")
def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not found")
    index = settings.FRONTEND_DIR / "index.html"
    if not index.exists():
        return JSONResponse({"detail": "Frontend не собран", "hint": "npm run build в /opt/tgws-panel/frontend-src"}, status_code=503)
    return FileResponse(index)
