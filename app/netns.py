"""Read the container network namespace: list and terminate client sockets."""
from __future__ import annotations

import ipaddress
import re

from . import dockerctl, settings

CONN_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\S+):(\d+)\s+(\S+):(\d+)(?:\s+.*)?$")


def _split_addr(value: str) -> tuple[str, int] | None:
    try:
        if value.startswith("["):
            host, _, port = value[1:].partition("]:")
            return host, int(port)
        host, _, port = value.rpartition(":")
        return host, int(port)
    except ValueError:
        return None


def active_connections(port: int = settings.PROXY_PORT) -> list[dict]:
    pid = dockerctl.container_pid()
    if not pid:
        return []
    rc, out, err = dockerctl.run(
        ["nsenter", "-t", str(pid), "-n", "ss", "-tin", "state", "established", "sport", "=", f":{port}"],
        timeout=10,
    )
    if rc != 0:
        return []
    conns: list[dict] = []
    current: dict | None = None
    for raw in out.splitlines():
        if not raw.strip():
            continue
        if raw[0].isspace():
            # tcp_info continuation line for the previous socket
            if current is not None:
                m = re.search(r"bytes_acked:(\d+)", raw)
                if m:
                    current["bytes_sent"] = int(m.group(1))
                m = re.search(r"bytes_received:(\d+)", raw)
                if m:
                    current["bytes_received"] = int(m.group(1))
            continue
        parts = raw.split()
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
    if not (0 < int(port) < 65536):
        return False, "Некорректный порт"
    pid = dockerctl.container_pid()
    if not pid:
        return False, "Контейнер не запущен"
    rc, out, err = dockerctl.run(
        [
            "nsenter",
            "-t",
            str(pid),
            "-n",
            "ss",
            "-K",
            "-t",
            "dst",
            ip,
            "dport",
            "=",
            str(int(port)),
        ],
        timeout=10,
    )
    if rc != 0:
        return False, (err or out or "ss -K завершился с ошибкой").strip()
    return True, "TCP-сессия принудительно закрыта (RST)"
