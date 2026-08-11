# Deploy Lokal / VPS (tanpa Docker)

Aplikasi dapat diinstall langsung di server fisik tanpa Docker, menggunakan
`scripts/install.sh` (otomatis, sekali jalan) atau manual langkah demi langkah.

## Platform yang didukung

| Platform | Arch | Python | Catatan |
|---|---|---|---|
| Ubuntu 22.04 (VPS) | x86_64 / arm64 | sistem 3.10+ | Paling stabil |
| Raspberry Pi OS Legacy 64-bit (bookworm/bullseye) | aarch64 | 3.12 via `uv` (prebuilt) | RPi 4/5, disarankan RAM >= 2GB |

Installer otomatis mendeteksi OS + arsitektur dan memilih Python yang sesuai
(RPi Legacy default Python 3.9 dipakai `uv` untuk install 3.12 prebuilt arm64,
tanpa perlu compile).

## Prasyarat

- Ubuntu 22.04 ATAU Raspberry Pi OS 64-bit (Legacy).
- Jalankan sebagai **root** (`sudo -i` atau `sudo bash ...`).
- Koneksi internet. Repo **publik** (default) atau privat (baca bagian token).

## Install otomatis (cara cepat)

```bash
# Repo publik
curl -fsSL https://raw.githubusercontent.com/orlin24/YoutubeManager/main/scripts/install.sh | bash

# atau clone lalu jalankan langsung
git clone https://github.com/orlin24/YoutubeManager.git
cd YoutubeManager
sudo bash scripts/install.sh
```

Yang dilakukan installer:

1. Deteksi OS + arsitektur, install dependensi sistem (git, curl, sqlite3, build-essential, util-linux).
2. Install `uv` (jika belum ada) untuk manajemen Python cepat.
3. Buat user sistem `aym`, clone repo ke `/opt/ai-youtube-manager`.
4. Buat virtualenv di `backend/.venv` + install `requirements.txt`.
5. Buat `backend/.env` (SQLite default di `backend/ai_youtube_manager.db`, `SECRET_KEY` acak).
6. Jalankan migrasi database: `alembic upgrade head`.
7. Pasang systemd service `ai-youtube-manager.service` (gunicorn + uvicorn worker, port 5000).
8. Pasang auto-update harian (timer systemd 03:00) memakai `scripts/update.sh`.

Selesai: buka `http://<IP-server>:5000`, buat akun admin di halaman login.

### Repo privat (token GitHub)

Jika repo diset privat, beri token saat install:

```bash
sudo AYM_GITHUB_TOKEN=github_pat_xxx bash scripts/install.sh
```

Token disimpan di `/opt/ai-youtube-manager/.github-token` (chmod 600) dan dipakai
oleh `update.sh` untuk git pull otomatis. Token **tidak pernah** disimpan di repo.

## Database: SQLite vs PostgreSQL

- **Default: SQLite** (file `backend/ai_youtube_manager.db`) - nol setup, cukup
  untuk pemakaian lokal/1 user. Semua migrasi Alembic sudah kompatibel SQLite.
- **Opsional PostgreSQL** untuk skala besar: export sebelum install:

```bash
sudo AYM_DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/ai_youtube_manager" bash scripts/install.sh
```

## Update otomatis dari GitHub (tanpa install ulang)

`scripts/update.sh` melakukan: `git fetch + pull --ff-only` → install dependency
baru (hanya jika `requirements.txt` berubah) → `alembic upgrade head` →
`systemctl restart ai-youtube-manager`. Aman dijalankan ulang (idempotent,
pakai `flock` supaya tidak tabrakan).

- **Otomatis**: timer systemd `ai-youtube-manager-update.timer` tiap hari 03:00
  (dipasang installer).
- **Manual**: `sudo /opt/ai-youtube-manager/scripts/update.sh`
- **Log**: `/var/log/ai-youtube-manager-update.log`
- **Cek timer**: `systemctl list-timers | grep ai-youtube-manager`

Catatan: frontend di-serve dari `frontend/dist` yang sudah ter-bundle di repo,
jadi server TIDAK perlu Node.js/npm - update cukup `git pull` + restart.

## Perintah berguna

```bash
systemctl status ai-youtube-manager        # status service
journalctl -u ai-youtube-manager -f        # log realtime
systemctl list-timers | grep ai-youtube-manager   # jadwal auto-update
systemctl restart ai-youtube-manager       # restart manual
```

## Install manual (alternatif tanpa script)

```bash
sudo apt-get update && sudo apt-get install -y python3-venv python3-pip git curl sqlite3 build-essential libffi-dev libssl-dev
sudo useradd --system --home /opt/ai-youtube-manager --shell /usr/sbin/nologin aym || true
sudo git clone https://github.com/orlin24/YoutubeManager.git /opt/ai-youtube-manager
cd /opt/ai-youtube-manager/backend
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo cp .env.example .env   # lalu edit: DATABASE_URL, SECRET_KEY
sudo .venv/bin/alembic upgrade head
# salin systemd/ai-youtube-manager.service, sesuaikan path, lalu:
sudo systemctl daemon-reload && sudo systemctl enable --now ai-youtube-manager
```

## Reverse proxy (opsional, VPS berdomain)

Salin `nginx/ai-youtube-manager.conf` ke `/etc/nginx/sites-available/`, sesuaikan
`server_name`, lalu `nginx -t && systemctl reload nginx`. Service tetap listen
di `0.0.0.0:5000`; untuk keamanan tambahan ubah menjadi `127.0.0.1:5000` di
unit systemd bila memakai nginx.
