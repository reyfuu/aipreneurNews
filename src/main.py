from __future__ import annotations

import argparse
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

import random
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

from .ai_writer import AIWriterError, generate_script, get_default_script
from .renderer import render_video
from .scraper import scrape_recent_news
from .footage import download_news_video
from .thumbnail import render_thumbnail
from .tts import generate_voiceover
from .uploader import upload_to_youtube
from .utils import append_jsonl, ensure_dir, load_json, now_local, now_utc, setup_logger, write_json


logger = setup_logger("news_clip_bot")


_VIDEO_STOP_WORDS = {
    "dan",
    "atau",
    "yang",
    "ini",
    "itu",
    "dan",
    "the",
    "a",
    "an",
    "of",
    "for",
    "to",
    "in",
    "on",
    "at",
    "with",
    "from",
    "by",
    "as",
    "its",
    "it",
    "is",
    "are",
    "was",
    "were",
    "be",
    "menjadi",
    "di",
    "yang",
    "ke",
    "yang",
    "pada",
    "para",
    "untuk",
    "dengan",
    "tanpa",
    "dari",
    "oleh",
    "ini",
    "itu",
    "juga",
}


def _merge_keywords(
    raw_keywords: list[str],
    *,
    selected_news_title: str = "",
    selected_news_summary: str = "",
    selected_news_source: str = "",
) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    title_tokens = re.findall(r"[A-Za-z0-9]{3,}", selected_news_title.lower())
    summary_tokens = re.findall(r"[A-Za-z0-9]{3,}", selected_news_summary.lower())
    title_chunks = [
        selected_news_title[:45].strip(),
        selected_news_title[:30].strip(),
        " ".join(title_tokens[:2]),
    ]

    def add_keyword(value: str) -> None:
        if not isinstance(value, str):
            return
        clean = " ".join(value.lower().split())
        if not clean or clean in seen:
            return
        if clean in _VIDEO_STOP_WORDS:
            return
        merged.append(clean)
        seen.add(clean)

    for value in raw_keywords:
        add_keyword(value)
    for keyword in title_chunks:
        add_keyword(keyword)
    for token in title_tokens:
        if token not in _VIDEO_STOP_WORDS:
            add_keyword(token)
    if selected_news_source:
        add_keyword(selected_news_source)
    for token in summary_tokens[:10]:
        if token not in _VIDEO_STOP_WORDS:
            add_keyword(token)
    return merged[:8]


def _parse_size(value: object) -> tuple[int, int] | None:
    if isinstance(value, (tuple, list)) and len(value) == 2:
        try:
            width = int(value[0])
            height = int(value[1])
            if width > 0 and height > 0:
                return (width, height)
        except (TypeError, ValueError):
            return None
        return None

    if not isinstance(value, str):
        return None
    normalized = value.lower().strip().replace("x", "x")
    if not normalized:
        return None
    parts = normalized.replace(",", "x").split("x")
    if len(parts) != 2:
        return None
    try:
        width = int(parts[0].strip())
        height = int(parts[1].strip())
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return (width, height)


def run_pipeline(
    *,
    skip_upload: bool = False,
    force_news: bool = False,
    run_date: str | None = None,
    on_progress: Callable[[str, str, int | None], None] | None = None,
) -> dict:
    if on_progress is None:
        on_progress = lambda *_args, **_kwargs: None

    load_dotenv()

    settings = load_json(Path("config/settings.json"))
    output_root = Path(settings["paths"]["output_dir"])
    feeds_file = Path(settings["paths"]["feeds_file"])
    prompts_file = Path(settings["paths"]["prompts_file"])
    template_video = Path(settings["paths"]["template_video"])
    template_thumb = Path(settings["paths"]["template_thumbnail"])

    tz = settings.get("timezone", "Asia/Jakarta")
    if run_date:
        parsed = datetime.fromisoformat(run_date)
        if parsed.tzinfo is None:
            now = parsed.replace(tzinfo=ZoneInfo(tz))
        else:
            now = parsed
    else:
        now = now_local(tz)

    date_dir = output_root / now.strftime("%Y-%m-%d")
    ensure_dir(date_dir)
    ensure_dir(date_dir / "footage")

    logger.info("Start pipeline for %s", now.isoformat())
    on_progress("Memulai pipeline", "setup", 5)

    feed_cfg = settings.get("feeds", {})
    on_progress("Mengambil berita terbaru", "fetch_news", 15)
    news = scrape_recent_news(
        feeds_file,
        window_min_hours=feed_cfg.get("window_hours_min", 6),
        window_max_hours=feed_cfg.get("window_hours_max", 12),
        limit_per_source=feed_cfg.get("feed_limit_per_source", 8),
        top_n=feed_cfg.get("max_items_for_ai", 5),
    )

    if not news:
        raise RuntimeError(
            "Tidak ada berita dalam rentang 6-12 jam terakhir. "
            "Cek feed/timezone, atau ubah window di config/ settings.json"
        )

    news_payload = [n.to_dict() for n in news]

    logger.info("Total berita valid: %d", len(news))
    on_progress(f"Menemukan {len(news)} berita", "fetch_news", 25)

    try:
        script = generate_script(
            news,
            str(prompts_file),
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            model=os.getenv("ANTHROPIC_MODEL", "cc/claude-opus-4-7"),
        )
    except Exception as exc:
        logger.warning("AI gagal (%s), fallback script lokal dipakai.", exc)
        script = get_default_script(news, str(prompts_file))
        on_progress("AI gagal, memakai template naskah fallback", "generate_script", 35)
    else:
        on_progress("Naskah selesai dibuat", "generate_script", 35)

    script_path = date_dir / "script.json"
    script["candidate_news"] = news_payload
    script["created_at"] = now_utc().isoformat()
    try:
        source_idx = int(script.get("selected_index", 0))
    except (TypeError, ValueError):
        source_idx = 0
    selected_news = news[source_idx] if 0 <= source_idx < len(news) else news[0]
    script["keywords"] = _merge_keywords(
        list(script.get("keywords", []) or []),
        selected_news_title=getattr(selected_news, "title", ""),
        selected_news_summary=getattr(selected_news, "summary", ""),
        selected_news_source=getattr(selected_news, "source", ""),
    )
    write_json(script_path, script)
    ig_caption_path = date_dir / "ig_caption.txt"
    ig_caption_path.write_text(script.get("ig_caption", ""), encoding="utf-8")

    # Voiceover (skip jika pakai audio YouTube — di-render dari footage langsung)
    voiceover_path = date_dir / "voiceover.mp3"
    voiceover_script = script.get("script_voiceover", "")
    if voiceover_script:
        on_progress("Membuat voiceover", "voiceover", 45)
        generate_voiceover(
            voiceover_script,
            voiceover_path,
            voice=os.getenv("EDGE_TTS_VOICE", "id-ID-GadisNeural"),
        )
    else:
        voiceover_path.write_bytes(b"")
        on_progress("Audio dari footage YouTube", "voiceover", 45)

    footage_dir = date_dir / "footage"
    footage_keywords = script.get("keywords") or [script.get("title", "international news")]
    if isinstance(footage_keywords, str):
        footage_keywords = [footage_keywords]
    output_size = _parse_size(settings["pipeline"].get("output_size"))
    footage_orientation = "portrait"
    if output_size and output_size[0] > output_size[1]:
        footage_orientation = "landscape"

    selected_title = script.get("title", "")
    selected_url = ""
    try:
        src_idx = int(script.get("selected_index", 0))
        if 0 <= src_idx < len(news):
            selected_url = news[src_idx].link
    except (TypeError, ValueError):
        pass

    on_progress("Mencari video berita", "download_footage", 55)
    footage_paths = download_news_video(
        title=selected_title,
        keywords=footage_keywords,
        source_url=selected_url,
        out_dir=footage_dir,
        preferred_duration=settings["pipeline"].get("target_video_duration_sec", 60),
        preferred_orientation=footage_orientation,
    )
    music_dir = Path(settings["paths"]["background_music_dir"])
    music_files = list(music_dir.glob("*.mp3")) if music_dir.exists() else []
    music_path = random.choice(music_files) if music_files else None

    # Render
    on_progress("Membuat video final", "render_video", 75)
    final_video = date_dir / "final_video.mp4"
    render_video(
        script=script,
        base_template=template_video,
        voiceover_path=voiceover_path,
        footage_paths=footage_paths,
        music_path=music_path,
        output_size=output_size,
        audio_mode=settings["pipeline"].get("audio_mode", "music_only"),
        out_path=final_video,
        duration=settings["pipeline"].get("target_video_duration_sec", 60),
        music_volume=float(settings["pipeline"].get("music_volume", 0.2)),
        font_path=settings["paths"].get("font_path"),
    )

    # Thumbnail
    on_progress("Membuat thumbnail", "thumbnail", 90)
    thumb_path = date_dir / "thumbnail.png"
    render_thumbnail(
        text=script.get("thumbnail_text", "Berita Terbaru"),
        template_path=template_thumb,
        out_path=thumb_path,
        font_path=settings["paths"].get("font_path"),
    )

    source_idx = script.get("selected_index", 0)
    try:
        source_idx = int(source_idx)
    except (TypeError, ValueError):
        source_idx = 0
    source_name = None
    if 0 <= source_idx < len(news):
        source_name = news[source_idx].source

    youtube_id = None
    if not skip_upload and settings.get("upload", {}).get("enabled", False):
        on_progress("Upload ke YouTube", "upload", 95)
        upload_cfg = settings["upload"]
        response = upload_to_youtube(
            video_path=final_video,
            title=script.get("title", "Daily News Clip"),
            description=script.get("description", ""),
            tags=script.get("tags", []),
            client_secrets=os.getenv("YT_CLIENT_SECRETS", "config/client_secret.json"),
            token_cache=upload_cfg.get("token_cache", ".cache/youtube_token.json"),
            category_id=upload_cfg.get("category_id", "25"),
            privacy_status=upload_cfg.get("privacy_status", "public"),
            thumbnail_path=thumb_path,
        )
        youtube_id = response.get("id")
    on_progress("Menyimpan riwayat output", "finalizing", 98)

    history = {
        "run_at": now.isoformat(),
        "output_dir": str(date_dir),
        "script_file": str(script_path),
        "ig_caption_file": str(ig_caption_path),
        "video_file": str(final_video),
        "thumbnail_file": str(thumb_path),
        "video_id": youtube_id,
        "title": script.get("title"),
        "source": source_name,
    }
    append_jsonl(Path("output/history.jsonl"), history)

    logger.info("Pipeline selesai. Video: %s", final_video)
    return history


def run_scheduler() -> None:
    import schedule
    import time

    settings = load_json(Path("config/settings.json"))
    run_time = settings.get("scheduler", {}).get("time", "06:00")
    logger.info("Scheduler aktif: setiap hari pukul %s", run_time)
    schedule.every().day.at(run_time).do(lambda: run_pipeline(skip_upload=False))
    while True:
        schedule.run_pending()
        time.sleep(30)


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily News Clip Automation")
    parser.add_argument("--skip-upload", action="store_true", help="Skip upload YouTube")
    parser.add_argument("--run-once", action="store_true", help="Run pipeline immediately")
    parser.add_argument("--run-date", help="Run as if date is YYYY-MM-DD")
    parser.add_argument("--daemon", action="store_true", help="Run scheduler loop")
    args = parser.parse_args()

    if args.daemon:
        run_scheduler()
        return 0

    if args.run_once or not args.daemon:
        try:
            run_pipeline(skip_upload=args.skip_upload, run_date=args.run_date)
            return 0
        except Exception as exc:
            logger.error("Pipeline gagal: %s", exc)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
