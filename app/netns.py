"""Panel-side active connection view; the helper performs all namespace work."""
from __future__ import annotations

import ipaddress

from . import helper_client, settings


def active_connections(port: int = settings.PROXY_PORT) -> list[dict]:
    data = helper_client.call("net.connections", timeout=15)
    return list(data.get("items") or [])


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
    try:
        result = helper_client.call("net.kill", timeout=20, ip=ip, port=port)
    except helper_client.HelperUnavailable as exc:
        return False, str(exc)
    except helper_client.HelperError as exc:
        return False, str(exc)
    return bool(result.get("ok")), str(result.get("message") or "")
