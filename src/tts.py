from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts


async def _generate_audio(text: str, out_path: Path | str, voice: str) -> None:
    path_obj = Path(out_path)
    communicate = edge_tts.Communicate(text=text, voice=voice)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    await communicate.save(str(path_obj))


def generate_voiceover(text: str, out_path: Path | str, voice: str = "id-ID-GadisNeural") -> Path:
    path_obj = Path(out_path)
    text = (text or "").strip()
    if not text:
        raise ValueError("script_voiceover kosong.")
    if len(text) > 2500:
        # Edge-TTS bisa memproses teks panjang, tapi kita batasi supaya stabil.
        text = text[:2450]
    asyncio.run(_generate_audio(text, path_obj, voice))
    return path_obj

