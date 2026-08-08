"""Smoke tests for render_video.

These exercise the REAL layering pipeline (template mask, footage box, title,
branding, outro) but stub out only the expensive encode step, so they stay
fast and don't break every time an internal helper is renamed. Pixel-level
"not white" guarantees live in tests/test_render_not_white.py.
"""
from pathlib import Path
from unittest import TestCase, mock, skipUnless
import tempfile
import shutil

import numpy as np
from moviepy import AudioClip, ColorClip

from src import renderer

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "new template.mp4"


def _make_clip(path: Path, seconds: float = 2.0) -> None:
    ColorClip((320, 240), color=(0, 200, 0)).with_duration(seconds).write_videofile(
        str(path), fps=12, codec="libx264", audio=False, logger=None,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )


def _make_silent_clip_with_audio(path: Path, seconds: float = 2.0) -> None:
    def silence(t):
        if np.isscalar(t):
            return np.zeros(2)
        return np.zeros((len(t), 2))

    silent = AudioClip(silence, duration=seconds, fps=44100)
    ColorClip((320, 240), color=(0, 200, 0)).with_duration(seconds).with_audio(silent).write_videofile(
        str(path), fps=12, codec="libx264", audio_codec="aac", logger=None,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )


def _make_clip_with_tone(path: Path, seconds: float = 30.0, frequency: float = 440.0) -> None:
    def sine(t):
        wave = 0.4 * np.sin(2 * np.pi * frequency * t)
        if np.isscalar(t):
            return np.array([wave, wave])
        return np.column_stack((wave, wave))

    tone = AudioClip(sine, duration=seconds, fps=44100)
    ColorClip((320, 240), color=(0, 200, 0)).with_duration(seconds).with_audio(tone).write_videofile(
        str(path), fps=12, codec="libx264", audio_codec="aac", logger=None,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )


def _make_voiceover(path: Path, seconds: float = 2.0, frequency: float = 440.0) -> None:
    def sine(t):
        wave = 0.4 * np.sin(2 * np.pi * frequency * t)
        if np.isscalar(t):
            return np.array([wave, wave])
        return np.column_stack((wave, wave))

    tone = AudioClip(
        sine,
        duration=seconds,
        fps=44100,
    )
    tone.write_audiofile(str(path), fps=44100, codec="pcm_s16le", logger=None)


def _stub_write(self, path, *args, **kwargs):
    Path(path).write_bytes(b"stub-video")


@skipUnless(TEMPLATE.exists(), "template video 'new template.mp4' not found")
class RenderVideoSmokeTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="renderer-test-"))
        self.clip = self.tmp / "clip.mp4"
        _make_clip(self.clip)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _render(self, footage_paths):
        out = self.tmp / "final.mp4"
        with mock.patch.object(renderer.CompositeVideoClip, "write_videofile", new=_stub_write):
            renderer.render_video(
                script={"title": "Judul Berita AI", "candidate_news": [{"source": "Test"}]},
                base_template=TEMPLATE,
                voiceover_path=self.tmp / "no_voiceover.mp3",
                footage_paths=footage_paths,
                music_path=None,
                out_path=out,
                duration=30,
            )
        return out

    def test_mix_audio_skips_empty_or_missing_voiceover_before_loading(self):
        for voiceover_path in ("", self.tmp / "no_voiceover.mp3"):
            with self.subTest(voiceover_path=voiceover_path), \
                    mock.patch.object(renderer, "AudioFileClip", side_effect=OSError) as audio_file:
                self.assertIsNone(renderer._mix_audio(voiceover_path, None, 30, 0.2))
            audio_file.assert_not_called()

    def _capture_audio_render(self, footage, music_path):
        captured = {}

        def capture_write(clip, path, *args, **kwargs):
            captured["audio"] = clip.audio
            Path(path).write_bytes(b"stub-video")

        with mock.patch.object(renderer.CompositeVideoClip, "write_videofile", new=capture_write):
            renderer.render_video(
                script={"title": "Judul Berita Indonesia"},
                base_template=TEMPLATE,
                voiceover_path=music_path or footage,
                footage_paths=[footage],
                music_path=music_path,
                out_path=self.tmp / "source-or-music.mp4",
                audio_mode="source_or_music",
                duration=30,
            )
        return captured["audio"]

    def test_renders_with_footage(self):
        """Full build with footage present completes and writes the output file."""
        out = self._render([self.clip])
        self.assertTrue(out.exists() and out.stat().st_size > 0)

    def test_renders_without_footage(self):
        """No footage (VPS download failure) still builds and writes — no crash."""
        out = self._render([])
        self.assertTrue(out.exists() and out.stat().st_size > 0)

    def test_footage_layer_is_composited(self):
        """The footage box is added as its own layer when footage is present."""
        captured = {}
        real_ctor = renderer.CompositeVideoClip

        def _capture(clips, *a, **k):
            captured.setdefault("counts", []).append(len(clips))
            return real_ctor(clips, *a, **k)

        with mock.patch.object(renderer.CompositeVideoClip, "write_videofile", new=_stub_write), \
                mock.patch("src.renderer.CompositeVideoClip", side_effect=_capture):
            renderer.render_video(
                script={"title": "Judul"},
                base_template=TEMPLATE,
                voiceover_path=self.tmp / "x.mp3",
                footage_paths=[self.clip],
                music_path=None,
                out_path=self.tmp / "a.mp4",
                duration=30,
            )
        # The outermost compose gets the most layers; with footage it must exceed
        # the no-footage baseline (fallback + template + gradient + bar + title + outro).
        self.assertTrue(captured.get("counts"))
        self.assertGreaterEqual(max(captured["counts"]), 6)

    def test_voiceover_only_does_not_use_silent_footage_audio(self):
        """A footage audio stream must not override an audible voiceover."""
        footage = self.tmp / "silent-footage.mp4"
        voiceover = self.tmp / "voiceover.wav"
        _make_silent_clip_with_audio(footage, seconds=30)
        _make_voiceover(voiceover)
        captured = {}

        def _capture_write(clip, path, *args, **kwargs):
            captured["audio"] = clip.audio
            Path(path).write_bytes(b"stub-video")

        with mock.patch.object(renderer.CompositeVideoClip, "write_videofile", new=_capture_write):
            renderer.render_video(
                script={"title": "Judul"},
                base_template=TEMPLATE,
                voiceover_path=voiceover,
                footage_paths=[footage],
                music_path=None,
                out_path=self.tmp / "voiceover.mp4",
                audio_mode="voiceover_only",
                duration=30,
            )

        sample = np.asarray(captured["audio"].get_frame(0.501))
        self.assertGreater(float(np.max(np.abs(sample))), 0.01)

    def test_source_or_music_uses_audible_footage(self):
        footage = self.tmp / "english.mp4"
        music = self.tmp / "music.wav"
        _make_clip_with_tone(footage, seconds=30)
        _make_voiceover(music, seconds=30, frequency=880)
        with mock.patch.object(renderer, "_has_audible_audio", return_value=True) as audible, \
                mock.patch.object(renderer, "_mix_audio", wraps=renderer._mix_audio) as mix:
            captured = self._capture_audio_render(footage, music_path=music)
        try:
            audible.assert_called_once_with(footage)
            mix.assert_not_called()
            self.assertGreater(float(captured.get_frame(0.501)[0]), 0.1)
        finally:
            captured.close()

    def test_source_or_music_falls_back_to_music(self):
        footage = self.tmp / "silent.mp4"
        music = self.tmp / "music.wav"
        _make_silent_clip_with_audio(footage, seconds=30)
        _make_voiceover(music, seconds=30, frequency=880)
        with mock.patch.object(renderer, "_has_audible_audio", return_value=False) as audible, \
                mock.patch.object(renderer, "_mix_audio", wraps=renderer._mix_audio) as mix:
            captured = self._capture_audio_render(footage, music_path=music)
        try:
            audible.assert_called_once_with(footage)
            mix.assert_called_once_with(music, music, 30, 0.2, "music_only")
            self.assertLess(float(captured.get_frame(0.501)[0]), -0.02)
        finally:
            captured.close()
