# Google Cloud Setup untuk AI YouTube Manager

Panduan ini menyiapkan kredensial Google OAuth agar aplikasi bisa membaca
analytics channel kamu dan mengelola video. Semua langkah dilakukan di
https://console.cloud.google.com.

## 1. Buat project

1. Buka https://console.cloud.google.com
2. Klik dropdown project (kiri atas) > **New Project**
3. Nama: misal `ai-youtube-manager`, klik **Create**
4. Pastikan project baru terpilih di dropdown.

## 2. Aktifkan YouTube API

1. Menu > **APIs & Services > Library**
2. Cari **YouTube Data API v3** > klik > **Enable**
3. Cari **YouTube Analytics API** > klik > **Enable**

## 3. Konfigurasi OAuth consent screen

1. Menu > **APIs & Services > OAuth consent screen**
2. **User Type**: pilih **External** > Create
3. Isi **App name** (misal `AI YouTube Manager`), **User support email**,
   **Developer contact email** > Save and Continue
4. **Scopes**: klik **Add or remove scopes** lalu tambahkan (opsional, bisa
   juga lewat pilihan default):
   - `https://www.googleapis.com/auth/youtube.readonly`
   - `https://www.googleapis.com/auth/youtube.upload`
   - `https://www.googleapis.com/auth/youtube`
   - `https://www.googleapis.com/auth/yt-analytics.readonly`
   - `https://www.googleapis.com/auth/yt-analytics-monetary.readonly`
   - `openid`, `email`, `profile`
   > Save and Continue
5. **Test users**: tambahkan email Google kamu (yang memiliki channel YouTube).
   > Save and Continue
6. Ringkasan > **Back to dashboard**.

> Catatan penting:
> - Mode **Testing** hanya mengizinkan akun test user (maks 100 akun) dan
>   token refresh akan kadaluarsa setelah 7 hari. Untuk produksi, klik
>   **Publish app** dan jika perlu ajukan verifikasi (Google akan meninjau).
> - Karena memakai scope sensitif, aplikasi yang dipublish ke **Production**
>   memerlukan verifikasi Google sebelum pengguna lain bisa menggunakannya.

## 4. Buat OAuth Client ID

1. Menu > **APIs & Services > Credentials**
2. Klik **+ Create Credentials** > **OAuth client ID**
3. Application type: **Web application**
4. Nama: misal `AYM Web Client`
5. **Authorized redirect URIs** -> **+ Add URI**:
   - Development: `http://localhost:5000/api/auth/google/callback`
   - VPS (dev, HTTP): `http://IP-VPS:5000/api/auth/google/callback`
   - Produksi (HTTPS): `https://youtube-manager.example.com/api/auth/google/callback`
   > Simpan. Daftar redirect URI harus PERSIS sama dengan `GOOGLE_REDIRECT_URI`
   > di `backend/.env` (termasuk port dan path `/api/auth/google/callback`).

> Catatan: Google menolak redirect URI `http://` untuk host non-localhost dalam
> beberapa kondisi. Untuk produksi publik gunakan HTTPS + domain (lihat bagian 5).

## 5. Catatan produksi (HTTP vs HTTPS)

- Google mengizinkan `http://localhost` untuk development.
- Untuk alamat IP publik dengan `http://`, pengalaman bisa gagal dengan
  `redirect_uri_mismatch` atau pembatasan browser (Secure cookies, mixed
  content). Solusi yang disarankan:
  1. Beli domain dan pasang SSL (certbot), atau
  2. Gunakan layanan tunnel (ngrok/cloudflared) untuk development jarak jauh.
- Setelah memakai HTTPS, perbarui di `backend/.env`:
  - `GOOGLE_REDIRECT_URI=https://domain.com/api/auth/google/callback`
  - `FRONTEND_URL=https://domain.com`
  - `APP_ENV=production`

## 6. Salin kredensial

1. Di halaman Credentials, klik client OAuth yang dibuat.
2. Salin **Client ID** dan **Client Secret**.
3. Isi ke `backend/.env`:

```
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxx
GOOGLE_REDIRECT_URI=http://IP-VPS:5000/api/auth/google/callback
FRONTEND_URL=http://IP-VPS:5000
```

4. Restart aplikasi: `systemctl restart ai-youtube-manager`

## 7. Verifikasi

1. Buka `http://IP-VPS:5000` > login > **Connect YouTube**.
2. Pilih akun test user, setujui permission.
3. Browser diarahkan kembali dengan `?connected=1`.
4. Di halaman Channels, channel muncul. Klik **Sync** untuk menarik data.
