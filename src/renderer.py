from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np
from PIL import Image, ImageFilter

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ColorClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    concatenate_audioclips,
    concatenate_videoclips,
    vfx,
)

from src.footage import _has_audible_audio

logger = logging.getLogger(__name__)

_DEFAULT_CANVAS = (1080, 1920)
_BRAND_NAME = "AIPreneur News"
_FONT_FALLBACKS = [
    "templates/fonts/Montserrat-ExtraBold.ttf",
    "templates/fonts/Montserrat-Black.ttf",
    "templates/fonts/Montserrat-Bold.ttf",
    "templates/fonts/Poppins-Bold.ttf",
    "Arial Bold",
    "Arial",
    "Helvetica Bold",
    "Helvetica",
    "DejaVuSans-Bold",
    "DejaVuSans",
]


def _resolve_font(custom_path: str | Path | None = None) -> str:
    from PIL import ImageFont
    candidates = []
    if custom_path:
        candidates.append(str(custom_path))
    
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
                ImageFont.truetype(str(p.resolve()), 32)
                return str(p.resolve())
            else:
                ImageFont.truetype(cand, 32)
                return cand
        except Exception:
            continue
    return _FONT_FALLBACKS[0]


_CAPTION_FONT = _resolve_font()
_CAPTION_COLOR = "white"
_CAPTION_STROKE_COLOR = "black"
_CAPTION_STROKE_WIDTH = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_size(size):
    if size is None:
        return None
    if isinstance(size, (tuple, list)) and len(size) == 2:
        try:
            w, h = int(size[0]), int(size[1])
        except (TypeError, ValueError):
            return None
        if w > 0 and h > 0:
            return (w, h)
    return None


# White box (footage area) bounds inside the 1080x1920 template.
_WHITE_BOX_BOUNDS = {"x1": 0, "y1": 410, "x2": 1079, "y2": 1087}


def _white_box_mask_clip(size, duration):
    """MoviePy mask: 1 (opaque) everywhere, 0 (transparent) over the white box.

    Attaching this as the template's mask makes the box a real see-through hole
    so the footage behind it shows — a bare RGBA frame from image_transform does
    NOT (MoviePy ignores the alpha channel), which is why the box rendered white.
    """
    w, h = size
    arr = np.ones((h, w), dtype=float)
    b = _WHITE_BOX_BOUNDS
    y1, y2 = max(0, b["y1"]), min(h, b["y2"])
    x1, x2 = max(0, b["x1"]), min(w, b["x2"])
    arr[y1:y2, x1:x2] = 0.0
    return ImageClip(arr, is_mask=True).with_duration(max(1, int(duration)))


def _load_base_video(template_path, duration, target_size=None):
    if template_path.exists():
        try:
            clip = VideoFileClip(str(template_path))
            target = max(1, int(duration))
            if not clip.duration or clip.duration <= 0:
                base = clip.with_duration(target)
            elif clip.duration >= target:
                base = clip.subclipped(0, target)
            else:
                repeat_count = max(2, math.ceil(target / clip.duration))
                looped = concatenate_videoclips([clip] * repeat_count, method="compose")
                base = looped.subclipped(0, target)

            resized = _resize_fill_clip(base, target_size) if target_size else base
            size = target_size or resized.size
            # Real transparent hole where the white box is, so footage shows through.
            return resized.with_mask(_white_box_mask_clip(size, target))
        except Exception as exc:
            logger.warning("Template video gagal dimuat: %s", exc)
    fallback_size = target_size or _DEFAULT_CANVAS
    return ColorClip(fallback_size, color=(15, 15, 15)).with_duration(duration)


def _resize_fill_clip(clip, target_size):
    tw, th = target_size
    if not hasattr(clip, "size") or clip.size is None:
        return clip
    sw, sh = clip.size
    if sw == 0 or sh == 0:
        return clip
    scale = max(tw / sw, th / sh)
    resized = clip.resized(new_size=(int(sw * scale), int(sh * scale)))
    cx = max(0, int((resized.w - tw) / 2))
    cy = max(0, int((resized.h - th) / 2))
    return resized.cropped(x1=cx, y1=cy, width=tw, height=th)


def _apply_fade(clip, fade_in=0.0, fade_out=0.0):
    if fade_in > 0:
        clip = clip.with_effects([vfx.FadeIn(fade_in)])
    if fade_out > 0:
        clip = clip.with_effects([vfx.FadeOut(fade_out)])
    return clip


# ---------------------------------------------------------------------------
# Ken Burns (slow zoom) effect
# ---------------------------------------------------------------------------

def _ken_burns(clip, zoom=0.06):
    w, h = clip.size
    dur = clip.duration if clip.duration else 1.0

    def _zoom_frame(get_frame, t):
        frame = get_frame(t)
        progress = min(1.0, max(0.0, t / dur)) if dur > 0 else 0.0
        scale = 1.0 + (progress * zoom)
        nw, nh = int(w * scale), int(h * scale)
        if nw == w and nh == h:
            return frame
        img = Image.fromarray(np.uint8(frame))
        img = img.resize((nw, nh), Image.LANCZOS)
        left = max(0, (nw - w) // 2)
        top = max(0, (nh - h) // 2)
        img = img.crop((left, top, left + w, top + h))
        return np.array(img)

    return clip.transform(_zoom_frame)


# ---------------------------------------------------------------------------
# Footage loading with Ken Burns + crossfade
# ---------------------------------------------------------------------------

def _load_footage_clip(clip_path, duration, target_size):
    clip = VideoFileClip(str(clip_path))
    if not clip.duration or clip.duration <= 0:
        base = _resize_fill_clip(clip.with_duration(max(1, duration)), target_size)
        return _ken_burns(base)
    if clip.duration >= duration:
        prepared = clip.subclipped(0, duration)
    else:
        count = max(2, math.ceil(duration / clip.duration))
        prepared = concatenate_videoclips([clip] * count, method="compose").subclipped(0, duration)
    filled = _resize_fill_clip(prepared, target_size)
    return _ken_burns(filled)


def _build_footage_background(footage_paths, duration, target_size, crossfade=0.4):
    paths = [Path(p) for p in footage_paths if Path(p).exists()]
    if not paths:
        return None

    clips = []
    for p in paths[:4]:
        try:
            clips.append(_load_footage_clip(p, duration, target_size))
        except Exception as exc:
            logger.warning("Footage gagal dimuat: %s", exc)

    if not clips:
        return None

    if len(clips) == 1:
        return _apply_fade(clips[0], fade_in=0.3, fade_out=0.4).with_duration(duration)

    per = max(3.0, duration / len(clips))
    positioned = []
    current = 0.0
    for i, c in enumerate(clips):
        seg = c.subclipped(0, min(per + crossfade, c.duration if c.duration else per))
        if i == 0:
            seg = seg.with_effects([vfx.FadeOut(crossfade)])
        elif i == len(clips) - 1:
            seg = seg.with_effects([vfx.FadeIn(crossfade)])
        else:
            seg = seg.with_effects([vfx.FadeIn(crossfade), vfx.FadeOut(crossfade)])
        seg = seg.with_start(current)
        positioned.append(seg)
        current += per

    comp = CompositeVideoClip(positioned, size=target_size)
    if comp.duration and comp.duration > duration:
        comp = comp.subclipped(0, duration)
    return comp.with_duration(duration)


# ---------------------------------------------------------------------------
# Overlays
# ---------------------------------------------------------------------------

def _text_overlay_clip(
    text,
    duration,
    position,
    fontsize,
    start=0.0,
    color=_CAPTION_COLOR,
    stroke_color=_CAPTION_STROKE_COLOR,
    stroke_width=_CAPTION_STROKE_WIDTH,
    max_width=1700,
    canvas_size=None,
    bg=False,
    bg_opacity=0.40,
):
    font_name = _CAPTION_FONT
    try:
        clip = TextClip(
            font=font_name,
            text=text,
            font_size=fontsize,
            color=color,
            method="caption",
            size=(max_width, None),
            text_align="center",
            stroke_color=stroke_color,
            stroke_width=stroke_width,
        )
        clip = clip.with_duration(duration).with_start(start).with_position(position)
        clip = _apply_fade(clip, fade_in=0.15, fade_out=0.15)
    except Exception:
        try:
            fallback_font = _resolve_font()
            clip = TextClip(
                font=fallback_font,
                text=text,
                font_size=fontsize - 4,
                color=color,
                method="caption",
                size=(max_width, None),
                text_align="center",
                stroke_color=stroke_color,
                stroke_width=max(1, stroke_width - 1),
            )
            clip = clip.with_duration(duration).with_start(start).with_position(position)
            clip = _apply_fade(clip, fade_in=0.15, fade_out=0.15)
        except Exception:
            clip = TextClip(
                text=text,
                font_size=max(20, fontsize - 8),
                color=color,
                method="label",
            )
            clip = clip.with_duration(duration).with_start(start).with_position(position)
            clip = _apply_fade(clip, fade_in=0.15, fade_out=0.15)

    if bg:
        pad = 30
        try:
            tw = min(max_width, clip.size[0] + pad)
            th = clip.size[1] + pad
            bg_bar = ColorClip((tw, th), color=(0, 0, 0))
            bg_bar = bg_bar.with_duration(duration).with_start(start).with_opacity(bg_opacity)
            if isinstance(position, tuple) and len(position) == 2:
                bg_bar = bg_bar.with_position((position[0] - pad // 2, position[1] - pad // 2))
            else:
                bg_bar = bg_bar.with_position(position)
            return CompositeVideoClip([bg_bar, clip], size=canvas_size)
        except Exception:
            return clip
    return clip


def _readability_gradient(size, duration):
    w, h = size
    overlay_h = int(h * 0.50)

    def _make_frame(t):
        arr = np.zeros((overlay_h, w, 4), dtype=np.uint8)
        for row in range(overlay_h):
            alpha = int(140 * (row / overlay_h))
            arr[row, :] = [0, 0, 0, alpha]
        return arr

    grad = ColorClip((w, overlay_h), color=(0, 0, 0)).with_duration(duration)
    try:
        grad = grad.transform(lambda g, t: _make_frame(t))
    except Exception:
        grad = grad.with_opacity(0.30)
    return grad.with_position(("center", h - overlay_h))


def _build_branding_bar(size, duration, source=None, brand=_BRAND_NAME):
    w, h = size
    bar_h = 100
    bottom_gap = 14  # lift the bar off the frame edge so descenders aren't clipped
    bar = ColorClip((w, bar_h), color=(6, 6, 6)).with_duration(duration).with_opacity(0.85)
    accent = ColorClip((w, 3), color=(255, 200, 0)).with_duration(duration)

    def _txt(text, fs, color):
        # margin gives descenders room so the label bbox never clips them.
        return TextClip(
            font=_CAPTION_FONT, text=text, font_size=fs, color=color,
            method="label", margin=(0, 6),
        ).with_duration(duration)

    name = _txt(brand.upper(), 28, "#FFCC00")
    middle_dot = _txt("·", 28, "#FFCC00")
    source_label = _txt(f"Sumber: {source}" if source else "Berita Terkini", 22, "white")

    ny = (bar_h - name.size[1]) // 2
    dy = (bar_h - middle_dot.size[1]) // 2
    sy = (bar_h - source_label.size[1]) // 2
    name = name.with_position((24, ny))
    middle_dot = middle_dot.with_position((24 + name.size[0] + 12, dy))
    source_label = source_label.with_position((24 + name.size[0] + 36, sy))

    clips = [bar, accent, name, middle_dot, source_label]
    bar_comp = CompositeVideoClip(clips, size=(w, bar_h))
    return bar_comp.with_position(("center", h - bar_h - bottom_gap))


def _build_outro(size, duration, text="Subscribe & like untuk update harian!", fontsize=42):
    w, h = size
    start = max(0, duration - 8)
    dur = min(8, duration - start)
    max_w = int(w * 0.88)

    overlay = ColorClip(size, color=(0, 0, 0)).with_duration(dur).with_start(start).with_opacity(0.55)

    txt = _text_overlay_clip(
        text,
        dur,
        ("center", "center"),
        fontsize,
        start=start,
        max_width=max_w,
        canvas_size=size,
    )
    return CompositeVideoClip([overlay, txt], size=size) if overlay else txt


# ---------------------------------------------------------------------------
# Sentence-synced captions
# ---------------------------------------------------------------------------

def _split_sentences(text):
    raw = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [s.strip() for s in raw if s.strip()]


def _wrap_words(words, max_per_line=7):
    lines = []
    line = []
    for w in words:
        line.append(w)
        if len(line) >= max_per_line:
            lines.append(" ".join(line))
            line = []
    if line:
        lines.append(" ".join(line))
    return lines


def _synced_captions(text, duration, base_size):
    sentences = _split_sentences(text)
    if not sentences:
        return []

    total_chars = sum(len(s) for s in sentences)
    if total_chars == 0:
        return []

    w, h = base_size
    max_text_w = int(w * 0.88)
    overlays = []
    start_time = 2.0
    usable_dur = max(1, duration - start_time - 5.0)
    y_base = 780          # below the template content box (y=696)
    y_step = 56

    for sentence in sentences:
        weight = len(sentence) / total_chars
        seg_dur = max(1.8, min(6.5, weight * usable_dur))
        seg_dur = min(seg_dur, duration - start_time - 1.0)
        if seg_dur <= 0.6:
            break

        lines = _wrap_words(sentence.split())
        for li, line in enumerate(lines):
            line_dur = seg_dur / max(1, len(lines))
            y = min(h - 240, y_base + (li * y_step))
            overlays.append(
                _text_overlay_clip(
                    line,
                    line_dur,
                    ("center", y),
                    50,
                    start=start_time + (li * line_dur * 0.4),
                    max_width=max_text_w,
                    bg=True,
                    bg_opacity=0.35,
                )
            )
        start_time += seg_dur * 0.82

    return overlays


# ---------------------------------------------------------------------------
# Audio mixing
# ---------------------------------------------------------------------------

def _mix_audio(voiceover_path, music_path, duration, music_volume, audio_mode="voiceover_and_music"):
    tracks = []
    if audio_mode != "music_only":
        try:
            voice = AudioFileClip(str(voiceover_path))
            if voice.duration and voice.duration > duration:
                voice = voice.subclipped(0, duration)
            voice = voice.with_volume_scaled(1.15)
            try:
                voice = voice.audio_fadein(0.15).audio_fadeout(0.3)
            except Exception:
                pass
            tracks.append(voice)
        except Exception as exc:
            logger.warning("Voiceover gagal dimuat: %s", exc)

    if music_path and music_path.exists() and audio_mode != "voiceover_only":
        try:
            music = AudioFileClip(str(music_path))
            if music.duration and music.duration < duration:
                count = int(duration // music.duration) + 1
                music = concatenate_audioclips([music] * count)
            music = music.subclipped(0, min(duration, music.duration if music.duration else duration))
            music = music.with_volume_scaled(max(0.0, music_volume * 0.6))
            try:
                music = music.audio_fadein(0.8).audio_fadeout(1.0)
            except Exception:
                pass
            tracks.append(music)
        except Exception as exc:
            logger.warning("Music track gagal dimuat: %s", exc)

    if not tracks:
        return None
    return CompositeAudioClip(tracks).with_duration(duration)


def _safe_audio_duration(path, fallback):
    try:
        clip = AudioFileClip(str(path))
        val = int(math.ceil(clip.duration or fallback))
        clip.close()
        return max(1, val)
    except Exception:
        return fallback


def _resize_to_box(clip, box_w, box_h):
    sw, sh = clip.w, clip.h
    if sw == 0 or sh == 0:
        return clip
    scale = max(box_w / sw, box_h / sh)
    rw, rh = int(sw * scale), int(sh * scale)
    resized = clip.resized(new_size=(rw, rh))
    cx = max(0, (rw - box_w) // 2)
    cy = max(0, (rh - box_h) // 2)
    return resized.cropped(x1=cx, y1=cy, width=box_w, height=box_h)


def _fit_into_box(clip, box_w, box_h):
    """Contain-fit: whole frame visible inside the box (no cropping)."""
    sw, sh = clip.w, clip.h
    if sw == 0 or sh == 0:
        return clip
    scale = min(box_w / sw, box_h / sh)
    return clip.resized(new_size=(max(1, int(sw * scale)), max(1, int(sh * scale))))


def _footage_box_blurred(clip, box_w, box_h, blur_radius=28, dim=0.82):
    """Box filled with a blurred, zoomed copy of the footage, sharp footage centered on top.

    Removes empty/white letterbox gaps: the whole footage frame stays visible (fit),
    and the surrounding area shows a blurred cover-crop of the same footage.
    """
    def _blur(frame):
        im = Image.fromarray(frame).filter(ImageFilter.GaussianBlur(radius=blur_radius))
        arr = np.array(im, dtype=np.uint8)
        if dim != 1.0:
            arr = (arr.astype(np.float32) * dim).astype(np.uint8)
        return arr

    background = _resize_to_box(clip, box_w, box_h).image_transform(_blur)
    # Inset the sharp footage so a blurred margin is always visible (framed-on-blur look).
    inset = 0.93
    foreground = _fit_into_box(clip, int(box_w * inset), int(box_h * inset))
    foreground = foreground.with_position(("center", "center"))
    return CompositeVideoClip([background, foreground], size=(box_w, box_h))


def _wrap_text_manual(text, max_width_chars=50):
    words = (text or "").split()
    if not words:
        return []
    lines = []
    current = ""
    for w in words:
        test = f"{current} {w}".strip()
        if len(test) <= max_width_chars:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def _fit_title_lines(text, box_w, box_h, font_name, max_lines=6, max_fs=76, min_fs=26):
    """Largest font whose word-wrapped lines fit inside (box_w x box_h). Fills the box."""
    from PIL import ImageFont

    words = (text or "").split()
    if not words:
        return min_fs, [], int(min_fs * 1.3)

    def wrap(font):
        lines, cur = [], ""
        for w in words:
            cand = f"{cur} {w}".strip()
            if not cur or font.getlength(cand) <= box_w:
                cur = cand
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    for fs in range(max_fs, min_fs - 1, -2):
        try:
            font = ImageFont.truetype(font_name, fs)
        except Exception:
            continue
        lines = wrap(font)
        line_h = int(fs * 1.3)
        too_wide = any(font.getlength(ln) > box_w for ln in lines)
        if not too_wide and len(lines) <= max_lines and len(lines) * line_h <= box_h:
            return fs, lines, line_h

    # Fallback: smallest size, hard-cap lines with an ellipsis.
    font = ImageFont.truetype(font_name, min_fs)
    lines = wrap(font)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" ,;:—-") + "…"
    return min_fs, lines, int(min_fs * 1.3)

def render_video(
    *,
    script: dict,
    base_template: Path,
    voiceover_path: Path,
    footage_paths: Iterable[Path],
    music_path: Optional[Path],
    out_path: Path,
    audio_mode: str = "voiceover_and_music",
    duration: int = 60,
    music_volume: float = 0.2,
    output_size=None,
    font_path: Optional[str | Path] = None,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    font_name = _resolve_font(font_path)

    target_size = _normalize_size(output_size) or _DEFAULT_CANVAS
    w, h = target_size
    overlay_max_w = int(w * 0.88)

    # ---- Template layout: white box (video), purple area (title) ----
    WHITE_BOX = {"x": 0, "y": 410, "w": 1079, "h": 677}

    # ---- Load footage (YouTube video) ----
    paths = [Path(p) for p in footage_paths if Path(p).exists()]
    footage_clip = None
    if paths:
        try:
            footage_clip = VideoFileClip(str(paths[0]))
        except Exception as exc:
            logger.warning("Footage video gagal: %s", exc)

    # Duration mengikuti footage YouTube, maksimal sesuai setting
    if footage_clip and footage_clip.duration:
        target_duration = min(int(duration), int(footage_clip.duration))
        target_duration = max(30, target_duration)
    else:
        target_duration = int(duration)

    overlay_clips: list = []

    # ---- Layer 0: solid fallback background ----
    overlay_clips.append(ColorClip(target_size, color=(10, 10, 10)).with_duration(target_duration))

    # ---- Layer 1: Video footage di KOTAK PUTIH (Di belakang bingkai template berlubang transparan) ----
    if paths:
        try:
            if len(paths) == 1:
                c = VideoFileClip(str(paths[0]))
                c_dur = min(target_duration, int(c.duration)) if c.duration else target_duration
                box = _footage_box_blurred(c.with_duration(c_dur), WHITE_BOX["w"], WHITE_BOX["h"])
            else:
                per_clip = max(3.0, target_duration / len(paths))
                box_clips = []
                for p in paths:
                    try:
                        c = VideoFileClip(str(p))
                        clip_dur = min(per_clip, c.duration) if c.duration else per_clip
                        box_c = _footage_box_blurred(c.with_duration(clip_dur), WHITE_BOX["w"], WHITE_BOX["h"])
                        box_clips.append(box_c)
                    except Exception as err:
                        logger.warning("Gagal load clip %s: %s", p, err)
                if box_clips:
                    box = concatenate_videoclips(box_clips, method="compose")
                    if box.duration and box.duration < target_duration:
                        repeat = math.ceil(target_duration / box.duration)
                        box = concatenate_videoclips([box] * repeat, method="compose").subclipped(0, target_duration)
                    else:
                        box = box.subclipped(0, target_duration)
                else:
                    box = None

            if box is not None:
                box = box.with_position((WHITE_BOX["x"], WHITE_BOX["y"]))
                box = _apply_fade(box, fade_in=0.3, fade_out=0.4)
                overlay_clips.append(box)
        except Exception as exc:
            logger.warning("Footage box rendering gagal: %s", exc)

    # ---- Layer 2: BASE TEMPLATE (Dengan lubang transparan di area kotak putih y=410..1087) ----
    if base_template.exists():
        try:
            template = _load_base_video(base_template, target_duration, target_size)
            overlay_clips.append(template.with_opacity(1.0))
        except Exception as exc:
            logger.warning("Template gagal: %s", exc)
    else:
        overlay_clips.append(ColorClip(target_size, color=(40, 22, 53)).with_duration(target_duration))

    # ---- Layer 3: readability gradient ----
    gradient = _readability_gradient(target_size, target_duration)
    if gradient is not None:
        overlay_clips.append(gradient)

    # ---- Layer 4: branding bar ----
    source = script.get("candidate_news", [{}])
    source_name = None
    if isinstance(source, list) and source:
        try:
            idx = int(script.get("selected_index", 0))
            source_name = source[idx].get("source") if 0 <= idx < len(source) else None
        except Exception:
            source_name = None
    branding = _build_branding_bar(target_size, target_duration, source=source_name)
    overlay_clips.append(branding)

    # ---- Layer 5: JUDUL di KOTAK UNGU (bigger, white + stroke, centered in box) ----
    title = script.get("title", "")
    if title:
        # Purple title box in the template (measured from the template frame).
        BOX_X1, BOX_Y1, BOX_X2, BOX_Y2 = 83, 1116, 823, 1431
        PAD_X, PAD_Y = 30, 22
        box_w = (BOX_X2 - BOX_X1) - 2 * PAD_X
        box_h = (BOX_Y2 - BOX_Y1) - 2 * PAD_Y

        # Auto-fit: largest font whose wrapped lines fill the box (no cramping, no cut-off).
        fs, text_lines, line_h = _fit_title_lines(title, box_w, box_h, font_name, max_lines=6)
        stroke_w = max(2, fs // 22)

        # Render the whole title as ONE multiline caption so descenders are never
        # clipped and lines are spaced/centered by MoviePy inside the box.
        try:
            tl = TextClip(
                font=font_name,
                text="\n".join(text_lines),
                font_size=fs,
                color="white",
                method="caption",
                size=(box_w, box_h),
                text_align="left",
                horizontal_align="left",
                vertical_align="center",
                stroke_color="black",
                stroke_width=stroke_w,
                margin=(0, 8),
            )
            tl = tl.with_duration(target_duration - 5).with_start(1.0)
            tl = tl.with_position((BOX_X1 + PAD_X, BOX_Y1 + PAD_Y))
            tl = _apply_fade(tl, fade_in=0.3, fade_out=0.3)
            overlay_clips.append(tl)
        except Exception as exc:
            logger.warning("Judul '%s' gagal: %s", title[:40], exc)

    # ---- Layer 6: outro CTA ----
    outro = _build_outro(target_size, target_duration)
    overlay_clips.append(outro)

    # ---- Compose video ----
    composed = CompositeVideoClip(overlay_clips).with_duration(target_duration)
    if composed.duration and composed.duration < target_duration:
        composed = composed.with_duration(target_duration)

    # ---- Audio mengikuti mode pipeline; audio footage tidak menimpa voiceover ----
    if audio_mode == "source_or_music":
        audio = None
        if footage_clip and footage_clip.audio and paths and _has_audible_audio(paths[0]):
            end = min(target_duration, footage_clip.audio.duration or target_duration)
            audio = footage_clip.audio.subclipped(0, end).with_volume_scaled(1.0)
        if audio is None:
            audio = _mix_audio(
                voiceover_path, music_path, target_duration, music_volume, "music_only"
            )
    else:
        audio = _mix_audio(
            voiceover_path, music_path, target_duration, music_volume, audio_mode
        )
    if audio is not None:
        composed = composed.with_audio(audio)

    fps = 30
    composed.write_videofile(
        str(out_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        bitrate="3600k",
        preset="medium",
        ffmpeg_params=["-pix_fmt", "yuv420p"],
        audio_bitrate="192k",
        threads=2,
        temp_audiofile=str(out_path.with_suffix(".m4a")),
    )
    return out_path
