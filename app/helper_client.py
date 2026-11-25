"""Client for the privileged helper's Unix socket.

The panel never talks to Docker, nsenter or root-owned proxy files directly.
Every such operation goes through this small, explicit protocol.
"""
from __future__ import annotations

import json
import socket
import struct
import time

from . import settings


class HelperUnavailable(RuntimeError):
    pass


class HelperError(RuntimeError):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


def call(op: str, timeout: float | None = None, **params):
    payload = json.dumps({"op": op, "params": params}, ensure_ascii=False).encode("utf-8") + b"\n"
    deadline = time.monotonic() + (timeout if timeout is not None else settings.HELPER_TIMEOUT)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(max(0.5, deadline - time.monotonic()))
        try:
            sock.connect(str(settings.HELPER_SOCKET))
        except OSError as exc:
            raise HelperUnavailable(f"helper недоступен: {exc}") from exc
        try:
            sock.sendall(payload)
        except OSError as exc:
            raise HelperUnavailable(f"helper: ошибка отправки: {exc}") from exc

        buf = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HelperUnavailable("helper: таймаут ответа")
            sock.settimeout(remaining)
            try:
                chunk = sock.recv(65536)
            except socket.timeout as exc:
                raise HelperUnavailable("helper: таймаут ответа") from exc
            except OSError as exc:
                raise HelperUnavailable(f"helper: ошибка чтения: {exc}") from exc
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > settings.HELPER_MAX_RESPONSE:
                raise HelperUnavailable("helper: слишком большой ответ")
            if b"\n" in chunk:
                break
        line = bytes(buf).split(b"\n", 1)[0]
        if not line:
            raise HelperUnavailable("helper: пустой ответ")
        try:
            data = json.loads(line.decode("utf-8"))
        except ValueError as exc:
            raise HelperUnavailable("helper: некорректный JSON") from exc
        if not data.get("ok"):
            raise HelperError(str(data.get("error") or "ошибка helper"), data.get("code"))
        return data.get("result")
    finally:
        sock.close()


def ping() -> bool:
    try:
        call("ping", timeout=3)
        return True
    except (HelperUnavailable, HelperError):
        return False
