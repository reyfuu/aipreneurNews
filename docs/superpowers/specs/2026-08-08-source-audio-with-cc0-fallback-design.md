# Source Audio with CC0 Music Fallback

## Goal

Gunakan suara asli video berita berbahasa Inggris ketika benar-benar terdengar,
sementara judul, thumbnail, dan overlay tetap berbahasa Indonesia. Jika tidak ada
kandidat video dengan audio yang layak, gunakan musik CC0 dan jangan membuat
voiceover AI.

## Audio Selection

1. Cari kandidat YouTube menggunakan ranking relevansi yang sudah ada.
2. Download kandidat satu per satu.
3. Periksa audio hasil download dengan FFmpeg `volumedetect`.
4. Terima kandidat jika memiliki audio dan `max_volume` lebih tinggi dari `-50 dB`.
5. Hapus kandidat yang gagal atau diam, lalu lanjut ke kandidat berikutnya.
6. Jika tidak ada kandidat YouTube yang lolos, gunakan visual fallback Pexels.
7. Renderer memakai audio kandidat yang lolos; jika tidak ada, renderer memakai
   musik CC0 lokal dari `assets/background_music/`.

Ambang `-50 dB` membedakan audio praktis diam seperti output saat ini (`-91 dB`)
dari percakapan atau musik yang masih dapat dinormalisasi oleh pemutar.

## Music Asset and License

Fallback awal menggunakan `Chill Beat.ogg` dari Wikimedia Commons. File tersebut
dirilis dengan CC0 1.0, sehingga dapat disalin, dimodifikasi, dan digunakan secara
komersial tanpa atribusi wajib. Repo tetap menyimpan catatan sumber dan lisensi
agar asal aset dapat diaudit.

Musik diunduh sekali saat implementasi dan disimpan lokal. Pipeline produksi tidak
bergantung pada ketersediaan Wikimedia pada setiap run.

## Pipeline and Rendering

- Tambahkan mode audio `source_or_music` sebagai konfigurasi produksi.
- Mode ini tidak memanggil Edge TTS dan membuat `voiceover.mp3` kosong demi
  kompatibilitas output yang sudah ada.
- Downloader mengembalikan footage yang sudah tervalidasi audionya jika tersedia.
- Renderer memakai audio footage pertama hanya dalam mode `source_or_music` dan
  hanya jika audio tersebut lolos validasi.
- Jika footage tidak memiliki audio layak, renderer mengulang musik fallback
  hingga durasi video selesai dengan volume latar yang aman.
- `script.title`, thumbnail, metadata, dan seluruh overlay tetap berasal dari
  writer Bahasa Indonesia; bahasa audio tidak mengubah judul.

## Failure Handling

- FFmpeg/FFprobe tidak tersedia atau pemeriksaan gagal: kandidat dianggap tidak
  layak dan pencarian dilanjutkan.
- Download YouTube gagal: lanjut ke kandidat berikutnya.
- Semua kandidat gagal: visual Pexels dan musik CC0 lokal.
- Musik lokal hilang: render tetap selesai tanpa audio dan menulis warning yang
  jelas; pipeline tidak crash.

## Verification

- Unit test menerima kandidat dengan audio terdengar.
- Unit test menolak kandidat tanpa stream audio dan audio diam `-91 dB`.
- Renderer test memastikan mode `source_or_music` memilih audio footage terdengar.
- Renderer test memastikan musik dipakai saat footage diam/tanpa audio.
- Pipeline test memastikan Edge TTS tidak dipanggil dan judul Indonesia tidak
  berubah.
- Seluruh test suite dijalankan lokal dan di VPS.
- Pipeline produksi dijalankan langsung, hasil diperiksa dengan FFprobe dan
  `volumedetect`, lalu diputar di browser dengan `muted=false` dan tanpa error.

## Out of Scope

- Transkripsi atau terjemahan audio Inggris.
- Mencampur suara asli dengan voiceover AI.
- Mengunduh musik baru pada setiap pipeline run.
- Sistem katalog musik atau pemilihan genre otomatis.
