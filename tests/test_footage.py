import json
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

    @mock.patch("src.footage._run_ytdlp")
    def test_search_youtube_keeps_view_count(self, run):
        run.return_value = CompletedProcess(
            [], 0,
            json.dumps({
                "title": "Viral AI clip",
                "webpage_url": "https://example/viral",
                "duration": 60,
                "view_count": 250000,
            }) + "\n",
            "",
        )

        self.assertEqual(footage._search_youtube("viral AI")[0]["view_count"], 250000)

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
            {"title": "OpenAI Astra report", "url": "https://example/1", "duration": 60, "view_count": 100000},
            {"title": "OpenAI Astra interview", "url": "https://example/2", "duration": 90, "view_count": 100000},
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

    @mock.patch("src.footage._has_audible_audio", return_value=True)
    @mock.patch("src.footage._download_youtube")
    @mock.patch("src.footage._search_youtube")
    def test_search_requires_100k_views_and_prefers_more_views(self, search, download, audible):
        selected = self.tmp / "viral.mp4"
        selected.write_bytes(b"video" * 1200)
        search.return_value = [
            {"title": "OpenAI clip", "url": "https://example/low", "duration": 60, "view_count": 99999},
            {"title": "OpenAI clip", "url": "https://example/min", "duration": 60, "view_count": 100000},
            {"title": "OpenAI clip", "url": "https://example/high", "duration": 60, "view_count": 900000},
            {"title": "OpenAI clip", "url": "https://example/missing", "duration": 60, "view_count": None},
        ]
        download.return_value = selected

        result = footage.search_and_download_news_video(title="OpenAI", out_dir=self.tmp)

        self.assertEqual(result, selected)
        self.assertEqual(download.call_args.args[0], "https://example/high")

    @mock.patch("src.footage._has_audible_audio", return_value=True)
    @mock.patch("src.footage._download_youtube")
    @mock.patch("src.footage._search_youtube")
    def test_search_accepts_exactly_100k_views(self, search, download, audible):
        selected = self.tmp / "minimum.mp4"
        selected.write_bytes(b"video" * 1200)
        search.return_value = [
            {"title": "AI clip", "url": "https://example/min", "duration": 60, "view_count": 100000},
        ]
        download.return_value = selected

        self.assertEqual(
            footage.search_and_download_news_video(title="AI", out_dir=self.tmp),
            selected,
        )

    @mock.patch("src.footage._download_youtube")
    @mock.patch("src.footage._search_youtube")
    def test_search_rejects_low_or_missing_views_before_download(self, search, download):
        search.return_value = [
            {"title": "AI clip", "url": "https://example/low", "duration": 60, "view_count": 99999},
            {"title": "AI clip", "url": "https://example/missing", "duration": 60, "view_count": None},
        ]

        self.assertIsNone(footage.search_and_download_news_video(title="AI", out_dir=self.tmp))
        download.assert_not_called()

    @mock.patch("src.footage._search_youtube", return_value=[])
    def test_search_adds_generic_ai_queries(self, search):
        self.assertIsNone(footage.search_and_download_news_video(title="AI news", out_dir=self.tmp))
        queries = [call.args[0] for call in search.call_args_list]
        self.assertIn("viral AI", queries)
        self.assertIn("artificial intelligence", queries)
        self.assertIn("AI technology", queries)

    @mock.patch("src.footage._has_audible_audio", return_value=True)
    @mock.patch("src.footage._download_youtube")
    @mock.patch("src.footage._search_youtube")
    def test_specific_search_wins_equal_relevance_before_generic_views(self, search, download, audible):
        selected = self.tmp / "specific.mp4"
        selected.write_bytes(b"video" * 1200)

        def results(query, max_results=8):
            if query == "viral AI":
                return [{"title": "AI clip", "url": "https://example/generic", "duration": 60, "view_count": 900000}]
            if query in {"artificial intelligence", "AI technology"}:
                return []
            return [{"title": "AI clip", "url": "https://example/specific", "duration": 60, "view_count": 100000}]

        search.side_effect = results
        download.return_value = selected

        result = footage.search_and_download_news_video(title="AI news", out_dir=self.tmp)

        self.assertEqual(result, selected)
        self.assertEqual(download.call_args.args[0], "https://example/specific")

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
