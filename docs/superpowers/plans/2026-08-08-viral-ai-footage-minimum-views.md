# Viral AI Footage Minimum Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hanya download footage YouTube bertema AI dengan sedikitnya 100.000 views, sambil mempertahankan fallback Pexels + musik CC0.

**Architecture:** Metadata `view_count` yang sudah disediakan yt-dlp dipertahankan oleh `_search_youtube`. `search_and_download_news_video` menambahkan query AI umum, menyaring kandidat sebelum download, lalu mengurutkan kandidat berdasarkan relevansi dan views tanpa API atau dependency baru.

**Tech Stack:** Python 3.10+, stdlib, yt-dlp JSON metadata, Django test runner.

## Global Constraints

- Kandidat YouTube harus memiliki `view_count >= 100_000`.
- Metadata `view_count` kosong atau tidak valid harus ditolak.
- Query berita tetap diprioritaskan; query fallback cukup bertema AI.
- Kandidat tetap harus memiliki audio dengan `max_volume > -50 dB` pada jendela render.
- Jika YouTube gagal atau tidak ada kandidat yang lolos, pipeline tetap menggunakan Pexels + musik CC0.
- Tidak menambah API key, dependency, database, atau dashboard setting.
- Output tetap disimpan di `output/YYYY-MM-DD/`.

---

### Task 1: Filter and Rank Viral AI Footage

**Files:**
- Modify: `src/footage.py:145-405`
- Modify: `tests/test_footage.py`

**Interfaces:**
- Consumes: yt-dlp JSON field `view_count`.
- Produces: `_search_youtube()` candidates containing integer `view_count`; `search_and_download_news_video(..., min_views=100_000)`.

- [ ] **Step 1: Add failing metadata parsing test**

```python
import json


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
```

- [ ] **Step 2: Run metadata test and verify RED**

Run: `.venv/bin/python manage.py test tests.test_footage.FootageAudioTest.test_search_youtube_keeps_view_count -v 2`

Expected: FAIL because `_search_youtube` currently drops `view_count`.

- [ ] **Step 3: Preserve minimal view metadata**

In `_search_youtube`, parse without inventing a default that could pass the filter:

```python
view_count = info.get("view_count")
try:
    view_count = int(view_count) if view_count is not None else None
except (TypeError, ValueError):
    view_count = None

videos.append({
    "title": title,
    "url": url,
    "duration": int(duration),
    "view_count": view_count,
})
```

- [ ] **Step 4: Add failing threshold, ranking, and fallback-query tests**

Update existing mocked candidates in `test_search_skips_silent_candidate` to include `"view_count": 100000`.

```python
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
```

- [ ] **Step 5: Run focused tests and verify RED**

Run: `.venv/bin/python manage.py test tests.test_footage.FootageAudioTest.test_search_requires_100k_views_and_prefers_more_views tests.test_footage.FootageAudioTest.test_search_accepts_exactly_100k_views tests.test_footage.FootageAudioTest.test_search_rejects_low_or_missing_views_before_download tests.test_footage.FootageAudioTest.test_search_adds_generic_ai_queries -v 2`

Expected: FAIL because candidates are not filtered/ranked by views and generic AI queries do not exist.

- [ ] **Step 6: Implement the minimal filter and ranking**

Add the parameter and generic queries:

```python
def search_and_download_news_video(
    title=None,
    keywords=None,
    out_dir=None,
    min_duration=15,
    max_duration=3600,
    clip_seconds=90,
    source_url=None,
    audio_duration=None,
    min_views=100_000,
):
    # existing setup
    for query in ("viral AI", "artificial intelligence", "AI technology"):
        if query not in queries:
            queries.append(query)
```

Filter before adding to `pool` and include views in the tie-break:

```python
view_count = v.get("view_count")
if not isinstance(view_count, int) or view_count < min_views:
    continue
v["score"] = _relevance(v["title"], match_words)
pool.setdefault(v["url"], v)

candidates = sorted(
    pool.values(),
    key=lambda v: (-v["score"], -v["view_count"], v["duration"]),
)
```

Update candidate logs to include `v["view_count"]`.

- [ ] **Step 7: Verify Task 1 and commit**

Run: `.venv/bin/python manage.py test tests.test_footage -v 2`

Run: `.venv/bin/python manage.py test tests -v 1`

Run: `git diff --check`

Expected: all tests PASS with clean output.

```bash
git add src/footage.py tests/test_footage.py
git commit -m "feat: require viral AI footage views"
```

### Task 2: Deploy and Verify VPS Behavior

**Files:**
- Modify only if verification exposes a scoped defect.

**Interfaces:**
- Consumes: approved Task 1 commit.
- Produces: active VPS service with minimum-view filtering and preserved fallback behavior.

- [ ] **Step 1: Verify worktree before deployment**

Run: `.venv/bin/python manage.py test tests -v 1`

Run: `git diff --check`

Expected: 0 failures; clean system check and no whitespace errors.

- [ ] **Step 2: Back up and deploy exact changed files**

Back up current production copies under `/var/backups/aipreneurNews/20260808-viral-ai-100k/`, then deploy only:

```text
src/footage.py
tests/test_footage.py
```

Compare SHA-256 hashes between worktree and production for both files.

- [ ] **Step 3: Verify production and restart service**

Run: `.venv/bin/python manage.py test tests -v 1`

Run: `systemctl restart aipreneur-news.service`

Run: `systemctl is-active aipreneur-news.service`

Expected: tests have 0 failures and service prints `active`.

- [ ] **Step 4: Verify filter from logs or a focused production test**

Run the focused footage suite on production and confirm candidates below 100.000 views and missing view counts never reach `_download_youtube`.

Do not trigger another full render unless the focused verification exposes a discrepancy; the filter acts before the already-verified download/render path.
