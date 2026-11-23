"""Storage usage and the enforced retention limits, for the admin UI."""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import dockerctl, settings


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


def _backups() -> tuple[int, int]:
    try:
        dirs = [d for d in settings.BACKUP_DIR.iterdir() if d.is_dir()]
    except OSError:
        return 0, 0
    return len(dirs), sum(_dir_size(d) for d in dirs)


def _docker_logs() -> tuple[int, int]:
    info = dockerctl.inspect_container()
    if not info:
        return 0, 0
    log_path = info.get("LogPath")
    if not log_path:
        return 0, 0
    base = Path(log_path)
    total = 0
    files = 0
    try:
        candidates = [base, *base.parent.glob(base.name + ".*")]
    except OSError:
        candidates = [base]
    for path in candidates:
        size = _file_size(path)
        if size:
            total += size
            files += 1
    return total, files


def snapshot() -> dict:
    db_main = _file_size(settings.DB_PATH)
    db_wal = _file_size(Path(str(settings.DB_PATH) + "-wal"))
    db_shm = _file_size(Path(str(settings.DB_PATH) + "-shm"))
    log_total, log_files = _panel_logs()
    backup_count, backup_bytes = _backups()
    docker_total, docker_count = _docker_logs()
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
