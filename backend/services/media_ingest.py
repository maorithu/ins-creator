from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional
import httpx

from backend.config import MEDIA_CACHE_DIR, SAMPLE_DATA_DIR, UPLOADS_DIR, settings
from backend.models.schemas import EventCategory, MediaItem, MediaType
from backend.services.dance_analyzer import (
    analyze_photo_item,
    analyze_video_dance_kinematics,
)
from backend.services.sample_generator import ensure_sample_dance_dataset
from backend.services import progress

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi"}
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


_ANALYZED_MEDIA_CACHE: Dict[str, MediaItem] = {}


def analysis_service_label(is_video: bool) -> str:
    """Human-readable description of which engines analyze a media item."""
    if is_video:
        return "OpenCV motion kinematics (jump & turn peaks) + EXIF"
    label = "Pillow EXIF + OpenCV sharpness & focal-point detection"
    if settings.gemini_api_key and len(settings.gemini_api_key.strip()) >= 20:
        label += f" + Gemini Vision ({settings.gemini_model})"
    return label


def _report_item(idx: int, total: int, verb: str, filename: str, is_video: bool, service: Optional[str] = None, half: float = 0.0) -> None:
    kind = "video" if is_video else "photo"
    progress.update(
        100.0 * (idx + half) / max(1, total),
        f"{verb} {kind} {idx + 1}/{total}: {filename}",
        service=service or analysis_service_label(is_video),
    )


def _infer_event_category_from_text(text: str) -> EventCategory:
    t = text.lower()
    if "rehearsal" in t or "studio" in t or "practice" in t:
        return EventCategory.REHEARSAL
    if "training" in t or "technique" in t or "class" in t or "acro" in t:
        return EventCategory.TRAINING
    if "competition" in t or "stage" in t or "award" in t or "solo" in t or "finale" in t:
        return EventCategory.COMPETITION
    if "showcase" in t or "recital" in t:
        return EventCategory.SHOWCASE
    return EventCategory.GENERAL


def _score_query_match(query: str, item: MediaItem) -> float:
    """Computes semantic & keyword relevance score [0.25..1.0] between user's search query and media item."""
    if not query or not query.strip():
        return 0.90

    q_tokens = [
        tok
        for tok in re.split(r"[^a-z0-9]+", query.lower())
        if len(tok) > 2 and tok not in {"the", "and", "from", "with", "for", "her"}
    ]
    if not q_tokens:
        return 0.90

    searchable_blob = " ".join(
        [
            item.filename.lower(),
            item.semantic_caption.lower(),
            item.event_category.value.lower(),
            " ".join(t.lower() for t in item.tags),
            " ".join(ev.move_type.value.lower() for ev in item.dance_events),
        ]
    )

    hits = 0.0
    for tok in q_tokens:
        if tok in searchable_blob:
            hits += 1.0
        elif tok in {"leap", "leaps", "jump", "jumps", "jete"} and "jump" in searchable_blob:
            hits += 0.95
        elif tok in {"turn", "turns", "spin", "spins", "pirouette"} and "turn" in searchable_blob:
            hits += 0.95
        elif tok in {"dance", "dancing", "daughter", "girl"}:
            hits += 0.75

    raw_ratio = hits / float(len(q_tokens))
    return round(min(1.0, max(0.35, 0.40 + 0.60 * raw_ratio)), 3)


class GooglePhotosClient:
    """
    Client supporting:
    1. Google Photos Picker API (2025+ standard: `https://photospicker.googleapis.com/v1/sessions`)
    2. Google Photos Library API search (`https://photoslibrary.googleapis.com/v1/mediaItems:search`)
    """

    def __init__(self, access_token: Optional[str] = None) -> None:
        self.access_token = access_token or settings.google_photos_access_token

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token and len(self.access_token.strip()) > 10)

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def create_picker_session(self) -> Dict[str, object]:
        """Creates an interactive Google Photos Picker session, refreshing OAuth token if expired."""
        if not self.is_configured:
            return {
                "configured": False,
                "mode": "demo_or_token_required",
                "message": "Please sign in with Google first to open the Google Photos Picker.",
            }
        try:
            resp = httpx.post(
                "https://photospicker.googleapis.com/v1/sessions",
                headers=self._headers(),
                json={},
                timeout=15.0,
            )
            if resp.status_code == 401:
                refreshed = settings.refresh_google_access_token_if_needed()
                if refreshed:
                    self.access_token = refreshed
                    resp = httpx.post(
                        "https://photospicker.googleapis.com/v1/sessions",
                        headers=self._headers(),
                        json={},
                        timeout=15.0,
                    )

            if resp.status_code == 200:
                data = resp.json()
                session_id = str(data.get("id") or "")
                if session_id:
                    settings.save_oauth_tokens(last_picker_session_id=session_id)
                return {
                    "configured": True,
                    "sessionId": session_id,
                    "pickerUri": data.get("pickerUri"),
                    "pollingConfig": data.get("pollingConfig", {}),
                }
            return {
                "configured": False,
                "error": f"Picker API returned status {resp.status_code}: {resp.text[:250]}",
            }
        except Exception as exc:
            return {"configured": False, "error": str(exc)}

    def get_picker_session_status(self, picker_session_id: Optional[str] = None) -> Dict[str, object]:
        """Checks whether the user has finished selecting media (`mediaItemsSet == True`) in the Picker session."""
        session_id = picker_session_id or settings.last_picker_session_id
        if not self.is_configured or not session_id:
            return {"sessionId": session_id, "mediaItemsSet": False, "ready": False}

        try:
            resp = httpx.get(
                f"https://photospicker.googleapis.com/v1/sessions/{session_id}",
                headers=self._headers(),
                timeout=15.0,
            )
            if resp.status_code == 401:
                refreshed = settings.refresh_google_access_token_if_needed()
                if refreshed:
                    self.access_token = refreshed
                    resp = httpx.get(
                        f"https://photospicker.googleapis.com/v1/sessions/{session_id}",
                        headers=self._headers(),
                        timeout=15.0,
                    )
            if resp.status_code == 200:
                data = resp.json()
                items_set = bool(data.get("mediaItemsSet", False))
                return {
                    "sessionId": session_id,
                    "mediaItemsSet": items_set,
                    "pickerUri": data.get("pickerUri"),
                }
            return {"sessionId": session_id, "mediaItemsSet": False, "error": resp.text[:200]}
        except Exception as exc:
            return {"sessionId": session_id, "mediaItemsSet": False, "error": str(exc)}

    def fetch_media_by_query_or_session(
        self, query: str = "", picker_session_id: Optional[str] = None, max_items: int = 25
    ) -> List[MediaItem]:
        """
        Fetches photos and videos from the active Google Photos Picker session (or Library API),
        downloads them into `MEDIA_CACHE_DIR`, and runs the dance CV analyzer on each item.
        """
        if not self.is_configured:
            return []

        active_session_id = picker_session_id or settings.last_picker_session_id
        raw_items: List[Dict[str, object]] = []
        progress.update(2, "Fetching the list of items you picked", service="Google Photos Picker API")

        try:
            if active_session_id:
                resp = httpx.get(
                    "https://photospicker.googleapis.com/v1/mediaItems",
                    headers=self._headers(),
                    params={"sessionId": active_session_id, "pageSize": max_items},
                    timeout=25.0,
                )
                if resp.status_code == 401:
                    refreshed = settings.refresh_google_access_token_if_needed()
                    if refreshed:
                        self.access_token = refreshed
                        resp = httpx.get(
                            "https://photospicker.googleapis.com/v1/mediaItems",
                            headers=self._headers(),
                            params={"sessionId": active_session_id, "pageSize": max_items},
                            timeout=25.0,
                        )
                if resp.status_code == 200:
                    raw_items = resp.json().get("mediaItems", [])
            if not raw_items:
                # Fallback to Google Photos Library list if Picker session had no items
                resp = httpx.get(
                    "https://photoslibrary.googleapis.com/v1/mediaItems",
                    headers=self._headers(),
                    params={"pageSize": max_items},
                    timeout=20.0,
                )
                if resp.status_code == 200:
                    raw_items = resp.json().get("mediaItems", [])
        except Exception:
            return []

        manifest_path = MEDIA_CACHE_DIR / "gp_manifest.json"
        gp_manifest: Dict[str, Dict[str, str]] = {}
        if manifest_path.exists():
            try:
                import json
                gp_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                gp_manifest = {}

        ingested: List[MediaItem] = []
        batch = raw_items[:max_items]
        total = len(batch)
        for idx, entry in enumerate(batch):
            if not isinstance(entry, dict):
                continue
            media_file = entry.get("mediaFile", entry)
            if not isinstance(media_file, dict):
                media_file = entry

            item_id = str(entry.get("id") or hashlib.md5(str(entry).encode()).hexdigest()[:10])
            base_url = str(media_file.get("baseUrl") or entry.get("baseUrl") or "")
            mime_type = str(media_file.get("mimeType") or entry.get("mimeType") or "").lower()
            entry_type = str(entry.get("type") or "").upper()
            create_time_raw = str(entry.get("createTime") or media_file.get("createTime") or "")
            filename = str(
                media_file.get("filename")
                or entry.get("filename")
                or f"gphoto_{item_id[:8]}"
            )

            if not base_url:
                continue

            is_video = (
                mime_type.startswith("video")
                or entry_type == "VIDEO"
                or Path(filename).suffix.lower() in VIDEO_EXTENSIONS
            )
            download_url = f"{base_url}=dv" if is_video else f"{base_url}=d"
            ext = ".mp4" if is_video else ".jpg"
            if not Path(filename).suffix:
                filename = f"{filename}{ext}"
            local_path = MEDIA_CACHE_DIR / f"gp_{item_id[:16]}{ext}"

            if not local_path.exists() or local_path.stat().st_size < 500:
                _report_item(idx, total, "Downloading", filename, is_video, service="Google Photos Picker API (media download)")
                try:
                    # Try authenticated download first (required by Picker API baseUrls), then unauthenticated fallback
                    dl = httpx.get(
                        download_url,
                        headers=self._headers(),
                        follow_redirects=True,
                        timeout=45.0,
                    )
                    if dl.status_code != 200 or len(dl.content) < 500:
                        dl = httpx.get(download_url, follow_redirects=True, timeout=45.0)
                    if dl.status_code == 200 and len(dl.content) >= 500:
                        local_path.write_bytes(dl.content)
                    else:
                        continue
                except Exception:
                    continue

            cache_id = f"gp_{item_id[:16]}"
            gp_manifest[cache_id] = {
                "filename": filename,
                "createTime": create_time_raw[:16].replace("T", " ") if create_time_raw else "",
            }

            if cache_id not in _ANALYZED_MEDIA_CACHE:
                media_obj = MediaItem(
                    id=cache_id,
                    filename=filename,
                    filepath=str(local_path),
                    url=f"/static/cache/{local_path.name}",
                    media_type=MediaType.VIDEO if is_video else MediaType.PHOTO,
                    event_category=_infer_event_category_from_text(f"{filename} {query}"),
                    tags=["google_photos", "dance"],
                    semantic_caption=f"Imported from Google Photos ({filename})",
                    source="google_photos",
                    creation_time=gp_manifest[cache_id]["createTime"] or None,
                )
                _report_item(idx, total, "Analyzing", filename, is_video, half=0.5)
                if is_video:
                    media_obj = analyze_video_dance_kinematics(media_obj)
                else:
                    media_obj = analyze_photo_item(media_obj)
                _ANALYZED_MEDIA_CACHE[cache_id] = media_obj

            ingested.append(_ANALYZED_MEDIA_CACHE[cache_id].model_copy(deep=True))

        if gp_manifest:
            try:
                import json
                manifest_path.write_text(json.dumps(gp_manifest, indent=2), encoding="utf-8")
            except Exception:
                pass

        return ingested


def list_imported_google_photos() -> List[MediaItem]:
    """Returns any previously downloaded Google Photos media items stored in MEDIA_CACHE_DIR."""
    manifest_path = MEDIA_CACHE_DIR / "gp_manifest.json"
    gp_manifest: Dict[str, Dict[str, str]] = {}
    if manifest_path.exists():
        try:
            import json
            gp_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            gp_manifest = {}

    results: List[MediaItem] = []
    gp_files = [
        f
        for f in sorted(MEDIA_CACHE_DIR.glob("gp_*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if f.is_file() and f.suffix.lower() != ".json" and f.stat().st_size >= 500
    ]
    for idx, fpath in enumerate(gp_files):
        cache_id = fpath.stem
        meta = gp_manifest.get(cache_id, {})
        orig_filename = meta.get("filename") or fpath.name
        orig_create_time = meta.get("createTime") or None

        if cache_id not in _ANALYZED_MEDIA_CACHE:
            is_video = fpath.suffix.lower() in VIDEO_EXTENSIONS
            item = MediaItem(
                id=cache_id,
                filename=orig_filename,
                filepath=str(fpath),
                url=f"/static/cache/{fpath.name}",
                media_type=MediaType.VIDEO if is_video else MediaType.PHOTO,
                event_category=_infer_event_category_from_text(orig_filename),
                tags=["google_photos", "dance"],
                semantic_caption=f"Imported from Google Photos ({orig_filename})",
                source="google_photos",
                creation_time=orig_create_time,
            )
            _report_item(idx, len(gp_files), "Analyzing", orig_filename, is_video)
            if is_video:
                item = analyze_video_dance_kinematics(item)
            else:
                item = analyze_photo_item(item)
            _ANALYZED_MEDIA_CACHE[cache_id] = item
        results.append(_ANALYZED_MEDIA_CACHE[cache_id].model_copy(deep=True))
    return results


def load_and_analyze_sample_dataset(query: str = "") -> List[MediaItem]:
    """Loads, analyzes (caching CV kinematics), and scores the built-in sample dance event media."""
    manifest = ensure_sample_dance_dataset()
    items: List[MediaItem] = []

    for idx, spec in enumerate(manifest):
        item_id = str(spec["id"])
        if item_id not in _ANALYZED_MEDIA_CACHE:
            filename = str(spec["filename"])
            fpath = SAMPLE_DATA_DIR / filename
            mtype = MediaType.VIDEO if spec["media_type"] == "video" else MediaType.PHOTO
            item = MediaItem(
                id=item_id,
                filename=filename,
                filepath=str(fpath),
                url=f"/static/sample/{filename}",
                media_type=mtype,
                event_category=EventCategory(str(spec["event_category"])),
                tags=list(spec["tags"]),  # type: ignore
                semantic_caption=str(spec["semantic_caption"]),
                source="sample",
            )
            _report_item(idx, len(manifest), "Analyzing demo", filename, mtype == MediaType.VIDEO)
            if mtype == MediaType.VIDEO:
                item = analyze_video_dance_kinematics(item)
            else:
                item = analyze_photo_item(item)
            _ANALYZED_MEDIA_CACHE[item_id] = item

        cached = _ANALYZED_MEDIA_CACHE[item_id].model_copy(deep=True)
        cached.query_match_score = _score_query_match(query, cached)
        items.append(cached)

    return items


def scan_local_directory(folder_path: str, query: str = "") -> List[MediaItem]:
    """Scans a user-specified local directory or `UPLOADS_DIR` for dance photos and videos."""
    root = Path(folder_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return []

    found_files: List[Path] = []
    for p in sorted(root.iterdir()):
        if p.is_file() and p.suffix.lower() in (VIDEO_EXTENSIONS | PHOTO_EXTENSIONS):
            found_files.append(p)

    results: List[MediaItem] = []
    batch_files = found_files[:24]
    for idx, fpath in enumerate(batch_files):
        cache_key = f"local_{hashlib.md5(str(fpath).encode()).hexdigest()[:10]}"
        if cache_key not in _ANALYZED_MEDIA_CACHE:
            ext = fpath.suffix.lower()
            is_video = ext in VIDEO_EXTENSIONS
            # Determine static serving URL
            if fpath.parent == UPLOADS_DIR:
                url = f"/static/uploads/{fpath.name}"
            elif fpath.parent == SAMPLE_DATA_DIR:
                url = f"/static/sample/{fpath.name}"
            else:
                # Copy or symlink into MEDIA_CACHE_DIR so FastAPI can stream it seamlessly
                cached_file = MEDIA_CACHE_DIR / f"{cache_key}_{fpath.name}"
                if not cached_file.exists():
                    cached_file.write_bytes(fpath.read_bytes())
                url = f"/static/cache/{cached_file.name}"

            item = MediaItem(
                id=cache_key,
                filename=fpath.name,
                filepath=str(fpath),
                url=url,
                media_type=MediaType.VIDEO if is_video else MediaType.PHOTO,
                event_category=_infer_event_category_from_text(f"{fpath.name} {query}"),
                tags=["local", is_video and "video" or "photo", "dance"],
                semantic_caption=f"Dance media item {fpath.stem.replace('_', ' ')}",
                source="upload" if fpath.parent == UPLOADS_DIR else "local",
            )
            _report_item(idx, len(batch_files), "Analyzing", fpath.name, is_video)
            if is_video:
                item = analyze_video_dance_kinematics(item)
            else:
                item = analyze_photo_item(item)
            _ANALYZED_MEDIA_CACHE[cache_key] = item

        cloned = _ANALYZED_MEDIA_CACHE[cache_key].model_copy(deep=True)
        cloned.query_match_score = _score_query_match(query, cloned)
        results.append(cloned)

    return results


def search_and_ingest_media(
    query: str,
    media_source: str = "auto",
    local_folder_path: Optional[str] = None,
    google_photos_session_id: Optional[str] = None,
    google_access_token: Optional[str] = None,
) -> List[MediaItem]:
    """
    Unified entry point:
    1. Checks Google Photos if `media_source in ('google_photos', 'auto')` and token is configured
    2. Checks user-uploaded media in `UPLOADS_DIR` or `local_folder_path`
    3. Combines or falls back to the sample dance rehearsal/training/competition dataset
    4. Ranks by query relevance + aesthetic & sharpness score
    """
    candidates: List[MediaItem] = []

    if media_source in ("google_photos", "auto"):
        gp_client = GooglePhotosClient(access_token=google_access_token)
        if gp_client.is_configured:
            with progress.scope(0, 50):
                gp_items = gp_client.fetch_media_by_query_or_session(
                    query=query, picker_session_id=google_photos_session_id
                )
            candidates.extend(gp_items)
        # Also include any already-imported Google Photos items cached on disk
        existing_gp_ids = {c.id for c in candidates}
        with progress.scope(50, 70):
            cached_gp_items = list_imported_google_photos()
        for cached_gp in cached_gp_items:
            if cached_gp.id not in existing_gp_ids:
                candidates.append(cached_gp)

    if local_folder_path:
        candidates.extend(scan_local_directory(local_folder_path, query=query))

    # Always include any files uploaded via the web studio
    with progress.scope(70, 90):
        uploaded_items = scan_local_directory(str(UPLOADS_DIR), query=query)
    existing_ids = {c.id for c in candidates}
    for u in uploaded_items:
        if u.id not in existing_ids:
            candidates.append(u)
            existing_ids.add(u.id)

    # Only include sample dataset when explicitly requested or when no user media has been imported/uploaded yet
    if media_source == "sample" or (media_source == "auto" and len(candidates) == 0):
        with progress.scope(90, 100):
            sample_items = load_and_analyze_sample_dataset(query=query)
        for s in sample_items:
            if s.id not in existing_ids:
                candidates.append(s)

    candidates.sort(
        key=lambda m: (m.query_match_score * 0.65 + m.aesthetic_score * 0.35),
        reverse=True,
    )
    return candidates
