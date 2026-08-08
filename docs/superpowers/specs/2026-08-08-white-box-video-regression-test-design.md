# White-box Video Regression Test

## Goal

Mencegah hasil render video menampilkan kotak putih polos pada area footage.

## Design

Tes utama membangun satu frame komposit memakai template produksi dan footage hijau sintetis. Tes membaca piksel pada batas area footage yang sama dengan renderer, lalu memastikan:

- titik tengah area bukan putih;
- warna hijau footage terlihat dominan;
- kurang dari 50% area footage berupa piksel mendekati putih;
- saat footage tidak tersedia, fallback tetap gelap dan bukan putih.

Tes menggunakan `unittest`, MoviePy, NumPy, dan FFmpeg yang sudah menjadi dependensi proyek. Tidak ada jaringan atau dependensi baru.

## End-to-end Check

Tes lambat opsional memanggil `render_video()`, membaca MP4 hasil encode, dan memeriksa frame pada detik kelima. Tes ini hanya berjalan jika `RUN_SLOW_RENDER=1`, sehingga pengujian biasa tetap cepat.

## Test Location and Inputs

- File tes: `tests/test_render_not_white.py`.
- Template: `new template.mp4`, mengikuti template yang sedang digunakan renderer dan tes renderer lain.
- Footage sintetis serta output sementara dibuat di direktori temporer dan dibersihkan setelah tes.
- Tes dilewati dengan pesan yang jelas jika template tidak tersedia.

## Success Criteria

- Tes gagal apabila mask template kembali menutup area footage dengan warna putih.
- Tes gagal apabila footage tidak masuk ke komposisi.
- Tes gagal apabila fallback tanpa footage menghasilkan kotak putih.
- Tes cepat berjalan tanpa API key dan tanpa akses jaringan.
