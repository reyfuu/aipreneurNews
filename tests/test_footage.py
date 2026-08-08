import json
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

import numpy as np
from moviepy import AudioClip

from src import footage
from src.content_history import sha256_file


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

    @mock.patch("src.footage._download_youtube")
    @mock.patch("src.footage._run_ytdlp")
    def test_malformed_view_count_normalizes_to_none_and_is_not_downloaded(self, run, download):
        run.return_value = CompletedProcess(
            [], 0,
            json.dumps({
                "title": "Viral AI clip",
                "webpage_url": "https://example/viral",
                "duration": 60,
                "view_count": "invalid",
            }) + "\n",
            "",
        )

        self.assertIsNone(footage._search_youtube("viral AI")[0]["view_count"])
        self.assertIsNone(footage.search_and_download_news_video(title="Viral AI", out_dir=self.tmp))
        download.assert_not_called()

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
    def test_search_skips_used_url_before_download(self, search, download, audible):
        selected = self.tmp / "new.mp4"
        selected.write_bytes(b"new video" * 800)
        search.return_value = [
            {"title": "Used AI", "url": "https://example/used", "duration": 60, "view_count": 900000},
            {"title": "New AI", "url": "https://example/new", "duration": 60, "view_count": 800000},
        ]
        download.return_value = selected
        items = []

        result = footage.search_and_download_news_video(
            title="AI", out_dir=self.tmp,
            used_footage_urls={"https://example/used"}, selected_items=items,
        )

        self.assertEqual(result, selected)
        self.assertEqual(download.call_args.args[0], "https://example/new")
        self.assertEqual(items[0]["url"], "https://example/new")

    @mock.patch("src.footage._has_audible_audio", return_value=True)
    @mock.patch("src.footage._download_youtube")
    @mock.patch("src.footage._search_youtube")
    def test_search_deletes_duplicate_hash_and_tries_next(self, search, download, audible):
        duplicate = self.tmp / "duplicate.mp4"
        fresh = self.tmp / "fresh.mp4"
        duplicate.write_bytes(b"same bytes" * 800)
        fresh.write_bytes(b"fresh bytes" * 800)
        search.return_value = [
            {"title": "First", "url": "https://example/first", "duration": 60, "view_count": 900000},
            {"title": "Second", "url": "https://example/second", "duration": 60, "view_count": 800000},
        ]
        download.side_effect = [duplicate, fresh]

        result = footage.search_and_download_news_video(
            title="AI", out_dir=self.tmp,
            used_footage_hashes={sha256_file(duplicate)}, selected_items=[],
        )

        self.assertEqual(result, fresh)
        self.assertFalse(duplicate.exists())

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
        self.assertIsNone(footage.search_and_download_news_video(out_dir=self.tmp))
        queries = [call.args[0] for call in search.call_args_list]
        expected = [
            "viral AI",
            "AI tools",
            "AI tutorial",
            "AI podcast",
            "AI robots",
            "AI demo",
            "generative AI",
            "ChatGPT",
            "Claude AI",
            "open source AI",
            "artificial intelligence",
        ]
        self.assertEqual(queries, expected)

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

    @mock.patch("src.footage.download_pexels_footage")
    @mock.patch("src.footage.search_and_download_news_video", return_value=None)
    def test_download_pexels_discards_duplicate_hash_and_records_fresh_item(self, search, pexels):
        duplicate = self.tmp / "duplicate.mp4"
        fresh = self.tmp / "fresh.mp4"
        duplicate.write_bytes(b"same bytes" * 800)
        fresh.write_bytes(b"fresh bytes" * 800)
        pexels.return_value = [duplicate, fresh]
        items = []

        result = footage.download_news_video(
            title="AI", out_dir=self.tmp,
            used_footage_hashes={sha256_file(duplicate)}, selected_items=items,
        )

        self.assertEqual(result, [fresh])
        self.assertFalse(duplicate.exists())
        self.assertEqual(items, [{
            "provider": "pexels",
            "url": "",
            "file": str(fresh),
            "sha256": sha256_file(fresh),
        }])

    @mock.patch("src.footage.download_pexels_footage")
    @mock.patch("src.footage.search_and_download_news_video", return_value=None)
    def test_download_raises_when_all_pexels_hashes_are_used(self, search, pexels):
        duplicate = self.tmp / "duplicate.mp4"
        duplicate.write_bytes(b"same bytes" * 800)
        pexels.return_value = [duplicate]

        with self.assertRaises(footage.NoNewFootage):
            footage.download_news_video(
                title="AI", out_dir=self.tmp,
                used_footage_hashes={sha256_file(duplicate)}, selected_items=[],
            )

        self.assertFalse(duplicate.exists())
