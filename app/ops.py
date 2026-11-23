"""Global lock for mutually exclusive administrative operations."""
from __future__ import annotations

import threading
from contextlib import contextmanager


class Busy(RuntimeError):
    pass


_lock = threading.Lock()
_current: str | None = None
_guard = threading.Lock()


@contextmanager
def operation(name: str):
    global _current
    if not _lock.acquire(blocking=False):
        with _guard:
            current = _current or "операция"
        raise Busy(f"Уже выполняется другая операция: {current}. Повторите позже.")
    with _guard:
        _current = name
    try:
        yield
    finally:
        with _guard:
            _current = None
        _lock.release()


def status() -> dict:
    with _guard:
        return {"busy": _lock.locked(), "current": _current}
