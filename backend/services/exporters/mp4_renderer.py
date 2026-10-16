from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from backend.config import EXPORTS_DIR
from backend.models.schemas import (
    AudioCueMap,
    InstagramPostCopy,
    MediaItem,
    MediaType,
    PhotoEffectType,
    TimelineClip,
    TransitionType,
)


def _load_clean_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Loads a clean macOS/system sans-serif font (Avenir Next, Helvetica Neue, SF, Arial) for crisp video titles."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Avenir Next.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size, index=0)
            except Exception:
                continue
    return ImageFont.load_default()


def _clean_video_overlay_text(text: str) -> str:
    """Strips emoji characters that standard TrueType fonts cannot render as vector glyphs, keeping clean punctuation."""
    if not text:
        return ""
    # Remove supplemental plane emojis and variation selectors while preserving standard Latin/CJK/punctuation
    cleaned = re.sub(r"[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _apply_color_grade(frame: np.ndarray, grade: str) -> np.ndarray:
    """Applies stylized dance color grading LUT approximation."""
    if grade == "warm_stage":
        b, g, r = cv2.split(frame)
        r = np.clip(r.astype(np.float32) * 1.09 + 6, 0, 255).astype(np.uint8)
        g = np.clip(g.astype(np.float32) * 1.03 + 2, 0, 255).astype(np.uint8)
        b = np.clip(b.astype(np.float32) * 0.94, 0, 255).astype(np.uint8)
        return cv2.merge([b, g, r])
    elif grade == "soft_pastel":
        lifted = np.clip(frame.astype(np.float32) * 0.92 + 22, 0, 255).astype(np.uint8)
        return lifted
    elif grade == "vivid_hype":
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.25, 0, 255)
        hsv[:, :, 2] = np.clip(hsv[:, :, 2] * 1.06, 0, 255)
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    elif grade == "vintage_film":
        b, g, r = cv2.split(frame)
        r = np.clip(r.astype(np.float32) * 1.06 + 10, 0, 255).astype(np.uint8)
        b = np.clip(b.astype(np.float32) * 0.90 + 12, 0, 255).astype(np.uint8)
        return cv2.merge([b, g, r])
    return frame


def _fit_and_ken_burns_frame(
    src_bgr: np.ndarray,
    out_w: int,
    out_h: int,
    progress: float,
    effect: Optional[PhotoEffectType],
    focal_x: float = 0.5,
    focal_y: float = 0.45,
) -> np.ndarray:
    """
    Renders a source image or video frame into vertical 9:16 `(out_w, out_h)` with 10 supported photo styles:
    - `ken_burns_zoom_in`: Slow Cinematic Zoom-In toward focal subject
    - `ken_burns_zoom_out`: Wide Stage Reveal Zoom-Out
    - `ken_burns_pan_lr`: Smooth Stage Pan (Left -> Right)
    - `ken_burns_pan_rl`: Smooth Stage Pan (Right -> Left)
    - `ken_burns_pan_diag`: Dynamic Diagonal Drift
    - `tilt_up_stage`: Vertical Tilt Up (Stage Floor to Spotlight)
    - `beat_pulse_zoom`: Rhythmic Beat-Pulse Zoom
    - `soft_glow_dissolve`: Dreamy Stage Bloom & Soft Zoom
    - `spotlight_vignette`: Stage Spotlight Radial Vignette
    - `polaroid_frame`: Clean Editorial Gallery Frame over Blurred Stage Backdrop
    """
    if src_bgr is None or src_bgr.size == 0:
        return np.zeros((out_h, out_w, 3), dtype=np.uint8)

    sh, sw = src_bgr.shape[:2]
    target_aspect = out_w / float(out_h)
    src_aspect = sw / float(sh)
    p = min(1.0, max(0.0, progress))

    # Special Style: Editorial Gallery / Polaroid Frame over blurred backdrop
    if effect == PhotoEffectType.POLAROID_FRAME:
        bg = cv2.resize(src_bgr, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        bg = cv2.GaussianBlur(bg, (45, 45), 0)
        bg = (bg.astype(np.float32) * 0.48).astype(np.uint8)

        card_scale = 0.84 + 0.04 * math.sin(p * math.pi)
        max_fw = int(out_w * card_scale)
        max_fh = int(out_h * 0.72)
        fit_s = min(max_fw / float(sw), max_fh / float(sh))
        fw = max(1, int(sw * fit_s))
        fh = max(1, int(sh * fit_s))
        fg = cv2.resize(src_bgr, (fw, fh), interpolation=cv2.INTER_AREA)

        pad = 12
        card_w = fw + pad * 2
        card_h = fh + pad * 2 + 18
        x0 = max(0, (out_w - card_w) // 2)
        y0 = max(0, (out_h - card_h) // 2)
        cv2.rectangle(bg, (x0, y0), (min(out_w, x0 + card_w), min(out_h, y0 + card_h)), (248, 248, 250), -1)
        bg[y0 + pad : y0 + pad + fh, x0 + pad : x0 + pad + fw] = fg
        return bg

    overscale = 1.32
    cw = int(out_w * overscale)
    ch = int(out_h * overscale)

    if abs(src_aspect - target_aspect) > 0.15:
        bg = cv2.resize(src_bgr, (cw, ch), interpolation=cv2.INTER_LINEAR)
        bg = cv2.GaussianBlur(bg, (35, 35), 0)
        bg = (bg.astype(np.float32) * 0.52).astype(np.uint8)

        scale_fit = min(cw / float(sw), ch / float(sh)) * 0.94
        fw = max(1, int(sw * scale_fit))
        fh = max(1, int(sh * scale_fit))
        fg = cv2.resize(src_bgr, (fw, fh), interpolation=cv2.INTER_LINEAR)
        x0 = (cw - fw) // 2
        y0 = (ch - fh) // 2
        bg[y0 : y0 + fh, x0 : x0 + fw] = fg
        canvas = bg
    else:
        canvas = cv2.resize(src_bgr, (cw, ch), interpolation=cv2.INTER_LINEAR)

    if effect == PhotoEffectType.KEN_BURNS_ZOOM_IN:
        zoom = 1.0 + 0.24 * p
        shift_x = (focal_x - 0.5) * 0.35 * p
        shift_y = (focal_y - 0.5) * 0.35 * p
    elif effect == PhotoEffectType.KEN_BURNS_ZOOM_OUT:
        zoom = 1.24 - 0.22 * p
        shift_x = (focal_x - 0.5) * 0.25 * (1.0 - p)
        shift_y = (focal_y - 0.5) * 0.25 * (1.0 - p)
    elif effect == PhotoEffectType.KEN_BURNS_PAN_LEFT_RIGHT:
        zoom = 1.16
        shift_x = -0.11 + 0.22 * p
        shift_y = 0.0
    elif effect == PhotoEffectType.KEN_BURNS_PAN_RIGHT_LEFT:
        zoom = 1.16
        shift_x = 0.11 - 0.22 * p
        shift_y = 0.0
    elif effect == PhotoEffectType.KEN_BURNS_PAN_DIAG:
        zoom = 1.06 + 0.16 * p
        shift_x = -0.08 + 0.16 * p
        shift_y = 0.06 - 0.12 * p
    elif effect == PhotoEffectType.TILT_UP_STAGE:
        zoom = 1.15
        shift_x = (focal_x - 0.5) * 0.15
        shift_y = 0.11 - 0.22 * p
    elif effect == PhotoEffectType.BEAT_PULSE_ZOOM:
        pulse = math.sin(p * math.pi * 2.0) ** 2
        zoom = 1.04 + 0.16 * pulse
        shift_x = 0.0
        shift_y = 0.0
    elif effect == PhotoEffectType.SOFT_GLOW_DISSOLVE:
        zoom = 1.04 + 0.14 * p
        shift_x = (focal_x - 0.5) * 0.20 * p
        shift_y = (focal_y - 0.5) * 0.20 * p
    elif effect == PhotoEffectType.SPOTLIGHT_VIGNETTE:
        zoom = 1.05 + 0.14 * p
        shift_x = (focal_x - 0.5) * 0.25 * p
        shift_y = (focal_y - 0.5) * 0.25 * p
    else:
        zoom = 1.02 + 0.05 * p
        shift_x = 0.0
        shift_y = 0.0

    crop_w = int(cw / zoom)
    crop_h = int(ch / zoom)
    cx = int(cw * (0.5 + shift_x))
    cy = int(ch * (0.5 + shift_y))

    x1 = min(cw - crop_w, max(0, cx - crop_w // 2))
    y1 = min(ch - crop_h, max(0, cy - crop_h // 2))
    cropped = canvas[y1 : y1 + crop_h, x1 : x1 + crop_w]
    out_frame = cv2.resize(cropped, (out_w, out_h), interpolation=cv2.INTER_LINEAR)

    if effect == PhotoEffectType.SOFT_GLOW_DISSOLVE:
        bloom = cv2.GaussianBlur(out_frame, (29, 29), 0)
        out_frame = cv2.addWeighted(out_frame, 0.80, bloom, 0.25, 6)
    elif effect == PhotoEffectType.SPOTLIGHT_VIGNETTE:
        yy, xx = np.ogrid[:out_h, :out_w]
        center_x = out_w * 0.5
        center_y = out_h * 0.48
        dist_sq = ((xx - center_x) / (out_w * 0.55)) ** 2 + ((yy - center_y) / (out_h * 0.55)) ** 2
        mask = np.clip(1.08 - 0.48 * dist_sq, 0.35, 1.0).astype(np.float32)[..., None]
        out_frame = np.clip(out_frame.astype(np.float32) * mask, 0, 255).astype(np.uint8)

    return out_frame


def _apply_clip_entry_transition(
    frame: np.ndarray,
    prev_last_frame: Optional[np.ndarray],
    f_idx: int,
    transition: TransitionType,
) -> np.ndarray:
    """Applies the selected visual transition across the first `trans_frames` frames of a clip."""
    trans_frames = 6
    if f_idx >= trans_frames or transition == TransitionType.CUT_ON_BEAT:
        return frame

    # alpha goes from 0.15 -> 1.0 across the transition window
    alpha = (f_idx + 1) / float(trans_frames + 1)
    h, w = frame.shape[:2]

    if transition == TransitionType.FLASH_WHITE and f_idx < 4:
        flash_w = (4 - f_idx) * 0.17
        return cv2.addWeighted(frame, 1.0 - flash_w, np.full_like(frame, 255), flash_w, 0)

    if transition == TransitionType.DIP_TO_BLACK:
        return np.clip(frame.astype(np.float32) * alpha, 0, 255).astype(np.uint8)

    if transition == TransitionType.CROSS_DISSOLVE and prev_last_frame is not None:
        return cv2.addWeighted(frame, alpha, prev_last_frame, 1.0 - alpha, 0)

    if transition == TransitionType.ZOOM_WHIP:
        zoom_factor = 1.0 + (1.0 - alpha) * 0.32
        zw = int(w / zoom_factor)
        zh = int(h / zoom_factor)
        x0 = (w - zw) // 2
        y0 = (h - zh) // 2
        zoomed = cv2.resize(frame[y0 : y0 + zh, x0 : x0 + zw], (w, h), interpolation=cv2.INTER_LINEAR)
        return zoomed

    if transition == TransitionType.SLIDE_LEFT and prev_last_frame is not None:
        offset_x = int(w * (1.0 - alpha))
        comp = np.zeros_like(frame)
        comp[:, : offset_x] = prev_last_frame[:, w - offset_x :]
        comp[:, offset_x:] = frame[:, : w - offset_x]
        return comp

    if transition == TransitionType.SLIDE_UP and prev_last_frame is not None:
        offset_y = int(h * (1.0 - alpha))
        comp = np.zeros_like(frame)
        comp[:offset_y, :] = prev_last_frame[h - offset_y :, :]
        comp[offset_y:, :] = frame[: h - offset_y, :]
        return comp

    if transition == TransitionType.LIGHT_LEAK_WARM:
        leak_strength = (1.0 - alpha) * 0.55
        warm_overlay = np.zeros_like(frame)
        warm_overlay[:, :] = (45, 145, 255)  # BGR warm golden amber flare
        return cv2.addWeighted(frame, 1.0 - leak_strength * 0.35, warm_overlay, leak_strength, 0)

    if transition == TransitionType.BLUR_DISSOLVE:
        ksize = max(1, int((1.0 - alpha) * 12) * 2 + 1)
        blurred = cv2.GaussianBlur(frame, (ksize, ksize), 0)
        if prev_last_frame is not None:
            prev_blur = cv2.GaussianBlur(prev_last_frame, (ksize, ksize), 0)
            return cv2.addWeighted(blurred, alpha, prev_blur, 1.0 - alpha, 0)
        return blurred

    return frame


def _draw_editorial_video_title(
    frame: np.ndarray,
    text: str,
    style: str = "minimal_lower_third",
    is_closing: bool = False,
) -> None:
    """
    Renders clean, anti-aliased editorial typography onto the video frame using Pillow.
    Supports:
    - `'minimal_lower_third'`: Subtle dark scrim + clean left-aligned editorial typography with thin accent bar
    - `'cinema_subtitle'`: Clean centered white subtitle with soft drop shadow (no background box)
    - `'frosted_pill'`: Rounded translucent frosted dark pill with crisp centered typography
    - `'none'`: Draws nothing (100% clean video)
    """
    if style == "none":
        return

    clean_txt = _clean_video_overlay_text(text)
    if not clean_txt:
        return

    h, w = frame.shape[:2]
    font_main = _load_clean_font(size=22 if not is_closing else 20, bold=True)

    # Word-wrap into clean lines (max ~28 chars per line)
    words = clean_txt.split()
    lines: List[str] = []
    cur: List[str] = []
    for word in words:
        cur.append(word)
        if len(" ".join(cur)) > 28:
            if len(cur) > 1:
                lines.append(" ".join(cur[:-1]))
                cur = [word]
            else:
                lines.append(" ".join(cur))
                cur = []
    if cur:
        lines.append(" ".join(cur))
    lines = lines[:2]

    # Convert BGR numpy array to RGBA Pillow image for smooth alpha compositing
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    base_img = Image.fromarray(rgb).convert("RGBA")
    overlay_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay_img)

    line_h = 30
    total_text_h = len(lines) * line_h

    if style == "cinema_subtitle":
        y_start = int(h * 0.82) - total_text_h // 2
        for i, ln in enumerate(lines):
            bbox = draw.textbbox((0, 0), ln, font=font_main)
            tw = bbox[2] - bbox[0]
            tx = (w - tw) // 2
            ty = y_start + i * line_h
            # Soft multi-offset shadow for high legibility over any stage lighting
            for dx, dy in [(-1, 1), (1, 1), (0, 2), (1, 2)]:
                draw.text((tx + dx, ty + dy), ln, font=font_main, fill=(0, 0, 0, 190))
            draw.text((tx, ty), ln, font=font_main, fill=(255, 255, 255, 250))

    elif style == "frosted_pill":
        max_tw = max((draw.textbbox((0, 0), ln, font=font_main)[2] for ln in lines), default=200)
        pad_x = 24
        pad_y = 14
        pill_w = min(w - 48, max_tw + pad_x * 2)
        pill_h = total_text_h + pad_y * 2 - 4
        x0 = (w - pill_w) // 2
        y0 = int(h * 0.80) - pill_h // 2 if is_closing else int(h * 0.12)
        draw.rounded_rectangle(
            [x0, y0, x0 + pill_w, y0 + pill_h],
            radius=16,
            fill=(15, 23, 42, 175),
            outline=(255, 255, 255, 55),
            width=1,
        )
        for i, ln in enumerate(lines):
            bbox = draw.textbbox((0, 0), ln, font=font_main)
            tw = bbox[2] - bbox[0]
            tx = (w - tw) // 2
            ty = y0 + pad_y - 2 + i * line_h
            draw.text((tx, ty), ln, font=font_main, fill=(255, 255, 255, 250))

    else:
        # Default: 'minimal_lower_third' — clean editorial lower-third card
        max_tw = max((draw.textbbox((0, 0), ln, font=font_main)[2] for ln in lines), default=200)
        x0 = 32
        y0 = int(h * 0.81) - total_text_h // 2
        box_w = min(w - 64, max_tw + 36)
        box_h = total_text_h + 22
        draw.rounded_rectangle(
            [x0, y0, x0 + box_w, y0 + box_h],
            radius=10,
            fill=(15, 23, 42, 160),
        )
        # Crisp white vertical editorial accent bar on the left edge
        draw.rounded_rectangle(
            [x0 + 10, y0 + 10, x0 + 13, y0 + box_h - 10],
            radius=2,
            fill=(255, 255, 255, 235),
        )
        for i, ln in enumerate(lines):
            tx = x0 + 22
            ty = y0 + 9 + i * line_h
            draw.text((tx, ty), ln, font=font_main, fill=(255, 255, 255, 250))

    composited = Image.alpha_composite(base_img, overlay_img).convert("RGB")
    frame[:, :] = cv2.cvtColor(np.array(composited), cv2.COLOR_RGB2BGR)


def render_session_mp4(
    session_id: str,
    timeline_clips: List[TimelineClip],
    media_lookup: Dict[str, MediaItem],
    audio_cue_map: Optional[AudioCueMap],
    post_copy: Optional[InstagramPostCopy],
    color_grade: str = "warm_stage",
    out_w: int = 540,
    out_h: int = 960,
    fps: int = 24,
) -> Path:
    """
    Renders the complete beat-synced vertical Instagram Reel MP4 with:
    - Slip-synced or manually trimmed video segments & dynamic speed ramping
    - 10 photo styles during sustained notes & pauses
    - 9 transition styles between clips
    - Clean editorial typography overlay (or clean no-text mode)
    - Synced audio track muxed into H.264 + AAC MP4
    """
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_mp4 = EXPORTS_DIR / f"{session_id}_reel.mp4"
    temp_silent_mp4 = EXPORTS_DIR / f"{session_id}_silent.mp4"

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd_video = [
        ffmpeg_exe,
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-s",
        f"{out_w}x{out_h}",
        "-pix_fmt",
        "bgr24",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-vcodec",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "ultrafast",
        "-crf",
        "22",
        str(temp_silent_mp4),
    ]
    proc = subprocess.Popen(
        cmd_video, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    total_duration = max((c.timeline_end_sec for c in timeline_clips), default=12.0)
    title_style = post_copy.video_title_style if post_copy else "minimal_lower_third"
    prev_last_frame: Optional[np.ndarray] = None

    for clip in timeline_clips:
        clip_frames = max(1, int(round(clip.duration_sec * fps)))
        media_item = media_lookup.get(clip.media_id)
        fpath = Path(media_item.filepath) if media_item else None

        if clip.media_type == MediaType.PHOTO and fpath and fpath.exists():
            photo_bgr = cv2.imread(str(fpath))
            last_rendered: Optional[np.ndarray] = None
            for f_idx in range(clip_frames):
                prog = f_idx / float(max(1, clip_frames - 1))
                global_t = clip.timeline_start_sec + (f_idx / float(fps))
                frame = _fit_and_ken_burns_frame(
                    src_bgr=photo_bgr,
                    out_w=out_w,
                    out_h=out_h,
                    progress=prog,
                    effect=clip.photo_effect or PhotoEffectType.KEN_BURNS_ZOOM_IN,
                    focal_x=clip.focal_point.center_x,
                    focal_y=clip.focal_point.center_y,
                )
                frame = _apply_color_grade(frame, color_grade)
                frame = _apply_clip_entry_transition(
                    frame=frame,
                    prev_last_frame=prev_last_frame,
                    f_idx=f_idx,
                    transition=clip.transition_in,
                )
                last_rendered = frame.copy()

                if post_copy and global_t <= 2.6:
                    _draw_editorial_video_title(
                        frame, post_copy.hook_title_overlay, style=title_style, is_closing=False
                    )
                elif post_copy and global_t >= total_duration - 2.0:
                    _draw_editorial_video_title(
                        frame, post_copy.ending_call_to_action, style=title_style, is_closing=True
                    )

                if proc.stdin:
                    proc.stdin.write(frame.tobytes())
            if last_rendered is not None:
                prev_last_frame = last_rendered

        elif fpath and fpath.exists():
            cap = cv2.VideoCapture(str(fpath))
            src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 24.0)
            if src_fps <= 1.0:
                src_fps = 24.0
            src_total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 90)

            start_frame = max(0, int(clip.source_in_sec * src_fps))
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            need_src_frames = max(12, int((clip.source_out_sec - clip.source_in_sec) * src_fps) + 8)
            loaded_frames: List[np.ndarray] = []
            for _ in range(min(src_total_frames, need_src_frames)):
                ret, vf = cap.read()
                if not ret:
                    break
                loaded_frames.append(vf)
            cap.release()

            if not loaded_frames:
                loaded_frames = [np.zeros((out_h, out_w, 3), dtype=np.uint8)]

            last_rendered_vid: Optional[np.ndarray] = None
            for f_idx in range(clip_frames):
                prog = f_idx / float(max(1, clip_frames - 1))
                global_t = clip.timeline_start_sec + (f_idx / float(fps))

                if clip.speed_ramp_curve:
                    warped_prog = 0.5 + 0.5 * math.sin((prog - 0.5) * math.pi)
                else:
                    warped_prog = prog

                src_i = min(
                    len(loaded_frames) - 1,
                    max(0, int(round(warped_prog * (len(loaded_frames) - 1)))),
                )
                raw_vf = loaded_frames[src_i]
                frame = _fit_and_ken_burns_frame(
                    src_bgr=raw_vf,
                    out_w=out_w,
                    out_h=out_h,
                    progress=prog,
                    effect=None,
                    focal_x=clip.focal_point.center_x,
                    focal_y=clip.focal_point.center_y,
                )
                frame = _apply_color_grade(frame, color_grade)
                frame = _apply_clip_entry_transition(
                    frame=frame,
                    prev_last_frame=prev_last_frame,
                    f_idx=f_idx,
                    transition=clip.transition_in,
                )
                last_rendered_vid = frame.copy()

                if post_copy and global_t <= 2.6:
                    _draw_editorial_video_title(
                        frame, post_copy.hook_title_overlay, style=title_style, is_closing=False
                    )
                elif post_copy and global_t >= total_duration - 2.0:
                    _draw_editorial_video_title(
                        frame, post_copy.ending_call_to_action, style=title_style, is_closing=True
                    )

                if proc.stdin:
                    proc.stdin.write(frame.tobytes())
            if last_rendered_vid is not None:
                prev_last_frame = last_rendered_vid

    if proc.stdin:
        proc.stdin.close()
    proc.wait(timeout=60)

    # Mux audio track with video
    if audio_cue_map and Path(audio_cue_map.filepath).exists():
        cmd_mux = [
            ffmpeg_exe,
            "-y",
            "-i",
            str(temp_silent_mp4),
            "-i",
            str(audio_cue_map.filepath),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_mp4),
        ]
        subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        temp_silent_mp4.unlink(missing_ok=True)
    else:
        temp_silent_mp4.replace(output_mp4)

    return output_mp4
