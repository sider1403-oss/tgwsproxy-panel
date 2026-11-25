"""Pure configuration schema/validation helpers shared by panel and helper.

No Docker, filesystem writes or database access here: this module can safely be
imported by both the unprivileged panel and the privileged helper.
"""
from __future__ import annotations

import ipaddress
import re

from ruamel.yaml import YAML

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.width = 4096
_yaml.indent(mapping=2, sequence=4, offset=2)

ENV_SCHEMA: dict[str, dict] = {
    "TG_HOST": {"type": "host", "label": "Адрес прослушивания", "group": "network"},
    "TG_PORT": {"type": "port", "label": "Порт", "group": "network"},
    "TG_LINK_IP": {"type": "ip", "label": "IP в ссылке tg://", "group": "network"},
    "TG_LISTEN_FAKETLS_DOMAIN": {"type": "domain", "label": "FakeTLS домен (SNI)", "group": "network"},
    "TG_POOL_SIZE": {"type": "int", "min": 0, "max": 4096, "label": "Размер пула WS", "group": "network"},
    "TG_DEFAULT_DOMAINS": {"type": "bool", "label": "CF домены по умолчанию", "group": "cloudflare"},
    "TG_CF_DISABLE_TLS": {"type": "bool", "label": "CF без TLS (ws://)", "group": "cloudflare"},
    "TG_CF_BALANCE": {"type": "bool", "label": "Балансировка CF", "group": "cloudflare"},
    "TG_CF_DOMAIN": {"type": "csv_domain", "label": "CF домены", "group": "cloudflare"},
    "TG_CF_WORKER_DOMAIN": {"type": "csv_domain", "label": "CF Worker домены", "group": "cloudflare"},
    "TG_CF_IP": {"type": "csv_ip", "label": "CF IP", "group": "cloudflare"},
    "TG_IP_FAIL_COOLDOWN": {"type": "int", "min": 0, "max": 86400, "label": "Cooldown DC IP, с", "group": "cloudflare"},
    "TG_FRONTING_DOMAIN": {"type": "domain", "label": "Fronting домен", "group": "cloudflare"},
    "TG_CLIENT_IDLE_TIMEOUT": {"type": "int", "min": 0, "max": 86400, "label": "Idle timeout, с", "group": "limits"},
    "TG_MAX_CONNECTIONS": {"type": "int", "min": 0, "max": 1000000, "label": "Макс. соединений", "group": "limits"},
    "TG_BUF_KB": {"type": "int", "min": 1, "max": 65536, "label": "Буфер, КиБ", "group": "limits"},
    "TG_VERBOSE": {"type": "bool", "label": "Verbose (DEBUG)", "group": "debug"},
    "TG_QUIET": {"type": "bool", "label": "Quiet (без логов)", "group": "debug"},
    "TG_SKIP_TLS_VERIFY": {"type": "bool", "label": "Не проверять TLS", "group": "debug"},
    "TG_NO_H2": {"type": "bool", "label": "Отключить HTTP/2", "group": "debug"},
    "TG_SOCKS_ENABLED": {"type": "bool", "label": "SOCKS5 включён", "group": "socks"},
    "TG_SOCKS_HOST": {"type": "ip", "label": "SOCKS5 адрес", "group": "socks"},
    "TG_SOCKS_PORT": {"type": "port", "label": "SOCKS5 порт", "group": "socks"},
    "TG_PINNED_UPSTREAM": {"type": "tiers", "label": "Порядок upstream", "group": "advanced"},
    "TG_PINNED_MEDIA_UPSTREAM": {"type": "tiers", "label": "Порядок upstream (медиа)", "group": "advanced"},
    "TG_OUTBOUND_PROXY": {"type": "str", "label": "Исходящий прокси", "group": "advanced"},
    "TG_NO_PROXY": {"type": "str", "label": "No-proxy список", "group": "advanced"},
    "TG_MTPROTO_PROXY": {"type": "str", "label": "MTProto upstream", "group": "advanced"},
    "TG_LOG_FILE": {"type": "str", "label": "Файл лога", "group": "advanced"},
}

BOOL_KEYS = {k for k, v in ENV_SCHEMA.items() if v["type"] == "bool"}
TIERS = {"ws", "cfworker", "cfproxy", "mtproto", "tcp"}
BASE_ENV = {"PATH", "HOSTNAME", "HOME", "TERM", "LANG", "PWD", "SHLVL", "TZ"}

SECRET_RE = re.compile(r"^[0-9a-f]{32}(,[0-9a-f]{32})*$")
TAG_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


class ConfigError(ValueError):
    pass


def load_compose_text(path) -> str:
    return path.read_text(encoding="utf-8")


def load_compose(path):
    text = load_compose_text(path)
    doc = _yaml.load(text)
    services(doc)
    return doc, text


def services(doc) -> dict:
    if not isinstance(doc, dict) or "services" not in doc:
        raise ConfigError("В compose-файле нет секции services")
    svc = doc["services"].get("tgwsproxy")
    if svc is None:
        raise ConfigError("В compose-файле нет сервиса tgwsproxy")
    return svc


def service_env(doc) -> dict:
    svc = services(doc)
    env = svc.get("environment") or {}
    return {str(k): str(v) if v is not None else "" for k, v in env.items()}


def mask_secret(value: str) -> str:
    parts = []
    for part in str(value).split(","):
        p = part.strip()
        if not p:
            continue
        if len(p) > 12:
            parts.append(p[:4] + "…" + p[-4:])
        else:
            parts.append("***")
    return ",".join(parts)


def masked_env(env: dict) -> dict:
    out = {}
    for k, v in env.items():
        out[k] = mask_secret(v) if k == "TG_SECRET" else v
    return out


def parse_dc_targets(command: list) -> list[dict]:
    targets = []
    i = 0
    while i < len(command):
        if str(command[i]) == "--dc-ip" and i + 1 < len(command):
            raw = str(command[i + 1])
            if ":" in raw:
                dc, ip = raw.split(":", 1)
                targets.append({"dc": dc, "ip": ip})
            i += 2
            continue
        i += 1
    return targets


def validate_value(key: str, value: str) -> str:
    spec = ENV_SCHEMA[key]
    t = spec["type"]
    v = str(value).strip()
    if t == "port":
        try:
            n = int(v)
        except ValueError:
            raise ConfigError(f"{key}: ожидается целое число (порт)")
        if not 1 <= n <= 65535:
            raise ConfigError(f"{key}: порт вне диапазона 1..65535")
        return str(n)
    if t == "int":
        try:
            n = int(v)
        except ValueError:
            raise ConfigError(f"{key}: ожидается целое число")
        lo, hi = spec.get("min"), spec.get("max")
        if lo is not None and n < lo or hi is not None and n > hi:
            raise ConfigError(f"{key}: значение вне диапазона {lo}..{hi}")
        return str(n)
    if t == "bool":
        lv = v.lower()
        if lv not in ("true", "false", "1", "0", "yes", "no", ""):
            raise ConfigError(f"{key}: ожидается true/false")
        return "true" if lv in ("true", "1", "yes") else "false"
    if t == "ip":
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ConfigError(f"{key}: некорректный IP-адрес «{v}»")
        return v
    if t == "host":
        if v not in ("0.0.0.0", "::"):
            try:
                ipaddress.ip_address(v)
            except ValueError:
                raise ConfigError(f"{key}: некорректный адрес прослушивания «{v}»")
        return v
    if t == "domain":
        if v and not re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?", v):
            raise ConfigError(f"{key}: некорректный домен")
        return v
    if t == "csv_domain":
        for part in filter(None, (p.strip() for p in v.split(","))):
            if not re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?", part):
                raise ConfigError(f"{key}: некорректный домен «{part}»")
        return v
    if t == "csv_ip":
        for part in filter(None, (p.strip() for p in v.split(","))):
            try:
                ipaddress.ip_address(part)
            except ValueError:
                raise ConfigError(f"{key}: некорректный IP «{part}»")
        return v
    if t == "tiers":
        for part in filter(None, (p.strip() for p in v.split(","))):
            if part not in TIERS:
                raise ConfigError(f"{key}: допустимые уровни: {', '.join(sorted(TIERS))}")
        return v
    return v


def validate_targets(targets: list[dict]) -> list[dict]:
    out = []
    for t in targets:
        dc = str(t.get("dc", "")).strip()
        ip = str(t.get("ip", "")).strip()
        if not dc and not ip:
            continue
        if not re.fullmatch(r"[1-5]", dc):
            raise ConfigError(f"DC «{dc}»: допустимы DC 1..5")
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise ConfigError(f"DC{dc}: некорректный IP-адрес «{ip}»")
        out.append({"dc": dc, "ip": ip})
    return out


def validate_secret(value: str) -> str:
    v = str(value).strip()
    if not SECRET_RE.fullmatch(v):
        raise ConfigError("TG_SECRET: ожидается список 32-символьных hex-ключей через запятую")
    if len(v.split(",")) > 64:
        raise ConfigError("TG_SECRET: слишком много ключей")
    return v
