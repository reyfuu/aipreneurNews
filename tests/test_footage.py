from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

import numpy as np
from moviepy import AudioClip

from src import footage


class FootageAudioTest(TestCase):
    def setUp(self):
        self._temp_dir = TemporaryDirectory()
        self.tmp = Path(self._temp_dir.name)

    def tearDown(self):
        self._temp_dir.cleanup()

    @mock.patch("src.footage.subprocess.run")
    def test_audible_audio_passes_threshold(self, run):
        run.return_value = CompletedProcess([], 0, "", "max_volume: -12.4 dB\\n")
        self.assertTrue(footage._has_audible_audio(Path("news.mp4")))

    @mock.patch("src.footage.subprocess.run")
    def test_silent_audio_is_rejected(self, run):
        run.return_value = CompletedProcess([], 0, "", "max_volume: -91.0 dB\\n")
        self.assertFalse(footage._has_audible_audio(Path("silent.mp4")))

    @mock.patch("src.footage.subprocess.run")
    def test_missing_audio_stream_is_rejected(self, run):
        run.return_value = CompletedProcess([], 1, "", "Output file does not contain any stream\\n")
        self.assertFalse(footage._has_audible_audio(Path("video-only.mp4")))

    def test_audio_after_render_window_is_rejected(self):
        delayed_tone = self.tmp / "delayed-tone.wav"

        def delayed_sine(t):
            if np.isscalar(t):
                wave = 0.0 if t < 2.0 else 0.4 * np.sin(2 * np.pi * 440 * t)
                return np.array([wave, wave])
            times = np.asarray(t)
            wave = np.where(times < 2.0, 0.0, 0.4 * np.sin(2 * np.pi * 440 * times))
            return np.column_stack((wave, wave))

        AudioClip(delayed_sine, duration=3, fps=44100).write_audiofile(
            str(delayed_tone), fps=44100, codec="pcm_s16le", logger=None
        )

        self.assertFalse(footage._has_audible_audio(delayed_tone, duration=1))
        self.assertTrue(footage._has_audible_audio(delayed_tone))

    @mock.patch("src.footage._has_audible_audio", side_effect=[False, True])
    @mock.patch("src.footage._download_youtube")
    @mock.patch("src.footage._search_youtube")
    def test_search_skips_silent_candidate(self, search, download, audible):
        first = self.tmp / "silent.mp4"
        second = self.tmp / "audible.mp4"
        first.write_bytes(b"video" * 1200)
        second.write_bytes(b"video" * 1200)
        search.return_value = [
            {"title": "OpenAI Astra report", "url": "https://example/1", "duration": 60},
            {"title": "OpenAI Astra interview", "url": "https://example/2", "duration": 90},
        ]
        download.side_effect = [first, second]

        result = footage.search_and_download_news_video(
            title="OpenAI Astra", out_dir=self.tmp, audio_duration=30
        )

        self.assertEqual(result, second)
        self.assertFalse(first.exists())
        self.assertEqual(
            audible.call_args_list,
            [mock.call(first, duration=30), mock.call(second, duration=30)],
        )

    @mock.patch("src.footage.search_and_download_news_video")
    def test_download_uses_preferred_duration_for_audio_check(self, search):
        selected = self.tmp / "selected.mp4"
        selected.write_bytes(b"video")
        search.return_value = selected

        self.assertEqual(
            footage.download_news_video(
                title="OpenAI Astra", out_dir=self.tmp, preferred_duration=42
            ),
            [selected],
        )
        self.assertEqual(search.call_args.kwargs["audio_duration"], 42)
