#!/usr/bin/env bash
# =============================================================================
# AI YouTube Manager - Auto Installer
# Mendukung:
#   - Ubuntu 22.04 (VPS, x86_64/arm64)
#   - Raspberry Pi OS (Legacy, 64-bit / arm64)
# Database: SQLite (default, tanpa setup eksternal) atau PostgreSQL (opsional).
# Frontend: memakai frontend/dist yang sudah ter-bundle di repo -> TANPA npm/node.
# =============================================================================
set -euo pipefail

APP_NAME="ai-youtube-manager"
INSTALL_DIR="/opt/${APP_NAME}"
SERVICE_USER="aym"
SERVICE="ai-youtube-manager.service"
REPO_URL="${AYM_REPO_URL:-https://github.com/orlin24/YoutubeManager.git}"
BRANCH="${AYM_BRANCH:-main}"
PYTHON_MIN="3.10"
TOKEN_FILE="${INSTALL_DIR}/.github-token"

export DEBIAN_FRONTEND=noninteractive

log()  { printf '\033[1;32m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

require_root() {
    [ "$(id -u)" -eq 0 ] || die "Jalankan sebagai root: sudo bash scripts/install.sh"
}

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID="$ID"
        OS_VERSION="$VERSION_ID"
    else
        die "Tidak bisa mendeteksi OS (/etc/os-release tidak ada)."
    fi
    ARCH="$(uname -m)"
    case "$ARCH" in
        x86_64)  ARCH_LABEL="amd64" ;;
        aarch64|arm64) ARCH_LABEL="arm64" ;;
        *)       warn "Arsitektur '$ARCH' belum teruji - lanjutkan?"; read -r -p "  [y/N] " ok; [ "${ok:-N}" = "y" ] || die "dibatalkan" ;;
    esac
    log "OS: $OS_ID $OS_VERSION | Arch: $ARCH_LABEL"
    case "$OS_ID" in
        ubuntu)
            [ "$OS_VERSION" = "22.04" ] || warn "Ubuntu $OS_VERSION terdeteksi (bukan 22.04) - tetap mencoba."
            ;;
        debian)
            # Raspberry Pi OS berbasis Debian (11=bullseye, 12=bookworm)
            log "Debian/RPi OS terdeteksi: $OS_VERSION"
            ;;
        raspbian)
            log "Raspberry Pi OS (raspbian) terdeteksi"
            ;;
        *)
            warn "Distro '$OS_ID' belum teruji - lanjutkan?"
            read -r -p "  [y/N] " ok; [ "${ok:-N}" = "y" ] || die "dibatalkan"
            ;;
    esac
}

apt_install() {
    if command -v apt-get >/dev/null; then
        log "Menginstall dependensi sistem: $*"
        apt-get update -y -qq
        apt-get install -y -qq "$@" || die "Gagal apt-get install $*"
    else
        warn "apt-get tidak ditemukan - pastikan $* sudah terinstall."
    fi
}

ensure_uv() {
    if ! command -v uv >/dev/null 2>&1; then
        log "Menginstall uv (Python package manager + Python runtime prebuilt)"
        if command -v curl >/dev/null 2>&1; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
        else
            apt_install curl
            curl -LsSf https://astral.sh/uv/install.sh | sh
        fi
        export PATH="$HOME/.local/bin:$PATH"
    fi
    command -v uv >/dev/null 2>&1 || die "uv tidak terinstall."
    log "uv: $(uv --version)"
}

pick_python() {
    # Butuh Python >= 3.10 (kode memakai sintaks 'X | None').
    # RPi OS Legacy (bullseye) default 3.9 -> install 3.12 prebuilt via uv.
    if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
        PY_BIN="$(command -v python3)"
        log "Menggunakan Python sistem: $($PY_BIN --version 2>&1)"
    else
        log "Python sistem < 3.10 - menginstall Python 3.12 via uv (prebuilt ${ARCH_LABEL})"
        uv python install 3.12 || die "Gagal install Python 3.12 via uv"
        PY_BIN="$(uv python find 3.12)"
        log "Python via uv: $($PY_BIN --version 2>&1)"
    fi
}

setup_service_user() {
    if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
        log "Membuat user sistem: $SERVICE_USER"
        useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER" || true
    fi
    mkdir -p "$INSTALL_DIR"
    chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"
}

clone_repo() {
    # Repo privat butuh token: export AYM_GITHUB_TOKEN sebelum install,
    # atau simpan di ${TOKEN_FILE} (chmod 600) - token TIDAK masuk repo.
    GIT_AUTH=()
    if [ -n "${AYM_GITHUB_TOKEN:-}" ]; then
        echo "$AYM_GITHUB_TOKEN" > "$TOKEN_FILE"
        chmod 600 "$TOKEN_FILE"
        GIT_AUTH=(-c http.extraheader="AUTHORIZATION: Bearer ${AYM_GITHUB_TOKEN}")
    elif [ -f "$TOKEN_FILE" ]; then
        TOKEN="$(tr -d '[:space:]' < "$TOKEN_FILE")"
        GIT_AUTH=(-c http.extraheader="AUTHORIZATION: Bearer ${TOKEN}")
    fi
    if [ -d "$INSTALL_DIR/.git" ]; then
        log "Repo sudah ada di $INSTALL_DIR - git pull"
        git -C "$INSTALL_DIR" "${GIT_AUTH[@]}" pull --ff-only origin "$BRANCH" || warn "git pull gagal - lanjut dengan kode existing"
    else
        log "Cloning repo: $REPO_URL (branch $BRANCH)"
        apt_install git ca-certificates
        git -C "$(dirname "$INSTALL_DIR")" "${GIT_AUTH[@]}" clone --branch "$BRANCH" --single-branch "$REPO_URL" "$INSTALL_DIR" || die "Gagal clone repo"
    fi
    [ -d "$INSTALL_DIR/backend" ] || die "Struktur repo tidak sesuai (backend/ tidak ada)."
}

build_venv() {
    log "Membuat virtualenv + install dependencies (bisa beberapa menit di RPi)"
    apt_install sqlite3 build-essential libffi-dev libssl-dev
    cd "$INSTALL_DIR/backend"
    rm -rf .venv
    "$PY_BIN" -m venv .venv
    # pip baru di RPi Legacy lama bisa lambat; uv jauh lebih cepat
    if command -v uv >/dev/null 2>&1; then
        VIRTUAL_ENV="$INSTALL_DIR/backend/.venv" uv pip install --python "$INSTALL_DIR/backend/.venv/bin/python" -r requirements.txt
    else
        .venv/bin/python -m pip install --upgrade pip -q
        .venv/bin/pip install -r requirements.txt -q
    fi
    .venv/bin/python -c "import fastapi, sqlalchemy, alembic" || die "Dependencies gagal terinstall"
    log "Dependencies OK"
}

write_env() {
    ENV_FILE="$INSTALL_DIR/backend/.env"
    if [ -f "$ENV_FILE" ]; then
        log ".env sudah ada - mempertahankan (ganti manual bila perlu)"
        return
    fi
    log "Membuat $ENV_FILE (SQLite default, SECRET_KEY random)"
    SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))' 2>/dev/null || openssl rand -base64 32 | tr -d '\n')"
    if [ "${AYM_DATABASE_URL:-}" != "" ]; then
        DB_URL="$AYM_DATABASE_URL"
    else
        DB_URL="sqlite:///${INSTALL_DIR}/backend/ai_youtube_manager.db"
    fi
    cat > "$ENV_FILE" <<EOF
APP_NAME=AI YouTube Manager
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=5000
APP_ORIGINS=http://localhost:5000
DATABASE_URL=${DB_URL}
SECRET_KEY=${SECRET}
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30
FRONTEND_URL=http://localhost:5000
LOG_LEVEL=INFO
AI_AUTONOMOUS_ENABLED=false
EOF
    chown "$SERVICE_USER":"$SERVICE_USER" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    log ".env dibuat. Setting OAuth/AI/Telegram via web UI (Settings)."
}

run_migrations() {
    log "Menjalankan migrasi database (alembic upgrade head)"
    cd "$INSTALL_DIR/backend"
    if [ -f .venv/bin/alembic ]; then
        .venv/bin/alembic upgrade head
    else
        .venv/bin/python -m alembic upgrade head
    fi
    log "Migrasi selesai"
}

write_service() {
    UNIT="/etc/systemd/system/${SERVICE}"
    log "Menulis systemd unit: $UNIT"
    cat > "$UNIT" <<EOF
[Unit]
Description=AI YouTube Manager (FastAPI + SPA)
After=network.target
Wants=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}/backend
EnvironmentFile=${INSTALL_DIR}/backend/.env
ExecStart=${INSTALL_DIR}/backend/.venv/bin/gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:5000 --timeout 120
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable "$SERVICE"
    systemctl restart "$SERVICE" || warn "Service gagal start - cek: journalctl -u ${SERVICE} -n 50"
    log "Service aktif: systemctl status $SERVICE"
}

setup_auto_update() {
    log "Memasang auto-update (git pull + deps + migrasi + restart) tiap hari 03:00"
    UPDATE_SCRIPT="$INSTALL_DIR/scripts/update.sh"
    [ -f "$UPDATE_SCRIPT" ] || die "scripts/update.sh tidak ditemukan di repo."
    chmod +x "$UPDATE_SCRIPT"
    # Token untuk auto-update repo privat (tidak disimpan di repo)
    if [ -n "${AYM_GITHUB_TOKEN:-}" ] && [ ! -f "$TOKEN_FILE" ]; then
        echo "$AYM_GITHUB_TOKEN" > "$TOKEN_FILE"
        chmod 600 "$TOKEN_FILE"
    fi
    [ -f "$TOKEN_FILE" ] && log "Token GitHub disimpan di $TOKEN_FILE (chmod 600)"

    cat > /etc/systemd/system/ai-youtube-manager-update.service <<EOF
[Unit]
Description=AI YouTube Manager - auto update from GitHub
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=${UPDATE_SCRIPT}
EOF

    cat > /etc/systemd/system/ai-youtube-manager-update.timer <<EOF
[Unit]
Description=Run AI YouTube Manager auto-update daily at 03:00

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
RandomizedDelaySec=600

[Install]
WantedBy=timers.target
EOF

    systemctl daemon-reload
    systemctl enable ai-youtube-manager-update.timer
    systemctl start ai-youtube-manager-update.timer
    log "Auto-update aktif: systemctl list-timers | grep ai-youtube-manager-update"
}

# -----------------------------------------------------------------------------
require_root
detect_os
apt_install curl git ca-certificates util-linux
ensure_uv
pick_python
setup_service_user
clone_repo
build_venv
write_env
run_migrations
write_service
setup_auto_update

PUBLIC_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
log "SELESAI!"
echo
printf '\033[1;32m  Akses web :\033[0m http://%s:5000\n' "${PUBLIC_IP:-<IP-server>}"
printf '\033[1;33m  Catatan   :\033[0m Setup akun admin pertama kali (halaman login -> "Buat akun").\n'
printf '\033[1;33m  Log       :\033[0m journalctl -u %s -f\n' "$SERVICE"
printf '\033[1;33m  Update    :\033[0m sudo %s/scripts/update.sh (manual) atau timer harian 03:00\n' "$INSTALL_DIR"
