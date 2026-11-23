# Security policy

## Deployment model

The panel is an administrative tool. It runs as **root** (it needs Docker, `nsenter` and a
raw socket for device fingerprinting) and is intended for a trusted LAN.

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
