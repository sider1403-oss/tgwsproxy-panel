"""Panel-side configuration API.

Reads of the compose file are safe for the unprivileged panel (file is 0644 and
contains no secret). Everything that needs root — .env, Docker, backups — goes
through the helper.
"""
from __future__ import annotations

import base64

from . import config_schema, helper_client, netmon_client, settings

ConfigError = config_schema.ConfigError


def read_compose_text() -> str:
    return config_schema.load_compose_text(settings.COMPOSE_FILE)


def load_compose():
    return config_schema.load_compose(settings.COMPOSE_FILE)


def compose_service() -> dict:
    doc, _ = load_compose()
    return config_schema.services(doc)


def service_env() -> dict:
    return config_schema.service_env(load_compose()[0])


def env_file_values() -> dict:
    data = helper_client.call("config.env", timeout=10)
    return dict(data.get("env") or {})


def effective_env() -> dict:
    data = helper_client.call("config.env", timeout=10)
    return dict(data.get("env") or {})


def snapshot() -> dict:
    doc, text = load_compose()
    svc = config_schema.services(doc)
    env_data = helper_client.call("config.env", timeout=10)
    env = dict(env_data.get("env") or {})
    env_file_keys = list(env_data.get("env_file_keys") or [])
    editable = {k: env.get(k, "") for k in config_schema.ENV_SCHEMA if k in env}
    unknown = sorted(k for k in env if k not in config_schema.ENV_SCHEMA and k != "TG_SECRET" and k not in config_schema.BASE_ENV)
    command = [str(x) for x in (svc.get("command") or [])]
    backups = helper_client.call("backup.list", timeout=15).get("items") or []
    return {
        "compose_raw": text,
        "environment": config_schema.masked_env(env),
        "editable_env": editable,
        "unknown_env": unknown,
        "schema": config_schema.ENV_SCHEMA,
        "image": svc.get("image"),
        "container_name": svc.get("container_name"),
        "restart": svc.get("restart"),
        "ports": [str(p) for p in (svc.get("ports") or [])],
        "command": command,
        "dc_targets": config_schema.parse_dc_targets(command),
        "env_file": {
            "path": str(settings.ENV_FILE),
            "exists": settings.ENV_FILE.exists(),
            "keys": env_file_keys,
        },
        "secret_source": "env_file" if "${TG_SECRET" in str(service_env().get("TG_SECRET", "")) else "compose",
        "backups": backups,
    }


def apply(
    *,
    env_updates: dict[str, str] | None = None,
    dc_targets: list[dict] | None = None,
    secret_value: str | None = None,
    tag: str = "config",
) -> dict:
    clean: dict[str, str] = {}
    for k, v in (env_updates or {}).items():
        if k not in config_schema.ENV_SCHEMA:
            raise ConfigError(f"Параметр {k} не разрешён к изменению через панель")
        clean[str(k)] = config_schema.validate_value(k, v)
    if secret_value is not None:
        secret_value = config_schema.validate_secret(secret_value)
    tag = str(tag or "config")
    if not config_schema.TAG_RE.fullmatch(tag):
        raise ConfigError("Некорректный тег резервной копии")
    result = helper_client.call(
        "config.apply",
        timeout=260,
        environment=clean,
        dc_targets=dc_targets,
        secret=secret_value,
        tag=tag,
    )
    if result.get("ok"):
        try:
            env = effective_env()
            netmon_client.set_port(int(env.get("TG_PORT", settings.PROXY_PORT)))
        except Exception:  # noqa: BLE001 - netmon is best effort
            pass
    return result


def list_backups() -> list[dict]:
    return list(helper_client.call("backup.list", timeout=15).get("items") or [])


def read_backup(name: str) -> bytes:
    data = helper_client.call("backup.read", timeout=30, name=name).get("data") or ""
    return base64.b64decode(data)


def restore_backup(name: str) -> dict:
    return helper_client.call("config.restore", timeout=260, name=name)
