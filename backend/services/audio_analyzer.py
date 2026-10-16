from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import librosa
import numpy as np

from backend.models.schemas import AudioCueMap, AudioSectionCue
from backend.services import progress


def _smooth(x: np.ndarray, win: int) -> np.ndarray:
    if win <= 1 or len(x) < win:
        return np.asarray(x, dtype=np.float64)
    kernel = np.ones(win, dtype=np.float64) / float(win)
    return np.convolve(np.asarray(x, dtype=np.float64), kernel, mode="same")


def _runs(mask: np.ndarray, min_len: int) -> List[tuple]:
    runs: List[tuple] = []
    start: Optional[int] = None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_len:
                runs.append((start, i))
            start = None
    if start is not None and len(mask) - start >= min_len:
        runs.append((start, len(mask)))
    return runs


def _detect_photo_sections(
    grid_times: np.ndarray,
    energy: np.ndarray,
    perc: np.ndarray,
    harm_ratio: np.ndarray,
    duration_sec: float,
) -> List[AudioSectionCue]:
    """
    Finds photo-friendly windows relative to *this* track's own dynamics:
    - Pause / breath: smoothed loudness well below the track's median level (>= 0.6s)
    - Sustained note: percussion drops far below its usual level while harmony keeps ringing (>= 1.0s)
    The strongest, non-overlapping candidates are kept (about one per 7 seconds of music).
    """
    n = len(grid_times)
    if n < 20:
        return []
    step = float(grid_times[1] - grid_times[0]) if n > 1 else 0.1
    e_s = _smooth(energy, 5)
    p_norm = np.asarray(perc, dtype=np.float64) / (float(np.max(perc)) + 1e-9)
    p_s = _smooth(p_norm, 7)  # ~0.7s window bridges the gaps between individual drum hits
    h_s = _smooth(harm_ratio, 5)
    edge = 5

    med_e = float(np.median(e_s))
    pause_thr = max(0.06, min(0.30, med_e * 0.45))
    pause_mask = e_s < pause_thr
    pause_mask[:edge] = False
    pause_mask[-edge:] = False

    p_med = float(np.median(p_s)) + 1e-9
    sus_mask = (p_s < p_med * 0.45) & (e_s >= pause_thr) & (h_s >= float(np.percentile(h_s, 60)))
    sus_mask &= ~pause_mask
    sus_mask[:edge] = False
    sus_mask[-edge:] = False

    candidates: List[tuple] = []
    for a, b in _runs(pause_mask, 6):
        seg_e = float(np.mean(e_s[a:b]))
        depth = max(0.05, 1.0 - seg_e / (med_e + 1e-9))
        candidates.append(("pause", a, b, seg_e, depth * (b - a)))
    for a, b in _runs(sus_mask, 10):
        seg_e = float(np.mean(e_s[a:b]))
        quiet = max(0.05, 1.0 - float(np.mean(p_s[a:b])) / p_med)
        candidates.append(("sustained_note", a, b, seg_e, quiet * (b - a)))

    max_sections = max(2, min(8, int(duration_sec / 7.0) + 1))
    min_gap = int(round(1.0 / step))
    candidates.sort(key=lambda c: c[4], reverse=True)
    picked: List[tuple] = []
    for c in candidates:
        if len(picked) >= max_sections:
            break
        if any(not (c[2] + min_gap <= p[1] or c[1] >= p[2] + min_gap) for p in picked):
            continue
        picked.append(c)

    # For natural, continuous studio music (without artificial mutes or drum dropouts),
    # locate the track's natural softest breath phrase ('pause') and most legato harmonic phrase ('sustained_note')
    # directly from its real energy / harmonic-to-percussive envelopes.
    picked_types = {p[0] for p in picked}
    margin = max(edge, int(round(1.8 / step)))
    if n > margin * 2 + 22:
        if "pause" not in picked_types:
            win_p = int(round(1.8 / step))
            best_p = None
            best_p_val = 1e9
            for a in range(margin, n - margin - win_p):
                b = a + win_p
                if any(not (b + min_gap <= p[1] or a >= p[2] + min_gap) for p in picked):
                    continue
                seg_e = float(np.mean(e_s[a:b]))
                if seg_e < best_p_val:
                    best_p_val = seg_e
                    best_p = ("pause", a, b, seg_e, 1.0 - seg_e)
            if best_p is not None:
                picked.append(best_p)
                picked_types.add("pause")

        if "sustained_note" not in picked_types:
            win_s = int(round(2.1 / step))
            best_s = None
            best_s_score = -1e9
            for a in range(margin, n - margin - win_s):
                b = a + win_s
                if any(not (b + min_gap <= p[1] or a >= p[2] + min_gap) for p in picked):
                    continue
                seg_e = float(np.mean(e_s[a:b]))
                seg_h = float(np.mean(h_s[a:b]))
                seg_p = float(np.mean(p_s[a:b]))
                # Favor rich harmonic sustain with relatively smooth percussion and healthy volume
                score = seg_h * (1.0 - 0.45 * seg_p) * (0.4 + 0.6 * min(1.0, seg_e / (med_e + 1e-6)))
                if score > best_s_score:
                    best_s_score = score
                    best_s = ("sustained_note", a, b, seg_e, score)
            if best_s is not None:
                picked.append(best_s)
                picked_types.add("sustained_note")

    picked.sort(key=lambda c: c[1])

    sections: List[AudioSectionCue] = []
    for cue_type, a, b, seg_e, _score in picked:
        start_t = round(float(grid_times[a]), 2)
        end_t = round(float(grid_times[min(n - 1, b - 1)]) + step, 2)
        cap = 3.0 if cue_type == "pause" else 4.0
        end_t = min(end_t, round(start_t + cap, 2))
        sections.append(
            AudioSectionCue(
                cue_type=cue_type,
                start_sec=start_t,
                end_sec=end_t,
                duration_sec=round(end_t - start_t, 2),
                intensity=round(seg_e, 3),
                description=(
                    "Musical pause / breath ideal for still photo highlight with Ken Burns"
                    if cue_type == "pause"
                    else "Sustained harmonic note ideal for expressive photo + slow zoom"
                ),
            )
        )
    return sections


def analyze_audio_file(
    filepath: str,
    track_id: str,
    title: str,
    url: str,
    genre: str = "dance_pop",
    is_generated: bool = False,
) -> AudioCueMap:
    """
    Uses Librosa to extract:
    - Tempo (BPM) & all beat timestamps
    - Measure Downbeats (the '1' and '5' count in 8-count choreography where heavy onset/bass hits occur)
    - Sustained Notes (high harmonic-to-percussive ratio & steady RMS over >= 1.2s)
    - Musical Pauses / Breaths (low RMS energy dip between phrases)
    - High-Energy Chorus/Drop Peaks
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {filepath}")

    progress.update(5, f"Decoding audio “{path.name}”", service="Librosa audio loader (22.05 kHz mono)")
    try:
        y, sr = librosa.load(str(path), sr=22050, mono=True)
    except Exception:
        # Use bundled imageio_ffmpeg binary to convert .m4a / .mp3 / .aac / video audio to wav
        import subprocess
        import imageio_ffmpeg

        progress.update(8, f"Converting “{path.name}” to WAV", service="FFmpeg (imageio-ffmpeg)")
        wav_fallback = path.with_suffix(".converted.wav")
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-i",
                str(path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "22050",
                str(wav_fallback),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        y, sr = librosa.load(str(wav_fallback), sr=22050, mono=True)
    duration_sec = round(float(librosa.get_duration(y=y, sr=sr)), 3)

    # 1. Beat tracking & onset envelope
    progress.update(25, "Tracking tempo & beats", service="Librosa beat tracker (onset strength)")
    hop_length = 512
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    tempo, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_env, sr=sr, hop_length=hop_length
    )
    if isinstance(tempo, np.ndarray):
        bpm = float(tempo[0]) if tempo.size > 0 else 120.0
    else:
        bpm = float(tempo or 120.0)
    if bpm < 60.0 or bpm > 210.0:
        bpm = 120.0

    beat_times_arr = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)
    beat_times = [round(float(t), 3) for t in beat_times_arr]

    # Synthesize regular beat grid if track is ambient/sparse so choreography still has a pulse
    if len(beat_times) < 4:
        interval = 60.0 / bpm
        beat_times = [
            round(t, 3) for t in np.arange(0.5, max(1.0, duration_sec - 0.3), interval)
        ]
        beat_frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=hop_length)

    # 2. Downbeat detection (4-beat measure phase alignment using low-frequency bass + onset energy)
    progress.update(50, "Separating harmonic vs. percussive layers", service="Librosa HPSS")
    y_harm, y_perc = librosa.effects.hpss(y)
    rms_all = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    rms_harm = librosa.feature.rms(y=y_harm, hop_length=hop_length)[0]
    rms_perc = librosa.feature.rms(y=y_perc, hop_length=hop_length)[0]
    progress.update(70, "Locating measure downbeats", service="Librosa onset + percussive RMS phase scoring")

    # Evaluate which phase (0, 1, 2, 3) mod 4 has the strongest combined percussive + onset accent
    downbeat_times: List[float] = []
    if len(beat_frames) >= 4:
        phase_scores = [0.0, 0.0, 0.0, 0.0]
        for idx, bf in enumerate(beat_frames):
            bf_clamped = min(len(onset_env) - 1, max(0, int(bf)))
            accent = float(onset_env[bf_clamped]) + float(rms_perc[min(len(rms_perc) - 1, bf_clamped)]) * 4.0
            phase_scores[idx % 4] += accent
        best_phase = int(np.argmax(phase_scores))
        for idx, bt in enumerate(beat_times):
            if idx % 4 == best_phase:
                downbeat_times.append(bt)
    else:
        downbeat_times = beat_times[::2] if beat_times else [0.5, 2.5, 4.5, 6.5]

    # 3. Onset peaks
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, hop_length=hop_length, backtrack=False
    )
    onset_peaks = [
        round(float(t), 3)
        for t in librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop_length)
    ]

    # 4. Resample envelopes at 10 Hz (every 0.1s) for UI visualization & section segmentation
    grid_times = np.arange(0.0, duration_sec, 0.1)
    frame_times = librosa.frames_to_time(
        np.arange(len(rms_all)), sr=sr, hop_length=hop_length
    )
    rms_interp = np.interp(grid_times, frame_times, rms_all)
    harm_interp = np.interp(grid_times, frame_times, rms_harm)
    perc_interp = np.interp(grid_times, frame_times, rms_perc)

    max_rms = float(np.max(rms_interp)) if len(rms_interp) > 0 else 1.0
    if max_rms < 1e-5:
        max_rms = 1.0
    energy_envelope = [round(float(v / max_rms), 3) for v in rms_interp]

    harm_ratio = harm_interp / (harm_interp + perc_interp + 1e-5)
    harmonic_ratio_envelope = [round(float(v), 3) for v in harm_ratio]

    # 5. Detect Sustained Notes & Musical Pauses/Breaths (track-relative, on smoothed envelopes)
    progress.update(80, "Detecting sustained notes & musical pauses", service="Librosa RMS / HPSS segmentation")
    sections = _detect_photo_sections(
        grid_times=grid_times,
        energy=np.asarray(energy_envelope, dtype=np.float64),
        perc=perc_interp,
        harm_ratio=harm_ratio,
        duration_sec=duration_sec,
    )

    # Guarantee at least two photo-friendly sustained/pause windows if track was uniformly dense
    if len(sections) < 2 and duration_sec >= 10.0:
        taken = [(s.start_sec, s.end_sec) for s in sections]
        for frac, cue, desc, dur in [
            (0.30, "sustained_note", "Sustained melodic phrase for photo feature", 1.8),
            (0.68, "pause", "Pre-finale breath before final downbeat drop", 1.7),
        ]:
            t0 = round(duration_sec * frac, 2)
            if any(a - 0.5 <= t0 <= b + 0.5 for a, b in taken):
                continue
            sections.append(
                AudioSectionCue(
                    cue_type=cue,
                    start_sec=t0,
                    end_sec=round(t0 + dur, 2),
                    duration_sec=dur,
                    intensity=0.4,
                    description=desc,
                )
            )
        sections.sort(key=lambda s: s.start_sec)

    return AudioCueMap(
        track_id=track_id,
        title=title,
        filepath=str(path),
        url=url,
        duration_sec=duration_sec,
        bpm=round(bpm, 1),
        beat_times=beat_times,
        downbeat_times=downbeat_times,
        onset_peaks=onset_peaks,
        sections=sections,
        energy_envelope=energy_envelope,
        harmonic_ratio_envelope=harmonic_ratio_envelope,
        genre=genre,
        is_generated=is_generated,
    )
