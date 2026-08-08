# Video History Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist completed story and footage identities in `output/history.jsonl`, skip them on later runs, and exit cleanly when no new content remains.

**Architecture:** Add a focused `src/content_history.py` module that tolerantly indexes JSONL history, normalizes story identity, hashes raw footage, scans legacy footage, and serializes pipeline runs. `src.footage` receives exclusion sets and reports every selected clip through an optional metadata list while preserving its existing return types. `src.main` filters/retries stories, passes footage exclusions, and appends completed or `no_new_content` rows.

**Tech Stack:** Python 3.10+, standard library (`json`, `hashlib`, `fcntl`, `contextlib`, `urllib.parse`), Django unittest runner, existing yt-dlp/MoviePy pipeline.

## Global Constraints

- Continue using `output/history.jsonl`; do not add a database, API, or dependency.
- Legacy rows without `status` are completed rows; malformed JSONL lines are warned and skipped.
- Exact normalized source URLs are the primary story identity; normalized-title token Jaccard similarity threshold is exactly `0.60`.
- Completed rows store every selected clip in `footage_items`, each with `provider`, `url`, `file`, and `sha256`.
- Used footage URLs are rejected before download; duplicate raw-file SHA-256 values are deleted and the next candidate is attempted.
- Scan retained `output/*/footage/` files once at run start to seed legacy footage hashes.
- If all stories or all otherwise-viable footage are duplicates, append `status: "no_new_content"` and do not render or upload.
- A concurrent trigger returns `status: "already_running"` and performs no pipeline work.
- Only a successful render creates a completed content identity. Upload failure still records that completed local video and the upload failure.
- Do not change 100,000-view filtering, relevance/query/view/duration ranking, audible-audio validation, or ordinary YouTube-to-Pexels failure fallback.
- Work in the existing isolated VPS worktree; preserve the production `.venv` and unrelated files.

---

### Task 1: Build the Tolerant History Index and Lock

**Files:**
- Create: `src/content_history.py`
- Create: `tests/test_content_history.py`

**Interfaces:**
- Produces: `HistoryIndex`, `normalize_url(value)`, `title_tokens(value)`, `titles_similar(left, right, threshold=0.60)`, `sha256_file(path)`, `load_history_index(history_path, output_root, logger=None)`, and `pipeline_lock(path)`.
- `HistoryIndex.story_seen(source_url="", title="") -> bool` checks exact URLs and title similarity.
- `HistoryIndex.footage_seen(url="", digest="") -> bool` checks exact normalized footage URLs and SHA-256 hashes.
- `pipeline_lock(path)` yields `True` to the lock holder and `False` to a concurrent caller.

- [ ] **Step 1: Write failing normalization and similarity tests**

```python
class ContentHistoryTest(TestCase):
    def test_normalize_url_removes_tracking_fragment_and_trailing_slash(self):
        value = "HTTPS://Example.com/story/?utm_source=rss&id=7#top"
        self.assertEqual(history.normalize_url(value), "https://example.com/story?id=7")

    def test_titles_similar_uses_jaccard_threshold(self):
        old = "OpenAI Rem Astra AI Ini Terlalu Bahaya"
        new = "OpenAI Rem Model AI Astra Terlalu Berbahaya"
        self.assertTrue(history.titles_similar(old, new, threshold=0.60))
        self.assertFalse(history.titles_similar(old, "Claude merilis fitur coding baru", threshold=0.60))
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `.venv/bin/python manage.py test tests.test_content_history.ContentHistoryTest.test_normalize_url_removes_tracking_fragment_and_trailing_slash tests.test_content_history.ContentHistoryTest.test_titles_similar_uses_jaccard_threshold -v 2`

Expected: ERROR because `src.content_history` does not exist.

- [ ] **Step 3: Implement URL and title identity**

```python
_TITLE_STOP_WORDS = {
    "a", "ai", "an", "and", "atau", "dan", "dari", "di", "in", "ini",
    "is", "itu", "ke", "model", "of", "on", "pada", "the", "to", "yang",
}

def normalize_url(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlsplit(value.strip())
    query = urlencode(sorted(
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ))
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, query, ""))

def title_tokens(value: str | None) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if token not in _TITLE_STOP_WORDS
    }

def titles_similar(left: str, right: str, threshold: float = 0.60) -> bool:
    left_tokens, right_tokens = title_tokens(left), title_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens) >= threshold
```

- [ ] **Step 4: Add failing tolerant-loader and legacy-scan tests**

```python
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
```

- [ ] **Step 5: Run the loader test and verify RED**

Run: `.venv/bin/python manage.py test tests.test_content_history.ContentHistoryTest.test_loader_keeps_valid_rows_skips_malformed_and_scans_legacy_footage -v 2`

Expected: FAIL because `HistoryIndex`, `sha256_file`, and `load_history_index` are missing.

- [ ] **Step 6: Implement the index and hashing**

```python
@dataclass
class HistoryIndex:
    source_urls: set[str] = field(default_factory=set)
    titles: list[str] = field(default_factory=list)
    footage_urls: set[str] = field(default_factory=set)
    footage_hashes: set[str] = field(default_factory=set)

    def story_seen(self, source_url: str = "", title: str = "") -> bool:
        normalized = normalize_url(source_url)
        return bool(
            (normalized and normalized in self.source_urls)
            or (title and any(titles_similar(title, old) for old in self.titles))
        )

    def footage_seen(self, url: str = "", digest: str = "") -> bool:
        normalized = normalize_url(url)
        return bool(
            (normalized and normalized in self.footage_urls)
            or (digest and digest in self.footage_hashes)
        )

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
```

`load_history_index` must read line by line, ignore rows with a non-completed explicit status, accept missing status as completed, index every `footage_items` entry, warn on malformed rows, and hash regular files matching `output_root.glob("*/footage/*")`. Catch `OSError` per legacy file so one disappearing file does not abort the load.

- [ ] **Step 7: Add a failing nonblocking lock test**

```python
def test_pipeline_lock_rejects_concurrent_holder(self):
    lock_path = self.output / "pipeline.lock"
    with history.pipeline_lock(lock_path) as first:
        with history.pipeline_lock(lock_path) as second:
            self.assertTrue(first)
            self.assertFalse(second)
```

- [ ] **Step 8: Implement the lock**

```python
@contextmanager
def pipeline_lock(path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
```

- [ ] **Step 9: Verify and commit Task 1**

Run: `.venv/bin/python manage.py test tests.test_content_history -v 2`

Run: `git diff --check`

Expected: all history tests pass and no whitespace errors.

```bash
git add src/content_history.py tests/test_content_history.py
git commit -m "feat: index completed content history"
```

---

### Task 2: Exclude and Report Used Footage

**Files:**
- Modify: `src/footage.py`
- Modify: `tests/test_footage.py`

**Interfaces:**
- Consumes: `normalize_url` and `sha256_file` from Task 1.
- Produces: `NoNewFootage`, plus optional keyword arguments on `search_and_download_news_video` and `download_news_video`: `used_footage_urls: set[str] | None`, `used_footage_hashes: set[str] | None`, and `selected_items: list[dict] | None`.
- Existing callers that omit the new arguments keep receiving `Path | None` from search and `list[Path]` from the main downloader.
- Each selected item has exactly `provider`, `url`, `file`, and `sha256`.

- [ ] **Step 1: Write the failing used-URL regression test**

```python
@mock.patch("src.footage._has_audible_audio", return_value=True)
@mock.patch("src.footage._download_youtube")
@mock.patch("src.footage._search_youtube")
def test_search_skips_used_url_before_download(self, search, download, audible):
    selected = self.tmp / "new.mp4"
    selected.write_bytes(b"new video" * 800)
    search.return_value = [
        {"title":"Used AI", "url":"https://example/used", "duration":60, "view_count":900000},
        {"title":"New AI", "url":"https://example/new", "duration":60, "view_count":800000},
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
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/bin/python manage.py test tests.test_footage.FootageAudioTest.test_search_skips_used_url_before_download -v 2`

Expected: ERROR because the new keyword arguments are unsupported.

- [ ] **Step 3: Implement URL exclusion and selected metadata**

Normalize `used_footage_urls` once. Keep the existing candidate sorting unchanged. Before `_download_youtube`, skip normalized URLs already used. After size and audio validation, calculate SHA-256, append this exact shape, and return the existing `Path`:

```python
selected_items.append({
    "provider": "youtube",
    "url": normalize_url(v["url"]),
    "file": str(video_path),
    "sha256": digest,
})
```

Raise `NoNewFootage("all YouTube footage candidates were already used")` only when an otherwise eligible pool was exhausted exclusively by used URLs or duplicate hashes. Ordinary download/audio/search failure continues to return `None` and use the existing Pexels fallback.

- [ ] **Step 4: Write the failing duplicate-hash regression test**

```python
@mock.patch("src.footage._has_audible_audio", return_value=True)
@mock.patch("src.footage._download_youtube")
@mock.patch("src.footage._search_youtube")
def test_search_deletes_duplicate_hash_and_tries_next(self, search, download, audible):
    duplicate = self.tmp / "duplicate.mp4"
    fresh = self.tmp / "fresh.mp4"
    duplicate.write_bytes(b"same bytes" * 800)
    fresh.write_bytes(b"fresh bytes" * 800)
    search.return_value = [
        {"title":"First", "url":"https://example/first", "duration":60, "view_count":900000},
        {"title":"Second", "url":"https://example/second", "duration":60, "view_count":800000},
    ]
    download.side_effect = [duplicate, fresh]

    result = footage.search_and_download_news_video(
        title="AI", out_dir=self.tmp,
        used_footage_hashes={sha256_file(duplicate)}, selected_items=[],
    )

    self.assertEqual(result, fresh)
    self.assertFalse(duplicate.exists())
```

- [ ] **Step 5: Run the hash test and verify RED, then implement it**

Run: `.venv/bin/python manage.py test tests.test_footage.FootageAudioTest.test_search_deletes_duplicate_hash_and_tries_next -v 2`

Expected: FAIL because duplicate hashes are not checked.

After a file passes size and audio checks, use `sha256_file(video_path)`. When used, unlink it and continue without appending metadata.

- [ ] **Step 6: Add Pexels metadata/hash coverage**

Add a test where `search_and_download_news_video` returns `None`, mocked `download_pexels_footage` returns one duplicate and one fresh file, and `download_news_video` returns only the fresh path while appending one `provider: "pexels"` item with empty `url`. Add a second test asserting all duplicate Pexels files raise `NoNewFootage`.

Implement post-download filtering over every Pexels path. Preserve the existing Pexels order. Delete newly downloaded duplicate files and include metadata for every retained file.

- [ ] **Step 7: Verify and commit Task 2**

Run: `.venv/bin/python manage.py test tests.test_footage -v 2`

Run: `.venv/bin/python manage.py test tests.test_content_history -v 1`

Run: `git diff --check`

Expected: all focused tests pass; ranking, 100k view, audio, and generic-query tests remain green.

```bash
git add src/footage.py tests/test_footage.py
git commit -m "feat: skip previously used footage"
```

---

### Task 3: Select a New Story and Persist Completed Identity

**Files:**
- Modify: `src/main.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `HistoryIndex`, `load_history_index`, `pipeline_lock`, `NoNewFootage`, and the Task 2 downloader arguments.
- Produces: completed history rows with `status`, story identity, and `footage_items`; operational results for `no_new_content` and `already_running`.
- Adds private helpers `_append_no_new_content(history_path, now, reason, on_progress) -> dict` and `_generate_unique_script(news, prompts_file, history_index) -> tuple[dict, object, list] | None`.

- [ ] **Step 1: Write a failing source-URL filtering test**

Add a pipeline test with two `_NewsItem` values. Write a completed history row for the first URL inside the configured temporary output root. Assert the writer receives only the second news item, rendering occurs once, and the returned completed row contains the second `source_url`.

```python
self.assertEqual([item.link for item in generate_script.call_args.args[0]], ["https://example/new"])
self.assertEqual(result["source_url"], "https://example/new")
self.assertEqual(result["status"], "completed")
```

- [ ] **Step 2: Run the source filtering test and verify RED**

Run: `.venv/bin/python manage.py test tests.test_pipeline.PipelineTest.test_pipeline_skips_completed_source_url -v 2`

Expected: FAIL because history is not loaded before writer selection.

- [ ] **Step 3: Load history and filter exact story URLs**

Use `history_path = output_root / "history.jsonl"`. Immediately after scraping:

```python
history_index = load_history_index(history_path, output_root, logger=logger)
news = [item for item in news if not history_index.story_seen(source_url=item.link)]
if not news:
    return _append_no_new_content(history_path, now, "all stories were already used", on_progress)
```

Ensure `news_payload` is built only after this filtering.

- [ ] **Step 4: Write a failing legacy-title retry test**

Mock `generate_script` with two results: the first generated title resembles a legacy history title at or above `0.60` and selects index 0; the second selects the remaining story with a distinct title. Assert two writer calls, the first selected item is absent from the second call, and only the second story is rendered.

- [ ] **Step 5: Run the retry test and verify RED, then implement the bounded retry**

Run: `.venv/bin/python manage.py test tests.test_pipeline.PipelineTest.test_pipeline_retries_after_legacy_title_duplicate -v 2`

Expected: FAIL because generated-title duplicates are not retried.

Implement `_generate_unique_script` with a local copy of candidate news:

```python
def _generate_unique_script(news, prompts_file, history_index):
    remaining = list(news)
    while remaining:
        try:
            script = generate_script(
                remaining,
                str(prompts_file),
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                model=os.getenv("ANTHROPIC_MODEL", "cc/claude-opus-4-7"),
            )
        except Exception as exc:
            logger.warning("AI gagal (%s), fallback script lokal dipakai.", exc)
            script = get_default_script(remaining, str(prompts_file))
        try:
            selected_index = int(script.get("selected_index", 0))
        except (TypeError, ValueError):
            selected_index = 0
        if not 0 <= selected_index < len(remaining):
            selected_index = 0
        selected_news = remaining[selected_index]
        if not history_index.story_seen(title=script.get("title", "")):
            return script, selected_news, remaining
        logger.info("Lewati topik yang sudah pernah dibuat: %s", script.get("title", ""))
        remaining.pop(selected_index)
    return None
```

- [ ] **Step 6: Write failing no-content short-circuit tests**

Add one test for all story URLs used and one where `download_news_video` raises `NoNewFootage`. Both must assert:

```python
self.assertEqual(result["status"], "no_new_content")
render_video.assert_not_called()
upload_to_youtube.assert_not_called()
```

Also assert one JSONL row with `status`, `run_at`, and reason `"all stories were already used"` or `"all footage was already used"` is appended.

- [ ] **Step 7: Implement no-content outcomes**

```python
def _append_no_new_content(history_path, now, reason, on_progress):
    row = {"run_at": now.isoformat(), "status": "no_new_content", "reason": reason}
    append_jsonl(history_path, row)
    on_progress("Tidak ada konten baru", "no_new_content", 100)
    return row
```

Catch only `NoNewFootage` around the footage selection call and return the helper result. Ordinary errors keep their existing behavior.

- [ ] **Step 8: Pass exclusions and persist selected identities**

Create `selected_items = []`, then call:

```python
footage_paths = download_news_video(
    title=selected_title,
    keywords=footage_keywords,
    source_url=selected_news.link,
    out_dir=footage_dir,
    preferred_duration=settings["pipeline"].get("target_video_duration_sec", 60),
    preferred_orientation=footage_orientation,
    used_footage_urls=history_index.footage_urls,
    used_footage_hashes=history_index.footage_hashes,
    selected_items=selected_items,
)
```

After successful render, extend the existing history row with:

```python
"status": "completed",
"source_url": selected_news.link,
"source_title": selected_news.title,
"title_key": " ".join(sorted(title_tokens(script.get("title", "")))),
"footage_items": selected_items,
```

Append to `history_path`, not hard-coded `Path("output/history.jsonl")`.

- [ ] **Step 9: Preserve identity when upload fails**

Add a test where rendering succeeds and `upload_to_youtube` raises. Require a completed row with `upload_status: "failed"`, `upload_error` containing the exception text, and the content identity fields. The pipeline returns that row rather than regenerating this completed local video later.

Wrap only upload in `try/except Exception`; on success set `upload_status: "uploaded"`, on skipped/disabled set `upload_status: "skipped"`, and on failure log the error and continue to history append.

- [ ] **Step 10: Add and implement serialization coverage**

Patch `src.main.pipeline_lock` to yield `False` and assert `run_pipeline` returns exactly:

```python
{"status": "already_running"}
```

Scraping, writer, render, and upload mocks must remain uncalled. Add `from functools import wraps`, then keep the existing function body intact with this wrapper:

```python
def _serialized_pipeline(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        settings = load_json(Path("config/settings.json"))
        output_root = Path(settings["paths"]["output_dir"])
        with pipeline_lock(output_root / "pipeline.lock") as acquired:
            if not acquired:
                return {"status": "already_running"}
            return func(*args, **kwargs)
    return wrapped
```

Add `@_serialized_pipeline` immediately above the existing `run_pipeline` declaration; do not change its signature.

- [ ] **Step 11: Verify and commit Task 3**

Run: `.venv/bin/python manage.py test tests.test_pipeline -v 2`

Run: `.venv/bin/python manage.py test tests.test_content_history tests.test_footage -v 1`

Run: `.venv/bin/python manage.py test tests -v 1`

Run: `git diff --check`

Expected: all tests pass with a clean Django system check.

```bash
git add src/main.py tests/test_pipeline.py
git commit -m "feat: prevent duplicate pipeline output"
```

---

### Task 4: Deploy, Seed Legacy Hashes, and Verify VPS

**Files:**
- Deploy reviewed versions of `src/content_history.py`, `src/footage.py`, `src/main.py`, `tests/test_content_history.py`, `tests/test_footage.py`, and `tests/test_pipeline.py`.
- Modify no other production files unless a reviewed fix explicitly requires it.

**Interfaces:**
- Consumes: approved Task 1-3 commits.
- Produces: active VPS service with persistent story and footage deduplication.

- [ ] **Step 1: Verify the complete feature worktree**

Run: `.venv/bin/python manage.py test tests -v 1`

Run: `git diff --check`

Expected: zero failures, expected existing skips only, clean system check, and no whitespace errors.

- [ ] **Step 2: Inspect legacy content without mutating it**

Record counts only:

```bash
wc -l output/history.jsonl
find output -path '*/footage/*' -type f | wc -l
```

Do not rewrite old JSONL rows and do not rename/delete legacy footage. Compatibility is provided by the tolerant loader and runtime scan.

- [ ] **Step 3: Back up and deploy exact files**

Back up existing production copies under:

```text
/var/backups/aipreneurNews/20260808-video-history-deduplication/
```

Copy only the six reviewed files listed for this task. Compare SHA-256 hashes between the approved worktree and production for every file.

- [ ] **Step 4: Verify production behavior**

Run: `.venv/bin/python manage.py test tests.test_content_history -v 2`

Run: `.venv/bin/python manage.py test tests.test_footage -v 1`

Run: `.venv/bin/python manage.py test tests.test_pipeline -v 1`

Run: `.venv/bin/python manage.py test tests -v 1`

Run: `systemctl restart aipreneur-news.service`

Run: `systemctl is-active aipreneur-news.service`

Run: `curl --retry 8 --retry-connrefused --retry-delay 1 -sS http://127.0.0.1:8008/api/health/`

Expected: all tests pass, service is `active`, and health contains `"status": "ok"`.

- [ ] **Step 5: Run one controlled duplicate test through the test suite, not production rendering**

Do not trigger a live full render or upload. The mocked pipeline tests must prove the first used story is skipped, the next story is chosen, duplicate footage is rejected, and exhausted content exits before render/upload.

- [ ] **Step 6: Merge after independent review**

After task reviews and final whole-branch review are clean, fast-forward the feature branch into VPS `main`. Re-run the full suite, restart the service, check `active`, check health, and confirm production/worktree SHA-256 equality for all six deployed files. Preserve the host-owned external worktree and pre-existing `.venv`.
