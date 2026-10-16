from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import (
    BASE_DIR,
    EXPORTS_DIR,
    MEDIA_CACHE_DIR,
    MUSIC_DIR,
    SAMPLE_DATA_DIR,
    SESSIONS_DIR,
    UPLOADS_DIR,
    settings,
)
from backend.models.schemas import (
    AudioCueMap,
    CreateSessionRequest,
    ExportArtifactInfo,
    MediaItem,
    StylePreset,
    UpdateTimelineRequest,
    WorkflowSession,
)
from backend.services.audio_analyzer import analyze_audio_file
from backend.services.exporters.capcut_exporter import export_capcut_draft
from backend.services.exporters.fcpxml_exporter import export_fcpxml_project
from backend.services.exporters.mp4_renderer import render_session_mp4
from backend.services.gemini_service import generate_instagram_post_copy
from backend.services.media_ingest import (
    GooglePhotosClient,
    load_and_analyze_sample_dataset,
    scan_local_directory,
    search_and_ingest_media,
)
from backend.services.music_generator import (
    ensure_builtin_music_tracks,
    generate_custom_music_track,
    get_music_track_by_id,
)
from backend.services.style_presets import (
    apply_supplemental_directions_to_preset,
    get_all_presets,
    get_preset_by_id,
)
from backend.services.timeline_composer import compose_beat_synced_timeline


app = FastAPI(
    title="Ins-Creator — AI Dance Instagram Reel & Post Studio",
    version="1.0.0",
    description=(
        "Automated creative workflow for generating beat-synced Instagram Reels, titles, "
        "captions, and CapCut / FCPXML editable timelines from dance rehearsal, training, and competition media."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static media & export directories
app.mount("/static/sample", StaticFiles(directory=str(SAMPLE_DATA_DIR)), name="static_sample")
app.mount("/static/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="static_uploads")
app.mount("/static/cache", StaticFiles(directory=str(MEDIA_CACHE_DIR)), name="static_cache")
app.mount("/static/music", StaticFiles(directory=str(MUSIC_DIR)), name="static_music")
app.mount("/static/exports", StaticFiles(directory=str(EXPORTS_DIR)), name="static_exports")


_SESSIONS_STORE: Dict[str, WorkflowSession] = {}


def _save_session(session: WorkflowSession) -> None:
    _SESSIONS_STORE[session.session_id] = session
    session_file = SESSIONS_DIR / f"{session.session_id}.json"
    session_file.write_text(session.model_dump_json(indent=2), encoding="utf-8")


def _load_session(session_id: str) -> WorkflowSession:
    if session_id in _SESSIONS_STORE:
        return _SESSIONS_STORE[session_id]
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if session_file.exists():
        data = json.loads(session_file.read_text(encoding="utf-8"))
        sess = WorkflowSession(**data)
        _SESSIONS_STORE[session_id] = sess
        return sess
    raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")


class ConfigUpdatePayload(BaseModel):
    gemini_api_key: Optional[str] = None
    google_photos_access_token: Optional[str] = None
    ai_music_api_key: Optional[str] = None


class MusicGeneratePayload(BaseModel):
    prompt: str
    target_duration_sec: float = 18.0
    preferred_bpm: Optional[float] = None


@app.get("/api/health")
def health_check() -> Dict[str, object]:
    return {
        "status": "ok",
        "gemini_configured": bool(settings.gemini_api_key),
        "google_photos_configured": bool(settings.google_photos_access_token),
        "capcut_drafts_dir": str(settings.capcut_drafts_dir),
    }


@app.post("/api/config")
def update_runtime_config(payload: ConfigUpdatePayload) -> Dict[str, object]:
    if payload.gemini_api_key is not None:
        settings.gemini_api_key = payload.gemini_api_key.strip() or None
    if payload.google_photos_access_token is not None:
        settings.google_photos_access_token = payload.google_photos_access_token.strip() or None
    if payload.ai_music_api_key is not None:
        settings.ai_music_api_key = payload.ai_music_api_key.strip() or None
    return {
        "status": "updated",
        "gemini_configured": bool(settings.gemini_api_key),
        "google_photos_configured": bool(settings.google_photos_access_token),
        "ai_music_configured": bool(settings.ai_music_api_key),
    }


@app.get("/api/presets", response_model=List[StylePreset])
def list_style_presets() -> List[StylePreset]:
    return get_all_presets()


@app.get("/api/music/tracks", response_model=List[AudioCueMap])
def list_music_tracks() -> List[AudioCueMap]:
    return ensure_builtin_music_tracks()


@app.post("/api/music/generate", response_model=AudioCueMap)
def create_ai_music_track(payload: MusicGeneratePayload) -> AudioCueMap:
    return generate_custom_music_track(
        prompt=payload.prompt,
        target_duration_sec=payload.target_duration_sec,
        preferred_bpm=payload.preferred_bpm,
    )


@app.post("/api/music/upload", response_model=AudioCueMap)
async def upload_custom_music(file: UploadFile = File(...)) -> AudioCueMap:
    filename = file.filename or f"custom_audio_{uuid.uuid4().hex[:6]}.wav"
    safe_name = f"upload_{uuid.uuid4().hex[:6]}_{Path(filename).name}"
    target_path = MUSIC_DIR / safe_name
    content = await file.read()
    target_path.write_bytes(content)

    track_id = f"custom_{uuid.uuid4().hex[:8]}"
    cue_map = analyze_audio_file(
        filepath=str(target_path),
        track_id=track_id,
        title=f"Uploaded Track: {Path(filename).stem}",
        url=f"/static/music/{safe_name}",
        genre="custom_upload",
        is_generated=False,
    )
    return cue_map


@app.get("/api/media/search", response_model=List[MediaItem])
def search_media_endpoint(
    query: str = "daughter dance rehearsal competition leaps and turns",
    source: str = "auto",
    local_folder_path: Optional[str] = None,
    google_photos_session_id: Optional[str] = None,
) -> List[MediaItem]:
    return search_and_ingest_media(
        query=query,
        media_source=source,
        local_folder_path=local_folder_path,
        google_photos_session_id=google_photos_session_id,
    )


@app.post("/api/media/google-photos/picker-session")
def start_google_photos_picker_session() -> Dict[str, object]:
    client = GooglePhotosClient()
    return client.create_picker_session()


@app.post("/api/media/upload", response_model=List[MediaItem])
async def upload_media_files(
    files: List[UploadFile] = File(...),
    query: str = Form(default="dance event"),
) -> List[MediaItem]:
    for f in files:
        fname = Path(f.filename or f"media_{uuid.uuid4().hex[:6]}.jpg").name
        dst = UPLOADS_DIR / fname
        data = await f.read()
        dst.write_bytes(data)

    return scan_local_directory(str(UPLOADS_DIR), query=query)


@app.post("/api/sessions/generate", response_model=WorkflowSession)
def generate_workflow_session(req: CreateSessionRequest) -> WorkflowSession:
    """
    Executes the full automated workflow:
    1. Fetches and ranks photos & videos matching `req.search_query` from Google Photos / Local / Sample
    2. Applies the chosen StylePreset + user's `req.supplemental_directions`
    3. Selects or generates the music track and extracts Downbeats, Beats, Sustained Notes, and Pauses
    4. Composes the beat-synced choreographic timeline (slip-syncing Jump Peaks & Turns to Downbeats,
       inserting Photos during Sustained Notes & Pauses with Ken Burns effects)
    5. Generates attractive Instagram Title Hook, Headline, 3-variant Captions, and Hashtags
    6. Renders the 9:16 vertical MP4 video and exports the editable CapCut Desktop Draft + FCPXML
    """
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    base_preset = get_preset_by_id(req.style_preset_id)
    active_preset = apply_supplemental_directions_to_preset(
        base_preset, req.supplemental_directions
    )

    # 1. Media Ingestion & Dance Kinematics Analysis
    all_matched = search_and_ingest_media(
        query=req.search_query,
        media_source=req.media_source,
        local_folder_path=req.local_folder_path,
        google_photos_session_id=req.google_photos_session_id,
    )
    if req.selected_media_ids:
        selected_set = set(req.selected_media_ids)
        filtered = [m for m in all_matched if m.id in selected_set]
        if filtered:
            all_matched = filtered

    # 2. Music Track Selection / Generation & Cue Analysis
    if req.music_generation_prompt and req.music_generation_prompt.strip():
        audio_cue_map = generate_custom_music_track(
            prompt=req.music_generation_prompt,
            target_duration_sec=req.target_duration_sec,
        )
    elif req.music_track_id:
        audio_cue_map = get_music_track_by_id(req.music_track_id)
    else:
        audio_cue_map = get_music_track_by_id(active_preset.default_music_genre)

    # 3. Beat-Synced Choreographic Timeline Assembly
    target_dur = req.target_duration_sec or active_preset.target_duration_sec
    timeline_clips = compose_beat_synced_timeline(
        matched_media=all_matched,
        audio_cue_map=audio_cue_map,
        preset=active_preset,
        supplemental_directions=req.supplemental_directions,
        target_duration_sec=target_dur,
    )

    # 4. Attractive Instagram Titles, Captions & Hashtags
    post_copy = generate_instagram_post_copy(
        search_query=req.search_query,
        style_preset=active_preset,
        supplemental_directions=req.supplemental_directions,
        matched_media=all_matched,
        timeline_clips=timeline_clips,
        audio_cue_map=audio_cue_map,
    )

    media_lookup = {m.id: m for m in all_matched}
    exports_info = ExportArtifactInfo()

    # 5. Render Direct MP4 Video
    if req.auto_render_mp4:
        mp4_path = render_session_mp4(
            session_id=session_id,
            timeline_clips=timeline_clips,
            media_lookup=media_lookup,
            audio_cue_map=audio_cue_map,
            post_copy=post_copy,
            color_grade=active_preset.color_grade_preset,
        )
        exports_info.mp4_filepath = str(mp4_path)
        exports_info.mp4_url = f"/static/exports/{mp4_path.name}?t={int(datetime.datetime.now().timestamp())}"
        exports_info.last_rendered_at = created_at

    # 6. Export Editable CapCut Desktop Draft & FCPXML
    if req.auto_export_capcut:
        project_title = f"DanceReel_{active_preset.name.replace(' ', '_')}_{session_id}"
        draft_dir, zip_path, installed = export_capcut_draft(
            session_id=session_id,
            project_title=project_title,
            timeline_clips=timeline_clips,
            media_lookup=media_lookup,
            audio_cue_map=audio_cue_map,
            post_copy=post_copy,
            install_to_local_capcut=True,
        )
        fcpxml_path = export_fcpxml_project(
            session_id=session_id,
            project_title=project_title,
            timeline_clips=timeline_clips,
            media_lookup=media_lookup,
            audio_cue_map=audio_cue_map,
            post_copy=post_copy,
        )
        exports_info.capcut_draft_path = str(draft_dir)
        exports_info.capcut_zip_url = f"/static/exports/{zip_path.name}"
        exports_info.capcut_installed_to_app = installed
        exports_info.fcpxml_filepath = str(fcpxml_path)
        exports_info.fcpxml_url = f"/static/exports/{fcpxml_path.name}"

    session = WorkflowSession(
        session_id=session_id,
        created_at=created_at,
        search_query=req.search_query,
        event_category=active_preset.event_focus,
        style_preset_id=active_preset.id,
        supplemental_directions=req.supplemental_directions,
        target_duration_sec=target_dur,
        media_source=req.media_source,
        matched_media=all_matched,
        audio_cue_map=audio_cue_map,
        timeline_clips=timeline_clips,
        post_copy=post_copy,
        exports=exports_info,
        color_grade=active_preset.color_grade_preset,
    )
    _save_session(session)
    return session


@app.get("/api/sessions", response_model=List[WorkflowSession])
def list_sessions() -> List[WorkflowSession]:
    sessions: List[WorkflowSession] = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), reverse=True)[:15]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append(WorkflowSession(**data))
        except Exception:
            continue
    return sessions


@app.get("/api/sessions/{session_id}", response_model=WorkflowSession)
def get_session(session_id: str) -> WorkflowSession:
    return _load_session(session_id)


@app.put("/api/sessions/{session_id}/timeline", response_model=WorkflowSession)
def update_session_timeline(
    session_id: str, req: UpdateTimelineRequest
) -> WorkflowSession:
    """Updates the interactive timeline, post copy, or color grade, and re-exports CapCut/FCPXML/MP4."""
    session = _load_session(session_id)

    # Recompute sequential start/end times if clip durations or order changed
    cursor = 0.0
    updated_clips = []
    for idx, clip in enumerate(req.timeline_clips):
        clip.index = idx
        clip.timeline_start_sec = round(cursor, 2)
        clip.timeline_end_sec = round(cursor + clip.duration_sec, 2)
        cursor = clip.timeline_end_sec
        updated_clips.append(clip)

    session.timeline_clips = updated_clips
    if req.post_copy is not None:
        session.post_copy = req.post_copy
    if req.color_grade is not None:
        session.color_grade = req.color_grade

    media_lookup = {m.id: m for m in session.matched_media}
    for m in load_and_analyze_sample_dataset():
        if m.id not in media_lookup:
            media_lookup[m.id] = m

    project_title = f"DanceReel_{session.session_id}"
    draft_dir, zip_path, installed = export_capcut_draft(
        session_id=session.session_id,
        project_title=project_title,
        timeline_clips=session.timeline_clips,
        media_lookup=media_lookup,
        audio_cue_map=session.audio_cue_map,
        post_copy=session.post_copy,
        install_to_local_capcut=True,
    )
    fcpxml_path = export_fcpxml_project(
        session_id=session.session_id,
        project_title=project_title,
        timeline_clips=session.timeline_clips,
        media_lookup=media_lookup,
        audio_cue_map=session.audio_cue_map,
        post_copy=session.post_copy,
    )
    session.exports.capcut_draft_path = str(draft_dir)
    session.exports.capcut_zip_url = f"/static/exports/{zip_path.name}"
    session.exports.capcut_installed_to_app = installed
    session.exports.fcpxml_filepath = str(fcpxml_path)
    session.exports.fcpxml_url = f"/static/exports/{fcpxml_path.name}"

    if req.re_render_mp4:
        mp4_path = render_session_mp4(
            session_id=session.session_id,
            timeline_clips=session.timeline_clips,
            media_lookup=media_lookup,
            audio_cue_map=session.audio_cue_map,
            post_copy=session.post_copy,
            color_grade=session.color_grade,
        )
        session.exports.mp4_filepath = str(mp4_path)
        session.exports.mp4_url = (
            f"/static/exports/{mp4_path.name}?t={int(datetime.datetime.now().timestamp())}"
        )
        session.exports.last_rendered_at = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()

    _save_session(session)
    return session


@app.post("/api/sessions/{session_id}/export-capcut", response_model=WorkflowSession)
def trigger_capcut_export(session_id: str) -> WorkflowSession:
    session = _load_session(session_id)
    media_lookup = {m.id: m for m in session.matched_media}
    project_title = f"DanceReel_{session.session_id}"
    draft_dir, zip_path, installed = export_capcut_draft(
        session_id=session.session_id,
        project_title=project_title,
        timeline_clips=session.timeline_clips,
        media_lookup=media_lookup,
        audio_cue_map=session.audio_cue_map,
        post_copy=session.post_copy,
        install_to_local_capcut=True,
    )
    session.exports.capcut_draft_path = str(draft_dir)
    session.exports.capcut_zip_url = f"/static/exports/{zip_path.name}"
    session.exports.capcut_installed_to_app = installed
    _save_session(session)
    return session


FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend_assets")


@app.get("/")
def serve_spa_root():
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Ins-Creator API is running. Visit /docs or build frontend."}

