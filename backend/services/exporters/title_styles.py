"""
On-screen hook / closing title styles for the 9:16 Reel.

The SAME code renders both the final MP4 frames and the Step 4 live preview PNGs,
so the preview is pixel-identical to what ends up in the video.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# (id, label, description, default position, default animation)
HOOK_TEXT_STYLES: List[Dict[str, str]] = [
    {"id": "bold_center_impact", "label": "Bold Center Hook", "description": "Huge condensed caps with thick outline — classic Reels/TikTok hook", "position": "center", "animation": "pop_in"},
    {"id": "classic_white_box", "label": "Instagram Classic Box", "description": "Black text on white rounded highlight boxes", "position": "center", "animation": "pop_in"},
    {"id": "neon_glow", "label": "Neon Stage Glow", "description": "Hot-pink neon glow like stage lights", "position": "center", "animation": "fade_in"},
    {"id": "elegant_serif", "label": "Elegant Serif", "description": "Didot italic with fine gold rules — lyrical & ballet", "position": "center", "animation": "fade_in"},
    {"id": "magazine_cover", "label": "Magazine Cover", "description": "Oversized Futura caps with a kicker label, top-left", "position": "top", "animation": "slide_up"},
    {"id": "gold_spotlight", "label": "Gold Spotlight", "description": "Gold-gradient Bodoni with soft glow — awards & finales", "position": "center", "animation": "fade_in"},
    {"id": "typewriter_mono", "label": "Typewriter", "description": "Mono label strips typed out letter by letter", "position": "bottom", "animation": "typewriter"},
    {"id": "minimal_lower_third", "label": "Editorial Lower-Third", "description": "Subtle dark card with accent bar", "position": "bottom", "animation": "slide_up"},
    {"id": "cinema_subtitle", "label": "Cinema Subtitle", "description": "Clean centered subtitle with soft shadow", "position": "bottom", "animation": "fade_in"},
    {"id": "frosted_pill", "label": "Frosted Glass Pill", "description": "Rounded translucent pill", "position": "top", "animation": "fade_in"},
    {"id": "none", "label": "No Text on Video", "description": "Clean video — add text natively in Instagram/CapCut", "position": "center", "animation": "none"},
]
HOOK_TEXT_ANIMATIONS: List[Dict[str, str]] = [
    {"id": "auto", "label": "Style Default"},
    {"id": "none", "label": "Static"},
    {"id": "fade_in", "label": "Fade In"},
    {"id": "pop_in", "label": "Pop In (bounce)"},
    {"id": "slide_up", "label": "Slide Up"},
    {"id": "typewriter", "label": "Typewriter Reveal"},
]
HOOK_TEXT_POSITIONS = ["auto", "top", "center", "bottom"]

_STYLE_INDEX = {s["id"]: s for s in HOOK_TEXT_STYLES}

_FONT_FILES: Dict[str, List[Tuple[str, int]]] = {
    "sans_bold": [("/System/Library/Fonts/HelveticaNeue.ttc", 1), ("/System/Library/Fonts/Helvetica.ttc", 1)],
    "sans_medium": [("/System/Library/Fonts/HelveticaNeue.ttc", 10), ("/System/Library/Fonts/Helvetica.ttc", 0)],
    "sans_black": [("/System/Library/Fonts/HelveticaNeue.ttc", 9), ("/System/Library/Fonts/Supplemental/Impact.ttf", 0)],
    "futura_bold": [("/System/Library/Fonts/Supplemental/Futura.ttc", 2)],
    "futura_xb": [("/System/Library/Fonts/Supplemental/Futura.ttc", 4), ("/System/Library/Fonts/Supplemental/Impact.ttf", 0)],
    "serif_italic": [("/System/Library/Fonts/Supplemental/Didot.ttc", 1), ("/System/Library/Fonts/Supplemental/Georgia Bold Italic.ttf", 0)],
    "serif_bold": [("/System/Library/Fonts/Supplemental/Bodoni 72.ttc", 2), ("/System/Library/Fonts/Supplemental/Didot.ttc", 2)],
    "mono": [("/System/Library/Fonts/Supplemental/Courier New Bold.ttf", 0), ("/System/Library/Fonts/Menlo.ttc", 1)],
    "cjk": [("/System/Library/Fonts/Hiragino Sans GB.ttc", 2), ("/System/Library/Fonts/STHeiti Medium.ttc", 0)],
}
_CJK_RE = re.compile(r"[\u3000-\u9fff\uac00-\ud7af\uff00-\uffef]")


def clean_overlay_text(text: str) -> str:
    """Strips emoji glyphs that TrueType fonts cannot render (avoids tofu boxes)."""
    if not text:
        return ""
    cleaned = re.sub(r"[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f\u200d]", "", text)
    return re.sub(r"\s+", " ", cleaned).strip()


@lru_cache(maxsize=128)
def _font(kind: str, size: int, cjk: bool = False) -> ImageFont.ImageFont:
    order = (["cjk"] if cjk else []) + [kind, "sans_bold"]
    for k in order:
        for path, idx in _FONT_FILES.get(k, []):
            if Path(path).exists():
                try:
                    return ImageFont.truetype(path, size=size, index=idx)
                except Exception:
                    continue
    return ImageFont.load_default()


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, stroke: int = 0) -> int:
    b = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    return b[2] - b[0]


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int, stroke: int = 0) -> List[str]:
    if _CJK_RE.search(text) and " " not in text.strip():
        tokens, joiner = list(text), ""
    else:
        tokens, joiner = text.split(), " "
    lines: List[str] = []
    cur = ""
    for tok in tokens:
        trial = f"{cur}{joiner}{tok}" if cur else tok
        if _text_w(draw, trial, font, stroke) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = tok
    if cur:
        lines.append(cur)
    return lines


def _fit(
    draw: ImageDraw.ImageDraw, text: str, kind: str, size: int, max_w: int, max_lines: int, stroke: int = 0
) -> Tuple[ImageFont.ImageFont, List[str], int]:
    cjk = bool(_CJK_RE.search(text))
    s = size
    while True:
        font = _font(kind, s, cjk)
        lines = _wrap(draw, text, font, max_w, stroke)
        if len(lines) <= max_lines or s <= int(size * 0.5):
            return font, lines[:max_lines], s
        s = int(s * 0.9)


def _reveal(lines: List[str], frac: float) -> List[str]:
    if frac >= 1.0:
        return lines
    total = sum(len(l) for l in lines)
    keep = int(round(total * max(0.0, frac)))
    out: List[str] = []
    for ln in lines:
        if keep <= 0:
            out.append("")
            continue
        out.append(ln[:keep])
        keep -= len(ln)
    return out


def _anchor_y(h: int, position: str, block_h: int, default: str) -> int:
    pos = default if position in ("", "auto", None) else position
    centers = {"top": 0.17, "center": 0.46, "bottom": 0.80}
    return int(h * centers.get(pos, 0.46) - block_h / 2)


def _shadow_layer(size: Tuple[int, int], draw_fn, radius: float, color=(0, 0, 0, 170)) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer), color)
    return layer.filter(ImageFilter.GaussianBlur(radius))


def _render_overlay(
    w: int, h: int, text: str, style: str, position: str, is_closing: bool, reveal: float
) -> Image.Image:
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    default_pos = _STYLE_INDEX.get(style, _STYLE_INDEX["bold_center_impact"])["position"]
    if is_closing and default_pos == "top":
        default_pos = "bottom"
    scale = w / 540.0

    def S(v: float) -> int:
        return max(1, int(round(v * scale)))

    if style == "bold_center_impact":
        txt = text.upper()
        stroke = S(5)
        font, lines, fs = _fit(draw, txt, "sans_black", S(66 if not is_closing else 50), w - S(60), 3, stroke)
        lines = _reveal(lines, reveal)
        lh = int(fs * 1.08)
        y0 = _anchor_y(h, position, lh * len(lines), default_pos)
        for i, ln in enumerate(lines):
            tx = (w - _text_w(draw, ln, font, stroke)) // 2
            draw.text((tx, y0 + i * lh), ln, font=font, fill=(255, 255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        return overlay

    if style == "classic_white_box":
        font, lines, fs = _fit(draw, text, "sans_bold", S(32 if not is_closing else 26), w - S(90), 3)
        lines = _reveal(lines, reveal)
        lh = int(fs * 1.42)
        y0 = _anchor_y(h, position, lh * len(lines), default_pos)
        pad_x, pad_y = S(14), S(7)
        for i, ln in enumerate(lines):
            if not ln:
                continue
            tw = _text_w(draw, ln, font)
            tx = (w - tw) // 2
            ty = y0 + i * lh
            bb = draw.textbbox((tx, ty), ln, font=font)
            draw.rounded_rectangle([bb[0] - pad_x, bb[1] - pad_y, bb[2] + pad_x, bb[3] + pad_y], radius=S(9), fill=(255, 255, 255, 250))
        for i, ln in enumerate(lines):
            if ln:
                tx = (w - _text_w(draw, ln, font)) // 2
                draw.text((tx, y0 + i * lh), ln, font=font, fill=(17, 17, 17, 255))
        return overlay

    if style == "neon_glow":
        txt = text.upper()
        font, lines, fs = _fit(draw, txt, "futura_bold", S(46 if not is_closing else 36), w - S(70), 3)
        lines = _reveal(lines, reveal)
        lh = int(fs * 1.2)
        y0 = _anchor_y(h, position, lh * len(lines), default_pos)
        pos = [((w - _text_w(draw, ln, font)) // 2, y0 + i * lh, ln) for i, ln in enumerate(lines)]

        def paint(d: ImageDraw.ImageDraw, color) -> None:
            for x, y, ln in pos:
                d.text((x, y), ln, font=font, fill=color, stroke_width=S(2), stroke_fill=color)

        overlay.alpha_composite(_shadow_layer((w, h), paint, S(14), (255, 40, 170, 230)))
        overlay.alpha_composite(_shadow_layer((w, h), paint, S(5), (255, 90, 200, 255)))
        d2 = ImageDraw.Draw(overlay)
        for x, y, ln in pos:
            d2.text((x, y), ln, font=font, fill=(255, 236, 250, 255))
        return overlay

    if style == "elegant_serif":
        font, lines, fs = _fit(draw, text, "serif_italic", S(46 if not is_closing else 38), w - S(80), 3)
        lines = _reveal(lines, reveal)
        lh = int(fs * 1.18)
        block = lh * len(lines)
        y0 = _anchor_y(h, position, block + S(40), default_pos) + S(20)
        pos = [((w - _text_w(draw, ln, font)) // 2, y0 + i * lh, ln) for i, ln in enumerate(lines)]

        def paint(d: ImageDraw.ImageDraw, color) -> None:
            for x, y, ln in pos:
                d.text((x, y), ln, font=font, fill=color)

        overlay.alpha_composite(_shadow_layer((w, h), paint, S(6), (0, 0, 0, 200)))
        d2 = ImageDraw.Draw(overlay)
        gold = (232, 204, 142, 235)
        rule_w = S(70)
        d2.line([(w // 2 - rule_w, y0 - S(16)), (w // 2 + rule_w, y0 - S(16))], fill=gold, width=S(2))
        d2.line([(w // 2 - rule_w, y0 + block + S(8)), (w // 2 + rule_w, y0 + block + S(8))], fill=gold, width=S(2))
        for x, y, ln in pos:
            d2.text((x, y), ln, font=font, fill=(255, 252, 245, 255))
        return overlay

    if style == "magazine_cover":
        txt = text.upper()
        font, lines, fs = _fit(draw, txt, "futura_xb", S(72 if not is_closing else 54), w - S(64), 3)
        lines = _reveal(lines, reveal)
        lh = int(fs * 0.98)
        kicker = "CURTAIN CALL" if is_closing else "ON STAGE NOW"
        kfont = _font("sans_bold", S(16))
        kick_h = S(30)
        block = kick_h + S(12) + lh * len(lines)
        y0 = _anchor_y(h, position, block, default_pos)
        x0 = S(32)
        kw = _text_w(draw, kicker, kfont)
        draw.rectangle([x0, y0, x0 + kw + S(20), y0 + kick_h], fill=(225, 29, 72, 245))
        draw.text((x0 + S(10), y0 + S(6)), kicker, font=kfont, fill=(255, 255, 255, 255))
        ty0 = y0 + kick_h + S(12)
        pos = [(x0, ty0 + i * lh, ln) for i, ln in enumerate(lines)]

        def paint(d: ImageDraw.ImageDraw, color) -> None:
            for x, y, ln in pos:
                d.text((x, y), ln, font=font, fill=color)

        overlay.alpha_composite(_shadow_layer((w, h), paint, S(8), (0, 0, 0, 190)))
        d2 = ImageDraw.Draw(overlay)
        for x, y, ln in pos:
            d2.text((x, y), ln, font=font, fill=(255, 255, 255, 255))
        return overlay

    if style == "gold_spotlight":
        font, lines, fs = _fit(draw, text, "serif_bold", S(50 if not is_closing else 40), w - S(70), 3)
        lines = _reveal(lines, reveal)
        lh = int(fs * 1.16)
        block = lh * len(lines)
        y0 = _anchor_y(h, position, block, default_pos)
        pos = [((w - _text_w(draw, ln, font)) // 2, y0 + i * lh, ln) for i, ln in enumerate(lines)]

        def paint(d: ImageDraw.ImageDraw, color) -> None:
            for x, y, ln in pos:
                d.text((x, y), ln, font=font, fill=color)

        overlay.alpha_composite(_shadow_layer((w, h), paint, S(12), (255, 190, 80, 120)))
        overlay.alpha_composite(_shadow_layer((w, h), paint, S(3), (40, 20, 0, 220)))
        mask = Image.new("L", (w, h), 0)
        paint(ImageDraw.Draw(mask), 255)
        grad = np.zeros((h, w, 4), dtype=np.uint8)
        top, bot = max(0, y0 - S(4)), min(h, y0 + block + S(8))
        ramp = np.linspace(0.0, 1.0, max(1, bot - top))[:, None]
        c1, c2 = np.array([255, 238, 170]), np.array([196, 140, 52])
        grad[top:bot, :, :3] = (c1 * (1 - ramp[..., None]) + c2 * ramp[..., None]).astype(np.uint8)
        grad[:, :, 3] = 255
        gold_img = Image.fromarray(grad, "RGBA")
        gold_img.putalpha(mask)
        overlay.alpha_composite(gold_img)
        return overlay

    if style == "typewriter_mono":
        font, lines, fs = _fit(draw, text, "mono", S(28 if not is_closing else 24), w - S(90), 4)
        shown = _reveal(lines, reveal)
        lh = int(fs * 1.6)
        y0 = _anchor_y(h, position, lh * len(lines), default_pos)
        x0 = S(36)
        last_idx = max((i for i, ln in enumerate(shown) if ln), default=-1)
        for i, ln in enumerate(shown):
            if not ln:
                continue
            tw = _text_w(draw, ln, font)
            draw.rectangle([x0 - S(10), y0 + i * lh - S(5), x0 + max(tw, S(8)) + S(10), y0 + i * lh + fs + S(6)], fill=(10, 10, 10, 215))
            draw.text((x0, y0 + i * lh), ln, font=font, fill=(255, 255, 255, 255))
            if reveal < 1.0 and i == last_idx:
                draw.rectangle([x0 + tw + S(3), y0 + i * lh + S(2), x0 + tw + S(13), y0 + i * lh + fs], fill=(255, 214, 10, 255))
        return overlay

    if style == "cinema_subtitle":
        font, lines, fs = _fit(draw, text, "sans_medium", S(28 if not is_closing else 24), w - S(70), 2)
        lines = _reveal(lines, reveal)
        lh = int(fs * 1.3)
        y0 = _anchor_y(h, position, lh * len(lines), "bottom" if default_pos == "bottom" else default_pos)
        pos = [((w - _text_w(draw, ln, font)) // 2, y0 + i * lh, ln) for i, ln in enumerate(lines)]

        def paint(d: ImageDraw.ImageDraw, color) -> None:
            for x, y, ln in pos:
                d.text((x, y + S(2)), ln, font=font, fill=color)

        overlay.alpha_composite(_shadow_layer((w, h), paint, S(4), (0, 0, 0, 220)))
        d2 = ImageDraw.Draw(overlay)
        for x, y, ln in pos:
            d2.text((x, y), ln, font=font, fill=(255, 255, 255, 252))
        return overlay

    if style == "frosted_pill":
        font, lines, fs = _fit(draw, text, "sans_bold", S(26 if not is_closing else 22), w - S(110), 2)
        lines = _reveal(lines, reveal)
        lh = int(fs * 1.3)
        full_w = max((_text_w(draw, ln, font) for ln in lines), default=S(100))
        pill_w = min(w - S(48), full_w + S(52))
        pill_h = lh * len(lines) + S(26)
        x0 = (w - pill_w) // 2
        y0 = _anchor_y(h, position, pill_h, default_pos)
        draw.rounded_rectangle([x0, y0, x0 + pill_w, y0 + pill_h], radius=S(pill_h // 2 if len(lines) == 1 else 20), fill=(15, 23, 42, 170), outline=(255, 255, 255, 70), width=S(1))
        for i, ln in enumerate(lines):
            tx = (w - _text_w(draw, ln, font)) // 2
            draw.text((tx, y0 + S(12) + i * lh), ln, font=font, fill=(255, 255, 255, 252))
        return overlay

    # Default: minimal_lower_third
    font, lines, fs = _fit(draw, text, "sans_bold", S(26 if not is_closing else 22), w - S(110), 2)
    lines = _reveal(lines, reveal)
    lh = int(fs * 1.3)
    max_tw = max((_text_w(draw, ln, font) for ln in lines), default=S(120))
    box_w = min(w - S(64), max_tw + S(44))
    box_h = lh * len(lines) + S(24)
    x0 = S(32)
    y0 = _anchor_y(h, position, box_h, default_pos)
    draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=S(10), fill=(15, 23, 42, 165))
    draw.rounded_rectangle([x0 + S(11), y0 + S(11), x0 + S(15), y0 + box_h - S(11)], radius=S(2), fill=(251, 191, 36, 240))
    for i, ln in enumerate(lines):
        draw.text((x0 + S(26), y0 + S(11) + i * lh), ln, font=font, fill=(255, 255, 255, 252))
    return overlay


def _ease_out_cubic(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _ease_out_back(x: float) -> float:
    x = max(0.0, min(1.0, x))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def resolve_animation(style: str, animation: Optional[str]) -> str:
    if not animation or animation == "auto":
        return _STYLE_INDEX.get(style, {}).get("animation", "fade_in")
    return animation


_OVERLAY_CACHE: Dict[tuple, Image.Image] = {}


def _cached_overlay(w: int, h: int, text: str, style: str, position: str, is_closing: bool, reveal: float) -> Image.Image:
    key = (w, h, text, style, position, is_closing, round(reveal, 3))
    ov = _OVERLAY_CACHE.get(key)
    if ov is None:
        if len(_OVERLAY_CACHE) > 256:
            _OVERLAY_CACHE.clear()
        ov = _render_overlay(w, h, text, style, position, is_closing, reveal)
        _OVERLAY_CACHE[key] = ov
    return ov


def compose_title_overlay(
    w: int,
    h: int,
    text: str,
    style: str = "bold_center_impact",
    position: str = "auto",
    animation: str = "auto",
    anim_t: float = 10.0,
    duration: float = 2.6,
    is_closing: bool = False,
) -> Optional[Image.Image]:
    """Returns the RGBA overlay for time `anim_t` seconds after the title appears (None = nothing to draw)."""
    if style == "none":
        return None
    clean = clean_overlay_text(text)
    if not clean:
        return None
    anim = resolve_animation(style, animation)
    entrance = 0.45
    e = max(0.0, min(1.0, anim_t / entrance))

    reveal = 1.0
    if anim == "typewriter":
        reveal = max(0.0, min(1.0, anim_t / max(0.4, duration * 0.55)))
        # quantize so cached overlays are reused across frames
        reveal = round(reveal * 40) / 40.0

    overlay = _cached_overlay(w, h, clean, style, position, is_closing, reveal)
    alpha = 1.0
    dy = 0
    scale = 1.0
    if anim == "fade_in":
        alpha = _ease_out_cubic(e)
    elif anim == "pop_in":
        scale = 0.55 + 0.45 * _ease_out_back(e)
        alpha = min(1.0, e * 2.2)
    elif anim == "slide_up":
        dy = int((1.0 - _ease_out_cubic(e)) * h * 0.06)
        alpha = _ease_out_cubic(e)
    if not is_closing:
        alpha *= max(0.0, min(1.0, (duration - anim_t) / 0.3))
    if alpha <= 0.01:
        return None

    out = overlay
    if scale != 1.0 or dy != 0:
        bbox = overlay.getbbox()
        if bbox:
            crop = overlay.crop(bbox)
            nw, nh = max(1, int(crop.width * scale)), max(1, int(crop.height * scale))
            crop = crop.resize((nw, nh), Image.BICUBIC)
            cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2 + dy
            out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            out.alpha_composite(crop, (max(0, cx - nw // 2), max(0, cy - nh // 2)))
    if alpha < 0.999:
        out = out.copy()
        a = out.getchannel("A").point(lambda v: int(v * alpha))
        out.putalpha(a)
    return out


def draw_title_on_frame(frame_bgr: np.ndarray, overlay: Optional[Image.Image]) -> None:
    """Alpha-composites the overlay onto a BGR frame in place."""
    if overlay is None:
        return
    ov = np.asarray(overlay, dtype=np.float32)
    a = ov[:, :, 3:4] / 255.0
    if not np.any(a):
        return
    rgb = ov[:, :, :3][:, :, ::-1]  # RGB -> BGR
    frame_bgr[:, :] = np.clip(frame_bgr.astype(np.float32) * (1 - a) + rgb * a, 0, 255).astype(np.uint8)


def render_title_preview(
    bg_bgr: np.ndarray,
    text: str,
    style: str,
    position: str = "auto",
    animation: str = "auto",
    t: float = 1.2,
    duration: float = 2.6,
    is_closing: bool = False,
) -> np.ndarray:
    frame = bg_bgr.copy()
    h, w = frame.shape[:2]
    ov = compose_title_overlay(w, h, text, style, position, animation, t, duration, is_closing)
    draw_title_on_frame(frame, ov)
    return frame


def gradient_backdrop(w: int = 540, h: int = 960) -> np.ndarray:
    """Stage-like fallback backdrop when no media frame is available."""
    yy = np.linspace(0, 1, h)[:, None]
    xx = np.linspace(-1, 1, w)[None, :]
    spot = np.exp(-((xx * 1.2) ** 2 + ((yy - 0.38) * 2.4) ** 2))
    base = np.stack([60 + 90 * spot, 30 + 50 * spot, 70 + 120 * spot], axis=-1)
    return np.clip(base, 0, 255).astype(np.uint8)


def frame_from_bgr_for_preview(src_bgr: np.ndarray, w: int, h: int) -> np.ndarray:
    """Center-crops a source image to 9:16 (preview background)."""
    sh, sw = src_bgr.shape[:2]
    target = w / float(h)
    if sw / float(sh) > target:
        nw = int(sh * target)
        x0 = (sw - nw) // 2
        crop = src_bgr[:, x0 : x0 + nw]
    else:
        nh = int(sw / target)
        y0 = max(0, int((sh - nh) * 0.4))
        crop = src_bgr[y0 : y0 + nh, :]
    return cv2.resize(crop, (w, h), interpolation=cv2.INTER_AREA)


_ = math  # keep import for potential easing extensions
