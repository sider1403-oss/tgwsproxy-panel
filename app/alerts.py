"""Alerting to Telegram / webhook with simple rules and cooldowns."""
from __future__ import annotations

import copy
import json
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from . import db, mask, settings

DEFAULTS = {
    "enabled": False,
    "telegram_token": "",
    "telegram_chat_id": "",
    "webhook_url": "",
    "rules": {
        "proxy_down": True,
        "warnings_10m": 60,
        "no_sessions_minutes": 0,
        "diag_fail": True,
    },
    "cooldown_minutes": 30,
}

_lock = threading.RLock()
_last_sent: dict[str, float] = {}
_last_eval = 0.0
_down_since: float | None = None
_down_alerted = False


def _path():
    return settings.CONFIG_DIR / "alerts.json"


def _merge_defaults(data: dict) -> dict:
    out = copy.deepcopy(DEFAULTS)
    out.update({k: v for k, v in data.items() if k in DEFAULTS})
    out["rules"].update(data.get("rules") or {})
    return out


def load() -> dict:
    with _lock:
        try:
            raw = _path().read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("not an object")
            return _merge_defaults(data)
        except (OSError, ValueError):
            return copy.deepcopy(DEFAULTS)


def save(payload: dict) -> dict:
    with _lock:
        current = load()
        if payload.get("clear_token"):
            token = ""
        elif payload.get("telegram_token"):
            token = str(payload["telegram_token"]).strip()
        else:
            token = current["telegram_token"]
        rules = current["rules"].copy()
        incoming_rules = payload.get("rules") or {}
        if "proxy_down" in incoming_rules:
            rules["proxy_down"] = bool(incoming_rules["proxy_down"])
        if "diag_fail" in incoming_rules:
            rules["diag_fail"] = bool(incoming_rules["diag_fail"])
        for key, minimum, maximum in (("warnings_10m", 0, 100000), ("no_sessions_minutes", 0, 100000)):
            if key in incoming_rules:
                try:
                    value = int(incoming_rules[key])
                except (TypeError, ValueError):
                    raise ValueError(f"{key}: ожидается целое число")
                rules[key] = max(minimum, min(maximum, value))
        try:
            cooldown = int(payload.get("cooldown_minutes", current["cooldown_minutes"]))
        except (TypeError, ValueError):
            raise ValueError("cooldown_minutes: ожидается целое число")
        data = {
            "enabled": bool(payload.get("enabled", current["enabled"])),
            "telegram_token": token,
            "telegram_chat_id": str(payload.get("telegram_chat_id", current["telegram_chat_id"]) or "").strip(),
            "webhook_url": str(payload.get("webhook_url", current["webhook_url"]) or "").strip(),
            "rules": rules,
            "cooldown_minutes": max(0, min(1440, cooldown)),
        }
        settings.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        settings.CONFIG_DIR.chmod(0o700)
        tmp = _path().with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(_path())
        return public(data)


def public(data: dict | None = None) -> dict:
    data = data or load()
    token = data.get("telegram_token") or ""
    masked = (token[:6] + "…" + token[-4:]) if len(token) > 12 else ("***" if token else "")
    return {
        "enabled": data["enabled"],
        "telegram_chat_id": data.get("telegram_chat_id") or "",
        "telegram_token_set": bool(token),
        "telegram_token_masked": masked,
        "webhook_url": data.get("webhook_url") or "",
        "rules": data["rules"],
        "cooldown_minutes": data["cooldown_minutes"],
        "configured": bool((token and data.get("telegram_chat_id")) or data.get("webhook_url")),
    }


def _post_json(url: str, payload: dict, timeout: float = 12.0) -> tuple[bool, str | None]:
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(4000)
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, mask.mask_text(str(exc))[:500]


def _deliver(rule: str, message: str, level: str = "warn") -> dict:
    cfg = load()
    text = f"[TGWSProxy] {message}\n{settings.PROXY_URL}"
    results = []
    token = cfg.get("telegram_token") or ""
    chat = cfg.get("telegram_chat_id") or ""
    if token and chat:
        ok, error = _post_json(
            f"https://api.telegram.org/bot{token}/sendMessage",
            {"chat_id": chat, "text": text, "disable_web_page_preview": True},
        )
        results.append({"channel": "telegram", "ok": ok, "error": error})
    webhook = cfg.get("webhook_url") or ""
    if webhook:
        ok, error = _post_json(
            webhook,
            {
                "source": "tgws-panel",
                "level": level,
                "rule": rule,
                "message": message,
                "text": text,
                "ts": db.now_iso(),
            },
        )
        results.append({"channel": "webhook", "ok": ok, "error": error})
    delivered = any(r["ok"] for r in results)
    if not results:
        error = "каналы уведомлений не настроены"
    else:
        errors = [f"{r['channel']}: {r['error']}" for r in results if not r["ok"] and r["error"]]
        error = "; ".join(errors) or None
    db.execute(
        "INSERT INTO alert_log(ts,rule,level,message,delivered,error) VALUES(?,?,?,?,?,?)",
        (db.now_iso(), rule, level, message, 1 if delivered else 0, error),
    )
    db.execute("DELETE FROM alert_log WHERE id NOT IN (SELECT id FROM alert_log ORDER BY id DESC LIMIT 500)")
    return {"ok": delivered, "results": results, "error": error}


def notify(rule: str, message: str, level: str = "warn", force: bool = False) -> bool:
    cfg = load()
    if not cfg.get("enabled") and not force:
        return False
    now = time.time()
    cooldown = max(0, int(cfg.get("cooldown_minutes", 30))) * 60
    with _lock:
        last = _last_sent.get(rule, 0.0)
        if not force and cooldown and now - last < cooldown:
            return False
        _last_sent[rule] = now
    threading.Thread(target=_deliver, args=(rule, message, level), daemon=True, name=f"alert-{rule}").start()
    return True


def send_test() -> dict:
    cfg = load()
    if not (cfg.get("telegram_token") and cfg.get("telegram_chat_id")) and not cfg.get("webhook_url"):
        return {"ok": False, "error": "Сначала укажите Telegram-бот/чат или webhook", "results": []}
    return _deliver("test", "Тестовое уведомление панели TGWSProxy", "info")


def history(limit: int = 50) -> list[dict]:
    rows = db.query("SELECT * FROM alert_log ORDER BY id DESC LIMIT ?", (limit,))
    out = []
    for r in rows:
        d = {k: r[k] for k in r.keys()}
        d["delivered"] = bool(d["delivered"])
        out.append(d)
    return out


def evaluate(status: dict, snapshot: dict) -> None:
    """Called from the collector; cheap checks with 60s throttle."""
    global _last_eval, _down_since, _down_alerted
    now = time.time()
    if now - _last_eval < 60:
        return
    _last_eval = now
    cfg = load()
    if not cfg.get("enabled"):
        return
    rules = cfg.get("rules") or {}
    running = bool(status.get("running"))

    if not running:
        if _down_since is None:
            _down_since = now
        if rules.get("proxy_down") and now - _down_since > 60 and not _down_alerted:
            _down_alerted = True
            notify("proxy_down", f"Прокси не работает ({status.get('state')}, exit {status.get('exit_code')})", "error")
    else:
        if _down_since is not None:
            was_alerted = _down_alerted
            _down_since = None
            _down_alerted = False
            if was_alerted:
                notify("proxy_recovered", "Прокси снова работает", "info")

    warnings_limit = int(rules.get("warnings_10m") or 0)
    if warnings_limit > 0:
        cutoff = db.iso(datetime.now(timezone.utc) - timedelta(minutes=10))
        count = db.query_one(
            "SELECT COUNT(*) AS n FROM events WHERE ts >= ? AND level IN ('WARN','ERROR')", (cutoff,)
        )["n"]
        if count >= warnings_limit:
            notify("warnings", f"Много предупреждений: {count} за 10 минут (порог {warnings_limit})", "warn")

    no_sessions = int(rules.get("no_sessions_minutes") or 0)
    if no_sessions > 0 and running:
        cutoff = db.iso(datetime.now(timezone.utc) - timedelta(minutes=no_sessions))
        count = db.query_one("SELECT COUNT(*) AS n FROM sessions WHERE ended_at >= ?", (cutoff,))["n"]
        if count == 0:
            notify("no_sessions", f"Нет завершённых сессий за {no_sessions} мин — возможно, клиенты не подключаются", "warn")

    if rules.get("diag_fail"):
        try:
            from . import diagnostics

            last = diagnostics.latest("quick")
        except Exception:  # noqa: BLE001
            last = None
        if last and last.get("status") == "fail":
            notify("diag_fail", f"Диагностика: {last.get('summary')}", "error")
