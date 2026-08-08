# Expanded Viral AI Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Perluas pencarian footage viral minimal 100.000 views ke semua kategori video bertema AI, termasuk Claude dan open-source AI.

**Architecture:** Pertahankan pipeline, ranking, filter views, validasi audio, dan fallback yang sudah ada. Ubah hanya daftar `generic_queries` di `src/footage.py` dan regression test yang memverifikasi daftar tersebut.

**Tech Stack:** Python 3.10+, yt-dlp, Django test runner.

## Global Constraints

- Pencarian berita spesifik tetap dijalankan sebelum query AI umum.
- Query umum harus persis: `viral AI`, `AI tools`, `AI tutorial`, `AI podcast`, `AI robots`, `AI demo`, `generative AI`, `ChatGPT`, `Claude AI`, `open source AI`, `artificial intelligence`.
- Semua kandidat YouTube tetap wajib memiliki `view_count >= 100_000`.
- Metadata views kosong atau invalid tetap ditolak.
- Video viral non-AI tidak boleh digunakan.
- Ranking tetap: relevansi berita, prioritas query spesifik, views tertinggi, durasi terpendek.
- Validasi audio dan fallback Pexels + musik CC0 tidak berubah.
- Tidak menambah YouTube API, API key, dependency, konfigurasi, database, atau dashboard setting.

---

### Task 1: Expand Generic AI Query Coverage

**Files:**
- Modify: `src/footage.py:300-345`
- Modify: `tests/test_footage.py:125-160`

**Interfaces:**
- Consumes: existing `generic_queries` group inside `search_and_download_news_video`.
- Produces: the exact ordered list of 11 general AI searches.

- [ ] **Step 1: Strengthen the query regression test first**

Replace the three individual assertions in `test_search_adds_generic_ai_queries` with an ordered expected list:

```python
def test_search_adds_generic_ai_queries(self, search):
    self.assertIsNone(footage.search_and_download_news_video(title="AI news", out_dir=self.tmp))
    queries = [call.args[0] for call in search.call_args_list]
    expected = [
        "viral AI",
        "AI tools",
        "AI tutorial",
        "AI podcast",
        "AI robots",
        "AI demo",
        "generative AI",
        "ChatGPT",
        "Claude AI",
        "open source AI",
        "artificial intelligence",
    ]
    generic = [query for query in queries if query in expected]
    self.assertEqual(generic, expected)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `.venv/bin/python manage.py test tests.test_footage.FootageAudioTest.test_search_adds_generic_ai_queries -v 2`

Expected: FAIL because the current list contains only `viral AI`, `artificial intelligence`, and `AI technology`.

- [ ] **Step 3: Replace only the generic query list**

```python
generic_queries = [
    "viral AI",
    "AI tools",
    "AI tutorial",
    "AI podcast",
    "AI robots",
    "AI demo",
    "generative AI",
    "ChatGPT",
    "Claude AI",
    "open source AI",
    "artificial intelligence",
]
```

Remove `AI technology`; do not modify filtering, ranking, audio, or fallback code.

- [ ] **Step 4: Verify and commit Task 1**

Run: `.venv/bin/python manage.py test tests.test_footage -v 2`

Run: `.venv/bin/python manage.py test tests -v 1`

Run: `git diff --check`

Expected: all tests PASS with clean system check.

```bash
git add src/footage.py tests/test_footage.py
git commit -m "feat: expand viral AI search queries"
```

### Task 2: Deploy and Verify VPS

**Files:**
- Modify only if verification exposes a scoped defect.

**Interfaces:**
- Consumes: approved Task 1 commit.
- Produces: active VPS service with the expanded query list.

- [ ] **Step 1: Verify worktree**

Run: `.venv/bin/python manage.py test tests -v 1`

Run: `git diff --check`

Expected: 0 failures and no whitespace errors.

- [ ] **Step 2: Back up and deploy exact files**

Back up production copies under `/var/backups/aipreneurNews/20260808-expanded-ai-queries/`, then deploy only:

```text
src/footage.py
tests/test_footage.py
```

Compare SHA-256 hashes between worktree and production.

- [ ] **Step 3: Verify production**

Run: `.venv/bin/python manage.py test tests -v 1`

Run: `.venv/bin/python manage.py test tests.test_footage -v 1`

Run: `systemctl restart aipreneur-news.service`

Run: `systemctl is-active aipreneur-news.service`

Run: `curl --retry 8 --retry-connrefused --retry-delay 1 -sS http://127.0.0.1:8008/api/health/`

Expected: tests pass, service is `active`, and health response contains `"status": "ok"`.

Do not trigger a full render; query selection is covered before the already-verified download/render path.
