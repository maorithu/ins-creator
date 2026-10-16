import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Pause, Play } from 'lucide-react';
import { AudioCueMap } from './types';

const BAR_COUNT = 160;

function downsample(values: number[], n: number): number[] {
  if (!values.length) return new Array(n).fill(0.1);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const a = Math.floor((i / n) * values.length);
    const b = Math.max(a + 1, Math.floor(((i + 1) / n) * values.length));
    let peak = 0;
    for (let j = a; j < b && j < values.length; j++) peak = Math.max(peak, values[j]);
    out.push(peak);
  }
  return out;
}

/**
 * Preview of the ACTIVE track: audio player + full-length energy waveform with
 * downbeats, sustained/pause windows, the Reel target window and a live playhead.
 * Everything is keyed on `cueMap.track_id`, so switching tracks fully resets it.
 */
export function MusicCuePreview({
  cueMap,
  targetDurationSec,
  autoPlay,
  onAutoPlayConsumed,
}: {
  cueMap: AudioCueMap;
  targetDurationSec: number;
  autoPlay: boolean;
  onAutoPlayConsumed: () => void;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const duration = Math.max(0.1, cueMap.duration_sec);
  const bars = useMemo(() => downsample(cueMap.energy_envelope, BAR_COUNT), [cueMap]);

  // Reset when the active track changes
  useEffect(() => {
    setCurrentTime(0);
    setIsPlaying(false);
    setLoadError(null);
    const el = audioRef.current;
    if (el) {
      el.load();
      if (autoPlay) {
        void el.play().catch(() => {});
        onAutoPlayConsumed();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cueMap.track_id, cueMap.url]);

  // Smooth playhead while playing
  useEffect(() => {
    if (!isPlaying) return;
    let raf = 0;
    const tick = () => {
      if (audioRef.current) setCurrentTime(audioRef.current.currentTime);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [isPlaying]);

  function seekTo(sec: number, play = true) {
    const el = audioRef.current;
    if (!el) return;
    el.currentTime = Math.max(0, Math.min(duration - 0.05, sec));
    setCurrentTime(el.currentTime);
    if (play) void el.play().catch(() => {});
  }

  function togglePlay() {
    const el = audioRef.current;
    if (!el) return;
    if (el.paused) void el.play().catch(() => {});
    else el.pause();
  }

  const pct = (sec: number) => `${Math.min(100, Math.max(0, (sec / duration) * 100))}%`;
  const nextDownbeat = cueMap.downbeat_times.find((d) => d >= currentTime - 0.05);
  const activeSection = cueMap.sections.find((s) => currentTime >= s.start_sec && currentTime <= s.end_sec);

  return (
    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-4">
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-wider text-emerald-700 mb-1">
          Now previewing
        </div>
        <div className="flex items-start justify-between gap-2 mb-1">
          <div className="text-xs font-semibold text-slate-900 leading-snug">{cueMap.title}</div>
          <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-slate-900 text-white shrink-0">
            {cueMap.bpm} BPM • {cueMap.duration_sec.toFixed(1)}s
          </span>
        </div>
        <div className="text-[11px] text-slate-500 mb-2">
          Genre: <span className="font-medium text-slate-700">{cueMap.genre}</span> •{' '}
          {cueMap.downbeat_times.length} downbeats • {cueMap.beat_times.length} beats •{' '}
          {cueMap.sections.length} photo cue{cueMap.sections.length === 1 ? '' : 's'}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={togglePlay}
            aria-label={isPlaying ? 'Pause track preview' : 'Play track preview'}
            className="w-9 h-9 rounded-full bg-slate-900 hover:bg-slate-800 text-white flex items-center justify-center shrink-0 cursor-pointer"
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
          </button>
          <audio
            ref={audioRef}
            key={cueMap.track_id}
            controls
            preload="auto"
            src={cueMap.url}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onEnded={() => setIsPlaying(false)}
            onSeeked={(e) => setCurrentTime(e.currentTarget.currentTime)}
            onTimeUpdate={(e) => !isPlaying && setCurrentTime(e.currentTarget.currentTime)}
            onError={() => setLoadError('This audio file could not be loaded by the browser.')}
            className="w-full h-9"
          />
        </div>
        {loadError && <p className="text-[11px] text-rose-600 mt-1">{loadError}</p>}
      </div>

      {/* Full-length cue map with playhead */}
      <div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-600 mb-1.5">
          <span className="inline-flex items-center gap-1">
            <span className="w-[2px] h-3 bg-slate-900 inline-block" /> Downbeat (jump/turn sync)
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="w-3 h-2.5 rounded-sm bg-indigo-300/70 inline-block" /> Sustained note
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="w-3 h-2.5 rounded-sm bg-amber-300/80 inline-block" /> Pause / breath
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="w-3 h-2.5 rounded-sm border border-dashed border-emerald-600 inline-block" /> Reel length
          </span>
        </div>
        <div
          role="slider"
          tabIndex={0}
          aria-label="Seek within track"
          aria-valuemin={0}
          aria-valuemax={Math.round(duration)}
          aria-valuenow={Math.round(currentTime)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowRight') seekTo(currentTime + 1, false);
            if (e.key === 'ArrowLeft') seekTo(currentTime - 1, false);
            if (e.key === ' ') {
              e.preventDefault();
              togglePlay();
            }
          }}
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            seekTo(((e.clientX - rect.left) / rect.width) * duration);
          }}
          className="relative h-24 rounded-lg bg-white border border-slate-200 overflow-hidden cursor-pointer select-none focus:outline-none focus:ring-2 focus:ring-slate-900/30"
        >
          {/* Reel target window */}
          <div
            className="absolute top-0 bottom-0 left-0 border-r-2 border-dashed border-emerald-600/70 bg-emerald-50/40"
            style={{ width: pct(Math.min(targetDurationSec, duration)) }}
          />
          {cueMap.sections.map((sec, idx) => (
            <div
              key={`${sec.start_sec}-${idx}`}
              style={{ left: pct(sec.start_sec), width: pct(sec.duration_sec) }}
              className={`absolute top-0 bottom-0 flex items-start justify-center pt-1 ${
                sec.cue_type === 'pause' ? 'bg-amber-300/50' : 'bg-indigo-300/45'
              }`}
              title={`${sec.cue_type === 'pause' ? 'Pause' : 'Sustained note'} ${sec.start_sec.toFixed(1)}s–${sec.end_sec.toFixed(1)}s`}
            >
              <span className="text-[8px] font-semibold uppercase text-slate-800 bg-white/85 px-0.5 rounded">
                {sec.cue_type === 'pause' ? 'Pause' : 'Hold'}
              </span>
            </div>
          ))}
          <div className="absolute inset-x-0 bottom-0 h-14 flex items-end gap-[1px] px-[1px]">
            {bars.map((val, idx) => {
              const barTime = ((idx + 0.5) / BAR_COUNT) * duration;
              const played = barTime <= currentTime;
              return (
                <div
                  key={idx}
                  style={{ height: `${Math.max(6, Math.round(val * 100))}%` }}
                  className={`flex-1 rounded-t-[1px] ${played ? 'bg-slate-700' : 'bg-slate-300'}`}
                />
              );
            })}
          </div>
          {cueMap.downbeat_times.map((db, idx) => (
            <div
              key={idx}
              style={{ left: pct(db) }}
              className="absolute top-5 bottom-0 w-[1.5px] bg-slate-900/80"
              title={`Downbeat @ ${db.toFixed(2)}s`}
            />
          ))}
          <div
            className="absolute top-0 bottom-0 w-[2px] bg-rose-500 shadow-[0_0_0_1px_rgba(255,255,255,0.7)]"
            style={{ left: pct(currentTime) }}
          />
        </div>
        <div className="flex justify-between text-[10px] font-mono text-slate-500 mt-1">
          <span>
            {currentTime.toFixed(1)}s
            {activeSection
              ? ` • in ${activeSection.cue_type === 'pause' ? 'pause' : 'sustained note'} (photo slot)`
              : nextDownbeat !== undefined
              ? ` • next downbeat ${nextDownbeat.toFixed(2)}s`
              : ''}
          </span>
          <span>{duration.toFixed(1)}s</span>
        </div>
      </div>

      <div className="space-y-1.5 text-xs text-slate-600">
        <div className="font-semibold text-slate-800">Measure downbeats (click to hear):</div>
        <div className="flex flex-wrap gap-1">
          {cueMap.downbeat_times.slice(0, 16).map((db, idx) => (
            <button
              type="button"
              key={idx}
              onClick={() => seekTo(Math.max(0, db - 0.8))}
              className="px-1.5 py-0.5 rounded bg-white border border-slate-200 hover:border-slate-400 font-mono text-[10px] text-slate-700 cursor-pointer"
            >
              {db.toFixed(2)}s
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-1.5 text-xs text-slate-600">
        <div className="font-semibold text-slate-800">Photo insertion cues:</div>
        {cueMap.sections.length === 0 && <div className="text-[11px] text-slate-500">None detected.</div>}
        {cueMap.sections.map((s, i) => (
          <button
            type="button"
            key={i}
            onClick={() => seekTo(s.start_sec)}
            className="w-full flex items-center justify-between text-[11px] px-2 py-1 rounded hover:bg-white border border-transparent hover:border-slate-200 cursor-pointer"
          >
            <span className="font-medium text-slate-700 inline-flex items-center gap-1.5">
              <span
                className={`w-2 h-2 rounded-sm ${s.cue_type === 'pause' ? 'bg-amber-400' : 'bg-indigo-400'}`}
              />
              {s.cue_type === 'pause' ? 'Pause / breath' : 'Sustained note'}
            </span>
            <span className="font-mono text-slate-500">
              {s.start_sec.toFixed(1)}s – {s.end_sec.toFixed(1)}s ({s.duration_sec.toFixed(1)}s)
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
