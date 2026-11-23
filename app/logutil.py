"""Rotating append-only log for the panel itself (bounded disk usage)."""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from . import settings

_lock = threading.Lock()


def _path():
    return settings.LOG_DIR / "panel.log"


def _rotate(path, backups: int) -> None:
    if backups <= 0:
        try:
            path.unlink()
        except OSError:
            pass
        return
    for index in range(backups - 1, 0, -1):
        src = path.with_name(f"{path.name}.{index}")
        dst = path.with_name(f"{path.name}.{index + 1}")
        if src.exists():
            os.replace(src, dst)
    if path.exists():
        os.replace(path, path.with_name(f"{path.name}.1"))


def append(message: str) -> None:
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = _path()
    limit = settings.PANEL_LOG_MAX_MB * 1024 * 1024
    with _lock:
        try:
            if path.exists() and path.stat().st_size >= limit:
                _rotate(path, settings.PANEL_LOG_BACKUPS)
        except OSError:
            pass
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(f"{stamp} {message}\n")
        except OSError:
            pass
