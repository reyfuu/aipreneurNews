from pathlib import Path
from unittest import TestCase, mock
import tempfile
import shutil


from src import renderer


class _FakeClip:
    def __init__(self, name: str, duration: float = 5.0, size=(1920, 1080), fps: float = 30.0):
        self.name = name
        self.duration = duration
        self.w, self.h = size
        self.fps = fps

    def with_duration(self, duration):
        self.duration = duration
        return self

    def with_start(self, start):
        self.start = start
        return self

    def with_position(self, position):
        self.position = position
        return self

    def with_opacity(self, opacity):
        self.opacity = opacity
        return self

    def subclipped(self, start: float, end: float):
        self.duration = max(0.0, end - start)
        return self

    def with_audio(self, audio):
        self.audio = audio
        return self


class _FakeCompositeVideoClip:
    created = None

    def __init__(self, clips, size=None):
        self.clips = clips
        self.duration = None
        self.size = size
        self.audio = None
        self.path = None
        _FakeCompositeVideoClip.created = self

    def with_duration(self, duration):
        self.duration = duration
        return self

    def with_audio(self, audio):
        self.audio = audio
        return self

    def write_videofile(self, path, *args, **kwargs):
        self.path = Path(path)
        self.path.write_bytes(b"fake video")


class _FakeAudio:
    def __init__(self, name: str):
        self.name = name


class RendererTest(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="renderer-test-")
        _FakeCompositeVideoClip.created = None

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @mock.patch("src.renderer.CompositeVideoClip", _FakeCompositeVideoClip)
    @mock.patch("src.renderer._load_base_video")
    @mock.patch("src.renderer._build_footage_background")
    @mock.patch("src.renderer._caption_overlays")
    @mock.patch("src.renderer._safe_audio_duration")
    @mock.patch("src.renderer._mix_audio")
    def test_render_video_uses_reference_footage(self, mix_audio, safe_audio_duration, caption_overlays, build_footage_bg, load_base_video):
        output = Path(self.tmpdir) / "final_video.mp4"
        load_base_video.return_value = _FakeClip("template", 5.0, (1080, 1920))
        build_footage_bg.return_value = _FakeClip("reference-clip", 60.0, (1080, 1920))
        caption_overlays.return_value = []
        safe_audio_duration.return_value = 60
        mix_audio.return_value = _FakeAudio("music")

        renderer.render_video(
            script={"hook": "Hook test", "title": "Judul", "script_voiceover": "kata kata"},
            base_template=Path("Template AIPreneur 1.mp4"),
            voiceover_path=Path("output/voiceover.mp3"),
            footage_paths=[Path("output/footage_1.mp4")],
            music_path=Path("assets/background_music/song.mp3"),
            out_path=output,
            duration=60,
            music_volume=0.1,
        )

        composition = _FakeCompositeVideoClip.created
        self.assertIsNotNone(composition)
        self.assertTrue(output.exists())
        self.assertEqual(composition.path, output)
        self.assertTrue(any(getattr(clip, "name", "") == "reference-clip" for clip in composition.clips))

    @mock.patch("src.renderer.CompositeAudioClip")
    @mock.patch("src.renderer._mix_audio")
    @mock.patch("src.renderer._safe_audio_duration", return_value=60)
    @mock.patch("src.renderer._load_base_video")
    @mock.patch("src.renderer._build_footage_background", return_value=None)
    @mock.patch("src.renderer._caption_overlays", return_value=[])
    @mock.patch("src.renderer.AudioFileClip")
    @mock.patch("src.renderer.concatenate_audioclips")
    @mock.patch("src.renderer.concatenate_videoclips")
    def test_render_video_generates_video_file(
        self,
        concat_videoclips,
        concat_audioclips,
        mock_audio_file,
        caption_overlays,
        build_footage_bg,
        load_base_video,
        safe_audio_duration,
        mix_audio,
        CompositeAudioClip,
    ):
        output = Path(self.tmpdir) / "final_video.mp4"
        load_base_video.return_value = _FakeClip("template", 5.0, (1080, 1920))
        mix_audio.return_value = _FakeAudio("music")

        class _ComposedClip(_FakeCompositeVideoClip):
            pass

        with mock.patch("src.renderer.CompositeVideoClip", _ComposedClip):
            renderer.render_video(
                script={"hook": "Hook test", "title": "Judul", "script_voiceover": "kata"},
                base_template=Path("Template AIPreneur 1.mp4"),
                voiceover_path=Path("output/voiceover.mp3"),
                footage_paths=[],
                music_path=Path("assets/background_music/song.mp3"),
                out_path=output,
                duration=60,
                music_volume=0.1,
            )

        self.assertTrue(output.exists())
