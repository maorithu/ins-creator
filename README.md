# Ins-Creator — AI Dance Instagram Reel & Post Studio

An automated workflow & interactive studio for creating beat-synced Instagram Reels, attractive titles/captions, and editable **CapCut Desktop Draft** / **FCPXML** projects from photos and videos of dance rehearsals, training sessions, and competitions.

## Key Features
1. **Photo & Video Search Query + Google Photos Ingestion**:
   - Connect directly to your **Google Photos Picker API / Library** or search local folders/uploads using natural language queries (e.g., *"daughter contemporary competition split leaps and turns"*).
   - Automatic deduplication, Laplacian sharpness filtering, aesthetic scoring, and focal bounding box detection.
2. **Dance Kinematics & Pose Analysis (`backend/services/dance_analyzer.py`)**:
   - Detects **Jump Peaks (Apex frames)** via vertical trajectory extrema and **Turns / Pirouettes** via horizontal rotational optical flow and width oscillation.
3. **Music Generation, Upload & Beat/Cue Extraction (`backend/services/audio_analyzer.py` & `music_generator.py`)**:
   - Extracts **BPM**, **Beat Grid**, **Measure Downbeats (1-count)**, **Sustained Harmonic Notes**, and **Musical Pauses/Breaths** using **Librosa**.
   - Includes 4 built-in multi-section dance tracks (*Competition Pop/EDM*, *Lyrical Piano & Strings*, *Studio Hip-Hop Hustle*, *Contemporary Dramatic Build*), custom MP3/WAV upload, and AI Music generation from prompts.
4. **6 Curated Dance Styles + Free-Form Supplemental Directions (`backend/services/style_presets.py`)**:
   - Choose from *Competition Stage Glory*, *Lyrical & Graceful Flow*, *Studio Rehearsal: Grit & Glow*, *Technique & Progress Spotlight*, *High-Energy 8-Count Hype*, or *Proud Parent Storyteller*, and steer any session with custom text directions.
5. **Choreographic Beat-Sync Timeline Engine (`backend/services/timeline_composer.py`)**:
   - **Slip-syncs video clips** so jump peaks and turn peaks land directly on musical downbeats (with optional speed ramping).
   - **Inserts curated photos** during sustained notes and musical pauses with **Ken Burns** pan/zoom and beat-pulse visual effects.
6. **Attractive Titles, Multi-Style Captions & Hashtags (`backend/services/gemini_service.py`)**:
   - Generates an on-screen Reel Title Hook, post headline, 3 caption variants (*Storytelling*, *Short & Hype*, *Technique Focus*), and curated dance hashtags.
7. **Direct 9:16 MP4 Render & Interactive CapCut / FCPXML Export (`backend/services/exporters/`)**:
   - Renders ready-to-post 9:16 vertical MP4 videos (`mp4_renderer.py`).
   - Exports and auto-installs editable **CapCut Desktop Drafts** (`draft_content.json` + `draft_meta_info.json` in `~/Movies/CapCut/User Data/Projects/com.lveditor.draft/`) and **FCPXML** timelines (`fcpxml_exporter.py`).

## Quick Start
```bash
./scripts/start.sh
```
Then open **http://127.0.0.1:8000** in your browser.

## Running Tests
```bash
PYTHONPATH=. ./backend/.venv/bin/pytest backend/tests/test_workflow.py -v
```
