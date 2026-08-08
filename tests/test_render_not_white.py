"""Guard against the "white/blank video" regression.

The white box (footage area, y=410..1087) must show the footage — not a plain
white or blank frame. On the VPS this broke when footage failed to download or
the template's white box was not cut out, leaving a solid white rectangle.

These tests reproduce the exact production compositing (Layer 0 fallback +
Layer 1 blurred footage box + Layer 2 masked template) with a synthetic
solid-green clip, then inspect real pixels — no network, one frame, fast.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path

import numpy as np

from moviepy import ColorClip, CompositeVideoClip, VideoFileClip

from src import renderer as R

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "new template.mp4"

# Same box the renderer uses (renderer.render_video WHITE_BOX).
WHITE_BOX = {"x": 0, "y": 410, "w": 1079, "h": 677}
TARGET_SIZE = (1080, 1920)
# A point safely inside the sharp (inset) footage area of the box.
SAMPLE_Y = WHITE_BOX["y"] + WHITE_BOX["h"] // 2
SAMPLE_X = WHITE_BOX["w"] // 2


def _make_green_clip(path: Path, seconds: float = 2.0) -> None:
    ColorClip((320, 240), color=(0, 255, 0)).with_duration(seconds).write_videofile(
        str(path), fps=12, codec="libx264", audio=False, logger=None,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )


def _compose(footage_paths, duration=2):
    """Rebuild Layer 0/1/2 exactly as render_video does for the white box."""
    overlay = [ColorClip(TARGET_SIZE, color=(10, 10, 10)).with_duration(duration)]
    paths = [Path(p) for p in footage_paths if Path(p).exists()]
    if paths:
        c = VideoFileClip(str(paths[0]))
        c_dur = min(duration, int(c.duration)) if c.duration else duration
        box = R._footage_box_blurred(c.with_duration(max(1, c_dur)), WHITE_BOX["w"], WHITE_BOX["h"])
        box = box.with_position((WHITE_BOX["x"], WHITE_BOX["y"]))
        overlay.append(box)
    template = R._load_base_video(TEMPLATE, duration, TARGET_SIZE)
    overlay.append(template.with_opacity(1.0))
    return CompositeVideoClip(overlay).with_duration(duration)


def _is_white(px, thr=225):
    return all(int(v) >= thr for v in px[:3])


@unittest.skipUnless(TEMPLATE.exists(), "template video 'new template.mp4' not found")
class WhiteBoxRenderTest(unittest.TestCase):
    tmp = REPO / "output" / "_test_tmp"

    @classmethod
    def setUpClass(cls):
        cls.tmp.mkdir(parents=True, exist_ok=True)
        cls.green = cls.tmp / "green.mp4"
        _make_green_clip(cls.green)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_footage_shows_through_white_box(self):
        """With footage present, the box shows the (green) footage, never white."""
        frame = _compose([self.green]).get_frame(1.0)
        px = frame[SAMPLE_Y, SAMPLE_X]
        r, g, b = int(px[0]), int(px[1]), int(px[2])
        self.assertFalse(_is_white(px), f"white box is WHITE at center: {px[:3]}")
        # Green footage must dominate -> proves footage composited into the hole.
        self.assertGreater(g, 120, f"footage green not visible: {px[:3]}")
        self.assertGreater(g, r + 40, f"footage not green-dominant: {px[:3]}")
        self.assertGreater(g, b + 40, f"footage not green-dominant: {px[:3]}")

    def test_box_region_not_mostly_white(self):
        """The whole box region must not be a near-white rectangle."""
        frame = _compose([self.green]).get_frame(1.0)
        region = frame[
            WHITE_BOX["y"]: WHITE_BOX["y"] + WHITE_BOX["h"],
            WHITE_BOX["x"]: WHITE_BOX["x"] + WHITE_BOX["w"],
        ]
        white_ratio = float(np.mean(np.all(region[:, :, :3] >= 225, axis=2)))
        self.assertLess(white_ratio, 0.5, f"box is {white_ratio:.0%} white")

    def test_missing_footage_is_dark_not_white(self):
        """No footage (VPS download failure) degrades to a DARK box, never white."""
        frame = _compose([]).get_frame(1.0)
        px = frame[SAMPLE_Y, SAMPLE_X]
        self.assertFalse(_is_white(px), f"empty box rendered WHITE: {px[:3]}")


@unittest.skipUnless(
    os.getenv("RUN_SLOW_RENDER") == "1" and TEMPLATE.exists(),
    "slow end-to-end render (set RUN_SLOW_RENDER=1 to enable)",
)
class EndToEndRenderTest(unittest.TestCase):
    """Full render_video() → real .mp4 → sample encoded frame. ~1-2 min."""

    def test_rendered_file_white_box_not_white(self):
        tmp = REPO / "output" / "_test_e2e"
        tmp.mkdir(parents=True, exist_ok=True)
        green = tmp / "green.mp4"
        # Longer than the render so the box stays filled the whole time
        # (production footage is ~90s; a single short clip is not looped).
        _make_green_clip(green, seconds=32.0)
        out = tmp / "final.mp4"
        R.render_video(
            script={"title": "Test Judul Berita AI", "candidate_news": [{"source": "Test"}]},
            base_template=TEMPLATE,
            voiceover_path=tmp / "missing_vo.mp3",
            footage_paths=[green],
            music_path=None,
            out_path=out,
            duration=30,
        )
        self.assertTrue(out.exists() and out.stat().st_size > 10_000)
        frame = VideoFileClip(str(out)).get_frame(5.0)
        px = frame[SAMPLE_Y, SAMPLE_X]
        self.assertFalse(_is_white(px), f"rendered white box is WHITE: {px[:3]}")
        self.assertGreater(int(px[1]), int(px[0]) + 20, f"footage not visible: {px[:3]}")
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
