from __future__ import annotations

import json
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import DanceMoveType, MediaType, PhotoEffectType


client = TestClient(app)


def test_health_and_presets() -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"

    presets_resp = client.get("/api/presets")
    assert presets_resp.status_code == 200
    presets = presets_resp.json()
    assert len(presets) >= 6
    ids = {p["id"] for p in presets}
    assert "competition_stage_glory" in ids
    assert "lyrical_graceful_flow" in ids
    assert "rehearsal_gritty_raw" in ids


def test_music_tracks_and_cue_extraction() -> None:
    r = client.get("/api/music/tracks")
    assert r.status_code == 200
    tracks = r.json()
    assert len(tracks) >= 4
    first = tracks[0]
    assert first["bpm"] > 70
    assert len(first["beat_times"]) >= 8
    assert len(first["downbeat_times"]) >= 2
    assert len(first["sections"]) >= 2
    cue_types = {s["cue_type"] for s in first["sections"]}
    assert "pause" in cue_types or "sustained_note" in cue_types


def test_ai_custom_music_generation() -> None:
    r = client.post(
        "/api/music/generate",
        json={
            "prompt": "Dramatic contemporary lyrical piano build with big competition leaps",
            "target_duration_sec": 15.0,
        },
    )
    assert r.status_code == 200
    cue_map = r.json()
    assert cue_map["is_generated"] is True
    assert Path(cue_map["filepath"]).exists()
    assert len(cue_map["downbeat_times"]) >= 2


def test_media_search_and_dance_kinematics() -> None:
    r = client.get(
        "/api/media/search",
        params={
            "query": "daughter contemporary competition split leap and pirouette turns",
            "source": "sample",
        },
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 6
    videos = [m for m in items if m["media_type"] == "video"]
    photos = [m for m in items if m["media_type"] == "photo"]
    assert len(videos) >= 3
    assert len(photos) >= 2

    # Verify jump peaks and turns are detected on the videos
    move_types = set()
    for v in videos:
        assert len(v["dance_events"]) >= 1
        for ev in v["dance_events"]:
            move_types.add(ev["move_type"])
    assert DanceMoveType.JUMP_PEAK.value in move_types
    assert DanceMoveType.TURN_SPIN.value in move_types


def test_end_to_end_session_generation_and_exports() -> None:
    r = client.post(
        "/api/sessions/generate",
        json={
            "search_query": "daughter dance competition split leap and rehearsal turns",
            "media_source": "sample",
            "style_preset_id": "competition_stage_glory",
            "supplemental_directions": (
                "Sync her highest jump peak to the main downbeat, insert a graceful stage photo "
                "during the sustained note with Ken Burns zoom, and make the title inspiring."
            ),
            "target_duration_sec": 14.0,
            "auto_render_mp4": True,
            "auto_export_capcut": True,
        },
    )
    assert r.status_code == 200
    session = r.json()

    # 1. Verify timeline clips include both downbeat-synced videos and sustained/pause photos with Ken Burns
    clips = session["timeline_clips"]
    assert len(clips) >= 4
    video_clips = [c for c in clips if c["media_type"] == MediaType.VIDEO.value]
    photo_clips = [c for c in clips if c["media_type"] == MediaType.PHOTO.value]
    assert len(video_clips) >= 2
    assert len(photo_clips) >= 1

    # Verify photo clip has Ken Burns / visual effect and is placed on sustained note or pause
    for pc in photo_clips:
        assert pc["photo_effect"] is not None
        assert "photo" in pc["synced_cue_type"]

    # Verify video clip has slip-sync explanation aligning jump peak or turn to a downbeat
    for vc in video_clips:
        assert vc["synced_beat_timestamp"] is not None
        assert vc["source_out_sec"] > vc["source_in_sec"]

    # 2. Verify attractive Instagram post titles, captions, and hashtags
    post_copy = session["post_copy"]
    assert post_copy is not None
    assert len(post_copy["hook_title_overlay"]) > 5
    assert len(post_copy["post_headline"]) > 5
    assert len(post_copy["caption_primary"]) > 40
    assert len(post_copy["caption_alternatives"]) >= 2
    assert len(post_copy["hashtags"]) >= 8

    # 3. Verify rendered MP4 file exists and is non-empty
    exports = session["exports"]
    mp4_path = Path(exports["mp4_filepath"])
    assert mp4_path.exists()
    assert mp4_path.stat().st_size > 15_000

    # 4. Verify CapCut Desktop Draft & FCPXML exports exist and are valid
    capcut_dir = Path(exports["capcut_draft_path"])
    assert (capcut_dir / "draft_content.json").exists()
    assert (capcut_dir / "draft_meta_info.json").exists()
    draft_json = json.loads((capcut_dir / "draft_content.json").read_text(encoding="utf-8"))
    assert draft_json["canvas_config"]["ratio"] == "9:16"
    assert len(draft_json["tracks"]) == 3

    fcpxml_path = Path(exports["fcpxml_filepath"])
    assert fcpxml_path.exists()
    assert "<fcpxml" in fcpxml_path.read_text(encoding="utf-8")

    # 5. Verify interactive timeline update endpoint works
    session_id = session["session_id"]
    clips[0]["photo_effect"] = PhotoEffectType.KEN_BURNS_PAN_DIAG.value
    update_resp = client.put(
        f"/api/sessions/{session_id}/timeline",
        json={
            "timeline_clips": clips,
            "post_copy": post_copy,
            "color_grade": "vivid_hype",
            "re_render_mp4": False,
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["color_grade"] == "vivid_hype"


def test_video_trim_photo_transition_styles_and_editorial_title() -> None:
    search_resp = client.get("/api/media/search", params={"query": "dance", "source": "sample"})
    items = search_resp.json()
    videos = [m for m in items if m["media_type"] == MediaType.VIDEO.value]
    assert len(videos) >= 1
    first_vid_id = videos[0]["id"]

    # Generate session with manual video portion trim
    r = client.post(
        "/api/sessions/generate",
        json={
            "search_query": "dance competition",
            "media_source": "sample",
            "selected_media_ids": [m["id"] for m in items[:4]],
            "media_trims": {
                first_vid_id: {
                    "trim_mode": "manual",
                    "trim_start_sec": 0.6,
                    "trim_end_sec": 2.8,
                }
            },
            "style_preset_id": "competition_stage_glory",
            "target_duration_sec": 10.0,
            "auto_render_mp4": False,
            "auto_export_capcut": False,
        },
    )
    assert r.status_code == 200
    session = r.json()
    session_id = session["session_id"]
    clips = session["timeline_clips"]

    # Check that manual trim bounds were respected for first_vid_id
    vid_clips = [c for c in clips if c["media_id"] == first_vid_id]
    assert len(vid_clips) >= 1
    assert vid_clips[0]["source_in_sec"] >= 0.55

    # Test new photo styles, new transitions, and editorial title styles with MP4 render
    photo_styles = ["polaroid_frame", "tilt_up_stage", "spotlight_vignette", "soft_glow_dissolve"]
    transitions = ["cross_dissolve", "slide_left", "light_leak_warm", "blur_dissolve"]
    for idx, c in enumerate(clips):
        if c["media_type"] == MediaType.PHOTO.value:
            c["photo_effect"] = photo_styles[idx % len(photo_styles)]
        c["transition_in"] = transitions[idx % len(transitions)]

    post_copy = session["post_copy"]
    post_copy["video_title_style"] = "frosted_pill"

    update_resp = client.put(
        f"/api/sessions/{session_id}/timeline",
        json={
            "timeline_clips": clips,
            "post_copy": post_copy,
            "color_grade": "warm_stage",
            "re_render_mp4": True,
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["post_copy"]["video_title_style"] == "frosted_pill"
    mp4_path = Path(updated["exports"]["mp4_filepath"])
    assert mp4_path.exists()
    assert mp4_path.stat().st_size > 10_000



def test_builtin_tracks_have_distinct_detected_cues() -> None:
    """Each built-in track's pause/sustained windows must be found where they were synthesized."""
    from backend.services.music_generator import BUILT_IN_TRACK_SPECS

    tracks = {t["track_id"]: t for t in client.get("/api/music/tracks").json()}
    signatures = set()
    for spec in BUILT_IN_TRACK_SPECS:
        cue = tracks[spec["track_id"]]
        kinds = {s["cue_type"]: s for s in cue["sections"]}
        assert "pause" in kinds and "sustained_note" in kinds
        p0, p1 = spec["pause_window"]
        s0, s1 = spec["sustained_window"]
        assert abs(kinds["pause"]["start_sec"] - p0) < 0.8
        assert abs(kinds["sustained_note"]["start_sec"] - s0) < 0.8
        assert len(cue["sections"]) <= 4  # no longer blanket-marks the whole track
        signatures.add(tuple((s["cue_type"], s["start_sec"]) for s in cue["sections"]))
    assert len(signatures) == len(BUILT_IN_TRACK_SPECS)


def test_unknown_music_track_is_rejected_not_silently_swapped() -> None:
    r = client.post(
        "/api/sessions/generate",
        json={"media_source": "sample", "music_track_id": "custom_doesnotexist", "auto_render_mp4": False, "auto_export_capcut": False},
    )
    assert r.status_code == 404
    assert "no longer available" in r.json()["detail"]


def test_progress_tracking_and_hook_preview() -> None:
    task_id = "test_task_progress_1"
    r = client.post(
        "/api/sessions/generate",
        headers={"X-Task-Id": task_id},
        json={"media_source": "sample", "target_duration_sec": 8.0, "auto_render_mp4": True, "auto_export_capcut": False},
    )
    assert r.status_code == 200
    prog = client.get(f"/api/progress/{task_id}").json()
    assert prog["status"] == "done"
    assert prog["percent"] == 100.0
    stages = " ".join(e["stage"] for e in prog["log"])
    assert "Rendering clip" in stages
    assert any(e["service"] for e in prog["log"])

    styles = client.get("/api/hook-styles").json()["styles"]
    assert len(styles) >= 10
    session_id = r.json()["session_id"]
    for st in styles:
        img = client.get(
            "/api/preview/hook-frame",
            params={"text": "Lillian's Flight 莉莲", "style": st["id"], "session_id": session_id, "width": 180},
        )
        assert img.status_code == 200
        assert img.headers["content-type"] == "image/jpeg"
        assert len(img.content) > 2000

    # Regenerating the post copy keeps the chosen on-screen text style
    post_copy = r.json()["post_copy"]
    post_copy.update({"video_title_style": "neon_glow", "hook_text_animation": "typewriter", "hook_text_position": "top", "hook_duration_sec": 3.4})
    upd = client.put(
        f"/api/sessions/{session_id}/timeline",
        json={"timeline_clips": r.json()["timeline_clips"], "post_copy": post_copy, "re_render_mp4": True},
    )
    assert upd.status_code == 200
    regen = client.post(f"/api/sessions/{session_id}/post-copy", json={"custom_prompt": "short"}).json()
    assert regen["post_copy"]["video_title_style"] == "neon_glow"
    assert regen["post_copy"]["hook_text_animation"] == "typewriter"
    assert regen["post_copy"]["hook_duration_sec"] == 3.4
