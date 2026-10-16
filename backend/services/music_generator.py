from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import soundfile as sf
import httpx

from backend.config import MUSIC_DIR, settings
from backend.models.schemas import AudioCueMap
from backend.services.audio_analyzer import analyze_audio_file


BUILT_IN_TRACK_SPECS: List[Dict[str, object]] = [
    {
        "track_id": "competition_edm_pop",
        "title": "Stage Spotlight Drop (Competition Pop/EDM - 124 BPM)",
        "genre": "competition_edm_pop",
        "bpm": 124.0,
        "duration_sec": 20.0,
        "chord_freqs": [(261.63, 329.63, 392.00), (220.00, 261.63, 329.63), (174.61, 220.00, 261.63), (196.00, 246.94, 293.66)],
        "pause_window": (6.2, 7.9),
        "sustained_window": (12.0, 14.2),
    },
    {
        "track_id": "lyrical_piano_strings",
        "title": "Golden Hour Arabesque (Lyrical Piano & Strings - 96 BPM)",
        "genre": "lyrical_piano_strings",
        "bpm": 96.0,
        "duration_sec": 20.0,
        "chord_freqs": [(293.66, 369.99, 440.00), (246.94, 293.66, 369.99), (196.00, 246.94, 293.66), (220.00, 277.18, 329.63)],
        "pause_window": (5.0, 6.8),
        "sustained_window": (10.5, 13.0),
    },
    {
        "track_id": "studio_hiphop_beat",
        "title": "8-Count Studio Hustle (Rehearsal Groove - 112 BPM)",
        "genre": "studio_hiphop_beat",
        "bpm": 112.0,
        "duration_sec": 20.0,
        "chord_freqs": [(220.00, 261.63, 329.63), (196.00, 246.94, 293.66), (174.61, 220.00, 261.63), (164.81, 207.65, 246.94)],
        "pause_window": (6.6, 8.3),
        "sustained_window": (13.0, 14.8),
    },
    {
        "track_id": "contemporary_dramatic_build",
        "title": "Velocity & Flight (Contemporary Cinematic Build - 118 BPM)",
        "genre": "contemporary_dramatic_build",
        "bpm": 118.0,
        "duration_sec": 20.0,
        "chord_freqs": [(261.63, 311.13, 392.00), (207.65, 261.63, 311.13), (233.08, 293.66, 349.23), (196.00, 246.94, 293.66)],
        "pause_window": (5.5, 7.2),
        "sustained_window": (11.4, 13.6),
    },
]


def _synthesize_dance_track_wav(
    filepath: Path,
    bpm: float,
    duration_sec: float,
    chord_freqs: List[tuple],
    pause_window: tuple,
    sustained_window: tuple,
    style_hint: str = "",
) -> None:
    """
    Synthesizes a rich, musically structured WAV audio track with:
    - Crisp measure downbeat sub-bass + kick accents (every 4 beats)
    - Regular beat kick & snare/clap pulse
    - Warm harmonic pad/piano chords
    - Explicit Sustained Harmonic Note section (no percussion, rich shimmering chord)
    - Explicit Musical Pause / Breath section (near-silent atmospheric shimmer before a big drop)
    """
    sr = 22050
    n_samples = int(duration_sec * sr)
    t = np.linspace(0.0, duration_sec, n_samples, endpoint=False)
    audio = np.zeros(n_samples, dtype=np.float64)

    beat_interval = 60.0 / bpm
    beat_times = np.arange(0.4, duration_sec - 0.3, beat_interval)

    p_start, p_end = pause_window
    s_start, s_end = sustained_window

    # 1. Harmonic Chords & Melodic Pad
    measure_dur = beat_interval * 4.0
    for idx, f_tuple in enumerate(chord_freqs * 6):
        m_start = idx * measure_dur
        if m_start >= duration_sec:
            break
        m_end = min(duration_sec, m_start + measure_dur)
        s_idx = int(m_start * sr)
        e_idx = int(m_end * sr)
        seg_t = t[s_idx:e_idx] - m_start
        env = np.minimum(1.0, seg_t / 0.15) * np.exp(-seg_t * 0.35)
        chord_wave = np.zeros_like(seg_t)
        for f in f_tuple:
            chord_wave += 0.14 * np.sin(2 * np.pi * f * seg_t)
            chord_wave += 0.06 * np.sin(2 * np.pi * (f * 2.0) * seg_t)
        audio[s_idx:e_idx] += chord_wave * env

    # 2. Dedicated Sustained Harmonic Note Section (boost warm string/piano sustain, suppress drums)
    s_i0, s_i1 = int(s_start * sr), min(n_samples, int(s_end * sr))
    if s_i1 > s_i0:
        seg_t = t[s_i0:s_i1] - s_start
        swell_env = np.sin(np.pi * seg_t / max(0.2, (s_end - s_start)))
        root_f = chord_freqs[0][0]
        fifth_f = chord_freqs[0][2]
        sustained_wave = (
            0.34 * np.sin(2 * np.pi * root_f * seg_t)
            + 0.24 * np.sin(2 * np.pi * fifth_f * seg_t)
            + 0.16 * np.sin(2 * np.pi * (root_f * 2.0) * seg_t)
        ) * swell_env
        audio[s_i0:s_i1] = sustained_wave

    # 3. Percussion: Downbeats (Beat 1 of measure) & Regular Beats
    for b_idx, bt in enumerate(beat_times):
        # Skip percussion inside the Musical Pause or Sustained Note windows so Librosa detects them cleanly
        if (p_start <= bt <= p_end) or (s_start <= bt <= s_end):
            continue

        b_sample = int(bt * sr)
        hit_len = int(0.28 * sr)
        end_sample = min(n_samples, b_sample + hit_len)
        seg_len = end_sample - b_sample
        if seg_len <= 10:
            continue

        seg_t = np.arange(seg_len) / float(sr)
        is_downbeat = (b_idx % 4) == 0

        if is_downbeat:
            # Heavy downbeat kick + sub-bass drop + bright chime transient
            freq_sweep = 150.0 * np.exp(-seg_t * 24.0) + 48.0
            phase = 2 * np.pi * np.cumsum(freq_sweep) / float(sr)
            kick = 0.72 * np.sin(phase) * np.exp(-seg_t * 10.0)
            chime = 0.25 * np.sin(2 * np.pi * 1046.5 * seg_t) * np.exp(-seg_t * 22.0)
            audio[b_sample:end_sample] += kick + chime
        else:
            # Regular beat pulse (kick on beat 3, crisp snare/clap on 2 & 4)
            if (b_idx % 2) == 1:
                rng = np.random.default_rng(seed=b_idx + 42)
                noise = rng.normal(0, 1, seg_len)
                snare = 0.32 * noise * np.exp(-seg_t * 28.0)
                body = 0.22 * np.sin(2 * np.pi * 195.0 * seg_t) * np.exp(-seg_t * 20.0)
                audio[b_sample:end_sample] += snare + body
            else:
                freq_sweep = 110.0 * np.exp(-seg_t * 28.0) + 52.0
                phase = 2 * np.pi * np.cumsum(freq_sweep) / float(sr)
                kick = 0.45 * np.sin(phase) * np.exp(-seg_t * 14.0)
                audio[b_sample:end_sample] += kick

    # 4. Enforce Musical Pause / Breath Window (attenuate to gentle atmospheric breath)
    p_i0, p_i1 = int(p_start * sr), min(n_samples, int(p_end * sr))
    if p_i1 > p_i0:
        audio[p_i0:p_i1] *= 0.08

    # Normalize safely to [-0.92, 0.92]
    peak = float(np.max(np.abs(audio)))
    if peak > 1e-5:
        audio = (audio / peak) * 0.90

    filepath.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(filepath), audio.astype(np.float32), sr)


_CACHED_CUE_MAPS: Dict[str, AudioCueMap] = {}


def ensure_builtin_music_tracks() -> List[AudioCueMap]:
    """Ensures all 4 built-in dance tracks are synthesized and analyzed."""
    results: List[AudioCueMap] = []
    for spec in BUILT_IN_TRACK_SPECS:
        track_id = str(spec["track_id"])
        wav_path = MUSIC_DIR / f"{track_id}.wav"
        if not wav_path.exists():
            _synthesize_dance_track_wav(
                filepath=wav_path,
                bpm=float(spec["bpm"]),
                duration_sec=float(spec["duration_sec"]),
                chord_freqs=list(spec["chord_freqs"]),  # type: ignore
                pause_window=tuple(spec["pause_window"]),  # type: ignore
                sustained_window=tuple(spec["sustained_window"]),  # type: ignore
            )
        if track_id not in _CACHED_CUE_MAPS:
            cue_map = analyze_audio_file(
                filepath=str(wav_path),
                track_id=track_id,
                title=str(spec["title"]),
                url=f"/static/music/{wav_path.name}",
                genre=str(spec["genre"]),
                is_generated=False,
            )
            _CACHED_CUE_MAPS[track_id] = cue_map
        results.append(_CACHED_CUE_MAPS[track_id])
    return results


def get_music_track_by_id(track_id: str) -> AudioCueMap:
    ensure_builtin_music_tracks()
    if track_id in _CACHED_CUE_MAPS:
        return _CACHED_CUE_MAPS[track_id]
    return _CACHED_CUE_MAPS["competition_edm_pop"]


def generate_custom_music_track(
    prompt: str,
    target_duration_sec: float = 18.0,
    preferred_bpm: Optional[float] = None,
) -> AudioCueMap:
    """
    Generates a custom dance soundtrack tailored to the user's prompt.
    If ELEVENLABS_API_KEY / AI_MUSIC_API_KEY is configured, calls the cloud sound generation endpoint;
    otherwise synthesizes a custom-structured multi-stem procedural dance track matching the prompt's mood & BPM.
    """
    prompt_clean = (prompt or "Inspiring contemporary competition dance").strip()
    digest = hashlib.md5(f"{prompt_clean}_{target_duration_sec}".encode("utf-8")).hexdigest()[:8]
    track_id = f"ai_gen_{digest}"
    wav_path = MUSIC_DIR / f"{track_id}.wav"

    lower = prompt_clean.lower()
    if preferred_bpm:
        bpm = preferred_bpm
    elif any(w in lower for w in ["fast", "hype", "edm", "jazz", "upbeat", "competition"]):
        bpm = 126.0
    elif any(w in lower for w in ["slow", "lyrical", "ballet", "piano", "graceful", "soft"]):
        bpm = 98.0
    else:
        bpm = 116.0

    dur = max(12.0, min(30.0, float(target_duration_sec) + 2.0))

    # Optional ElevenLabs Sound Generation API hook if key is configured
    if settings.ai_music_api_key and not wav_path.exists():
        try:
            resp = httpx.post(
                "https://api.elevenlabs.io/v1/sound-generation",
                headers={"xi-api-key": settings.ai_music_api_key},
                json={"text": prompt_clean, "duration_seconds": min(22.0, dur)},
                timeout=20.0,
            )
            if resp.status_code == 200 and len(resp.content) > 1000:
                wav_path.write_bytes(resp.content)
        except Exception:
            pass

    if not wav_path.exists():
        chord_freqs = [
            (261.63, 329.63, 392.00),
            (220.00, 261.63, 329.63),
            (174.61, 220.00, 261.63),
            (196.00, 246.94, 293.66),
        ]
        p_start = round(dur * 0.30, 1)
        s_start = round(dur * 0.62, 1)
        _synthesize_dance_track_wav(
            filepath=wav_path,
            bpm=bpm,
            duration_sec=dur,
            chord_freqs=chord_freqs,
            pause_window=(p_start, p_start + 1.7),
            sustained_window=(s_start, s_start + 2.1),
            style_hint=prompt_clean,
        )

    cue_map = analyze_audio_file(
        filepath=str(wav_path),
        track_id=track_id,
        title=f"AI Custom Track: {prompt_clean[:38]} ({int(bpm)} BPM)",
        url=f"/static/music/{wav_path.name}",
        genre="ai_generated",
        is_generated=True,
    )
    _CACHED_CUE_MAPS[track_id] = cue_map
    return cue_map
