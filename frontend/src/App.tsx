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
import { ProgressPanel, useTaskRunner, xhrUpload } from './ProgressPanel';
import { MusicCuePreview } from './MusicCuePreview';
import { HookStyleStudio } from './HookStyleStudio';

const PHOTO_EFFECT_OPTIONS = [
  { value: 'ken_burns_zoom_in', label: 'Slow Cinematic Zoom-In (Focus Dancer)' },
  { value: 'ken_burns_zoom_out', label: 'Wide Stage Reveal Zoom-Out' },
  { value: 'ken_burns_pan_lr', label: 'Smooth Stage Pan (Left → Right)' },
  { value: 'ken_burns_pan_rl', label: 'Smooth Stage Pan (Right → Left)' },
  { value: 'ken_burns_pan_diag', label: 'Dynamic Diagonal Drift' },
  { value: 'tilt_up_stage', label: 'Vertical Tilt Up (Floor to Spotlight)' },
  { value: 'beat_pulse_zoom', label: 'Rhythmic Beat-Pulse Zoom' },
  { value: 'soft_glow_dissolve', label: 'Dreamy Stage Bloom & Soft Zoom' },
  { value: 'spotlight_vignette', label: 'Stage Spotlight Vignette & Focus' },
  { value: 'polaroid_frame', label: 'Editorial Gallery Framed Portrait' },
];

const TRANSITION_OPTIONS = [
  { value: 'cut_on_beat', label: 'Hard Cut on Beat' },
  { value: 'cross_dissolve', label: 'Smooth Cross-Dissolve' },
  { value: 'flash_white', label: 'Stage Strobe White Flash' },
  { value: 'dip_to_black', label: 'Cinematic Fade from Black' },
  { value: 'zoom_whip', label: 'Dynamic Zoom-In Whip' },
  { value: 'slide_left', label: 'Smooth Slide Left Push' },
  { value: 'slide_up', label: 'Vertical Reel Slide Up' },
  { value: 'light_leak_warm', label: 'Golden Stage Light Leak' },
  { value: 'blur_dissolve', label: 'Defocus Rack-Focus Dissolve' },
];

async function fetchJson<T>(url: string, init: RequestInit = {}, taskId?: string): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (taskId) headers.set('X-Task-Id', taskId);
  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || body);
    } catch {
      detail = await res.text().catch(() => '');
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

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
  const [mediaTrims, setMediaTrims] = useState<
    Record<string, { trim_mode: 'auto' | 'manual'; trim_start_sec: number; trim_end_sec: number }>
  >({});
  const videoRefs = useRef<Record<string, HTMLVideoElement | null>>({});

  // User workflow inputs
  const [selectedPresetId, setSelectedPresetId] = useState('competition_stage_glory');
  const [supplementalDirections, setSupplementalDirections] = useState(
    'Sync her highest jump peak to the main measure downbeat with slow-motion at the apex, insert a poised photo during the sustained note with Ken Burns zoom, and write an inspiring proud-parent caption.'
  );
  const [selectedMusicId, setSelectedMusicId] = useState('competition_edm_pop');
  const [musicGenreFilter, setMusicGenreFilter] = useState<string>('all');
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
  const [postCopyPrompt, setPostCopyPrompt] = useState<string>('');
  const [isRegeneratingPostCopy, setIsRegeneratingPostCopy] = useState<boolean>(false);

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
  const { task, runTask, showWaiting, finish: finishTask, dismiss: dismissTask } =
    useTaskRunner(setStatusMessage);
  const [autoPlayMusic, setAutoPlayMusic] = useState(false);
  const pickerPollBusyRef = useRef(false);

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
      const [mediaRes, sessRes] = await Promise.all([
        fetch('/api/media/search?source=google_photos'),
        fetch('/api/sessions'),
      ]);
      if (mediaRes.ok) {
        const mediaData: MediaItem[] = await mediaRes.json();
        const userOnly = mediaData.filter((m) => m.source !== 'sample');
        if (userOnly.length > 0) {
          setMatchedMedia(userOnly);
          setSelectedMediaIds(new Set(userOnly.map((m) => m.id)));
        }
      }
      if (sessRes.ok) {
        const sessList: WorkflowSession[] = await sessRes.json();
        if (sessList.length > 0) {
          const latest = sessList[0];
          setSession(latest);
          setTimelineClips(latest.timeline_clips);
          setPostCopy(latest.post_copy || null);
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
    const pickerTaskId = `gp_${sessionId}`;
    showWaiting(
      pickerTaskId,
      'Importing from Google Photos',
      'Waiting for you to pick photos & videos in the Google Photos tab, then click “Done”…',
      'Google Photos Picker API'
    );

    pickerPollTimerRef.current = window.setInterval(async () => {
      // Never overlap polls: one poll may be busy downloading & analyzing the picked items
      if (pickerPollBusyRef.current) return;
      pickerPollBusyRef.current = true;
      try {
        const res = await fetch(`/api/media/google-photos/picker-session/${sessionId}`, {
          headers: { 'X-Task-Id': pickerTaskId },
        });
        if (!res.ok) return;
        const data = await res.json();
        if (data.mediaItemsSet && Array.isArray(data.importedItems)) {
          stopPickerPolling();
          finishTask(pickerTaskId, true, `Imported ${data.importedItems.length} item(s)`);
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
      } finally {
        pickerPollBusyRef.current = false;
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
    stopPickerPolling();
    try {
      const url = activePickerSessionId
        ? `/api/media/google-photos/import?session_id=${encodeURIComponent(activePickerSessionId)}`
        : '/api/media/google-photos/import';
      const imported = await runTask(
        'Importing from Google Photos',
        { stage: 'Contacting Google Photos…', service: 'Google Photos Picker API' },
        (taskId) => fetchJson<MediaItem[]>(url, { method: 'POST' }, taskId),
        'Import complete'
      );
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
    const totalMb = validFiles.reduce((acc, f) => acc + f.size, 0) / (1024 * 1024);
    try {
      const uploaded = await runTask(
        `Importing ${validFiles.length} file(s)`,
        {
          stage: `Uploading ${validFiles.length} file(s) (${totalMb.toFixed(1)} MB)`,
          service: 'Browser → local Ins-Creator server',
          uploadShare: 0.3,
        },
        (taskId, onUpload) =>
          xhrUpload<MediaItem[]>('/api/media/upload', formData, { 'X-Task-Id': taskId }, onUpload),
        'Import & analysis complete'
      );
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
      const data = await runTask(
        'Loading demo media',
        { stage: 'Preparing demo dance clips & photos', service: 'Local sample dataset' },
        (taskId) => fetchJson<MediaItem[]>('/api/media/search?source=sample', {}, taskId)
      );
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

  async function handleReanalyzeMedia() {
    setIsImportingMedia(true);
    setStatusMessage('Analyzing media EXIF, quality, focal points, and dance metadata...');
    try {
      const data = await runTask(
        'Re-analyzing media metadata',
        { stage: 'Clearing analysis cache', service: 'Local media cache' },
        (taskId) => fetchJson<MediaItem[]>('/api/media/reanalyze', { method: 'POST' }, taskId)
      );
      setMatchedMedia(data);
      setStatusMessage(`Analyzed and applied metadata to ${data.length} media item(s).`);
    } catch (err) {
      console.error(err);
      setStatusMessage('Failed to re-analyze media metadata.');
    } finally {
      setIsImportingMedia(false);
    }
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
      const cueMap = await runTask(
        `Analyzing “${file.name}”`,
        {
          stage: `Uploading ${(file.size / (1024 * 1024)).toFixed(1)} MB`,
          service: 'Browser → local Ins-Creator server',
          uploadShare: 0.25,
        },
        (taskId, onUpload) =>
          xhrUpload<AudioCueMap>('/api/music/upload', formData, { 'X-Task-Id': taskId }, onUpload),
        'Track analyzed & selected'
      );
      setMusicTracks((prev) => [
        cueMap,
        ...prev.filter((t) => t.track_id !== cueMap.track_id),
      ]);
      setSelectedMusicId(cueMap.track_id);
      setAutoPlayMusic(true);
      setStatusMessage(
        `Uploaded and selected "${cueMap.title}" (${cueMap.bpm} BPM, ${cueMap.downbeat_times.length} downbeats).`
      );
    } catch (err) {
      console.error(err);
      setStatusMessage('Error uploading audio file.');
    } finally {
      setIsGeneratingMusic(false);
      e.target.value = '';
    }
  }

  async function handleGenerateCustomMusic() {
    if (!customMusicPrompt.trim()) return;
    setIsGeneratingMusic(true);
    const selectedPhotoCount = matchedMedia.filter(
      (m) => selectedMediaIds.has(m.id) && m.media_type === 'photo'
    ).length;
    const photoMomentCount = Math.max(2, selectedPhotoCount || 3);
    setStatusMessage(
      `Generating custom Gemini Lyria soundtrack for "${customMusicPrompt}" with ${photoMomentCount} photo-showcase phrases...`
    );
    try {
      const cueMap = await runTask(
        'Generating custom music via Gemini Lyria',
        {
          stage: `Composing “${customMusicPrompt.slice(0, 36)}” (${photoMomentCount} photo moments)`,
          service: 'Gemini 2.5 Flash + Lyria 3',
        },
        (taskId) =>
          fetchJson<AudioCueMap>(
            '/api/music/generate',
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                prompt: customMusicPrompt,
                target_duration_sec: targetDurationSec,
                photo_count: photoMomentCount,
              }),
            },
            taskId
          ),
        'Track generated & selected'
      );
      setMusicTracks((prev) => [
        cueMap,
        ...prev.filter((t) => t.track_id !== cueMap.track_id),
      ]);
      setSelectedMusicId(cueMap.track_id);
      setAutoPlayMusic(true);
      setStatusMessage(`Generated and selected "${cueMap.title}" (${cueMap.bpm} BPM).`);
    } catch (err) {
      console.error(err);
      setStatusMessage('Error generating custom music track.');
    } finally {
      setIsGeneratingMusic(false);
    }
  }

  function updateMediaTrim(
    mediaId: string,
    totalDuration: number,
    patch: Partial<{ trim_mode: 'auto' | 'manual'; trim_start_sec: number; trim_end_sec: number }>
  ) {
    setMediaTrims((prev) => {
      const existing = prev[mediaId] || {
        trim_mode: 'auto',
        trim_start_sec: 0,
        trim_end_sec: Math.round(totalDuration * 10) / 10,
      };
      const next = { ...existing, ...patch };
      if (next.trim_start_sec < 0) next.trim_start_sec = 0;
      if (next.trim_end_sec > totalDuration) next.trim_end_sec = Math.round(totalDuration * 10) / 10;
      if (next.trim_end_sec <= next.trim_start_sec + 0.5) {
        next.trim_end_sec = Math.min(
          Math.round(totalDuration * 10) / 10,
          Math.round((next.trim_start_sec + 2.5) * 10) / 10
        );
      }
      return { ...prev, [mediaId]: next };
    });
  }

  function seekAndSelectVideoPortion(
    mediaId: string,
    totalDuration: number,
    centerSec: number,
    windowHalfSec: number = 1.6
  ) {
    const startSec = Math.max(0, Math.round((centerSec - windowHalfSec) * 10) / 10);
    const endSec = Math.min(
      Math.round(totalDuration * 10) / 10,
      Math.round((centerSec + windowHalfSec) * 10) / 10
    );
    updateMediaTrim(mediaId, totalDuration, {
      trim_mode: 'manual',
      trim_start_sec: startSec,
      trim_end_sec: endSec,
    });
    const vidEl = videoRefs.current[mediaId];
    if (vidEl) {
      vidEl.currentTime = startSec;
      void vidEl.play().catch(() => {});
      window.setTimeout(() => {
        if (vidEl && !vidEl.paused) {
          vidEl.pause();
        }
      }, Math.max(1500, (endSec - startSec) * 1000));
    }
  }

  async function handleGenerateSessionAndAdvance() {
    setIsGeneratingSession(true);
    setStatusMessage(
      'Aligning jump peaks & turns to measure downbeats, placing photos on sustained notes/pauses, rendering 9:16 MP4, and generating CapCut draft...'
    );
    try {
      const requestBody = JSON.stringify({
          search_query: supplementalDirections || 'dance event',
          media_source: 'auto',
          style_preset_id: selectedPresetId,
          supplemental_directions: supplementalDirections,
          music_track_id: selectedMusicId,
          music_generation_prompt: null,
          target_duration_sec: targetDurationSec,
          selected_media_ids: selectedMediaIds.size > 0 ? Array.from(selectedMediaIds) : null,
          media_trims: Object.keys(mediaTrims).length > 0 ? mediaTrims : null,
          auto_render_mp4: true,
          auto_export_capcut: true,
        });
      const sess = await runTask(
        'Generating Reel & Post',
        { stage: 'Starting workflow', service: 'Ins-Creator pipeline' },
        (taskId) =>
          fetchJson<WorkflowSession>(
            '/api/sessions/generate',
            { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: requestBody },
            taskId
          ),
        'Reel, post copy & CapCut draft ready'
      );
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
      const updated = await runTask(
        reRenderMp4 ? 'Re-rendering MP4' : 'Saving timeline',
        { stage: 'Applying timeline changes', service: 'Ins-Creator pipeline' },
        (taskId) =>
          fetchJson<WorkflowSession>(
            `/api/sessions/${session.session_id}/timeline`,
            {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                timeline_clips: timelineClips,
                post_copy: postCopy,
                color_grade: session.color_grade,
                re_render_mp4: reRenderMp4,
              }),
            },
            taskId
          ),
        reRenderMp4 ? 'Video re-rendered' : 'Timeline saved'
      );
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

  async function handleRegeneratePostCopy(promptOverride?: string) {
    if (!session) return;
    const promptToUse = promptOverride !== undefined ? promptOverride : postCopyPrompt;
    if (promptOverride !== undefined) {
      setPostCopyPrompt(promptOverride);
    }
    setIsRegeneratingPostCopy(true);
    setStatusMessage(
      promptToUse.trim()
        ? `Regenerating personalized post copy with prompt: "${promptToUse.trim()}"...`
        : 'Regenerating personalized post copy from media metadata...'
    );
    try {
      const updated = await runTask(
        'Regenerating post copy',
        { stage: 'Writing personalized captions', service: 'Copywriter' },
        (taskId) =>
          fetchJson<WorkflowSession>(
            `/api/sessions/${session.session_id}/post-copy`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ custom_prompt: promptToUse }),
            },
            taskId
          ),
        'Post copy updated'
      );
      setSession(updated);
      setTimelineClips(updated.timeline_clips);
      setPostCopy(updated.post_copy || null);
      setStatusMessage('Personalized Instagram post titles, captions, and hashtags updated.');
    } catch (err) {
      console.error(err);
      setStatusMessage('Error regenerating post copy.');
    } finally {
      setIsRegeneratingPostCopy(false);
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

  const selectedMusicTrack =
    musicTracks.find((t) => t.track_id === selectedMusicId) ||
    session?.audio_cue_map ||
    musicTracks[0];

  const activeCueMap =
    currentStep === 4 && session?.audio_cue_map
      ? session.audio_cue_map
      : selectedMusicTrack;

  const activePreset = presets.find((p) => p.id === selectedPresetId) || presets[0];

  const displayedCaption =
    selectedCaptionVariantIdx === -1
      ? postCopy?.caption_primary || ''
      : postCopy?.caption_alternatives?.[selectedCaptionVariantIdx]?.text || '';

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
      <ProgressPanel task={task} onDismiss={dismissTask} />
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
                    Imported Session Media ({selectedMediaIds.size} of {matchedMedia.length} selected)
                  </h3>
                  <p className="text-xs text-slate-500">
                    Each imported photo or video is analyzed for EXIF camera/date metadata, focal subject framing, sharpness, and dance peaks.
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
                        onClick={handleReanalyzeMedia}
                        disabled={isImportingMedia}
                        className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded border border-slate-200 hover:bg-slate-50 text-slate-700 font-medium transition"
                      >
                        <RefreshCw className={`w-3 h-3 ${isImportingMedia ? 'animate-spin' : ''}`} />
                        Re-Analyze Metadata
                      </button>
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
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {matchedMedia.map((item) => {
                    const isChecked = selectedMediaIds.has(item.id);
                    const vTrim = mediaTrims[item.id] || {
                      trim_mode: item.trim_mode === 'manual' ? 'manual' : 'auto',
                      trim_start_sec: item.trim_start_sec ?? 0,
                      trim_end_sec:
                        item.trim_end_sec ?? Math.round((item.duration_sec || 10) * 10) / 10,
                    };
                    return (
                      <div
                        key={item.id}
                        onClick={() => toggleMediaSelection(item.id)}
                        className={`rounded-xl border overflow-hidden text-left cursor-pointer transition flex flex-col justify-between ${
                          isChecked
                            ? 'border-slate-900 bg-slate-50/40 shadow-sm'
                            : 'border-slate-200 bg-white opacity-60 hover:opacity-100'
                        }`}
                      >
                        {/* Thumbnail / Video Preview */}
                        <div className="h-44 bg-slate-900 flex items-center justify-center overflow-hidden relative">
                          {item.media_type === 'photo' ? (
                            <img
                              src={item.url}
                              alt={item.filename}
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <video
                              ref={(el) => {
                                videoRefs.current[item.id] = el;
                              }}
                              src={item.url}
                              controls={vTrim.trim_mode === 'manual'}
                              muted
                              playsInline
                              preload="metadata"
                              onClick={(e) => {
                                if (vTrim.trim_mode === 'manual') e.stopPropagation();
                              }}
                              className="w-full h-full object-cover"
                            />
                          )}
                          <div className="absolute top-2 left-2 flex items-center gap-1.5 pointer-events-none">
                            <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-900/80 text-white uppercase">
                              {item.media_type}
                            </span>
                            {item.event_category && item.event_category !== 'general' && (
                              <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-white/90 text-slate-900 capitalize">
                                {item.event_category}
                              </span>
                            )}
                          </div>
                          <span className="absolute top-2 right-2 text-[10px] font-medium px-2 py-0.5 rounded bg-slate-900/80 text-slate-100 pointer-events-none">
                            {item.width}×{item.height}
                            {item.media_type === 'video' ? ` • ${item.duration_sec.toFixed(1)}s` : ''}
                          </span>
                        </div>

                        <div className="p-3.5 flex-1 flex flex-col justify-between gap-2.5">
                          <div className="space-y-1.5">
                            <div className="flex items-center gap-2 min-w-0">
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={() => {}}
                                className="rounded border-slate-300 text-slate-900 focus:ring-slate-900 shrink-0"
                              />
                              <span
                                className="text-xs font-semibold text-slate-900 truncate"
                                title={item.filename}
                              >
                                {item.filename}
                              </span>
                            </div>

                            {/* Analyzed Semantic Description */}
                            {item.semantic_caption && (
                              <p className="text-[11px] text-slate-600 leading-snug line-clamp-2 bg-white border border-slate-200/80 rounded-md px-2.5 py-1.5">
                                {item.semantic_caption}
                              </p>
                            )}

                            {/* Inferred Style & Context Tags */}
                            {item.tags && item.tags.length > 0 && (
                              <div className="flex flex-wrap gap-1 pt-0.5">
                                {item.tags.map((tag, idx) => (
                                  <span
                                    key={idx}
                                    className="text-[10px] px-2 py-0.5 rounded-full bg-slate-200/70 text-slate-800 font-medium"
                                  >
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>

                          {/* Applied Technical & EXIF Metadata + Video Portion Selection Footer */}
                          <div className="pt-2 border-t border-slate-200/70 space-y-2 text-[11px]">
                            {(item.camera_model || item.creation_time) && (
                              <div className="flex flex-wrap items-center justify-between gap-1 text-slate-600">
                                {item.camera_model && (
                                  <span className="font-medium text-slate-700 truncate">
                                    📷 {item.camera_model}
                                  </span>
                                )}
                                {item.creation_time && (
                                  <span className="text-[10px] text-slate-500">
                                    {item.creation_time}
                                  </span>
                                )}
                              </div>
                            )}

                            <div className="flex flex-wrap items-center justify-between gap-1 text-[10px] text-slate-600">
                              <span>
                                Quality <b>{Math.round(item.aesthetic_score * 100)}%</b> • Sharpness{' '}
                                <b>{Math.round(item.sharpness_score * 100)}%</b>
                              </span>
                              {item.focal_point && (
                                <span className="text-slate-500">
                                  Focal ({item.focal_point.center_x.toFixed(2)},{' '}
                                  {item.focal_point.center_y.toFixed(2)})
                                </span>
                              )}
                            </div>

                            {/* Video Portion Selection: Auto AI Peaks vs. Manual Trim Range */}
                            {item.media_type === 'video' && (
                              <div
                                onClick={(e) => e.stopPropagation()}
                                className="p-2.5 rounded-lg bg-white border border-slate-200 space-y-2 mt-1 cursor-default"
                              >
                                <div className="flex items-center justify-between gap-1">
                                  <span className="text-[10px] font-semibold text-slate-800 flex items-center gap-1">
                                    <Scissors className="w-3 h-3 text-slate-600" />
                                    Video Portion Selection
                                  </span>
                                  <div className="inline-flex rounded-md border border-slate-200 p-0.5 bg-slate-100">
                                    <button
                                      type="button"
                                      onClick={() =>
                                        updateMediaTrim(item.id, item.duration_sec, {
                                          trim_mode: 'auto',
                                        })
                                      }
                                      className={`px-2 py-0.5 rounded text-[10px] font-medium transition ${
                                        vTrim.trim_mode === 'auto'
                                          ? 'bg-slate-900 text-white'
                                          : 'text-slate-600 hover:text-slate-900'
                                      }`}
                                    >
                                      Auto (AI Peaks)
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() =>
                                        updateMediaTrim(item.id, item.duration_sec, {
                                          trim_mode: 'manual',
                                        })
                                      }
                                      className={`px-2 py-0.5 rounded text-[10px] font-medium transition ${
                                        vTrim.trim_mode === 'manual'
                                          ? 'bg-slate-900 text-white'
                                          : 'text-slate-600 hover:text-slate-900'
                                      }`}
                                    >
                                      Manual Trim
                                    </button>
                                  </div>
                                </div>

                                {vTrim.trim_mode === 'manual' ? (
                                  <div className="space-y-1.5">
                                    <div className="grid grid-cols-2 gap-2">
                                      <div>
                                        <label className="block text-[9px] text-slate-500">
                                          Start (0s – {item.duration_sec.toFixed(1)}s)
                                        </label>
                                        <input
                                          type="number"
                                          step={0.5}
                                          min={0}
                                          max={Math.max(0, item.duration_sec - 1)}
                                          value={vTrim.trim_start_sec}
                                          onChange={(e) =>
                                            updateMediaTrim(item.id, item.duration_sec, {
                                              trim_mode: 'manual',
                                              trim_start_sec: Number(e.target.value) || 0,
                                            })
                                          }
                                          className="w-full rounded border border-slate-300 px-2 py-1 text-[11px] font-mono text-slate-900"
                                        />
                                      </div>
                                      <div>
                                        <label className="block text-[9px] text-slate-500">
                                          End (max {item.duration_sec.toFixed(1)}s)
                                        </label>
                                        <input
                                          type="number"
                                          step={0.5}
                                          min={0.5}
                                          max={item.duration_sec}
                                          value={vTrim.trim_end_sec}
                                          onChange={(e) =>
                                            updateMediaTrim(item.id, item.duration_sec, {
                                              trim_mode: 'manual',
                                              trim_end_sec:
                                                Number(e.target.value) || item.duration_sec,
                                            })
                                          }
                                          className="w-full rounded border border-slate-300 px-2 py-1 text-[11px] font-mono text-slate-900"
                                        />
                                      </div>
                                    </div>
                                    <div className="flex items-center justify-between text-[10px] text-slate-600">
                                      <span>
                                        Selected: <b>{vTrim.trim_start_sec.toFixed(1)}s</b> –{' '}
                                        <b>{vTrim.trim_end_sec.toFixed(1)}s</b> (
                                        {Math.max(0, vTrim.trim_end_sec - vTrim.trim_start_sec).toFixed(1)}s)
                                      </span>
                                      <button
                                        type="button"
                                        onClick={() => {
                                          const vidEl = videoRefs.current[item.id];
                                          if (vidEl) {
                                            vidEl.currentTime = vTrim.trim_start_sec;
                                            void vidEl.play().catch(() => {});
                                          }
                                        }}
                                        className="text-[10px] font-semibold text-slate-900 underline cursor-pointer"
                                      >
                                        Preview Range
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <p className="text-[10px] text-slate-500">
                                    Automatically slip-syncs the best detected jump/turn peaks to musical downbeats. Click any peak below to preview or lock onto it:
                                  </p>
                                )}

                                {item.dance_events.length > 0 && (
                                  <div className="flex flex-wrap gap-1 pt-0.5 max-h-16 overflow-y-auto">
                                    {item.dance_events.map((ev, i) => (
                                      <button
                                        key={i}
                                        type="button"
                                        onClick={() =>
                                          seekAndSelectVideoPortion(
                                            item.id,
                                            item.duration_sec,
                                            ev.timestamp_sec,
                                            1.8
                                          )
                                        }
                                        title="Click to preview & select this movement peak"
                                        className="px-2 py-0.5 rounded bg-slate-900 hover:bg-slate-700 text-white text-[10px] font-medium transition cursor-pointer"
                                      >
                                        {ev.move_type === 'jump_peak' ? 'Jump' : 'Turn'} @{' '}
                                        {ev.timestamp_sec.toFixed(1)}s
                                      </button>
                                    ))}
                                  </div>
                                )}
                              </div>
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
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
                      <label className="block text-xs font-semibold text-slate-700">
                        Choose from Built-In or Uploaded Dance Tracks ({musicTracks.length} tracks)
                      </label>
                      <div className="flex flex-wrap items-center gap-1">
                        {[
                          { id: 'all', label: 'All Genres' },
                          { id: 'ballet', label: '🩰 Ballet' },
                          { id: 'lyrical', label: '🎹 Lyrical & Neoclassical' },
                          { id: 'contemporary_jazz', label: '🎭 Contemporary & Jazz' },
                          { id: 'upbeat', label: '⚡ Pop, EDM & Hip-Hop' },
                        ].map((tab) => (
                          <button
                            key={tab.id}
                            type="button"
                            onClick={() => setMusicGenreFilter(tab.id)}
                            className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition ${
                              musicGenreFilter === tab.id
                                ? 'bg-slate-900 text-white'
                                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                            }`}
                          >
                            {tab.label}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
                      {musicTracks
                        .filter((track) => {
                          if (musicGenreFilter === 'all') return true;
                          const g = (track.genre || '').toLowerCase();
                          if (musicGenreFilter === 'ballet') return g.includes('ballet');
                          if (musicGenreFilter === 'lyrical')
                            return g.includes('lyrical') || g.includes('neoclassical');
                          if (musicGenreFilter === 'contemporary_jazz')
                            return g.includes('contemporary') || g.includes('jazz') || g.includes('broadway');
                          if (musicGenreFilter === 'upbeat')
                            return (
                              g.includes('edm') ||
                              g.includes('pop') ||
                              g.includes('hiphop') ||
                              g.includes('kpop')
                            );
                          return true;
                        })
                        .map((track) => {
                          const isSelected = track.track_id === selectedMusicId;
                          const isBallet = (track.genre || '').toLowerCase().includes('ballet');
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
                                  <div className="flex flex-wrap items-center gap-1.5">
                                    <span className="text-xs font-semibold text-slate-900">
                                      {track.title}
                                    </span>
                                    {track.is_generated && (
                                      <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-semibold">
                                        ✨ Gemini AI
                                      </span>
                                    )}
                                    {isBallet && (
                                      <span className="px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200 text-[10px] font-semibold">
                                        Ballet
                                      </span>
                                    )}
                                  </div>
                                  <div className="text-[11px] text-slate-500 mt-0.5">
                                    Tempo: <span className="font-semibold text-slate-700">{track.bpm} BPM</span> •{' '}
                                    Genre: <span className="font-medium text-slate-600">{track.genre.replace(/_/g, ' ')}</span> •{' '}
                                    {track.downbeat_times.length} Measure Downbeats •{' '}
                                    {track.sections.length} Sustained/Pause Windows
                                  </div>
                                </div>
                              </div>
                              <div className="flex items-center gap-2 shrink-0">
                                <span className="text-[11px] font-mono text-slate-500">
                                  {track.duration_sec.toFixed(0)}s
                                </span>
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedMusicId(track.track_id);
                                    setAutoPlayMusic(true);
                                  }}
                                  aria-label={`Preview ${track.title}`}
                                  className="w-7 h-7 rounded-full border border-slate-300 bg-white hover:bg-slate-100 flex items-center justify-center cursor-pointer"
                                >
                                  <Play className="w-3 h-3 ml-0.5 text-slate-800" />
                                </button>
                              </div>
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
                        Generate Custom AI Music Track (Gemini Lyria)
                      </label>
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={customMusicPrompt}
                          onChange={(e) => setCustomMusicPrompt(e.target.value)}
                          placeholder="e.g., Classical ballet waltz or lyrical piano"
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
                      <p className="text-[11px] text-slate-500 mt-1">
                        ✨ Automatically hints Gemini Lyria to weave{' '}
                        <span className="font-semibold text-slate-700">
                          {Math.max(
                            2,
                            matchedMedia.filter(
                              (m) => selectedMediaIds.has(m.id) && m.media_type === 'photo'
                            ).length || 3
                          )}{' '}
                          natural legato/rubato phrases
                        </span>{' '}
                        matching your selected photos.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Right 5 cols: Audio Player & Detected Musical Cues Summary */}
                <div className="lg:col-span-5 space-y-4 lg:border-l lg:border-slate-100 lg:pl-6">
                  <label className="block text-xs font-semibold text-slate-700">
                    Active Track Preview & Cue Structure
                  </label>
                  {activeCueMap && (
                    <MusicCuePreview
                      cueMap={activeCueMap}
                      targetDurationSec={targetDurationSec}
                      autoPlay={autoPlayMusic}
                      onAutoPlayConsumed={() => setAutoPlayMusic(false)}
                    />
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
                      const matchedMedia = session?.matched_media.find((m) => m.id === clip.media_id);
                      const maxVideoDur = matchedMedia?.duration_sec || 60;
                      const slotDuration = Math.max(0.8, Number((clip.timeline_end_sec - clip.timeline_start_sec).toFixed(2)));
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
                                  {!isPhoto && (
                                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200">
                                      Source: {clip.source_in_sec.toFixed(1)}s – {clip.source_out_sec.toFixed(1)}s
                                    </span>
                                  )}
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
                                  Photo Effect / Style
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
                              <div className="sm:col-span-2 space-y-1.5">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <label className="block text-[11px] font-medium text-slate-600">
                                    Video Portion (Source In / Out • Max {maxVideoDur.toFixed(1)}s)
                                  </label>
                                  <span className="text-[10px] text-slate-500">
                                    Slot length: {slotDuration.toFixed(1)}s
                                  </span>
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                  <div className="flex items-center gap-1.5 bg-white border border-slate-300 rounded-md px-2 py-1">
                                    <span className="text-[10px] text-slate-500 font-medium">In (s):</span>
                                    <input
                                      type="number"
                                      step="0.2"
                                      min={0}
                                      max={Math.max(0, maxVideoDur - 0.5)}
                                      value={clip.source_in_sec}
                                      onChange={(e) => {
                                        const newIn = Math.max(0, Number(e.target.value) || 0);
                                        const newOut = Number(Math.min(maxVideoDur, Math.max(newIn + 0.8, newIn + slotDuration)).toFixed(2));
                                        setTimelineClips((prev) => {
                                          const copy = [...prev];
                                          copy[idx] = {
                                            ...copy[idx],
                                            source_in_sec: Number(newIn.toFixed(2)),
                                            source_out_sec: newOut,
                                            sync_explanation: `Manual video portion [${newIn.toFixed(1)}s–${newOut.toFixed(1)}s] synced to musical cue.`,
                                          };
                                          return copy;
                                        });
                                      }}
                                      className="w-full text-xs font-mono text-slate-900 focus:outline-none"
                                    />
                                  </div>
                                  <div className="flex items-center gap-1.5 bg-white border border-slate-300 rounded-md px-2 py-1">
                                    <span className="text-[10px] text-slate-500 font-medium">Out (s):</span>
                                    <input
                                      type="number"
                                      step="0.2"
                                      min={0.5}
                                      max={maxVideoDur}
                                      value={clip.source_out_sec}
                                      onChange={(e) => {
                                        const newOut = Math.min(maxVideoDur, Math.max((clip.source_in_sec || 0) + 0.5, Number(e.target.value) || 1));
                                        setTimelineClips((prev) => {
                                          const copy = [...prev];
                                          copy[idx] = {
                                            ...copy[idx],
                                            source_out_sec: Number(newOut.toFixed(2)),
                                            sync_explanation: `Manual video portion [${clip.source_in_sec.toFixed(1)}s–${newOut.toFixed(1)}s] synced to musical cue.`,
                                          };
                                          return copy;
                                        });
                                      }}
                                      className="w-full text-xs font-mono text-slate-900 focus:outline-none"
                                    />
                                  </div>
                                </div>
                                {matchedMedia && matchedMedia.dance_events.length > 0 && (
                                  <div className="flex flex-wrap items-center gap-1 pt-0.5">
                                    <span className="text-[10px] text-slate-500">Auto-snap to AI Peak:</span>
                                    {matchedMedia.dance_events.slice(0, 6).map((ev, evIdx) => {
                                      const halfWin = Math.max(1.1, slotDuration / 2);
                                      const targetIn = Number(Math.max(0, Math.min(maxVideoDur - slotDuration, ev.timestamp_sec - halfWin)).toFixed(2));
                                      const targetOut = Number(Math.min(maxVideoDur, targetIn + slotDuration).toFixed(2));
                                      const isSelectedPeak = Math.abs(clip.source_in_sec - targetIn) < 0.35;
                                      return (
                                        <button
                                          key={evIdx}
                                          type="button"
                                          onClick={() => {
                                            setTimelineClips((prev) => {
                                              const copy = [...prev];
                                              copy[idx] = {
                                                ...copy[idx],
                                                source_in_sec: targetIn,
                                                source_out_sec: targetOut,
                                                matched_dance_move: ev.move_type,
                                                sync_explanation: `Synced ${ev.move_type === 'jump_peak' ? 'Jump Apex' : 'Turn Peak'} @ ${ev.timestamp_sec.toFixed(2)}s [${targetIn.toFixed(1)}s–${targetOut.toFixed(1)}s] to downbeat.`,
                                              };
                                              return copy;
                                            });
                                          }}
                                          className={`text-[10px] px-1.5 py-0.5 rounded border transition cursor-pointer ${
                                            isSelectedPeak
                                              ? 'bg-indigo-600 text-white border-indigo-600 font-semibold'
                                              : 'bg-white text-indigo-700 border-indigo-200 hover:bg-indigo-50'
                                          }`}
                                        >
                                          {ev.move_type === 'jump_peak' ? 'Jump' : 'Turn'} @ {ev.timestamp_sec.toFixed(1)}s
                                        </button>
                                      );
                                    })}
                                  </div>
                                )}
                              </div>
                            )}

                            <div>
                              <label className="block text-[11px] font-medium text-slate-600 mb-1">
                                Transition Style
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
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                          <FileText className="w-4 h-4 text-slate-700" />
                          Personalized Instagram Post Titles & Caption
                        </h3>
                        <p className="text-xs text-slate-500">
                          Grounded in your imported media metadata (dancer/routine filenames, styles, dates & camera context).
                        </p>
                      </div>
                      <button
                        onClick={() =>
                          copyToClipboard(
                            'all_post',
                            `${postCopy.post_headline}\n\n${displayedCaption}\n\n${postCopy.hashtags.join(' ')}`
                          )
                        }
                        className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shrink-0 transition"
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

                    {/* Personalized Media Metadata Context Used */}
                    {session && session.matched_media.length > 0 && (
                      <div className="p-3 rounded-lg bg-slate-50 border border-slate-200/80 space-y-1.5">
                        <div className="text-[11px] font-semibold text-slate-700">
                          Media Context Linked to This Post ({session.matched_media.length} items):
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {session.matched_media.slice(0, 6).map((m) => (
                            <span
                              key={m.id}
                              className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-700"
                            >
                              <b className="text-slate-900">{m.filename}</b>
                              {m.tags.length > 0 && (
                                <span className="text-slate-500">
                                  ({m.tags.slice(0, 2).join(', ')})
                                </span>
                              )}
                              {m.creation_time && (
                                <span className="text-slate-400">• {m.creation_time.split(' ')[0]}</span>
                              )}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Regenerate Post Copy with Custom Prompt */}
                    <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-2.5">
                      <label className="block text-xs font-semibold text-slate-800">
                        Regenerate Post Content with Custom Prompt
                      </label>
                      <div className="flex flex-col sm:flex-row gap-2">
                        <input
                          type="text"
                          value={postCopyPrompt}
                          onChange={(e) => setPostCopyPrompt(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              void handleRegeneratePostCopy();
                            }
                          }}
                          placeholder="e.g., Mention Lillian's contemporary solo 'In The Current', thank her choreographer, or make it short & witty..."
                          className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus:outline-none focus:border-slate-900"
                        />
                        <button
                          onClick={() => void handleRegeneratePostCopy()}
                          disabled={isRegeneratingPostCopy}
                          className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-xs font-semibold shrink-0 transition cursor-pointer"
                        >
                          <RefreshCw
                            className={`w-3.5 h-3.5 ${isRegeneratingPostCopy ? 'animate-spin' : ''}`}
                          />
                          {isRegeneratingPostCopy ? 'Regenerating...' : 'Regenerate Post'}
                        </button>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                        <span className="text-[10px] font-medium text-slate-500">Quick prompts:</span>
                        {[
                          "Highlight Lillian's contemporary solo 'In The Current' & stage poise",
                          'Short & punchy hype caption for Instagram Reels',
                          'Thank her dance teacher, choreographer & studio family',
                          'Playful & funny dance parent perspective',
                          'Bilingual English + 中文 stage storytelling',
                        ].map((presetPrompt) => (
                          <button
                            key={presetPrompt}
                            type="button"
                            onClick={() => void handleRegeneratePostCopy(presetPrompt)}
                            disabled={isRegeneratingPostCopy}
                            className="text-[10px] px-2 py-0.5 rounded-full border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 transition cursor-pointer"
                          >
                            {presetPrompt}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">
                          On-Screen Hook Text
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
                          Closing Line (last 2s)
                        </label>
                        <input
                          type="text"
                          value={postCopy.ending_call_to_action}
                          onChange={(e) =>
                            setPostCopy({ ...postCopy, ending_call_to_action: e.target.value })
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

                    <HookStyleStudio
                      postCopy={postCopy}
                      setPostCopy={setPostCopy}
                      sessionId={session?.session_id}
                      onApply={() => void handleApplyTimelineAdjustments(true)}
                      isRendering={isUpdatingTimeline}
                    />

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
                        className="w-full rounded-lg border border-slate-300 bg-white p-3 text-xs text-slate-800 leading-relaxed"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                        Personalized Tags & Hashtags
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
                  placeholder="Paste OAuth access token..."
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
