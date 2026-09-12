import unittest
from unittest import mock

from src import publisher_instagram as ig


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.text = str(payload)

    def json(self):
        return self._payload


class BuildPublicUrlTest(unittest.TestCase):
    def test_builds_output_endpoint_url(self):
        url = ig.build_public_video_url(
            "https://news.aipreneur.co.id", "2026-09-12", "clip name.mp4"
        )
        self.assertEqual(
            url, "https://news.aipreneur.co.id/api/outputs/2026-09-12/clip%20name.mp4"
        )

    def test_trailing_slash_does_not_duplicate(self):
        url = ig.build_public_video_url("https://x.id/", "2026-09-12", "a.mp4")
        self.assertEqual(url, "https://x.id/api/outputs/2026-09-12/a.mp4")

    def test_empty_base_url_is_rejected(self):
        with self.assertRaises(ig.InstagramPublishError):
            ig.build_public_video_url("", "2026-09-12", "a.mp4")

    def test_non_https_is_rejected(self):
        # Meta menolak URL non-HTTPS, jadi jangan sampai terkirim.
        with self.assertRaises(ig.InstagramPublishError):
            ig.build_public_video_url("http://localhost:8001", "2026-09-12", "a.mp4")


class TrimCaptionTest(unittest.TestCase):
    def test_caption_is_truncated_to_limit(self):
        trimmed = ig.trim_caption("a" * (ig.CAPTION_LIMIT + 500))
        self.assertLessEqual(len(trimmed), ig.CAPTION_LIMIT)

    def test_extra_hashtags_are_dropped(self):
        caption = "Judul " + " ".join(f"#tag{i}" for i in range(40))
        trimmed = ig.trim_caption(caption)
        self.assertEqual(trimmed.count("#"), ig.MAX_HASHTAGS)
        self.assertTrue(trimmed.startswith("Judul "))

    def test_normal_caption_is_untouched(self):
        self.assertEqual(ig.trim_caption("  Halo dunia #ai  "), "Halo dunia #ai")


class PublishReelTest(unittest.TestCase):
    def test_happy_path_creates_waits_and_publishes(self):
        post = mock.Mock(
            side_effect=[
                FakeResponse({"id": "CONTAINER1"}),
                FakeResponse({"id": "MEDIA1"}),
            ]
        )
        get = mock.Mock(
            side_effect=[
                FakeResponse({"status_code": "IN_PROGRESS"}),
                FakeResponse({"status_code": "FINISHED"}),
                FakeResponse({"permalink": "https://instagram.com/reel/abc"}),
            ]
        )
        with mock.patch.object(ig.requests, "post", post), mock.patch.object(
            ig.requests, "get", get
        ):
            result = ig.publish_reel(
                video_url="https://x.id/a.mp4",
                caption="halo",
                ig_user_id="IGID",
                access_token="TOKEN",
                poll_interval=0,
                sleep=lambda _s: None,
            )

        self.assertEqual(result["media_id"], "MEDIA1")
        self.assertEqual(result["container_id"], "CONTAINER1")
        self.assertEqual(result["permalink"], "https://instagram.com/reel/abc")

        create_kwargs = post.call_args_list[0].kwargs["data"]
        self.assertEqual(create_kwargs["media_type"], "REELS")
        self.assertEqual(create_kwargs["video_url"], "https://x.id/a.mp4")
        self.assertEqual(create_kwargs["caption"], "halo")
        self.assertEqual(create_kwargs["share_to_feed"], "true")

        publish_kwargs = post.call_args_list[1].kwargs["data"]
        self.assertEqual(publish_kwargs["creation_id"], "CONTAINER1")

    def test_missing_credentials_raises(self):
        with mock.patch.dict("os.environ", {"IG_USER_ID": "", "IG_ACCESS_TOKEN": ""}, clear=False):
            with self.assertRaises(ig.InstagramPublishError):
                ig.publish_reel(video_url="https://x.id/a.mp4", ig_user_id="", access_token="")

    def test_container_error_status_raises_and_does_not_publish(self):
        post = mock.Mock(return_value=FakeResponse({"id": "CONTAINER1"}))
        get = mock.Mock(return_value=FakeResponse({"status_code": "ERROR", "status": "bad video"}))
        with mock.patch.object(ig.requests, "post", post), mock.patch.object(
            ig.requests, "get", get
        ):
            with self.assertRaises(ig.InstagramPublishError) as ctx:
                ig.publish_reel(
                    video_url="https://x.id/a.mp4",
                    ig_user_id="IGID",
                    access_token="TOKEN",
                    poll_interval=0,
                    sleep=lambda _s: None,
                )
        self.assertIn("ERROR", str(ctx.exception))
        # Hanya container yang dibuat; media_publish tidak boleh dipanggil.
        self.assertEqual(post.call_count, 1)

    def test_api_error_payload_is_surfaced(self):
        post = mock.Mock(
            return_value=FakeResponse(
                {"error": {"message": "Invalid OAuth access token", "code": 190}}, status_code=400
            )
        )
        with mock.patch.object(ig.requests, "post", post):
            with self.assertRaises(ig.InstagramPublishError) as ctx:
                ig.publish_reel(
                    video_url="https://x.id/a.mp4", ig_user_id="IGID", access_token="BAD"
                )
        self.assertIn("Invalid OAuth access token", str(ctx.exception))

    def test_timeout_when_container_never_finishes(self):
        get = mock.Mock(return_value=FakeResponse({"status_code": "IN_PROGRESS"}))
        with mock.patch.object(ig.requests, "get", get):
            with self.assertRaises(ig.InstagramPublishError) as ctx:
                ig.wait_for_container(
                    container_id="C1",
                    access_token="TOKEN",
                    poll_interval=0,
                    max_wait_seconds=0,
                    sleep=lambda _s: None,
                )
        self.assertIn("belum siap", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
