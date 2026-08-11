#!/usr/bin/env bash
# =============================================================================
# AI YouTube Manager - Auto Update dari GitHub
# Digunakan oleh: systemd timer harian (03:00) ATAU manual.
# Aman dijalankan berulang: git pull --ff-only + deps + migrasi + restart.
# Repo privat: simpan token di /opt/ai-youtube-manager/.github-token (chmod 600)
#   atau export GITHUB_TOKEN sebelum menjalankan. Token TIDAK disimpan di repo.
# =============================================================================
set -euo pipefail

APP_NAME="ai-youtube-manager"
INSTALL_DIR="/opt/${APP_NAME}"
SERVICE="ai-youtube-manager.service"
BRANCH="${AYM_BRANCH:-main}"
REPO_URL="${AYM_REPO_URL:-https://github.com/orlin24/YoutubeManager.git}"
TOKEN_FILE="${INSTALL_DIR}/.github-token"
LOG_FILE="/var/log/ai-youtube-manager-update.log"

log() { printf '[update] %s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"; }
die() { printf '[update] ERROR: %s\n' "$*" | tee -a "$LOG_FILE" >&2; exit 1; }

# Hanya jalankan sekali jika dipanggil berbarengan (mis. timer + manual).
exec 9>"${INSTALL_DIR}/.update.lock"
if ! flock -n 9; then
    log "Update lain sedang berjalan - dilewati."
    exit 0
fi

[ -d "$INSTALL_DIR/.git" ] || die "Repo tidak ada di $INSTALL_DIR - jalankan scripts/install.sh dulu."
command -v git >/dev/null 2>&1 || die "git belum terinstall."

# --- Bahan kredensial untuk repo privat -------------------------------------
GIT_AUTH=()
if [ -n "${GITHUB_TOKEN:-}" ]; then
    GIT_AUTH=(-c http.extraheader="AUTHORIZATION: Bearer ${GITHUB_TOKEN}")
elif [ -f "$TOKEN_FILE" ]; then
    TOKEN="$(tr -d '[:space:]' < "$TOKEN_FILE")"
    GIT_AUTH=(-c http.extraheader="AUTHORIZATION: Bearer ${TOKEN}")
fi

# --- 1) Tarik kode terbaru ---------------------------------------------------
log "git fetch + pull (branch ${BRANCH})"
git -C "$INSTALL_DIR" "${GIT_AUTH[@]}" fetch origin "$BRANCH"
if git -C "$INSTALL_DIR" rev-parse --verify -q "origin/$BRANCH" >/dev/null; then
    BEFORE="$(git -C "$INSTALL_DIR" rev-parse HEAD)"
    git -C "$INSTALL_DIR" "${GIT_AUTH[@]}" pull --ff-only origin "$BRANCH"
    AFTER="$(git -C "$INSTALL_DIR" rev-parse HEAD)"
    if [ "$BEFORE" = "$AFTER" ]; then
        log "Tidak ada pembaruan (sudah di commit terbaru)."
        exit 0
    fi
    log "Update: ${BEFORE:0:7} -> ${AFTER:0:7}"
else
    log "Branch origin/$BRANCH belum ada - skip pull."
    exit 0
fi

# --- 2) Install dependency baru (jika requirements.txt berubah) ---------------
if git -C "$INSTALL_DIR" diff --name-only "$BEFORE" "$AFTER" | grep -q "backend/requirements.txt"; then
    log "requirements.txt berubah - menginstall dependencies"
    cd "$INSTALL_DIR/backend"
    if command -v uv >/dev/null 2>&1; then
        VIRTUAL_ENV="$INSTALL_DIR/backend/.venv" uv pip install --python "$INSTALL_DIR/backend/.venv/bin/python" -r requirements.txt
    else
        .venv/bin/pip install -r requirements.txt -q
    fi
fi

# --- 3) Migrasi database ------------------------------------------------------
log "alembic upgrade head"
cd "$INSTALL_DIR/backend"
if [ -f .venv/bin/alembic ]; then
    .venv/bin/alembic upgrade head || die "Migrasi gagal - service tidak di-restart."
else
    .venv/bin/python -m alembic upgrade head || die "Migrasi gagal - service tidak di-restart."
fi

# --- 4) Restart service -------------------------------------------------------
log "restart ${SERVICE}"
systemctl restart "$SERVICE" || die "Restart service gagal."

log "Update selesai."
