"""Thin wrappers around docker, docker compose and container network access."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone

from . import db, settings

_version_cache: tuple[float, str | None] = (0.0, None)


def run(cmd: list[str], timeout: int = 60, cwd: str | None = None) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            errors="replace",
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s: {' '.join(cmd)}"
    except FileNotFoundError as exc:
        return 127, "", str(exc)


def compose(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
    cmd = ["docker", "compose", "-f", str(settings.COMPOSE_FILE), "--env-file", str(settings.ENV_FILE), *args]
    return run(cmd, timeout=timeout, cwd=str(settings.PROXY_DIR))


def inspect_container() -> dict | None:
    rc, out, err = run(["docker", "inspect", settings.CONTAINER], timeout=20)
    if rc != 0:
        return None
    try:
        data = json.loads(out)
        return data[0] if data else None
    except (ValueError, IndexError):
        return None


def image_name() -> str:
    info = inspect_container()
    if info:
        return info.get("Config", {}).get("Image") or ""
    return ""


def container_pid() -> int | None:
    info = inspect_container()
    if not info:
        return None
    pid = info.get("State", {}).get("Pid")
    return int(pid) if pid else None


def status() -> dict:
    info = inspect_container()
    if info is None:
        return {
            "exists": False,
            "state": "not_found",
            "health": None,
            "uptime": 0,
            "started_at": None,
            "pid": None,
            "restart_policy": None,
            "image": None,
            "ports": [],
            "error": "контейнер tgwsproxy не найден",
        }
    state = info.get("State", {})
    started = state.get("StartedAt")
    uptime = 0
    if started and state.get("Running"):
        dt = db.parse_iso(started)
        if dt:
            uptime = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    health = None
    if state.get("Running") and isinstance(state.get("Health"), dict):
        health = state["Health"].get("Status")
    ports = []
    for port, binds in (info.get("NetworkSettings", {}).get("Ports") or {}).items():
        if binds:
            for b in binds:
                ports.append(f"{b.get('HostIp')}:{b.get('HostPort')} → {port}")
        else:
            ports.append(port)
    env_map = {}
    for item in info.get("Config", {}).get("Env") or []:
        if "=" in item:
            k, v = item.split("=", 1)
            env_map[k] = v
    try:
        proxy_port = int(env_map.get("TG_PORT") or settings.PROXY_PORT)
    except ValueError:
        proxy_port = settings.PROXY_PORT
    return {
        "exists": True,
        "state": state.get("Status", "unknown"),
        "running": bool(state.get("Running")),
        "health": health,
        "uptime": uptime,
        "started_at": started,
        "finished_at": state.get("FinishedAt"),
        "restart_policy": (info.get("HostConfig", {}).get("RestartPolicy") or {}).get("Name"),
        "image": info.get("Config", {}).get("Image"),
        "image_id": info.get("Image"),
        "pid": state.get("Pid"),
        "ports": ports,
        "proxy_port": proxy_port,
        "exit_code": state.get("ExitCode"),
        "error": state.get("Error") or None,
    }


def version(refresh: bool = False) -> str | None:
    global _version_cache
    now = time.time()
    if not refresh and _version_cache[1] and now - _version_cache[0] < 600:
        return _version_cache[1]
    ver: str | None = None
    rc, out, err = run(["docker", "exec", settings.CONTAINER, "tg-ws-proxy", "--version"], timeout=10)
    if rc == 0 and out.strip():
        m = re.search(r"(\d+\.\d+\.\d+)", out)
        if m:
            ver = m.group(1)
    if ver is None:
        img = image_name()
        if img:
            rc, out, _ = run(
                ["docker", "run", "--rm", "--entrypoint", "tg-ws-proxy", img, "--version"], timeout=30
            )
            if rc == 0 and out.strip():
                m = re.search(r"(\d+\.\d+\.\d+)", out)
                if m:
                    ver = m.group(1)
    if ver is None:
        ver = db.get_meta("proxy_version")
    if ver:
        db.set_meta("proxy_version", ver)
        _version_cache = (now, ver)
    return ver


def net_counters(pid: int) -> tuple[int, int] | None:
    """Cumulative rx/tx bytes of the container eth0 interface (via its netns)."""
    rc, out, err = run(["nsenter", "-t", str(pid), "-n", "cat", "/proc/net/dev"], timeout=10)
    if rc != 0:
        return None
    for line in out.splitlines():
        if ":" not in line:
            continue
        name, data = line.split(":", 1)
        if name.strip() != "eth0":
            continue
        parts = data.split()
        if len(parts) < 9:
            return None
        try:
            return int(parts[0]), int(parts[8])
        except ValueError:
            return None
    return None


def proc_stat(pid: int) -> dict | None:
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as fh:
            raw = fh.read()
        rpar = raw.rfind(")")
        fields = raw[rpar + 2 :].split()
        # fields[0] is state (field 3); utime is field 14 -> index 11, stime 15 -> 12
        utime, stime = int(fields[11]), int(fields[12])
        rss_pages = int(fields[21])
        hz = os.sysconf("SC_CLK_TCK")
        return {
            "ticks": utime + stime,
            "hz": hz,
            "rss": rss_pages * os.sysconf("SC_PAGE_SIZE"),
        }
    except (OSError, ValueError, IndexError):
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
