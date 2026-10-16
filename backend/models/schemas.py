from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class MediaType(str, Enum):
    VIDEO = "video"
    PHOTO = "photo"


class EventCategory(str, Enum):
    REHEARSAL = "dance_rehearsal"
    TRAINING = "dance_training"
    COMPETITION = "dance_competition"
    SHOWCASE = "dance_showcase"
    GENERAL = "general"


class DanceMoveType(str, Enum):
    JUMP_PEAK = "jump_peak"
    TURN_SPIN = "turn_spin"
    POSE_HOLD = "pose_hold"
    HIGH_ENERGY = "high_energy"
    GRACEFUL_FLOW = "graceful_flow"


class PhotoEffectType(str, Enum):
    KEN_BURNS_ZOOM_IN = "ken_burns_zoom_in"
    KEN_BURNS_ZOOM_OUT = "ken_burns_zoom_out"
    KEN_BURNS_PAN_LEFT_RIGHT = "ken_burns_pan_lr"
    KEN_BURNS_PAN_RIGHT_LEFT = "ken_burns_pan_rl"
    KEN_BURNS_PAN_DIAG = "ken_burns_pan_diag"
    TILT_UP_STAGE = "tilt_up_stage"
    BEAT_PULSE_ZOOM = "beat_pulse_zoom"
    SOFT_GLOW_DISSOLVE = "soft_glow_dissolve"
    SPOTLIGHT_VIGNETTE = "spotlight_vignette"
    POLAROID_FRAME = "polaroid_frame"


class TransitionType(str, Enum):
    CUT_ON_BEAT = "cut_on_beat"
    CROSS_DISSOLVE = "cross_dissolve"
    FLASH_WHITE = "flash_white"
    DIP_TO_BLACK = "dip_to_black"
    ZOOM_WHIP = "zoom_whip"
    SLIDE_LEFT = "slide_left"
    SLIDE_UP = "slide_up"
    LIGHT_LEAK_WARM = "light_leak_warm"
    BLUR_DISSOLVE = "blur_dissolve"


class DanceMovementEvent(BaseModel):
    """Represents a detected choreographic peak inside a video clip."""

    move_type: DanceMoveType
    timestamp_sec: float = Field(..., description="Exact timestamp in clip where peak occurs (e.g. jump apex)")
    start_sec: float = Field(..., description="Start of the movement phrase")
    end_sec: float = Field(..., description="End of the movement phrase")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    intensity_score: float = Field(default=0.8, ge=0.0, le=1.0)
    description: str = Field(default="")


class BoundingBoxCenter(BaseModel):
    """Normalized [0..1] focal point of the dancer for smart Ken Burns & 9:16 crop."""

    center_x: float = 0.5
    center_y: float = 0.45
    box_width: float = 0.5
    box_height: float = 0.7


class MediaItem(BaseModel):
    """A photo or video clip ingested from Google Photos or Local Storage."""

    id: str
    filename: str
    filepath: str
    url: str
    thumbnail_url: Optional[str] = None
    media_type: MediaType
    width: int = 1080
    height: int = 1920
    duration_sec: float = 0.0
    creation_time: Optional[str] = None
    camera_model: Optional[str] = None
    event_category: EventCategory = EventCategory.GENERAL
    tags: List[str] = Field(default_factory=list)
    semantic_caption: str = ""
    sharpness_score: float = 0.8
    aesthetic_score: float = 0.85
    energy_curve: List[float] = Field(default_factory=list, description="Per-0.25s normalized visual motion energy")
    dance_events: List[DanceMovementEvent] = Field(default_factory=list)
    focal_point: BoundingBoxCenter = Field(default_factory=BoundingBoxCenter)
    source: str = "local"  # "google_photos", "local", "sample", "upload"
    query_match_score: float = 1.0
    trim_mode: str = "auto"  # "auto" or "manual"
    trim_start_sec: Optional[float] = None
    trim_end_sec: Optional[float] = None


class AudioSectionCue(BaseModel):
    """Sustained note, pause/breath, or high-energy drop section in the music track."""

    cue_type: str = Field(..., description="'sustained_note', 'pause', 'drop_build', or 'chorus_peak'")
    start_sec: float
    end_sec: float
    duration_sec: float
    intensity: float = 0.5
    description: str = ""


class AudioCueMap(BaseModel):
    """Musical structure extracted by Librosa from the active music track."""

    track_id: str
    title: str
    filepath: str
    url: str
    duration_sec: float
    bpm: float
    beat_times: List[float] = Field(default_factory=list, description="All beat timestamps in seconds")
    downbeat_times: List[float] = Field(
        default_factory=list,
        description="Measure downbeats (the '1' and '5' count in 8-count choreography)",
    )
    onset_peaks: List[float] = Field(default_factory=list)
    sections: List[AudioSectionCue] = Field(
        default_factory=list,
        description="Sustained notes, pauses, and energy drops for intelligent photo/video placement",
    )
    energy_envelope: List[float] = Field(default_factory=list, description="Normalized RMS envelope @ 10Hz")
    harmonic_ratio_envelope: List[float] = Field(default_factory=list)
    genre: str = "dance_pop"
    is_generated: bool = False


class StylePreset(BaseModel):
    """Curated creative style preset for Instagram dance reels."""

    id: str
    name: str
    tagline: str
    description: str
    event_focus: EventCategory
    default_music_genre: str
    target_duration_sec: float = 16.0
    video_to_photo_ratio: float = 0.7
    cut_pacing: str = "medium_dynamic"  # "fast_hype", "medium_dynamic", "slow_lyrical"
    preferred_photo_effects: List[PhotoEffectType] = Field(default_factory=list)
    preferred_transitions: List[TransitionType] = Field(default_factory=list)
    color_grade_preset: str = "warm_stage"  # "warm_stage", "crisp_studio", "soft_pastel", "vivid_hype", "vintage_film"
    speed_ramp_on_peaks: bool = True
    caption_tone: str = "proud_inspiring"
    badge_color: str = "#ec4899"


class TimelineClip(BaseModel):
    """Single item placed on the beat-synced edit timeline."""

    clip_id: str
    index: int
    media_id: str
    filename: str
    media_type: MediaType
    media_url: str
    # Timeline coordinates (in output video seconds)
    timeline_start_sec: float
    timeline_end_sec: float
    duration_sec: float
    # Source media trim coordinates
    source_in_sec: float = 0.0
    source_out_sec: float = 0.0
    playback_speed: float = 1.0
    speed_ramp_curve: Optional[str] = None  # e.g. "1.2x -> 0.5x apex -> 1.0x"
    # Sync & Cue metadata
    synced_cue_type: str = Field(
        default="downbeat",
        description="Why this clip was placed here: 'downbeat_jump_peak', 'downbeat_turn', 'sustained_note_photo', 'musical_pause_photo', 'beat_flow'",
    )
    synced_beat_timestamp: Optional[float] = None
    matched_dance_move: Optional[DanceMoveType] = None
    matched_move_source_sec: Optional[float] = None
    sync_explanation: str = ""
    # Visual effects & overlays
    photo_effect: Optional[PhotoEffectType] = None
    transition_in: TransitionType = TransitionType.CUT_ON_BEAT
    text_overlay: Optional[str] = None
    focal_point: BoundingBoxCenter = Field(default_factory=BoundingBoxCenter)


class InstagramPostCopy(BaseModel):
    """Attractive titles, hooks, captions, and hashtags for the Instagram post."""

    hook_title_overlay: str = Field(..., description="Punchy on-screen title hook for first 2.5s of the Reel")
    ending_call_to_action: str = Field(default="Keep shining on stage ✨")
    video_title_style: str = Field(
        default="bold_center_impact",
        description="Hook/closing text style id (see title_styles.HOOK_TEXT_STYLES), or 'none'",
    )
    hook_text_animation: str = Field(default="auto", description="auto | none | fade_in | pop_in | slide_up | typewriter")
    hook_text_position: str = Field(default="auto", description="auto | top | center | bottom")
    hook_duration_sec: float = Field(default=2.6, ge=0.8, le=8.0)
    post_headline: str = Field(..., description="Attractive main title/headline for the Instagram post")
    caption_primary: str = Field(..., description="Full storytelling Instagram caption")
    caption_alternatives: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Alternative captions (e.g. Short & Hype, Technique & Growth, Proud Parent)",
    )
    hashtags: Union[List[Dict[str, str]], List[str]] = Field(default_factory=list)
    music_credit_note: str = ""


class ExportArtifactInfo(BaseModel):
    """Information about rendered MP4, CapCut Draft, or FCPXML exports."""

    mp4_url: Optional[str] = None
    mp4_filepath: Optional[str] = None
    capcut_draft_path: Optional[str] = None
    capcut_zip_url: Optional[str] = None
    capcut_installed_to_app: bool = False
    fcpxml_url: Optional[str] = None
    fcpxml_filepath: Optional[str] = None
    last_rendered_at: Optional[str] = None


class WorkflowSession(BaseModel):
    """Complete state of a user's creative Instagram Reel session."""

    session_id: str
    created_at: str
    search_query: str
    event_category: EventCategory = EventCategory.COMPETITION
    style_preset_id: str = "competition_stage_glory"
    supplemental_directions: str = ""
    target_duration_sec: float = 16.0
    media_source: str = "sample"  # "google_photos", "local", "sample"
    matched_media: List[MediaItem] = Field(default_factory=list)
    audio_cue_map: Optional[AudioCueMap] = None
    timeline_clips: List[TimelineClip] = Field(default_factory=list)
    post_copy: Optional[InstagramPostCopy] = None
    exports: ExportArtifactInfo = Field(default_factory=ExportArtifactInfo)
    color_grade: str = "warm_stage"


class CreateSessionRequest(BaseModel):
    """Request payload to run the automated workflow from a search query & style."""

    search_query: str = Field(
        default="daughter contemporary dance competition leaps and turns",
        description="Search query to fetch and rank photos & videos",
    )
    media_source: str = Field(default="auto", description="'google_photos', 'local', or 'auto'")
    local_folder_path: Optional[str] = None
    google_photos_session_id: Optional[str] = None
    style_preset_id: str = "competition_stage_glory"
    supplemental_directions: str = Field(
        default="Highlight her highest split leap on the biggest beat drop, insert a smiling backstage photo during the soft piano pause, and write an inspiring proud parent caption.",
    )
    music_track_id: Optional[str] = None
    music_generation_prompt: Optional[str] = None
    target_duration_sec: float = 16.0
    selected_media_ids: Optional[List[str]] = None
    media_trims: Optional[Dict[str, Dict[str, Any]]] = None
    auto_render_mp4: bool = True
    auto_export_capcut: bool = True


class UpdateTimelineRequest(BaseModel):
    """Payload for interactive timeline edits in the web studio."""

    timeline_clips: List[TimelineClip]
    post_copy: Optional[InstagramPostCopy] = None
    color_grade: Optional[str] = None
    re_render_mp4: bool = False
