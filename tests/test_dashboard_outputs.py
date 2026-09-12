import os
import tempfile
from pathlib import Path
from unittest import mock
import django
from django.test import Client, TestCase, override_settings

if not django.apps.apps.ready:
    django.setup()

from dashboard import services


class DashboardOutputsTest(TestCase):
    def test_outputs_use_project_root_and_prefer_latest_canonical_video(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as cwd_dir:
            project_root = Path(temp_dir)
            output_root = project_root / "output"
            older_dir = output_root / "2026-08-07"
            newer_dir = output_root / "2026-08-08"
            older_dir.mkdir(parents=True)
            newer_dir.mkdir(parents=True)

            older_video = older_dir / "final_video.mp4"
            newer_video = newer_dir / "final_video.mp4"
            test_video = newer_dir / "test_rebuild.mp4"
            older_video.write_bytes(b"older")
            newer_video.write_bytes(b"newer")
            test_video.write_bytes(b"test")
            os.utime(older_video, (100, 100))
            os.utime(newer_video, (200, 200))
            os.utime(test_video, (300, 300))

            original_cwd = Path.cwd()
            os.chdir(cwd_dir)
            try:
                with override_settings(BASE_DIR=project_root):
                    outputs = services.get_outputs()
            finally:
                os.chdir(original_cwd)

            self.assertTrue(outputs)
            self.assertEqual(outputs[0]["date"], "2026-08-08")
            self.assertEqual(outputs[0]["final_video"]["name"], "final_video.mp4")

    def test_output_file_is_served_from_project_root(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as cwd_dir:
            project_root = Path(temp_dir)
            output_dir = project_root / "output" / "2026-08-08"
            output_dir.mkdir(parents=True)
            video_path = output_dir / "final_video.mp4"
            video_path.write_bytes(b"video")

            original_cwd = Path.cwd()
            os.chdir(cwd_dir)
            try:
                with override_settings(
                    BASE_DIR=project_root, ALLOWED_HOSTS=["testserver", "*"]
                ):
                    response = Client().get("/api/outputs/2026-08-08/final_video.mp4")
            finally:
                os.chdir(original_cwd)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"video")

    def test_output_file_serves_slugified_video_name(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as cwd_dir:
            project_root = Path(temp_dir)
            output_dir = project_root / "output" / "2026-08-08"
            output_dir.mkdir(parents=True)
            # Pipeline menulis nama ter-slugify per berita, bukan final_video.mp4.
            video_path = output_dir / "mecka_ai_nears_500m_valuation_105926.mp4"
            video_path.write_bytes(b"0123456789")

            original_cwd = Path.cwd()
            os.chdir(cwd_dir)
            try:
                with override_settings(
                    BASE_DIR=project_root, ALLOWED_HOSTS=["testserver", "*"]
                ):
                    client = Client()
                    response = client.get(f"/api/outputs/2026-08-08/{video_path.name}")
                    partial = client.get(
                        f"/api/outputs/2026-08-08/{video_path.name}",
                        headers={"range": "bytes=2-4"},
                    )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "video/mp4")
            self.assertEqual(response["Accept-Ranges"], "bytes")
            self.assertIn("inline", response["Content-Disposition"])
            self.assertEqual(b"".join(response.streaming_content), b"0123456789")

            self.assertEqual(partial.status_code, 206)
            self.assertEqual(partial["Content-Range"], "bytes 2-4/10")
            self.assertEqual(partial["Content-Length"], "3")
            self.assertEqual(b"".join(partial.streaming_content), b"234")

    def test_output_file_rejects_traversal_and_unlisted_files(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as cwd_dir:
            project_root = Path(temp_dir)
            output_dir = project_root / "output" / "2026-08-08"
            output_dir.mkdir(parents=True)
            (output_dir / "final_video.mp4").write_bytes(b"video")
            (output_dir / "notes.md").write_text("nope", encoding="utf-8")
            (project_root / "secret.json").write_text("{}", encoding="utf-8")

            original_cwd = Path.cwd()
            os.chdir(cwd_dir)
            try:
                with override_settings(
                    BASE_DIR=project_root, ALLOWED_HOSTS=["testserver", "*"]
                ):
                    client = Client()
                    codes = [
                        client.get("/api/outputs/2026-08-08/notes.md").status_code,
                        client.get("/api/outputs/2026-08-08/secret.json").status_code,
                        client.get("/api/outputs/2026-08-08/../secret.json").status_code,
                        client.get(
                            "/api/outputs/2026-08-08/%2E%2E/secret.json"
                        ).status_code,
                    ]
            finally:
                os.chdir(original_cwd)

            self.assertEqual(codes, [404, 404, 404, 404])
