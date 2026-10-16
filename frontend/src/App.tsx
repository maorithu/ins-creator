import React, { useEffect, useState } from 'react';
import {
  Sparkles,
  Search,
  Music,
  Film,
  Image as ImageIcon,
  Play,
  Download,
  Scissors,
  Sliders,
  Copy,
  Check,
  Upload,
  RefreshCw,
  Wand2,
  Zap,
  Award,
  Camera,
  Share2,
  Settings,
  ArrowUpDown,
  ChevronRight,
  CheckCircle2,
  FolderOpen,
} from 'lucide-react';
import {
  AudioCueMap,
  InstagramPostCopy,
  MediaItem,
  StylePreset,
  TimelineClip,
  WorkflowSession,
} from './types';

const PHOTO_EFFECT_OPTIONS = [
  { value: 'ken_burns_zoom_in', label: 'Ken Burns Slow Zoom In (Focus Dancer)' },
  { value: 'ken_burns_zoom_out', label: 'Ken Burns Pull Out Reveal' },
  { value: 'ken_burns_pan_diag', label: 'Ken Burns Diagonal Stage Pan' },
  { value: 'ken_burns_pan_lr', label: 'Ken Burns Horizontal Glide' },
  { value: 'beat_pulse_zoom', label: 'Beat-Pulse Dynamic Zoom' },
  { value: 'soft_glow_dissolve', label: 'Soft Stage Glow Dissolve' },
];

const TRANSITION_OPTIONS = [
  { value: 'cut_on_beat', label: 'Hard Cut on Beat' },
  { value: 'flash_white', label: 'Stage Strobe White Flash' },
  { value: 'cross_dissolve', label: 'Smooth Lyrical Dissolve' },
  { value: 'zoom_whip', label: 'Kinetic Zoom Whip' },
];

export function App() {
  // Preset & Music catalog state
  const [presets, setPresets] = useState<StylePreset[]>([]);
  const [musicTracks, setMusicTracks] = useState<AudioCueMap[]>([]);
  const [matchedMedia, setMatchedMedia] = useState<MediaItem[]>([]);

  // User workflow inputs
  const [searchQuery, setSearchQuery] = useState(
    'daughter contemporary dance competition split leaps, rehearsal turns & backstage smiles'
  );
  const [mediaSource, setMediaSource] = useState<'auto' | 'google_photos' | 'local' | 'sample'>('auto');
  const [localFolderPath, setLocalFolderPath] = useState('');
  const [selectedPresetId, setSelectedPresetId] = useState('competition_stage_glory');
  const [supplementalDirections, setSupplementalDirections] = useState(
    'Sync her highest grand jeté jump peak to the main measure downbeat with slow-mo at the apex, insert a poised stage photo during the sustained note with Ken Burns zoom, and write an inspiring proud-parent caption.'
  );
  const [selectedMusicId, setSelectedMusicId] = useState('competition_edm_pop');
  const [customMusicPrompt, setCustomMusicPrompt] = useState('');
  const [targetDurationSec, setTargetDurationSec] = useState(16);

  // Active generated session state
  const [session, setSession] = useState<WorkflowSession | null>(null);
  const [timelineClips, setTimelineClips] = useState<TimelineClip[]>([]);
  const [postCopy, setPostCopy] = useState<InstagramPostCopy | null>(null);
  const [selectedCaptionVariantIdx, setSelectedCaptionVariantIdx] = useState<number>(-1); // -1 = primary

  // UI status state
  const [isSearchingMedia, setIsSearchingMedia] = useState(false);
  const [isGeneratingSession, setIsGeneratingSession] = useState(false);
  const [isUpdatingTimeline, setIsUpdatingTimeline] = useState(false);
  const [isGeneratingMusic, setIsGeneratingMusic] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [geminiKeyInput, setGeminiKeyInput] = useState('');
  const [googleTokenInput, setGoogleTokenInput] = useState('');
  const [statusBanner, setStatusBanner] = useState<string | null>(null);

  useEffect(() => {
    void loadInitialCatalog();
  }, []);

  async function loadInitialCatalog() {
    try {
      const [pRes, mRes, mediaRes] = await Promise.all([
        fetch('/api/presets'),
        fetch('/api/music/tracks'),
        fetch(`/api/media/search?query=${encodeURIComponent(searchQuery)}&source=auto`),
      ]);
      const pData: StylePreset[] = await pRes.json();
      const mData: AudioCueMap[] = await mRes.json();
      const mediaData: MediaItem[] = await mediaRes.json();

      setPresets(pData);
      setMusicTracks(mData);
      setMatchedMedia(mediaData);

      // Automatically generate an initial complete session so the studio is immediately populated
      await handleGenerateSession(pData[0]?.id || 'competition_stage_glory', mData[0]?.track_id || 'competition_edm_pop');
    } catch (err) {
      console.error('Failed loading initial catalog:', err);
    }
  }

  async function handleSearchMedia() {
    setIsSearchingMedia(true);
    setStatusBanner('Searching Google Photos & local dance library with computer vision kinematics...');
    try {
      const params = new URLSearchParams({
        query: searchQuery,
        source: mediaSource,
      });
      if (localFolderPath.trim()) {
        params.set('local_folder_path', localFolderPath.trim());
      }
      const res = await fetch(`/api/media/search?${params.toString()}`);
      const data: MediaItem[] = await res.json();
      setMatchedMedia(data);
      setStatusBanner(`Found & analyzed ${data.length} dance videos/photos matching "${searchQuery}"`);
    } catch (err) {
      console.error(err);
      setStatusBanner('Error searching media.');
    } finally {
      setIsSearchingMedia(false);
    }
  }

  async function handleGooglePhotosPicker() {
    setStatusBanner('Connecting to Google Photos Picker API...');
    try {
      const res = await fetch('/api/media/google-photos/picker-session', { method: 'POST' });
      const data = await res.json();
      if (data.configured && data.pickerUri) {
        window.open(data.pickerUri, '_blank');
        setStatusBanner('Google Photos Picker opened! Select your dance album/photos and click Fetch Media.');
      } else {
        setShowSettingsModal(true);
        setStatusBanner(
          data.message ||
            'Configure your Google Photos OAuth Bearer Token in Settings (or use Smart Local / Built-in Dance Event Media).'
        );
      }
    } catch (err) {
      console.error(err);
    }
  }

  async function handleMediaUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const formData = new FormData();
    Array.from(files).forEach((f) => formData.append('files', f));
    formData.append('query', searchQuery);

    setStatusBanner(`Uploading & running MediaPipe/CV dance kinematics on ${files.length} file(s)...`);
    try {
      const res = await fetch('/api/media/upload', {
        method: 'POST',
        body: formData,
      });
      const uploaded: MediaItem[] = await res.json();
      setMatchedMedia((prev) => {
        const existingIds = new Set(uploaded.map((u) => u.id));
        return [...uploaded, ...prev.filter((p) => !existingIds.has(p.id))];
      });
      setStatusBanner(`Uploaded and analyzed ${uploaded.length} media item(s)!`);
    } catch (err) {
      console.error(err);
    }
  }

  async function handleMusicUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);

    setIsGeneratingMusic(true);
    setStatusBanner(`Uploading "${file.name}" & extracting downbeats, sustained notes & pauses with Librosa...`);
    try {
      const res = await fetch('/api/music/upload', {
        method: 'POST',
        body: formData,
      });
      const cueMap: AudioCueMap = await res.json();
      setMusicTracks((prev) => [cueMap, ...prev]);
      setSelectedMusicId(cueMap.track_id);
      setStatusBanner(`Analyzed "${cueMap.title}" (${cueMap.bpm} BPM, ${cueMap.downbeat_times.length} downbeats)!`);
    } catch (err) {
      console.error(err);
    } finally {
      setIsGeneratingMusic(false);
    }
  }

  async function handleGenerateCustomMusic() {
    if (!customMusicPrompt.trim()) return;
    setIsGeneratingMusic(true);
    setStatusBanner(`Generating custom dance track for "${customMusicPrompt}" & mapping beat cues...`);
    try {
      const res = await fetch('/api/music/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: customMusicPrompt,
          target_duration_sec: targetDurationSec,
        }),
      });
      const cueMap: AudioCueMap = await res.json();
      setMusicTracks((prev) => [cueMap, ...prev]);
      setSelectedMusicId(cueMap.track_id);
      setStatusBanner(`Generated & beat-mapped "${cueMap.title}"!`);
    } catch (err) {
      console.error(err);
    } finally {
      setIsGeneratingMusic(false);
    }
  }

  async function handleGenerateSession(overridePresetId?: string, overrideMusicId?: string) {
    setIsGeneratingSession(true);
    setStatusBanner(
      'Running AI Choreography Studio: aligning jump peaks & turns to downbeats, placing photos on sustained notes/pauses with Ken Burns, rendering 9:16 MP4 & exporting CapCut Draft...'
    );
    try {
      const res = await fetch('/api/sessions/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          search_query: searchQuery,
          media_source: mediaSource,
          local_folder_path: localFolderPath.trim() || null,
          style_preset_id: overridePresetId || selectedPresetId,
          supplemental_directions: supplementalDirections,
          music_track_id: overrideMusicId || selectedMusicId,
          music_generation_prompt: null,
          target_duration_sec: targetDurationSec,
          auto_render_mp4: true,
          auto_export_capcut: true,
        }),
      });
      const sess: WorkflowSession = await res.json();
      setSession(sess);
      setTimelineClips(sess.timeline_clips);
      setPostCopy(sess.post_copy || null);
      setMatchedMedia(sess.matched_media);
      setSelectedCaptionVariantIdx(-1);
      setStatusBanner(
        `Session ${sess.session_id} ready! Rendered 9:16 MP4 Reel + installed editable CapCut Desktop Draft.`
      );
    } catch (err) {
      console.error(err);
      setStatusBanner('Error generating workflow session.');
    } finally {
      setIsGeneratingSession(false);
    }
  }

  async function handleApplyTimelineAdjustments(reRenderMp4: boolean) {
    if (!session) return;
    setIsUpdatingTimeline(true);
    setStatusBanner(
      reRenderMp4
        ? 'Re-rendering 9:16 MP4 video and updating CapCut Desktop Draft & FCPXML...'
        : 'Updating CapCut Desktop Draft & FCPXML timeline...'
    );
    try {
      const res = await fetch(`/api/sessions/${session.session_id}/timeline`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          timeline_clips: timelineClips,
          post_copy: postCopy,
          color_grade: session.color_grade,
          re_render_mp4: reRenderMp4,
        }),
      });
      const updated: WorkflowSession = await res.json();
      setSession(updated);
      setTimelineClips(updated.timeline_clips);
      setPostCopy(updated.post_copy || null);
      setStatusBanner(
        reRenderMp4
          ? 'MP4 Reel re-rendered and CapCut Draft updated!'
          : 'Timeline saved & synced to CapCut Draft!'
      );
    } catch (err) {
      console.error(err);
    } finally {
      setIsUpdatingTimeline(false);
    }
  }

  function handleClipFieldChange(index: number, field: keyof TimelineClip, value: unknown) {
    setTimelineClips((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  }

  function handleSwapClipOrder(index: number, direction: -1 | 1) {
    const targetIdx = index + direction;
    if (targetIdx < 0 || targetIdx >= timelineClips.length) return;
    setTimelineClips((prev) => {
      const copy = [...prev];
      const temp = copy[index];
      copy[index] = copy[targetIdx];
      copy[targetIdx] = temp;
      return copy;
    });
  }

  function copyToClipboard(key: string, text: string) {
    navigator.clipboard.writeText(text);
    setCopiedField(key);
    setTimeout(() => setCopiedField(null), 2000);
  }

  async function handleSaveSettings() {
    await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        gemini_api_key: geminiKeyInput,
        google_photos_access_token: googleTokenInput,
      }),
    });
    setShowSettingsModal(false);
    setStatusBanner('API credentials updated for live Google Photos & Gemini calls.');
  }

  const activeCueMap =
    session?.audio_cue_map ||
    musicTracks.find((t) => t.track_id === selectedMusicId) ||
    musicTracks[0];

  const displayedCaption =
    selectedCaptionVariantIdx === -1
      ? postCopy?.caption_primary || ''
      : postCopy?.caption_alternatives?.[selectedCaptionVariantIdx]?.text || '';

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Studio Header */}
      <header className="border-b border-slate-800/80 bg-slate-900/70 backdrop-blur-md sticky top-0 z-30">
        <div className="max-w-[1600px] mx-auto px-6 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-pink-500 via-fuchsia-500 to-amber-500 flex items-center justify-center shadow-lg shadow-pink-500/20">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-lg font-bold tracking-tight bg-gradient-to-r from-white via-pink-200 to-amber-200 bg-clip-text text-transparent">
                  Ins-Creator Studio
                </h1>
                <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-pink-500/15 text-pink-300 border border-pink-500/30">
                  Dance Reel & CapCut AI Workflow
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Google Photos Ingestion • Jump Apex & Turn Downbeat Sync • Sustained-Note Ken Burns Photos • CapCut Draft Export
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowSettingsModal(true)}
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-800/80 hover:bg-slate-800 text-xs font-medium text-slate-300 border border-slate-700/70 transition"
            >
              <Settings className="w-4 h-4 text-pink-400" />
              Google Photos / API Keys
            </button>

            <button
              onClick={() => handleGenerateSession()}
              disabled={isGeneratingSession}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-pink-600 via-fuchsia-600 to-amber-500 hover:from-pink-500 hover:to-amber-400 text-white font-semibold text-sm shadow-lg shadow-pink-600/25 disabled:opacity-50 transition cursor-pointer"
            >
              {isGeneratingSession ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Wand2 className="w-4 h-4" />
              )}
              {isGeneratingSession ? 'Creating Beat-Synced Reel...' : 'Auto-Create Reel & Post'}
            </button>
          </div>
        </div>

        {statusBanner && (
          <div className="bg-gradient-to-r from-pink-950/60 via-slate-900 to-indigo-950/60 border-t border-pink-500/20 px-6 py-1.5 text-xs text-pink-200 flex items-center justify-between max-w-[1600px] mx-auto">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 text-pink-400 shrink-0" />
              <span>{statusBanner}</span>
            </div>
            <button
              onClick={() => setStatusBanner(null)}
              className="text-slate-400 hover:text-white text-[11px]"
            >
              Dismiss
            </button>
          </div>
        )}
      </header>

      {/* Main 12-Column Studio Grid */}
      <main className="max-w-[1600px] w-full mx-auto px-6 py-6 grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1">
        {/* LEFT COLUMN (4 cols): Query Input, Google Photos Source, Style Presets, Supplemental Directions, Music */}
        <div className="lg:col-span-4 space-y-5">
          {/* 1. Photo & Video Search Query + Google Photos Ingestion */}
          <section className="rounded-2xl bg-slate-900/90 border border-slate-800 p-5 shadow-xl">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <Camera className="w-4 h-4 text-pink-400" />
                1. Event Search Query & Google Photos
              </h2>
              <span className="text-[11px] text-slate-400">
                {matchedMedia.length} items indexed
              </span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">
                  Photo & Video Search Query (Rehearsal, Training, Competition)
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="e.g., daughter contemporary competition split leaps and turns"
                    className="flex-1 rounded-xl bg-slate-950 border border-slate-700/80 px-3.5 py-2 text-xs text-white focus:outline-none focus:border-pink-500"
                  />
                  <button
                    onClick={handleSearchMedia}
                    disabled={isSearchingMedia}
                    className="px-3.5 py-2 rounded-xl bg-pink-600/20 hover:bg-pink-600/30 border border-pink-500/40 text-pink-200 text-xs font-medium flex items-center gap-1.5 shrink-0"
                  >
                    <Search className="w-3.5 h-3.5" />
                    Fetch
                  </button>
                </div>
              </div>

              {/* Quick Query Chips */}
              <div className="flex flex-wrap gap-1.5">
                {[
                  'Competition stage split leaps & turns',
                  'Dance rehearsal studio triple pirouette',
                  'Technique training firebird jumps & smiles',
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => {
                      setSearchQuery(q);
                    }}
                    className="text-[11px] px-2.5 py-1 rounded-lg bg-slate-800/90 hover:bg-slate-700 text-slate-300 border border-slate-700/60 transition"
                  >
                    {q}
                  </button>
                ))}
              </div>

              {/* Source selector & Google Photos Picker / Upload */}
              <div className="grid grid-cols-2 gap-2 pt-1">
                <button
                  onClick={handleGooglePhotosPicker}
                  className="flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-slate-800/90 hover:bg-slate-800 border border-slate-700 text-xs text-slate-200 font-medium transition"
                >
                  <ImageIcon className="w-3.5 h-3.5 text-amber-400" />
                  Google Photos Picker
                </button>

                <label className="flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-slate-800/90 hover:bg-slate-800 border border-slate-700 text-xs text-slate-200 font-medium transition cursor-pointer">
                  <Upload className="w-3.5 h-3.5 text-pink-400" />
                  Upload Photos/Videos
                  <input
                    type="file"
                    multiple
                    accept="video/*,image/*"
                    onChange={handleMediaUpload}
                    className="hidden"
                  />
                </label>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <FolderOpen className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                <input
                  type="text"
                  value={localFolderPath}
                  onChange={(e) => setLocalFolderPath(e.target.value)}
                  placeholder="Optional local folder path (e.g. ~/Pictures/DanceEvent)"
                  className="w-full rounded-lg bg-slate-950/70 border border-slate-800 px-2.5 py-1.5 text-[11px] text-slate-300 focus:outline-none focus:border-pink-500"
                />
              </div>
            </div>
          </section>

          {/* 2. Default Style Presets + Supplemental Directions */}
          <section className="rounded-2xl bg-slate-900/90 border border-slate-800 p-5 shadow-xl">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
              <Sparkles className="w-4 h-4 text-amber-400" />
              2. Creative Style Preset & Supplemental Directions
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mb-4">
              {presets.map((preset) => {
                const isSelected = preset.id === selectedPresetId;
                return (
                  <button
                    key={preset.id}
                    onClick={() => {
                      setSelectedPresetId(preset.id);
                      setSelectedMusicId(preset.default_music_genre);
                    }}
                    className={`text-left p-3 rounded-xl border transition flex flex-col justify-between ${
                      isSelected
                        ? 'bg-pink-500/15 border-pink-500 shadow-md shadow-pink-500/10'
                        : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between gap-1 mb-1">
                        <span className="text-xs font-bold text-white line-clamp-1">
                          {preset.name}
                        </span>
                        <span
                          className="w-2 h-2 rounded-full shrink-0"
                          style={{ backgroundColor: preset.badge_color }}
                        />
                      </div>
                      <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                        {preset.tagline}
                      </p>
                    </div>
                    <div className="mt-2 flex items-center gap-1.5 text-[10px] text-pink-300 font-medium">
                      <span>{Math.round(preset.video_to_photo_ratio * 100)}% video</span>
                      <span>•</span>
                      <span>{preset.cut_pacing.replace('_', ' ')}</span>
                    </div>
                  </button>
                );
              })}
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Supplemental Creative Directions (Free-Form Requirements)
              </label>
              <textarea
                rows={3}
                value={supplementalDirections}
                onChange={(e) => setSupplementalDirections(e.target.value)}
                placeholder="Type extra instructions: e.g., Highlight her split leap on the biggest beat drop, insert a backstage smiling photo during the soft piano pause with Ken Burns zoom..."
                className="w-full rounded-xl bg-slate-950 border border-slate-700/80 p-3 text-xs text-slate-100 leading-relaxed focus:outline-none focus:border-pink-500"
              />
            </div>
          </section>

          {/* 3. Music Selection, AI Music Generation & Beat Sync Settings */}
          <section className="rounded-2xl bg-slate-900/90 border border-slate-800 p-5 shadow-xl">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <Music className="w-4 h-4 text-cyan-400" />
                3. Music & Beat/Cue Synchronization
              </h2>
              <label className="text-[11px] px-2.5 py-1 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 text-cyan-300 border border-cyan-500/30 cursor-pointer flex items-center gap-1">
                <Upload className="w-3 h-3" />
                Upload MP3/WAV
                <input
                  type="file"
                  accept="audio/*"
                  onChange={handleMusicUpload}
                  className="hidden"
                />
              </label>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">
                  Active Music Track (Auto-Analyzed for Downbeats, Sustained Notes & Pauses)
                </label>
                <select
                  value={selectedMusicId}
                  onChange={(e) => setSelectedMusicId(e.target.value)}
                  className="w-full rounded-xl bg-slate-950 border border-slate-700/80 px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500"
                >
                  {musicTracks.map((t) => (
                    <option key={t.track_id} value={t.track_id}>
                      {t.title} — {t.bpm} BPM ({t.downbeat_times.length} downbeats, {t.sections.length} photo cues)
                    </option>
                  ))}
                </select>
              </div>

              {activeCueMap && (
                <div className="rounded-xl bg-slate-950/90 border border-slate-800 p-3 space-y-2">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-cyan-300 font-semibold">
                      Tempo: {activeCueMap.bpm} BPM
                    </span>
                    <span className="text-amber-300">
                      {activeCueMap.downbeat_times.length} Measure Downbeats
                    </span>
                    <span className="text-purple-300">
                      {activeCueMap.sections.length} Sustained/Pause Cues
                    </span>
                  </div>
                  <audio
                    controls
                    src={activeCueMap.url}
                    className="w-full h-8 opacity-90"
                  />
                </div>
              )}

              {/* AI Custom Music Generator */}
              <div className="pt-1 border-t border-slate-800/80">
                <label className="block text-xs text-slate-400 mb-1">
                  Or Generate Custom AI Dance Music from Prompt
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={customMusicPrompt}
                    onChange={(e) => setCustomMusicPrompt(e.target.value)}
                    placeholder="e.g., Emotional lyrical piano building to epic competition drop"
                    className="flex-1 rounded-xl bg-slate-950 border border-slate-700/80 px-3 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500"
                  />
                  <button
                    onClick={handleGenerateCustomMusic}
                    disabled={isGeneratingMusic}
                    className="px-3 py-1.5 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-200 text-xs font-medium shrink-0"
                  >
                    {isGeneratingMusic ? '...' : 'Generate'}
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>

        {/* CENTER COLUMN (5 cols): Beat & Kinematics Waveform + Interactive Timeline + Media Pool */}
        <div className="lg:col-span-5 space-y-5">
          {/* Musical Cue Map & Choreographic Beat Alignment Visualizer */}
          <section className="rounded-2xl bg-slate-900/90 border border-slate-800 p-5 shadow-xl">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Zap className="w-4 h-4 text-amber-400" />
                  Beat-Sync & Choreographic Cue Map
                </h2>
                <p className="text-[11px] text-slate-400">
                  Amber bars = Measure Downbeats (Jump Apex / Turn Sync) • Purple zones = Sustained Notes & Pauses (Ken Burns Photos)
                </p>
              </div>
              {session && (
                <span className="text-[11px] font-mono px-2.5 py-1 rounded-md bg-slate-800 text-slate-300">
                  {timelineClips.length} Cuts • {session.target_duration_sec}s
                </span>
              )}
            </div>

            {/* Waveform + Downbeat & Sustained/Pause Cues Bar */}
            {activeCueMap && (
              <div className="relative h-24 rounded-xl bg-slate-950 border border-slate-800 p-3 overflow-hidden flex flex-col justify-end">
                {/* Sustained Note / Pause Highlight Zones */}
                {activeCueMap.sections.map((sec, idx) => {
                  const leftPct = Math.min(95, (sec.start_sec / targetDurationSec) * 100);
                  const widthPct = Math.max(4, (sec.duration_sec / targetDurationSec) * 100);
                  if (leftPct >= 100) return null;
                  return (
                    <div
                      key={idx}
                      style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                      className="absolute top-0 bottom-0 bg-purple-500/20 border-x border-purple-400/40 flex items-start justify-center pt-1"
                      title={`${sec.cue_type}: ${sec.description}`}
                    >
                      <span className="text-[9px] font-semibold uppercase tracking-tighter text-purple-200 bg-purple-950/80 px-1 rounded">
                        {sec.cue_type === 'pause' ? 'Pause (Photo)' : 'Sustained (Photo)'}
                      </span>
                    </div>
                  );
                })}

                {/* Downbeat vertical markers */}
                {activeCueMap.downbeat_times.map((db, idx) => {
                  const leftPct = (db / targetDurationSec) * 100;
                  if (leftPct > 100) return null;
                  return (
                    <div
                      key={idx}
                      style={{ left: `${leftPct}%` }}
                      className="absolute top-5 bottom-0 w-0.5 bg-amber-400/80 z-10"
                      title={`Measure Downbeat @ ${db}s`}
                    >
                      <span className="absolute -top-4 -translate-x-1/2 text-[9px] font-mono text-amber-300">
                        {db.toFixed(1)}s
                      </span>
                    </div>
                  );
                })}

                {/* RMS Energy Envelope Bars */}
                <div className="flex items-end gap-[2px] h-12 w-full z-0">
                  {activeCueMap.energy_envelope
                    .slice(0, Math.min(activeCueMap.energy_envelope.length, Math.round(targetDurationSec * 10)))
                    .map((val, idx) => (
                      <div
                        key={idx}
                        style={{ height: `${Math.max(12, Math.round(val * 100))}%` }}
                        className="flex-1 bg-gradient-to-t from-pink-600/60 to-cyan-400/70 rounded-t-sm"
                      />
                    ))}
                </div>
              </div>
            )}

            {/* Interactive Beat-Synced Timeline Clips */}
            <div className="mt-4 space-y-2.5 max-h-[430px] overflow-y-auto pr-1">
              {timelineClips.map((clip, idx) => {
                const isPhoto = clip.media_type === 'photo';
                return (
                  <div
                    key={clip.clip_id}
                    className={`rounded-xl border p-3 transition ${
                      isPhoto
                        ? 'bg-purple-950/20 border-purple-500/30'
                        : 'bg-slate-950/80 border-slate-800 hover:border-pink-500/40'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <span className="w-6 h-6 rounded-lg bg-slate-800 text-xs font-bold flex items-center justify-center text-slate-200">
                          {idx + 1}
                        </span>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-white">
                              {clip.filename}
                            </span>
                            <span
                              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                                isPhoto
                                  ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                                  : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                              }`}
                            >
                              {isPhoto
                                ? clip.synced_cue_type === 'musical_pause_photo'
                                  ? 'Musical Pause • Photo'
                                  : 'Sustained Note • Photo'
                                : clip.matched_dance_move === 'turn_spin'
                                ? 'Downbeat • Turn Peak'
                                : 'Downbeat • Jump Apex'}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400 mt-0.5">
                            {clip.sync_explanation}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-1 shrink-0">
                        <span className="text-[11px] font-mono text-slate-400 mr-1">
                          {clip.timeline_start_sec.toFixed(1)}s–{clip.timeline_end_sec.toFixed(1)}s
                        </span>
                        <button
                          onClick={() => handleSwapClipOrder(idx, -1)}
                          disabled={idx === 0}
                          title="Move clip earlier"
                          className="p-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-30 text-xs"
                        >
                          ↑
                        </button>
                        <button
                          onClick={() => handleSwapClipOrder(idx, 1)}
                          disabled={idx === timelineClips.length - 1}
                          title="Move clip later"
                          className="p-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-30 text-xs"
                        >
                          ↓
                        </button>
                      </div>
                    </div>

                    {/* Interactive Per-Clip Controls (Ken Burns effect for Photos / Speed Ramp & Transition for Videos) */}
                    <div className="mt-2.5 pt-2.5 border-t border-slate-800/70 grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px]">
                      {isPhoto ? (
                        <div className="col-span-2">
                          <label className="block text-[10px] text-purple-300 mb-0.5">
                            Photo Visual Effect (Ken Burns / Pulse)
                          </label>
                          <select
                            value={clip.photo_effect || 'ken_burns_zoom_in'}
                            onChange={(e) =>
                              handleClipFieldChange(idx, 'photo_effect', e.target.value)
                            }
                            className="w-full rounded-lg bg-slate-900 border border-slate-700 px-2 py-1 text-[11px] text-white"
                          >
                            {PHOTO_EFFECT_OPTIONS.map((opt) => (
                              <option key={opt.value} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                          </select>
                        </div>
                      ) : (
                        <div className="col-span-2">
                          <label className="block text-[10px] text-amber-300 mb-0.5">
                            Apex Downbeat Sync & Speed Ramp
                          </label>
                          <div className="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 truncate">
                            {clip.speed_ramp_curve || '1.0x Direct Slip-Sync to Downbeat'}
                          </div>
                        </div>
                      )}

                      <div>
                        <label className="block text-[10px] text-slate-400 mb-0.5">
                          Entry Transition
                        </label>
                        <select
                          value={clip.transition_in}
                          onChange={(e) =>
                            handleClipFieldChange(idx, 'transition_in', e.target.value)
                          }
                          className="w-full rounded-lg bg-slate-900 border border-slate-700 px-2 py-1 text-[11px] text-white"
                        >
                          {TRANSITION_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Save / Re-render Interactive Timeline Bar */}
            {session && (
              <div className="mt-4 pt-3 border-t border-slate-800 flex items-center justify-between gap-2">
                <button
                  onClick={() => handleApplyTimelineAdjustments(false)}
                  disabled={isUpdatingTimeline}
                  className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 flex items-center gap-1.5 transition"
                >
                  <Scissors className="w-3.5 h-3.5 text-cyan-400" />
                  Sync Edits to CapCut Draft & XML
                </button>

                <button
                  onClick={() => handleApplyTimelineAdjustments(true)}
                  disabled={isUpdatingTimeline}
                  className="px-4 py-2 rounded-xl bg-pink-600/25 hover:bg-pink-600/35 border border-pink-500/40 text-xs font-semibold text-pink-200 flex items-center gap-1.5 transition"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isUpdatingTimeline ? 'animate-spin' : ''}`} />
                  Re-Render 9:16 Video with Edits
                </button>
              </div>
            )}
          </section>

          {/* Analyzed Dance Media Pool (Showing Detected Jump Peaks, Turns & Photo Scores) */}
          <section className="rounded-2xl bg-slate-900/90 border border-slate-800 p-5 shadow-xl">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
              <Film className="w-4 h-4 text-pink-400" />
              Analyzed Event Media Pool (Jump Peaks, Turns & Photo Aesthetics)
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-64 overflow-y-auto pr-1">
              {matchedMedia.map((item) => (
                <div
                  key={item.id}
                  className="p-2.5 rounded-xl bg-slate-950/80 border border-slate-800/90 flex flex-col justify-between gap-1.5"
                >
                  <div>
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-xs font-semibold text-white truncate">
                        {item.filename}
                      </span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-pink-300 font-mono shrink-0">
                        {Math.round(item.query_match_score * 100)}% match
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 line-clamp-2 mt-0.5">
                      {item.semantic_caption}
                    </p>
                  </div>

                  <div className="flex flex-wrap gap-1 pt-1">
                    {item.media_type === 'video' ? (
                      item.dance_events.map((ev, i) => (
                        <span
                          key={i}
                          className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30"
                        >
                          {ev.move_type === 'jump_peak' ? '⚡ Jump Apex' : '🌀 Turn Peak'} @{' '}
                          {ev.timestamp_sec.toFixed(2)}s
                        </span>
                      ))
                    ) : (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-300 border border-purple-500/30">
                        📸 Photo • Aesthetic {Math.round(item.aesthetic_score * 100)}%
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* RIGHT COLUMN (3 cols): 9:16 Video Preview, CapCut Interactive Export, Attractive Titles & Captions */}
        <div className="lg:col-span-3 space-y-5">
          {/* 9:16 Vertical Reel Player & CapCut / FCPXML Export Actions */}
          <section className="rounded-2xl bg-slate-900/90 border border-slate-800 p-5 shadow-xl">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <Play className="w-4 h-4 text-pink-400" />
                9:16 Instagram Reel Output
              </h2>
              {session?.exports.mp4_url && (
                <a
                  href={session.exports.mp4_url}
                  download={`InsCreator_${session.session_id}.mp4`}
                  className="text-[11px] px-2.5 py-1 rounded-lg bg-pink-600/20 hover:bg-pink-600/30 text-pink-200 border border-pink-500/40 flex items-center gap-1"
                >
                  <Download className="w-3 h-3" />
                  MP4
                </a>
              )}
            </div>

            <div className="aspect-[9/16] max-h-[420px] mx-auto rounded-2xl overflow-hidden bg-slate-950 border border-slate-800 flex items-center justify-center relative shadow-inner">
              {session?.exports.mp4_url ? (
                <video
                  key={session.exports.mp4_url}
                  src={session.exports.mp4_url}
                  controls
                  playsInline
                  loop
                  className="w-full h-full object-contain"
                />
              ) : (
                <div className="text-center p-6 text-xs text-slate-500">
                  Generating 9:16 vertical beat-synced video...
                </div>
              )}
            </div>

            {/* CapCut Desktop & NLE Interactive Editing Export Box */}
            {session && (
              <div className="mt-4 pt-3 border-t border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-white flex items-center gap-1.5">
                    <Scissors className="w-3.5 h-3.5 text-cyan-400" />
                    Interactive Video Editor Hand-off
                  </span>
                  {session.exports.capcut_installed_to_app && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                      Installed to CapCut.app
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Includes full multi-track timeline, beat & downbeat markers, Ken Burns keyframes, and text overlays for interactive fine-tuning in CapCut or Final Cut / DaVinci.
                </p>

                <div className="grid grid-cols-2 gap-2 pt-1">
                  {session.exports.capcut_zip_url && (
                    <a
                      href={session.exports.capcut_zip_url}
                      download
                      className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-200 text-xs font-semibold transition"
                    >
                      <Download className="w-3.5 h-3.5" />
                      CapCut Draft (.zip)
                    </a>
                  )}
                  {session.exports.fcpxml_url && (
                    <a
                      href={session.exports.fcpxml_url}
                      download
                      className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-medium transition"
                    >
                      <Download className="w-3.5 h-3.5" />
                      FCPXML Timeline
                    </a>
                  )}
                </div>
              </div>
            )}
          </section>

          {/* Attractive Titles, Captions & Hashtags Studio */}
          {postCopy && (
            <section className="rounded-2xl bg-slate-900/90 border border-slate-800 p-5 shadow-xl space-y-3.5">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Share2 className="w-4 h-4 text-amber-400" />
                  Attractive Post Titles & Content
                </h2>
                <button
                  onClick={() =>
                    copyToClipboard(
                      'all_post',
                      `${postCopy.post_headline}\n\n${displayedCaption}\n\n${postCopy.hashtags.join(' ')}`
                    )
                  }
                  className="text-[11px] px-2.5 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 flex items-center gap-1"
                >
                  {copiedField === 'all_post' ? (
                    <>
                      <Check className="w-3 h-3" /> Copied!
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" /> Copy Full Post
                    </>
                  )}
                </button>
              </div>

              {/* Video On-Screen Hook Title */}
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">
                  On-Screen Reel Title Hook (0.0s–2.6s)
                </label>
                <input
                  type="text"
                  value={postCopy.hook_title_overlay}
                  onChange={(e) =>
                    setPostCopy({ ...postCopy, hook_title_overlay: e.target.value })
                  }
                  className="w-full rounded-xl bg-slate-950 border border-slate-700/80 px-3 py-1.5 text-xs font-semibold text-pink-200"
                />
              </div>

              {/* Post Headline */}
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">
                  Instagram Post Title / Headline
                </label>
                <input
                  type="text"
                  value={postCopy.post_headline}
                  onChange={(e) =>
                    setPostCopy({ ...postCopy, post_headline: e.target.value })
                  }
                  className="w-full rounded-xl bg-slate-950 border border-slate-700/80 px-3 py-1.5 text-xs font-bold text-white"
                />
              </div>

              {/* Caption Tone Selector Pills */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-[11px] text-slate-400">Caption Style</label>
                  <div className="flex gap-1">
                    <button
                      onClick={() => setSelectedCaptionVariantIdx(-1)}
                      className={`text-[10px] px-2 py-0.5 rounded-md ${
                        selectedCaptionVariantIdx === -1
                          ? 'bg-pink-600 text-white'
                          : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      Storytelling
                    </button>
                    {postCopy.caption_alternatives.map((alt, i) => (
                      <button
                        key={i}
                        onClick={() => setSelectedCaptionVariantIdx(i)}
                        className={`text-[10px] px-2 py-0.5 rounded-md ${
                          selectedCaptionVariantIdx === i
                            ? 'bg-pink-600 text-white'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {alt.label.split(' ')[0]}
                      </button>
                    ))}
                  </div>
                </div>

                <textarea
                  rows={6}
                  value={displayedCaption}
                  onChange={(e) => {
                    if (selectedCaptionVariantIdx === -1) {
                      setPostCopy({ ...postCopy, caption_primary: e.target.value });
                    } else {
                      const nextAlts = [...postCopy.caption_alternatives];
                      nextAlts[selectedCaptionVariantIdx] = {
                        ...nextAlts[selectedCaptionVariantIdx],
                        text: e.target.value,
                      };
                      setPostCopy({ ...postCopy, caption_alternatives: nextAlts });
                    }
                  }}
                  className="w-full rounded-xl bg-slate-950 border border-slate-700/80 p-3 text-xs text-slate-200 leading-relaxed"
                />
              </div>

              {/* Hashtags */}
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">
                  Curated Dance Hashtags
                </label>
                <div className="flex flex-wrap gap-1">
                  {postCopy.hashtags.map((tag) => (
                    <span
                      key={tag}
                      className="text-[10px] px-2 py-0.5 rounded-md bg-slate-950 border border-slate-800 text-pink-300"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </section>
          )}
        </div>
      </main>

      {/* Google Photos OAuth & Gemini API Key Modal */}
      {showSettingsModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-md rounded-2xl bg-slate-900 border border-slate-700 p-6 space-y-4 shadow-2xl">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Settings className="w-4 h-4 text-pink-400" />
              Google Photos & AI API Configuration
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Ins-Creator works out-of-the-box with local folders, uploads, and the built-in dance dataset. To fetch directly from your personal Google Photos account or use live Gemini 2.5 API copywriting, paste your tokens below:
            </p>

            <div className="space-y-3">
              <div>
                <label className="block text-xs text-slate-300 mb-1">
                  Google Photos OAuth Bearer Access Token (`photospicker.mediaitems.readonly`)
                </label>
                <input
                  type="password"
                  value={googleTokenInput}
                  onChange={(e) => setGoogleTokenInput(e.target.value)}
                  placeholder="ya29.a0..."
                  className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs text-white"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">
                  Google Gemini API Key (`GEMINI_API_KEY`)
                </label>
                <input
                  type="password"
                  value={geminiKeyInput}
                  onChange={(e) => setGeminiKeyInput(e.target.value)}
                  placeholder="AIzaSy..."
                  className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs text-white"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowSettingsModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-800 text-xs text-slate-300"
              >
                Close
              </button>
              <button
                onClick={handleSaveSettings}
                className="px-4 py-2 rounded-xl bg-pink-600 hover:bg-pink-500 text-xs font-semibold text-white"
              >
                Save Credentials
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
export default App;
