"""Panel-wide paths and constants (overridable via environment variables)."""
from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


PANEL_ROOT = Path(_env("TGWS_PANEL_ROOT", "/opt/tgws-panel"))
APP_DIR = PANEL_ROOT / "app"
DATA_DIR = PANEL_ROOT / "data"
BACKUP_DIR = PANEL_ROOT / "backups"
LOG_DIR = PANEL_ROOT / "logs"
CONFIG_DIR = PANEL_ROOT / "config"
FRONTEND_DIR = PANEL_ROOT / "frontend"
DB_PATH = DATA_DIR / "panel.db"

PROXY_DIR = Path(_env("TGWS_PROXY_DIR", "/opt/tg-ws-proxy"))
COMPOSE_FILE = PROXY_DIR / "docker-compose.yml"
ENV_FILE = PROXY_DIR / ".env"
CONTAINER = _env("TGWS_CONTAINER", "tgwsproxy")
SERVICE_KEY = _env("TGWS_SERVICE", "tgwsproxy")

PANEL_PORT = _env_int("PANEL_PORT", 8090)
PUBLIC_HOST = _env("PANEL_PUBLIC_HOST", "127.0.0.1")
PROXY_PORT = _env_int("TGWS_PROXY_PORT", 1443)

# Authentication/session settings.
SESSION_IDLE_MINUTES = _env_int("SESSION_IDLE_MINUTES", 60)
SESSION_ABSOLUTE_HOURS = _env_int("SESSION_ABSOLUTE_HOURS", 12)

# Only trust X-Forwarded-* when the direct peer is one of these proxies.
# Comma-separated IPs/CIDRs, e.g. "127.0.0.1,10.0.0.0/8".
TRUSTED_PROXIES = _env("PANEL_TRUSTED_PROXIES", "")

# Extra allowed browser origins for CSRF checks (comma-separated), e.g.
# "https://panel.example.com".
ALLOWED_ORIGINS = _env("PANEL_ALLOWED_ORIGINS", "")


def allowed_origins() -> set[str]:
    port = PANEL_PORT
    origins = {
        f"http://{PUBLIC_HOST}:{port}",
        f"https://{PUBLIC_HOST}:{port}",
        f"http://localhost:{port}",
        f"https://localhost:{port}",
        f"http://127.0.0.1:{port}",
        f"https://127.0.0.1:{port}",
    }
    for item in (ALLOWED_ORIGINS or "").split(","):
        item = item.strip().rstrip("/")
        if item:
            origins.add(item)
    return {x.rstrip("/") for x in origins}

PROXY_URL = f"http://{PUBLIC_HOST}:{PANEL_PORT}"

# How many days of samples/events to keep.
KEEP_DAYS = 7
KEEP_EVENTS_MAX = 300000
KEEP_SESSIONS_DAYS = 90
KEEP_SESSIONS_MAX = 300000
DB_SIZE_LIMIT_MB = 200

# Panel-side log rotation.
PANEL_LOG_MAX_MB = 5
PANEL_LOG_BACKUPS = 2

# How many configuration backups to keep.
BACKUPS_KEEP = 50

# Docker json-file limits defined in docker-compose.yml (10m × 3 files).
DOCKER_LOG_MAX_MB = 30

# systemd-journald cap installed by /etc/systemd/journald.conf.d/99-tgws-panel.conf
JOURNAL_MAX_MB = 100

# Interface used for passive TCP SYN fingerprinting (device hints).
SNIFF_IFACE = _env("TGWS_SNIFF_IFACE", "eth0")

# Privilege separation: the panel talks to these two Unix sockets only.
HELPER_SOCKET = Path(_env("TGWS_HELPER_SOCKET", "/run/tgws-panel/helper.sock"))
NETMON_SOCKET = Path(_env("TGWS_NETMON_SOCKET", "/run/tgws-panel-netmon/netmon.sock"))
HELPER_TIMEOUT = _env_int("TGWS_HELPER_TIMEOUT", 30)
HELPER_MAX_RESPONSE = _env_int("TGWS_HELPER_MAX_RESPONSE", 100 * 1024 * 1024)
NETMON_TIMEOUT = 5
NETMON_INTERVAL = 5
DOCKER_CONTAINERS_DIR = Path(_env("TGWS_DOCKER_CONTAINERS_DIR", "/var/lib/docker/containers"))
HELPER_MAX_REQUEST = 256 * 1024
HELPER_BACKUP_MAX_BYTES = 64 * 1024 * 1024
HELPER_REQUIRE_CGROUP = _env("TGWS_HELPER_REQUIRE_CGROUP", "1") not in ("0", "false", "no")
