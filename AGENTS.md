# AGENTS.md

## Tujuan Proyek
- Membangun otomatisasi harian pembuatan video berita (30–60 detik) dalam Bahasa Indonesia.
- Memindahkan alur: scrape berita → pilih + rewrite by Claude → voiceover → footage → render → thumbnail → upload.
- Menyediakan tampilan kontrol berbasis web untuk trigger dan monitoring pipeline.

## Cakupan yang Ingin Dicapai
- Scraper RSS: BBC, Reuters, CNN, The Guardian, Al Jazeera (6–12 jam terakhir).
- AI Writer: hasil JSON wajib lengkap (`selected_index`, `title`, `script_voiceover`, `hook`, `keywords`, `thumbnail_text`, `description`, `tags`).
- TTS: Edge-TTS `id-ID-GadisNeural`.
- Footage: download otomatis dari Pexels (landscape).
- Rendering: MoviePy + template base 1080p + overlay teks.
- Thumbnail: generator otomatis dari template PNG + teks.
- Upload: YouTube API dengan metadata siap pakai.

## Peran Agen (untuk kolaborasi)
1. `scraper` → validasi feed, waktu publikasi, dan filter window.
2. `ai_writer` → prompt + validasi output JSON.
3. `tts` → konversi script jadi audio.
4. `footage` → ambil footage legal dari Pexels.
5. `renderer` → komposisi video (visual + audio + teks).
6. `thumbnail` → render preview/judul untuk CTR.
7. `uploader` → upload otomatis + thumbnail + logging.
8. `main` → orkestrasi step + fallback + history.
9. `dashboard` → Django API + Vite frontend untuk menjalankan pipeline dari browser dan melihat output.

## Konvensi Kerja
- Bahasa utama komentar/commit/note: Indonesia/English campuran sesuai konteks.
- Script utama dikelola via modul terpisah sesuai domain fungsional.
- Semua file output disimpan ke `output/YYYY-MM-DD/`.
- Selalu simpan JSON source dan log ke `output/history.jsonl`.
- Tidak copy-paste isi artikel; wajib rewrite 100%.
- Pastikan legal: pakai sumber stock footage yang legal (Pexels/Pixabay), kredit sumber berita di deskripsi.
- Hindari menjalankan tes/validasi otomatis tanpa permintaan eksplisit jika tidak perlu (selaras instruksi kerja).

## Aturan Teknis
- Python 3.10+.
- FFmpeg harus terpasang untuk rendering.
- Semua path relatif dari root proyek.
- API key tidak ditulis ke git; gunakan `.env`.

## Jadwal Operasi
- Mode lokal: `python -m src.main --run-once --skip-upload`.
- Mode produksi lokal: `--daemon`.
- Mode cloud: workflow `.github/workflows/daily.yml` (cron 23:00 UTC / 06:00 WIB).

## File Wajib Hadir
- `config/feeds.json`
- `config/prompts.txt`
- `config/settings.json`
- `templates/base_template.mp4`
- `templates/thumb_template.png`
- `assets/background_music/*.mp3` (opsional tapi disarankan)

## Keputusan Rutin
- Jika pipeline gagal di salah satu modul, lanjutkan fallback:
  - AI Writer gagal → gunakan skrip fallback berbasis berita teratas.
  - Pexels/fetch tidak ada → render tetap jalan dengan visual fallback template.
  - Upload gagal → history tetap tercatat; pipeline tidak menghentikan file output.
