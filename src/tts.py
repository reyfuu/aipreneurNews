from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts


async def _generate_audio(text: str, out_path: Path, voice: str) -> None:
    communicate = edge_tts.Communicate(text=text, voice=voice)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    await communicate.save(str(out_path))


def generate_voiceover(text: str, out_path: Path, voice: str = "id-ID-GadisNeural") -> Path:
    text = (text or "").strip()
    if not text:
        raise ValueError("script_voiceover kosong.")
    if len(text) > 2500:
        # Edge-TTS bisa memproses teks panjang, tapi kita batasi supaya stabil.
        text = text[:2450]
    asyncio.run(_generate_audio(text, out_path, voice))
    return out_path

