from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
import cv2
import imageio_ffmpeg
import numpy as np

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


def _apply_color_grade(frame: np.ndarray, grade: str) -> np.ndarray:
    """Applies stylized dance color grading LUT approximation."""
    if grade == "warm_stage":
        # Boost warm golden highlights & rich contrast
        b, g, r = cv2.split(frame)
        r = np.clip(r.astype(np.float32) * 1.09 + 6, 0, 255).astype(np.uint8)
        g = np.clip(g.astype(np.float32) * 1.03 + 2, 0, 255).astype(np.uint8)
        b = np.clip(b.astype(np.float32) * 0.94, 0, 255).astype(np.uint8)
        return cv2.merge([b, g, r])
    elif grade == "soft_pastel":
        # Dreamy lyrical lift
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
    Renders a source image or video frame into vertical 9:16 `(out_w, out_h)` with:
    - Blurred ambient background fill if aspect ratio differs
    - Smooth sub-pixel Ken Burns zoom-in, zoom-out, horizontal pan, diagonal pan, or beat-pulse zoom
    """
    if src_bgr is None or src_bgr.size == 0:
        return np.zeros((out_h, out_w, 3), dtype=np.uint8)

    sh, sw = src_bgr.shape[:2]
    target_aspect = out_w / float(out_h)
    src_aspect = sw / float(sh)

    # First create a cover-scaled canvas of size (int(out_w * 1.32), int(out_h * 1.32)) for smooth zoom/pan
    overscale = 1.32
    cw = int(out_w * overscale)
    ch = int(out_h * overscale)

    if abs(src_aspect - target_aspect) > 0.15:
        # Fit with aspect preservation over a soft-blurred 9:16 backdrop
        bg = cv2.resize(src_bgr, (cw, ch), interpolation=cv2.INTER_LINEAR)
        bg = cv2.GaussianBlur(bg, (35, 35), 0)
        bg = (bg.astype(np.float32) * 0.55).astype(np.uint8)

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

    # Compute Ken Burns crop window (crop_w, crop_h) inside (cw, ch)
    p = min(1.0, max(0.0, progress))
    if effect == PhotoEffectType.KEN_BURNS_ZOOM_IN:
        zoom = 1.0 + 0.24 * p
        shift_x = (focal_x - 0.5) * 0.35 * p
        shift_y = (focal_y - 0.5) * 0.35 * p
    elif effect == PhotoEffectType.KEN_BURNS_ZOOM_OUT:
        zoom = 1.24 - 0.22 * p
        shift_x = (focal_x - 0.5) * 0.25 * (1.0 - p)
        shift_y = (focal_y - 0.5) * 0.25 * (1.0 - p)
    elif effect == PhotoEffectType.KEN_BURNS_PAN_LEFT_RIGHT:
        zoom = 1.15
        shift_x = -0.10 + 0.20 * p
        shift_y = 0.0
    elif effect == PhotoEffectType.KEN_BURNS_PAN_DIAG:
        zoom = 1.06 + 0.16 * p
        shift_x = -0.08 + 0.16 * p
        shift_y = 0.06 - 0.12 * p
    elif effect == PhotoEffectType.BEAT_PULSE_ZOOM:
        pulse = math.sin(p * math.pi * 2.0) ** 2
        zoom = 1.04 + 0.16 * pulse
        shift_x = 0.0
        shift_y = 0.0
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
    return cv2.resize(cropped, (out_w, out_h), interpolation=cv2.INTER_LINEAR)


def _draw_wrapped_banner_text(
    frame: np.ndarray,
    text: str,
    y_center: int,
    alpha: float = 0.85,
    accent_color: tuple = (210, 120, 255),
) -> None:
    """Draws an attractive Instagram Reel title pill overlay with word wrapping."""
    if not text or alpha <= 0.05:
        return
    h, w = frame.shape[:2]
    words = text.split()
    lines: List[str] = []
    cur: List[str] = []
    for word in words:
        cur.append(word)
        if len(" ".join(cur)) > 26:
            if len(cur) > 1:
                lines.append(" ".join(cur[:-1]))
                cur = [word]
            else:
                lines.append(" ".join(cur))
                cur = []
    if cur:
        lines.append(" ".join(cur))

    font = cv2.FONT_HERSHEY_DUPLEX
    scale = 0.72
    thickness = 2
    line_h = 34
    box_h = len(lines) * line_h + 28
    box_w = min(w - 48, max(260, max(len(ln) for ln in lines) * 15 + 48))

    x0 = (w - box_w) // 2
    y0 = max(24, y_center - box_h // 2)
    x1 = x0 + box_w
    y1 = min(h - 24, y0 + box_h)

    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x1, y1), (22, 16, 34), -1)
    cv2.rectangle(overlay, (x0, y0), (x1, y1), accent_color, 2)
    cv2.addWeighted(overlay, min(0.82, alpha), frame, 1.0 - min(0.82, alpha), 0, frame)

    for i, ln in enumerate(lines):
        (tw, th), _ = cv2.getTextSize(ln, font, scale, thickness)
        tx = (w - tw) // 2
        ty = y0 + 28 + i * line_h
        cv2.putText(frame, ln, (tx, ty), font, scale, (255, 250, 255), thickness, cv2.LINE_AA)


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
    - Slip-synced video segments & dynamic speed ramping around jump peaks / turns
    - Still photos during sustained notes & pauses with smooth Ken Burns zoom/pan
    - Beat flash / crossfade transitions
    - Attractive on-screen title hook overlay & closing CTA
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

    for clip in timeline_clips:
        clip_frames = max(1, int(round(clip.duration_sec * fps)))
        media_item = media_lookup.get(clip.media_id)
        fpath = Path(media_item.filepath) if media_item else None

        if clip.media_type == MediaType.PHOTO and fpath and fpath.exists():
            photo_bgr = cv2.imread(str(fpath))
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

                # Transition flash on entry
                if f_idx < 4 and clip.transition_in == TransitionType.FLASH_WHITE:
                    flash_w = (4 - f_idx) * 0.18
                    frame = cv2.addWeighted(
                        frame, 1.0 - flash_w, np.full_like(frame, 255), flash_w, 0
                    )

                # Hook title overlay during first 2.6s
                if post_copy and global_t <= 2.6:
                    _draw_wrapped_banner_text(
                        frame, post_copy.hook_title_overlay, int(out_h * 0.15)
                    )
                elif post_copy and global_t >= total_duration - 2.0:
                    _draw_wrapped_banner_text(
                        frame, post_copy.ending_call_to_action, int(out_h * 0.84)
                    )

                if proc.stdin:
                    proc.stdin.write(frame.tobytes())

        elif fpath and fpath.exists():
            cap = cv2.VideoCapture(str(fpath))
            src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 24.0)
            if src_fps <= 1.0:
                src_fps = 24.0
            src_total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 90)

            # Preload trimmed source segment frames
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

            for f_idx in range(clip_frames):
                prog = f_idx / float(max(1, clip_frames - 1))
                global_t = clip.timeline_start_sec + (f_idx / float(fps))

                # Apply subtle speed-ramp curve around beat apex if enabled
                if clip.speed_ramp_curve:
                    # S-curve time-warping: faster approach, slower through mid-clip beat apex
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

                # Highlight subtle golden pulse right on the synced downbeat apex!
                if clip.synced_beat_timestamp and abs(global_t - clip.synced_beat_timestamp) <= 0.10:
                    frame = cv2.addWeighted(
                        frame, 0.85, np.full_like(frame, (190, 230, 255)), 0.15, 0
                    )

                if f_idx < 3 and clip.transition_in == TransitionType.FLASH_WHITE:
                    flash_w = (3 - f_idx) * 0.20
                    frame = cv2.addWeighted(
                        frame, 1.0 - flash_w, np.full_like(frame, 255), flash_w, 0
                    )

                if post_copy and global_t <= 2.6:
                    _draw_wrapped_banner_text(
                        frame, post_copy.hook_title_overlay, int(out_h * 0.15)
                    )
                elif post_copy and global_t >= total_duration - 2.0:
                    _draw_wrapped_banner_text(
                        frame, post_copy.ending_call_to_action, int(out_h * 0.84)
                    )

                if proc.stdin:
                    proc.stdin.write(frame.tobytes())

    if proc.stdin:
        proc.stdin.close()
    proc.wait()

    # Mux audio track with video if audio_cue_map exists
    if audio_cue_map and Path(audio_cue_map.filepath).exists():
        cmd_mux = [
            ffmpeg_exe,
            "-y",
            "-i",
            str(temp_silent_mp4),
            "-i",
            str(audio_cue_map.filepath),
            "-t",
            str(round(total_duration, 2)),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_mp4),
        ]
        subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if output_mp4.exists() and output_mp4.stat().st_size > 1000:
            temp_silent_mp4.unlink(missing_ok=True)
            return output_mp4

    temp_silent_mp4.replace(output_mp4)
    return output_mp4
