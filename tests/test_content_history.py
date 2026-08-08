from pathlib import Path
import shutil
import tempfile
from unittest import TestCase

from src import content_history as history


class ContentHistoryTest(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="content-history-test-")
        self.output = Path(self.tmpdir) / "output"
        self.history = self.output / "history.jsonl"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_normalize_url_removes_tracking_fragment_and_trailing_slash(self):
        value = "HTTPS://Example.com/story/?utm_source=rss&id=7#top"
        self.assertEqual(history.normalize_url(value), "https://example.com/story?id=7")

    def test_titles_similar_uses_jaccard_threshold(self):
        old = "OpenAI Rem Astra AI Ini Terlalu Bahaya"
        new = "OpenAI Rem Model AI Astra Terlalu Berbahaya"
        self.assertTrue(history.titles_similar(old, new, threshold=0.60))
        self.assertFalse(history.titles_similar(old, "Claude merilis fitur coding baru", threshold=0.60))

    def test_loader_keeps_valid_rows_skips_malformed_and_scans_legacy_footage(self):
        footage = self.output / "2026-08-08" / "footage" / "old.mp4"
        footage.parent.mkdir(parents=True)
        footage.write_bytes(b"legacy clip")
        self.history.write_text(
            '{"title":"Old AI Story","source_url":"https://example.com/story/",'
            '"footage_items":[{"provider":"youtube","url":"https://youtu.be/abc",'
            '"file":"old.mp4","sha256":"stored"}]}\nnot-json\n'
            '{"status":"no_new_content","source_url":"https://ignored.example"}\n',
            encoding="utf-8",
        )

        index = history.load_history_index(self.history, self.output)

        self.assertTrue(index.story_seen(source_url="https://example.com/story"))
        self.assertTrue(index.footage_seen(url="https://youtu.be/abc"))
        self.assertIn(history.sha256_file(footage), index.footage_hashes)
        self.assertFalse(index.story_seen(source_url="https://ignored.example"))

    def test_loader_skips_wrong_typed_fields_and_keeps_later_valid_rows(self):
        self.history.parent.mkdir(parents=True)
        self.history.write_text(
            '{"status":"completed","source_url":123,"title":[],"footage_items":'
            '[{"url":{"bad":true},"sha256":["bad"]}]}\n'
            '{"status":"completed","source_url":"https://example.com/partial",'
            '"title":7,"footage_items":{"bad":true}}\n'
            '{"status":"completed","source_url":"https://example.com/valid",'
            '"title":"Valid later story","footage_items":['
            '{"url":"https://videos.example/valid","sha256":"valid-digest"}]}\n',
            encoding="utf-8",
        )

        index = history.load_history_index(self.history, self.output)

        self.assertTrue(index.story_seen(source_url="https://example.com/partial"))
        self.assertTrue(index.story_seen(source_url="https://example.com/valid"))
        self.assertTrue(
            index.footage_seen(url="https://videos.example/valid", digest="valid-digest")
        )

    def test_current_rows_use_exact_title_keys_while_only_legacy_titles_are_fuzzy(self):
        self.history.parent.mkdir(parents=True)
        self.history.write_text(
            '{"status":"completed","source_url":"https://example.com/openai",'
            '"title":"OpenAI luncurkan fitur baru",'
            '"title_key":"baru fitur luncurkan openai"}\n'
            '{"status":"completed","title":"Claude merilis alat coding baru"}\n',
            encoding="utf-8",
        )

        index = history.load_history_index(self.history, self.output)

        self.assertTrue(index.story_seen(source_url="https://example.com/openai"))
        self.assertTrue(
            index.story_seen(
                source_url="https://example.com/other",
                title="OPENAI Luncurkan Fitur Baru!",
            )
        )
        self.assertFalse(
            index.story_seen(
                source_url="https://example.com/google",
                title="Google luncurkan fitur baru",
            )
        )
        self.assertTrue(index.story_seen(title="Claude merilis alat coding terbaru"))

    def test_pipeline_lock_rejects_concurrent_holder(self):
        lock_path = self.output / "pipeline.lock"
        with history.pipeline_lock(lock_path) as first:
            with history.pipeline_lock(lock_path) as second:
                self.assertTrue(first)
                self.assertFalse(second)
