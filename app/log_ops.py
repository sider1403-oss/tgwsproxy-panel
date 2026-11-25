"""Read-only access to the current tgwsproxy Docker json log files."""
from __future__ import annotations

import base64
import os
from pathlib import Path

from . import docker_core, settings


def _container_log_dir() -> Path | None:
    info = docker_core.inspect_container()
    if not info:
        return None
    log_path = info.get("LogPath")
    if not log_path:
        return None
    base = Path(log_path).resolve()
    root = settings.DOCKER_CONTAINERS_DIR.resolve()
    try:
        base.relative_to(root)
    except ValueError:
        return None
    if not base.name.endswith("-json.log") and "-json.log." not in base.name:
        return None
    return base


def list_files() -> dict:
    base = _container_log_dir()
    if base is None:
        return {"items": []}
    parent = base.parent
    items = []
    candidates = [base]
    try:
        candidates.extend(sorted(parent.glob(base.name + ".*")))
    except OSError:
        pass
    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0)
    for path in candidates:
        try:
            st = path.stat()
        except OSError:
            continue
        if not path.is_file():
            continue
        items.append(
            {
                "inode": str(st.st_ino),
                "name": path.name,
                "size": int(st.st_size),
                "mtime": int(st.st_mtime),
            }
        )
    return {"items": items}


def read_chunk(inode: str, offset: int, max_bytes: int = 1024 * 1024) -> dict:
    inode = str(inode)
    if not inode.isdigit():
        raise ValueError("Некорректный inode")
    try:
        offset = int(offset)
        max_bytes = int(max_bytes)
    except (TypeError, ValueError):
        raise ValueError("Некорректный offset/max_bytes")
    if offset < 0:
        raise ValueError("Некорректный offset")
    if not (1 <= max_bytes <= 1024 * 1024):
        raise ValueError("max_bytes вне диапазона")
    base = _container_log_dir()
    if base is None:
        raise ValueError("Лог контейнера недоступен")
    candidate = None
    for item in list_files()["items"]:
        if item["inode"] == inode:
            candidate = base.parent / item["name"]
            break
    if candidate is None:
        raise ValueError("Файл лога не принадлежит текущему tgwsproxy")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(settings.DOCKER_CONTAINERS_DIR.resolve())
    except ValueError:
        raise ValueError("Некорректный путь лога")
    size = resolved.stat().st_size
    if offset > size:
        offset = 0
    with open(resolved, "rb") as fh:
        fh.seek(offset)
        data = fh.read(max_bytes)
    return {
        "data": base64.b64encode(data).decode("ascii"),
        "next_offset": offset + len(data),
        "size": int(size),
        "eof": offset + len(data) >= size,
    }


def docker_log_stats() -> dict:
    base = _container_log_dir()
    if base is None:
        return {"bytes": 0, "files": 0}
    total = 0
    files = 0
    candidates = [base]
    try:
        candidates.extend(base.parent.glob(base.name + ".*"))
    except OSError:
        candidates = [base]
    for path in candidates:
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        if size:
            total += size
            files += 1
    return {"bytes": total, "files": files}
