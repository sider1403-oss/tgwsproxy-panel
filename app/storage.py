"""Storage usage and the enforced retention limits, for the admin UI."""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import helper_client, settings


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for root, _dirs, names in os.walk(path):
            for name in names:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _panel_logs() -> tuple[int, list[dict]]:
    items = []
    total = 0
    for path in sorted(settings.LOG_DIR.glob("panel.log*")):
        size = _file_size(path)
        total += size
        items.append({"name": path.name, "bytes": size})
    return total, items


def _helper_stats() -> dict:
    try:
        return helper_client.call("storage.stats", timeout=15)
    except (helper_client.HelperUnavailable, helper_client.HelperError):
        return {"docker_log": {"bytes": 0, "files": 0}, "backups": {"count": 0, "bytes": 0}}


def snapshot() -> dict:
    db_main = _file_size(settings.DB_PATH)
    db_wal = _file_size(Path(str(settings.DB_PATH) + "-wal"))
    db_shm = _file_size(Path(str(settings.DB_PATH) + "-shm"))
    log_total, log_files = _panel_logs()
    remote = _helper_stats()
    docker_total = int((remote.get("docker_log") or {}).get("bytes") or 0)
    docker_count = int((remote.get("docker_log") or {}).get("files") or 0)
    backup_count = int((remote.get("backups") or {}).get("count") or 0)
    backup_bytes = int((remote.get("backups") or {}).get("bytes") or 0)
    disk = shutil.disk_usage("/")
    return {
        "db": {"main": db_main, "wal": db_wal, "shm": db_shm, "total": db_main + db_wal + db_shm},
        "panel_log": {"total": log_total, "files": log_files},
        "backups": {"count": backup_count, "bytes": backup_bytes},
        "docker_log": {"bytes": docker_total, "files": docker_count},
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": round(disk.used / disk.total * 100, 1) if disk.total else 0,
        },
        "limits": {
            "panel_log_max_mb": settings.PANEL_LOG_MAX_MB,
            "panel_log_backups": settings.PANEL_LOG_BACKUPS,
            "db_soft_limit_mb": settings.DB_SIZE_LIMIT_MB,
            "sessions_days": settings.KEEP_SESSIONS_DAYS,
            "sessions_max": settings.KEEP_SESSIONS_MAX,
            "events_days": settings.KEEP_DAYS,
            "events_max": settings.KEEP_EVENTS_MAX,
            "audit_days": 30,
            "backups_keep": settings.BACKUPS_KEEP,
            "docker_log_max_mb": settings.DOCKER_LOG_MAX_MB,
            "journal_max_mb": settings.JOURNAL_MAX_MB,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
