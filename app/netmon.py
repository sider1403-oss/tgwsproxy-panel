"""Passive TCP SYN fingerprint collector.

Runs as tgws-netmon with CAP_NET_RAW only. It never touches Docker, the panel
database or the proxy configuration: fingerprints are exposed over a local Unix
socket and persisted in its own state directory.
"""
from __future__ import annotations

import grp
import json
import os
import pwd
import signal
import socket
import struct
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import settings

MAX_HINTS = 10000
_state_lock = threading.Lock()
_hints: dict[str, dict] = {}
_port = settings.PROXY_PORT
_stop = threading.Event()
_sock: socket.socket | None = None

STATE_DIR = Path(os.environ.get("TGWS_NETMON_STATE", "/var/lib/tgws-panel-netmon"))
STATE_FILE = STATE_DIR / "hints.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _log(msg: str) -> None:
    print(f"{_now()} {msg}", flush=True)


def _load() -> None:
    global _port
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(data.get("port"), int):
        _port = int(data["port"])
    for item in data.get("hints") or []:
        if isinstance(item, dict) and item.get("ip"):
            _hints[str(item["ip"])] = item


def _persist() -> None:
    with _state_lock:
        payload = {"port": _port, "generated_at": _now(), "hints": list(_hints.values())}
    tmp = STATE_FILE.with_suffix(".tmp")
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        tmp.replace(STATE_FILE)
    except OSError as exc:
        _log(f"state persist failed: {exc}")


def _store(ip: str, ttl: int, window: int, mss: int | None, ws: int | None, ts: bool, sack: bool, options: str) -> None:
    with _state_lock:
        _hints[ip] = {
            "ip": ip,
            "ttl": ttl,
            "window": window,
            "mss": mss,
            "ws": ws,
            "ts": ts,
            "sack": sack,
            "options": options,
            "port": _port,
            "last_seen": _now(),
        }
        if len(_hints) > MAX_HINTS:
            # Drop the oldest entries; hints are best-effort by definition.
            for key, _ in sorted(_hints.items(), key=lambda kv: kv[1].get("last_seen") or "")[: len(_hints) - MAX_HINTS]:
                _hints.pop(key, None)


class Sniffer(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True, name="netmon-sniffer")
        self.sock: socket.socket | None = None

    def run(self) -> None:
        try:
            self.sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0800))
            self.sock.bind((settings.SNIFF_IFACE, 0))
            self.sock.settimeout(1.0)
        except OSError as exc:
            _log(f"sniffer disabled ({settings.SNIFF_IFACE}): {exc}")
            return
        _log(f"sniffer started on {settings.SNIFF_IFACE}, proxy port {_port}")
        try:
            while not _stop.is_set():
                try:
                    data, _addr = self.sock.recvfrom(65535)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    self._handle(data)
                except Exception:  # noqa: BLE001 - malformed packet must not stop capture
                    continue
        finally:
            try:
                self.sock.close()
            except OSError:
                pass

    def _handle(self, data: bytes) -> None:
        if len(data) < 34:
            return
        offset = 14
        ethertype = struct.unpack("!H", data[12:14])[0]
        if ethertype == 0x8100:
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
        if dport != _port:
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
        _store(src, ttl, window, mss, ws, ts, sack, ",".join(order))


def _panel_uid() -> int:
    try:
        return pwd.getpwnam("tgws-panel").pw_uid
    except KeyError:
        return -1


def _panel_gid() -> int:
    try:
        return grp.getgrnam("tgws-panel").gr_gid
    except KeyError:
        return -1


def _peer_ok(conn: socket.socket) -> bool:
    try:
        raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", raw)
        return uid == _panel_uid()
    except OSError:
        return False


def _handle_client(conn: socket.socket) -> None:
    try:
        if not _peer_ok(conn):
            conn.sendall(b'{"ok":false,"error":"forbidden peer"}\n')
            return
        conn.settimeout(10)
        buf = bytearray()
        while b"\n" not in buf and len(buf) < 65536:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf.extend(chunk)
        line = bytes(buf).split(b"\n", 1)[0]
        req = json.loads(line.decode("utf-8")) if line else {}
        op = req.get("op")
        params = req.get("params") or {}
        global _port
        if op == "get":
            with _state_lock:
                result = {"port": _port, "hints": list(_hints.values()), "generated_at": _now()}
        elif op == "set_port":
            port = int(params.get("port"))
            if not 1 <= port <= 65535:
                raise ValueError("port")
            with _state_lock:
                _port = port
            result = {"port": _port}
        else:
            raise ValueError("unknown op")
        conn.sendall(json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode() + b"\n")
    except Exception as exc:  # noqa: BLE001
        try:
            conn.sendall(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode() + b"\n")
        except OSError:
            pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def _serve() -> None:
    global _sock
    path = settings.NETMON_SOCKET
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    _sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    _sock.bind(str(path))
    os.chmod(path, 0o660)
    try:
        os.chown(path, os.getuid(), _panel_gid())
    except OSError:
        pass
    _sock.listen(8)
    _sock.settimeout(1.0)
    _log(f"netmon listening on {path}")
    while not _stop.is_set():
        try:
            conn, _ = _sock.accept()
        except socket.timeout:
            continue
        except OSError:
            if _stop.is_set():
                break
            continue
        threading.Thread(target=_handle_client, args=(conn,), daemon=True).start()


def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    signal.signal(signal.SIGINT, lambda *_: _stop.set())
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _load()
    t = Sniffer()
    t.start()
    threading.Thread(target=_serve, daemon=True).start()
    while not _stop.is_set():
        _persist()
        _stop.wait(20)
    try:
        if _sock:
            _sock.close()
    except OSError:
        pass
    try:
        settings.NETMON_SOCKET.unlink()
    except OSError:
        pass


if __name__ == "__main__":
    main()
