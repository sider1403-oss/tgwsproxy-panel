# Security policy

## Deployment model

The panel is an administrative tool. By design it runs as **root** (it needs Docker,
`nsenter` and a raw socket for device fingerprinting) and has **no built-in authentication**
(the first version was explicitly built for a trusted LAN).

Do not expose port 8090 to the internet. If remote access is required, put the panel behind
a reverse proxy with authentication and TLS, or use an SSH tunnel.

The Telegram bot token is stored in `/opt/tgws-panel/config/alerts.json` (mode `600`);
the API masks it.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository (Security → Report a
vulnerability) instead of a public issue. Include the version/commit, reproduction steps and
the expected impact.
