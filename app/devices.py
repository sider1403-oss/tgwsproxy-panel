"""Best-effort device hints for clients.

The passive AF_PACKET sniffer lives in tgws-panel-netmon (CAP_NET_RAW only).
This module reads the resulting fingerprints over a local Unix socket,
classifies the OS family and stores the hint in the panel DB. Manual labels in
`device_labels` always win.
"""
from __future__ import annotations

import ipaddress
import threading
import time

from . import db, logutil, netmon_client, settings

FAMILY_LABELS = {
    "windows": "Windows",
    "apple": "iOS/macOS",
    "ios": "iOS",
    "macos": "macOS",
    "android": "Android",
    "linux": "Linux",
    "other": "Другое",
    "unknown": "неизвестно",
}
MANUAL_FAMILIES = {"android", "ios", "macos", "windows", "linux", "other"}

_sync_lock = threading.Lock()
_last_sync = 0.0


def classify(ttl: int, window: int, options: str) -> str:
    opts = [x for x in (options or "").split(",") if x]
    if ttl >= 100:
        return "windows"
    if 32 <= ttl <= 80:
        # Apple (iOS/macOS): MSS,NOP,WS,...,TS,SACK — window scale before timestamps
        if "WS" in opts and "TS" in opts and opts.index("WS") < opts.index("TS"):
            return "apple"
        # Linux/Android: SACK before timestamps, window scale after
        if "TS" in opts and "SACK" in opts and opts.index("SACK") < opts.index("TS"):
            return "android" if window >= 65000 else "linux"
    return "unknown"


def _store_hint(ip: str, ttl: int, window: int, mss: int | None, ws: int | None, ts: bool, sack: bool, options: str) -> None:
    family = classify(ttl, window, options)
    label = FAMILY_LABELS.get(family, family)
    row = db.query_one("SELECT ttl, window, options FROM device_hints WHERE ip=?", (ip,))
    if row and row["ttl"] == ttl and row["window"] == window and (row["options"] or "") == options:
        return
    db.execute(
        "INSERT INTO device_hints(ip,family,label,ttl,window,mss,ws,ts,sack,options,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(ip) DO UPDATE SET family=excluded.family,label=excluded.label,ttl=excluded.ttl,"
        "window=excluded.window,mss=excluded.mss,ws=excluded.ws,ts=excluded.ts,sack=excluded.sack,"
        "options=excluded.options,updated_at=excluded.updated_at",
        (
            ip,
            family,
            label,
            ttl,
            window,
            mss,
            ws,
            1 if ts else 0,
            1 if sack else 0,
            options,
            db.now_iso(),
        ),
    )


def sync_netmon(force: bool = False) -> int:
    """Pull fingerprints from netmon and persist them. Best effort."""
    global _last_sync
    now = time.time()
    with _sync_lock:
        if not force and now - _last_sync < settings.NETMON_INTERVAL:
            return 0
        _last_sync = now
        try:
            data = netmon_client.get()
        except netmon_client.NetmonUnavailable:
            return 0
    hints = data.get("hints") or []
    port = int(data.get("port") or settings.PROXY_PORT)
    stored = 0
    for hint in hints:
        try:
            if int(hint.get("port") or 0) != port:
                continue
            ip = str(hint.get("ip") or "")
            ipaddress.ip_address(ip)
            _store_hint(
                ip,
                int(hint.get("ttl") or 0),
                int(hint.get("window") or 0),
                int(hint["mss"]) if hint.get("mss") is not None else None,
                int(hint["ws"]) if hint.get("ws") is not None else None,
                bool(hint.get("ts")),
                bool(hint.get("sack")),
                str(hint.get("options") or ""),
            )
            stored += 1
        except (ValueError, TypeError):
            continue
    return stored


def lookup(ip: str) -> dict:
    manual = db.query_one("SELECT family,label,updated_at FROM device_labels WHERE ip=?", (ip,))
    if manual:
        family = manual["family"]
        return {
            "family": family,
            "label": manual["label"] or FAMILY_LABELS.get(family, family),
            "source": "manual",
            "detail": f"указано администратором {manual['updated_at']}",
            "confidence": "high",
        }
    hint = db.query_one("SELECT * FROM device_hints WHERE ip=?", (ip,))
    if hint:
        family = hint["family"] or "unknown"
        detail = f"TCP SYN: TTL {hint['ttl']}, window {hint['window']}, options: {hint['options'] or '—'}"
        if family == "apple":
            detail += ". iOS и macOS по SYN неразличимы — точный тип можно указать вручную."
        elif family in ("android", "linux"):
            detail += ". Android и Linux могут определяться неточно — тип можно указать вручную."
        return {
            "family": family,
            "label": FAMILY_LABELS.get(family, family),
            "source": "syn",
            "detail": detail,
            "confidence": "low",
        }
    return {
        "family": "unknown",
        "label": FAMILY_LABELS["unknown"],
        "source": "none",
        "detail": "Нет SYN-отпечатка для этого IP. Устройство можно указать вручную.",
        "confidence": "none",
    }


def lookup_many(ips: list[str]) -> dict[str, dict]:
    cache: dict[str, dict] = {}
    for ip in set(ips):
        cache[ip] = lookup(ip)
    return cache


def set_label(ip: str, family: str) -> dict:
    ipaddress.ip_address(ip)
    family = family.lower()
    if family not in MANUAL_FAMILIES:
        raise ValueError("Недопустимый тип устройства")
    db.execute(
        "INSERT INTO device_labels(ip,family,label,updated_at) VALUES(?,?,?,?) "
        "ON CONFLICT(ip) DO UPDATE SET family=excluded.family,label=excluded.label,updated_at=excluded.updated_at",
        (ip, family, FAMILY_LABELS[family], db.now_iso()),
    )
    return lookup(ip)


def clear_label(ip: str) -> dict:
    ipaddress.ip_address(ip)
    db.execute("DELETE FROM device_labels WHERE ip=?", (ip,))
    return lookup(ip)
