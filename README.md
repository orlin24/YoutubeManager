# AI YouTube Manager

AI YouTube Manager adalah **AI employee** untuk channel YouTube kamu: menganalisis
performa channel secara mendalam, membuat content plan 30 hari, menulis judul dan
deskripsi yang dioptimasi SEO, merekomendasikan waktu tayang terbaik, mengelola
komentar dan playlist - dan selalu meminta **persetujuan manusia** untuk semua
tindakan berisiko tinggi (publish, delete, upload).

Target akses: `http://IP-VPS:5000`

---

## 1. Requirements

- Ubuntu 22.04 LTS (VPS) atau macOS/Windows untuk development
- Python 3.11+ (backend menggunakan FastAPI + SQLAlchemy)
- Node.js 18+ (frontend React + TypeScript + Vite)
- PostgreSQL 14+
- (Opsional) Kunci API AI yang kompatibel dengan OpenAI (OpenAI, Groq, Together, Ollama, dll)
- (Diperlukan untuk YouTube) Google Cloud project dengan YouTube Data API v3 dan YouTube Analytics API

## 2. Installation Ubuntu 22.04

Cara tercepat (sebagai root/sudo):

```bash
cd /opt
git clone <repo-url> ai-youtube-manager
cd ai-youtube-manager
sudo bash scripts/install.sh
```

Script menginstall semua dependensi, membuat database, menjalankan migrasi,
membangun frontend, dan memasang systemd service. Instalasi manual langkah demi
langkah ada di `docs/DEPLOYMENT.md`.

Untuk development lokal:

```bash
# Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # isi sesuai kebutuhan
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 5000

# Frontend (terminal lain)
cd frontend
npm install
npm run dev   # http://localhost:5173 (proxy /api -> :5000)
```

## 3. PostgreSQL setup

```bash
sudo apt install postgresql postgresql-contrib
sudo -u postgres psql
```

```sql
CREATE ROLE aym LOGIN PASSWORD 'ganti-dengan-password-kuat';
CREATE DATABASE ai_youtube_manager OWNER aym;
```

Lalu set di `backend/.env`:

```
DATABASE_URL=postgresql+psycopg://aym:ganti-dengan-password-kuat@localhost:5432/ai_youtube_manager
```

## 4. Environment variables

Salin `backend/.env.example` ke `backend/.env` dan isi:

| Variable | Keterangan |
| --- | --- |
| `DATABASE_URL` | Koneksi PostgreSQL (lihat bagian 3) |
| `SECRET_KEY` | Rahasia untuk JWT; generate dengan `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Kredensial OAuth Google (bagian 5-7) |
| `GOOGLE_REDIRECT_URI` | `http://IP-VPS:5000/api/auth/google/callback` |
| `AI_API_KEY` / `AI_MODEL` / `AI_BASE_URL` | Kunci API AI (bagian 8) |
| `FRONTEND_URL` | Tujuan redirect setelah OAuth, misal `http://IP-VPS:5000` |
| `APP_ENV` | `development` atau `production` (production mengaktifkan cookie Secure) |

Jangan pernah commit file `.env`. Tidak ada secret yang di-hardcode.

## 5. Google Cloud project setup

1. Buka https://console.cloud.google.com dan buat project baru (misal `ai-youtube-manager`).
2. Pastikan billing aktif (opsional tapi disarankan untuk kuota yang lebih tinggi).
3. Detail langkah demi langkah: **`docs/GOOGLE_CLOUD_SETUP.md`**.

## 6. YouTube API activation

1. Di Google Cloud Console, buka **APIs & Services > Library**.
2. Aktifkan:
   - **YouTube Data API v3**
   - **YouTube Analytics API**
3. Cek kuota di **APIs & Services > Quotas** (Data API default 10.000 unit/hari).

## 7. OAuth configuration

1. **APIs & Services > OAuth consent screen**:
   - User Type: *External*
   - Tambahkan email kamu sebagai *test user*
   - (Untuk produksi: submit untuk verifikasi, atau tetap pakai test user)
2. **APIs & Services > Credentials > Create Credentials > OAuth client ID**:
   - Application type: *Web application*
   - Authorized redirect URIs: **`http://IP-VPS:5000/api/auth/google/callback`**
3. Salin **Client ID** dan **Client Secret** ke `backend/.env`.

Catatan: Google mengizinkan `http://localhost` untuk development. Untuk produksi
publik, sangat disarankan HTTPS + domain (lihat bagian 13); Google membatasi
redirect URI `http://` non-localhost.

## 8. AI API configuration

AI Manager memakai API yang kompatibel dengan OpenAI (`/v1/chat/completions`):

```bash
# backend/.env
AI_API_KEY=sk-...            # kunci API kamu
AI_MODEL=gpt-4o-mini         # model yang dipakai
AI_BASE_URL=https://api.openai.com/v1
```

Bisa juga memakai Groq, Together, atau model lokal via Ollama:

```bash
AI_BASE_URL=http://localhost:11434/v1
AI_MODEL=llama3.1
```

Tanpa `AI_API_KEY`, aplikasi tetap berjalan dengan analisis heuristik
(AI Performance Score berbasis CTR, watch time, dll) dan menampilkan status
`AI: not configured` di health check.

## 9. Database migration

```bash
cd backend
.venv/bin/alembic upgrade head      # jalankan migrasi
.venv/bin/alembic downgrade base    # rollback
.venv/bin/alembic revision --autogenerate -m "deskripsi"   # buat migrasi baru
```

## 10. Start development server

```bash
# Terminal 1 - backend (port 5000)
cd backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 5000

# Terminal 2 - frontend (port 5173, proxy ke /api)
cd frontend
npm run dev
```

Buka `http://localhost:5173`. Backend juga menyajikan frontend hasil build di
`http://localhost:5000` jika `frontend/dist` ada (`cd frontend && npm run build`).

## 11. Production deployment

```bash
cd backend
.venv/bin/gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 3 -b 127.0.0.1:5000 --timeout 120
```

Atau pakai systemd (sudah disiapkan di `scripts/install.sh`):

```bash
sudo cp systemd/ai-youtube-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ai-youtube-manager
journalctl -u ai-youtube-manager -f
```

## 12. Nginx

Konfigurasi siap pakai: `nginx/ai-youtube-manager.conf`. Instalasi:

```bash
sudo cp nginx/ai-youtube-manager.conf /etc/nginx/sites-available/aym.conf
sudo ln -s /etc/nginx/sites-available/aym.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Ubah `server_name` sesuai domain kamu. Backend tetap berjalan di
`127.0.0.1:5000` dan di-proxy oleh Nginx.

## 13. SSL

Dengan domain + HTTPS (disarankan untuk produksi):

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d youtube-manager.example.com
```

Lalu ubah `GOOGLE_REDIRECT_URI` dan `FRONTEND_URL` di `backend/.env` ke
`https://youtube-manager.example.com/...` dan daftarkan redirect URI baru di
Google Cloud Console. Restart service.

## 14. Firewall

```bash
# Development saja - buka port 5000
sudo ufw allow 5000/tcp

# Produksi - hanya SSH, HTTP, HTTPS
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## 15. Troubleshooting

| Gejala | Penyebab / Solusi |
| --- | --- |
| `Google OAuth is not configured` | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` kosong di `backend/.env` |
| `redirect_uri_mismatch` | Redirect URI di Google Console tidak sama persis dengan `GOOGLE_REDIRECT_URI` |
| `YouTube authorization has expired` | Token kadaluarsa/revoked; buka **Channels > Connect YouTube** ulang |
| `quota exceeded` (YouTube API) | Kuota harian Google habis; tunggu reset atau minta tambahan kuota |
| AI mengembalikan `AI_NOT_CONFIGURED` | `AI_API_KEY` kosong; isi di `backend/.env` dan restart |
| Dashboard kosong | Jalankan **Sync** di halaman Channels; tunggu scheduler (tiap 1 jam) |
| `database: error` di health check | Periksa `DATABASE_URL` dan apakah PostgreSQL berjalan |
| Port 5000 tidak terbuka | `sudo ufw allow 5000/tcp` (dev) atau gunakan Nginx (produksi) |

## 16. Backup

```bash
bash scripts/backup.sh
```

Membuat dump PostgreSQL di `backups/` (retensi 14 hari). Untuk offsite,
sinkronkan folder `backups/` dengan `rclone` ke S3/Google Drive/Wasabi.

Restore:

```bash
pg_restore -d postgresql+psycopg://aym:pass@localhost:5432/ai_youtube_manager --clean backups/ai_youtube_manager_<timestamp>.dump
```

## 17. Security

- Semua token (OAuth YouTube) dienkripsi dengan Fernet sebelum disimpan di DB
  (`TOKEN_ENCRYPTION_KEY`, default derivasi dari `SECRET_KEY`).
- Password di-hash dengan bcrypt. JWT memakai HS256 + `SECRET_KEY`.
- Cookie httpOnly + SameSite=Lax (+ Secure saat `APP_ENV=production`), plus
  verifikasi Origin untuk mutasi (CSRF defense-in-depth).
- Rate limiting pada endpoint auth dan AI.
- Audit log mencatat semua tindakan penting (login, connect, upload, publish,
  delete, approval, settings).
- High-risk actions (publish, delete, upload publik) **selalu** lewat approval
  manusia - AI tidak pernah mengeksekusinya langsung.
- Tidak ada secret yang di-hardcode; semua dari environment.
- HTTPS + domain direkomendasikan untuk produksi (bagian 13).

## 18. How to connect YouTube channel

1. Buka `http://IP-VPS:5000` dan **register/login**.
2. Klik **Connect YouTube** (atau buka `/api/auth/google`).
3. Pilih akun Google yang memiliki channel, setujui permission yang diminta.
4. Browser diarahkan kembali; channel muncul di halaman **Channels**.
5. Klik **Sync** untuk menarik statistik channel + video terbaru.
6. Buka **Dashboard** untuk melihat ringkasan, **AI Assistant** untuk analisis,
   dan **Approvals** untuk menyetujui/menolak tindakan berisiko.
7. Isi profil AI di **Channels > AI memory** (niche, audiens, gaya konten) agar
   rekomendasi AI semakin relevan.

---

## Fitur

- **Dashboard**: ringkasan channel, pertumbuhan, top & underperforming videos,
  rekomendasi AI, approval pending, audit terbaru, status sistem.
- **AI Employee** (10 agen): channel analyst, SEO specialist, content strategist,
  title/description specialist, analytics analyst, publishing manager, comment
  assistant, decision engine.
- **AI Performance Score** 0-100 (heuristik berbobot: CTR, retention, velocity,
  konversi subscriber, watch time, engagement) - bukan metrik resmi YouTube.
- **Approval system**: semua tindakan berisiko tinggi butuh persetujuan manusia.
- **Audit log** lengkap.
- **Content plan** 7 status (IDEA -> PUBLISHED) dengan generator AI.
- **Google OAuth** untuk menghubungkan channel YouTube (token dienkripsi).
- Deployment siap: systemd, Nginx, Docker Compose, script backup.
