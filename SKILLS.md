# SKILLS.md

## Skill: Scraping & Ingestion
- Mengumpulkan berita dari RSS.
- Validasi timestamp dan filter window 6–12 jam.
- Normalisasi data ke format:
  - `title`, `summary`, `link`, `source`, `pub_date`.
- Menyimpan kandidat untuk pipeline AI.

## Skill: Prompting & Script Generation
- Menyiapkan prompt standar untuk Claude di `config/prompts.txt`.
- Mengirim 5 berita teratas untuk dipilih.
- Menerima JSON output dan memvalidasi field wajib.
- Konversi output ke format internal (`script_voiceover`).

## Skill: TTS (Text-to-Speech)
- Mengubah script voiceover ke file MP3.
- Menjaga kualitas suara netral dan pace yang sesuai narasi berita.

## Skill: Stock Footage Acquisition
- Query Pexels via keyword.
- Memilih klip landscape otomatis.
- Membatasi jumlah unduhan menjadi 3–5 klip.

## Skill: Video Rendering
- Komposisi:
  - Template base (1080p, 60 detik).
  - Stock footage per segmen.
  - Overlay teks (hook, lower third, outro).
  - Audio voice + background music (volume rendah).
- Menghasilkan `output/YYYY-MM-DD/final_video.mp4`.

## Skill: Thumbnail Production
- Memuat template 1280x720.
- Menambahkan teks CTA/thumbnail berukuran besar, tegas.
- Menyimpan `output/YYYY-MM-DD/thumbnail.png`.

## Skill: Publishing Automation
- Upload YouTube via API v3.
- Metadata:
  - title
  - description (2 paragraf + sumber)
  - tags (maksimal 10)
  - categoryId `25`
  - privacy `public`
- Upload thumbnail otomatis.

## Skill: Orkestrasi & Operasional
- Mengatur urutan step dengan toleransi error.
- Menulis histori run ke `output/history.jsonl`.
- Menyediakan mode sekali jalan (`--run-once`) dan mode daemon scheduler.

## Skill: Antarmuka Web (Django + Vite)
- Menyediakan endpoint API untuk run pipeline, tracking status, dan daftar output.
- Menyajikan dashboard frontend (Vite) untuk operator non-teknis.
- Memastikan integrasi backend-frontend melalui proxy API saat pengembangan.

## Skill: Dokumentasi & Operasi
- Menyusun `.env.example`, `README.md`, dan panduan setup.
- Menyediakan catatan legal/safety.
- Menyiapkan workflow GitHub Actions sebagai opsi cloud scheduler.
