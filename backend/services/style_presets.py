from __future__ import annotations

from typing import Dict, List, Optional
from backend.models.schemas import (
    EventCategory,
    PhotoEffectType,
    StylePreset,
    TransitionType,
)


STYLE_PRESETS: List[StylePreset] = [
    StylePreset(
        id="competition_stage_glory",
        name="Competition Stage Glory",
        tagline="Dramatic build, speed-ramped leaps on heavy downbeats & stage warmth",
        description=(
            "Designed for dance competition solos and group numbers. Aligns jump apexes "
            "and rapid turns right onto major measure downbeats with speed-ramping, "
            "inserts poised stage photos during sustained musical notes, and applies a golden spotlight grade."
        ),
        event_focus=EventCategory.COMPETITION,
        default_music_genre="competition_edm_pop",
        target_duration_sec=16.0,
        video_to_photo_ratio=0.75,
        cut_pacing="medium_dynamic",
        preferred_photo_effects=[
            PhotoEffectType.KEN_BURNS_ZOOM_IN,
            PhotoEffectType.BEAT_PULSE_ZOOM,
            PhotoEffectType.KEN_BURNS_PAN_DIAG,
        ],
        preferred_transitions=[
            TransitionType.FLASH_WHITE,
            TransitionType.CUT_ON_BEAT,
            TransitionType.ZOOM_WHIP,
        ],
        color_grade_preset="warm_stage",
        speed_ramp_on_peaks=True,
        caption_tone="proud_inspiring",
        badge_color="#f59e0b",
    ),
    StylePreset(
        id="lyrical_graceful_flow",
        name="Lyrical & Graceful Flow",
        tagline="Poetic piano & strings, slow-mo extensions, and dreamy Ken Burns pans",
        description=(
            "Tailored for ballet, contemporary, and lyrical routines. Emphasizes fluid extensions, "
            "gentle cross-dissolves, slow-motion peaks on harmonic swells, and expressive photo "
            "features during sustained notes and musical breaths."
        ),
        event_focus=EventCategory.SHOWCASE,
        default_music_genre="lyrical_piano_strings",
        target_duration_sec=18.0,
        video_to_photo_ratio=0.60,
        cut_pacing="slow_lyrical",
        preferred_photo_effects=[
            PhotoEffectType.KEN_BURNS_ZOOM_IN,
            PhotoEffectType.KEN_BURNS_ZOOM_OUT,
            PhotoEffectType.SOFT_GLOW_DISSOLVE,
        ],
        preferred_transitions=[
            TransitionType.CROSS_DISSOLVE,
            TransitionType.CUT_ON_BEAT,
        ],
        color_grade_preset="soft_pastel",
        speed_ramp_on_peaks=True,
        caption_tone="poetic_emotional",
        badge_color="#a855f7",
    ),
    StylePreset(
        id="rehearsal_gritty_raw",
        name="Studio Rehearsal: Grit & Glow",
        tagline="Behind-the-scenes hustle, crisp studio beats & candid photo flashes",
        description=(
            "Captures the dedication of dance rehearsal—counts, sweat, corrections, and breakthroughs. "
            "Uses punchy snare/beat cuts, inserts candid studio photos during musical pauses, and pairs "
            "with an authentic growth-mindset caption."
        ),
        event_focus=EventCategory.REHEARSAL,
        default_music_genre="studio_hiphop_beat",
        target_duration_sec=15.0,
        video_to_photo_ratio=0.70,
        cut_pacing="fast_hype",
        preferred_photo_effects=[
            PhotoEffectType.BEAT_PULSE_ZOOM,
            PhotoEffectType.KEN_BURNS_PAN_LEFT_RIGHT,
            PhotoEffectType.KEN_BURNS_ZOOM_IN,
        ],
        preferred_transitions=[
            TransitionType.CUT_ON_BEAT,
            TransitionType.FLASH_WHITE,
        ],
        color_grade_preset="crisp_studio",
        speed_ramp_on_peaks=False,
        caption_tone="dedication_grit",
        badge_color="#ec4899",
    ),
    StylePreset(
        id="training_technique_spotlight",
        name="Technique & Progress Spotlight",
        tagline="Precision jump apexes, clean pirouette spotting & milestone storytelling",
        description=(
            "Ideal for dance training sessions (flexibility, turns, leaps, acro). Slows down right at "
            "the jump peak or turn finish on the downbeat so viewers can admire form and technique."
        ),
        event_focus=EventCategory.TRAINING,
        default_music_genre="contemporary_dramatic_build",
        target_duration_sec=16.0,
        video_to_photo_ratio=0.65,
        cut_pacing="medium_dynamic",
        preferred_photo_effects=[
            PhotoEffectType.KEN_BURNS_ZOOM_IN,
            PhotoEffectType.KEN_BURNS_PAN_DIAG,
        ],
        preferred_transitions=[
            TransitionType.CUT_ON_BEAT,
            TransitionType.CROSS_DISSOLVE,
        ],
        color_grade_preset="crisp_studio",
        speed_ramp_on_peaks=True,
        caption_tone="technique_milestone",
        badge_color="#06b6d4",
    ),
    StylePreset(
        id="high_energy_hype_reel",
        name="High-Energy 8-Count Hype",
        tagline="Rapid-fire beat drops, zoom pulses & electrifying competition energy",
        description=(
            "Built for jazz, hip-hop, pom, and upbeat numbers. Every downbeat triggers a high-energy "
            "action cut or beat-pulsed photo with bold kinetic energy."
        ),
        event_focus=EventCategory.COMPETITION,
        default_music_genre="competition_edm_pop",
        target_duration_sec=14.0,
        video_to_photo_ratio=0.80,
        cut_pacing="fast_hype",
        preferred_photo_effects=[
            PhotoEffectType.BEAT_PULSE_ZOOM,
            PhotoEffectType.KEN_BURNS_ZOOM_IN,
        ],
        preferred_transitions=[
            TransitionType.ZOOM_WHIP,
            TransitionType.FLASH_WHITE,
            TransitionType.CUT_ON_BEAT,
        ],
        color_grade_preset="vivid_hype",
        speed_ramp_on_peaks=True,
        caption_tone="short_punchy_hype",
        badge_color="#ef4444",
    ),
    StylePreset(
        id="memory_lane_storyteller",
        name="Proud Parent Storyteller",
        tagline="Warm cinematic memories blending backstage smiles with stage magic",
        description=(
            "Balances heartfelt candid photos (getting ready, hugs, smiles) during gentle musical "
            "sustained notes with show-stopping dance clips on the chorus downbeats."
        ),
        event_focus=EventCategory.GENERAL,
        default_music_genre="lyrical_piano_strings",
        target_duration_sec=18.0,
        video_to_photo_ratio=0.50,
        cut_pacing="slow_lyrical",
        preferred_photo_effects=[
            PhotoEffectType.KEN_BURNS_ZOOM_IN,
            PhotoEffectType.KEN_BURNS_ZOOM_OUT,
            PhotoEffectType.KEN_BURNS_PAN_LEFT_RIGHT,
        ],
        preferred_transitions=[
            TransitionType.CROSS_DISSOLVE,
            TransitionType.FLASH_WHITE,
        ],
        color_grade_preset="vintage_film",
        speed_ramp_on_peaks=True,
        caption_tone="heartfelt_parent",
        badge_color="#10b981",
    ),
]


PRESET_MAP: Dict[str, StylePreset] = {p.id: p for p in STYLE_PRESETS}


def get_all_presets() -> List[StylePreset]:
    return STYLE_PRESETS


def get_preset_by_id(preset_id: str) -> StylePreset:
    return PRESET_MAP.get(preset_id, STYLE_PRESETS[0])


def apply_supplemental_directions_to_preset(
    preset: StylePreset, supplemental_directions: str
) -> StylePreset:
    """Dynamically adapts preset parameters based on the user's free-text supplemental prompt."""
    modified = preset.model_copy(deep=True)
    if not supplemental_directions:
        return modified

    text = supplemental_directions.lower()
    if any(k in text for k in ["fast", "hype", "energetic", "upbeat", "quick"]):
        modified.cut_pacing = "fast_hype"
    elif any(k in text for k in ["slow", "calm", "graceful", "lyrical", "gentle", "emotional"]):
        modified.cut_pacing = "slow_lyrical"

    if any(k in text for k in ["more photo", "mostly photo", "lots of photo"]):
        modified.video_to_photo_ratio = 0.4
    elif any(k in text for k in ["more video", "mostly video", "action"]):
        modified.video_to_photo_ratio = 0.8

    if "ken burns" in text or "zoom" in text:
        modified.preferred_photo_effects = [
            PhotoEffectType.KEN_BURNS_ZOOM_IN,
            PhotoEffectType.KEN_BURNS_PAN_DIAG,
            PhotoEffectType.KEN_BURNS_ZOOM_OUT,
        ]
    if "no speed" in text or "normal speed" in text:
        modified.speed_ramp_on_peaks = False
    elif "slow mo" in text or "speed ramp" in text or "apex" in text or "jump" in text:
        modified.speed_ramp_on_peaks = True

    return modified
