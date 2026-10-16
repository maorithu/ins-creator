from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional, Tuple
import cv2
import numpy as np

from backend.models.schemas import (
    BoundingBoxCenter,
    DanceMovementEvent,
    DanceMoveType,
    MediaItem,
    MediaType,
)


def compute_sharpness_score(bgr_frame: np.ndarray) -> float:
    """Computes normalized sharpness score [0..1] via Laplacian variance."""
    if bgr_frame is None or bgr_frame.size == 0:
        return 0.5
    gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
    variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    # Normalize typical dance video/photo Laplacian variance (50..800) into [0.3..0.99]
    norm = min(0.99, max(0.30, 0.30 + 0.69 * (1.0 - math.exp(-variance / 250.0))))
    return round(norm, 3)


def compute_aesthetic_score(bgr_frame: np.ndarray, sharpness: float) -> float:
    """Evaluates colorfulness, contrast, exposure balance, and sharpness."""
    if bgr_frame is None or bgr_frame.size == 0:
        return 0.75
    hsv = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2HSV)
    sat_mean = float(np.mean(hsv[:, :, 1])) / 255.0
    val_mean = float(np.mean(hsv[:, :, 2])) / 255.0
    val_std = float(np.std(hsv[:, :, 2])) / 128.0

    exposure_score = 1.0 - abs(val_mean - 0.55) * 1.2
    contrast_score = min(1.0, val_std * 1.3)
    color_score = min(1.0, sat_mean * 1.8 + 0.3)

    combined = 0.35 * sharpness + 0.25 * exposure_score + 0.20 * contrast_score + 0.20 * color_score
    return round(min(0.99, max(0.45, combined)), 3)


def detect_subject_focal_box(bgr_frame: np.ndarray) -> BoundingBoxCenter:
    """Finds the primary subject/dancer bounding box center using saliency/brightness + contour analysis."""
    if bgr_frame is None or bgr_frame.size == 0:
        return BoundingBoxCenter()

    h, w = bgr_frame.shape[:2]
    gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 0)

    # Edge + high-luminance spotlight map typical of stage & studio dancers
    edges = cv2.Canny(blurred, 40, 140)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    combined = cv2.bitwise_or(edges, thresh)

    # Weight toward center-vertical region where dancers usually perform
    ys, xs = np.nonzero(combined)
    if len(xs) < 50:
        return BoundingBoxCenter(center_x=0.5, center_y=0.45, box_width=0.5, box_height=0.7)

    cx = float(np.median(xs)) / float(w)
    cy = float(np.median(ys)) / float(h)
    bw = min(0.85, max(0.25, float(np.percentile(xs, 85) - np.percentile(xs, 15)) / float(w)))
    bh = min(0.90, max(0.35, float(np.percentile(ys, 85) - np.percentile(ys, 15)) / float(h)))

    return BoundingBoxCenter(
        center_x=round(min(0.8, max(0.2, cx)), 3),
        center_y=round(min(0.75, max(0.25, cy)), 3),
        box_width=round(bw, 3),
        box_height=round(bh, 3),
    )


def _extract_exif_and_enrich_metadata(item: MediaItem, bgr_frame: Optional[np.ndarray] = None) -> MediaItem:
    """
    Extracts EXIF metadata (Capture Date/Time, Camera Make/Model) using Pillow,
    parses human-readable dance context from filenames (e.g. '093LillianWeiInTheCurrentCont12903.JPG'),
    and optionally enriches with Gemini Vision when configured.
    """
    import re
    from PIL import Image, ExifTags
    from backend.config import settings
    from backend.models.schemas import EventCategory

    path = Path(item.filepath)
    if path.exists() and item.media_type == MediaType.PHOTO:
        try:
            with Image.open(path) as pil_img:
                exif = pil_img.getexif()
                if exif:
                    decoded = {ExifTags.TAGS.get(k, k): v for k, v in exif.items() if k in ExifTags.TAGS}
                    make = str(decoded.get("Make") or "").strip()
                    model = str(decoded.get("Model") or "").strip()
                    if model:
                        if make and not model.lower().startswith(make.lower()):
                            item.camera_model = f"{make} {model}"
                        else:
                            item.camera_model = model
                    dt_raw = str(decoded.get("DateTimeOriginal") or decoded.get("DateTime") or "").strip()
                    if dt_raw and not item.creation_time:
                        # Convert '2026:03:26 11:45:38' -> '2026-03-26 11:45'
                        parts = dt_raw.split(" ")
                        date_part = parts[0].replace(":", "-")
                        time_part = parts[1][:5] if len(parts) > 1 else ""
                        item.creation_time = f"{date_part} {time_part}".strip()
        except Exception:
            pass

    # Parse intelligent dance tags & caption from filename + visual properties
    stem = Path(item.filename).stem
    # Split camelCase like '093LillianWeiInTheCurrentCont12903' -> 'Lillian Wei In The Current Cont'
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", stem)
    words = re.sub(r"[0-9_]+", " ", words).strip()

    inferred_tags = list(dict.fromkeys(item.tags))
    lower_name = f"{item.filename} {words}".lower()

    if "cont" in lower_name or "contemporary" in lower_name:
        inferred_tags.append("Contemporary")
        item.event_category = EventCategory.COMPETITION
    if "lyrical" in lower_name:
        inferred_tags.append("Lyrical")
    if "ballet" in lower_name or "arabesque" in lower_name:
        inferred_tags.append("Ballet")
    if "rehearsal" in lower_name or "studio" in lower_name:
        inferred_tags.append("Rehearsal")
        item.event_category = EventCategory.REHEARSAL
    if "training" in lower_name or "acro" in lower_name:
        inferred_tags.append("Training")
        item.event_category = EventCategory.TRAINING
    if "comp" in lower_name or "stage" in lower_name or "current" in lower_name:
        if "Stage" not in inferred_tags:
            inferred_tags.append("Stage Performance")
        item.event_category = EventCategory.COMPETITION

    aspect_label = "Portrait" if item.height >= item.width else "Landscape Stage"
    if aspect_label not in inferred_tags:
        inferred_tags.append(aspect_label)

    if item.camera_model and "Canon" in item.camera_model and "Pro DSLR" not in inferred_tags:
        inferred_tags.append("Pro Stage Photo")
    elif item.camera_model and "iPhone" in item.camera_model and "Mobile Capture" not in inferred_tags:
        inferred_tags.append("Candid / Mobile")

    # Try Gemini Vision analysis if API key is configured (AIza...) and caption is generic
    used_gemini = False
    if (
        settings.gemini_api_key
        and len(settings.gemini_api_key.strip()) >= 20
        and getattr(_extract_exif_and_enrich_metadata, "_gemini_ok", True)
        and (
            not item.semantic_caption
            or item.semantic_caption.startswith("Imported from")
            or item.semantic_caption.startswith("Dance media")
        )
    ):
        try:
            from google import genai
            from PIL import Image

            if path.exists() and item.media_type == MediaType.PHOTO:
                client = genai.Client(api_key=settings.gemini_api_key)
                with Image.open(path) as img_for_ai:
                    img_copy = img_for_ai.copy()
                    img_copy.thumbnail((768, 768))
                    resp = client.models.generate_content(
                        model=settings.gemini_model,
                        contents=[
                            img_copy,
                            "Describe this dance event photo in one concise sentence (max 18 words) focusing on pose, lighting, or setting, and list 3 short tags separated by commas after a pipe '|'. Example: Poised contemporary floor reach under blue stage lights | Contemporary, Stage Lighting, Extension",
                        ],
                    )
                    txt = (resp.text or "").strip()
                    if txt:
                        parts = txt.split("|")
                        item.semantic_caption = parts[0].strip()
                        if len(parts) > 1:
                            for tg in parts[1].split(","):
                                clean_tg = tg.strip()
                                if clean_tg and clean_tg not in inferred_tags:
                                    inferred_tags.append(clean_tg)
                        used_gemini = True
        except Exception:
            setattr(_extract_exif_and_enrich_metadata, "_gemini_ok", False)


    if not used_gemini and (
        not item.semantic_caption
        or item.semantic_caption.startswith("Imported from")
        or item.semantic_caption.startswith("Dance media")
    ):
        # Generate rich descriptive metadata summary based on visual analysis, EXIF, and parsed filename
        cam_note = f" captured on {item.camera_model}" if item.camera_model else ""
        if len(words) > 4 and not words.lower().startswith("img") and not words.lower().startswith("gp"):
            item.semantic_caption = (
                f"{aspect_label} performance photograph ('{words}'){cam_note} — "
                f"sharpness {int(item.sharpness_score * 100)}%, focal center ({item.focal_point.center_x:.2f}, {item.focal_point.center_y:.2f})."
            )
        else:
            lighting_desc = "warm high-key lighting" if item.aesthetic_score >= 0.75 else "stage spotlight contrast"
            item.semantic_caption = (
                f"{aspect_label} dance event capture{cam_note} with {lighting_desc} — "
                f"focal subject at ({item.focal_point.center_x:.2f}, {item.focal_point.center_y:.2f})."
            )

    item.tags = [t for t in inferred_tags if t not in ("google_photos", "local", "dance", "photo", "video")][:5]
    return item


def analyze_photo_item(item: MediaItem) -> MediaItem:
    """Populates sharpness, aesthetic score, dimensions, focal point, EXIF metadata, and AI/CV tags for a photo."""
    path = Path(item.filepath)
    if not path.exists():
        return item

    img = cv2.imread(str(path))
    if img is None:
        return item

    h, w = img.shape[:2]
    item.width = w
    item.height = h
    item.sharpness_score = compute_sharpness_score(img)
    item.aesthetic_score = compute_aesthetic_score(img, item.sharpness_score)
    item.focal_point = detect_subject_focal_box(img)
    item = _extract_exif_and_enrich_metadata(item, img)
    return item


def analyze_video_dance_kinematics(item: MediaItem) -> MediaItem:
    """
    Analyzes a dance video clip to extract:
    - Duration & dimensions
    - Per-0.25s visual motion energy curve
    - Jump Peak (Apex) events: local minima in vertical centroid y(t) accompanied by launch/landing velocity
    - Turn / Pirouette Spin events: high horizontal optical flow / width oscillation while vertical centroid stays level
    - Pose Hold events: sudden stillness after motion
    """
    path = Path(item.filepath)
    if not path.exists():
        return item

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return item

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    if fps <= 1.0:
        fps = 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1080)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1920)
    duration_sec = round(frame_count / fps, 3) if frame_count > 0 else 4.0

    item.width = width
    item.height = height
    item.duration_sec = duration_sec

    # Sample at ~12 Hz for fast, accurate trajectory & optical flow analysis
    sample_step = max(1, int(round(fps / 12.0)))
    sampled_times: List[float] = []
    centroid_y_series: List[float] = []
    centroid_x_series: List[float] = []
    bbox_width_series: List[float] = []
    motion_energy_series: List[float] = []
    rotational_asymmetry_series: List[float] = []

    prev_gray = None
    mid_frame_bgr = None
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx == frame_count // 2 or mid_frame_bgr is None:
            mid_frame_bgr = frame.copy()

        if frame_idx % sample_step == 0:
            t_sec = frame_idx / fps
            sampled_times.append(t_sec)
            small = cv2.resize(frame, (180, 320))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            if prev_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray, gray, None, 0.5, 2, 13, 2, 5, 1.1, 0
                )
                fx = flow[..., 0]
                fy = flow[..., 1]
                mag = np.sqrt(fx * fx + fy * fy)
                active_mask = mag > 1.2

                energy = float(np.mean(mag))
                motion_energy_series.append(energy)

                # Track the bright foreground dancer subject in the lower 80% of the frame (avoiding top stage lights)
                subject_roi = gray[int(320 * 0.18) :, :]
                _, bright = cv2.threshold(subject_roi, 155, 255, cv2.THRESH_BINARY)
                bys, bxs = np.nonzero(bright)
                if len(bxs) > 20:
                    cy = (float(np.mean(bys)) + 320 * 0.18) / 320.0
                    cx = float(np.mean(bxs)) / 180.0
                    bw = float(np.percentile(bxs, 85) - np.percentile(bxs, 15)) / 180.0
                elif np.any(active_mask):
                    ys, xs = np.nonzero(active_mask)
                    cy = float(np.mean(ys)) / 320.0
                    cx = float(np.mean(xs)) / 180.0
                    bw = float(np.percentile(xs, 85) - np.percentile(xs, 15)) / 180.0
                else:
                    cy = centroid_y_series[-1] if centroid_y_series else 0.58
                    cx = centroid_x_series[-1] if centroid_x_series else 0.50
                    bw = bbox_width_series[-1] if bbox_width_series else 0.30

                if np.any(active_mask):
                    horiz_speed = float(np.mean(np.abs(fx[active_mask])))
                    vert_speed = float(np.mean(np.abs(fy[active_mask]))) + 1e-4
                    spin_ratio = horiz_speed / (vert_speed + 0.35)
                else:
                    spin_ratio = 0.1

                centroid_y_series.append(cy)
                centroid_x_series.append(cx)
                bbox_width_series.append(bw)
                rotational_asymmetry_series.append(spin_ratio)
            else:
                subject_roi = gray[int(320 * 0.18) :, :]
                _, bright = cv2.threshold(subject_roi, 155, 255, cv2.THRESH_BINARY)
                bys, bxs = np.nonzero(bright)
                cy = (float(np.mean(bys)) + 320 * 0.18) / 320.0 if len(bys) > 20 else 0.58
                cx = float(np.mean(bxs)) / 180.0 if len(bxs) > 20 else 0.50
                bw = (
                    float(np.percentile(bxs, 85) - np.percentile(bxs, 15)) / 180.0
                    if len(bxs) > 20
                    else 0.30
                )
                centroid_y_series.append(cy)
                centroid_x_series.append(cx)
                bbox_width_series.append(bw)
                motion_energy_series.append(0.0)
                rotational_asymmetry_series.append(0.0)

            prev_gray = gray

        frame_idx += 1

    cap.release()

    if mid_frame_bgr is not None:
        item.sharpness_score = compute_sharpness_score(mid_frame_bgr)
        item.aesthetic_score = compute_aesthetic_score(mid_frame_bgr, item.sharpness_score)
        item.focal_point = detect_subject_focal_box(mid_frame_bgr)

    if len(sampled_times) < 5:
        return item

    # Normalize motion energy curve
    max_e = max(motion_energy_series) if motion_energy_series else 1.0
    if max_e < 1e-4:
        max_e = 1.0
    norm_energy = [round(min(1.0, e / max_e), 3) for e in motion_energy_series]
    item.energy_curve = norm_energy

    events: List[DanceMovementEvent] = []
    cy_arr = np.array(centroid_y_series, dtype=np.float64)
    if len(cy_arr) >= 5:
        cy_smooth = np.convolve(cy_arr, [0.25, 0.5, 0.25], mode="same")
    else:
        cy_smooth = cy_arr

    median_y = float(np.median(cy_smooth))

    # 1. Detect Jump Peaks (local minimum in screen Y = highest elevation on stage)
    for i in range(2, len(sampled_times) - 2):
        y_val = float(cy_smooth[i])
        elevation_gain = median_y - y_val
        if (
            y_val <= cy_smooth[i - 1]
            and y_val <= cy_smooth[i + 1]
            and y_val < cy_smooth[i - 2]
            and y_val < cy_smooth[i + 2]
            and elevation_gain > 0.045
        ):
            t_peak = round(sampled_times[i], 3)
            if any(
                ev.move_type == DanceMoveType.JUMP_PEAK and abs(ev.timestamp_sec - t_peak) < 1.0
                for ev in events
            ):
                continue
            intensity = round(min(0.99, max(0.65, 0.60 + elevation_gain * 2.8)), 3)
            events.append(
                DanceMovementEvent(
                    move_type=DanceMoveType.JUMP_PEAK,
                    timestamp_sec=t_peak,
                    start_sec=round(max(0.0, t_peak - 0.65), 3),
                    end_sec=round(min(duration_sec, t_peak + 0.65), 3),
                    confidence=round(min(0.98, 0.72 + elevation_gain * 2.0), 3),
                    intensity_score=intensity,
                    description=f"Jump apex detected at {t_peak:.2f}s (elevation +{int(elevation_gain*100)}%)",
                )
            )

    # 2. Detect Turns / Pirouettes (high horizontal spin ratio + width oscillation while Y is near baseline)
    spin_arr = np.array(rotational_asymmetry_series, dtype=np.float64)
    bw_arr = np.array(bbox_width_series, dtype=np.float64)
    bw_diff = np.abs(np.gradient(bw_arr)) if len(bw_arr) > 3 else np.zeros_like(spin_arr)
    combined_spin = spin_arr + bw_diff * 6.0

    for i in range(2, len(sampled_times) - 2):
        s_val = float(combined_spin[i])
        e_val = float(norm_energy[i])
        y_diff = abs(float(cy_smooth[i]) - median_y)
        if (
            s_val >= combined_spin[i - 1]
            and s_val >= combined_spin[i + 1]
            and s_val > 0.65
            and e_val > 0.30
            and y_diff < 0.042
        ):
            t_turn = round(sampled_times[i], 3)
            if any(abs(ev.timestamp_sec - t_turn) < 0.9 for ev in events):
                continue
            events.append(
                DanceMovementEvent(
                    move_type=DanceMoveType.TURN_SPIN,
                    timestamp_sec=t_turn,
                    start_sec=round(max(0.0, t_turn - 0.6), 3),
                    end_sec=round(min(duration_sec, t_turn + 0.6), 3),
                    confidence=round(min(0.96, 0.68 + s_val * 0.15), 3),
                    intensity_score=round(min(0.97, max(0.65, e_val)), 3),
                    description=f"Pirouette / turn velocity peak at {t_turn:.2f}s",
                )
            )

    # 3. Fallback: If neither jump peak nor turn was strongly isolated, mark the highest energy peak
    if not events and len(norm_energy) > 2:
        peak_idx = int(np.argmax(norm_energy))
        t_peak = round(sampled_times[peak_idx], 3)
        filename_lower = item.filename.lower()
        inferred_type = (
            DanceMoveType.TURN_SPIN
            if ("turn" in filename_lower or "spin" in filename_lower or "pirouette" in filename_lower)
            else DanceMoveType.JUMP_PEAK
        )
        events.append(
            DanceMovementEvent(
                move_type=inferred_type,
                timestamp_sec=t_peak,
                start_sec=round(max(0.0, t_peak - 0.7), 3),
                end_sec=round(min(duration_sec, t_peak + 0.7), 3),
                confidence=0.82,
                intensity_score=max(0.75, float(norm_energy[peak_idx])),
                description=f"Choreographic peak ({inferred_type.value}) at {t_peak:.2f}s",
            )
        )

    events.sort(key=lambda e: e.timestamp_sec)
    item.dance_events = events
    item = _extract_exif_and_enrich_metadata(item, mid_frame_bgr)
    return item

