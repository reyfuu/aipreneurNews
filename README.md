# Daily News Clip Automation

Sistem otomatis membuat 1 video berita internasional per hari (30–60 detik) dalam Bahasa Indonesia.

## Fitur

- Scrape 5 RSS media internasional (BBC, Reuters, CNN, The Guardian, Al Jazeera)
- Seleksi berita 6–12 jam terakhir
- Rewrite script via Claude (Bahasa Indonesia)
- Generate voiceover dengan Edge-TTS (`id-ID-GadisNeural`)
- Download stock video gratis dari Pexels
- Render video dengan template + text overlay (MoviePy)
- Caption overlay langsung ke video (untuk subtitle)
- Caption khusus IG tersimpan otomatis per hari
- Generate thumbnail otomatis
- Upload ke YouTube dengan metadata siap pakai
- Scheduler lokal (`schedule`) atau GitHub Actions

## Struktur Proyek

```text
news-clip-bot/
├── .env.example
├── requirements.txt
├── README.md
├── config/
│   ├── feeds.json
│   ├── prompts.txt
│   └── settings.json
├── templates/
│   ├── base_template.mp4      # Buat manual 1x
│   ├── thumb_template.png     # Buat manual 1x
│   └── fonts/                # Font kustom
├── assets/
│   └── background_music/      # Isi MP3 bebas copyright
├── output/
│   └── YYYY-MM-DD/
├── src/
│   ├── ...
└── .github/workflows/daily.yml
```

## Setup

1. Instal dependensi sistem:
   - `ffmpeg` (wajib)
2. Buat virtualenv dan install package:
   - `pip install -r requirements.txt`
3. Copy `.env.example` ke `.env` lalu isi API key:
   - `ANTHROPIC_API_KEY`
   - `PEXELS_API_KEY`
   - `YT_CLIENT_SECRETS` (opsional untuk upload)
4. Siapkan template video:
   - `templates/base_template.mp4` (1920x1080, 60 detik)
   - `templates/thumb_template.png` (1280x720)
5. Siapkan musik:
   - simpan `.mp3` ke `assets/background_music/`

## Menjalankan (lokal)

- Jalankan sekali:
  - `python -m src.main --run-once`
- Jalankan scheduler lokal:
  - `python -m src.main --daemon`
- Skip upload saat testing:
  - `python -m src.main --run-once --skip-upload`

## Menjalankan tampilan web (Django + Vite)

- Backend API (Django):
  - `python manage.py migrate` (sekali pertama)
  - `python manage.py runserver 8000` (atau `8001/8002` jika port lain dipakai)
- Frontend (Vite):
  - `cd frontend`
  - `npm install`
  - `npm run dev`
- Buka:
  - `http://localhost:5173`
- Jika backend Anda jalan di port selain `8000`, set environment variable saat jalankan Vite:
  - `DJANGO_HOST=127.0.0.1 DJANGO_PORT=8002 npm run dev`
- Endpoint API yang dipakai UI:
  - `POST /api/run/` → mulai pipeline (body opsional: `skip_upload`, `run_date`)
  - `GET /api/task/<task_id>/` → status task
  - `GET /api/outputs/` → daftar output terbaru
  - `GET /api/outputs/<tanggal>/<filename>` → unduh file output (opsional)

## Output

Setiap hari akan menghasilkan folder:
- `output/YYYY-MM-DD/script.json`
- `output/YYYY-MM-DD/ig_caption.txt`
- `output/YYYY-MM-DD/voiceover.mp3`
- `output/YYYY-MM-DD/final_video.mp4`
- `output/YYYY-MM-DD/thumbnail.png`
- log history: `output/history.jsonl`

## Catatan

- Pastikan tidak copy-paste teks asli dari sumber. Claude sudah diberi instruksi rewrite.
- Gunakan footage dari sumber yang legal (Pexels/Pixabay) sesuai brief.
- Music sebaiknya ambil dari YouTube Audio Library atau lisensi gratis.
