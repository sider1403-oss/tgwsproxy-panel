"""Tiny client for tgws-panel-netmon."""
from __future__ import annotations

import json
import socket

from . import settings


class NetmonUnavailable(RuntimeError):
    pass


def call(op: str, timeout: float | None = None, **params) -> dict:
    payload = json.dumps({"op": op, "params": params}, ensure_ascii=False).encode("utf-8") + b"\n"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout or settings.NETMON_TIMEOUT)
        try:
            sock.connect(str(settings.NETMON_SOCKET))
        except OSError as exc:
            raise NetmonUnavailable(str(exc)) from exc
        sock.sendall(payload)
        buf = bytearray()
        while b"\n" not in buf:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > 4 * 1024 * 1024:
                raise NetmonUnavailable("netmon: слишком большой ответ")
        line = bytes(buf).split(b"\n", 1)[0]
        data = json.loads(line.decode("utf-8"))
        if not data.get("ok"):
            raise NetmonUnavailable(str(data.get("error") or "netmon error"))
        return data.get("result") or {}
    except (OSError, ValueError) as exc:
        raise NetmonUnavailable(str(exc)) from exc
    finally:
        sock.close()


def get() -> dict:
    return call("get")


def set_port(port: int) -> dict:
    return call("set_port", port=int(port))
