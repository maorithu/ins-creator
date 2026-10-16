import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Pause, Play, RefreshCw, Type } from 'lucide-react';
import { InstagramPostCopy } from './types';

interface HookStyleDef {
  id: string;
  label: string;
  description: string;
  position: string;
  animation: string;
}
interface HookAnimDef {
  id: string;
  label: string;
}

const POSITIONS = [
  { id: 'auto', label: 'Auto' },
  { id: 'top', label: 'Top' },
  { id: 'center', label: 'Center' },
  { id: 'bottom', label: 'Bottom' },
];

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

function previewUrl(params: Record<string, string | number | boolean | undefined | null>): string {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
  });
  return `/api/preview/hook-frame?${q.toString()}`;
}

/**
 * Pick the on-screen hook text style with real previews. Thumbnails & the large
 * preview are rendered by the same backend engine as the MP4, so they match exactly.
 */
export function HookStyleStudio({
  postCopy,
  setPostCopy,
  sessionId,
  onApply,
  isRendering,
}: {
  postCopy: InstagramPostCopy;
  setPostCopy: (pc: InstagramPostCopy) => void;
  sessionId?: string;
  onApply: () => void;
  isRendering: boolean;
}) {
  const [styles, setStyles] = useState<HookStyleDef[]>([]);
  const [animations, setAnimations] = useState<HookAnimDef[]>([]);
  const [previewClosing, setPreviewClosing] = useState(false);
  const [isAnimating, setIsAnimating] = useState(false);
  const [animFrameUrl, setAnimFrameUrl] = useState<string | null>(null);
  const [appliedSignature, setAppliedSignature] = useState<string>('');
  const animTimerRef = useRef<number | null>(null);

  const style = postCopy.video_title_style || 'bold_center_impact';
  const animation = postCopy.hook_text_animation || 'auto';
  const position = postCopy.hook_text_position || 'auto';
  const hookDur = postCopy.hook_duration_sec || 2.6;
  const text = previewClosing ? postCopy.ending_call_to_action : postCopy.hook_title_overlay;
  const debouncedText = useDebounced(text, 450);
  const signature = `${style}|${animation}|${position}|${hookDur}|${postCopy.hook_title_overlay}|${postCopy.ending_call_to_action}`;

  useEffect(() => {
    fetch('/api/hook-styles')
      .then((r) => r.json())
      .then((d) => {
        setStyles(d.styles || []);
        setAnimations(d.animations || []);
      })
      .catch(() => {});
  }, []);

  // Treat the style present when the component first mounts (i.e. what's in the current MP4) as applied
  useEffect(() => {
    setAppliedSignature(signature);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  useEffect(() => () => stopAnimation(), []);

  const common = {
    text: debouncedText,
    session_id: sessionId,
    position,
    animation,
    duration: previewClosing ? 2.0 : hookDur,
    closing: previewClosing,
  };
  const largeUrl = previewUrl({ ...common, style, t: previewClosing ? 1.6 : Math.min(hookDur - 0.35, 1.8), width: 360 });

  const thumbs = useMemo(
    () =>
      styles.map((s) => ({
        ...s,
        url: previewUrl({ ...common, style: s.id, animation: 'none', t: 1.5, width: 180 }),
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [styles, debouncedText, sessionId, position, previewClosing]
  );

  function patch(p: Partial<InstagramPostCopy>) {
    stopAnimation();
    setPostCopy({ ...postCopy, ...p });
  }

  function stopAnimation() {
    if (animTimerRef.current) {
      window.clearInterval(animTimerRef.current);
      animTimerRef.current = null;
    }
    setIsAnimating(false);
    setAnimFrameUrl(null);
  }

  function playAnimation() {
    stopAnimation();
    const dur = previewClosing ? 2.0 : hookDur;
    const fps = 12;
    const total = Math.max(2, Math.round(dur * fps));
    const urls = Array.from({ length: total }, (_, i) =>
      previewUrl({ ...common, text, style, t: (i / fps).toFixed(3), width: 360 })
    );
    // Preload all frames, then play them back in sequence
    let loaded = 0;
    setIsAnimating(true);
    urls.forEach((u) => {
      const img = new Image();
      img.onload = img.onerror = () => {
        loaded += 1;
        if (loaded === urls.length) {
          let idx = 0;
          animTimerRef.current = window.setInterval(() => {
            setAnimFrameUrl(urls[idx]);
            idx += 1;
            if (idx >= urls.length) {
              if (animTimerRef.current) window.clearInterval(animTimerRef.current);
              animTimerRef.current = null;
              window.setTimeout(() => {
                setIsAnimating(false);
                setAnimFrameUrl(null);
              }, 700);
            }
          }, 1000 / fps);
        }
      };
      img.src = u;
    });
  }

  const activeDef = styles.find((s) => s.id === style);
  const effectiveAnim =
    animation === 'auto' ? activeDef?.animation || 'fade_in' : animation;
  const dirty = signature !== appliedSignature;

  return (
    <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/60 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h4 className="text-xs font-semibold text-slate-900 flex items-center gap-1.5">
            <Type className="w-3.5 h-3.5" /> On-Screen Hook Text Style
          </h4>
          <p className="text-[11px] text-slate-500">
            Previews are rendered by the same engine as your MP4, on your first clip&apos;s frame.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {dirty && <span className="text-[10px] font-medium text-amber-700">Unsaved style changes</span>}
          <button
            type="button"
            onClick={() => {
              setAppliedSignature(signature);
              onApply();
            }}
            disabled={isRendering}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-xs font-semibold cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRendering ? 'animate-spin' : ''}`} />
            {isRendering ? 'Rendering…' : 'Apply & Re-Render MP4'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Style gallery */}
        <div className="lg:col-span-7">
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-2.5 max-h-[520px] overflow-y-auto pr-1">
            {thumbs.map((s) => {
              const selected = s.id === style;
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => patch({ video_title_style: s.id })}
                  title={s.description}
                  aria-pressed={selected}
                  className={`group text-left rounded-lg overflow-hidden border-2 bg-white transition cursor-pointer ${
                    selected ? 'border-slate-900 ring-2 ring-slate-900/15' : 'border-transparent hover:border-slate-300'
                  }`}
                >
                  <div className="aspect-[9/16] bg-slate-200 overflow-hidden">
                    <img
                      src={s.url}
                      alt={`${s.label} preview`}
                      loading="lazy"
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div className="px-1.5 py-1">
                    <div className={`text-[10px] font-semibold leading-tight ${selected ? 'text-slate-900' : 'text-slate-700'}`}>
                      {s.label}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Large live preview + controls */}
        <div className="lg:col-span-5 space-y-3">
          <div className="flex items-center gap-1.5">
            {(['hook', 'closing'] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => {
                  stopAnimation();
                  setPreviewClosing(k === 'closing');
                }}
                className={`text-[11px] px-2.5 py-1 rounded-md font-medium cursor-pointer ${
                  (k === 'closing') === previewClosing
                    ? 'bg-slate-900 text-white'
                    : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
                }`}
              >
                {k === 'hook' ? 'Opening hook' : 'Closing line'}
              </button>
            ))}
          </div>
          <div className="relative mx-auto w-full max-w-[270px] aspect-[9/16] rounded-xl overflow-hidden bg-slate-900 shadow-md">
            <img
              src={animFrameUrl || largeUrl}
              alt="Live hook text preview"
              className="w-full h-full object-cover"
            />
            {style !== 'none' && (
              <button
                type="button"
                onClick={() => (isAnimating ? stopAnimation() : playAnimation())}
                className="absolute bottom-2 right-2 inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-black/60 hover:bg-black/75 text-white text-[10px] font-semibold backdrop-blur cursor-pointer"
              >
                {isAnimating ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                {isAnimating ? (animFrameUrl ? 'Playing' : 'Loading…') : 'Play animation'}
              </button>
            )}
          </div>
          {activeDef && <p className="text-[11px] text-slate-600 text-center">{activeDef.description}</p>}

          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="block text-[11px] font-medium text-slate-600 mb-1">Animation</label>
              <select
                value={animation}
                onChange={(e) => patch({ hook_text_animation: e.target.value })}
                className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-900"
              >
                {animations.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.id === 'auto' ? `Style default (${effectiveAnim.replace('_', ' ')})` : a.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-slate-600 mb-1">
                Hook duration: {hookDur.toFixed(1)}s
              </label>
              <input
                type="range"
                min={1.5}
                max={5}
                step={0.1}
                value={hookDur}
                onChange={(e) => patch({ hook_duration_sec: Number(e.target.value) })}
                className="w-full accent-slate-900"
              />
            </div>
          </div>
          <div>
            <label className="block text-[11px] font-medium text-slate-600 mb-1">Position</label>
            <div className="grid grid-cols-4 gap-1">
              {POSITIONS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => patch({ hook_text_position: p.id })}
                  aria-pressed={position === p.id}
                  className={`text-[11px] py-1 rounded-md font-medium cursor-pointer ${
                    position === p.id
                      ? 'bg-slate-900 text-white'
                      : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
