# Viral AI Footage Minimum Views Design

## Goal

Hanya gunakan footage YouTube bertema AI yang memiliki sedikitnya 100.000 views, sambil tetap memastikan pipeline selalu dapat menghasilkan video.

## Selection Flow

1. Cari kandidat YouTube yang paling relevan dengan judul dan keyword berita.
2. Tambahkan query fallback bertema AI: `viral AI`, `artificial intelligence`, dan `AI technology`.
3. Ambil `view_count` dari metadata hasil pencarian yt-dlp.
4. Tolak kandidat bila `view_count` tidak tersedia atau kurang dari 100.000.
5. Urutkan kandidat yang lolos berdasarkan relevansi judul terlebih dahulu, lalu jumlah views tertinggi.
6. Download kandidat secara berurutan dan pertahankan validasi audio yang sudah ada: bagian yang dirender harus memiliki `max_volume > -50 dB`.
7. Jika YouTube tidak menghasilkan kandidat yang dapat diunduh—termasuk karena anti-bot—gunakan fallback Pexels dan musik CC0 agar output tetap dibuat.

## Minimal Interface Changes

- `_search_youtube()` menyertakan `view_count` pada setiap kandidat.
- `search_and_download_news_video()` menerima `min_views=100_000` dan melakukan filter sebelum download.
- Tidak ada API key, dependency, database, atau dashboard setting baru.
- Log kandidat menyertakan jumlah views agar keputusan dapat diaudit.

## Error Handling

- Metadata `view_count` kosong atau tidak valid dianggap tidak memenuhi syarat.
- Kegagalan yt-dlp tetap mengikuti fallback yang sudah ada.
- Kandidat viral yang tidak memiliki audio terdengar tetap ditolak.

## Tests

- Kandidat dengan 99.999 views ditolak.
- Kandidat dengan tepat 100.000 views diterima.
- Kandidat tanpa `view_count` ditolak.
- Di antara kandidat dengan relevansi sama, views tertinggi diprioritaskan.
- Query fallback AI ikut digunakan.
- Fallback Pexels tetap berjalan ketika tidak ada kandidat YouTube yang lolos.

## Out of Scope

- YouTube Data API.
- Pengaturan minimum views dari dashboard.
- Jaminan bahwa footage viral membahas berita yang sama; query berita tetap diprioritaskan, sedangkan fallback cukup bertema AI.
