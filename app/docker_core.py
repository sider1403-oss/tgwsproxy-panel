"""Direct, privileged Docker operations used only by the helper.

Every function here is called by an explicit helper operation; there is no
generic "run this command" entry point exposed over the socket.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from . import settings

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


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    if "." in v:
        head, tail = v.split(".", 1)
        frac = "".join(ch for ch in tail if ch.isdigit())[:6]
        tz = ""
        for i, ch in enumerate(tail):
            if ch in "+-":
                tz = tail[i:]
                break
        v = f"{head}.{frac}{tz}" if tz else f"{head}.{frac}"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def container_pid() -> int | None:
    info = inspect_container()
    if not info:
        return None
    pid = info.get("State", {}).get("Pid")
    return int(pid) if pid else None


def netns_path() -> str:
    """Resolve the current tgwsproxy SandboxKey to a validated netns path.

    The path comes only from docker inspect of the fixed container; it must be
    absolute and its resolved target must stay inside /var/run/docker/netns.
    """
    info = inspect_container()
    if not info:
        raise RuntimeError("контейнер tgwsproxy не найден")
    raw = info.get("NetworkSettings", {}).get("SandboxKey")
    if not isinstance(raw, str) or not raw.startswith("/"):
        raise RuntimeError("docker inspect не вернул абсолютный SandboxKey")
    root = Path("/var/run/docker/netns").resolve()
    try:
        resolved = Path(raw).resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"network namespace недоступен: {exc}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("SandboxKey вне /var/run/docker/netns") from exc
    if not resolved.is_file():
        raise RuntimeError("SandboxKey не является файлом namespace")
    return str(resolved)


def image_name() -> str:
    info = inspect_container()
    if info:
        return info.get("Config", {}).get("Image") or ""
    return ""


def status() -> dict:
    info = inspect_container()
    if info is None:
        return {
            "available": True,
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
        dt = _parse_iso(started)
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
        "available": True,
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


def service(action: str) -> dict:
    if action not in ("start", "stop", "restart"):
        raise ValueError("Недопустимое действие")
    rc, out, err = run(["docker", action, settings.CONTAINER], timeout=120)
    time.sleep(0.5 if action != "restart" else 1.5)
    st = status()
    ok = bool(st.get("running"))
    if action == "stop":
        ok = not st.get("running")
    return {
        "ok": bool(rc == 0 and ok),
        "action": action,
        "output": (out or "").strip()[-4000:],
        "error": None if (rc == 0 and ok) else (err or "контейнер не достиг нужного состояния").strip()[-2000:],
        "state": st,
    }


def version(refresh: bool = False) -> str | None:
    global _version_cache
    now = time.time()
    if not refresh and _version_cache[1] and now - _version_cache[0] < 600:
        return _version_cache[1]
    ver: str | None = None
    rc, out, _err = run(["docker", "exec", settings.CONTAINER, "tg-ws-proxy", "--version"], timeout=10)
    if rc == 0 and out.strip():
        m = re.search(r"(\d+\.\d+\.\d+)", out)
        if m:
            ver = m.group(1)
    if ver:
        _version_cache = (now, ver)
    return ver


def logs(lines: int = 100, since: str | None = None) -> dict:
    cmd = ["docker", "logs", "--tail", str(lines)]
    if since:
        cmd.extend(["--since", since])
    cmd.append(settings.CONTAINER)
    rc, out, err = run(cmd, timeout=30)
    text = out if rc == 0 else (err or out)
    return {"ok": rc == 0, "text": text, "lines": lines}


def proc_stat(pid: int) -> dict | None:
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as fh:
            raw = fh.read()
        rpar = raw.rfind(")")
        fields = raw[rpar + 2 :].split()
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


def tcp_check(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "TCP-порт отвечает"
    except OSError as exc:
        return False, f"TCP: {exc}"
