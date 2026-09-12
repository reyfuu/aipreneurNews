from pathlib import Path
import json
from datetime import datetime
import tempfile
import shutil
from unittest import TestCase, mock

from src import main
from src.footage import NoNewFootage


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

    def _settings(self, output_dir, *, upload_enabled=False):
        return {
            "timezone": "Asia/Jakarta",
            "feeds": {"window_hours_min": 6, "window_hours_max": 12, "feed_limit_per_source": 8, "max_items_for_ai": 5},
            "pipeline": {"target_video_duration_sec": 60, "music_volume": 0.2, "audio_mode": "music_only"},
            "upload": {"enabled": upload_enabled},
            "paths": {
                "output_dir": str(output_dir), "template_video": "template.mp4", "template_thumbnail": "thumbnail.png",
                "background_music_dir": str(Path(self.tmpdir) / "music"), "prompts_file": "config/prompts.txt", "feeds_file": "config/feeds.json",
            },
        }

    @mock.patch("src.main.append_jsonl")
    @mock.patch("src.main.generate_voiceover")
    @mock.patch("src.main.render_thumbnail")
    @mock.patch("src.main.render_video")
    @mock.patch("src.main.upload_to_youtube")
    @mock.patch("src.main.download_news_video")
    @mock.patch("src.main.scrape_recent_news")
    @mock.patch("src.main.generate_script")
    @mock.patch("src.main.load_json")
    def test_pipeline_skips_completed_source_url(
        self,
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
        run_date = "2026-08-06T10:00:00"
        load_json.return_value = {
            "timezone": "Asia/Jakarta",
            "feeds": {"window_hours_min": 6, "window_hours_max": 12, "feed_limit_per_source": 8, "max_items_for_ai": 5},
            "pipeline": {"target_video_duration_sec": 60, "music_volume": 0.2, "audio_mode": "music_only"},
            "upload": {"enabled": False},
            "paths": {
                "output_dir": str(output_dir),
                "template_video": "template.mp4",
                "template_thumbnail": "thumbnail.png",
                "background_music_dir": str(Path(self.tmpdir) / "music"),
                "prompts_file": "config/prompts.txt",
                "feeds_file": "config/feeds.json",
            },
        }
        history_path = output_dir / "history.jsonl"
        history_path.parent.mkdir(parents=True)
        history_path.write_text(
            '{"status":"completed","source_url":"https://example/used"}\n',
            encoding="utf-8",
        )
        scrape_news.return_value = [
            _NewsItem("Reuters", "Used story", "Summary", "https://example/used", datetime.fromisoformat(run_date)),
            _NewsItem("Reuters", "New story", "Summary", "https://example/new", datetime.fromisoformat(run_date)),
        ]
        generate_script.return_value = {
            "selected_index": 0, "title": "Fresh story title", "script_voiceover": "",
            "keywords": ["fresh"], "thumbnail_text": "Fresh", "description": "Description", "tags": ["news"],
        }
        download_footage.return_value = [Path(self.tmpdir) / "footage.mp4"]

        result = main.run_pipeline(skip_upload=True, run_date=run_date)

        self.assertEqual([item.link for item in generate_script.call_args.args[0]], ["https://example/new"])
        self.assertEqual(result["source_url"], "https://example/new")
        self.assertEqual(result["status"], "completed")
        render_video.assert_called_once()

    @mock.patch("src.main.append_jsonl")
    @mock.patch("src.main.generate_voiceover")
    @mock.patch("src.main.render_thumbnail")
    @mock.patch("src.main.render_video")
    @mock.patch("src.main.upload_to_youtube")
    @mock.patch("src.main.download_news_video")
    @mock.patch("src.main.scrape_recent_news")
    @mock.patch("src.main.generate_script")
    @mock.patch("src.main.load_json")
    def test_pipeline_retries_after_legacy_title_duplicate(
        self,
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
        run_date = "2026-08-06T10:00:00"
        load_json.return_value = {
            "timezone": "Asia/Jakarta",
            "feeds": {"window_hours_min": 6, "window_hours_max": 12, "feed_limit_per_source": 8, "max_items_for_ai": 5},
            "pipeline": {"target_video_duration_sec": 60, "music_volume": 0.2, "audio_mode": "music_only"},
            "upload": {"enabled": False},
            "paths": {
                "output_dir": str(output_dir), "template_video": "template.mp4",
                "template_thumbnail": "thumbnail.png", "background_music_dir": str(Path(self.tmpdir) / "music"),
                "prompts_file": "config/prompts.txt", "feeds_file": "config/feeds.json",
            },
        }
        history_path = output_dir / "history.jsonl"
        history_path.parent.mkdir(parents=True)
        history_path.write_text('{"status":"completed","title":"OpenAI Meluncurkan Model Baru Coding"}\n', encoding="utf-8")
        scrape_news.return_value = [
            _NewsItem("Reuters", "First story", "Summary", "https://example/first", datetime.fromisoformat(run_date)),
            _NewsItem("Reuters", "Second story", "Summary", "https://example/second", datetime.fromisoformat(run_date)),
        ]
        generate_script.side_effect = [
            {"selected_index": 0, "title": "OpenAI Luncurkan Model Baru Coding", "script_voiceover": "", "keywords": [], "thumbnail_text": "First", "description": "", "tags": []},
            {"selected_index": 0, "title": "Distinct second story", "script_voiceover": "", "keywords": [], "thumbnail_text": "Second", "description": "", "tags": []},
        ]
        download_footage.return_value = [Path(self.tmpdir) / "footage.mp4"]

        result = main.run_pipeline(skip_upload=True, run_date=run_date)

        self.assertEqual(generate_script.call_count, 2)
        self.assertEqual([item.link for item in generate_script.call_args_list[1].args[0]], ["https://example/second"])
        self.assertEqual(result["source_url"], "https://example/second")
        renderer_script = render_video.call_args.kwargs["script"]
        self.assertEqual(renderer_script["candidate_news"], [{
            "source": "Reuters",
            "title": "Second story",
            "summary": "Summary",
            "link": "https://example/second",
            "published": "2026-08-06T10:00:00",
        }])
        self.assertEqual(renderer_script["selected_index"], 0)
        self.assertEqual(renderer_script["candidate_news"][renderer_script["selected_index"]]["link"], "https://example/second")
        render_video.assert_called_once()

    @mock.patch("src.main.render_thumbnail")
    @mock.patch("src.main.render_video")
    @mock.patch("src.main.download_news_video")
    @mock.patch("src.main.generate_script")
    @mock.patch("src.main.scrape_recent_news")
    @mock.patch("src.main.load_json")
    def test_pipeline_clamps_selected_index_for_renderer_source_and_history(
        self, load_json, scrape_news, generate_script, download, render, thumbnail
    ):
        output_dir = Path(self.tmpdir) / "output"
        run_date = "2026-08-06T10:00:00"
        load_json.return_value = self._settings(output_dir)
        scrape_news.return_value = [
            _NewsItem("Reuters", "First source", "First summary", "https://example/first", datetime.now()),
            _NewsItem("BBC", "Second source", "Second summary", "https://example/second", datetime.now()),
        ]
        generate_script.return_value = {
            "selected_index": 99,
            "title": "Fresh generated title",
            "script_voiceover": "",
            "keywords": [],
            "thumbnail_text": "Fresh",
            "description": "",
            "tags": [],
        }
        footage_item = {
            "provider": "pexels",
            "url": "",
            "file": str(Path(self.tmpdir) / "fresh.mp4"),
            "sha256": "abc123",
        }

        def select_footage(*args, **kwargs):
            kwargs["selected_items"].append(footage_item)
            return [Path(footage_item["file"])]

        download.side_effect = select_footage

        result = main.run_pipeline(skip_upload=True, run_date=run_date)

        renderer_script = render.call_args.kwargs["script"]
        self.assertEqual(renderer_script["selected_index"], 0)
        self.assertEqual(renderer_script["candidate_news"][0]["link"], "https://example/first")
        self.assertEqual(result["source_url"], "https://example/first")
        self.assertEqual(result["source_title"], "First source")
        self.assertEqual(result["source"], "Reuters")
        self.assertEqual(result["title_key"], "fresh generated title")
        self.assertEqual(result["footage_items"], [footage_item])
        persisted = json.loads(
            (output_dir / "history.jsonl").read_text(encoding="utf-8").splitlines()[0]
        )
        self.assertEqual(persisted, result)
        script_payload = json.loads(
            (output_dir / "2026-08-06" / "script.json").read_text(encoding="utf-8")
        )
        self.assertEqual(script_payload["selected_index"], 0)
        self.assertEqual(script_payload["candidate_news"][0]["link"], result["source_url"])

    @mock.patch("src.main.append_jsonl")
    @mock.patch("src.main.generate_voiceover")
    @mock.patch("src.main.render_thumbnail")
    @mock.patch("src.main.render_video")
    @mock.patch("src.main.upload_to_youtube")
    @mock.patch("src.main.download_news_video")
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
                "audio_mode": "source_or_music",
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

        video_file = Path(history["video_file"])
        self.assertTrue(video_file.exists(), f"video not written: {video_file}")
        self.assertEqual(video_file.parent, date_dir)
        self.assertTrue((date_dir / "ig_caption.txt").exists())
        self.assertEqual((date_dir / "ig_caption.txt").read_text(encoding="utf-8").strip(), "Caption IG test")
        self.assertEqual(history["output_dir"], str(date_dir))
        self.assertIn("video_file", history)
        self.assertEqual(render_video.call_args.kwargs["audio_mode"], "source_or_music")
        self.assertFalse(generate_voiceover.called)
        self.assertEqual(render_video.call_args.kwargs["script"]["title"], "Judul Berita")
        self.assertTrue(render_video.called)


    @mock.patch("src.main.render_video")
    @mock.patch("src.main.upload_to_youtube")
    @mock.patch("src.main.generate_script")
    @mock.patch("src.main.scrape_recent_news")
    @mock.patch("src.main.load_json")
    def test_pipeline_returns_no_new_content_when_all_story_urls_are_used(self, load_json, scrape_news, generate_script, upload, render):
        output_dir = Path(self.tmpdir) / "output"
        load_json.return_value = self._settings(output_dir)
        history_path = output_dir / "history.jsonl"
        history_path.parent.mkdir(parents=True)
        history_path.write_text('{"status":"completed","source_url":"https://example/used"}\n', encoding="utf-8")
        scrape_news.return_value = [_NewsItem("Reuters", "Used", "", "https://example/used", datetime.now())]
        before_lines = history_path.read_text(encoding="utf-8").splitlines()

        result = main.run_pipeline(skip_upload=True, run_date="2026-08-06T10:00:00")

        lines = history_path.read_text(encoding="utf-8").splitlines()
        expected = {
            "run_at": "2026-08-06T10:00:00+07:00",
            "status": "no_new_content",
            "reason": "all stories were already used",
        }
        self.assertEqual(result, expected)
        self.assertEqual(len(lines), len(before_lines) + 1)
        self.assertEqual(json.loads(lines[-1]), expected)
        render.assert_not_called()
        upload.assert_not_called()
        generate_script.assert_not_called()

    @mock.patch("src.main.render_video")
    @mock.patch("src.main.upload_to_youtube")
    @mock.patch("src.main.download_news_video", side_effect=NoNewFootage("used"))
    @mock.patch("src.main.generate_script")
    @mock.patch("src.main.scrape_recent_news")
    @mock.patch("src.main.load_json")
    def test_pipeline_returns_no_new_content_when_all_footage_is_used(self, load_json, scrape_news, generate_script, download, upload, render):
        output_dir = Path(self.tmpdir) / "output"
        load_json.return_value = self._settings(output_dir)
        scrape_news.return_value = [_NewsItem("Reuters", "Fresh", "", "https://example/fresh", datetime.now())]
        generate_script.return_value = {"selected_index": 0, "title": "Fresh title", "script_voiceover": "", "keywords": [], "thumbnail_text": "", "description": "", "tags": []}

        result = main.run_pipeline(skip_upload=True, run_date="2026-08-06T10:00:00")
        history_path = output_dir / "history.jsonl"

        lines = history_path.read_text(encoding="utf-8").splitlines()
        expected = {
            "run_at": "2026-08-06T10:00:00+07:00",
            "status": "no_new_content",
            "reason": "all footage was already used",
        }
        self.assertEqual(result, expected)
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), expected)
        render.assert_not_called()
        upload.assert_not_called()

    @mock.patch("src.main.render_video")
    @mock.patch("src.main.upload_to_youtube")
    @mock.patch("src.main.generate_script")
    @mock.patch("src.main.scrape_recent_news")
    @mock.patch("src.main.load_json")
    def test_pipeline_appends_one_exact_no_new_row_after_legacy_title_exhaustion(
        self, load_json, scrape_news, generate_script, upload, render
    ):
        output_dir = Path(self.tmpdir) / "output"
        load_json.return_value = self._settings(output_dir)
        history_path = output_dir / "history.jsonl"
        history_path.parent.mkdir(parents=True)
        history_path.write_text(
            '{"status":"completed","title":"OpenAI meluncurkan model coding baru"}\n',
            encoding="utf-8",
        )
        scrape_news.return_value = [
            _NewsItem("Reuters", "Fresh URL", "", "https://example/fresh", datetime.now())
        ]
        generate_script.return_value = {
            "selected_index": 0,
            "title": "OpenAI luncurkan model coding baru",
        }

        result = main.run_pipeline(skip_upload=True, run_date="2026-08-06T10:00:00")

        expected = {
            "run_at": "2026-08-06T10:00:00+07:00",
            "status": "no_new_content",
            "reason": "all stories were already used",
        }
        lines = history_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(result, expected)
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[-1]), expected)
        render.assert_not_called()
        upload.assert_not_called()

    @mock.patch("src.main.render_thumbnail")
    @mock.patch("src.main.render_video")
    @mock.patch("src.main.upload_to_youtube", side_effect=RuntimeError("upload offline"))
    @mock.patch("src.main.download_news_video")
    @mock.patch("src.main.generate_script")
    @mock.patch("src.main.scrape_recent_news")
    @mock.patch("src.main.load_json")
    def test_pipeline_persists_completed_identity_when_upload_fails(self, load_json, scrape_news, generate_script, download, upload, render, thumbnail):
        output_dir = Path(self.tmpdir) / "output"
        load_json.return_value = self._settings(output_dir, upload_enabled=True)
        scrape_news.return_value = [_NewsItem("Reuters", "Fresh source", "", "https://example/fresh", datetime.now())]
        generate_script.return_value = {"selected_index": 0, "title": "Fresh title", "script_voiceover": "", "keywords": [], "thumbnail_text": "", "description": "", "tags": []}
        download.return_value = [Path(self.tmpdir) / "footage.mp4"]

        result = main.run_pipeline(run_date="2026-08-06T10:00:00")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["upload_status"], "failed")
        self.assertIn("upload offline", result["upload_error"])
        self.assertEqual(result["source_url"], "https://example/fresh")
        self.assertEqual(json.loads((output_dir / "history.jsonl").read_text(encoding="utf-8").splitlines()[-1])["upload_status"], "failed")

    @mock.patch("src.main.render_thumbnail", side_effect=RuntimeError("thumbnail broken"))
    @mock.patch("src.main.render_video")
    @mock.patch("src.main.upload_to_youtube", return_value={"id": "uploaded-video"})
    @mock.patch("src.main.download_news_video")
    @mock.patch("src.main.generate_script")
    @mock.patch("src.main.scrape_recent_news")
    @mock.patch("src.main.load_json")
    def test_pipeline_persists_rendered_identity_and_uploads_without_failed_thumbnail(
        self, load_json, scrape_news, generate_script, download, upload, render, thumbnail
    ):
        output_dir = Path(self.tmpdir) / "output"
        load_json.return_value = self._settings(output_dir, upload_enabled=True)
        scrape_news.return_value = [
            _NewsItem("Reuters", "Fresh source", "", "https://example/fresh", datetime.now())
        ]
        generate_script.return_value = {
            "selected_index": 0,
            "title": "Fresh title",
            "script_voiceover": "",
            "keywords": [],
            "thumbnail_text": "Fresh",
            "description": "",
            "tags": [],
        }
        download.return_value = [Path(self.tmpdir) / "footage.mp4"]

        first = main.run_pipeline(run_date="2026-08-06T10:00:00")

        self.assertEqual(first["status"], "completed")
        self.assertEqual(first["thumbnail_status"], "failed")
        self.assertIn("thumbnail broken", first["thumbnail_error"])
        self.assertIsNone(first["thumbnail_file"])
        self.assertEqual(first["upload_status"], "uploaded")
        self.assertIsNone(upload.call_args.kwargs["thumbnail_path"])
        persisted = json.loads(
            (output_dir / "history.jsonl").read_text(encoding="utf-8").splitlines()[0]
        )
        self.assertEqual(persisted, first)

        second = main.run_pipeline(run_date="2026-08-06T10:00:00")

        self.assertEqual(second["status"], "no_new_content")
        self.assertEqual(generate_script.call_count, 1)
        render.assert_called_once()
        upload.assert_called_once()

    @mock.patch("src.main.upload_to_youtube")
    @mock.patch("src.main.render_video")
    @mock.patch("src.main.generate_script")
    @mock.patch("src.main.scrape_recent_news")
    @mock.patch("src.main.pipeline_lock")
    @mock.patch("src.main.load_json")
    def test_pipeline_returns_already_running_without_work(self, load_json, pipeline_lock, scrape_news, generate_script, render, upload):
        load_json.return_value = self._settings(Path(self.tmpdir) / "output")
        pipeline_lock.return_value.__enter__.return_value = False

        self.assertEqual(main.run_pipeline(), {"status": "already_running"})
        scrape_news.assert_not_called()
        generate_script.assert_not_called()
        render.assert_not_called()
        upload.assert_not_called()


class PipelineInstagramTest(TestCase):
    """Langkah publish Instagram dipasang setelah render, di belakang config flag."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="pipeline-ig-")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _settings(self, output_dir, *, ig_enabled):
        return {
            "timezone": "Asia/Jakarta",
            "feeds": {"window_hours_min": 6, "window_hours_max": 12, "feed_limit_per_source": 8, "max_items_for_ai": 5},
            "pipeline": {"target_video_duration_sec": 60, "music_volume": 0.2, "audio_mode": "music_only"},
            "upload": {"enabled": False},
            "instagram": {
                "enabled": ig_enabled,
                "share_to_feed": True,
                "public_base_url": "https://news.example.id",
            },
            "paths": {
                "output_dir": str(output_dir), "template_video": "template.mp4",
                "template_thumbnail": "thumbnail.png",
                "background_music_dir": str(Path(self.tmpdir) / "music"),
                "prompts_file": "config/prompts.txt", "feeds_file": "config/feeds.json",
            },
        }

    def _run(
        self,
        *,
        ig_enabled,
        skip_upload=False,
        skip_instagram=False,
        publish_side_effect=None,
    ):
        output_dir = Path(self.tmpdir) / "output"
        run_date = "2026-08-06T10:00:00"
        with mock.patch("src.main.append_jsonl"), \
             mock.patch("src.main.generate_voiceover"), \
             mock.patch("src.main.render_thumbnail"), \
             mock.patch("src.main.render_video"), \
             mock.patch("src.main.upload_to_youtube"), \
             mock.patch("src.main.download_news_video") as download_footage, \
             mock.patch("src.main.scrape_recent_news") as scrape_news, \
             mock.patch("src.main.generate_script") as generate_script, \
             mock.patch("src.main.load_json") as load_json, \
             mock.patch("src.main.publish_reel") as publish_reel:
            load_json.return_value = self._settings(output_dir, ig_enabled=ig_enabled)
            scrape_news.return_value = [
                _NewsItem("Reuters", "A story", "Summary", "https://example/a",
                          datetime.fromisoformat(run_date)),
            ]
            generate_script.return_value = {
                "selected_index": 0, "title": "A story", "script_voiceover": "",
                "keywords": ["ai"], "thumbnail_text": "A", "description": "Desc",
                "tags": ["news"], "ig_caption": "Caption IG #ai",
            }
            download_footage.return_value = [Path(self.tmpdir) / "footage.mp4"]
            publish_reel.return_value = {
                "media_id": "MEDIA1", "container_id": "C1",
                "permalink": "https://instagram.com/reel/x",
            }
            if publish_side_effect is not None:
                publish_reel.side_effect = publish_side_effect
            result = main.run_pipeline(
                skip_upload=skip_upload,
                skip_instagram=skip_instagram,
                run_date=run_date,
            )
        return result, publish_reel

    def test_publishes_when_enabled(self):
        result, publish_reel = self._run(ig_enabled=True, skip_upload=False)
        publish_reel.assert_called_once()
        kwargs = publish_reel.call_args.kwargs
        self.assertTrue(
            kwargs["video_url"].startswith("https://news.example.id/api/outputs/2026-08-06/")
        )
        self.assertEqual(kwargs["caption"], "Caption IG #ai")
        self.assertEqual(result["instagram_status"], "published")
        self.assertEqual(result["instagram_media_id"], "MEDIA1")
        self.assertEqual(result["instagram_permalink"], "https://instagram.com/reel/x")

    def test_disabled_by_config(self):
        result, publish_reel = self._run(ig_enabled=False, skip_upload=False)
        publish_reel.assert_not_called()
        self.assertEqual(result["instagram_status"], "skipped")

    def test_skip_upload_also_skips_instagram(self):
        result, publish_reel = self._run(ig_enabled=True, skip_upload=True)
        publish_reel.assert_not_called()
        self.assertEqual(result["instagram_status"], "skipped")

    def test_skip_instagram_flag_skips_only_instagram(self):
        result, publish_reel = self._run(ig_enabled=True, skip_instagram=True)
        publish_reel.assert_not_called()
        self.assertEqual(result["instagram_status"], "skipped")
        # Video tetap dirender seperti biasa.
        self.assertEqual(result["status"], "completed")

    def test_failure_does_not_break_pipeline(self):
        from src.publisher_instagram import InstagramPublishError

        result, _ = self._run(
            ig_enabled=True,
            skip_upload=False,
            publish_side_effect=InstagramPublishError("token kedaluwarsa"),
        )
        # Video tetap dianggap sukses; kegagalan IG hanya dicatat.
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["instagram_status"], "failed")
        self.assertIn("token kedaluwarsa", result["instagram_error"])


class SkipFlagRoutingTest(TestCase):
    """--skip-youtube dan --skip-instagram hanya mematikan platformnya sendiri."""

    def _run(self, **flags):
        settings = {
            "timezone": "Asia/Jakarta",
            "feeds": {"window_hours_min": 6, "window_hours_max": 12, "feed_limit_per_source": 8, "max_items_for_ai": 5},
            "pipeline": {"target_video_duration_sec": 60, "music_volume": 0.2, "audio_mode": "music_only"},
            "upload": {"enabled": True},
            "instagram": {"enabled": True, "public_base_url": "https://news.example.id"},
            "paths": {
                "output_dir": str(Path(self.tmpdir) / "output"), "template_video": "template.mp4",
                "template_thumbnail": "thumbnail.png",
                "background_music_dir": str(Path(self.tmpdir) / "music"),
                "prompts_file": "config/prompts.txt", "feeds_file": "config/feeds.json",
            },
        }
        run_date = "2026-08-06T10:00:00"
        with mock.patch("src.main.append_jsonl"), \
             mock.patch("src.main.generate_voiceover"), \
             mock.patch("src.main.render_thumbnail"), \
             mock.patch("src.main.render_video"), \
             mock.patch("src.main.upload_to_youtube") as upload_yt, \
             mock.patch("src.main.download_news_video") as download_footage, \
             mock.patch("src.main.scrape_recent_news") as scrape_news, \
             mock.patch("src.main.generate_script") as generate_script, \
             mock.patch("src.main.load_json") as load_json, \
             mock.patch("src.main.publish_reel") as publish_reel:
            load_json.return_value = settings
            scrape_news.return_value = [
                _NewsItem("Reuters", "A story", "Summary", "https://example/a",
                          datetime.fromisoformat(run_date)),
            ]
            generate_script.return_value = {
                "selected_index": 0, "title": "A story", "script_voiceover": "",
                "keywords": ["ai"], "thumbnail_text": "A", "description": "Desc",
                "tags": ["news"], "ig_caption": "Caption",
            }
            download_footage.return_value = [Path(self.tmpdir) / "footage.mp4"]
            upload_yt.return_value = {"id": "YT1"}
            publish_reel.return_value = {"media_id": "IG1", "container_id": "C1", "permalink": None}
            result = main.run_pipeline(run_date=run_date, **flags)
        return result, upload_yt, publish_reel

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="skip-flags-")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_flags_runs_both(self):
        result, upload_yt, publish_reel = self._run()
        upload_yt.assert_called_once()
        publish_reel.assert_called_once()
        self.assertEqual(result["upload_status"], "uploaded")
        self.assertEqual(result["instagram_status"], "published")

    def test_skip_youtube_keeps_instagram(self):
        result, upload_yt, publish_reel = self._run(skip_youtube=True)
        upload_yt.assert_not_called()
        publish_reel.assert_called_once()
        self.assertEqual(result["upload_status"], "skipped")
        self.assertEqual(result["instagram_status"], "published")

    def test_skip_instagram_keeps_youtube(self):
        result, upload_yt, publish_reel = self._run(skip_instagram=True)
        upload_yt.assert_called_once()
        publish_reel.assert_not_called()
        self.assertEqual(result["upload_status"], "uploaded")
        self.assertEqual(result["instagram_status"], "skipped")

    def test_skip_upload_is_master_switch(self):
        result, upload_yt, publish_reel = self._run(skip_upload=True)
        upload_yt.assert_not_called()
        publish_reel.assert_not_called()
        self.assertEqual(result["upload_status"], "skipped")
        self.assertEqual(result["instagram_status"], "skipped")

    def test_both_platform_flags_together(self):
        _, upload_yt, publish_reel = self._run(skip_youtube=True, skip_instagram=True)
        upload_yt.assert_not_called()
        publish_reel.assert_not_called()
