from __future__ import annotations

import html
import json
import logging
import os
import re
from typing import List
from pathlib import Path

import anthropic

from .models import NewsItem

logger = logging.getLogger(__name__)


class AIWriterError(RuntimeError):
    pass


def _format_ig_caption(
    *,
    title: str,
    description: str,
    tags: list[str],
    source: str | None = None,
    link: str | None = None,
) -> str:
    tag_words = []
    if source:
        tag_words.append(source.lower())
    tag_words.extend(tags[:6] if tags else [])
    tag_words.extend(["berita", "beritaAI", "teknologi"])
    hashtags = " ".join([f"#{w.replace(' ', '')}" for w in dict.fromkeys(tag_words) if w])

    parts = [title.strip()]
    if description and description.strip():
        parts.append(description.strip())

    src_lines = []
    if source:
        src_lines.append(f"📰 Sumber: {source}")
    if link:
        src_lines.append(f"🔗 {link}")
    if src_lines:
        parts.append("\n".join(src_lines))

    if hashtags:
        parts.append(hashtags)
    return "\n\n".join(parts)


def _serialize_news(items: List[NewsItem]) -> str:
    lines = []
    for idx, item in enumerate(items):
        lines.append(
            f"{idx}. Source: {item.source}\n"
            f"Title: {item.title}\n"
            f"Summary: {item.summary}\n"
            f"Link: {item.link}\n"
            f"Published: {item.pub_date.isoformat()}"
        )
    return "\n\n".join(lines)


def _extract_json(response_text: str) -> dict:
    # Accept both clean JSON and JSON wrapped in fences.
    match = re.search(r"\{[\s\S]*\}", response_text)
    if not match:
        raise AIWriterError("No JSON object found in Claude response.")
    raw_json = match.group(0)
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise AIWriterError(f"Invalid JSON from Claude: {exc}") from exc


def generate_script(
    news_items: List[NewsItem],
    prompt_file: str,
    *,
    api_key: str | None = None,
    model: str = "claude-3-5-sonnet-20240620",
    max_tokens: int = 1800,
) -> dict:
    import requests
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv(os.path.expanduser("~/api/.env"))

    if not api_key:
        api_key = os.getenv("API_KEY_9ROUTER") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise AIWriterError("API Key tidak ditemukan. Pastikan ANTHROPIC_API_KEY atau API_KEY_9ROUTER telah diset.")

    prompt_template = Path(prompt_file).read_text(encoding="utf-8")
    prompt = str(prompt_template).replace("[ISI DARI SCRAPER]", _serialize_news(news_items))

    # If the model is a 9router model (usually contains '/' or is specified by the user)
    is_9router = "/" in model or model.startswith("ollama-") or model.startswith("hermes-") or "claude-opus" in model

    if is_9router:
        base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:20128/v1")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a creative news producer for YouTube Indonesian audience."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.4,
            "stream": False
        }
        try:
            logger.info(f"Mengirim permintaan ke 9router ({base_url}) dengan model: {model}")
            res = requests.post(f"{base_url}/chat/completions", json=data, headers=headers, timeout=60)
            res.raise_for_status()
            res_json = res.json()
            response_text = res_json["choices"][0]["message"]["content"]
        except Exception as exc:
            raise AIWriterError(f"Gagal memanggil 9router API: {exc}") from exc
    else:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.4,
            system="You are a creative news producer for YouTube Indonesian audience.",
            messages=[{"role": "user", "content": prompt}],
        )
        text_parts = []
        for block in message.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
        response_text = "".join(text_parts)
        
    if not response_text:
        raise AIWriterError("Claude tidak mengembalikan teks.")

    payload = _extract_json(response_text)
    required_keys = {
        "selected_index",
        "title",
        "hook",
        "script_voiceover",
        "description_text",
        "keywords",
        "thumbnail_text",
        "description",
        "tags",
    }
    missing = required_keys - set(payload.keys())
    if missing:
        raise AIWriterError(f"Claude response missing fields: {sorted(missing)}")

    payload.setdefault("description", "")
    payload.setdefault("tags", [])
    payload.setdefault("ig_caption", "")
    selected_index = int(payload.get("selected_index", 0))
    source = None
    link = None
    if 0 <= selected_index < len(news_items):
        source = news_items[selected_index].source
        link = news_items[selected_index].link
    payload.setdefault("source_url", link)
    payload.setdefault(
        "ig_caption",
        _format_ig_caption(
            title=payload.get("title", "Berita AI Hari Ini"),
            description=payload.get("description", ""),
            tags=payload.get("tags", []),
            source=source,
            link=link,
        ),
    )
    return payload


def _clean_headline(text: str, max_len: int = 80) -> str:
    """Decode entities and trim to a whole-word headline (never cut mid-word)."""
    text = " ".join(html.unescape(text or "").split())
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return f"{cut}…"


NEWLINE = chr(10)


def get_default_script(news_items: List[NewsItem], prompt_file: str) -> dict:
    """Script cadangan saat LLM tidak tersedia.

    Semua kalimat yang ditulis sendiri di sini berbahasa Indonesia. Judul dan
    ringkasan aslinya tetap Inggris karena menerjemahkan butuh model bahasa;
    field `language` menandai itu supaya jelas di dashboard dan history.
    """
    if not news_items:
        raise AIWriterError("Tidak ada berita untuk dipilih.")
    chosen = news_items[0]
    headline = _clean_headline(chosen.title)
    summary = _clean_headline(chosen.summary, 220)
    source = chosen.source

    # Judul asli dipertahankan utuh: menerjemahkannya butuh LLM (lihat generate_script).
    judul = headline
    inti = summary or "Perkembangan terbaru di dunia kecerdasan buatan."
    deskripsi_singkat = (
        f"Kabar terbaru dari {source}. {inti} "
        "Simak rangkumannya dalam video singkat ini."
    )

    script = {
        "selected_index": 0,
        "title": judul,
        "description_text": deskripsi_singkat,
        "hook": "Update AI terbaru yang perlu kamu tahu hari ini.",
        "script_voiceover": (
            f"Halo, ini kabar terbaru dunia kecerdasan buatan dari {source}. "
            f"{inti} "
            "Menarik, kan? Simak terus AIPreneur News untuk update AI setiap hari."
        ),
        "keywords": ["AI", "kecerdasan buatan", "teknologi", source.lower()],
        "thumbnail_text": "Kabar AI Hari Ini",
        "description": (
            deskripsi_singkat
            + f"{NEWLINE}{NEWLINE}Sumber: {source}{NEWLINE}{chosen.link}"
            + f"{NEWLINE}{NEWLINE}#AI #KecerdasanBuatan #Teknologi"
        ),
        "tags": ["AI", "kecerdasan buatan", "teknologi", "indonesia", source.lower()],
        "source_url": chosen.link,
        "source_item": chosen.to_dict(),
        "language": "id-fallback",
    }
    script["ig_caption"] = _format_ig_caption(
        title=judul,
        description=deskripsi_singkat,
        tags=script["tags"],
        source=source,
        link=chosen.link,
    )
    return script
