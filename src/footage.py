from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


def _ytdlp_cmd():
    """Return yt-dlp args, preferring venv install."""
    venv_ytdlp = Path(sys.executable).parent / "yt-dlp"
    if venv_ytdlp.exists():
        return [str(venv_ytdlp)]
    return [sys.executable, "-m", "yt_dlp"]


# --- Pexels helpers (fallback) ---

def _pick_clip_file(video_data, *, prefer_portrait=False):
    files = video_data.get("video_files", [])
    if not files:
        return None
    landscape = []
    portrait = []
    for f in files:
        w = int(f.get("width", 0) or 0)
        h = int(f.get("height", 0) or 0)
        if w <= 0 or h <= 0:
            continue
        (landscape if w >= h else portrait).append(f)
    preferred = portrait if prefer_portrait else landscape
    candidates = preferred or landscape or portrait or files
    candidates = [f for f in candidates if int(f.get("width", 0) or 0) > 0]
    if not candidates:
        return None
    candidates = sorted(
        candidates,
        key=lambda f: int(f.get("width", 0) or 0) * int(f.get("height", 0) or 0),
        reverse=True,
    )
    return candidates[0].get("link")


def _download_file(url, out_path):
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as fh:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                fh.write(chunk)


def download_pexels_footage(
    keywords,
    count=3,
    out_dir=None,
    *,
    preferred_orientation="portrait",
    api_key=None,
):
    _DEFAULT_PEXELS = "563492ad6f917000010000015407d57053e144a9b6c1664d4361537b"
    api_key = api_key or os.getenv("PEXELS_API_KEY") or _DEFAULT_PEXELS
    if not api_key:
        logger.warning("PEXELS_API_KEY tidak diset. Skip footage download.")
        return []

    out_dir = Path(out_dir) if out_dir else Path("output/footage")
    out_dir.mkdir(parents=True, exist_ok=True)

    headers = {"Authorization": api_key}
    used: set[str] = set()
    clip_urls: list[str] = []

    orientations = [preferred_orientation]
    if preferred_orientation not in ("landscape", "portrait"):
        orientations = ["portrait", "landscape"]
    orientations.append("mixed")

    for kw in (keywords or ["news"]):
        for orientation in orientations:
            params = {"query": kw, "per_page": 10}
            if orientation in ("landscape", "portrait"):
                params["orientation"] = orientation
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                params=params,
                headers=headers,
                timeout=30,
            )
            if resp.status_code != 200:
                continue
            for video in resp.json().get("videos", []):
                url = _pick_clip_file(video, prefer_portrait=(orientation != "landscape"))
                if url and url not in used and url not in clip_urls:
                    clip_urls.append(url)
                if len(clip_urls) >= count:
                    break
            if len(clip_urls) >= count:
                break
        if len(clip_urls) >= count:
            break

    downloaded: list[Path] = []
    for url in clip_urls:
        if len(downloaded) >= count:
            break
        out_path = out_dir / f"footage_{len(downloaded)+1}.mp4"
        try:
            _download_file(url, out_path)
            downloaded.append(out_path)
            used.add(url)
        except Exception as exc:
            logger.warning("Gagal download footage: %s", exc)
    return downloaded


# --- YouTube search & download via yt-dlp ---

def _run_ytdlp(args, timeout=120):
    try:
        cmd = _ytdlp_cmd() + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result
    except FileNotFoundError:
        logger.warning("yt-dlp tidak ditemukan. Install: pip install yt-dlp")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp timeout")
        return None


def _search_youtube(query, max_results=5):
    """Search YouTube and return parsed video info list."""
    result = _run_ytdlp(
        [
            f"ytsearch{max_results}:{query}",
            "-j",
            "--skip-download",
            "--no-playlist",
            "--no-write-sub",
            "--no-write-auto-sub",
            "--extractor-args",
            "youtube:player_client=android,web",
        ],
        timeout=60,
    )
    if not result or result.returncode != 0:
        logger.warning("yt-dlp search gagal: %s", result.stderr[:200] if result else "")
        return []

    videos = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            info = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        duration = info.get("duration") or 0
        view_count = info.get("view_count")
        try:
            view_count = int(view_count) if view_count is not None else None
        except (TypeError, ValueError):
            view_count = None
        url = info.get("webpage_url") or info.get("url")
        title = info.get("title")
        if duration and url and title:
            videos.append({
                "title": title,
                "url": url,
                "duration": int(duration),
                "view_count": view_count,
            })
    return videos


def _download_youtube(url, out_path, clip_seconds=None):
    """Download a YouTube video to out_path (without extension, yt-dlp adds it).

    When clip_seconds is set, only the opening section is fetched so that long
    news videos (streams, podcasts) download fast and still supply a clip + audio
    for the white box.
    """
    out_path = Path(out_path)
    stem = out_path.parent / out_path.stem
    args = [
        url,
        "-f",
        "bestvideo[height<=720]+bestaudio[ext=m4a]/best[height<=720]/best",
        "-o",
        str(stem) + ".%(ext)s",
        "--no-playlist",
        "--merge-output-format",
        "mp4",
        "--extractor-args",
        "youtube:player_client=android,web",
    ]
    if clip_seconds:
        args += [
            "--download-sections",
            f"*0-{int(clip_seconds)}",
            "--force-keyframes-at-cuts",
        ]
    result = _run_ytdlp(args, timeout=180)
    if not result or result.returncode != 0:
        logger.warning("yt-dlp download gagal: %s", result.stderr[:300] if result else "")
        return None

    found = sorted(
        stem.parent.glob(stem.name + ".*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if found:
        return found[0]
    return None


def _audio_max_volume(path, duration=None):
    try:
        command = ["ffmpeg", "-hide_banner", "-i", str(path)]
        if duration is not None:
            command += ["-t", str(duration)]
        command += ["-af", "volumedetect", "-vn", "-f", "null", "-"]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", result.stderr)
    return float(match.group(1)) if match else None


def _has_audible_audio(path, threshold_db=-50.0, duration=None):
    volume = _audio_max_volume(path, duration=duration)
    return volume is not None and volume > threshold_db


_MATCH_STOPWORDS = {
    "news", "update", "video", "latest", "breaking", "report", "reportedly",
    "says", "said", "this", "that", "with", "from", "your", "will", "have",
    "first", "more", "over", "into", "about", "here", "just", "make", "made",
    "what", "when", "where", "they", "their", "them", "para", "yang", "untuk",
    "dari", "dengan", "adalah", "dalam", "akan", "ini", "itu", "juga",
}


def _match_words(title=None, keywords=None):
    """Significant words from the news title/keywords used to score footage relevance."""
    words: set[str] = set()
    sources = [title or ""] + list(keywords or [])
    for src in sources:
        for w in re.findall(r"[a-z0-9]{4,}", str(src).lower()):
            if w not in _MATCH_STOPWORDS:
                words.add(w)
    return words


def _relevance(candidate_title, match_words):
    ct = (candidate_title or "").lower()
    return sum(1 for w in match_words if w in ct)


_GENERIC_KEYWORDS = {"ai", "technology", "tech", "news", "update", "the verge ai", "verge"}


def _focus_query(title, n=5):
    """A short, specific search query from the most meaningful title words."""
    words = [
        w for w in re.findall(r"[A-Za-z0-9]+", title or "")
        if len(w) >= 3 and w.lower() not in _MATCH_STOPWORDS
    ]
    return " ".join(words[:n])


def _rank_keywords(keywords):
    """Specific multi-word keywords first; ultra-generic ones (ai, technology) last."""
    seen = list(dict.fromkeys(k for k in (keywords or []) if k and k.strip()))

    def score(k):
        kl = k.lower().strip()
        wc = len(kl.split())
        specific = kl not in _GENERIC_KEYWORDS and wc >= 2
        return (1 if specific else 0, wc)

    return sorted(seen, key=score, reverse=True)


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
    """Cari video berita dari YouTube yang RELEVAN dengan judul, lalu download.

    Kandidat dari semua query dikumpulkan lalu di-skor berdasarkan berapa banyak
    kata judul berita yang muncul di judul video; yang paling relevan dipilih
    dengan urutan ranking: relevansi → prioritas query spesifik → views menurun →
    durasi menaik. Sumber berita YouTube umumnya panjang, jadi
    max_duration longgar dan hanya potongan awal (clip_seconds) yang di-download.
    """
    out_dir = Path(out_dir) if out_dir else Path("output/footage")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Story-specific queries win tie-breaks over generic AI searches.
    specific_queries: list[str] = []
    focus = _focus_query(title) or (title or "").strip()
    if focus:
        specific_queries.append(focus)
        specific_queries.append(f"{focus} news")
    for kw in _rank_keywords(keywords)[:3]:
        q = f"{kw} news"
        if q not in specific_queries:
            specific_queries.append(q)
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

    match_words = _match_words(title, keywords)

    # Pool candidates across queries, de-duped by URL.
    pool: dict[str, dict] = {}
    for query_priority, query_group in enumerate((specific_queries, generic_queries)):
        for query in query_group:
            for v in _search_youtube(query, max_results=8):
                if not (min_duration <= v["duration"] <= max_duration):
                    continue
                view_count = v.get("view_count")
                if not isinstance(view_count, int) or view_count < min_views:
                    continue
                v["score"] = _relevance(v["title"], match_words)
                v["query_priority"] = query_priority
                pool.setdefault(v["url"], v)

    if not pool:
        return None

    candidates = sorted(
        pool.values(),
        key=lambda v: (-v["score"], v["query_priority"], -v["view_count"], v["duration"]),
    )
    best_score = candidates[0]["score"]
    logger.info(
        "Footage kandidat: %d (skor tertinggi %d) untuk kata kunci %s",
        len(candidates), best_score, sorted(match_words)[:6],
    )

    for v in candidates:
        logger.info(
            "Coba footage (skor %d, %d views, %ds): %s",
            v["score"], v["view_count"], v["duration"], v["title"][:60],
        )
        out_stem = f"yt_{hash(v['url']) % 1000000:06d}"
        video_path = _download_youtube(v["url"], out_dir / out_stem, clip_seconds=clip_seconds)
        if video_path and video_path.stat().st_size > 5000:
            if _has_audible_audio(video_path, duration=audio_duration):
                logger.info("Footage terpilih dengan audio (skor %d): %s", v["score"], video_path)
                return video_path
            logger.info("Footage ditolak karena audio diam/tidak ada: %s", video_path)
            video_path.unlink(missing_ok=True)

    return None


# --- Main downloader (multi-source) ---

def download_news_video(
    title=None,
    keywords=None,
    source_url=None,
    out_dir=None,
    preferred_duration=60,
    pexels_api_key=None,
    preferred_orientation="portrait",
):
    """
    Cari & download video berita dari berbagai sumber:
    1. YouTube search (prioritas)
    2. Pexels fallback
    """
    out_dir = Path(out_dir) if out_dir else Path("output/footage")
    out_dir.mkdir(parents=True, exist_ok=True)

    kw_list = list(keywords) if keywords else []
    if title and title not in kw_list:
        kw_list.insert(0, title)

    # Grab a bit more than the target so the renderer has room to subclip.
    clip_seconds = int(preferred_duration) + 30

    video_path = search_and_download_news_video(
        title=title,
        keywords=kw_list,
        out_dir=out_dir,
        min_duration=15,
        max_duration=3600,
        clip_seconds=clip_seconds,
        source_url=source_url,
        audio_duration=preferred_duration,
    )

    if video_path:
        return [video_path]

    logger.info("YouTube tidak menghasilkan video, fallback ke Pexels...")
    return download_pexels_footage(
        keywords=kw_list or ["news", "headline"],
        count=3,
        out_dir=out_dir,
        preferred_orientation=preferred_orientation,
        api_key=pexels_api_key,
    )


# Legacy alias — keep backwards compat
def download_footage(keywords, count, out_dir, *, preferred_orientation="portrait", api_key=None):
    return download_pexels_footage(
        keywords=keywords,
        count=count,
        out_dir=out_dir,
        preferred_orientation=preferred_orientation,
        api_key=api_key,
    )
