# Video History Deduplication Design

**Date:** 2026-08-08

**Status:** Approved design

**Scope:** Prevent the pipeline from producing the same story or reusing the same source footage more than once.

## Goal

Use the existing `output/history.jsonl` as the durable content registry. Before a run renders or uploads anything, the pipeline must reject:

1. a news story that has already produced a completed video; and
2. a footage source that has already appeared in a completed video.

If the first choice is a duplicate, the pipeline tries the next eligible story or footage candidate. If no new content remains, it exits cleanly with `status: "no_new_content"` and does not render or upload.

## Non-goals

- No database or external API is added.
- No retention window: completed content remains excluded for the lifetime of the history file.
- No semantic embedding service or LLM call solely for deduplication.
- Existing ranking, 100,000-view filtering, audio validation, and legal Pexels fallback remain intact except for excluding already-used content.

## History Schema

Successful rows retain all current fields and add:

```json
{
  "status": "completed",
  "source_url": "https://publisher.example/story",
  "source_title": "Original feed title",
  "title_key": "normalized generated title",
  "footage_provider": "youtube",
  "footage_url": "https://www.youtube.com/watch?v=...",
  "footage_file": "output/2026-08-08/footage/yt_123456.mp4",
  "footage_sha256": "..."
}
```

Legacy rows without `status` are treated as completed. Missing new fields are valid and must not break history loading.

When a run finds no eligible content, append an operational row containing `run_at`, `status: "no_new_content"`, and a short `reason`. These rows never contribute URLs, hashes, or titles to the exclusion sets.

Malformed JSONL lines are skipped with a warning; valid lines continue to load.

## Story Deduplication

At pipeline start, load completed history rows and build:

- exact normalized `source_url` values;
- generated title keys and legacy `title` values.

Candidate feed items whose source URL already exists are removed before the writer runs. This is the primary and exact check for all new history rows.

For legacy history that lacks `source_url`, the writer result is checked against prior generated titles. Titles are normalized to lowercase alphanumeric tokens, punctuation is removed, and Indonesian/English filler words are ignored. Two titles are considered the same topic when their token Jaccard similarity is at least `0.60`. If the selected result matches legacy history, remove its selected feed item and run the writer again against the remaining candidates. The loop is bounded by the number of feed candidates.

If no feed candidates remain, return `no_new_content` before voiceover, footage download, rendering, thumbnail generation, or upload.

## Footage Deduplication

Build two exclusion sets from completed history:

- exact normalized `footage_url` values;
- `footage_sha256` values.

For backward compatibility, scan existing `output/*/footage/` files once per run and add their SHA-256 values to the hash exclusion set. This lets retained legacy footage participate even though older history rows did not store its URL.

During candidate selection:

1. skip a YouTube candidate before download when its URL is already used;
2. download the next eligible candidate using the existing rank order;
3. hash the downloaded raw footage;
4. if its hash is already used, delete that new duplicate file and continue;
5. after audio validation succeeds, expose the selected provider, URL, file path, and hash to the pipeline for the final history row.

Pexels keeps its existing role when YouTube has no usable candidate. Its downloaded files are also checked by SHA-256. If candidates existed but every viable candidate was excluded only because it was already used, return `no_new_content` rather than rendering a repeated clip.

Existing downloader return behavior remains backward compatible for current callers and tests; metadata is exposed through an optional result path/interface used by `src.main`.

## Run Serialization

Use a process-level file lock under `output/` for the full pipeline run. A concurrent trigger returns `status: "already_running"` instead of reading stale history and producing the same selection twice. The lock is released on success or exception.

## Data Flow

1. Acquire pipeline lock.
2. Load tolerant history index and legacy footage hashes.
3. Scrape feed and remove exact source-URL duplicates.
4. Generate a script; reject legacy-title duplicates and retry with remaining news.
5. Search ranked footage while excluding used URLs and hashes.
6. If no new story or footage remains, append `no_new_content` and exit cleanly.
7. Render, thumbnail, and optionally upload as today.
8. Only after a successful render, append the completed row with story and footage identities.
9. Release the lock.

## Error Handling

- Missing history file means an empty history.
- One malformed JSON line is logged and ignored.
- Missing legacy footage files are ignored.
- A file that disappears during hashing is logged and skipped.
- Existing YouTube/Pexels failure fallback behavior remains unchanged.
- A render failure does not create a completed history identity. If rendering succeeds but upload fails, still record the content identity as completed together with the upload failure, because a finished local video already exists and must not be regenerated.

## Tests

Add focused tests proving:

- current and legacy history rows load safely;
- malformed lines do not discard valid rows;
- an exact source URL is removed before writer selection;
- a legacy similar title is rejected at the `0.60` threshold and the next story is chosen;
- used footage URLs are skipped before download;
- duplicate raw-file hashes are deleted and the next footage candidate is tried;
- legacy `output/*/footage/` hashes are included;
- successful history rows contain all new identity fields;
- exhausted story or footage candidates return `no_new_content` without render/upload;
- concurrent execution returns `already_running`;
- existing pipeline, footage ranking, minimum-view, audio, and fallback tests continue to pass.

## Deployment

Implement in an isolated VPS worktree, run focused and full test suites, obtain an independent review, back up changed production files, deploy exact reviewed files, compare hashes, restart `aipreneur-news.service`, verify health, and then fast-forward the feature branch into VPS `main`.
