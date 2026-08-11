# Deployment Manual (Ubuntu 22.04)

Panduan ini menjelaskan instalasi langkah demi langkah, setara dengan
`scripts/install.sh` tapi manual - berguna untuk debugging atau custom setup.

## 1. System packages

```bash
sudo apt update
sudo apt install -y curl gnupg ca-certificates openssl nginx postgresql postgresql-contrib software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt install -y nodejs
```

## 2. Clone + backend

```bash
cd /opt
sudo git clone <repo-url> ai-youtube-manager
sudo chown -R $USER:$USER ai-youtube-manager
cd ai-youtube-manager/backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# edit .env: SECRET_KEY, DATABASE_URL, GOOGLE_CLIENT_ID/SECRET, AI_API_KEY
```

## 3. Database

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE aym LOGIN PASSWORD 'STRONG_PASSWORD';
CREATE DATABASE ai_youtube_manager OWNER aym;
SQL
```

Di `backend/.env`:

```
DATABASE_URL=postgresql+psycopg://aym:STRONG_PASSWORD@localhost:5432/ai_youtube_manager
```

## 4. Migration

```bash
cd backend
.venv/bin/alembic upgrade head
```

## 5. Frontend build

```bash
cd frontend
npm ci
npm run build
```

Hasil build (`frontend/dist`) otomatis disajikan backend di `/`.

## 6. Systemd service

```bash
sudo cp systemd/ai-youtube-manager.service /etc/systemd/system/
sudo sed -i 's|__APP_DIR__|/opt/ai-youtube-manager|g' /etc/systemd/system/ai-youtube-manager.service
sudo systemctl daemon-reload
sudo systemctl enable --now ai-youtube-manager
systemctl status ai-youtube-manager
```

## 7. Nginx

```bash
sudo cp nginx/ai-youtube-manager.conf /etc/nginx/sites-available/aym.conf
sudo ln -s /etc/nginx/sites-available/aym.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
# edit server_name di /etc/nginx/sites-available/aym.conf
sudo nginx -t
sudo systemctl reload nginx
```

## 8. SSL (disarankan)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d youtube-manager.example.com
```

Perbarui `GOOGLE_REDIRECT_URI` / `FRONTEND_URL` di `.env` ke HTTPS, daftarkan
redirect URI baru di Google Console, lalu:

```bash
sudo systemctl restart ai-youtube-manager
```

## 9. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

(Untuk development saja: `sudo ufw allow 5000/tcp`.)

## 10. Rollback

```bash
# Rollback migrasi DB
cd backend && .venv/bin/alembic downgrade -1

# Kembalikan service ke versi sebelumnya
cd /opt && sudo mv ai-youtube-manager ai-youtube-manager.new
sudo git -C ai-youtube-manager checkout <commit-sebelumnya>
sudo systemctl restart ai-youtube-manager

# Restore database
bash scripts/backup.sh   # jalankan SEBELUM perubahan
pg_restore -d "$DATABASE_URL" --clean backups/ai_youtube_manager_<timestamp>.dump
```
