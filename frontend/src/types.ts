export interface DanceMovementEvent {
  move_type: 'jump_peak' | 'turn_spin' | 'pose_hold' | 'high_energy' | 'graceful_flow';
  timestamp_sec: number;
  start_sec: number;
  end_sec: number;
  confidence: number;
  intensity_score: number;
  description: string;
}

export interface BoundingBoxCenter {
  center_x: number;
  center_y: number;
  box_width: number;
  box_height: number;
}

export interface MediaItem {
  id: string;
  filename: string;
  filepath: string;
  url: string;
  thumbnail_url?: string;
  media_type: 'video' | 'photo';
  width: number;
  height: number;
  duration_sec: number;
  creation_time?: string | null;
  camera_model?: string | null;
  event_category: string;
  tags: string[];
  semantic_caption: string;
  sharpness_score: number;
  aesthetic_score: number;
  energy_curve: number[];
  dance_events: DanceMovementEvent[];
  focal_point: BoundingBoxCenter;
  source: string;
  query_match_score: number;
}

export interface AudioSectionCue {
  cue_type: 'sustained_note' | 'pause' | 'drop_build' | 'chorus_peak' | string;
  start_sec: number;
  end_sec: number;
  duration_sec: number;
  intensity: number;
  description: string;
}

export interface AudioCueMap {
  track_id: string;
  title: string;
  filepath: string;
  url: string;
  duration_sec: number;
  bpm: number;
  beat_times: number[];
  downbeat_times: number[];
  onset_peaks: number[];
  sections: AudioSectionCue[];
  energy_envelope: number[];
  harmonic_ratio_envelope: number[];
  genre: string;
  is_generated: boolean;
}

export interface StylePreset {
  id: string;
  name: string;
  tagline: string;
  description: string;
  event_focus: string;
  default_music_genre: string;
  target_duration_sec: number;
  video_to_photo_ratio: number;
  cut_pacing: string;
  preferred_photo_effects: string[];
  preferred_transitions: string[];
  color_grade_preset: string;
  speed_ramp_on_peaks: boolean;
  caption_tone: string;
  badge_color: string;
}

export interface TimelineClip {
  clip_id: string;
  index: number;
  media_id: string;
  filename: string;
  media_type: 'video' | 'photo';
  media_url: string;
  timeline_start_sec: number;
  timeline_end_sec: number;
  duration_sec: number;
  source_in_sec: number;
  source_out_sec: number;
  playback_speed: number;
  speed_ramp_curve?: string | null;
  synced_cue_type: string;
  synced_beat_timestamp?: number | null;
  matched_dance_move?: string | null;
  matched_move_source_sec?: number | null;
  sync_explanation: string;
  photo_effect?: string | null;
  transition_in: string;
  text_overlay?: string | null;
  focal_point: BoundingBoxCenter;
}

export interface InstagramPostCopy {
  hook_title_overlay: string;
  ending_call_to_action: string;
  post_headline: string;
  caption_primary: string;
  caption_alternatives: { label: string; text: string }[];
  hashtags: string[];
  music_credit_note: string;
}

export interface ExportArtifactInfo {
  mp4_url?: string | null;
  mp4_filepath?: string | null;
  capcut_draft_path?: string | null;
  capcut_zip_url?: string | null;
  capcut_installed_to_app: boolean;
  fcpxml_url?: string | null;
  fcpxml_filepath?: string | null;
  last_rendered_at?: string | null;
}

export interface WorkflowSession {
  session_id: string;
  created_at: string;
  search_query: string;
  event_category: string;
  style_preset_id: string;
  supplemental_directions: string;
  target_duration_sec: number;
  media_source: string;
  matched_media: MediaItem[];
  audio_cue_map?: AudioCueMap | null;
  timeline_clips: TimelineClip[];
  post_copy?: InstagramPostCopy | null;
  exports: ExportArtifactInfo;
  color_grade: string;
}
