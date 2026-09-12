# Auto-publish ke Instagram Reels

Panduan menyalakan publish otomatis ke Instagram setelah akun dan kredensial siap.

## Syarat yang tidak bisa ditawar

Instagram Content Publishing API **tidak menerima upload file langsung**. Kita hanya
mengirim URL, lalu server Meta yang mengunduh videonya sendiri. Artinya:

- Video harus bisa diakses publik lewat **HTTPS** saat pipeline berjalan.
- `localhost` dan IP lokal tidak bisa dipakai.
- Server harus sudah hidup sebelum langkah publish dijalankan.

Proyek ini sudah menyediakan endpoint yang cocok: `GET /api/outputs/<tanggal>/<file>.mp4`.
Jadi kalau dashboard Django sudah online di `https://news.aipreneur.co.id`, tidak perlu
storage tambahan. Kalau belum, videonya perlu ditaruh di S3/Cloudinary/CDN dan
`PUBLIC_BASE_URL` diarahkan ke sana.

## 1. Siapkan akun

1. Ubah akun Instagram jadi **Professional** (Business atau Creator).
   Settings → Account type and tools → Switch to professional account.
2. Tautkan ke sebuah **Facebook Page**. Content Publishing API menolak akun personal
   dan akun yang tidak tertaut Page.

## 2. Buat Meta App

1. Buka <https://developers.facebook.com/apps> → Create App → tipe **Business**.
2. Tambahkan produk **Instagram** (Instagram Graph API).
3. Di App Roles, pastikan akun Facebook kamu terdaftar sebagai Admin/Developer.
   Selama masih Development mode, permission bisa diberikan tanpa App Review
   selama akunnya milik sendiri.
4. Minta permission berikut:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_read_engagement`

## 3. Ambil IG_USER_ID dan token

Pakai Graph API Explorer (<https://developers.facebook.com/tools/explorer>):

```text
GET /me/accounts                        → dapat <PAGE_ID>
GET /<PAGE_ID>?fields=instagram_business_account   → dapat IG_USER_ID
```

Token dari Explorer berumur ~1 jam. Tukar jadi long-lived (±60 hari):

```text
GET /oauth/access_token
  ?grant_type=fb_exchange_token
  &client_id=<APP_ID>
  &client_secret=<APP_SECRET>
  &fb_exchange_token=<SHORT_LIVED_TOKEN>
```

> Token long-lived tetap kedaluwarsa. Catat tanggalnya dan perbarui sebelum habis,
> atau publish akan gagal dengan error OAuth code 190.

## 4. Isi konfigurasi

`.env`:

```dotenv
PUBLIC_BASE_URL=https://news.aipreneur.co.id
IG_USER_ID=17841400000000000
IG_ACCESS_TOKEN=EAAG...
```

`config/settings.json`:

```json
"instagram": {
  "enabled": true,
  "share_to_feed": true,
  "api_version": "v25.0",
  "poll_interval_sec": 10,
  "max_wait_sec": 300,
  "public_base_url": ""
}
```

`PUBLIC_BASE_URL` di `.env` menang atas `public_base_url` di settings.

## 5. Uji sebelum menyalakan otomatis

Cek URL dan caption yang akan dikirim, tanpa publish apa pun:

```bash
python -m src.publisher_instagram --date 2026-09-12 --dry-run
```

Pastikan URL yang tercetak benar-benar bisa dibuka dari internet (bukan hanya dari
komputermu). Uji dari luar jaringan:

```bash
curl -I https://news.aipreneur.co.id/api/outputs/2026-09-12/namafile.mp4
```

Harus `200` dengan `Content-Type: video/mp4`. Kalau `404`, videonya belum tersaji publik.

Lalu publish sungguhan satu output yang sudah ada:

```bash
python -m src.publisher_instagram --date 2026-09-12
```

## 6. Nyalakan di pipeline harian

Setelah uji manual berhasil, `instagram.enabled: true` membuat pipeline otomatis
publish setiap kali selesai render. Urutannya: render → thumbnail → YouTube → Instagram.

```bash
python -m src.main --run-once                   # YouTube + Instagram
python -m src.main --run-once --skip-instagram  # YouTube saja
python -m src.main --run-once --skip-youtube    # Instagram saja
python -m src.main --run-once --skip-upload     # tidak keduanya
```

Di dashboard, dua checkbox **Skip YouTube** dan **Skip Instagram** melakukan hal
yang sama lewat `POST /api/run/`.

## Perilaku saat gagal

Kegagalan Instagram **tidak menjatuhkan pipeline** — video tetap tersimpan dan
statusnya dicatat di `output/history.jsonl`:

| Field | Isi |
| --- | --- |
| `instagram_status` | `published` / `failed` / `skipped` |
| `instagram_media_id` | ID media bila sukses |
| `instagram_permalink` | URL Reel bila sukses |
| `instagram_error` | pesan error bila gagal |

## Batasan yang perlu diingat

- **100 post per 24 jam** per akun lewat API. Satu video per hari jauh di bawah batas.
- Caption dipotong otomatis di 2.200 karakter dan maksimal 30 hashtag
  (lihat `trim_caption` di [`src/publisher_instagram.py`](../src/publisher_instagram.py)).
- Container kedaluwarsa bila tidak dipublikasikan dalam 24 jam.
- Meta menyarankan polling status container maksimal 5 menit; default `max_wait_sec`
  sudah 300 detik.
- Video 1080x1920 60 detik dari pipeline ini sudah sesuai format Reels.
