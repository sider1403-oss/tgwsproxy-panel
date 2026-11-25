"""Network namespace operations used only by the privileged helper.

The namespace is entered through Docker's SandboxKey path
(`nsenter --net=<validated path>`), not through `-t <pid> -n`. This avoids
requiring CAP_SYS_PTRACE and keeps the helper's capability set unchanged.
"""
from __future__ import annotations

import ipaddress
import re

from . import docker_core, settings

CONN_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\S+):(\d+)\s+(\S+):(\d+)(?:\s+.*)?$")


class NetnsError(RuntimeError):
    pass


def _safe(value: str | None, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit]


def _run_in_ns(args: list[str], timeout: int = 10) -> str:
    try:
        path = docker_core.netns_path()
    except RuntimeError as exc:
        raise NetnsError(str(exc)) from exc
    rc, out, err = docker_core.run(["nsenter", f"--net={path}", *args], timeout=timeout)
    if rc != 0:
        raise NetnsError(_safe(err or out) or f"nsenter завершился с кодом {rc}")
    return out


def _split_addr(value: str) -> tuple[str, int] | None:
    try:
        if value.startswith("["):
            host, _, port = value[1:].partition("]:")
            return host, int(port)
        host, _, port = value.rpartition(":")
        return host, int(port)
    except ValueError:
        return None


def active_connections(port: int | None = None) -> list[dict]:
    proxy_port = int(port or settings.PROXY_PORT)
    out = _run_in_ns(
        ["ss", "-H", "-tin", "state", "established", "sport", "=", f":{proxy_port}"],
        timeout=10,
    )
    conns: list[dict] = []
    current: dict | None = None
    for raw in out.splitlines():
        if not raw.strip():
            continue
        if raw[0].isspace():
            if current is not None:
                m = re.search(r"bytes_acked:(\d+)", raw)
                if m:
                    current["bytes_sent"] = int(m.group(1))
                m = re.search(r"bytes_received:(\d+)", raw)
                if m:
                    current["bytes_received"] = int(m.group(1))
            continue
        parts = raw.split()
        # Be robust to ss variants that still print a State column.
        if parts and parts[0] == "ESTAB":
            parts = parts[1:]
        if len(parts) < 4 or not parts[0].isdigit():
            current = None
            continue
        local = _split_addr(parts[2])
        peer = _split_addr(parts[3])
        if not local or not peer:
            current = None
            continue
        current = {
            "ip": peer[0],
            "port": peer[1],
            "local_ip": local[0],
            "local_port": local[1],
            "state": "ESTAB",
            "bytes_sent": None,
            "bytes_received": None,
        }
        conns.append(current)
    return conns


def kill_connection(ip: str, port: int) -> tuple[bool, str]:
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return False, "Некорректный IP-адрес"
    try:
        port = int(port)
    except (TypeError, ValueError):
        return False, "Некорректный порт"
    if not (0 < port < 65536):
        return False, "Некорректный порт"
    st = docker_core.status()
    proxy_port = int(st.get("proxy_port") or settings.PROXY_PORT)
    match = [
        c
        for c in active_connections(proxy_port)
        if c.get("ip") == ip
        and int(c.get("port") or 0) == port
        and int(c.get("local_port") or 0) == proxy_port
    ]
    if not match:
        return False, "Соединение не найдено среди активных подключений tgwsproxy"
    _run_in_ns(
        [
            "ss",
            "-K",
            "-t",
            "sport",
            "=",
            f":{proxy_port}",
            "dst",
            ip,
            "dport",
            "=",
            str(port),
        ],
        timeout=10,
    )
    return True, "TCP-сессия принудительно закрыта (RST)"


def net_counters() -> dict | None:
    out = _run_in_ns(["cat", "/proc/net/dev"], timeout=10)
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
            return {"rx": int(parts[0]), "tx": int(parts[8])}
        except ValueError:
            return None
    return None
