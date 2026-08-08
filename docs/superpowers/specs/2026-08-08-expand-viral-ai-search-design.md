# Expanded Viral AI Search Design

## Goal

Perluas pencarian footage YouTube agar mencakup semua jenis video bertema AI—bukan hanya berita—dengan tetap mewajibkan sedikitnya 100.000 views.

## Search Queries

Pencarian berita spesifik tetap dijalankan terlebih dahulu. Setelah itu, pencarian umum AI menggunakan daftar berikut:

1. `viral AI`
2. `AI tools`
3. `AI tutorial`
4. `AI podcast`
5. `AI robots`
6. `AI demo`
7. `generative AI`
8. `ChatGPT`
9. `Claude AI`
10. `open source AI`
11. `artificial intelligence`

## Selection Rules

- Semua kandidat YouTube wajib memiliki `view_count >= 100_000`.
- Metadata views yang kosong atau tidak valid tetap ditolak.
- Urutan ranking tetap: relevansi berita, prioritas query spesifik, views tertinggi, lalu durasi terpendek.
- Kandidat terpilih tetap wajib memiliki audio dengan `max_volume > -50 dB` pada jendela yang dirender.
- Query umum hanya bertema AI; video viral di luar topik AI tidak boleh digunakan.

## Failure Handling

- Jika pencarian atau download YouTube gagal, termasuk karena anti-bot, pipeline tetap menggunakan Pexels dan musik CC0.
- Tidak ada perubahan pada output, judul Bahasa Indonesia, renderer, atau mekanisme audio.

## YouTube API Decision

YouTube Data API tidak digunakan. yt-dlp tetap menangani pencarian, metadata `view_count`, dan download. API resmi dapat ditambahkan kemudian hanya jika reliabilitas pencarian metadata menjadi masalah; API tersebut tidak menggantikan proses download.

## Minimal Code Changes

- Ganti daftar query AI umum di `src/footage.py` dengan 11 query di atas.
- Tidak menambah API key, dependency, konfigurasi, database, atau dashboard setting.

## Tests

- Test memastikan seluruh 11 query umum dipanggil.
- Test memastikan query berita spesifik tetap memiliki prioritas di atas query umum ketika relevansinya sama.
- Regression test minimum 100.000 views, metadata invalid, audio, dan fallback yang sudah ada tetap lulus.

## Out of Scope

- YouTube Data API.
- Pengaturan query dari dashboard.
- Video viral non-AI.
- Pengurutan berdasarkan umur video atau kecepatan pertumbuhan views.
