"""Best-effort device hints for clients.

tg-ws-proxy (and MTProto in general) does not expose the client's device: the
proxy only logs IP:port, DC, transport and byte counters, and the Telegram
payload is end-to-end encrypted.  This module passively fingerprints the TCP
SYN of incoming connections (TTL, window size, TCP options) and classifies the
OS family.  It is an approximation: Windows is usually reliable, and
iOS/macOS cannot be told apart from a SYN.  The admin can override the type
per IP in the UI; that manual label always wins.
"""
from __future__ import annotations

import ipaddress
import socket
import struct
import threading
import time

from . import config_editor, db, logutil, settings

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


class Sniffer(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True, name="device-sniffer")
        self.stop_event = threading.Event()
        self.sock: socket.socket | None = None
        self.port = settings.PROXY_PORT
        self.last_port_check = 0.0
        self.packets = 0

    def run(self) -> None:
        iface = settings.SNIFF_IFACE
        try:
            self.sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0800))
            self.sock.bind((iface, 0))
            self.sock.settimeout(1.0)
        except OSError as exc:
            logutil.append(f"device sniffer disabled ({iface}): {exc}")
            return
        logutil.append(f"device sniffer started on {iface}, proxy port {self.port}")
        try:
            while not self.stop_event.is_set():
                try:
                    data, _addr = self.sock.recvfrom(65535)
                except socket.timeout:
                    self._refresh_port()
                    continue
                except OSError:
                    break
                try:
                    self._handle(data)
                except Exception:  # noqa: BLE001 - malformed packet must not stop the sniffer
                    continue
        finally:
            try:
                self.sock.close()
            except OSError:
                pass

    def _refresh_port(self) -> None:
        now = time.time()
        if now - self.last_port_check < 60:
            return
        self.last_port_check = now
        try:
            env = config_editor.effective_env()
            port = int(env.get("TG_PORT") or settings.PROXY_PORT)
        except Exception:  # noqa: BLE001
            return
        if port != self.port:
            self.port = port
            logutil.append(f"device sniffer target port changed to {port}")

    def _handle(self, data: bytes) -> None:
        if len(data) < 34:
            return
        offset = 14
        ethertype = struct.unpack("!H", data[12:14])[0]
        if ethertype == 0x8100:  # VLAN tagged
            ethertype = struct.unpack("!H", data[16:18])[0]
            offset = 18
        if ethertype != 0x0800:
            return
        ip = data[offset:]
        if len(ip) < 20:
            return
        ihl = (ip[0] & 0x0F) * 4
        if ip[0] >> 4 != 4 or ihl < 20 or len(ip) < ihl + 20:
            return
        if ip[9] != 6:
            return
        frag = struct.unpack("!H", ip[6:8])[0]
        if frag & 0x1FFF:
            return
        ttl = ip[8]
        src = socket.inet_ntoa(ip[12:16])
        tcp = ip[ihl:]
        _sport, dport = struct.unpack("!HH", tcp[0:4])
        if dport != self.port:
            return
        flags = tcp[13]
        if not (flags & 0x02) or (flags & 0x10):
            return
        doff = (tcp[12] >> 4) * 4
        if doff < 20 or len(tcp) < doff:
            return
        window = struct.unpack("!H", tcp[14:16])[0]
        opts = tcp[20:doff]
        mss = ws = None
        ts = sack = False
        order: list[str] = []
        i = 0
        while i < len(opts):
            kind = opts[i]
            if kind == 0:
                break
            if kind == 1:
                order.append("NOP")
                i += 1
                continue
            if i + 1 >= len(opts):
                break
            length = opts[i + 1]
            if length < 2 or i + length > len(opts):
                break
            body = opts[i + 2 : i + length]
            if kind == 2 and len(body) >= 2:
                mss = struct.unpack("!H", body[:2])[0]
                order.append("MSS")
            elif kind == 3 and body:
                ws = body[0]
                order.append("WS")
            elif kind == 4:
                sack = True
                order.append("SACK")
            elif kind == 8 and len(body) >= 8:
                ts = True
                order.append("TS")
            else:
                order.append(f"OPT{kind}")
            i += length
        self.packets += 1
        _store_hint(src, ttl, window, mss, ws, ts, sack, ",".join(order))

    def stop(self) -> None:
        self.stop_event.set()
