from __future__ import annotations

import json
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.config import EXPORTS_DIR, settings
from backend.models.schemas import (
    AudioCueMap,
    InstagramPostCopy,
    MediaItem,
    MediaType,
    PhotoEffectType,
    TimelineClip,
)


def _sec_to_us(seconds: float) -> int:
    """Converts seconds to CapCut microseconds (`1s = 1,000,000 us`)."""
    return int(round(seconds * 1_000_000))


def _build_capcut_keyframes_for_photo(
    effect: Optional[PhotoEffectType], duration_us: int
) -> List[Dict[str, object]]:
    """Generates CapCut scale/position keyframes for Ken Burns photo effects."""
    if not effect:
        return []

    start_scale = 1.0
    end_scale = 1.18
    if effect == PhotoEffectType.KEN_BURNS_ZOOM_OUT:
        start_scale, end_scale = 1.20, 1.0
    elif effect == PhotoEffectType.BEAT_PULSE_ZOOM:
        start_scale, end_scale = 1.05, 1.22

    return [
        {
            "id": str(uuid.uuid4()).upper(),
            "keyframe_list": [
                {
                    "id": str(uuid.uuid4()).upper(),
                    "time_offset": 0,
                    "values": [start_scale, start_scale],
                    "curveType": "Line",
                },
                {
                    "id": str(uuid.uuid4()).upper(),
                    "time_offset": duration_us,
                    "values": [end_scale, end_scale],
                    "curveType": "Line",
                },
            ],
            "property_type": "KFTypeScaleX",
        }
    ]


def export_capcut_draft(
    session_id: str,
    project_title: str,
    timeline_clips: List[TimelineClip],
    media_lookup: Dict[str, MediaItem],
    audio_cue_map: Optional[AudioCueMap],
    post_copy: Optional[InstagramPostCopy],
    install_to_local_capcut: bool = True,
) -> Tuple[Path, Path, bool]:
    """
    Generates a complete CapCut Desktop Draft folder (`draft_content.json`, `draft_meta_info.json`,
    and bundled `Resources/` media) plus a downloadable `.zip` archive.
    Also installs the draft directly into macOS CapCut Desktop's `com.lveditor.draft` directory
    when available so the user can open CapCut and immediately edit the timeline interactively.
    """
    draft_folder_name = f"InsCreator_{session_id}"
    staging_dir = EXPORTS_DIR / "capcut_drafts" / draft_folder_name
    resources_dir = staging_dir / "Resources"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    resources_dir.mkdir(parents=True, exist_ok=True)

    now_us = int(time.time() * 1_000_000)
    total_duration_sec = max((c.timeline_end_sec for c in timeline_clips), default=15.0)
    total_duration_us = _sec_to_us(total_duration_sec)

    video_materials: List[Dict[str, object]] = []
    audio_materials: List[Dict[str, object]] = []
    text_materials: List[Dict[str, object]] = []
    speeds_materials: List[Dict[str, object]] = []

    video_segments: List[Dict[str, object]] = []
    audio_segments: List[Dict[str, object]] = []
    text_segments: List[Dict[str, object]] = []

    # 1. Build video & photo materials + segments
    for clip in timeline_clips:
        media_item = media_lookup.get(clip.media_id)
        src_path = Path(media_item.filepath) if media_item else None
        bundled_path_str = ""
        if src_path and src_path.exists():
            dst_file = resources_dir / src_path.name
            if not dst_file.exists():
                shutil.copy2(src_path, dst_file)
            # Point to absolute path so CapCut on this Mac resolves it immediately
            bundled_path_str = str(dst_file.resolve())

        mat_id = str(uuid.uuid4()).upper()
        speed_id = str(uuid.uuid4()).upper()
        is_photo = clip.media_type == MediaType.PHOTO

        video_materials.append(
            {
                "id": mat_id,
                "type": "photo" if is_photo else "video",
                "path": bundled_path_str,
                "material_name": clip.filename,
                "width": media_item.width if media_item else 1080,
                "height": media_item.height if media_item else 1920,
                "duration": _sec_to_us(media_item.duration_sec if (media_item and not is_photo) else 10.0),
                "crop": {
                    "lower_left_x": 0.0,
                    "lower_left_y": 1.0,
                    "lower_right_x": 1.0,
                    "lower_right_y": 1.0,
                    "upper_left_x": 0.0,
                    "upper_left_y": 0.0,
                    "upper_right_x": 1.0,
                    "upper_right_y": 0.0,
                },
            }
        )

        speeds_materials.append(
            {
                "id": speed_id,
                "speed": clip.playback_speed,
                "mode": 0,
                "type": "speed",
            }
        )

        seg_dur_us = _sec_to_us(clip.duration_sec)
        src_start_us = _sec_to_us(clip.source_in_sec) if not is_photo else 0
        target_start_us = _sec_to_us(clip.timeline_start_sec)

        keyframes = (
            _build_capcut_keyframes_for_photo(clip.photo_effect, seg_dur_us)
            if is_photo
            else []
        )

        video_segments.append(
            {
                "id": str(uuid.uuid4()).upper(),
                "material_id": mat_id,
                "extra_material_refs": [speed_id],
                "source_timerange": {
                    "start": src_start_us,
                    "duration": seg_dur_us,
                },
                "target_timerange": {
                    "start": target_start_us,
                    "duration": seg_dur_us,
                },
                "speed": clip.playback_speed,
                "volume": 0.0,  # Muted camera audio so beat-synced music track is clean
                "visible": True,
                "common_keyframes": keyframes,
                "clip": {
                    "alpha": 1.0,
                    "flip": {"horizontal": False, "vertical": False},
                    "rotation": 0.0,
                    "scale": {"x": 1.0, "y": 1.0},
                    "transform": {"x": 0.0, "y": 0.0},
                },
                "custom_meta": {
                    "synced_cue_type": clip.synced_cue_type,
                    "synced_beat_timestamp": clip.synced_beat_timestamp,
                    "matched_dance_move": clip.matched_dance_move.value if clip.matched_dance_move else None,
                    "photo_effect": clip.photo_effect.value if clip.photo_effect else None,
                    "sync_explanation": clip.sync_explanation,
                },
            }
        )

    # 2. Build synced Audio Track + Beat Markers
    beat_markers: List[Dict[str, object]] = []
    if audio_cue_map:
        audio_src = Path(audio_cue_map.filepath)
        bundled_audio_str = ""
        if audio_src.exists():
            dst_audio = resources_dir / audio_src.name
            if not dst_audio.exists():
                shutil.copy2(audio_src, dst_audio)
            bundled_audio_str = str(dst_audio.resolve())

        audio_mat_id = str(uuid.uuid4()).upper()
        audio_materials.append(
            {
                "id": audio_mat_id,
                "type": "extract_music",
                "name": audio_cue_map.title,
                "path": bundled_audio_str,
                "duration": _sec_to_us(audio_cue_map.duration_sec),
                "bpm": audio_cue_map.bpm,
            }
        )
        audio_segments.append(
            {
                "id": str(uuid.uuid4()).upper(),
                "material_id": audio_mat_id,
                "source_timerange": {"start": 0, "duration": total_duration_us},
                "target_timerange": {"start": 0, "duration": total_duration_us},
                "volume": 1.0,
                "visible": True,
            }
        )

        for db in audio_cue_map.downbeat_times:
            if db <= total_duration_sec:
                beat_markers.append(
                    {
                        "time_us": _sec_to_us(db),
                        "label": f"Downbeat (1-Count) @ {db:.2f}s",
                        "level": 2,
                    }
                )
        for sec in audio_cue_map.sections:
            if sec.start_sec <= total_duration_sec:
                beat_markers.append(
                    {
                        "time_us": _sec_to_us(sec.start_sec),
                        "label": f"{sec.cue_type.upper()} ({sec.start_sec:.1f}s-{sec.end_sec:.1f}s)",
                        "level": 3,
                    }
                )

    # 3. Build Title Hook & Ending Call-To-Action Text Track
    if post_copy:
        hook_mat_id = str(uuid.uuid4()).upper()
        text_materials.append(
            {
                "id": hook_mat_id,
                "type": "text",
                "content": json.dumps(
                    {
                        "text": post_copy.hook_title_overlay,
                        "styles": [{"fill": {"content": {"solid": {"color": [1.0, 1.0, 1.0]}}}, "size": 11.0}],
                    }
                ),
            }
        )
        text_segments.append(
            {
                "id": str(uuid.uuid4()).upper(),
                "material_id": hook_mat_id,
                "target_timerange": {"start": 0, "duration": _sec_to_us(2.6)},
                "visible": True,
            }
        )

    draft_content = {
        "id": str(uuid.uuid4()).upper(),
        "name": project_title,
        "version": 360000,
        "fps": 30.0,
        "duration": total_duration_us,
        "canvas_config": {
            "width": 1080,
            "height": 1920,
            "ratio": "9:16",
        },
        "materials": {
            "videos": video_materials,
            "audios": audio_materials,
            "texts": text_materials,
            "speeds": speeds_materials,
            "beats": beat_markers,
        },
        "tracks": [
            {
                "id": str(uuid.uuid4()).upper(),
                "type": "video",
                "segments": video_segments,
            },
            {
                "id": str(uuid.uuid4()).upper(),
                "type": "audio",
                "segments": audio_segments,
            },
            {
                "id": str(uuid.uuid4()).upper(),
                "type": "text",
                "segments": text_segments,
            },
        ],
    }

    draft_meta_info = {
        "draft_id": str(uuid.uuid4()).upper(),
        "draft_name": project_title,
        "draft_fold_path": str(staging_dir.resolve()),
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_duration": total_duration_us,
    }

    (staging_dir / "draft_content.json").write_text(
        json.dumps(draft_content, indent=2), encoding="utf-8"
    )
    (staging_dir / "draft_meta_info.json").write_text(
        json.dumps(draft_meta_info, indent=2), encoding="utf-8"
    )

    # Create downloadable ZIP archive
    zip_path = EXPORTS_DIR / f"{session_id}_capcut_draft.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_p in staging_dir.rglob("*"):
            if file_p.is_file():
                zf.write(file_p, file_p.relative_to(staging_dir.parent))

    # Optionally install directly into macOS CapCut Desktop Drafts directory
    installed_to_app = False
    if install_to_local_capcut:
        try:
            target_root = settings.capcut_drafts_dir
            target_root.mkdir(parents=True, exist_ok=True)
            app_draft_dir = target_root / draft_folder_name
            if app_draft_dir.exists():
                shutil.rmtree(app_draft_dir)
            shutil.copytree(staging_dir, app_draft_dir)
            installed_to_app = True
        except Exception:
            installed_to_app = False

    return staging_dir, zip_path, installed_to_app
