from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import librosa
import numpy as np

from backend.models.schemas import AudioCueMap, AudioSectionCue


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

    try:
        y, sr = librosa.load(str(path), sr=22050, mono=True)
    except Exception:
        # Use bundled imageio_ffmpeg binary to convert .m4a / .mp3 / .aac / video audio to wav
        import subprocess
        import imageio_ffmpeg

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
    y_harm, y_perc = librosa.effects.hpss(y)
    rms_all = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    rms_harm = librosa.feature.rms(y=y_harm, hop_length=hop_length)[0]
    rms_perc = librosa.feature.rms(y=y_perc, hop_length=hop_length)[0]

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

    # 5. Detect Sustained Notes & Musical Pauses/Breaths
    sections: List[AudioSectionCue] = []
    n_steps = len(grid_times)
    median_e = float(np.median(energy_envelope)) if energy_envelope else 0.5

    # Scan with a sliding window for (a) Musical Pauses (low energy dip >= 0.8s)
    # and (b) Sustained Notes (high harmonic ratio >= 0.65 & moderate energy >= 1.1s)
    i = 5  # skip very start
    while i < n_steps - 10:
        # Check for pause/breath dip
        window_e = energy_envelope[i : i + 10]
        window_h = harmonic_ratio_envelope[i : i + 12]
        mean_e = float(np.mean(window_e))
        mean_h = float(np.mean(window_h))

        if mean_e < max(0.24, median_e * 0.58):
            # Extend pause window
            end_i = i + 10
            while end_i < n_steps - 3 and energy_envelope[end_i] < max(0.28, median_e * 0.65):
                end_i += 1
            start_t = round(float(grid_times[i]), 2)
            end_t = round(float(grid_times[min(n_steps - 1, end_i)]), 2)
            dur = round(end_t - start_t, 2)
            if dur >= 0.8:
                sections.append(
                    AudioSectionCue(
                        cue_type="pause",
                        start_sec=start_t,
                        end_sec=min(end_t, round(start_t + 2.6, 2)),
                        duration_sec=min(dur, 2.6),
                        intensity=round(mean_e, 3),
                        description="Musical pause / breath ideal for still photo highlight with Ken Burns",
                    )
                )
                i = end_i + 8
                continue

        # Check for sustained harmonic note
        if mean_h > 0.66 and mean_e >= 0.22:
            end_i = i + 12
            while (
                end_i < n_steps - 3
                and harmonic_ratio_envelope[end_i] > 0.62
                and end_i - i < 28
            ):
                end_i += 1
            start_t = round(float(grid_times[i]), 2)
            end_t = round(float(grid_times[min(n_steps - 1, end_i)]), 2)
            dur = round(end_t - start_t, 2)
            if dur >= 1.1:
                sections.append(
                    AudioSectionCue(
                        cue_type="sustained_note",
                        start_sec=start_t,
                        end_sec=end_t,
                        duration_sec=dur,
                        intensity=round(mean_e, 3),
                        description="Sustained harmonic note ideal for expressive photo + slow zoom",
                    )
                )
                i = end_i + 10
                continue

        i += 3

    # Guarantee at least two photo-friendly sustained/pause windows if track was uniformly dense
    if len(sections) < 2 and duration_sec >= 10.0:
        t1 = round(duration_sec * 0.28, 2)
        t2 = round(duration_sec * 0.68, 2)
        sections.append(
            AudioSectionCue(
                cue_type="sustained_note",
                start_sec=t1,
                end_sec=round(t1 + 1.8, 2),
                duration_sec=1.8,
                intensity=0.45,
                description="Sustained melodic phrase for photo feature",
            )
        )
        sections.append(
            AudioSectionCue(
                cue_type="pause",
                start_sec=t2,
                end_sec=round(t2 + 1.7, 2),
                duration_sec=1.7,
                intensity=0.30,
                description="Pre-finale breath before final downbeat drop",
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
