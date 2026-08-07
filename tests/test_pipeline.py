from pathlib import Path
from datetime import datetime
import tempfile
import shutil
from unittest import TestCase, mock

from src import main


class _NewsItem:
    def __init__(self, source: str, title: str, summary: str, link: str, pub_date: datetime):
        self.source = source
        self.title = title
        self.summary = summary
        self.link = link
        self.pub_date = pub_date

    def to_dict(self):
        return {
            "source": self.source,
            "title": self.title,
            "summary": self.summary,
            "link": self.link,
            "published": self.pub_date.isoformat(),
        }


class PipelineTest(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="pipeline-test-")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @mock.patch("src.main.append_jsonl")
    @mock.patch("src.main.generate_voiceover")
    @mock.patch("src.main.render_thumbnail")
    @mock.patch("src.main.render_video")
    @mock.patch("src.main.upload_to_youtube")
    @mock.patch("src.main.download_footage")
    @mock.patch("src.main.scrape_recent_news")
    @mock.patch("src.main.generate_script")
    @mock.patch("src.main.load_json")
    @mock.patch("src.main.now_local")
    @mock.patch("src.main.now_utc", return_value=datetime.fromisoformat("2026-08-06T10:00:00+00:00"))
    def test_pipeline_creates_video_and_caption(
        self,
        now_utc,
        now_local,
        load_json,
        generate_script,
        scrape_news,
        download_footage,
        upload_to_youtube,
        render_video,
        render_thumbnail,
        generate_voiceover,
        append_jsonl,
    ):
        output_dir = Path(self.tmpdir) / "output"
        run_date = datetime(2026, 8, 6, 10, 0, 0)
        now_local.return_value = run_date

        load_json.return_value = {
            "timezone": "Asia/Jakarta",
            "feeds": {"window_hours_min": 6, "window_hours_max": 12, "feed_limit_per_source": 8, "max_items_for_ai": 5},
            "pipeline": {
                "target_video_duration_sec": 60,
                "target_voice_duration_sec": 60,
                "target_footage_count": 3,
                "music_volume": 0.2,
                "audio_mode": "music_only",
            },
            "upload": {"enabled": False},
            "scheduler": {"mode": "local", "time": "06:00", "tz": "Asia/Jakarta"},
            "paths": {
                "output_dir": str(output_dir),
                "template_video": "Template AIPreneur 1.mp4",
                "template_thumbnail": "templates/thumb_template.png",
                "font_path": "templates/fonts/arial-bold.ttf",
                "background_music_dir": str(Path(self.tmpdir) / "music"),
                "prompts_file": "config/prompts.txt",
                "feeds_file": "config/feeds.json",
            },
        }

        scrape_news.return_value = [
            _NewsItem("The Guardian", "News title", "Isi ringkas", "https://example.com", run_date)
        ]
        generate_script.return_value = {
            "selected_index": 0,
            "title": "Judul Berita",
            "script_voiceover": "Ini isi naskah",
            "hook": "Pembuka",
            "keywords": ["news", "world"],
            "thumbnail_text": "Judul",
            "description": "Deskripsi berita",
            "tags": ["news", "world"],
            "ig_caption": "Caption IG test",
            "script": "Isi script",
        }
        download_footage.return_value = [Path(self.tmpdir) / "footage_1.mp4"]
        def _fake_voiceover(*args, **kwargs):
            path = args[1]
            path.write_bytes(b"fake mp3")
        generate_voiceover.side_effect = _fake_voiceover

        def _fake_render_video(*args, **kwargs):
            out_path = kwargs["out_path"]
            out_path.write_bytes(b"fake video")
        render_video.side_effect = _fake_render_video

        def _fake_thumbnail(*args, **kwargs):
            out_path = kwargs["out_path"]
            out_path.write_bytes(b"fake thumb")
        render_thumbnail.side_effect = _fake_thumbnail

        history = main.run_pipeline(skip_upload=True)
        date_dir = Path(output_dir) / "2026-08-06"

        self.assertTrue((date_dir / "final_video.mp4").exists())
        self.assertTrue((date_dir / "ig_caption.txt").exists())
        self.assertEqual((date_dir / "ig_caption.txt").read_text(encoding="utf-8").strip(), "Caption IG test")
        self.assertEqual(history["output_dir"], str(date_dir))
        self.assertIn("video_file", history)
        self.assertEqual(render_video.call_args.kwargs["audio_mode"], "music_only")
        self.assertTrue(render_video.called)
