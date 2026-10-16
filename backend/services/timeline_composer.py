from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple

from backend.models.schemas import (
    AudioCueMap,
    AudioSectionCue,
    DanceMoveType,
    DanceMovementEvent,
    MediaItem,
    MediaType,
    PhotoEffectType,
    StylePreset,
    TimelineClip,
    TransitionType,
)


def _build_musical_slots(
    audio_cue_map: AudioCueMap,
    preset: StylePreset,
    target_duration_sec: float,
) -> List[Dict[str, object]]:
    """
    Partitions the timeline `[0, target_duration_sec]` into beat-aligned choreographic slots.
    Each slot is tagged as:
    - `'sustained_note_photo'` or `'musical_pause_photo'` if it overlaps a detected sustained note or pause
    - `'downbeat_action'` if it contains or starts on a measure downbeat
    """
    total_dur = min(float(target_duration_sec), float(audio_cue_map.duration_sec))
    if total_dur < 6.0:
        total_dur = min(14.0, float(audio_cue_map.duration_sec))

    # Determine slot duration from cut pacing & BPM
    bpm = max(70.0, min(180.0, audio_cue_map.bpm))
    beat_sec = 60.0 / bpm
    if preset.cut_pacing == "fast_hype":
        nominal_slot = max(1.8, round(beat_sec * 4.0, 2))
    elif preset.cut_pacing == "slow_lyrical":
        nominal_slot = max(2.8, round(beat_sec * 6.0, 2))
    else:
        nominal_slot = max(2.2, round(beat_sec * 4.0, 2))

    # Build boundary anchors from downbeats + sustained/pause section boundaries
    downbeats = [d for d in audio_cue_map.downbeat_times if 0.2 <= d <= total_dur - 0.8]
    if not downbeats:
        downbeats = [round(t, 2) for t in range(2, int(total_dur), 2)]

    # Build sequential slots snapped to downbeats or section cues
    slots: List[Dict[str, object]] = []
    cursor = 0.0

    # Index audio sections (sustained notes & pauses) inside [0, total_dur]
    valid_sections: List[AudioSectionCue] = [
        s for s in audio_cue_map.sections if s.start_sec < total_dur - 1.0 and s.end_sec > 1.2
    ]

    while cursor < total_dur - 0.9:
        # Check if cursor is entering or very close to a sustained note or pause section
        matching_sec: Optional[AudioSectionCue] = None
        for sec in valid_sections:
            if abs(sec.start_sec - cursor) <= 0.9 or (sec.start_sec <= cursor < sec.end_sec - 0.8):
                matching_sec = sec
                break

        if matching_sec is not None:
            slot_end = min(total_dur, max(cursor + 1.6, min(matching_sec.end_sec, cursor + 2.8)))
            # Snap slot_end to nearest beat if close
            nearest_beats = [b for b in audio_cue_map.beat_times if abs(b - slot_end) <= 0.35]
            if nearest_beats:
                slot_end = nearest_beats[0]
            slot_end = round(min(total_dur, slot_end), 2)
            cue_label = (
                "musical_pause_photo" if matching_sec.cue_type == "pause" else "sustained_note_photo"
            )
            slots.append(
                {
                    "start_sec": round(cursor, 2),
                    "end_sec": slot_end,
                    "duration_sec": round(slot_end - cursor, 2),
                    "slot_type": "photo",
                    "cue_type": cue_label,
                    "target_beat_sec": round((cursor + slot_end) * 0.5, 2),
                    "section_desc": matching_sec.description,
                }
            )
            valid_sections.remove(matching_sec)
            cursor = slot_end
            continue

        # Otherwise create a video action slot targeting a downbeat inside `[cursor + 0.4, slot_end - 0.3]`
        raw_end = min(total_dur, cursor + nominal_slot)
        # If there is an upcoming section start soon, stop right at that section start
        upcoming_sec = [
            s for s in valid_sections if cursor + 1.4 <= s.start_sec <= raw_end + 0.6
        ]
        if upcoming_sec:
            slot_end = round(upcoming_sec[0].start_sec, 2)
        else:
            # Snap to nearest downbeat or beat near raw_end
            cand_beats = [b for b in audio_cue_map.beat_times if abs(b - raw_end) <= 0.45]
            slot_end = round(cand_beats[0] if cand_beats else raw_end, 2)

        if total_dur - slot_end < 1.2:
            slot_end = round(total_dur, 2)

        slot_dur = round(slot_end - cursor, 2)
        # Find the primary downbeat inside this slot (or nearest beat near middle of slot) for apex slip-sync!
        inner_downbeats = [
            d for d in downbeats if (cursor + 0.35) <= d <= (slot_end - 0.25)
        ]
        if inner_downbeats:
            target_downbeat = inner_downbeats[0]
        else:
            inner_beats = [
                b for b in audio_cue_map.beat_times if (cursor + 0.3) <= b <= (slot_end - 0.2)
            ]
            target_downbeat = (
                inner_beats[len(inner_beats) // 2]
                if inner_beats
                else round(cursor + slot_dur * 0.55, 2)
            )

        slots.append(
            {
                "start_sec": round(cursor, 2),
                "end_sec": slot_end,
                "duration_sec": slot_dur,
                "slot_type": "video",
                "cue_type": "downbeat_action",
                "target_beat_sec": round(float(target_downbeat), 2),
                "section_desc": f"Downbeat hit at {target_downbeat:.2f}s",
            }
        )
        cursor = slot_end

    # Ensure at least one photo slot exists if photos are available
    if not any(s["slot_type"] == "photo" for s in slots) and len(slots) >= 3:
        mid_idx = len(slots) // 2
        slots[mid_idx]["slot_type"] = "photo"
        slots[mid_idx]["cue_type"] = "sustained_note_photo"
        slots[mid_idx]["section_desc"] = "Sustained harmonic phrase for photo highlight"

    return slots


def _compute_slip_sync_trim(
    video_item: MediaItem,
    event: Optional[DanceMovementEvent],
    slot_start_sec: float,
    slot_duration_sec: float,
    target_downbeat_sec: float,
    min_bound_sec: float = 0.0,
    max_bound_sec: Optional[float] = None,
) -> Tuple[float, float, float]:
    """
    Calculates `(source_in_sec, source_out_sec, apex_source_sec)` so that `event.timestamp_sec`
    (the jump peak or turn peak) lands strictly at `target_downbeat_sec` on the output timeline,
    respecting optional manual `[min_bound_sec, max_bound_sec]` bounds.
    """
    clip_dur = max(1.5, float(video_item.duration_sec or 4.0))
    lo = max(0.0, min(clip_dur - 0.5, float(min_bound_sec or 0.0)))
    hi = min(clip_dur, float(max_bound_sec if max_bound_sec is not None and max_bound_sec > lo else clip_dur))
    avail_span = max(0.8, hi - lo)

    offset_to_beat = max(0.3, min(slot_duration_sec - 0.25, target_downbeat_sec - slot_start_sec))

    if event is not None:
        apex_sec = float(event.timestamp_sec)
    else:
        apex_sec = lo + avail_span * 0.5

    desired_in = apex_sec - offset_to_beat
    max_in = max(lo, hi - slot_duration_sec)
    source_in = round(min(max_in, max(lo, desired_in)), 2)
    source_out = round(min(clip_dur, source_in + slot_duration_sec), 2)
    return source_in, source_out, round(apex_sec, 2)


def compose_beat_synced_timeline(
    matched_media: List[MediaItem],
    audio_cue_map: AudioCueMap,
    preset: StylePreset,
    supplemental_directions: str = "",
    target_duration_sec: float = 16.0,
) -> List[TimelineClip]:
    """
    Assembles the complete beat-synced edit timeline:
    1. Builds musical slots from `audio_cue_map` (downbeat action slots + sustained note / pause photo slots).
    2. For each video slot, supports both:
       - Automatic mode: picks distinct, non-overlapping Jump Peak or Turn Spin events and slip-syncs them to downbeats.
       - Manual mode: uses the user's selected `[trim_start_sec, trim_end_sec]` portion of the video.
    3. For each sustained note or pause slot, inserts a curated still photo with a Ken Burns or stage visual effect.
    """
    videos = [m for m in matched_media if m.media_type == MediaType.VIDEO]
    photos = [m for m in matched_media if m.media_type == MediaType.PHOTO]

    videos.sort(
        key=lambda v: (
            v.query_match_score * 0.6
            + v.aesthetic_score * 0.4
            + (max((e.intensity_score for e in v.dance_events), default=0.5) * 0.3)
        ),
        reverse=True,
    )
    photos.sort(
        key=lambda p: (p.query_match_score * 0.6 + p.aesthetic_score * 0.4),
        reverse=True,
    )

    slots = _build_musical_slots(
        audio_cue_map=audio_cue_map,
        preset=preset,
        target_duration_sec=target_duration_sec,
    )

    photo_effects = preset.preferred_photo_effects or [
        PhotoEffectType.KEN_BURNS_ZOOM_IN,
        PhotoEffectType.KEN_BURNS_PAN_DIAG,
        PhotoEffectType.KEN_BURNS_ZOOM_OUT,
        PhotoEffectType.SOFT_GLOW_DISSOLVE,
        PhotoEffectType.SPOTLIGHT_VIGNETTE,
    ]
    transitions = preset.preferred_transitions or [
        TransitionType.CUT_ON_BEAT,
        TransitionType.CROSS_DISSOLVE,
        TransitionType.FLASH_WHITE,
    ]

    timeline: List[TimelineClip] = []
    vid_idx = 0
    photo_idx = 0
    used_peaks_by_video: Dict[str, List[float]] = {}
    manual_cursor_by_video: Dict[str, float] = {}

    for idx, slot in enumerate(slots):
        s_start = float(slot["start_sec"])
        s_end = float(slot["end_sec"])
        s_dur = float(slot["duration_sec"])
        slot_type = str(slot["slot_type"])
        cue_type = str(slot["cue_type"])
        target_beat = float(slot["target_beat_sec"])

        use_photo = (slot_type == "photo" and len(photos) > 0) or (len(videos) == 0 and len(photos) > 0)

        if use_photo:
            p_item = photos[photo_idx % len(photos)]
            photo_idx += 1
            effect = photo_effects[(photo_idx - 1) % len(photo_effects)]
            trans = TransitionType.CROSS_DISSOLVE if "sustained" in cue_type else TransitionType.FLASH_WHITE

            cue_label_human = (
                "Musical Pause / Breath"
                if "pause" in cue_type
                else "Sustained Harmonic Note"
            )
            effect_human = effect.value.replace("_", " ").title()

            timeline.append(
                TimelineClip(
                    clip_id=f"clip_{idx+1}_{uuid.uuid4().hex[:6]}",
                    index=idx,
                    media_id=p_item.id,
                    filename=p_item.filename,
                    media_type=MediaType.PHOTO,
                    media_url=p_item.url,
                    timeline_start_sec=s_start,
                    timeline_end_sec=s_end,
                    duration_sec=s_dur,
                    source_in_sec=0.0,
                    source_out_sec=s_dur,
                    playback_speed=1.0,
                    synced_cue_type=cue_type,
                    synced_beat_timestamp=target_beat,
                    matched_dance_move=DanceMoveType.POSE_HOLD,
                    matched_move_source_sec=0.0,
                    sync_explanation=(
                        f"Inserted photo during {cue_label_human} ({s_start:.1f}s–{s_end:.1f}s) "
                        f"with {effect_human} focused on dancer ({p_item.focal_point.center_x:.2f}, {p_item.focal_point.center_y:.2f})."
                    ),
                    photo_effect=effect,
                    transition_in=trans,
                    focal_point=p_item.focal_point,
                )
            )
        else:
            v_item = videos[vid_idx % len(videos)]
            vid_idx += 1
            used_peaks = used_peaks_by_video.setdefault(v_item.id, [])

            clip_total_dur = max(1.5, float(v_item.duration_sec or 4.0))
            is_manual = (
                v_item.trim_mode == "manual"
                and v_item.trim_start_sec is not None
            )
            t_min = float(v_item.trim_start_sec or 0.0) if is_manual else 0.0
            t_max = (
                float(v_item.trim_end_sec)
                if (is_manual and v_item.trim_end_sec is not None and v_item.trim_end_sec > t_min + 0.5)
                else clip_total_dur
            )

            # Filter candidate dance events within [t_min, t_max]
            candidate_events = [
                ev for ev in v_item.dance_events if (t_min - 0.2) <= ev.timestamp_sec <= (t_max + 0.2)
            ]
            if not candidate_events and not is_manual:
                candidate_events = list(v_item.dance_events)

            chosen_ev: Optional[DanceMovementEvent] = None
            if candidate_events:
                # Prefer high-intensity peaks that haven't been used in an earlier slot yet
                unused = [
                    ev
                    for ev in sorted(candidate_events, key=lambda e: e.intensity_score, reverse=True)
                    if all(abs(ev.timestamp_sec - prev_t) >= 2.0 for prev_t in used_peaks)
                ]
                chosen_ev = unused[0] if unused else candidate_events[(len(used_peaks)) % len(candidate_events)]
                used_peaks.append(chosen_ev.timestamp_sec)

            if is_manual and chosen_ev is None:
                # Step cleanly through the user's manually selected [t_min, t_max] window
                cur_pos = manual_cursor_by_video.get(v_item.id, t_min)
                if cur_pos + s_dur > t_max + 0.2:
                    cur_pos = t_min
                src_in = round(max(0.0, min(clip_total_dur - s_dur, cur_pos)), 2)
                src_out = round(min(clip_total_dur, src_in + s_dur), 2)
                apex_src_sec = round((src_in + src_out) * 0.5, 2)
                manual_cursor_by_video[v_item.id] = src_out
            else:
                src_in, src_out, apex_src_sec = _compute_slip_sync_trim(
                    video_item=v_item,
                    event=chosen_ev,
                    slot_start_sec=s_start,
                    slot_duration_sec=s_dur,
                    target_downbeat_sec=target_beat,
                    min_bound_sec=t_min,
                    max_bound_sec=t_max,
                )

            move_type = chosen_ev.move_type if chosen_ev else DanceMoveType.JUMP_PEAK
            move_label = "Jump Apex" if move_type == DanceMoveType.JUMP_PEAK else "Pirouette / Turn Peak"
            synced_cue = (
                "downbeat_jump_peak"
                if move_type == DanceMoveType.JUMP_PEAK
                else "downbeat_turn"
            )
            speed_curve = (
                "1.15x approach -> 0.55x slow-mo at downbeat apex -> 1.0x"
                if preset.speed_ramp_on_peaks
                else None
            )
            trans = transitions[idx % len(transitions)]

            if is_manual:
                sync_desc = (
                    f"Manual video segment [{src_in:.2f}s–{src_out:.2f}s] (from selected range {t_min:.1f}s–{t_max:.1f}s) "
                    f"aligned to Downbeat @ {target_beat:.2f}s."
                )
            else:
                sync_desc = (
                    f"Auto slip-synced [{src_in:.2f}s–{src_out:.2f}s] so {move_label} "
                    f"(at {apex_src_sec:.2f}s in source) lands directly on Downbeat @ {target_beat:.2f}s."
                )

            timeline.append(
                TimelineClip(
                    clip_id=f"clip_{idx+1}_{uuid.uuid4().hex[:6]}",
                    index=idx,
                    media_id=v_item.id,
                    filename=v_item.filename,
                    media_type=MediaType.VIDEO,
                    media_url=v_item.url,
                    timeline_start_sec=s_start,
                    timeline_end_sec=s_end,
                    duration_sec=s_dur,
                    source_in_sec=src_in,
                    source_out_sec=src_out,
                    playback_speed=1.0,
                    speed_ramp_curve=speed_curve,
                    synced_cue_type=synced_cue,
                    synced_beat_timestamp=target_beat,
                    matched_dance_move=move_type,
                    matched_move_source_sec=apex_src_sec,
                    sync_explanation=sync_desc,
                    photo_effect=None,
                    transition_in=trans,
                    focal_point=v_item.focal_point,
                )
            )

    return timeline
