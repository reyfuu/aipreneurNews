"""Publish Reels ke Instagram lewat Content Publishing API (Instagram Graph API).

Catatan penting soal cara kerja API-nya: Instagram tidak menerima upload byte
langsung. Kita memberi URL video, lalu server Meta yang mengunduh sendiri. Jadi
`output/<tanggal>/<video>.mp4` harus bisa diakses publik lewat HTTPS sebelum
langkah ini dipanggil (lihat `PUBLIC_BASE_URL` di .env).

Alur resmi: buat container -> tunggu status FINISHED -> publish.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from urllib.parse import quote, urljoin

import requests

logger = logging.getLogger(__name__)

DEFAULT_API_VERSION = "v25.0"
GRAPH_HOST = "https://graph.instagram.com"
# Batas caption Instagram; hashtag di luar 30 buah akan ditolak API.
CAPTION_LIMIT = 2200
MAX_HASHTAGS = 30


class InstagramPublishError(RuntimeError):
    """Gagal membuat, memproses, atau mempublikasikan container Instagram."""


def build_public_video_url(base_url: str, date: str, filename: str) -> str:
    """Bangun URL publik video dari base URL + endpoint output dashboard."""
    if not base_url:
        raise InstagramPublishError(
            "PUBLIC_BASE_URL belum diset. Instagram perlu URL publik untuk menarik video."
        )
    if not base_url.endswith("/"):
        base_url += "/"
    path = f"api/outputs/{quote(date)}/{quote(filename)}"
    url = urljoin(base_url, path)
    if not url.startswith("https://"):
        raise InstagramPublishError(
            f"URL video harus HTTPS agar diterima Instagram, dapat: {url}"
        )
    return url


def trim_caption(caption: str) -> str:
    """Pangkas caption ke batas Instagram dan buang hashtag berlebih."""
    text = (caption or "").strip()
    words = text.split(" ")
    hashtag_count = 0
    kept: list[str] = []
    for word in words:
        if word.startswith("#"):
            hashtag_count += 1
            if hashtag_count > MAX_HASHTAGS:
                continue
        kept.append(word)
    text = " ".join(kept)
    if len(text) > CAPTION_LIMIT:
        text = text[: CAPTION_LIMIT - 1].rstrip() + "…"
    return text


def _graph_url(api_version: str, path: str) -> str:
    return f"{GRAPH_HOST}/{api_version}/{path.lstrip('/')}"


def _post(url: str, data: dict, timeout: int) -> dict:
    try:
        response = requests.post(url, data=data, timeout=timeout)
    except requests.RequestException as exc:
        raise InstagramPublishError(f"Request ke Instagram gagal: {exc}") from exc
    return _parse_response(response)


def _get(url: str, params: dict, timeout: int) -> dict:
    try:
        response = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise InstagramPublishError(f"Request ke Instagram gagal: {exc}") from exc
    return _parse_response(response)


def _parse_response(response: requests.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not response.ok or "error" in payload:
        error = payload.get("error", {})
        message = error.get("message") or response.text[:300]
        code = error.get("code")
        raise InstagramPublishError(
            f"Instagram API error (HTTP {response.status_code}"
            f"{f', code {code}' if code else ''}): {message}"
        )
    return payload


def create_reel_container(
    *,
    ig_user_id: str,
    access_token: str,
    video_url: str,
    caption: str = "",
    share_to_feed: bool = True,
    cover_url: str | None = None,
    api_version: str = DEFAULT_API_VERSION,
    timeout: int = 60,
) -> str:
    data = {
        "media_type": "REELS",
        "video_url": video_url,
        "access_token": access_token,
        "share_to_feed": "true" if share_to_feed else "false",
    }
    if caption:
        data["caption"] = caption
    if cover_url:
        data["cover_url"] = cover_url

    payload = _post(_graph_url(api_version, f"{ig_user_id}/media"), data, timeout)
    container_id = payload.get("id")
    if not container_id:
        raise InstagramPublishError(f"Container ID tidak ada di respons: {payload}")
    logger.info("Container Instagram dibuat: %s", container_id)
    return str(container_id)


def wait_for_container(
    *,
    container_id: str,
    access_token: str,
    api_version: str = DEFAULT_API_VERSION,
    poll_interval: int = 10,
    max_wait_seconds: int = 300,
    timeout: int = 30,
    sleep=time.sleep,
) -> None:
    """Tunggu sampai container siap. Meta menyarankan polling maksimal 5 menit."""
    deadline = time.monotonic() + max_wait_seconds
    last_status = "UNKNOWN"
    while True:
        payload = _get(
            _graph_url(api_version, container_id),
            {"fields": "status_code,status", "access_token": access_token},
            timeout,
        )
        last_status = payload.get("status_code", "UNKNOWN")
        if last_status == "FINISHED":
            return
        if last_status in {"ERROR", "EXPIRED"}:
            raise InstagramPublishError(
                f"Container {container_id} berstatus {last_status}: {payload.get('status', '')}"
            )
        if time.monotonic() >= deadline:
            break
        logger.info("Container %s masih %s, menunggu...", container_id, last_status)
        sleep(poll_interval)
    raise InstagramPublishError(
        f"Container {container_id} belum siap setelah {max_wait_seconds}s (status terakhir: {last_status})"
    )


def publish_container(
    *,
    ig_user_id: str,
    container_id: str,
    access_token: str,
    api_version: str = DEFAULT_API_VERSION,
    timeout: int = 60,
) -> str:
    payload = _post(
        _graph_url(api_version, f"{ig_user_id}/media_publish"),
        {"creation_id": container_id, "access_token": access_token},
        timeout,
    )
    media_id = payload.get("id")
    if not media_id:
        raise InstagramPublishError(f"Media ID tidak ada di respons: {payload}")
    return str(media_id)


def fetch_permalink(
    *,
    media_id: str,
    access_token: str,
    api_version: str = DEFAULT_API_VERSION,
    timeout: int = 30,
) -> str | None:
    try:
        payload = _get(
            _graph_url(api_version, media_id),
            {"fields": "permalink", "access_token": access_token},
            timeout,
        )
        return payload.get("permalink")
    except InstagramPublishError as exc:
        logger.warning("Gagal ambil permalink: %s", exc)
        return None


def publish_reel(
    *,
    video_url: str,
    caption: str = "",
    ig_user_id: str | None = None,
    access_token: str | None = None,
    share_to_feed: bool = True,
    cover_url: str | None = None,
    api_version: str = DEFAULT_API_VERSION,
    poll_interval: int = 10,
    max_wait_seconds: int = 300,
    timeout: int = 60,
    sleep=time.sleep,
) -> dict:
    """Publikasikan satu Reel. Mengembalikan dict berisi media_id dan permalink."""
    ig_user_id = ig_user_id or os.getenv("IG_USER_ID", "")
    access_token = access_token or os.getenv("IG_ACCESS_TOKEN", "")
    if not ig_user_id or not access_token:
        raise InstagramPublishError(
            "IG_USER_ID dan IG_ACCESS_TOKEN wajib diset untuk publish ke Instagram."
        )

    caption = trim_caption(caption)
    container_id = create_reel_container(
        ig_user_id=ig_user_id,
        access_token=access_token,
        video_url=video_url,
        caption=caption,
        share_to_feed=share_to_feed,
        cover_url=cover_url,
        api_version=api_version,
        timeout=timeout,
    )
    wait_for_container(
        container_id=container_id,
        access_token=access_token,
        api_version=api_version,
        poll_interval=poll_interval,
        max_wait_seconds=max_wait_seconds,
        timeout=timeout,
        sleep=sleep,
    )
    media_id = publish_container(
        ig_user_id=ig_user_id,
        container_id=container_id,
        access_token=access_token,
        api_version=api_version,
        timeout=timeout,
    )
    permalink = fetch_permalink(
        media_id=media_id, access_token=access_token, api_version=api_version, timeout=timeout
    )
    logger.info("Reel terbit: %s (%s)", media_id, permalink or "tanpa permalink")
    return {"media_id": media_id, "container_id": container_id, "permalink": permalink}


def _cli() -> int:
    """Publish ulang satu output yang sudah ada, untuk uji coba kredensial."""
    import argparse

    from dotenv import load_dotenv

    from .utils import load_json, setup_logger

    load_dotenv()
    setup_logger("instagram_publisher")

    parser = argparse.ArgumentParser(description="Publish output harian ke Instagram Reels")
    parser.add_argument("--date", required=True, help="Folder output, format YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Tampilkan URL & caption tanpa publish")
    args = parser.parse_args()

    settings = load_json(Path("config/settings.json"))
    ig_cfg = settings.get("instagram", {})
    date_dir = Path(settings["paths"]["output_dir"]) / args.date
    if not date_dir.is_dir():
        print(f"Folder output tidak ada: {date_dir}")
        return 1

    videos = sorted(date_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not videos:
        print(f"Tidak ada file .mp4 di {date_dir}")
        return 1

    caption_file = date_dir / "ig_caption.txt"
    caption = caption_file.read_text(encoding="utf-8") if caption_file.exists() else ""
    # Env menang atas settings.json; `or` menangani env yang diset tapi kosong.
    base_url = os.getenv("PUBLIC_BASE_URL") or ig_cfg.get("public_base_url", "")
    try:
        video_url = build_public_video_url(base_url, args.date, videos[0].name)
    except InstagramPublishError as exc:
        print(f"Konfigurasi belum lengkap: {exc}")
        return 1

    if args.dry_run:
        print(f"video_url : {video_url}")
        print(f"caption   : {trim_caption(caption)[:200]}")
        return 0

    try:
        result = publish_reel(
            video_url=video_url,
            caption=caption,
            share_to_feed=bool(ig_cfg.get("share_to_feed", True)),
            api_version=ig_cfg.get("api_version", DEFAULT_API_VERSION),
            poll_interval=int(ig_cfg.get("poll_interval_sec", 10)),
            max_wait_seconds=int(ig_cfg.get("max_wait_sec", 300)),
        )
    except InstagramPublishError as exc:
        print(f"Gagal publish: {exc}")
        return 1

    print(f"Berhasil: {result['permalink'] or result['media_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
