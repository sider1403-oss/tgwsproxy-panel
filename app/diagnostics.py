"""Channel diagnostics: quick checks and an on-demand end-to-end MTProto probe."""
from __future__ import annotations

import json
import random
import re
import socket
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config_editor, config_schema, db, dockerctl, helper_client, keys, logutil, mask, settings

DOMAIN_RE = re.compile(r"kws\d+\.[A-Za-z0-9.-]+")
RESULT_LINE_RE = re.compile(r"^\s*([A-Za-z0-9.:_-]+)\s+\.\.\.\s+\[(OK|FAIL|SKIP)\s*\]\s*(\d+)?\s*ms")
WORKER: "Worker | None" = None


def _iso(dt: datetime) -> str:
    return db.iso(dt)


def _row(row) -> dict | None:
    if row is None:
        return None
    d = {k: row[k] for k in row.keys()}
    d["ok"] = bool(d["ok"])
    try:
        detail = json.loads(d["detail"]) if d["detail"] else {}
        if not isinstance(detail, dict):
            detail = {}
    except ValueError:
        detail = {}
    d.update(detail)
    d["detail"] = detail
    return d


def latest(kind: str) -> dict | None:
    return _row(db.query_one("SELECT * FROM diagnostics WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,)))


def history(limit: int = 20) -> list[dict]:
    rows = db.query("SELECT * FROM diagnostics ORDER BY id DESC LIMIT ?", (limit,))
    return [_row(r) for r in rows if r is not None]


def _store(kind: str, ok: bool, status: str, summary: str, detail: dict, duration_ms: int) -> dict:
    db.execute(
        "INSERT INTO diagnostics(ts,kind,ok,status,summary,detail,duration_ms) VALUES(?,?,?,?,?,?,?)",
        (db.now_iso(), kind, 1 if ok else 0, status, summary, json.dumps(detail, ensure_ascii=False), duration_ms),
    )
    db.execute(
        "DELETE FROM diagnostics WHERE id NOT IN (SELECT id FROM diagnostics ORDER BY id DESC LIMIT 500)"
    )
    result = {
        "ts": db.now_iso(),
        "kind": kind,
        "ok": ok,
        "status": status,
        "summary": summary,
        "duration_ms": duration_ms,
        **detail,
    }
    return result


def _resolve(host: str, timeout: float = 2.0) -> tuple[str | None, str | None]:
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(socket.getaddrinfo, host, None, socket.AF_INET, socket.SOCK_STREAM)
        try:
            infos = fut.result(timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)
    if not infos:
        return None, "нет адресов"
    return infos[0][4][0], None


def _tcp(host: str, port: int, timeout: float = 1.8) -> tuple[bool, int | None, str | None]:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, int((time.perf_counter() - started) * 1000), None
    except OSError as exc:
        return False, None, str(exc)


def _cf_hosts(limit: int = 6) -> tuple[list[str], str | None]:
    env = config_editor.effective_env()
    raw = (env.get("TG_CF_DOMAIN") or "").strip()
    if raw:
        hosts = [x.strip() for x in raw.split(",") if x.strip()]
        return hosts[:limit], "конфигурация"
    cutoff = _iso(datetime.now(timezone.utc) - timedelta(hours=6))
    rows = db.query(
        "SELECT message FROM events WHERE ts >= ? AND message LIKE '%kws%' ORDER BY id DESC LIMIT 500",
        (cutoff,),
    )
    found: list[str] = []
    for r in rows:
        for m in DOMAIN_RE.finditer(r["message"] or ""):
            host = m.group(0).rstrip(".")
            if host.endswith("telegram.org"):
                # direct WS hosts, not Cloudflare proxy domains
                continue
            if host not in found:
                found.append(host)
    if found:
        return found[:limit], "журнал"
    return ["kws2.pclead.co.uk"], "fallback"


def _check_cf() -> dict:
    env = config_editor.effective_env()
    plain = str(env.get("TG_CF_DISABLE_TLS", "")).lower() in ("1", "true", "yes")
    primary_port = 80 if plain else 443
    hosts, source = _cf_hosts()
    items: list[dict] = []

    def check(host: str) -> dict:
        ip, dns_err = _resolve(host)
        item = {
            "host": host,
            "dns": ip,
            "ok": False,
            "port": primary_port,
            "latency_ms": None,
            "error": dns_err,
        }
        if not ip:
            return item
        ok, latency, err = _tcp(ip, primary_port)
        if not ok and primary_port == 80:
            ok2, latency2, err2 = _tcp(ip, 443)
            if ok2:
                item.update({"port": 443, "latency_ms": latency2, "ok": True, "error": None})
                return item
            err = f"80: {err}; 443: {err2}"
        item.update({"ok": ok, "latency_ms": latency, "error": None if ok else err})
        return item

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, len(hosts))) as ex:
        futures = [ex.submit(check, h) for h in hosts]
        try:
            for fut in as_completed(futures, timeout=8):
                try:
                    items.append(fut.result())
                except Exception as exc:  # noqa: BLE001
                    items.append({"host": "?", "ok": False, "error": str(exc)})
        except Exception:  # noqa: BLE001 - keep the results we already have
            pass
    elapsed = int((time.perf_counter() - started) * 1000)
    ok_count = sum(1 for i in items if i["ok"])
    if ok_count == 0:
        status = "fail"
        detail = "ни один CF-домен не отвечает"
    elif ok_count < len(items):
        status = "warn"
        detail = f"отвечают {ok_count} из {len(items)} CF-доменов (источник: {source})"
    else:
        status = "ok"
        detail = f"доступны {ok_count} из {len(items)} CF-доменов (источник: {source})"
    return {
        "id": "cf",
        "label": "Cloudflare / CF-домены",
        "status": status,
        "latency_ms": elapsed,
        "detail": detail,
        "items": sorted(items, key=lambda x: x["host"]),
    }


def _check_dc() -> dict:
    try:
        svc = config_editor.compose_service()
        targets = config_schema.parse_dc_targets([str(x) for x in (svc.get("command") or [])])
    except Exception as exc:  # noqa: BLE001
        return {"id": "dc", "label": "Прямые DC", "status": "skip", "detail": f"не удалось прочитать конфигурацию: {exc}"}
    if not targets:
        return {"id": "dc", "label": "Прямые DC", "status": "skip", "detail": "в конфигурации нет --dc-ip"}

    def check(t: dict) -> dict:
        ok, latency, err = _tcp(t["ip"], 443, timeout=1.2)
        return {"dc": t["dc"], "ip": t["ip"], "ok": ok, "latency_ms": latency, "error": err}

    with ThreadPoolExecutor(max_workers=max(1, len(targets))) as ex:
        items = list(ex.map(check, targets))
    ok_count = sum(1 for i in items if i["ok"])
    if ok_count == len(items):
        status = "ok"
        detail = "прямые DC доступны"
    elif ok_count == 0:
        status = "ok"
        detail = "прямые DC недоступны (ожидаемо при блокировке) — используется CF"
    else:
        status = "warn"
        detail = f"прямые DC доступны частично: {ok_count} из {len(items)}"
    return {"id": "dc", "label": "Прямые DC", "status": status, "detail": detail, "items": items}


def quick_check() -> dict:
    started = time.perf_counter()
    checks: list[dict] = []
    st = dockerctl.status()
    env = config_editor.effective_env()
    port = int(env.get("TG_PORT", settings.PROXY_PORT))

    if not st.get("exists"):
        checks.append({"id": "container", "label": "Контейнер", "status": "fail", "detail": "tgwsproxy не найден"})
    elif not st.get("running"):
        checks.append(
            {"id": "container", "label": "Контейнер", "status": "fail", "detail": f"остановлен (exit {st.get('exit_code')})"}
        )
    else:
        health = st.get("health")
        status = "ok" if health in ("healthy", None) else "warn"
        checks.append(
            {
                "id": "container",
                "label": "Контейнер",
                "status": status,
                "detail": f"{st.get('state')}, health: {health or '—'}, uptime {st.get('uptime')} c",
                "latency_ms": None,
            }
        )

    p_ok, p_lat, p_err = _tcp(settings.PUBLIC_HOST, port, timeout=2.0)
    checks.append(
        {
            "id": "port",
            "label": f"Порт {port}",
            "status": "ok" if p_ok else "fail",
            "latency_ms": p_lat,
            "detail": "TCP-порт отвечает" if p_ok else f"нет ответа: {p_err}",
        }
    )

    try:
        validated = helper_client.call("config.validate", timeout=30)
    except (helper_client.HelperUnavailable, helper_client.HelperError) as exc:
        validated = {"ok": False, "error": str(exc)}
    checks.append(
        {
            "id": "config",
            "label": "Конфигурация compose",
            "status": "ok" if validated.get("ok") else "fail",
            "detail": "валидна" if validated.get("ok") else str(validated.get("error") or "ошибка проверки")[:300],
        }
    )

    cf = _check_cf()
    checks.append(cf)
    dc = _check_dc()
    checks.append(dc)

    cutoff = _iso(datetime.now(timezone.utc) - timedelta(minutes=10))
    warn_count = db.query_one(
        "SELECT COUNT(*) AS n FROM events WHERE ts >= ? AND level IN ('WARN','ERROR')", (cutoff,)
    )["n"]
    sessions_count = db.query_one("SELECT COUNT(*) AS n FROM sessions WHERE ended_at >= ?", (cutoff,))["n"]
    checks.append(
        {
            "id": "logs",
            "label": "Журнал за 10 минут",
            "status": "ok" if warn_count < 60 else "warn",
            "detail": f"предупреждений/ошибок: {warn_count}, завершённых сессий: {sessions_count}",
        }
    )

    statuses = [c["status"] for c in checks if c.get("status")]
    if "fail" in statuses:
        overall = "fail"
    elif "warn" in statuses:
        overall = "warn"
    else:
        overall = "ok"
    failed = [c["label"] for c in checks if c["status"] == "fail"]
    warned = [c["label"] for c in checks if c["status"] == "warn"]
    if overall == "fail":
        summary = "Проблемы: " + ", ".join(failed)
    elif overall == "warn":
        summary = "Работает с замечаниями: " + ", ".join(warned)
    else:
        summary = "Канал в порядке"
    duration = int((time.perf_counter() - started) * 1000)
    return _store("quick", overall != "fail", overall, summary, {"checks": checks}, duration)


def full_probe() -> dict:
    raise RuntimeError("Сквозная проверка отключена: временные контейнеры запрещены")


class Worker(threading.Thread):
    def __init__(self, interval: int = 120) -> None:
        super().__init__(daemon=True, name="panel-diagnostics")
        self.interval = interval
        self.stop_event = threading.Event()

    def run(self) -> None:
        # let the panel and collector settle after start
        if self.stop_event.wait(8):
            return
        while not self.stop_event.is_set():
            try:
                quick_check()
            except Exception as exc:  # noqa: BLE001
                logutil.append(f"diagnostics worker error: {exc}")
            if self.stop_event.wait(self.interval):
                break

    def stop(self) -> None:
        self.stop_event.set()
