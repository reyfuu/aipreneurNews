import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from src import thumbnail


def _make_video(path: Path, *, dark_first: bool = True) -> None:
    """Klip 2 detik: 1 detik gelap lalu 1 detik berpola, untuk menguji pemilihan frame."""
    from moviepy import ImageSequenceClip

    dark = np.zeros((160, 90, 3), dtype=np.uint8)
    bright = np.random.RandomState(0).randint(60, 200, (160, 90, 3), dtype=np.uint8)
    frames = ([dark] * 10 + [bright] * 10) if dark_first else ([bright] * 20)
    ImageSequenceClip([f for f in frames], fps=10).write_videofile(
        str(path), codec="libx264", audio=False, logger=None
    )


class FrameScoreTest(unittest.TestCase):
    def test_flat_black_scores_lowest(self):
        black = np.zeros((20, 20, 3), dtype=np.uint8)
        detailed = np.random.RandomState(1).randint(60, 200, (20, 20, 3), dtype=np.uint8)
        self.assertLess(thumbnail._frame_score(black), thumbnail._frame_score(detailed))

    def test_flat_white_also_scores_low(self):
        white = np.full((20, 20, 3), 255, dtype=np.uint8)
        detailed = np.random.RandomState(2).randint(60, 200, (20, 20, 3), dtype=np.uint8)
        self.assertLess(thumbnail._frame_score(white), thumbnail._frame_score(detailed))


class RenderThumbnailTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="thumb-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_uses_video_frame_and_skips_black_intro(self):
        video = self.tmpdir / "clip.mp4"
        _make_video(video)
        out = thumbnail.render_thumbnail(
            text="Judul Uji",
            template_path=None,
            out_path=self.tmpdir / "thumb.png",
            video_path=video,
        )
        image = Image.open(out)
        self.assertEqual(image.size, thumbnail.THUMB_SIZE)
        # Frame gelap di awal harus dilewati, jadi hasilnya tidak seluruhnya hitam.
        self.assertGreater(np.asarray(image.convert("L")).mean(), 12)

    def test_falls_back_to_solid_when_video_missing(self):
        out = thumbnail.render_thumbnail(
            text="Tanpa Video",
            template_path=None,
            out_path=self.tmpdir / "thumb.png",
            video_path=self.tmpdir / "tidak-ada.mp4",
        )
        self.assertEqual(Image.open(out).size, thumbnail.THUMB_SIZE)

    def test_template_used_when_no_video(self):
        template = self.tmpdir / "tpl.png"
        Image.new("RGB", (1280, 720), (10, 120, 60)).save(template)
        out = thumbnail.render_thumbnail(
            text="Pakai Template",
            template_path=template,
            out_path=self.tmpdir / "thumb.png",
            video_path=None,
        )
        pixels = np.asarray(Image.open(out).convert("RGB"))
        # Warna template hijau harus masih dominan di sisi kanan (tanpa scrim).
        right_edge = pixels[:, -50:, :]
        self.assertGreater(right_edge[:, :, 1].mean(), right_edge[:, :, 0].mean())

    def test_long_text_is_wrapped_not_overflowing(self):
        out = thumbnail.render_thumbnail(
            text="Judul yang sangat panjang sekali untuk menguji pembungkusan teks otomatis "
            "supaya tidak melimpah keluar dari kanvas thumbnail",
            template_path=None,
            out_path=self.tmpdir / "thumb.png",
            video_path=None,
        )
        self.assertEqual(Image.open(out).size, thumbnail.THUMB_SIZE)

    def test_empty_text_gets_default(self):
        out = thumbnail.render_thumbnail(
            text="", template_path=None, out_path=self.tmpdir / "thumb.png", video_path=None
        )
        self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
