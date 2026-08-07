from __future__ import annotations

from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont


def _choose_font(size: int, font_path: str | None) -> ImageFont.FreeTypeFont:
    candidates = []
    if font_path:
        candidates.append(font_path)
    base_dir = Path(__file__).resolve().parent.parent
    candidates.extend([
        str(base_dir / "templates" / "fonts" / "Montserrat-ExtraBold.ttf"),
        str(base_dir / "templates" / "fonts" / "Montserrat-Black.ttf"),
        str(base_dir / "templates" / "fonts" / "Montserrat-Bold.ttf"),
        str(base_dir / "templates" / "fonts" / "Poppins-Bold.ttf"),
        "templates/fonts/Montserrat-ExtraBold.ttf",
        "templates/fonts/Montserrat-Black.ttf",
        "templates/fonts/Montserrat-Bold.ttf",
        "templates/fonts/Poppins-Bold.ttf",
        "Arial Bold",
        "Helvetica Bold",
        "Arial",
    ])
    for cand in candidates:
        try:
            p = Path(cand)
            if p.exists():
                return ImageFont.truetype(str(p.resolve()), size=size)
            else:
                return ImageFont.truetype(cand, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        width = draw.textlength(candidate, font=font)
        if width <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_thumbnail(*, text: str, template_path: Path, out_path: Path, font_path: str | None = None) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if template_path.exists():
        base = Image.open(template_path).convert("RGB")
    else:
        base = Image.new("RGB", (1280, 720), color=(20, 20, 20))

    # Dark overlay for readability
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 120))
    base = base.convert("RGBA")
    base.alpha_composite(overlay, (0, 0))
    draw = ImageDraw.Draw(base)
    draw = ImageDraw.Draw(base)
    w, h = base.size
    font = _choose_font(92, font_path)
    lines = _wrap_text(text, font, max_width=w - 120, draw=draw)
    # Keep at most 2 lines for thumbnail
    lines = lines[:2]
    text_block = "\n".join(lines)

    left, top, right, bottom = draw.multiline_textbbox((0, 0), text_block, font=font, align="center")
    text_w = right - left
    text_h = bottom - top
    x = max(20, (w - text_w) // 2)
    y = h // 2 - text_h // 2

    # shadow
    for dx in (-2, 2):
        for dy in (-2, 2):
            draw.multiline_text((x + dx, y + dy), text_block, font=font, fill="black", align="center")
    draw.multiline_text((x, y), text_block, font=font, fill="yellow", align="center")
    base.convert("RGB").save(out_path)
    return out_path
