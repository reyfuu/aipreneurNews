from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

THUMB_SIZE = (1280, 720)
# Beberapa titik dicoba lalu dipilih yang paling "berisi"; frame tunggal sering
# kena layar hitam atau transisi.
SAMPLE_RATIOS = (0.12, 0.25, 0.38, 0.52, 0.66, 0.8)
MIN_FRAME_TIME = 0.5


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


def _frame_score(frame) -> float:
    """Skor frame: detail tinggi tapi pencahayaan tidak ekstrem."""
    gray = frame.mean(axis=2) if frame.ndim == 3 else frame
    mean = float(gray.mean())
    detail = float(gray.std())
    # Frame nyaris hitam/putih polos dihukum, meski std-nya kebetulan tinggi.
    exposure = 1.0 - abs(mean - 128.0) / 128.0
    return detail * max(0.0, exposure)


def grab_video_frame(video_path: Path, *, frame_time: float | None = None):
    """Ambil frame paling informatif dari video sebagai PIL Image. None bila gagal."""
    try:
        from moviepy import VideoFileClip
    except ImportError:
        logger.warning("moviepy tidak tersedia, thumbnail tidak bisa ambil frame video.")
        return None

    clip = None
    try:
        clip = VideoFileClip(str(video_path))
        duration = clip.duration or 0
        if not duration:
            return None
        limit = max(0.0, duration - 0.2)

        if frame_time is not None:
            times = [min(frame_time, limit)]
        else:
            times = []
            for ratio in SAMPLE_RATIOS:
                t = min(max(MIN_FRAME_TIME, duration * ratio), limit)
                if t not in times:
                    times.append(t)

        best_frame = None
        best_score = -1.0
        best_time = None
        for t in times:
            try:
                frame = clip.get_frame(t)
            except Exception:
                continue
            score = _frame_score(frame)
            if score > best_score:
                best_frame, best_score, best_time = frame, score, t

        if best_frame is None:
            return None
        logger.info("Frame thumbnail dari detik %.1f (skor %.1f)", best_time or 0, best_score)
        return Image.fromarray(best_frame).convert("RGB")
    except Exception as exc:
        logger.warning("Gagal ambil frame dari %s: %s", video_path, exc)
        return None
    finally:
        if clip is not None:
            try:
                clip.close()
            except Exception:
                pass


def _cover_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Skala lalu potong tengah supaya mengisi penuh tanpa distorsi."""
    target_w, target_h = size
    src_w, src_h = image.size
    if not src_w or not src_h:
        return Image.new("RGB", size, (16, 32, 24))
    scale = max(target_w / src_w, target_h / src_h)
    new_size = (max(1, round(src_w * scale)), max(1, round(src_h * scale)))
    resized = image.resize(new_size, Image.LANCZOS)
    left = (new_size[0] - target_w) // 2
    top = (new_size[1] - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _side_scrim(base: Image.Image, text_width: int) -> None:
    """Gelapkan kolom kiri supaya judul terbaca di atas frame apa pun."""
    width, height = base.size
    scrim = Image.new("RGBA", (width, 1), (0, 0, 0, 0))
    fade_end = min(width, int(text_width * 1.25))
    for x in range(width):
        if x <= text_width:
            alpha = 205
        elif x < fade_end:
            alpha = int(205 * (1 - (x - text_width) / max(1, fade_end - text_width)))
        else:
            alpha = 0
        scrim.putpixel((x, 0), (0, 0, 0, alpha))
    base.alpha_composite(scrim.resize((width, height)), (0, 0))


def _compose_background(
    *, video_path: Path | None, template_path: Path | None, frame_time: float | None
) -> tuple[Image.Image, Image.Image | None, str]:
    """Kembalikan (latar 16:9, frame asli untuk panel, sumber latar)."""
    if video_path is not None and Path(video_path).exists():
        frame = grab_video_frame(Path(video_path), frame_time=frame_time)
        if frame is not None:
            from PIL import ImageFilter

            backdrop = _cover_crop(frame, THUMB_SIZE).filter(ImageFilter.GaussianBlur(22))
            return backdrop, frame, "video_frame"

    if template_path is not None and Path(template_path).exists():
        return _cover_crop(Image.open(template_path).convert("RGB"), THUMB_SIZE), None, "template"

    return Image.new("RGB", THUMB_SIZE, (13, 32, 24)), None, "solid"


def render_thumbnail(
    *,
    text: str,
    template_path: Path | None,
    out_path: Path,
    font_path: str | None = None,
    video_path: Path | None = None,
    frame_time: float | None = None,
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = THUMB_SIZE

    backdrop, frame, source = _compose_background(
        video_path=video_path, template_path=template_path, frame_time=frame_time
    )
    logger.info("Thumbnail memakai latar: %s", source)
    base = backdrop.convert("RGBA")

    # Frame portrait ditempel utuh di kanan; judul mendapat kolom kirinya sendiri.
    panel_right = 0
    if frame is not None:
        panel = frame.copy()
        panel.thumbnail((int(width * 0.46), height), Image.LANCZOS)
        panel_x = width - panel.size[0]
        panel_y = (height - panel.size[1]) // 2
        base.alpha_composite(panel.convert("RGBA"), (panel_x, panel_y))
        panel_right = panel_x

    margin = 60
    text_area = (panel_right - margin * 2) if panel_right else (width - margin * 2)
    text_area = max(320, text_area)
    _side_scrim(base, text_area + margin)

    draw = ImageDraw.Draw(base)
    text = " ".join((text or "").split()) or "Berita AI Hari Ini"

    # Turunkan ukuran font sampai muat maksimal 4 baris di kolom kiri.
    font = _choose_font(76, font_path)
    lines = _wrap_text(text, font, text_area, draw)
    for font_size in (76, 68, 60, 54, 48, 42):
        font = _choose_font(font_size, font_path)
        lines = _wrap_text(text, font, text_area, draw)
        if len(lines) <= 4:
            break
    lines = lines[:4]
    block = chr(10).join(lines)

    _, top, _, bottom = draw.multiline_textbbox(
        (0, 0), block, font=font, align="left", spacing=12
    )
    y = max(margin, (height - (bottom - top)) // 2 - top)

    for dx in (-3, 0, 3):
        for dy in (-3, 0, 3):
            if dx or dy:
                draw.multiline_text(
                    (margin + dx, y + dy), block, font=font, fill=(0, 0, 0),
                    align="left", spacing=12,
                )
    draw.multiline_text(
        (margin, y), block, font=font, fill=(255, 221, 51), align="left", spacing=12
    )

    base.convert("RGB").save(out_path)
    return out_path
