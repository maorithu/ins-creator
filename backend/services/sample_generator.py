from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List
import cv2
import imageio_ffmpeg
import numpy as np
import subprocess

from backend.config import SAMPLE_DATA_DIR


SAMPLE_MEDIA_MANIFEST: List[Dict[str, object]] = [
    {
        "id": "vid_comp_split_leap",
        "filename": "competition_stage_split_leap.mp4",
        "media_type": "video",
        "event_category": "dance_competition",
        "duration_sec": 4.5,
        "apex_sec": 2.2,
        "move_mode": "jump_peak",
        "tags": ["competition", "stage", "split leap", "grand jete", "contemporary", "daughter", "spotlight"],
        "semantic_caption": "Daughter soaring into a full 180-degree grand jeté split leap under golden competition stage spotlights.",
        "palette": ((45, 22, 65), (215, 165, 255), (255, 215, 120)),
    },
    {
        "id": "vid_rehearsal_pirouette",
        "filename": "rehearsal_studio_triple_pirouette.mp4",
        "media_type": "video",
        "event_category": "dance_rehearsal",
        "duration_sec": 4.2,
        "apex_sec": 2.0,
        "move_mode": "turn_spin",
        "tags": ["rehearsal", "studio", "pirouette", "turns", "spins", "training", "daughter", "mirror"],
        "semantic_caption": "Clean triple pirouette turn sequence in the dance rehearsal studio with sharp spotting finish.",
        "palette": ((55, 45, 38), (120, 210, 255), (255, 140, 190)),
    },
    {
        "id": "vid_training_firebird_jump",
        "filename": "training_acro_firebird_jump.mp4",
        "media_type": "video",
        "event_category": "dance_training",
        "duration_sec": 4.0,
        "apex_sec": 1.85,
        "move_mode": "jump_peak",
        "tags": ["training", "jump", "firebird", "leap", "technique", "flexibility", "daughter", "rehearsal"],
        "semantic_caption": "Explosive firebird arch jump during technique training session hitting peak elevation mid-clip.",
        "palette": ((35, 50, 62), (130, 245, 215), (255, 190, 110)),
    },
    {
        "id": "vid_comp_finale_turns",
        "filename": "competition_finale_fouette_turns.mp4",
        "media_type": "video",
        "event_category": "dance_competition",
        "duration_sec": 4.5,
        "apex_sec": 2.35,
        "move_mode": "turn_spin",
        "tags": ["competition", "finale", "fouette", "turns", "stage", "solo", "daughter", "encore"],
        "semantic_caption": "High-speed fouetté a la seconde turns culminating in a dramatic stage finale pose.",
        "palette": ((30, 20, 58), (255, 160, 210), (255, 230, 140)),
    },
    {
        "id": "photo_stage_arabesque",
        "filename": "photo_stage_golden_arabesque.jpg",
        "media_type": "photo",
        "event_category": "dance_competition",
        "tags": ["photo", "competition", "arabesque", "pose", "graceful", "stage", "daughter", "lyrical"],
        "semantic_caption": "Poised needle arabesque extension caught in warm stage side-lighting during a sustained note.",
        "palette": ((38, 24, 64), (255, 195, 135), (245, 155, 225)),
        "pose_style": "arabesque",
    },
    {
        "id": "photo_rehearsal_candid_smile",
        "filename": "photo_rehearsal_water_break_smile.jpg",
        "media_type": "photo",
        "event_category": "dance_rehearsal",
        "tags": ["photo", "rehearsal", "smile", "candid", "backstage", "training", "daughter", "happy"],
        "semantic_caption": "Candid glowing smile at the studio barre after nailing her eight-count combination.",
        "palette": ((52, 42, 62), (165, 225, 255), (255, 185, 210)),
        "pose_style": "portrait_smile",
    },
    {
        "id": "photo_competition_award_hug",
        "filename": "photo_backstage_costume_sparkle.jpg",
        "media_type": "photo",
        "event_category": "dance_competition",
        "tags": ["photo", "competition", "costume", "backstage", "proud", "daughter", "wings"],
        "semantic_caption": "Backstage pre-stage focus in sparkling competition costume ready to step into the lights.",
        "palette": ((42, 30, 58), (240, 200, 255), (255, 220, 130)),
        "pose_style": "crown_pose",
    },
]


def _draw_stage_background(
    w: int, h: int, bg_bgr: tuple, accent_bgr: tuple, t_norm: float
) -> np.ndarray:
    """Renders a rich stage/studio backdrop with spotlight beams and floor reflection."""
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    y_grad = np.linspace(0.6, 1.35, h).reshape(h, 1, 1)
    base = np.array(bg_bgr, dtype=np.float32).reshape(1, 1, 3)
    frame[:] = np.clip(base * y_grad, 0, 255).astype(np.uint8)

    # Stage floor horizon at 78% height
    floor_y = int(h * 0.78)
    cv2.line(frame, (0, floor_y), (w, floor_y), (110, 100, 135), 2)

    # Diagonal spotlight cones
    overlay = frame.copy()
    beam_shift = int(math.sin(t_norm * math.pi * 2.0) * 35)
    pts1 = np.array(
        [[int(w * 0.25), 0], [int(w * 0.45), 0], [int(w * 0.80) + beam_shift, floor_y], [int(w * 0.10) + beam_shift, floor_y]],
        dtype=np.int32,
    )
    cv2.fillPoly(overlay, [pts1], accent_bgr)
    cv2.addWeighted(overlay, 0.16, frame, 0.84, 0, frame)
    return frame


def _draw_dancer_figure(
    frame: np.ndarray,
    cx: int,
    cy: int,
    scale: float,
    color_main: tuple,
    color_costume: tuple,
    move_mode: str,
    phase: float,
) -> None:
    """
    Draws an expressive, articulated dancer silhouette + costume flow:
    - For 'jump_peak': phase in [0..1] where 0.5 is peak split-leap elevation with wide horizontal legs & arched arms
    - For 'turn_spin': oscillating horizontal arm/skirt width and rapid spotting marks creating clear horizontal optical flow
    """
    # Head
    head_r = max(10, int(18 * scale))
    head_y = cy - int(95 * scale)
    cv2.circle(frame, (cx, head_y), head_r, (245, 235, 250), -1, cv2.LINE_AA)
    # Hair bun
    cv2.circle(frame, (cx - int(8 * scale), head_y - int(14 * scale)), max(5, int(8 * scale)), (220, 195, 235), -1, cv2.LINE_AA)

    # Torso / Leotard
    shoulder_y = cy - int(65 * scale)
    hip_y = cy + int(5 * scale)
    torso_pts = np.array(
        [
            [cx - int(22 * scale), shoulder_y],
            [cx + int(22 * scale), shoulder_y],
            [cx + int(15 * scale), hip_y],
            [cx - int(15 * scale), hip_y],
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(frame, [torso_pts], color_costume, cv2.LINE_AA)

    if move_mode == "jump_peak":
        # Split angle increases sharply near jump apex (phase ~ 0.5)
        split_factor = math.exp(-((phase - 0.5) / 0.22) ** 2)
        leg_len = int(115 * scale)
        angle_deg = 22.0 + 68.0 * split_factor  # reaches 90 deg each side = 180 deg grand jete at apex!
        rad = math.radians(angle_deg)

        # Front & back legs
        front_x = cx + int(leg_len * math.sin(rad))
        front_y = hip_y + int(leg_len * math.cos(rad))
        back_x = cx - int(leg_len * math.sin(rad))
        back_y = hip_y + int(leg_len * math.cos(rad) * 0.85)

        cv2.line(frame, (cx + int(8 * scale), hip_y), (front_x, front_y), (250, 235, 245), max(6, int(10 * scale)), cv2.LINE_AA)
        cv2.line(frame, (cx - int(8 * scale), hip_y), (back_x, back_y), (250, 235, 245), max(6, int(10 * scale)), cv2.LINE_AA)

        # Flowing lyrical skirt trail
        skirt_pts = np.array(
            [
                [cx - int(18 * scale), hip_y],
                [cx + int(18 * scale), hip_y],
                [cx + int(52 * scale * (0.5 + split_factor)), hip_y + int(42 * scale)],
                [cx - int(58 * scale * (0.5 + split_factor)), hip_y + int(48 * scale)],
            ],
            dtype=np.int32,
        )
        cv2.fillPoly(frame, [skirt_pts], color_main, cv2.LINE_AA)

        # Graceful crown/V arms reaching upward at apex
        arm_len = int(85 * scale)
        arm_lift = int(65 * scale * split_factor)
        cv2.line(
            frame,
            (cx - int(20 * scale), shoulder_y),
            (cx - int(65 * scale), shoulder_y + int(25 * scale) - arm_lift),
            (250, 235, 245),
            max(5, int(8 * scale)),
            cv2.LINE_AA,
        )
        cv2.line(
            frame,
            (cx + int(20 * scale), shoulder_y),
            (cx + int(65 * scale), shoulder_y + int(25 * scale) - arm_lift),
            (250, 235, 245),
            max(5, int(8 * scale)),
            cv2.LINE_AA,
        )

    elif move_mode == "turn_spin":
        # Rapid rotational motion around vertical axis: spinning skirt ribbons + passers/fouette leg
        spin_intensity = math.exp(-((phase - 0.5) / 0.25) ** 2)
        theta = phase * math.pi * 14.0  # multiple fast revolutions
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        # Standing supporting leg on relevé
        foot_y = hip_y + int(115 * scale)
        cv2.line(frame, (cx, hip_y), (cx, foot_y), (250, 235, 245), max(6, int(10 * scale)), cv2.LINE_AA)

        # Retiré / Passé knee rotating horizontally
        knee_x = cx + int(62 * scale * cos_t)
        knee_y = hip_y + int(42 * scale)
        cv2.line(frame, (cx, hip_y), (knee_x, knee_y), (250, 235, 245), max(6, int(9 * scale)), cv2.LINE_AA)
        cv2.line(frame, (knee_x, knee_y), (cx, hip_y + int(55 * scale)), (250, 235, 245), max(5, int(8 * scale)), cv2.LINE_AA)

        # Spinning skirt flare & ribbon particles moving horizontally so optical flow sees strong horizontal rotation
        flare_w = int((38 + 45 * spin_intensity) * scale)
        skirt_pts = np.array(
            [
                [cx - int(16 * scale), hip_y],
                [cx + int(16 * scale), hip_y],
                [cx + flare_w, hip_y + int(42 * scale)],
                [cx - flare_w, hip_y + int(42 * scale)],
            ],
            dtype=np.int32,
        )
        cv2.fillPoly(frame, [skirt_pts], color_main, cv2.LINE_AA)

        # Orbiting ribbon/sparkle nodes that translate horizontally across the torso
        for k in range(5):
            ang = theta + k * (2 * math.pi / 5.0)
            rx = cx + int(math.sin(ang) * 75 * scale * (0.4 + 0.6 * spin_intensity))
            ry = shoulder_y + int(k * 16 * scale)
            cv2.circle(frame, (rx, ry), max(5, int(8 * scale)), color_costume, -1, cv2.LINE_AA)

    else:
        # Poised photo pose (arabesque / portrait / crown)
        foot_y = hip_y + int(115 * scale)
        cv2.line(frame, (cx, hip_y), (cx, foot_y), (250, 235, 245), max(7, int(11 * scale)), cv2.LINE_AA)
        cv2.line(
            frame,
            (cx, hip_y),
            (cx - int(95 * scale), hip_y - int(45 * scale)),
            (250, 235, 245),
            max(7, int(10 * scale)),
            cv2.LINE_AA,
        )
        cv2.line(
            frame,
            (cx, shoulder_y),
            (cx + int(75 * scale), shoulder_y - int(45 * scale)),
            (250, 235, 245),
            max(6, int(9 * scale)),
            cv2.LINE_AA,
        )
        skirt_pts = np.array(
            [
                [cx - int(20 * scale), hip_y],
                [cx + int(20 * scale), hip_y],
                [cx + int(55 * scale), hip_y + int(46 * scale)],
                [cx - int(55 * scale), hip_y + int(46 * scale)],
            ],
            dtype=np.int32,
        )
        cv2.fillPoly(frame, [skirt_pts], color_main, cv2.LINE_AA)


def _generate_sample_video(spec: Dict[str, object], target_path: Path) -> None:
    """Generates a 540x960 @ 24fps H.264 MP4 dance clip with realistic jump apex or turn trajectory."""
    w, h = 540, 960
    fps = 24
    duration_sec = float(spec["duration_sec"])
    apex_sec = float(spec["apex_sec"])
    move_mode = str(spec["move_mode"])
    bg_bgr, main_bgr, costume_bgr = spec["palette"]  # type: ignore
    total_frames = int(duration_sec * fps)

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-s",
        f"{w}x{h}",
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
        "23",
        str(target_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for idx in range(total_frames):
        t_sec = idx / float(fps)
        t_norm = t_sec / duration_sec
        frame = _draw_stage_background(w, h, bg_bgr, main_bgr, t_norm)

        base_cy = int(h * 0.60)
        base_cx = int(w * 0.50)

        if move_mode == "jump_peak":
            # Parabolic ballistic jump centered right at apex_sec!
            dt = t_sec - apex_sec
            jump_window = 0.75
            if abs(dt) <= jump_window:
                norm_dt = dt / jump_window  # -1..1
                # Parabolic height gain: peak at dt=0
                elevation_px = int((1.0 - norm_dt * norm_dt) * (h * 0.24))
                cy = base_cy - elevation_px
                cx = base_cx + int(norm_dt * 55)
                phase = 0.5 + 0.5 * norm_dt
            else:
                # Preparatory chassé / landing plié
                cy = base_cy + int(12 * math.sin(t_sec * 6.0))
                cx = base_cx + int(math.copysign(55, dt))
                phase = 0.0 if dt < 0 else 1.0
        else:
            # Turn / spin centered at apex_sec with strong horizontal motion & level vertical center
            dt = t_sec - apex_sec
            turn_window = 0.85
            cy = base_cy
            cx = base_cx + int(10 * math.sin(t_sec * 4.0))
            if abs(dt) <= turn_window:
                phase = 0.5 + 0.5 * (dt / turn_window)
            else:
                phase = 0.05

        _draw_dancer_figure(
            frame=frame,
            cx=cx,
            cy=cy,
            scale=1.15,
            color_main=main_bgr,
            color_costume=costume_bgr,
            move_mode=move_mode,
            phase=phase,
        )

        # Subtle stage caption badge at bottom corner
        label = str(spec["event_category"]).replace("_", " ").upper()
        cv2.putText(
            frame,
            label,
            (28, h - 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (225, 220, 240),
            1,
            cv2.LINE_AA,
        )
        if proc.stdin:
            proc.stdin.write(frame.tobytes())

    if proc.stdin:
        proc.stdin.close()
    proc.wait()


def _generate_sample_photo(spec: Dict[str, object], target_path: Path) -> None:
    """Generates a high-resolution 1080x1440 dance event photograph."""
    w, h = 1080, 1440
    bg_bgr, main_bgr, costume_bgr = spec["palette"]  # type: ignore
    frame = _draw_stage_background(w, h, bg_bgr, main_bgr, 0.35)

    # Bokeh stage lights in upper background
    rng = np.random.default_rng(seed=len(str(spec["id"])))
    overlay = frame.copy()
    for _ in range(18):
        bx = int(rng.integers(80, w - 80))
        by = int(rng.integers(90, int(h * 0.55)))
        br = int(rng.integers(18, 52))
        cv2.circle(overlay, (bx, by), br, costume_bgr, -1, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.22, frame, 0.78, 0, frame)

    _draw_dancer_figure(
        frame=frame,
        cx=int(w * 0.52),
        cy=int(h * 0.56),
        scale=2.1,
        color_main=main_bgr,
        color_costume=costume_bgr,
        move_mode="photo_pose",
        phase=0.5,
    )
    cv2.imwrite(str(target_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 94])


def ensure_sample_dance_dataset() -> List[Dict[str, object]]:
    """Ensures all sample dance rehearsal, training, and competition videos & photos exist on disk."""
    SAMPLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for spec in SAMPLE_MEDIA_MANIFEST:
        target = SAMPLE_DATA_DIR / str(spec["filename"])
        if not target.exists() or target.stat().st_size < 1000:
            if spec["media_type"] == "video":
                _generate_sample_video(spec, target)
            else:
                _generate_sample_photo(spec, target)
    return SAMPLE_MEDIA_MANIFEST
