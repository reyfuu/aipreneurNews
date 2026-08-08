# Source Audio with CC0 Music Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gunakan audio Inggris asli yang terdengar, pertahankan judul Indonesia, dan gunakan musik CC0 jika tidak ada footage dengan audio layak.

**Architecture:** `src/footage.py` memvalidasi volume setiap hasil YouTube sebelum menerimanya. `src/renderer.py` menjalankan mode `source_or_music`: pakai audio footage tervalidasi, atau loop musik lokal. `src/main.py` tidak memanggil TTS untuk mode ini dan tetap meneruskan script Indonesia tanpa perubahan.

**Tech Stack:** Python 3.10+, stdlib `subprocess`, FFmpeg, MoviePy, Django test runner, yt-dlp, Wikimedia Commons CC0.

## Global Constraints

- Judul, thumbnail, metadata, dan overlay tetap Bahasa Indonesia.
- Audio Inggris asli boleh digunakan tanpa diterjemahkan.
- Kandidat dianggap terdengar jika `max_volume > -50 dB`.
- Jika tidak ada kandidat terdengar, gunakan musik CC0 lokal; jangan gunakan voiceover AI.
- Musik hanya diunduh sekali saat implementasi, bukan pada setiap pipeline run.
- API key dan credential tidak boleh ditulis ke git.
- Output produksi tetap disimpan di `output/YYYY-MM-DD/`.

---

### Task 1: Validate Downloaded Footage Audio

**Files:**
- Create: `tests/test_footage.py`
- Modify: `src/footage.py:127-378`

**Interfaces:**
- Consumes: FFmpeg executable available on PATH and downloaded `Path` objects.
- Produces: `_audio_max_volume(path: Path) -> float | None` and `_has_audible_audio(path: Path, threshold_db: float = -50.0) -> bool`.

- [ ] **Step 1: Write failing volume parser tests**

```python
from pathlib import Path
from subprocess import CompletedProcess
from unittest import TestCase, mock

from src import footage


class FootageAudioTest(TestCase):
    @mock.patch("src.footage.subprocess.run")
    def test_audible_audio_passes_threshold(self, run):
        run.return_value = CompletedProcess([], 0, "", "max_volume: -12.4 dB\n")
        self.assertTrue(footage._has_audible_audio(Path("news.mp4")))

    @mock.patch("src.footage.subprocess.run")
    def test_silent_audio_is_rejected(self, run):
        run.return_value = CompletedProcess([], 0, "", "max_volume: -91.0 dB\n")
        self.assertFalse(footage._has_audible_audio(Path("silent.mp4")))

    @mock.patch("src.footage.subprocess.run")
    def test_missing_audio_stream_is_rejected(self, run):
        run.return_value = CompletedProcess([], 1, "", "Output file does not contain any stream\n")
        self.assertFalse(footage._has_audible_audio(Path("video-only.mp4")))
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/python manage.py test tests.test_footage.FootageAudioTest -v 2`

Expected: ERROR because `_has_audible_audio` does not exist.

- [ ] **Step 3: Implement the minimal FFmpeg volume check**

```python
def _audio_max_volume(path):
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", result.stderr)
    return float(match.group(1)) if match else None


def _has_audible_audio(path, threshold_db=-50.0):
    volume = _audio_max_volume(path)
    return volume is not None and volume > threshold_db
```

- [ ] **Step 4: Add a failing candidate-selection test**

```python
@mock.patch("src.footage._has_audible_audio", side_effect=[False, True])
@mock.patch("src.footage._download_youtube")
@mock.patch("src.footage._search_youtube")
def test_search_skips_silent_candidate(self, search, download, audible):
    first = self.tmp / "silent.mp4"
    second = self.tmp / "audible.mp4"
    first.write_bytes(b"video")
    second.write_bytes(b"video")
    search.return_value = [
        {"title": "OpenAI Astra report", "url": "https://example/1", "duration": 60},
        {"title": "OpenAI Astra interview", "url": "https://example/2", "duration": 90},
    ]
    download.side_effect = [first, second]
    result = footage.search_and_download_news_video(title="OpenAI Astra", out_dir=self.tmp)
    self.assertEqual(result, second)
    self.assertFalse(first.exists())
```

- [ ] **Step 5: Run candidate test and verify RED**

Run: `.venv/bin/python manage.py test tests.test_footage.FootageAudioTest.test_search_skips_silent_candidate -v 2`

Expected: FAIL because the first downloaded file is returned without validation.

- [ ] **Step 6: Reject silent downloads and continue candidates**

Replace the success branch in `search_and_download_news_video` with:

```python
if video_path and video_path.stat().st_size > 5000:
    if _has_audible_audio(video_path):
        logger.info("Footage terpilih dengan audio (skor %d): %s", v["score"], video_path)
        return video_path
    logger.info("Footage ditolak karena audio diam/tidak ada: %s", video_path)
    video_path.unlink(missing_ok=True)
```

- [ ] **Step 7: Run footage tests and commit**

Run: `.venv/bin/python manage.py test tests.test_footage -v 2`

Expected: all footage tests PASS.

```bash
git add src/footage.py tests/test_footage.py
git commit -m "feat: reject silent news footage"
```

### Task 2: Render Source Audio or CC0 Music

**Files:**
- Modify: `src/renderer.py:613-790`
- Modify: `tests/test_renderer.py`

**Interfaces:**
- Consumes: `_has_audible_audio(path)` from Task 1, first footage clip audio, optional `music_path`.
- Produces: `render_video` support for `audio_mode="source_or_music"`, selecting exactly one audible source.

- [ ] **Step 1: Add failing renderer tests for both branches**

Reuse the real audio fixtures already in `tests/test_renderer.py`. Add this audible footage helper:

```python
def _make_clip_with_tone(path: Path, seconds: float = 30.0) -> None:
    def sine(t):
        wave = 0.4 * np.sin(2 * np.pi * 440 * t)
        if np.isscalar(t):
            return np.array([wave, wave])
        return np.column_stack((wave, wave))

    tone = AudioClip(sine, duration=seconds, fps=44100)
    ColorClip((320, 240), color=(0, 200, 0)).with_duration(seconds).with_audio(tone).write_videofile(
        str(path), fps=12, codec="libx264", audio_codec="aac", logger=None,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )
```

Add this class helper to capture `CompositeVideoClip.audio` at the existing stubbed encode boundary:

```python
def _capture_audio_render(self, footage, music_path):
    captured = {}

    def capture_write(clip, path, *args, **kwargs):
        captured["audio"] = clip.audio
        Path(path).write_bytes(b"stub-video")

    with mock.patch.object(renderer.CompositeVideoClip, "write_videofile", new=capture_write):
        renderer.render_video(
            script={"title": "Judul Berita Indonesia"},
            base_template=TEMPLATE,
            voiceover_path=self.tmp / "empty.mp3",
            footage_paths=[footage],
            music_path=music_path,
            out_path=self.tmp / "source-or-music.mp4",
            audio_mode="source_or_music",
            duration=30,
        )
    return captured["audio"]
```

```python
def test_source_or_music_uses_audible_footage(self):
    footage = self.tmp / "english.mp4"
    _make_clip_with_tone(footage, seconds=30)
    captured = self._capture_audio_render(footage, music_path=None)
    self.assertGreater(float(np.max(np.abs(captured.get_frame(0.501)))), 0.01)

def test_source_or_music_falls_back_to_music(self):
    footage = self.tmp / "silent.mp4"
    music = self.tmp / "music.wav"
    _make_silent_clip_with_audio(footage, seconds=30)
    _make_voiceover(music)
    captured = self._capture_audio_render(footage, music_path=music)
    self.assertGreater(float(np.max(np.abs(captured.get_frame(0.501)))), 0.01)
```

- [ ] **Step 2: Run renderer tests and verify RED**

Run: `.venv/bin/python manage.py test tests.test_renderer.RenderVideoSmokeTest -v 2`

Expected: at least one `source_or_music` branch fails because the mode does not exist.

- [ ] **Step 3: Implement explicit source-or-music selection**

In `render_video`, keep the first footage clip for both duration and audio. At the audio selection point:

```python
if audio_mode == "source_or_music":
    audio = None
    if footage_clip and footage_clip.audio and paths and _has_audible_audio(paths[0]):
        end = min(target_duration, footage_clip.audio.duration or target_duration)
        audio = footage_clip.audio.subclipped(0, end).with_volume_scaled(1.0)
    if audio is None:
        audio = _mix_audio(voiceover_path, music_path, target_duration, music_volume, "music_only")
else:
    audio = _mix_audio(voiceover_path, music_path, target_duration, music_volume, audio_mode)
if audio is not None:
    composed = composed.with_audio(audio)
```

Import `_has_audible_audio` from `src.footage`. Do not add a new abstraction or dependency.

- [ ] **Step 4: Run renderer tests and commit**

Run: `.venv/bin/python manage.py test tests.test_renderer -v 2`

Expected: all renderer tests PASS.

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "feat: render original audio with music fallback"
```

### Task 3: Configure Pipeline and Add CC0 Asset

**Files:**
- Modify: `src/main.py:233-293`
- Modify: `config/settings.json`
- Modify: `tests/test_pipeline.py`
- Create: `assets/background_music/chill-beat-cc0.ogg`
- Create: `assets/background_music/chill-beat-cc0.LICENSE.txt`

**Interfaces:**
- Consumes: `audio_mode="source_or_music"`, local CC0 audio file.
- Produces: pipeline invocation that skips TTS, preserves Indonesian script fields, and passes source-or-music inputs to renderer.

- [ ] **Step 1: Change pipeline test to specify desired behavior and verify RED**

Use `audio_mode: "source_or_music"`, keep `script["title"] = "Judul Berita"`, then assert:

```python
self.assertEqual(render_video.call_args.kwargs["audio_mode"], "source_or_music")
self.assertFalse(generate_voiceover.called)
self.assertEqual(render_video.call_args.kwargs["script"]["title"], "Judul Berita")
```

Run: `.venv/bin/python manage.py test tests.test_pipeline.PipelineTest -v 2`

Expected: FAIL because current code still calls Edge TTS for every non-`music_only` mode.

- [ ] **Step 2: Skip TTS for source-or-music mode**

```python
voice_modes = {"voiceover_only", "voiceover_and_music"}
if voiceover_script and audio_mode in voice_modes:
    generate_voiceover(
        voiceover_script,
        voiceover_path,
        voice=os.getenv("EDGE_TTS_VOICE", "id-ID-GadisNeural"),
    )
else:
    voiceover_path.write_bytes(b"")
```

Keep title/script generation unchanged. Set `config/settings.json` to `"audio_mode": "source_or_music"`.

- [ ] **Step 3: Download and record the CC0 fallback asset**

Download `https://commons.wikimedia.org/wiki/Special:Redirect/file/Chill_Beat.ogg` into `assets/background_music/chill-beat-cc0.ogg`. Write these exact fields into `chill-beat-cc0.LICENSE.txt`, replacing only the checksum with the output of `shasum -a 256`:

```text
Title: Chill Beat
Author: Maddy
Source: https://commons.wikimedia.org/wiki/File:Chill_Beat.ogg
License: CC0 1.0 Universal
License URL: https://creativecommons.org/publicdomain/zero/1.0/
Downloaded: 2026-08-08
```

Append a `SHA-256:` line containing the exact output of
`shasum -a 256 assets/background_music/chill-beat-cc0.ogg`; do not commit a
placeholder value.

Update music discovery in `src/main.py`:

```python
music_files = [
    path for pattern in ("*.mp3", "*.ogg", "*.wav")
    for path in music_dir.glob(pattern)
] if music_dir.exists() else []
```

- [ ] **Step 4: Run pipeline test, asset probe, and commit**

Run: `.venv/bin/python manage.py test tests.test_pipeline.PipelineTest -v 2`

Run: `ffprobe -v error -show_entries format=duration,size -of json assets/background_music/chill-beat-cc0.ogg`

Expected: pipeline test PASS; asset duration is greater than 30 seconds and size greater than 100 KB.

```bash
git add src/main.py config/settings.json tests/test_pipeline.py assets/background_music/chill-beat-cc0.ogg assets/background_music/chill-beat-cc0.LICENSE.txt
git commit -m "feat: add CC0 music audio fallback"
```

### Task 4: Full Verification, VPS Deployment, and Live Output

**Files:**
- Modify only if a test exposes a scoped defect.

**Interfaces:**
- Consumes: completed Tasks 1–3.
- Produces: deployed VPS service and browser-playable output with Indonesian title and non-silent audio.

- [ ] **Step 1: Run full local verification**

Run: `.venv/bin/python manage.py test tests -v 1`

Run: `git diff --check`

Expected: 0 failed tests; no whitespace errors.

- [ ] **Step 2: Back up and deploy exact changed files to VPS**

Back up changed VPS files under `/var/backups/aipreneurNews/20260808-source-audio/`, upload the files, and verify local/remote SHA-256 values match.

- [ ] **Step 3: Run full VPS verification and restart service**

Run remotely: `.venv/bin/python manage.py test tests -v 1`

Run remotely: `systemctl restart aipreneur-news.service`

Run remotely: `systemctl is-active aipreneur-news.service`

Expected: tests have 0 failures and service prints `active`.

- [ ] **Step 4: Trigger one production pipeline run**

Use the dashboard API with `skip_upload=true`. Poll its task endpoint until `status` is `finished` or `failed`; do not restart the service during the run.

- [ ] **Step 5: Verify Indonesian title and audible final MP4**

Run FFprobe against the new MP4 and FFmpeg `volumedetect`. Assert:

- H.264 video at 1080x1920.
- AAC audio exists.
- `max_volume > -50 dB`.
- `script.json` title and dashboard preview title are Indonesian.

- [ ] **Step 6: Verify browser playback**

Reload `https://news.aipreneur.co.id`, play the latest video, and inspect:

```javascript
({
  paused: video.paused,
  currentTime: video.currentTime,
  duration: video.duration,
  muted: video.muted,
  volume: video.volume,
  error: video.error && video.error.message,
})
```

Expected: `paused=false`, `currentTime>2`, `muted=false`, `volume=1`, `error=null`.

- [ ] **Step 7: Final commit if verification required scoped fixes**

Commit only files changed to address observed verification failures. Do not commit output videos or credentials.
