"""Read, validate, back up and apply the proxy's docker-compose configuration."""
from __future__ import annotations

import ipaddress
import json
import re
import shutil
import threading
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from . import db, dockerctl, settings

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.width = 4096
_yaml.indent(mapping=2, sequence=4, offset=2)

_apply_lock = threading.Lock()

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


class ConfigError(ValueError):
    pass


def _services(doc) -> dict:
    if not isinstance(doc, dict) or "services" not in doc:
        raise ConfigError("В compose-файле нет секции services")
    svc = doc["services"].get(settings.SERVICE_KEY)
    if svc is None:
        raise ConfigError(f"В compose-файле нет сервиса {settings.SERVICE_KEY}")
    return svc


def read_compose_text() -> str:
    return settings.COMPOSE_FILE.read_text(encoding="utf-8")


def load_compose():
    text = read_compose_text()
    doc = _yaml.load(text)
    _services(doc)
    return doc, text


def compose_service() -> dict:
    doc, _ = load_compose()
    return _services(doc)


def service_env() -> dict:
    svc = compose_service()
    env = svc.get("environment") or {}
    return {str(k): str(v) if v is not None else "" for k, v in env.items()}


def effective_env() -> dict:
    info = dockerctl.inspect_container()
    if info:
        pairs = info.get("Config", {}).get("Env") or []
        out = {}
        for item in pairs:
            if "=" in item:
                k, v = item.split("=", 1)
                out[k] = v
        if out:
            return out
    # Fallback: compose env with ${VAR} substitution from .env
    env = service_env()
    values = env_file_values()
    for k, v in list(env.items()):
        m = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::[^}]*)?\}", v or "")
        if m:
            env[k] = values.get(m.group(1), "")
    return env


def env_file_values() -> dict:
    out: dict[str, str] = {}
    if not settings.ENV_FILE.exists():
        return out
    for line in settings.ENV_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


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
        if k == "TG_SECRET":
            out[k] = mask_secret(v)
        else:
            out[k] = v
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


def snapshot() -> dict:
    doc, text = load_compose()
    svc = _services(doc)
    env = effective_env()
    editable = {k: env.get(k, "") for k in ENV_SCHEMA if k in env}
    unknown = sorted(k for k in env if k not in ENV_SCHEMA and k != "TG_SECRET" and k not in BASE_ENV)
    command = [str(x) for x in (svc.get("command") or [])]
    return {
        "compose_raw": text,
        "environment": masked_env(env),
        "editable_env": editable,
        "unknown_env": unknown,
        "schema": ENV_SCHEMA,
        "image": svc.get("image"),
        "container_name": svc.get("container_name"),
        "restart": svc.get("restart"),
        "ports": [str(p) for p in (svc.get("ports") or [])],
        "command": command,
        "dc_targets": parse_dc_targets(command),
        "env_file": {
            "path": str(settings.ENV_FILE),
            "exists": settings.ENV_FILE.exists(),
            "keys": sorted(env_file_values().keys()),
        },
        "secret_source": "env_file" if "${TG_SECRET" in str(service_env().get("TG_SECRET", "")) else "compose",
        "backups": list_backups(),
    }


def _validate_value(key: str, value: str) -> str:
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


def backup(tag: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", tag)[:40] or "manual"
    dest = settings.BACKUP_DIR / f"{stamp}-{safe}"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(settings.COMPOSE_FILE, dest / "docker-compose.yml")
    if settings.ENV_FILE.exists():
        shutil.copy2(settings.ENV_FILE, dest / ".env")
        try:
            (dest / ".env").chmod(0o600)
        except OSError:
            pass
    meta = {"tag": tag, "created_at": db.now_iso(), "files": sorted(p.name for p in dest.iterdir())}
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    _prune_backups()
    return dest


def _prune_backups(keep: int | None = None) -> None:
    keep = keep or settings.BACKUPS_KEEP
    try:
        dirs = sorted((d for d in settings.BACKUP_DIR.iterdir() if d.is_dir()), reverse=True)
    except OSError:
        return
    for old in dirs[keep:]:
        shutil.rmtree(old, ignore_errors=True)


def list_backups() -> list[dict]:
    out = []
    if not settings.BACKUP_DIR.exists():
        return out
    for d in sorted(settings.BACKUP_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        meta = {}
        mf = d / "meta.json"
        if mf.exists():
            try:
                meta = json.loads(mf.read_text(encoding="utf-8"))
            except ValueError:
                meta = {}
        out.append(
            {
                "name": d.name,
                "created_at": meta.get("created_at"),
                "tag": meta.get("tag"),
                "size": sum(p.stat().st_size for p in d.iterdir() if p.is_file()),
            }
        )
    return out


def _write_env_secret(value: str) -> None:
    settings.ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if settings.ENV_FILE.exists():
        lines = settings.ENV_FILE.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith("TG_SECRET="):
            lines[i] = f"TG_SECRET={value}"
            found = True
            break
    if not found:
        lines.append(f"TG_SECRET={value}")
    text = "\n".join(lines).rstrip("\n") + "\n"
    settings.ENV_FILE.write_text(text, encoding="utf-8")
    try:
        settings.ENV_FILE.chmod(0o600)
    except OSError:
        pass


def _restore_backup_files(src: Path) -> None:
    shutil.copy2(src / "docker-compose.yml", settings.COMPOSE_FILE)
    if (src / ".env").exists():
        shutil.copy2(src / ".env", settings.ENV_FILE)
        try:
            settings.ENV_FILE.chmod(0o600)
        except OSError:
            pass


def _wait_ready(timeout: float = 50.0) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        st = dockerctl.status()
        last = st
        health = st.get("health")
        if st.get("running") and health in (None, "healthy"):
            return st
        time.sleep(1.5)
    return last


def apply(
    *,
    env_updates: dict[str, str] | None = None,
    dc_targets: list[dict] | None = None,
    secret_value: str | None = None,
    tag: str = "config",
) -> dict:
    """Validate and apply configuration changes; always keeps a backup."""
    with _apply_lock:
        started = time.time()
        env_updates = env_updates or {}
        clean: dict[str, str] = {}
        for k, v in env_updates.items():
            if k not in ENV_SCHEMA:
                raise ConfigError(f"Параметр {k} не разрешён к изменению через панель")
            clean[k] = _validate_value(k, v)
        targets = validate_targets(dc_targets) if dc_targets is not None else None

        doc, _ = load_compose()
        svc = _services(doc)
        current_env = svc.get("environment") or {}
        env_sets = {k: v for k, v in clean.items() if str(current_env.get(k)) != v}
        current_command = [str(x) for x in (svc.get("command") or [])]
        targets_changed = targets is not None and parse_dc_targets(current_command) != targets
        uses_env_file = "${TG_SECRET" in str(service_env().get("TG_SECRET", ""))
        if secret_value is not None:
            if uses_env_file:
                old_secret = (env_file_values().get("TG_SECRET") or "").strip()
            else:
                old_secret = str(current_env.get("TG_SECRET") or "").strip()
            secret_changed = old_secret != secret_value.strip()
        else:
            secret_changed = False

        if not env_sets and not targets_changed and not secret_changed:
            return {
                "ok": True,
                "noop": True,
                "message": "Изменений нет — перезапуск не требуется",
                "duration_ms": int((time.time() - started) * 1000),
                "state": dockerctl.status(),
            }

        bak = backup(tag)
        old_compose = read_compose_text()
        old_env = settings.ENV_FILE.read_text(encoding="utf-8") if settings.ENV_FILE.exists() else None
        try:
            if env_sets:
                env = svc.get("environment")
                if env is None:
                    svc["environment"] = env = {}
                for k, v in env_sets.items():
                    env[k] = v
            if targets_changed and targets is not None:
                rebuilt: list = []
                inserted = False
                i = 0
                while i < len(current_command):
                    if current_command[i] == "--dc-ip" and i + 1 < len(current_command):
                        if not inserted:
                            for t in targets:
                                rebuilt.extend(["--dc-ip", DoubleQuotedScalarString(f"{t['dc']}:{t['ip']}")])
                            inserted = True
                        i += 2
                        continue
                    rebuilt.append(current_command[i])
                    i += 1
                if not inserted:
                    for t in targets:
                        rebuilt.extend(["--dc-ip", DoubleQuotedScalarString(f"{t['dc']}:{t['ip']}")])
                svc["command"] = rebuilt
            if secret_changed:
                assert secret_value is not None
                if uses_env_file:
                    _write_env_secret(secret_value)
                else:
                    svc.setdefault("environment", {})["TG_SECRET"] = secret_value

            buf = StringIO()
            _yaml.dump(doc, buf)
            new_text = buf.getvalue()
            if old_compose.startswith("\n") and not new_text.startswith("\n"):
                new_text = "\n" + new_text
            if old_compose.endswith("\n\n") and not new_text.endswith("\n\n"):
                new_text += "\n"
            if new_text != old_compose:
                settings.COMPOSE_FILE.write_text(new_text, encoding="utf-8")

            rc, out, err = dockerctl.compose(["config", "-q"], timeout=30)
            if rc != 0:
                raise ConfigError("Проверка compose не пройдена: " + (err or out).strip())

            rc, out, err = dockerctl.compose(["up", "-d"], timeout=180)
            if rc != 0:
                raise ConfigError("docker compose up -d: " + (err or out).strip()[-1500:])

            st = _wait_ready()
            if not st.get("running"):
                raise ConfigError("Контейнер не перешёл в состояние running после применения")

            ok, tcp_msg = dockerctl.tcp_check(settings.PUBLIC_HOST, int(effective_env().get("TG_PORT", 1443)))
            return {
                "ok": True,
                "backup": bak.name,
                "duration_ms": int((time.time() - started) * 1000),
                "output": (out or "").strip()[-4000:],
                "state": st,
                "port_check": tcp_msg,
                "warnings": [] if ok else [tcp_msg],
            }
        except Exception as exc:  # noqa: BLE001 - roll back on any failure
            try:
                settings.COMPOSE_FILE.write_text(old_compose, encoding="utf-8")
                if old_env is not None:
                    settings.ENV_FILE.write_text(old_env, encoding="utf-8")
            except OSError:
                pass
            rollback_msg = ""
            try:
                dockerctl.compose(["up", "-d"], timeout=180)
                st = _wait_ready(30)
                rollback_msg = "Конфигурация восстановлена, контейнер запущен" if st.get("running") else "Откат выполнен, но контейнер не запущен"
            except Exception as exc2:  # noqa: BLE001
                rollback_msg = f"Ошибка откатa: {exc2}"
            return {
                "ok": False,
                "error": str(exc),
                "backup": bak.name,
                "rollback": rollback_msg,
                "duration_ms": int((time.time() - started) * 1000),
            }


def restore_backup(name: str) -> dict:
    with _apply_lock:
        root = settings.BACKUP_DIR.resolve()
        src = (settings.BACKUP_DIR / name).resolve()
        try:
            src.relative_to(root)
        except ValueError:
            raise ConfigError("Некорректное имя резервной копии")
        if not src.is_dir() or not (src / "docker-compose.yml").exists():
            raise ConfigError("Резервная копия не найдена")
        bak = backup("before-restore")
        old_compose = read_compose_text()
        old_env = settings.ENV_FILE.read_text(encoding="utf-8") if settings.ENV_FILE.exists() else None
        try:
            _restore_backup_files(src)
            rc, out, err = dockerctl.compose(["config", "-q"], timeout=30)
            if rc != 0:
                raise ConfigError("Восстановленная конфигурация некорректна: " + (err or out).strip())
            rc, out, err = dockerctl.compose(["up", "-d"], timeout=180)
            if rc != 0:
                raise ConfigError("docker compose up -d: " + (err or out).strip())
            st = _wait_ready()
            return {"ok": True, "state": st, "backup_before_restore": bak.name, "output": (out or "").strip()[-2000:]}
        except Exception as exc:  # noqa: BLE001
            settings.COMPOSE_FILE.write_text(old_compose, encoding="utf-8")
            if old_env is not None:
                settings.ENV_FILE.write_text(old_env, encoding="utf-8")
            try:
                dockerctl.compose(["up", "-d"], timeout=180)
            except Exception:  # noqa: BLE001
                pass
            return {"ok": False, "error": str(exc), "backup_before_restore": bak.name}
