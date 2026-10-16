from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple
import librosa
import numpy as np
from scipy import signal
import soundfile as sf
import httpx

from backend.config import MUSIC_DIR, settings
from backend.models.schemas import AudioCueMap
from backend.services.audio_analyzer import analyze_audio_file
from backend.services import progress


MUSIC_ENGINE_VERSION = "v4_gemini_lyria_sculpted_2026"
GEMINI_MUSIC_MODELS = ["models/lyria-3-clip-preview", "models/lyria-3.5", "models/lyria-3-pro-preview"]


def _midi_to_freq(midi_note: float) -> float:
    return 440.0 * (2.0 ** ((midi_note - 69.0) / 12.0))


BUILT_IN_TRACK_SPECS: List[Dict[str, Any]] = [
    {
        "track_id": "ballet_adagio_swan",
        "title": "Swan Lake Reverie (Classical Ballet Adagio • Harp, Violin & Cello - 86 BPM)",
        "genre": "classical_ballet_adagio",
        "arrangement": "ballet_adagio",
        "bpm": 86.0,
        "duration_sec": 22.0,
        "lyria_prompt": (
            "Instrumental classical romantic ballet adagio. "
            "Flowing concert harp arpeggios, emotional solo violin and warm cello melody in A minor, "
            "lush romantic orchestral string swells, steady 86 BPM ballet phrasing, studio orchestral recording, "
            "instrumental only, no vocals."
        ),
        "chords_midi": [(57, 60, 64, 69), (53, 57, 60, 69), (50, 57, 62, 65), (52, 56, 59, 64)],
        "melody_midi": [69, 72, 76, 77, 76, 74, 72, 71, 69, 72, 76, 81, 79, 77, 76, 74],
        "pause_window": (6.4, 8.1),
        "sustained_window": (12.6, 14.8),
    },
    {
        "track_id": "ballet_waltz_flowers",
        "title": "Valse Royale (Classical Ballet Waltz • Strings, Flute & Harp - 108 BPM)",
        "genre": "classical_ballet_waltz",
        "arrangement": "ballet_waltz",
        "bpm": 108.0,
        "duration_sec": 21.0,
        "lyria_prompt": (
            "Instrumental classical ballet grand waltz in D major. "
            "Graceful orchestral strings, concert harp glissandos, lyrical flute and violin counter-melody, "
            "clear downbeat waltz pulse at 108 BPM for ballet turns and grand jetes, classical ballet orchestra, "
            "instrumental only, no vocals."
        ),
        "chords_midi": [(50, 57, 62, 66), (47, 54, 59, 62), (43, 50, 55, 59), (45, 52, 57, 61)],
        "melody_midi": [74, 78, 81, 79, 78, 76, 74, 71, 71, 74, 79, 78, 76, 74, 76, 78],
        "pause_window": (4.8, 6.5),
        "sustained_window": (11.2, 13.4),
    },
    {
        "track_id": "ballet_variation_sugarplum",
        "title": "Allegro Brillante (Ballet Variation • Celesta & Pizzicato Strings - 122 BPM)",
        "genre": "classical_ballet_variation",
        "arrangement": "ballet_variation",
        "bpm": 122.0,
        "duration_sec": 20.0,
        "lyria_prompt": (
            "Instrumental classical ballet variation for solo pointe dancer. "
            "Sparkling crystalline celesta bell melody paired with playful bouncy pizzicato strings, woodwinds, and light orchestral accents. "
            "Crisp rhythmic precision at 122 BPM for petit allegro jumps and pirouette turns. "
            "Instrumental only, no vocals."
        ),
        "chords_midi": [(52, 55, 59, 64), (48, 55, 60, 64), (45, 52, 57, 60), (47, 54, 59, 63)],
        "melody_midi": [76, 75, 76, 71, 74, 72, 69, 71, 76, 79, 83, 81, 79, 78, 76, 75],
        "pause_window": (7.0, 8.7),
        "sustained_window": (13.4, 15.5),
    },
    {
        "track_id": "lyrical_piano_strings",
        "title": "Golden Hour Arabesque (Lyrical Grand Piano & Cello - 94 BPM)",
        "genre": "lyrical_piano_strings",
        "arrangement": "lyrical_piano",
        "bpm": 94.0,
        "duration_sec": 21.0,
        "lyria_prompt": (
            "Emotive lyrical contemporary dance soundtrack at 94 BPM. "
            "Intimate concert grand piano playing flowing arpeggios joined by a soaring solo cello, warm chamber strings, and soft brush percussion. "
            "Instrumental only, no vocals."
        ),
        "chords_midi": [(43, 50, 55, 59), (42, 50, 57, 62), (40, 47, 55, 59), (48, 55, 59, 64)],
        "melody_midi": [67, 71, 74, 79, 78, 74, 71, 69, 67, 71, 76, 74, 72, 71, 69, 67],
        "pause_window": (5.0, 6.8),
        "sustained_window": (10.5, 13.0),
    },
    {
        "track_id": "neoclassical_chamber_pulse",
        "title": "Pointe & Precision (Neoclassical Strings & Piano Ostinato - 104 BPM)",
        "genre": "neoclassical_strings",
        "arrangement": "neoclassical",
        "bpm": 104.0,
        "duration_sec": 20.0,
        "lyria_prompt": (
            "Instrumental neoclassical chamber music for modern ballet and technique showcase. "
            "Driving spiccato string eighth-note ostinato, resonant grand piano melody in C minor, and deep cello downbeat accents at 104 BPM. "
            "Instrumental only, no vocals."
        ),
        "chords_midi": [(48, 55, 60, 63), (44, 51, 56, 60), (51, 55, 58, 63), (46, 53, 58, 62)],
        "melody_midi": [72, 75, 79, 77, 75, 74, 72, 70, 68, 72, 75, 79, 77, 75, 74, 72],
        "pause_window": (5.8, 7.5),
        "sustained_window": (11.8, 14.0),
    },
    {
        "track_id": "studio_hiphop_beat",
        "title": "8-Count Studio Hustle (Neo-Soul Rhodes & Boom-Bap Groove - 100 BPM)",
        "genre": "studio_hiphop_beat",
        "arrangement": "hiphop_groove",
        "bpm": 100.0,
        "duration_sec": 20.0,
        "lyria_prompt": (
            "Cool dance studio rehearsal hip-hop and neo-soul groove at 100 BPM. "
            "Warm Rhodes electric piano jazz chords, deep melodic 808 bassline, crisp punchy boom-bap kick and rimshot snare for 8-count choreography. "
            "Instrumental only, no vocals."
        ),
        "chords_midi": [(41, 48, 53, 56), (49, 53, 56, 60), (46, 53, 58, 61), (48, 55, 58, 64)],
        "melody_midi": [65, 68, 72, 70, 68, 65, 63, 60, 65, 68, 72, 75, 72, 70, 68, 67],
        "pause_window": (6.6, 8.3),
        "sustained_window": (13.0, 14.8),
    },
    {
        "track_id": "contemporary_dramatic_build",
        "title": "Velocity & Flight (Contemporary Cinematic Crescendo - 116 BPM)",
        "genre": "contemporary_dramatic_build",
        "arrangement": "contemporary_cinematic",
        "bpm": 116.0,
        "duration_sec": 20.0,
        "lyria_prompt": (
            "Cinematic contemporary competition dance soundtrack at 116 BPM. "
            "Dramatic piano motif, pulsing sub-bass, atmospheric strings, and powerful orchestral timpani and tom drum builds "
            "that hit hard on measure downbeats for big contemporary leaps. Instrumental only, no vocals."
        ),
        "chords_midi": [(50, 57, 62, 65), (46, 53, 58, 62), (41, 48, 53, 57), (48, 55, 60, 64)],
        "melody_midi": [74, 77, 81, 79, 77, 76, 74, 72, 70, 74, 77, 81, 84, 81, 79, 76],
        "pause_window": (5.5, 7.2),
        "sustained_window": (11.4, 13.6),
    },
    {
        "track_id": "jazz_funk_broadway",
        "title": "Center Stage Strut (Broadway Jazz & Brass Groove - 120 BPM)",
        "genre": "jazz_broadway_groove",
        "arrangement": "jazz_broadway",
        "bpm": 120.0,
        "duration_sec": 20.0,
        "lyria_prompt": (
            "Upbeat Broadway showstopper jazz and funk dance instrumental at 120 BPM. "
            "Walking upright bassline, syncopated jazz piano, sassy big-band brass horn stabs on measure downbeats, and crisp swing drums. "
            "Instrumental only, no vocals."
        ),
        "chords_midi": [(46, 53, 58, 62), (43, 50, 55, 59), (48, 55, 60, 63), (41, 48, 53, 57)],
        "melody_midi": [70, 74, 77, 79, 77, 74, 72, 70, 72, 75, 79, 82, 81, 79, 77, 74],
        "pause_window": (7.4, 9.1),
        "sustained_window": (13.8, 15.9),
    },
    {
        "track_id": "competition_edm_pop",
        "title": "Stage Spotlight Drop (Melodic Competition Pop/EDM - 126 BPM)",
        "genre": "competition_edm_pop",
        "arrangement": "edm_pop",
        "bpm": 126.0,
        "duration_sec": 20.0,
        "lyria_prompt": (
            "Uplifting melodic competition dance pop and progressive EDM anthem at 126 BPM. "
            "Bright plucked synth arpeggios, euphoric lead melody hook, and a clean high-impact festival beat drop on the downbeat for big dance leaps. "
            "Instrumental only, no vocals."
        ),
        "chords_midi": [(45, 52, 57, 60), (41, 48, 53, 57), (48, 55, 60, 64), (43, 50, 55, 59)],
        "melody_midi": [76, 76, 79, 76, 74, 72, 71, 72, 76, 79, 81, 79, 76, 74, 72, 71],
        "pause_window": (6.2, 7.9),
        "sustained_window": (12.0, 14.2),
    },
    {
        "track_id": "kpop_fierce_encore",
        "title": "Encore Finale (High-Energy Commercial Dance Pop - 132 BPM)",
        "genre": "commercial_kpop_dance",
        "arrangement": "kpop_dance",
        "bpm": 132.0,
        "duration_sec": 20.0,
        "lyria_prompt": (
            "Electrifying high-energy K-Pop and commercial jazz-funk dance finale at 132 BPM. "
            "Driving synth bass, catchy brassy synth lead hook, crisp claps and 8-count choreography accents. "
            "Instrumental only, no vocals."
        ),
        "chords_midi": [(40, 47, 52, 55), (48, 55, 60, 64), (43, 50, 55, 59), (50, 57, 62, 66)],
        "melody_midi": [76, 79, 83, 81, 79, 76, 74, 76, 79, 83, 86, 83, 81, 79, 78, 76],
        "pause_window": (5.2, 6.9),
        "sustained_window": (10.8, 12.9),
    },
]


def _enrich_music_prompt_with_gemini(
    user_prompt: str, target_duration_sec: float, preferred_bpm: Optional[float]
) -> Tuple[str, str, float]:
    """
    Uses Gemini (`gemini-2.5-flash`) to transform a user prompt into a rich,
    genre-specific instrumental music prompt for Gemini Lyria (`lyria-3-clip-preview`).
    """
    lower = user_prompt.lower()
    base_spec = _infer_spec_from_prompt(lower)
    default_bpm = float(preferred_bpm) if preferred_bpm else float(base_spec["bpm"])
    default_genre = str(base_spec["genre"])

    if not settings.gemini_api_key:
        return (
            f"Continuous, natural instrumental dance soundtrack: {user_prompt}. {int(default_bpm)} BPM, expressive flowing melody and clear measure downbeats. Instrumental only, no vocals.",
            default_genre,
            default_bpm,
        )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        sys_instruction = (
            "You are an expert dance music director and composer. "
            "Given a user's music request for a dance video reel, output a JSON object with keys:\n"
            '- "lyria_prompt": A vivid 2-3 sentence instrumental music generation prompt specifying exact acoustic/electronic instruments, key/mood, continuous natural flowing musicality (no abrupt stops or mutes), and clear rhythmic pulse for dance. CRITICAL RULE: Never mention any real artist, composer, band, or copyrighted song names (translate any artist/song reference into pure musical style, era, and instrumentation descriptions). Always end with "Continuous studio instrumental only, no vocals."\n'
            '- "genre": A short snake_case genre tag (e.g. "classical_ballet_adagio", "classical_ballet_waltz", "classical_ballet_variation", "lyrical_piano_strings", "neoclassical_strings", "contemporary_cinematic", "jazz_broadway_groove", "studio_hiphop_beat", "latin_ballroom", "competition_edm_pop").\n'
            '- "bpm": Ideal numeric tempo in BPM between 76 and 145 matching the requested style.'
        )
        resp = client.models.generate_content(
            model=settings.gemini_model,
            contents=f"User music request: {user_prompt}\nPreferred BPM: {preferred_bpm or 'auto'}",
            config=types.GenerateContentConfig(
                system_instruction=sys_instruction,
                response_mime_type="application/json",
                temperature=0.7,
            ),
        )
        if resp.text:
            data = json.loads(resp.text)
            lyria_prompt = str(data.get("lyria_prompt") or "").strip()
            genre_slug = str(data.get("genre") or default_genre).strip().lower().replace(" ", "_")
            bpm_val = float(data.get("bpm") or default_bpm)
            if lyria_prompt:
                return lyria_prompt, genre_slug, max(70.0, min(160.0, bpm_val))
    except Exception:
        pass

    return (
        f"Continuous, natural instrumental dance music for: {user_prompt}. Expressive flowing melody, authentic instrumentation, {int(default_bpm)} BPM. Instrumental only, no vocals.",
        default_genre,
        default_bpm,
    )


def _generate_audio_via_gemini_lyria(
    prompt: str,
    output_wav_path: Path,
    pause_window: Optional[Tuple[float, float]] = None,
    sustained_window: Optional[Tuple[float, float]] = None,
    chord_midi: Tuple[int, ...] = (57, 60, 64, 69),
    target_duration_sec: float = 30.0,
) -> bool:
    """
    Calls Gemini's Lyria music generation model (`models/lyria-3-clip-preview` / `models/lyria-3.5`)
    using `settings.gemini_api_key` to generate natural, continuous studio-quality music audio without artificial mutes or holds.
    """
    if not settings.gemini_api_key:
        return False

    try:
        from google import genai
        import imageio_ffmpeg

        client = genai.Client(api_key=settings.gemini_api_key)
        audio_bytes: Optional[bytes] = None

        for attempt in range(2):
            for model_name in GEMINI_MUSIC_MODELS:
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                    )
                    if resp and resp.candidates:
                        for cand in resp.candidates:
                            if not cand.content or not cand.content.parts:
                                continue
                            for part in cand.content.parts:
                                if part.inline_data and part.inline_data.data and len(part.inline_data.data) > 10_000:
                                    audio_bytes = part.inline_data.data
                                    break
                            if audio_bytes:
                                break
                    if audio_bytes:
                        break
                except Exception:
                    time.sleep(1.2)
                    continue
            if audio_bytes:
                break

        if not audio_bytes:
            return False

        output_wav_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_mp3 = output_wav_path.with_suffix(".mp3")
        tmp_mp3.write_bytes(audio_bytes)
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-i",
                str(tmp_mp3),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "22050",
                "-acodec",
                "pcm_s16le",
                str(output_wav_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tmp_mp3.unlink(missing_ok=True)

        return output_wav_path.exists() and output_wav_path.stat().st_size > 20_000
    except Exception:
        return False


# ============================================================================
# Offline Multi-Instrument Synthesizer Fallback
# ============================================================================

def _synthesize_dance_track_wav(
    filepath: Path,
    bpm: float,
    duration_sec: float,
    chords_midi: List[Tuple[int, ...]],
    melody_midi: List[int],
    pause_window: Tuple[float, float],
    sustained_window: Tuple[float, float],
    arrangement: str = "edm_pop",
) -> None:
    sr = 22050
    n_samples = int(duration_sec * sr)
    t = np.linspace(0.0, duration_sec, n_samples, endpoint=False)
    audio = np.zeros(n_samples, dtype=np.float64)

    beat_interval = 60.0 / bpm
    beat_times = np.arange(0.4, duration_sec - 0.3, beat_interval)
    p_start, p_end = pause_window
    s_start, s_end = sustained_window

    measure_dur = beat_interval * 4.0
    for idx, m_tuple in enumerate(chords_midi * 6):
        m_start = idx * measure_dur
        if m_start >= duration_sec:
            break
        m_end = min(duration_sec, m_start + measure_dur)
        s_idx, e_idx = int(m_start * sr), int(m_end * sr)
        seg_t = t[s_idx:e_idx] - m_start
        env = np.minimum(1.0, seg_t / 0.12) * np.exp(-seg_t * 0.35)
        chord_wave = np.zeros_like(seg_t)
        for m_note in m_tuple:
            f = _midi_to_freq(m_note)
            chord_wave += 0.14 * np.sin(2 * np.pi * f * seg_t) + 0.06 * np.sin(2 * np.pi * (f * 2.0) * seg_t)
        audio[s_idx:e_idx] += chord_wave * env

    for b_idx, bt in enumerate(beat_times):
        b_sample = int(bt * sr)
        hit_len = int(0.26 * sr)
        end_sample = min(n_samples, b_sample + hit_len)
        seg_len = end_sample - b_sample
        if seg_len <= 10:
            continue
        seg_t = np.arange(seg_len) / float(sr)
        mel_f = _midi_to_freq(melody_midi[b_idx % len(melody_midi)])
        mel_note = 0.22 * np.sin(2 * np.pi * mel_f * seg_t) * np.exp(-seg_t * 4.5)
        if (b_idx % 4) == 0:
            freq_sweep = 135.0 * np.exp(-seg_t * 24.0) + 48.0
            phase = 2 * np.pi * np.cumsum(freq_sweep) / float(sr)
            kick = 0.65 * np.sin(phase) * np.exp(-seg_t * 10.0)
            audio[b_sample:end_sample] += kick + mel_note
        else:
            if (b_idx % 2) == 1:
                rng = np.random.default_rng(seed=b_idx + 42)
                snare = 0.24 * rng.normal(0, 1, seg_len) * np.exp(-seg_t * 28.0)
                audio[b_sample:end_sample] += snare + mel_note
            else:
                freq_sweep = 105.0 * np.exp(-seg_t * 28.0) + 52.0
                phase = 2 * np.pi * np.cumsum(freq_sweep) / float(sr)
                kick = 0.42 * np.sin(phase) * np.exp(-seg_t * 14.0)
                audio[b_sample:end_sample] += kick + mel_note

    peak = float(np.max(np.abs(audio)))
    if peak > 1e-5:
        audio = (audio / peak) * 0.90
    filepath.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(filepath), audio.astype(np.float32), sr, subtype="PCM_16")


# ============================================================================
# Catalog & Custom Registry Persistence
# ============================================================================

_CACHED_CUE_MAPS: Dict[str, AudioCueMap] = {}
_BUILTIN_REGISTRY_PATH = MUSIC_DIR / "builtin_tracks.json"
_CUSTOM_REGISTRY_PATH = MUSIC_DIR / "custom_tracks.json"
_REGISTRY_LOADED = False


def _load_builtin_registry() -> None:
    if not _BUILTIN_REGISTRY_PATH.exists():
        return
    try:
        raw = json.loads(_BUILTIN_REGISTRY_PATH.read_text(encoding="utf-8"))
        for entry in raw:
            tid = str(entry.get("track_id", ""))
            wav_path = MUSIC_DIR / f"{tid}.wav"
            if tid and wav_path.exists():
                entry["filepath"] = str(wav_path)
                entry["url"] = f"/static/music/{wav_path.name}"
                cue = AudioCueMap(**entry)
                _CACHED_CUE_MAPS.setdefault(tid, cue)
    except Exception:
        pass


def _save_builtin_registry() -> None:
    builtins = []
    for spec in BUILT_IN_TRACK_SPECS:
        tid = str(spec["track_id"])
        if tid in _CACHED_CUE_MAPS:
            d = _CACHED_CUE_MAPS[tid].model_dump()
            # Store portable relative path in JSON so any git checkout works cleanly
            d["filepath"] = f"data/music/{tid}.wav"
            builtins.append(d)
    try:
        _BUILTIN_REGISTRY_PATH.write_text(json.dumps(builtins, indent=2), encoding="utf-8")
    except Exception:
        pass


def _load_custom_registry() -> None:
    global _REGISTRY_LOADED
    if _REGISTRY_LOADED:
        return
    _REGISTRY_LOADED = True
    _load_builtin_registry()
    if not _CUSTOM_REGISTRY_PATH.exists():
        return
    try:
        raw = json.loads(_CUSTOM_REGISTRY_PATH.read_text(encoding="utf-8"))
        for entry in raw:
            cue = AudioCueMap(**entry)
            if Path(cue.filepath).exists():
                _CACHED_CUE_MAPS.setdefault(cue.track_id, cue)
    except Exception:
        pass


def _save_custom_registry() -> None:
    builtin_ids = {str(s["track_id"]) for s in BUILT_IN_TRACK_SPECS}
    customs = [c.model_dump() for tid, c in _CACHED_CUE_MAPS.items() if tid not in builtin_ids]
    try:
        _CUSTOM_REGISTRY_PATH.write_text(json.dumps(customs), encoding="utf-8")
    except Exception:
        pass


def register_custom_music_track(cue_map: AudioCueMap) -> AudioCueMap:
    """Registers an uploaded or AI-generated track in the runtime catalog (persisted to disk)."""
    _load_custom_registry()
    _CACHED_CUE_MAPS[cue_map.track_id] = cue_map
    _save_custom_registry()
    return cue_map


def _generate_single_builtin_spec(spec: Dict[str, Any], force_regenerate: bool) -> AudioCueMap:
    track_id = str(spec["track_id"])
    wav_path = MUSIC_DIR / f"{track_id}.wav"
    pause_win = tuple(spec["pause_window"])
    sust_win = tuple(spec["sustained_window"])
    chords = list(spec["chords_midi"])

    if force_regenerate or not wav_path.exists():
        lyria_prompt = str(spec.get("lyria_prompt") or spec["title"])
        generated_ok = _generate_audio_via_gemini_lyria(
            prompt=lyria_prompt,
            output_wav_path=wav_path,
            pause_window=pause_win,  # type: ignore
            sustained_window=sust_win,  # type: ignore
            chord_midi=chords[0],
            target_duration_sec=float(spec["duration_sec"]),
        )
        if not generated_ok:
            _synthesize_dance_track_wav(
                filepath=wav_path,
                bpm=float(spec["bpm"]),
                duration_sec=float(spec["duration_sec"]),
                chords_midi=chords,
                melody_midi=list(spec["melody_midi"]),
                pause_window=pause_win,  # type: ignore
                sustained_window=sust_win,  # type: ignore
                arrangement=str(spec.get("arrangement", "edm_pop")),
            )

    return analyze_audio_file(
        filepath=str(wav_path),
        track_id=track_id,
        title=str(spec["title"]),
        url=f"/static/music/{wav_path.name}",
        genre=str(spec["genre"]),
        is_generated=False,
    )


def ensure_builtin_music_tracks(force_regenerate: bool = False) -> List[AudioCueMap]:
    """
    Loads the pre-generated built-in dance tracks and their pre-computed cue maps from `data/music/`
    (checked into the repository). Only generates audio if a `.wav` file is physically missing
    or `force_regenerate=True` is explicitly requested.
    """
    _load_custom_registry()
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    if not _CACHED_CUE_MAPS:
        _load_builtin_registry()

    builtin_ids = {str(s["track_id"]) for s in BUILT_IN_TRACK_SPECS}
    if force_regenerate:
        for bid in list(builtin_ids):
            _CACHED_CUE_MAPS.pop(bid, None)

    missing_specs = [
        s for s in BUILT_IN_TRACK_SPECS
        if force_regenerate or str(s["track_id"]) not in _CACHED_CUE_MAPS or not (MUSIC_DIR / f"{s['track_id']}.wav").exists()
    ]

    if missing_specs:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(_generate_single_builtin_spec, spec, force_regenerate) for spec in missing_specs]
            for fut in futures:
                cue_map = fut.result()
                _CACHED_CUE_MAPS[cue_map.track_id] = cue_map
        _save_builtin_registry()

    results: List[AudioCueMap] = [
        _CACHED_CUE_MAPS[str(spec["track_id"])] for spec in BUILT_IN_TRACK_SPECS
    ]

    custom_tracks = [
        cue for tid, cue in _CACHED_CUE_MAPS.items() if tid not in builtin_ids
    ]
    return list(reversed(custom_tracks)) + results


def get_music_track_by_id(track_id: str) -> AudioCueMap:
    ensure_builtin_music_tracks()
    if track_id in _CACHED_CUE_MAPS:
        return _CACHED_CUE_MAPS[track_id]
    raise KeyError(f"Music track '{track_id}' not found")


def _infer_spec_from_prompt(prompt_lower: str) -> Dict[str, Any]:
    if any(w in prompt_lower for w in ["waltz", "3/4", "flowers", "ballroom", "royal"]):
        return BUILT_IN_TRACK_SPECS[1]
    if any(w in prompt_lower for w in ["variation", "sugar", "celesta", "nutcracker", "petit allegro", "pointe"]):
        return BUILT_IN_TRACK_SPECS[2]
    if any(w in prompt_lower for w in ["ballet", "swan", "adagio", "classical", "orchestra", "harp", "violin"]):
        return BUILT_IN_TRACK_SPECS[0]
    if any(w in prompt_lower for w in ["neoclassical", "chamber", "ostinato", "cello", "modern classical"]):
        return BUILT_IN_TRACK_SPECS[4]
    if any(w in prompt_lower for w in ["lyrical", "piano", "graceful", "soft", "emotional", "slow"]):
        return BUILT_IN_TRACK_SPECS[3]
    if any(w in prompt_lower for w in ["hip", "hop", "street", "groove", "rhodes", "soul", "rehearsal", "urban"]):
        return BUILT_IN_TRACK_SPECS[5]
    if any(w in prompt_lower for w in ["jazz", "broadway", "funk", "sassy", "swing", "strut", "theater"]):
        return BUILT_IN_TRACK_SPECS[7]
    if any(w in prompt_lower for w in ["kpop", "k-pop", "fierce", "commercial", "pom", "fast", "130"]):
        return BUILT_IN_TRACK_SPECS[9]
    if any(w in prompt_lower for w in ["contemporary", "dramatic", "cinematic", "build", "crescendo"]):
        return BUILT_IN_TRACK_SPECS[6]
    return BUILT_IN_TRACK_SPECS[8]


def generate_custom_music_track(
    prompt: str,
    target_duration_sec: float = 18.0,
    preferred_bpm: Optional[float] = None,
) -> AudioCueMap:
    """
    Generates a custom dance soundtrack tailored to the user's prompt via Gemini (`gemini-2.5-flash` + `lyria-3-clip-preview`).
    """
    prompt_clean = (prompt or "Inspiring contemporary competition dance").strip()
    digest = hashlib.md5(f"{prompt_clean}_{target_duration_sec}_{preferred_bpm}_{MUSIC_ENGINE_VERSION}".encode("utf-8")).hexdigest()[:8]
    track_id = f"ai_gen_{digest}"
    wav_path = MUSIC_DIR / f"{track_id}.wav"

    progress.update(5, f"Crafting musical arrangement for “{prompt_clean[:40]}”", service="Gemini 2.5 Flash")
    lyria_prompt, genre_slug, target_bpm = _enrich_music_prompt_with_gemini(
        user_prompt=prompt_clean,
        target_duration_sec=target_duration_sec,
        preferred_bpm=preferred_bpm,
    )

    dur = max(14.0, min(28.0, float(target_duration_sec) + 3.0))
    base_spec = _infer_spec_from_prompt(prompt_clean.lower())
    seed_val = int(digest, 16)
    p_start = round(dur * (0.24 + (seed_val % 9) * 0.012), 1)
    s_start = round(dur * (0.55 + ((seed_val >> 4) % 9) * 0.012), 1)
    pause_win = (p_start, round(p_start + 1.7, 1))
    sust_win = (s_start, round(s_start + 2.1, 1))

    if not wav_path.exists():
        progress.update(15, f"Generating studio audio via Gemini Lyria ({int(target_bpm)} BPM)", service="Gemini Lyria 3")
        generated_ok = _generate_audio_via_gemini_lyria(
            prompt=lyria_prompt,
            output_wav_path=wav_path,
            pause_window=pause_win,
            sustained_window=sust_win,
            chord_midi=base_spec["chords_midi"][0],
            target_duration_sec=dur,
        )

        if not generated_ok and settings.ai_music_api_key:
            progress.update(25, f"Generating soundtrack for “{prompt_clean[:40]}”", service="ElevenLabs Sound Generation API")
            try:
                resp = httpx.post(
                    "https://api.elevenlabs.io/v1/sound-generation",
                    headers={"xi-api-key": settings.ai_music_api_key},
                    json={"text": prompt_clean, "duration_seconds": min(22.0, dur)},
                    timeout=20.0,
                )
                if resp.status_code == 200 and len(resp.content) > 1000:
                    wav_path.write_bytes(resp.content)
                    generated_ok = True
            except Exception:
                pass

        if not generated_ok:
            progress.update(25, f"Synthesizing {int(target_bpm)} BPM soundtrack", service="Multi-instrument synthesizer")
            _synthesize_dance_track_wav(
                filepath=wav_path,
                bpm=target_bpm,
                duration_sec=dur,
                chords_midi=list(base_spec["chords_midi"]),
                melody_midi=list(base_spec["melody_midi"]),
                pause_window=pause_win,
                sustained_window=sust_win,
                arrangement=str(base_spec["arrangement"]),
            )

    progress.update(55, "Analyzing generated track for beats & cues", service="Librosa")
    with progress.scope(55, 100):
        cue_map = analyze_audio_file(
            filepath=str(wav_path),
            track_id=track_id,
            title=f"Gemini AI Music: {prompt_clean[:38]} ({int(target_bpm)} BPM)",
            url=f"/static/music/{wav_path.name}",
            genre=genre_slug,
            is_generated=True,
        )
    return register_custom_music_track(cue_map)
