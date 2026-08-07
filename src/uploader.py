from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _load_credentials(client_secrets: str, token_cache: str) -> Credentials:
    creds = None
    token_path = Path(token_cache)
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if not Path(client_secrets).exists():
        raise FileNotFoundError(f"Client secrets tidak ada: {client_secrets}")

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload_to_youtube(
    *,
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    client_secrets: str,
    token_cache: str,
    category_id: str = "25",
    privacy_status: str = "public",
    thumbnail_path: Path | None = None,
) -> dict:
    creds = _load_credentials(client_secrets, token_cache)
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags[:10],
            "categoryId": category_id,
        },
        "status": {"privacyStatus": privacy_status},
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )
    response = request.execute()
    video_id = response.get("id")

    if thumbnail_path and thumbnail_path.exists() and video_id:
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path)),
            ).execute()
        except Exception as exc:
            logger.warning("Gagal upload thumbnail: %s", exc)

    return response

