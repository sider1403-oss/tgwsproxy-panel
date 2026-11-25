# Security policy

## Deployment model

The panel is an administrative tool for a trusted LAN. The FastAPI process runs as the
unprivileged system user `tgws-panel` and has **no** root, Docker Socket, `sudo` or `docker`
group access. Privileged work is split into two small services:

- `tgws-panel-helper` (root, Unix socket, `SO_PEERCRED`) exposes only a fixed allowlist:
  container status/logs/start/stop/restart/version for `tgwsproxy`, `nsenter`/`ss`,
  configuration apply/restore, backups and Docker-log chunks. There is no generic command
  execution and no way to address another container.
- `tgws-panel-netmon` (user `tgws-netmon`, `CAP_NET_RAW`) captures TCP SYN fingerprints
  and has no access to Docker, `.env`, the panel database or proxy configuration.

The panel listens on `0.0.0.0:8090` but must stay LAN-only (or behind a TLS reverse proxy).

Since v1.1.0 the panel requires a login:

- one administrator, created from the first-run page (the administrator chooses the
  password) or the `tgws-panel-admin create-admin` CLI;
- Argon2id password hashes, server-side sessions in SQLite, CSRF protection,
  login rate limiting and a security journal;
- session cookies are `HttpOnly`, `SameSite=Lax` and `Secure` when HTTPS is detected;
- all `/api/*` endpoints except `/api/health`, `/api/auth/status`, `/api/auth/login`
  and `/api/auth/setup` require a session.

Do not expose port 8090 directly to the internet. For remote access use an SSH tunnel or a
reverse proxy with TLS and authentication. When TLS terminates at a reverse proxy, set
`PANEL_TRUSTED_PROXIES` to the proxy address (and `PANEL_ALLOWED_ORIGINS` to the public
origin) so `X-Forwarded-*` headers are trusted only from that proxy.

Secrets: the proxy `TG_SECRET` is masked in API responses; viewing a key requires the current
password. Configuration backups and `config/alerts.json` are root-only (`700`/`600`).

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository (Security → Report a
vulnerability) instead of a public issue. Include the version/commit, reproduction steps and
the expected impact.
