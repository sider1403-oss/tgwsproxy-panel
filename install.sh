#!/usr/bin/env bash
# TGWSProxy panel installer — one-line install / update.
#
#   curl -fsSL https://raw.githubusercontent.com/sider1403-oss/tgwsproxy-panel/main/install.sh | sudo bash
#
# Options:
#   --version <tag>     install a specific release tag (default: latest release/tag)
#   --prefix <dir>      panel directory (default: /opt/tgws-panel)
#   --proxy-dir <dir>   tg-ws-proxy directory (default: /opt/tg-ws-proxy)
#   --port <port>       panel port (default: 8090)
#   --host <host/ip>    public host used in links and CSRF origins (default: detected IP)
#   --from-local <dir>  install from a local checkout instead of downloading a release
#   --skip-systemd      do not install units or start services (for tests/containers)
#   --dry-run           print the plan and exit without changing anything
set -euo pipefail

REPO_OWNER="sider1403-oss"
REPO_NAME="tgwsproxy-panel"
VERSION=""
PREFIX="/opt/tgws-panel"
PROXY_DIR="/opt/tg-ws-proxy"
PORT="8090"
PUBLIC_HOST=""
LOCAL_SRC=""
SKIP_SYSTEMD=0
DRY_RUN=0

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m warn:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
run()  {
  if [ "$DRY_RUN" = "1" ]; then
    printf '    would run: %s\n' "$*"
  else
    "$@"
  fi
}

usage() {
  cat >&2 <<'EOF'
usage: install.sh [options]

  --version <tag>     install a specific release tag (default: latest release/tag)
  --prefix <dir>      panel directory (default: /opt/tgws-panel)
  --proxy-dir <dir>   tg-ws-proxy directory (default: /opt/tg-ws-proxy)
  --port <port>       panel port (default: 8090)
  --host <host/ip>    public host used in links and CSRF origins (default: detected IP)
  --from-local <dir>  install from a local checkout instead of downloading a release
  --skip-systemd      do not install units or start services (for tests/containers)
  --dry-run           print the plan and exit without changing anything
EOF
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --version)      VERSION="${2:?}"; shift 2 ;;
    --prefix)       PREFIX="${2:?}"; shift 2 ;;
    --proxy-dir)    PROXY_DIR="${2:?}"; shift 2 ;;
    --port)         PORT="${2:?}"; shift 2 ;;
    --host)         PUBLIC_HOST="${2:?}"; shift 2 ;;
    --from-local)   LOCAL_SRC="${2:?}"; shift 2 ;;
    --skip-systemd) SKIP_SYSTEMD=1; shift ;;
    --dry-run)      DRY_RUN=1; shift ;;
    -h|--help)      usage ;;
    *) die "unknown option: $1 (try --help)" ;;
  esac
done

[ "$(id -u)" = "0" ] || die "run as root: curl -fsSL ... | sudo bash"
[ -d /run/systemd/system ] || [ "$SKIP_SYSTEMD" = "1" ] || die "systemd is required (use --skip-systemd only for tests)"
command -v curl >/dev/null || die "curl is required"
command -v tar  >/dev/null || die "tar is required"

PKG=""
if   command -v apt-get >/dev/null; then PKG="apt"
elif command -v dnf     >/dev/null; then PKG="dnf"
elif command -v yum     >/dev/null; then PKG="yum"
elif command -v zypper  >/dev/null; then PKG="zypper"
fi

install_pkgs() {
  [ -n "$PKG" ] || { warn "no package manager, skipping install of: $*"; return 0; }
  log "installing packages: $*"
  case "$PKG" in
    apt)    run env DEBIAN_FRONTEND=noninteractive apt-get update -qq
            run env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" ;;
    dnf)    run dnf install -y -q "$@" ;;
    yum)    run yum install -y -q "$@" ;;
    zypper) run zypper --non-interactive install -y "$@" ;;
  esac
}

have_python() {
  command -v python3 >/dev/null 2>&1 &&
    python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null
}

api() { curl -fsSL -H 'Accept: application/vnd.github+json' "https://api.github.com/repos/$REPO_OWNER/$REPO_NAME/$1" 2>/dev/null || true; }

resolve_version() {
  [ -n "$VERSION" ] && return 0
  VERSION="$(api releases/latest | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n1)"
  if [ -z "$VERSION" ]; then
    VERSION="$(api 'tags?per_page=1' | sed -n 's/.*"name": *"\(v[0-9][^"]*\)".*/\1/p' | head -n1)"
  fi
  if [ -z "$VERSION" ]; then
    VERSION="main"
    warn "could not detect a release tag, using branch 'main'"
  fi
}

fetch_source() {
  if [ -n "$LOCAL_SRC" ]; then
    [ -d "$LOCAL_SRC/app" ] || die "--from-local: $LOCAL_SRC does not look like the panel checkout"
    SRC_DIR="$LOCAL_SRC"
    log "using local sources from $SRC_DIR"
    return 0
  fi
  local url dir
  if [ "$VERSION" = "main" ]; then
    url="https://github.com/$REPO_OWNER/$REPO_NAME/archive/refs/heads/main.tar.gz"
  else
    url="https://github.com/$REPO_OWNER/$REPO_NAME/archive/refs/tags/$VERSION.tar.gz"
  fi
  log "downloading $url"
  SRC_DIR="$(mktemp -d /tmp/tgws-panel-src.XXXXXX)"
  if [ "$DRY_RUN" = "1" ]; then
    printf '    would download and unpack into %s\n' "$SRC_DIR"
    SRC_DIR=""
    return 0
  fi
  curl -fsSL "$url" -o "$SRC_DIR/src.tar.gz" || die "cannot download $url"
  tar xzf "$SRC_DIR/src.tar.gz" -C "$SRC_DIR"
  dir="$(find "$SRC_DIR" -maxdepth 1 -mindepth 1 -type d -name "$REPO_NAME-*" | head -n1)"
  [ -n "$dir" ] || die "cannot find extracted source in $SRC_DIR"
  rm -f "$SRC_DIR/src.tar.gz"
  SRC_DIR="$dir"
}

build_frontend() {
  local dest="$1"
  command -v npm >/dev/null || install_pkgs nodejs npm
  command -v npm >/dev/null || die "npm is required to build the frontend; install Node.js 18+ and re-run"
  log "building frontend from sources"
  run env npm_config_cache=/tmp/tgws-npm-cache npm --prefix "$SRC_DIR/frontend-src" ci --no-audit --no-fund
  run env npm_config_cache=/tmp/tgws-npm-cache npm --prefix "$SRC_DIR/frontend-src" run build
  run cp -a "$SRC_DIR/frontend/." "$dest/"
}

fetch_frontend() {
  local dest="$1" url tmp
  if [ -n "$LOCAL_SRC" ] && [ -d "$LOCAL_SRC/frontend/index.html" ]; then
    log "using prebuilt frontend from $LOCAL_SRC/frontend"
    run cp -a "$LOCAL_SRC/frontend/." "$dest/"
    return 0
  fi
  if [ "$VERSION" != "main" ] && [ "$DRY_RUN" = "0" ]; then
    url="https://github.com/$REPO_OWNER/$REPO_NAME/releases/download/$VERSION/frontend-dist.tar.gz"
    tmp="$(mktemp /tmp/tgws-frontend.XXXXXX.tar.gz)"
    if curl -fsSL "$url" -o "$tmp" 2>/dev/null; then
      log "using prebuilt frontend from $VERSION release asset"
      tar xzf "$tmp" -C "$dest"
      rm -f "$tmp"
      return 0
    fi
    rm -f "$tmp"
  fi
  if [ "$DRY_RUN" = "1" ]; then
    log "would build or download the frontend"
    return 0
  fi
  build_frontend "$dest"
}

stop_services() {
  [ "$SKIP_SYSTEMD" = "1" ] && return 0
  log "stopping running services (if any)"
  run systemctl stop tgws-panel tgws-panel-netmon tgws-panel-helper 2>/dev/null || true
}

create_users() {
  getent group tgws-panel >/dev/null || run groupadd --system tgws-panel
  id -u tgws-panel >/dev/null 2>&1 || run useradd --system --gid tgws-panel --home-dir "$PREFIX" \
    --no-create-home --shell /usr/sbin/nologin tgws-panel
  getent group tgws-netmon >/dev/null || run groupadd --system tgws-netmon
  id -u tgws-netmon >/dev/null 2>&1 || run useradd --system --gid tgws-netmon --home-dir /var/lib/tgws-panel-netmon \
    --no-create-home --shell /usr/sbin/nologin tgws-netmon
}

install_files() {
  log "installing panel files into $PREFIX"
  run install -d -m 755 "$PREFIX"
  if [ "$DRY_RUN" = "1" ]; then
    printf '    would replace %s/app and %s/frontend\n' "$PREFIX" "$PREFIX"
    return 0
  fi
  rm -rf "$PREFIX/app.new" "$PREFIX/frontend.new"
  cp -a "$SRC_DIR/app" "$PREFIX/app.new"
  install -d -m 755 "$PREFIX/frontend.new"
  fetch_frontend "$PREFIX/frontend.new"
  rm -rf "$PREFIX/app.old" "$PREFIX/frontend.old"
  [ -d "$PREFIX/app" ] && mv "$PREFIX/app" "$PREFIX/app.old"
  [ -d "$PREFIX/frontend" ] && mv "$PREFIX/frontend" "$PREFIX/frontend.old"
  mv "$PREFIX/app.new" "$PREFIX/app"
  mv "$PREFIX/frontend.new" "$PREFIX/frontend"
  rm -rf "$PREFIX/app.old" "$PREFIX/frontend.old"
  for f in requirements.txt README.md CHANGELOG.md SECURITY.md LICENSE; do
    if [ -f "$SRC_DIR/$f" ]; then install -m 644 "$SRC_DIR/$f" "$PREFIX/$f"; fi
  done
  if [ -d "$SRC_DIR/deploy" ]; then
    rm -rf "$PREFIX/deploy"
    cp -a "$SRC_DIR/deploy" "$PREFIX/deploy"
  fi
  chown -R root:root "$PREFIX/app" "$PREFIX/frontend" 2>/dev/null || true
}

setup_dirs() {
  log "preparing data directories and permissions"
  run install -d -o tgws-panel -g tgws-panel -m 700 "$PREFIX/data" "$PREFIX/config"
  run install -d -o tgws-panel -g tgws-panel -m 750 "$PREFIX/logs"
  run install -d -o root -g root -m 700 "$PREFIX/backups"
  run install -d -o tgws-netmon -g tgws-netmon -m 700 /var/lib/tgws-panel-netmon
  if [ "$DRY_RUN" = "0" ]; then
    chown -R tgws-panel:tgws-panel "$PREFIX/data" "$PREFIX/config" "$PREFIX/logs" 2>/dev/null || true
    [ -f "$PREFIX/data/panel.db" ] && chmod 600 "$PREFIX/data/panel.db"* 2>/dev/null || true
    [ -f "$PREFIX/logs/panel.log" ] && chmod 600 "$PREFIX/logs/panel.log"* 2>/dev/null || true
  fi
}

detect_host() {
  [ -n "$PUBLIC_HOST" ] && return 0
  PUBLIC_HOST="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [ -n "$PUBLIC_HOST" ] || PUBLIC_HOST="127.0.0.1"
}

detect_iface() {
  ip route 2>/dev/null | awk '/^default/ {print $5; exit}'
}

setup_env() {
  local env=/etc/tgws-panel.env
  if [ -f "$env" ]; then
    log "keeping existing $env"
    return 0
  fi
  log "creating $env"
  detect_host
  run install -m 600 "$SRC_DIR/deploy/panel.env.example" "$env"
  if [ "$DRY_RUN" = "0" ]; then
    local iface; iface="$(detect_iface)"; [ -n "$iface" ] || iface="eth0"
    sed -i \
      -e "s#^PANEL_PUBLIC_HOST=.*#PANEL_PUBLIC_HOST=$PUBLIC_HOST#" \
      -e "s#^PANEL_PORT=.*#PANEL_PORT=$PORT#" \
      -e "s#^TGWS_PANEL_ROOT=.*#TGWS_PANEL_ROOT=$PREFIX#" \
      -e "s#^TGWS_PROXY_DIR=.*#TGWS_PROXY_DIR=$PROXY_DIR#" \
      -e "s#^TGWS_SNIFF_IFACE=.*#TGWS_SNIFF_IFACE=$iface#" \
      "$env"
  fi
}

setup_venv() {
  log "installing Python dependencies"
  run python3 -m venv "$PREFIX/venv"
  run "$PREFIX/venv/bin/pip" install --quiet --upgrade pip
  run "$PREFIX/venv/bin/pip" install --quiet -r "$PREFIX/requirements.txt"
}

install_units() {
  [ "$SKIP_SYSTEMD" = "1" ] && { log "skipping systemd units (--skip-systemd)"; return 0; }
  log "installing systemd units and CLI"
  for unit in tgws-panel.service tgws-panel-helper.service tgws-panel-netmon.service; do
    run install -m 644 "$SRC_DIR/deploy/$unit" "/etc/systemd/system/$unit"
  done
  run install -m 755 "$SRC_DIR/deploy/tgws-panel-admin" /usr/local/bin/tgws-panel-admin
  run install -d -m 755 /etc/systemd/journald.conf.d
  run install -m 644 "$SRC_DIR/deploy/99-tgws-panel.conf" /etc/systemd/journald.conf.d/99-tgws-panel.conf
  run systemctl restart systemd-journald
  run systemctl daemon-reload
}

start_services() {
  [ "$SKIP_SYSTEMD" = "1" ] && return 0
  log "starting services"
  run systemctl enable --now tgws-panel-helper tgws-panel-netmon tgws-panel
  [ "$DRY_RUN" = "1" ] && return 0
  log "waiting for the panel on port $PORT"
  local i
  for i in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
      log "panel is up"
      return 0
    fi
    sleep 1
  done
  warn "panel did not answer in 30s; check: journalctl -u tgws-panel -n 50 --no-pager"
}

summary() {
  detect_host
  cat <<EOF

TGWSProxy panel $VERSION installed.

  Panel:        http://$PUBLIC_HOST:$PORT
  Directory:    $PREFIX
  Env file:     /etc/tgws-panel.env
  Services:     tgws-panel tgws-panel-helper tgws-panel-netmon

First login: open the URL and create the administrator (login + password >= 12 chars),
or use:  sudo tgws-panel-admin create-admin --username <login>

Update later:  curl -fsSL https://raw.githubusercontent.com/$REPO_OWNER/$REPO_NAME/main/install.sh | sudo bash -s -- --version <tag>
Uninstall:     systemctl disable --now tgws-panel tgws-panel-netmon tgws-panel-helper
               rm -rf $PREFIX /var/lib/tgws-panel-netmon /etc/tgws-panel.env
EOF
}

main() {
  resolve_version
  log "installer: $REPO_NAME $VERSION -> $PREFIX"
  if [ "$DRY_RUN" = "1" ]; then log "dry run: nothing will be changed"; fi
  if ! have_python; then
    install_pkgs python3 python3-venv
    have_python || die "Python 3.11+ is required"
  fi
  if [ ! -d "$PROXY_DIR" ]; then
    warn "tg-ws-proxy is not found in $PROXY_DIR — install it first (see README)"
  fi
  fetch_source
  create_users
  stop_services
  install_files
  setup_dirs
  setup_env
  setup_venv
  install_units
  start_services
  if [ -z "${SRC_DIR:-}" ] || [ -z "$LOCAL_SRC" ]; then
    summary
  else
    summary
  fi
  if [ -n "${SRC_DIR:-}" ] && [ -z "$LOCAL_SRC" ] && [ "$DRY_RUN" = "0" ]; then
    rm -rf "$(dirname "$SRC_DIR")" 2>/dev/null || true
  fi
}

main "$@"
