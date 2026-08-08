from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

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

        result = footage.search_and_download_news_video(title="OpenAI Astra", out_dir=self.tmp)

        self.assertEqual(result, second)
        self.assertFalse(first.exists())
