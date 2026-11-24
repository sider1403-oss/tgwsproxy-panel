"""Panel-side view of the proxy container.

All privileged operations are delegated to tgws-panel-helper over a Unix socket.
This module never talks to Docker, nsenter or root-owned files directly.
"""
from __future__ import annotations

import os
import time

from . import db, helper_client, settings

_version_cache: tuple[float, str | None] = (0.0, None)


def status() -> dict:
    return helper_client.call("docker.status")


def image_name() -> str:
    try:
        return str(status().get("image") or "")
    except helper_client.HelperUnavailable:
        return ""


def container_pid() -> int | None:
    try:
        pid = status().get("pid")
        return int(pid) if pid else None
    except (helper_client.HelperUnavailable, TypeError, ValueError):
        return None


def version(refresh: bool = False) -> str | None:
    global _version_cache
    now = time.time()
    if not refresh and _version_cache[1] and now - _version_cache[0] < 600:
        return _version_cache[1]
    ver: str | None = None
    try:
        ver = helper_client.call("docker.version", timeout=20, refresh=refresh).get("version")
    except helper_client.HelperUnavailable:
        ver = None
    if ver is None:
        ver = db.get_meta("proxy_version")
    if ver:
        db.set_meta("proxy_version", ver)
        _version_cache = (now, ver)
    return ver


def net_counters() -> tuple[int, int] | None:
    try:
        data = helper_client.call("net.counters", timeout=15)
    except helper_client.HelperUnavailable:
        return None
    if not data:
        return None
    try:
        return int(data["rx"]), int(data["tx"])
    except (KeyError, TypeError, ValueError):
        return None


def proc_stat() -> dict | None:
    try:
        return helper_client.call("container.proc", timeout=10)
    except helper_client.HelperUnavailable:
        return None


def lxc_cpu_usec() -> int | None:
    """Cumulative CPU time of this LXC container (cgroup v2 accounting)."""
    try:
        with open("/sys/fs/cgroup/cpu.stat", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("usage_usec "):
                    return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return None


def host_cpu_times() -> tuple[int, int] | None:
    try:
        with open("/proc/stat", "r", encoding="utf-8") as fh:
            line = fh.readline()
        parts = [int(x) for x in line.split()[1:]]
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        return sum(parts), idle
    except (OSError, ValueError, IndexError):
        return None


def host_mem() -> tuple[int, int]:
    total = used = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            vals = {}
            for line in fh:
                k, v = line.split(":", 1)
                vals[k] = int(v.strip().split()[0]) * 1024
        total = vals.get("MemTotal", 0)
        avail = vals.get("MemAvailable", vals.get("MemFree", 0))
        used = max(0, total - avail)
    except (OSError, ValueError):
        pass
    return total, used


def tcp_check(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "TCP-порт отвечает"
    except OSError as exc:
        return False, f"TCP: {exc}"
