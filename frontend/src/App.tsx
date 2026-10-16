import React, { useEffect, useRef, useState } from 'react';
import {
  Image as ImageIcon,
  Play,
  Download,
  Scissors,
  Copy,
  Check,
  Upload,
  RefreshCw,
  Settings,
  ChevronRight,
  ChevronLeft,
  CheckCircle2,
  FolderOpen,
  FileText,
  Sliders,
  Trash2,
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
  { value: 'ken_burns_zoom_in', label: 'Ken Burns Slow Zoom In (Focus Subject)' },
  { value: 'ken_burns_zoom_out', label: 'Ken Burns Pull Out' },
  { value: 'ken_burns_pan_diag', label: 'Ken Burns Diagonal Pan' },
  { value: 'ken_burns_pan_lr', label: 'Ken Burns Horizontal Pan' },
  { value: 'beat_pulse_zoom', label: 'Beat-Pulse Subtle Zoom' },
  { value: 'soft_glow_dissolve', label: 'Soft Dissolve' },
];

const TRANSITION_OPTIONS = [
  { value: 'cut_on_beat', label: 'Cut on Beat' },
  { value: 'flash_white', label: 'White Flash' },
  { value: 'cross_dissolve', label: 'Cross Dissolve' },
  { value: 'zoom_whip', label: 'Zoom Transition' },
];

const WORKFLOW_STEPS = [
  {
    number: 1,
    title: 'Import Media',
    subtitle: 'Google Photos or local folder upload',
  },
  {
    number: 2,
    title: 'Style & Directions',
    subtitle: 'Pick a preset & add custom notes',
  },
  {
    number: 3,
    title: 'Music & Beat Sync',
    subtitle: 'Select or generate beat-mapped audio',
  },
  {
    number: 4,
    title: 'Review & Export',
    subtitle: 'Adjust timeline, copy & CapCut draft',
  },
];

export function App() {
  // Active wizard step (1..4)
  const [currentStep, setCurrentStep] = useState<number>(1);

  // Catalog state
  const [presets, setPresets] = useState<StylePreset[]>([]);
  const [musicTracks, setMusicTracks] = useState<AudioCueMap[]>([]);
  const [matchedMedia, setMatchedMedia] = useState<MediaItem[]>([]);
  const [selectedMediaIds, setSelectedMediaIds] = useState<Set<string>>(new Set());

  // User workflow inputs
  const [selectedPresetId, setSelectedPresetId] = useState('competition_stage_glory');
  const [supplementalDirections, setSupplementalDirections] = useState(
    'Sync her highest jump peak to the main measure downbeat with slow-motion at the apex, insert a poised photo during the sustained note with Ken Burns zoom, and write an inspiring proud-parent caption.'
  );
  const [selectedMusicId, setSelectedMusicId] = useState('competition_edm_pop');
  const [customMusicPrompt, setCustomMusicPrompt] = useState('');
  const [targetDurationSec, setTargetDurationSec] = useState(16);

  // Active Google Photos Picker polling state
  const [activePickerSessionId, setActivePickerSessionId] = useState<string | null>(null);
  const [isWaitingForGooglePicker, setIsWaitingForGooglePicker] = useState(false);
  const [isImportingMedia, setIsImportingMedia] = useState(false);
  const pickerPollTimerRef = useRef<number | null>(null);

  // Active generated session state
  const [session, setSession] = useState<WorkflowSession | null>(null);
  const [timelineClips, setTimelineClips] = useState<TimelineClip[]>([]);
  const [postCopy, setPostCopy] = useState<InstagramPostCopy | null>(null);
  const [selectedCaptionVariantIdx, setSelectedCaptionVariantIdx] = useState<number>(-1);

  // UI status state
  const [isGeneratingSession, setIsGeneratingSession] = useState(false);
  const [isUpdatingTimeline, setIsUpdatingTimeline] = useState(false);
  const [isGeneratingMusic, setIsGeneratingMusic] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [geminiKeyInput, setGeminiKeyInput] = useState('');
  const [googleClientIdInput, setGoogleClientIdInput] = useState('');
  const [googleClientSecretInput, setGoogleClientSecretInput] = useState('');
  const [googleTokenInput, setGoogleTokenInput] = useState('');
  const [googlePhotosConnected, setGooglePhotosConnected] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    void loadInitialCatalog();
    const onMessage = (event: MessageEvent) => {
      if (event.data && event.data.type === 'GOOGLE_PHOTOS_CONNECTED') {
        setGooglePhotosConnected(true);
        setShowSettingsModal(false);
        setStatusMessage(
          'Google Photos account connected! Click "Import from Google Photos" to select your photos and videos.'
        );
      }
    };
    window.addEventListener('message', onMessage);
    return () => {
      window.removeEventListener('message', onMessage);
      if (pickerPollTimerRef.current) {
        window.clearInterval(pickerPollTimerRef.current);
      }
    };
  }, []);

  async function loadInitialCatalog() {
    try {
      const [hRes, pRes, mRes] = await Promise.all([
        fetch('/api/health'),
        fetch('/api/presets'),
        fetch('/api/music/tracks'),
      ]);
      const hData = await hRes.json();
      const pData: StylePreset[] = await pRes.json();
      const mData: AudioCueMap[] = await mRes.json();

      if (hData.google_client_id) {
        setGoogleClientIdInput(hData.google_client_id);
      }
      setGooglePhotosConnected(Boolean(hData.google_photos_configured));
      setPresets(pData);
      setMusicTracks(mData);

      // Check if user already has imported Google Photos or uploaded local files from a recent session
      const mediaRes = await fetch('/api/media/search?source=google_photos');
      if (mediaRes.ok) {
        const mediaData: MediaItem[] = await mediaRes.json();
        const userOnly = mediaData.filter((m) => m.source !== 'sample');
        if (userOnly.length > 0) {
          setMatchedMedia(userOnly);
          setSelectedMediaIds(new Set(userOnly.map((m) => m.id)));
        }
      }
    } catch (err) {
      console.error('Failed loading initial catalog:', err);
    }
  }

  function stopPickerPolling() {
    if (pickerPollTimerRef.current) {
      window.clearInterval(pickerPollTimerRef.current);
      pickerPollTimerRef.current = null;
    }
    setIsWaitingForGooglePicker(false);
  }

  function startPickerPolling(sessionId: string) {
    stopPickerPolling();
    setActivePickerSessionId(sessionId);
    setIsWaitingForGooglePicker(true);

    pickerPollTimerRef.current = window.setInterval(async () => {
      try {
        const res = await fetch(`/api/media/google-photos/picker-session/${sessionId}`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.mediaItemsSet && Array.isArray(data.importedItems)) {
          stopPickerPolling();
          const imported: MediaItem[] = data.importedItems;
          if (imported.length > 0) {
            setMatchedMedia((prev) => {
              const nonSample = prev.filter((p) => p.source !== 'sample');
              const existingIds = new Set(imported.map((i) => i.id));
              return [...imported, ...nonSample.filter((p) => !existingIds.has(p.id))];
            });
            setSelectedMediaIds((prev) => {
              const next = new Set(prev);
              imported.forEach((i) => next.add(i.id));
              return next;
            });
            setStatusMessage(
              `Imported and analyzed ${imported.length} photo(s)/video(s) from Google Photos.`
            );
          } else {
            setStatusMessage('Selection completed in Google Photos.');
          }
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 3000);
  }

  async function handleGooglePhotosPicker() {
    setStatusMessage('Opening Google Photos Picker...');
    try {
      const res = await fetch('/api/media/google-photos/picker-session', { method: 'POST' });
      const data = await res.json();
      if (data.configured && data.pickerUri && data.sessionId) {
        window.open(data.pickerUri, '_blank');
        startPickerPolling(data.sessionId);
        setStatusMessage(
          'Select your photos and videos in the Google Photos tab and click "Done" in the top-right corner. They will import here automatically.'
        );
      } else {
        setShowSettingsModal(true);
        setStatusMessage(
          data.error ||
            data.message ||
            'Please click "Sign in with Google" to authorize Google Photos first.'
        );
      }
    } catch (err) {
      console.error(err);
    }
  }

  async function handleManualFetchFromGooglePicker() {
    setIsImportingMedia(true);
    setStatusMessage('Downloading and analyzing your selected items from Google Photos...');
    try {
      const url = activePickerSessionId
        ? `/api/media/google-photos/import?session_id=${encodeURIComponent(activePickerSessionId)}`
        : '/api/media/google-photos/import';
      const res = await fetch(url, { method: 'POST' });
      const imported: MediaItem[] = await res.json();
      stopPickerPolling();
      if (imported.length > 0) {
        setMatchedMedia((prev) => {
          const nonSample = prev.filter((p) => p.source !== 'sample');
          const existingIds = new Set(imported.map((i) => i.id));
          return [...imported, ...nonSample.filter((p) => !existingIds.has(p.id))];
        });
        setSelectedMediaIds((prev) => {
          const next = new Set(prev);
          imported.forEach((i) => next.add(i.id));
          return next;
        });
        setStatusMessage(`Imported ${imported.length} item(s) from Google Photos!`);
      } else {
        setStatusMessage(
          'No items returned yet. Make sure you clicked "Done" in the top-right corner of the Google Photos selection tab.'
        );
      }
    } catch (err) {
      console.error(err);
      setStatusMessage('Failed importing from Google Photos.');
    } finally {
      setIsImportingMedia(false);
    }
  }

  async function handleMediaUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    // Filter only supported image & video files when uploading a folder
    const validFiles = Array.from(files).filter((f) => {
      const ext = f.name.toLowerCase();
      return (
        f.type.startsWith('video/') ||
        f.type.startsWith('image/') ||
        ext.endsWith('.mp4') ||
        ext.endsWith('.mov') ||
        ext.endsWith('.jpg') ||
        ext.endsWith('.jpeg') ||
        ext.endsWith('.png') ||
        ext.endsWith('.webp')
      );
    });

    if (validFiles.length === 0) {
      setStatusMessage('No supported photo or video files found in selection.');
      return;
    }

    const formData = new FormData();
    validFiles.forEach((f) => formData.append('files', f));
    formData.append('query', 'dance event');

    setIsImportingMedia(true);
    setStatusMessage(
      `Importing and analyzing dance movements on ${validFiles.length} file(s)...`
    );
    try {
      const res = await fetch('/api/media/upload', {
        method: 'POST',
        body: formData,
      });
      const uploaded: MediaItem[] = await res.json();
      setMatchedMedia((prev) => {
        const nonSample = prev.filter((p) => p.source !== 'sample');
        const existingIds = new Set(uploaded.map((u) => u.id));
        return [...uploaded, ...nonSample.filter((p) => !existingIds.has(p.id))];
      });
      setSelectedMediaIds((prev) => {
        const next = new Set(prev);
        uploaded.forEach((u) => next.add(u.id));
        return next;
      });
      setStatusMessage(`Imported and analyzed ${uploaded.length} item(s).`);
    } catch (err) {
      console.error(err);
      setStatusMessage('Error uploading files.');
    } finally {
      setIsImportingMedia(false);
      e.target.value = '';
    }
  }

  async function handleLoadSampleMedia() {
    setIsImportingMedia(true);
    setStatusMessage('Loading demo dance event videos & photos...');
    try {
      const res = await fetch('/api/media/search?source=sample');
      const data: MediaItem[] = await res.json();
      setMatchedMedia(data);
      setSelectedMediaIds(new Set(data.map((m) => m.id)));
      setStatusMessage(`Loaded ${data.length} demo dance items.`);
    } catch (err) {
      console.error(err);
    } finally {
      setIsImportingMedia(false);
    }
  }

  async function handleClearAllMedia() {
    stopPickerPolling();
    await fetch('/api/media/clear', { method: 'POST' });
    setMatchedMedia([]);
    setSelectedMediaIds(new Set());
    setStatusMessage('Cleared imported media list.');
  }

  async function handleStartGoogleOAuthSignIn() {
    try {
      await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          google_client_id: googleClientIdInput,
          google_client_secret: googleClientSecretInput,
        }),
      });
      const res = await fetch('/api/auth/google/start');
      const data = await res.json();
      if (data.auth_url) {
        window.open(data.auth_url, 'google_oauth_popup', 'width=540,height=680');
        setStatusMessage('Opened Google Sign-In window. Authorize access to connect your Google Photos.');
      }
    } catch (err) {
      console.error(err);
      setStatusMessage('Could not start Google OAuth flow.');
    }
  }

  function toggleMediaSelection(id: string) {
    setSelectedMediaIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        if (next.size > 1) next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  async function handleMusicUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);

    setIsGeneratingMusic(true);
    setStatusMessage(`Analyzing "${file.name}" for downbeats, sustained notes, and pauses...`);
    try {
      const res = await fetch('/api/music/upload', {
        method: 'POST',
        body: formData,
      });
      const cueMap: AudioCueMap = await res.json();
      setMusicTracks((prev) => [cueMap, ...prev]);
      setSelectedMusicId(cueMap.track_id);
      setStatusMessage(`Uploaded "${cueMap.title}" (${cueMap.bpm} BPM).`);
    } catch (err) {
      console.error(err);
    } finally {
      setIsGeneratingMusic(false);
    }
  }

  async function handleGenerateCustomMusic() {
    if (!customMusicPrompt.trim()) return;
    setIsGeneratingMusic(true);
    setStatusMessage(`Generating custom soundtrack for "${customMusicPrompt}"...`);
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
      setStatusMessage(`Generated and analyzed "${cueMap.title}" (${cueMap.bpm} BPM).`);
    } catch (err) {
      console.error(err);
    } finally {
      setIsGeneratingMusic(false);
    }
  }

  async function handleGenerateSessionAndAdvance() {
    setIsGeneratingSession(true);
    setStatusMessage(
      'Aligning jump peaks & turns to measure downbeats, placing photos on sustained notes/pauses, rendering 9:16 MP4, and generating CapCut draft...'
    );
    try {
      const res = await fetch('/api/sessions/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          search_query: supplementalDirections || 'dance event',
          media_source: 'auto',
          style_preset_id: selectedPresetId,
          supplemental_directions: supplementalDirections,
          music_track_id: selectedMusicId,
          music_generation_prompt: null,
          target_duration_sec: targetDurationSec,
          selected_media_ids: selectedMediaIds.size > 0 ? Array.from(selectedMediaIds) : null,
          auto_render_mp4: true,
          auto_export_capcut: true,
        }),
      });
      const sess: WorkflowSession = await res.json();
      setSession(sess);
      setTimelineClips(sess.timeline_clips);
      setPostCopy(sess.post_copy || null);
      setSelectedCaptionVariantIdx(-1);
      setCurrentStep(4);
      setStatusMessage('Session generated. Review your video, post copy, and CapCut export below.');
    } catch (err) {
      console.error(err);
      setStatusMessage('Failed to generate session.');
    } finally {
      setIsGeneratingSession(false);
    }
  }

  async function handleApplyTimelineAdjustments(reRenderMp4: boolean) {
    if (!session) return;
    setIsUpdatingTimeline(true);
    setStatusMessage(
      reRenderMp4
        ? 'Re-rendering 9:16 MP4 video and updating CapCut draft...'
        : 'Saving timeline changes to CapCut draft and FCPXML...'
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
      setStatusMessage(
        reRenderMp4
          ? 'Video re-rendered and CapCut draft updated.'
          : 'Timeline saved to CapCut draft and FCPXML.'
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
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        gemini_api_key: geminiKeyInput,
        google_client_id: googleClientIdInput,
        google_client_secret: googleClientSecretInput,
        google_photos_access_token: googleTokenInput,
      }),
    });
    const data = await res.json();
    setGooglePhotosConnected(Boolean(data.google_photos_configured));
    setShowSettingsModal(false);
    setStatusMessage('Credentials saved.');
  }

  const activeCueMap =
    session?.audio_cue_map ||
    musicTracks.find((t) => t.track_id === selectedMusicId) ||
    musicTracks[0];

  const activePreset = presets.find((p) => p.id === selectedPresetId) || presets[0];

  const displayedCaption =
    selectedCaptionVariantIdx === -1
      ? postCopy?.caption_primary || ''
      : postCopy?.caption_alternatives?.[selectedCaptionVariantIdx]?.text || '';

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
      {/* Clean Professional Top Navigation Bar */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-slate-900 text-white flex items-center justify-center font-semibold text-sm">
              IC
            </div>
            <div>
              <h1 className="text-base font-semibold text-slate-900 leading-tight">
                Ins-Creator
              </h1>
              <p className="text-xs text-slate-500">
                Automated Dance Reel & Instagram Post Workflow
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {googlePhotosConnected && (
              <span className="hidden sm:inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                Google Photos Connected
              </span>
            )}
            <button
              onClick={() => setShowSettingsModal(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-medium text-slate-700 transition"
            >
              <Settings className="w-3.5 h-3.5 text-slate-500" />
              API & Google Photos Settings
            </button>
          </div>
        </div>

        {/* Horizontal Step-by-Step Progress Bar */}
        <div className="border-t border-slate-100 bg-slate-50/70">
          <div className="max-w-6xl mx-auto px-6 py-3">
            <nav aria-label="Progress" className="grid grid-cols-1 sm:grid-cols-4 gap-2">
              {WORKFLOW_STEPS.map((step) => {
                const isActive = currentStep === step.number;
                const isCompleted = currentStep > step.number || (step.number === 4 && session !== null);
                return (
                  <button
                    key={step.number}
                    onClick={() => setCurrentStep(step.number)}
                    className={`flex items-center gap-3 p-2.5 rounded-lg border text-left transition ${
                      isActive
                        ? 'bg-white border-slate-900 shadow-sm'
                        : isCompleted
                        ? 'bg-white/70 border-slate-200 hover:border-slate-300'
                        : 'bg-transparent border-transparent hover:bg-white/50'
                    }`}
                  >
                    <div
                      className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 ${
                        isActive
                          ? 'bg-slate-900 text-white'
                          : isCompleted
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-200 text-slate-600'
                      }`}
                    >
                      {isCompleted && !isActive ? <Check className="w-3.5 h-3.5" /> : step.number}
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-slate-900 truncate">
                        Step {step.number}: {step.title}
                      </div>
                      <div className="text-[11px] text-slate-500 truncate">
                        {step.subtitle}
                      </div>
                    </div>
                  </button>
                );
              })}
            </nav>
          </div>
        </div>

        {statusMessage && (
          <div className="bg-slate-900 text-white px-6 py-2 text-xs">
            <div className="max-w-6xl mx-auto flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span>{statusMessage}</span>
              </div>
              <button
                onClick={() => setStatusMessage(null)}
                className="text-slate-400 hover:text-white text-[11px] shrink-0"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}
      </header>

      {/* Main Guided Workspace Container */}
      <main className="max-w-6xl w-full mx-auto px-6 py-8 flex-1">
        {/* ===================================================================
            STEP 1: IMPORT MEDIA (GOOGLE PHOTOS OR LOCAL FOLDER / FILES)
           =================================================================== */}
        {currentStep === 1 && (
          <div className="space-y-6">
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-slate-100">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Step 1 of 4
                  </span>
                  <h2 className="text-lg font-semibold text-slate-900 mt-0.5">
                    Import Event Photos & Videos
                  </h2>
                  <p className="text-sm text-slate-600 mt-0.5">
                    Choose how you want to bring in your daughter&apos;s dance event photos and videos. Imported clips are automatically analyzed for jump peaks and turns.
                  </p>
                </div>
                <button
                  onClick={() => setCurrentStep(2)}
                  disabled={matchedMedia.length === 0}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-40 text-white text-xs font-semibold shrink-0 transition"
                >
                  Continue to Step 2: Style
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>

              {/* Two Clean Primary Import Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-6">
                {/* Option 1: Google Photos */}
                <div className="rounded-xl border border-slate-200 p-5 bg-slate-50/50 flex flex-col justify-between space-y-4">
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                        <ImageIcon className="w-4 h-4 text-slate-700" />
                        Option A: Import from Google Photos
                      </div>
                      {googlePhotosConnected && (
                        <span className="text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded font-medium">
                          Account Linked
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed">
                      Opens your Google Photos library where you can search or pick photos and videos from the dance event. When you click <b>Done</b> in Google Photos, your selection is automatically imported here.
                    </p>
                  </div>

                  <div className="space-y-2 pt-2">
                    <button
                      onClick={handleGooglePhotosPicker}
                      disabled={isImportingMedia}
                      className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition cursor-pointer"
                    >
                      <ImageIcon className="w-4 h-4" />
                      {isWaitingForGooglePicker
                        ? 'Re-open Google Photos Picker'
                        : 'Select from Google Photos'}
                    </button>

                    {(isWaitingForGooglePicker || activePickerSessionId) && (
                      <div className="p-3 rounded-lg bg-white border border-slate-200 flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 text-xs text-slate-700">
                          <RefreshCw
                            className={`w-3.5 h-3.5 text-slate-600 shrink-0 ${
                              isWaitingForGooglePicker || isImportingMedia ? 'animate-spin' : ''
                            }`}
                          />
                          <span>
                            {isWaitingForGooglePicker
                              ? 'Waiting for you to click "Done" in Google Photos...'
                              : 'Finished selecting in Google Photos?'}
                          </span>
                        </div>
                        <button
                          onClick={handleManualFetchFromGooglePicker}
                          disabled={isImportingMedia}
                          className="px-3 py-1.5 rounded-md bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shrink-0"
                        >
                          {isImportingMedia ? 'Importing...' : 'Import Selected Now'}
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {/* Option 2: Upload Folder or Files from Computer */}
                <div className="rounded-xl border border-slate-200 p-5 bg-slate-50/50 flex flex-col justify-between space-y-4">
                  <div className="space-y-1.5">
                    <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                      <FolderOpen className="w-4 h-4 text-slate-700" />
                      Option B: Upload from a Local Folder
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed">
                      Select an entire folder of event photos/videos from your Mac, or pick individual `.mp4`, `.mov`, and `.jpg`/`.png` files directly from Finder.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-2">
                    <label className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition cursor-pointer">
                      <FolderOpen className="w-4 h-4" />
                      Upload Entire Folder
                      <input
                        type="file"
                        multiple
                        // @ts-expect-error webkitdirectory is standard in modern browsers for folder selection
                        webkitdirectory=""
                        directory=""
                        onChange={handleMediaUpload}
                        className="hidden"
                      />
                    </label>

                    <label className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-800 text-xs font-semibold transition cursor-pointer">
                      <Upload className="w-4 h-4" />
                      Select Individual Files
                      <input
                        type="file"
                        multiple
                        accept="video/*,image/*"
                        onChange={handleMediaUpload}
                        className="hidden"
                      />
                    </label>
                  </div>
                </div>
              </div>
            </div>

            {/* Imported Media List */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">
                    Imported Session Media ({selectedMediaIds.size} selected)
                  </h3>
                  <p className="text-xs text-slate-500">
                    Videos show detected Jump Peaks and Turn timestamps used for beat-syncing in Step 3.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  {matchedMedia.length === 0 ? (
                    <button
                      onClick={handleLoadSampleMedia}
                      className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600 font-medium"
                    >
                      Load Demo Dance Media (For Testing)
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={() => setSelectedMediaIds(new Set(matchedMedia.map((m) => m.id)))}
                        className="text-xs px-2.5 py-1 rounded border border-slate-200 hover:bg-slate-50 text-slate-600"
                      >
                        Select All
                      </button>
                      <button
                        onClick={handleClearAllMedia}
                        className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded border border-slate-200 hover:bg-red-50 hover:text-red-700 hover:border-red-200 text-slate-600 transition"
                      >
                        <Trash2 className="w-3 h-3" />
                        Clear List
                      </button>
                    </>
                  )}
                </div>
              </div>

              {matchedMedia.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 p-10 text-center space-y-2">
                  <p className="text-sm font-medium text-slate-700">
                    No photos or videos imported yet
                  </p>
                  <p className="text-xs text-slate-500 max-w-md mx-auto">
                    Use <b>Option A (Import from Google Photos)</b> or <b>Option B (Upload from a Local Folder)</b> above to import media for this session.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
                  {matchedMedia.map((item) => {
                    const isChecked = selectedMediaIds.has(item.id);
                    return (
                      <div
                        key={item.id}
                        onClick={() => toggleMediaSelection(item.id)}
                        className={`rounded-lg border overflow-hidden text-left cursor-pointer transition flex flex-col justify-between ${
                          isChecked
                            ? 'border-slate-900 bg-slate-50/60'
                            : 'border-slate-200 bg-white opacity-60 hover:opacity-100'
                        }`}
                      >
                        {/* Thumbnail / Video Preview */}
                        <div className="h-36 bg-slate-900 flex items-center justify-center overflow-hidden relative">
                          {item.media_type === 'photo' ? (
                            <img
                              src={item.url}
                              alt={item.filename}
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <video
                              src={item.url}
                              muted
                              playsInline
                              preload="metadata"
                              className="w-full h-full object-cover"
                            />
                          )}
                          <span className="absolute top-2 right-2 text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-900/80 text-white uppercase">
                            {item.media_type}
                          </span>
                        </div>

                        <div className="p-3 flex-1 flex flex-col justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => {}}
                              className="rounded border-slate-300 text-slate-900 focus:ring-slate-900"
                            />
                            <span className="text-xs font-semibold text-slate-900 truncate">
                              {item.filename}
                            </span>
                          </div>

                          <div className="pt-2 border-t border-slate-100 flex flex-wrap items-center justify-between gap-1 text-[11px]">
                            {item.media_type === 'video' ? (
                              <div className="flex flex-wrap gap-1">
                                {item.dance_events.map((ev, i) => (
                                  <span
                                    key={i}
                                    className="px-2 py-0.5 rounded bg-slate-200/80 text-slate-800 font-medium"
                                  >
                                    {ev.move_type === 'jump_peak' ? 'Jump Peak' : 'Turn Peak'} @{' '}
                                    {ev.timestamp_sec.toFixed(2)}s
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                                Still Photo • Quality {Math.round(item.aesthetic_score * 100)}%
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ===================================================================
            STEP 2: STYLE PRESET & SUPPLEMENTAL DIRECTIONS
           =================================================================== */}
        {currentStep === 2 && (
          <div className="space-y-6">
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-slate-100">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Step 2 of 4
                  </span>
                  <h2 className="text-lg font-semibold text-slate-900 mt-0.5">
                    Select a Style Preset & Add Supplemental Directions
                  </h2>
                  <p className="text-sm text-slate-600 mt-0.5">
                    Choose a baseline editing structure for the event, then type any specific requests for how clips, photos, and captions should be handled.
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => setCurrentStep(1)}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-xs font-medium text-slate-700 transition"
                  >
                    <ChevronLeft className="w-4 h-4" />
                    Back
                  </button>
                  <button
                    onClick={() => setCurrentStep(3)}
                    className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition"
                  >
                    Continue to Step 3: Music
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* 6 Preset Cards in Clean Professional Layout */}
              <div className="pt-5">
                <label className="block text-xs font-semibold text-slate-700 mb-3">
                  Default Dance Event Style Presets
                </label>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
                  {presets.map((preset) => {
                    const isSelected = preset.id === selectedPresetId;
                    return (
                      <button
                        key={preset.id}
                        onClick={() => {
                          setSelectedPresetId(preset.id);
                          setSelectedMusicId(preset.default_music_genre);
                        }}
                        className={`p-4 rounded-xl border text-left transition flex flex-col justify-between ${
                          isSelected
                            ? 'border-slate-900 bg-slate-900 text-white shadow-sm'
                            : 'border-slate-200 bg-white hover:border-slate-300 text-slate-900'
                        }`}
                      >
                        <div>
                          <div className="flex items-center justify-between gap-2 mb-1.5">
                            <span className="text-sm font-semibold">{preset.name}</span>
                            {isSelected && (
                              <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-white/20 text-white">
                                Active
                              </span>
                            )}
                          </div>
                          <p
                            className={`text-xs leading-relaxed ${
                              isSelected ? 'text-slate-300' : 'text-slate-600'
                            }`}
                          >
                            {preset.description}
                          </p>
                        </div>

                        <div
                          className={`mt-4 pt-2.5 border-t flex items-center justify-between text-[11px] font-medium ${
                            isSelected
                              ? 'border-slate-700 text-slate-300'
                              : 'border-slate-100 text-slate-500'
                          }`}
                        >
                          <span>
                            {Math.round(preset.video_to_photo_ratio * 100)}% Video /{' '}
                            {Math.round((1 - preset.video_to_photo_ratio) * 100)}% Photo
                          </span>
                          <span className="capitalize">{preset.cut_pacing.replace('_', ' ')}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Supplemental Requirements Input */}
              <div className="pt-6 mt-6 border-t border-slate-100 grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-8">
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Supplemental Directions (Optional Free-Text Instructions)
                  </label>
                  <p className="text-xs text-slate-500 mb-2">
                    Specify any custom pacing, which moves or photos to highlight, Ken Burns preferences, or the tone for the Instagram post.
                  </p>
                  <textarea
                    rows={4}
                    value={supplementalDirections}
                    onChange={(e) => setSupplementalDirections(e.target.value)}
                    placeholder="e.g., Highlight her highest split leap on the biggest downbeat, insert a smiling rehearsal photo during the piano pause with a slow zoom-in, and keep the caption heartfelt."
                    className="w-full rounded-lg border border-slate-300 bg-white p-3 text-sm text-slate-900 leading-relaxed focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                  />
                </div>

                <div className="lg:col-span-4 space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Target Reel Duration (Seconds)
                    </label>
                    <input
                      type="number"
                      min={10}
                      max={30}
                      value={targetDurationSec}
                      onChange={(e) => setTargetDurationSec(Number(e.target.value) || 16)}
                      className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                    />
                  </div>
                  <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-600 space-y-1">
                    <div className="font-semibold text-slate-800">Preset Summary</div>
                    <div>• Style: {activePreset?.name}</div>
                    <div>
                      • Speed Ramp on Jump/Turn Apex:{' '}
                      {activePreset?.speed_ramp_on_peaks ? 'Enabled' : 'Standard 1.0x'}
                    </div>
                    <div>• Color Grade: {activePreset?.color_grade_preset.replace('_', ' ')}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ===================================================================
            STEP 3: MUSIC & BEAT CUE SYNCHRONIZATION
           =================================================================== */}
        {currentStep === 3 && (
          <div className="space-y-6">
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-slate-100">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Step 3 of 4
                  </span>
                  <h2 className="text-lg font-semibold text-slate-900 mt-0.5">
                    Select, Upload, or Generate Music & Inspect Beat Cues
                  </h2>
                  <p className="text-sm text-slate-600 mt-0.5">
                    Librosa analyzes the audio track for measure downbeats (synced to jump peaks and turns) and sustained notes or pauses (where still photos are inserted with Ken Burns effects).
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => setCurrentStep(2)}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-xs font-medium text-slate-700 transition"
                  >
                    <ChevronLeft className="w-4 h-4" />
                    Back
                  </button>
                  <button
                    onClick={handleGenerateSessionAndAdvance}
                    disabled={isGeneratingSession}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold disabled:opacity-50 transition cursor-pointer"
                  >
                    {isGeneratingSession ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        Generating Reel & Post...
                      </>
                    ) : (
                      <>
                        Generate Reel & Post (Step 4)
                        <ChevronRight className="w-4 h-4" />
                      </>
                    )}
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 pt-5">
                {/* Left 7 cols: Track Selection & AI Generation */}
                <div className="lg:col-span-7 space-y-5">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-2">
                      Choose from Built-In or Uploaded Dance Tracks
                    </label>
                    <div className="space-y-2">
                      {musicTracks.map((track) => {
                        const isSelected = track.track_id === selectedMusicId;
                        return (
                          <div
                            key={track.track_id}
                            onClick={() => setSelectedMusicId(track.track_id)}
                            className={`p-3.5 rounded-lg border cursor-pointer transition flex items-center justify-between ${
                              isSelected
                                ? 'border-slate-900 bg-slate-50'
                                : 'border-slate-200 bg-white hover:border-slate-300'
                            }`}
                          >
                            <div className="flex items-center gap-3">
                              <input
                                type="radio"
                                checked={isSelected}
                                onChange={() => {}}
                                className="text-slate-900 focus:ring-slate-900"
                              />
                              <div>
                                <div className="text-xs font-semibold text-slate-900">
                                  {track.title}
                                </div>
                                <div className="text-[11px] text-slate-500 mt-0.5">
                                  Tempo: {track.bpm} BPM • {track.downbeat_times.length} Measure Downbeats •{' '}
                                  {track.sections.length} Sustained Note / Pause Windows
                                </div>
                              </div>
                            </div>
                            <span className="text-[11px] font-mono text-slate-500">
                              {track.duration_sec.toFixed(0)}s
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Upload or Generate Custom Audio */}
                  <div className="pt-4 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                        Upload Custom Audio File
                      </label>
                      <label className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-xs font-medium text-slate-700 cursor-pointer transition">
                        <Upload className="w-3.5 h-3.5 text-slate-600" />
                        Upload MP3 / WAV / M4A
                        <input
                          type="file"
                          accept="audio/*"
                          onChange={handleMusicUpload}
                          className="hidden"
                        />
                      </label>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                        Generate Custom AI Music Track
                      </label>
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={customMusicPrompt}
                          onChange={(e) => setCustomMusicPrompt(e.target.value)}
                          placeholder="e.g., Lyrical piano building to drop"
                          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-900"
                        />
                        <button
                          onClick={handleGenerateCustomMusic}
                          disabled={isGeneratingMusic}
                          className="px-3.5 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shrink-0 disabled:opacity-50"
                        >
                          {isGeneratingMusic ? '...' : 'Generate'}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right 5 cols: Audio Player & Detected Musical Cues Summary */}
                <div className="lg:col-span-5 space-y-4 lg:border-l lg:border-slate-100 lg:pl-6">
                  <label className="block text-xs font-semibold text-slate-700">
                    Active Track Preview & Cue Structure
                  </label>
                  {activeCueMap && (
                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-4">
                      <div>
                        <div className="text-xs font-semibold text-slate-900 mb-2">
                          {activeCueMap.title}
                        </div>
                        <audio controls src={activeCueMap.url} className="w-full h-9" />
                      </div>

                      {/* Clean Beat & Section Cue Map */}
                      <div>
                        <div className="flex items-center justify-between text-[11px] text-slate-600 mb-1.5">
                          <span>Dark ticks = Downbeats (Jump/Turn Sync)</span>
                          <span>Shaded = Sustained/Pause (Photos)</span>
                        </div>
                        <div className="relative h-20 rounded-lg bg-white border border-slate-200 p-2 overflow-hidden flex flex-col justify-end">
                          {activeCueMap.sections.map((sec, idx) => {
                            const leftPct = Math.min(95, (sec.start_sec / targetDurationSec) * 100);
                            const widthPct = Math.max(5, (sec.duration_sec / targetDurationSec) * 100);
                            if (leftPct >= 100) return null;
                            return (
                              <div
                                key={idx}
                                style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                                className="absolute top-0 bottom-0 bg-slate-200/70 border-x border-slate-300 flex items-start justify-center pt-1"
                              >
                                <span className="text-[9px] font-semibold uppercase text-slate-700 bg-white/90 px-1 rounded">
                                  {sec.cue_type === 'pause' ? 'Pause' : 'Sustained'}
                                </span>
                              </div>
                            );
                          })}

                          {activeCueMap.downbeat_times.map((db, idx) => {
                            const leftPct = (db / targetDurationSec) * 100;
                            if (leftPct > 100) return null;
                            return (
                              <div
                                key={idx}
                                style={{ left: `${leftPct}%` }}
                                className="absolute top-4 bottom-0 w-[1.5px] bg-slate-900 z-10"
                                title={`Downbeat @ ${db}s`}
                              />
                            );
                          })}

                          <div className="flex items-end gap-[2px] h-10 w-full z-0">
                            {activeCueMap.energy_envelope
                              .slice(0, Math.round(targetDurationSec * 10))
                              .map((val, idx) => (
                                <div
                                  key={idx}
                                  style={{ height: `${Math.max(12, Math.round(val * 100))}%` }}
                                  className="flex-1 bg-slate-400/70 rounded-t-sm"
                                />
                              ))}
                          </div>
                        </div>
                      </div>

                      <div className="space-y-1.5 text-xs text-slate-600">
                        <div className="font-semibold text-slate-800">
                          Detected Photo Insertion Cues:
                        </div>
                        {activeCueMap.sections.map((s, i) => (
                          <div key={i} className="flex items-center justify-between text-[11px]">
                            <span className="capitalize font-medium text-slate-700">
                              • {s.cue_type.replace('_', ' ')}
                            </span>
                            <span className="font-mono text-slate-500">
                              {s.start_sec.toFixed(1)}s – {s.end_sec.toFixed(1)}s ({s.duration_sec.toFixed(1)}s)
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ===================================================================
            STEP 4: REVIEW TIMELINE, VIDEO PREVIEW, POST COPY & CAPCUT EXPORT
           =================================================================== */}
        {currentStep === 4 && (
          <div className="space-y-6">
            {/* Step 4 Header Bar */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Step 4 of 4
                </span>
                <h2 className="text-lg font-semibold text-slate-900 mt-0.5">
                  Review Beat-Synced Timeline, Instagram Copy & Export
                </h2>
                <p className="text-sm text-slate-600 mt-0.5">
                  Preview the rendered 9:16 video, fine-tune clip order or Ken Burns photo effects, copy your Instagram post content, or open the editable project in CapCut Desktop.
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => setCurrentStep(3)}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-xs font-medium text-slate-700 transition"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Back to Music
                </button>
                <button
                  onClick={handleGenerateSessionAndAdvance}
                  disabled={isGeneratingSession}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold disabled:opacity-50 transition"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isGeneratingSession ? 'animate-spin' : ''}`} />
                  Regenerate Session
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left 4 cols: 9:16 Video Player + Direct MP4 / CapCut / FCPXML Downloads */}
              <div className="lg:col-span-4 space-y-6">
                <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                      <Play className="w-4 h-4 text-slate-700" />
                      9:16 Reel Video Preview
                    </h3>
                    {session?.exports.mp4_url && (
                      <a
                        href={session.exports.mp4_url}
                        download={`InsCreator_${session.session_id}.mp4`}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-slate-900 hover:underline"
                      >
                        <Download className="w-3.5 h-3.5" />
                        Download MP4
                      </a>
                    )}
                  </div>

                  <div className="aspect-[9/16] max-h-[440px] mx-auto rounded-lg overflow-hidden bg-slate-900 border border-slate-200 flex items-center justify-center">
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
                      <div className="text-xs text-slate-400 p-6 text-center">
                        Click &quot;Generate Reel &amp; Post&quot; in Step 3 to render your video.
                      </div>
                    )}
                  </div>

                  {/* Interactive Editing Software Export Section (CapCut & FCPXML) */}
                  {session && (
                    <div className="mt-5 pt-4 border-t border-slate-100 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-900 flex items-center gap-1.5">
                          <Scissors className="w-3.5 h-3.5 text-slate-700" />
                          Video Editing Software Hand-off
                        </span>
                        {session.exports.capcut_installed_to_app && (
                          <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Installed to CapCut
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-500 leading-relaxed">
                        Exported with multi-track video/audio, beat markers, and Ken Burns keyframes for interactive adjustment in CapCut Desktop or Final Cut / DaVinci Resolve.
                      </p>
                      <div className="grid grid-cols-2 gap-2">
                        {session.exports.capcut_zip_url && (
                          <a
                            href={session.exports.capcut_zip_url}
                            download
                            className="inline-flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition"
                          >
                            <Download className="w-3.5 h-3.5" />
                            CapCut Draft (.zip)
                          </a>
                        )}
                        {session.exports.fcpxml_url && (
                          <a
                            href={session.exports.fcpxml_url}
                            download
                            className="inline-flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-xs font-medium transition"
                          >
                            <Download className="w-3.5 h-3.5" />
                            FCPXML Project
                          </a>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Right 8 cols: Interactive Beat-Synced Timeline + Instagram Titles & Copy */}
              <div className="lg:col-span-8 space-y-6">
                {/* Interactive Beat-Synced Timeline */}
                <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                        <Sliders className="w-4 h-4 text-slate-700" />
                        Beat-Synced Edit Timeline ({timelineClips.length} Cuts)
                      </h3>
                      <p className="text-xs text-slate-500">
                        Jump peaks and turns are slip-synced to measure downbeats; still photos are placed on sustained notes and pauses.
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => handleApplyTimelineAdjustments(false)}
                        disabled={isUpdatingTimeline}
                        className="px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-xs font-medium text-slate-700 transition"
                      >
                        Update CapCut Draft
                      </button>
                      <button
                        onClick={() => handleApplyTimelineAdjustments(true)}
                        disabled={isUpdatingTimeline}
                        className="px-3.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition"
                      >
                        {isUpdatingTimeline ? 'Rendering...' : 'Re-Render MP4'}
                      </button>
                    </div>
                  </div>

                  <div className="space-y-2.5 max-h-[380px] overflow-y-auto pr-1">
                    {timelineClips.map((clip, idx) => {
                      const isPhoto = clip.media_type === 'photo';
                      return (
                        <div
                          key={clip.clip_id}
                          className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/50 hover:bg-slate-50 transition"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-start gap-3">
                              <span className="w-6 h-6 rounded-md bg-slate-900 text-white text-xs font-semibold flex items-center justify-center shrink-0 mt-0.5">
                                {idx + 1}
                              </span>
                              <div>
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="text-xs font-semibold text-slate-900">
                                    {clip.filename}
                                  </span>
                                  <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-slate-200 text-slate-800">
                                    {isPhoto
                                      ? clip.synced_cue_type === 'musical_pause_photo'
                                        ? 'Musical Pause • Photo'
                                        : 'Sustained Note • Photo'
                                      : clip.matched_dance_move === 'turn_spin'
                                      ? 'Downbeat • Turn Peak'
                                      : 'Downbeat • Jump Peak'}
                                  </span>
                                </div>
                                <p className="text-xs text-slate-600 mt-1">
                                  {clip.sync_explanation}
                                </p>
                              </div>
                            </div>

                            <div className="flex items-center gap-1 shrink-0">
                              <span className="text-xs font-mono text-slate-500 mr-1.5">
                                {clip.timeline_start_sec.toFixed(1)}s – {clip.timeline_end_sec.toFixed(1)}s
                              </span>
                              <button
                                onClick={() => handleSwapClipOrder(idx, -1)}
                                disabled={idx === 0}
                                className="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 text-xs"
                                title="Move up"
                              >
                                ↑
                              </button>
                              <button
                                onClick={() => handleSwapClipOrder(idx, 1)}
                                disabled={idx === timelineClips.length - 1}
                                className="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 text-xs"
                                title="Move down"
                              >
                                ↓
                              </button>
                            </div>
                          </div>

                          <div className="mt-3 pt-2.5 border-t border-slate-200/70 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                            {isPhoto ? (
                              <div className="sm:col-span-2">
                                <label className="block text-[11px] font-medium text-slate-600 mb-1">
                                  Photo Effect (Ken Burns / Zoom)
                                </label>
                                <select
                                  value={clip.photo_effect || 'ken_burns_zoom_in'}
                                  onChange={(e) =>
                                    handleClipFieldChange(idx, 'photo_effect', e.target.value)
                                  }
                                  className="w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900"
                                >
                                  {PHOTO_EFFECT_OPTIONS.map((opt) => (
                                    <option key={opt.value} value={opt.value}>
                                      {opt.label}
                                    </option>
                                  ))}
                                </select>
                              </div>
                            ) : (
                              <div className="sm:col-span-2">
                                <label className="block text-[11px] font-medium text-slate-600 mb-1">
                                  Beat Synchronization & Speed Profile
                                </label>
                                <div className="px-2.5 py-1.5 rounded-md border border-slate-200 bg-white text-xs text-slate-700 truncate">
                                  {clip.speed_ramp_curve || '1.0x Direct Slip-Sync to Downbeat'}
                                </div>
                              </div>
                            )}

                            <div>
                              <label className="block text-[11px] font-medium text-slate-600 mb-1">
                                Transition
                              </label>
                              <select
                                value={clip.transition_in}
                                onChange={(e) =>
                                  handleClipFieldChange(idx, 'transition_in', e.target.value)
                                }
                                className="w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900"
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
                </div>

                {/* Attractive Instagram Post Titles, Captions & Hashtags */}
                {postCopy && (
                  <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                          <FileText className="w-4 h-4 text-slate-700" />
                          Instagram Post Titles & Caption
                        </h3>
                        <p className="text-xs text-slate-500">
                          Generated for your event and supplemental directions. Edit any field or switch caption tones below.
                        </p>
                      </div>
                      <button
                        onClick={() =>
                          copyToClipboard(
                            'all_post',
                            `${postCopy.post_headline}\n\n${displayedCaption}\n\n${postCopy.hashtags.join(' ')}`
                          )
                        }
                        className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition"
                      >
                        {copiedField === 'all_post' ? (
                          <>
                            <Check className="w-3.5 h-3.5" /> Copied Post
                          </>
                        ) : (
                          <>
                            <Copy className="w-3.5 h-3.5" /> Copy Full Post
                          </>
                        )}
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">
                          On-Screen Video Title Hook (First 2.6s)
                        </label>
                        <input
                          type="text"
                          value={postCopy.hook_title_overlay}
                          onChange={(e) =>
                            setPostCopy({ ...postCopy, hook_title_overlay: e.target.value })
                          }
                          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-900"
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">
                          Instagram Post Headline
                        </label>
                        <input
                          type="text"
                          value={postCopy.post_headline}
                          onChange={(e) =>
                            setPostCopy({ ...postCopy, post_headline: e.target.value })
                          }
                          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-900"
                        />
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="text-xs font-semibold text-slate-700">
                          Post Caption Content
                        </label>
                        <div className="flex gap-1.5">
                          <button
                            onClick={() => setSelectedCaptionVariantIdx(-1)}
                            className={`text-xs px-2.5 py-1 rounded-md font-medium ${
                              selectedCaptionVariantIdx === -1
                                ? 'bg-slate-900 text-white'
                                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                            }`}
                          >
                            Storytelling
                          </button>
                          {postCopy.caption_alternatives.map((alt, i) => (
                            <button
                              key={i}
                              onClick={() => setSelectedCaptionVariantIdx(i)}
                              className={`text-xs px-2.5 py-1 rounded-md font-medium ${
                                selectedCaptionVariantIdx === i
                                  ? 'bg-slate-900 text-white'
                                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                              }`}
                            >
                              {alt.label.split(' ')[0]}
                            </button>
                          ))}
                        </div>
                      </div>

                      <textarea
                        rows={5}
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
                        className="w-full rounded-lg border border-slate-300 bg-white p-3 text-xs text-slate-800 leading-relaxed"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                        Tags & Hashtags
                      </label>
                      <div className="flex flex-wrap gap-1.5">
                        {postCopy.hashtags.map((tag) => (
                          <span
                            key={tag}
                            className="text-xs px-2.5 py-1 rounded-md bg-slate-100 text-slate-700 font-medium"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Clean Settings Modal */}
      {showSettingsModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-lg rounded-xl bg-white border border-slate-200 p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-slate-900 flex items-center gap-2">
                <Settings className="w-4 h-4 text-slate-600" />
                Google Photos OAuth & API Settings
              </h3>
              {googlePhotosConnected && (
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium">
                  Google Photos Connected
                </span>
              )}
            </div>

            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 space-y-2.5">
              <div className="text-xs font-semibold text-slate-800">
                1-Click Google Photos Sign-In (OAuth 2.0)
              </div>
              <p className="text-xs text-slate-600 leading-relaxed">
                Your Client ID is pre-loaded. In Google Cloud Console under your OAuth Client ID, ensure{' '}
                <code className="px-1.5 py-0.5 rounded bg-slate-200 text-slate-800 font-mono text-[11px]">
                  http://127.0.0.1:8000/api/auth/google/callback
                </code>{' '}
                is listed under <b>Authorized redirect URIs</b>, then click below:
              </p>

              <div className="space-y-2">
                <div>
                  <label className="block text-[11px] font-medium text-slate-600 mb-0.5">
                    Google OAuth Client ID
                  </label>
                  <input
                    type="text"
                    value={googleClientIdInput}
                    onChange={(e) => setGoogleClientIdInput(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 font-mono"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-medium text-slate-600 mb-0.5">
                    Google OAuth Client Secret (Configured)
                  </label>
                  <input
                    type="password"
                    value={googleClientSecretInput}
                    onChange={(e) => setGoogleClientSecretInput(e.target.value)}
                    placeholder="Leave blank to keep existing secret..."
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900"
                  />
                </div>
              </div>

              <button
                onClick={handleStartGoogleOAuthSignIn}
                className="w-full py-2 px-4 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition cursor-pointer"
              >
                Sign in with Google & Authorize Google Photos
              </button>
            </div>

            <div className="space-y-3 pt-1">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Or Paste Google Photos OAuth Bearer Token Directly
                </label>
                <input
                  type="password"
                  value={googleTokenInput}
                  onChange={(e) => setGoogleTokenInput(e.target.value)}
                  placeholder="ya29.a0..."
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Google Gemini API Key (Configured)
                </label>
                <input
                  type="password"
                  value={geminiKeyInput}
                  onChange={(e) => setGeminiKeyInput(e.target.value)}
                  placeholder="Leave blank to keep existing key..."
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowSettingsModal(false)}
                className="px-4 py-2 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-xs font-medium text-slate-700"
              >
                Close
              </button>
              <button
                onClick={handleSaveSettings}
                className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-xs font-semibold text-white"
              >
                Save Settings
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
export default App;
