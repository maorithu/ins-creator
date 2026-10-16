from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MEDIA_CACHE_DIR = DATA_DIR / "media_cache"
UPLOADS_DIR = DATA_DIR / "uploads"
MUSIC_DIR = DATA_DIR / "music"
SESSIONS_DIR = DATA_DIR / "sessions"
EXPORTS_DIR = DATA_DIR / "exports"
SAMPLE_DATA_DIR = DATA_DIR / "sample_dance_event"

for _d in [
    DATA_DIR,
    MEDIA_CACHE_DIR,
    UPLOADS_DIR,
    MUSIC_DIR,
    SESSIONS_DIR,
    EXPORTS_DIR,
    SAMPLE_DATA_DIR,
]:
    _d.mkdir(parents=True, exist_ok=True)


class Settings:
    """Application settings loaded from environment variables or runtime config."""

    def __init__(self) -> None:
        self.gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.google_client_id: Optional[str] = os.getenv("GOOGLE_CLIENT_ID")
        self.google_client_secret: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET")
        self.google_photos_access_token: Optional[str] = os.getenv("GOOGLE_PHOTOS_ACCESS_TOKEN")
        self.google_photos_refresh_token: Optional[str] = os.getenv("GOOGLE_PHOTOS_REFRESH_TOKEN")
        self.last_picker_session_id: Optional[str] = None
        self.ai_music_api_key: Optional[str] = os.getenv("AI_MUSIC_API_KEY") or os.getenv("ELEVENLABS_API_KEY")
        self.ai_music_provider: str = os.getenv("AI_MUSIC_PROVIDER", "procedural_plus_api")
        self.local_photos_dirs: list[str] = [
            str(SAMPLE_DATA_DIR),
            str(UPLOADS_DIR),
            str(Path.home() / "Pictures"),
        ]
        self._load_persisted_tokens()

    @property
    def oauth_tokens_file(self) -> Path:
        return DATA_DIR / "google_oauth_tokens.json"

    def _load_persisted_tokens(self) -> None:
        if self.oauth_tokens_file.exists():
            try:
                import json

                data = json.loads(self.oauth_tokens_file.read_text(encoding="utf-8"))
                if data.get("access_token") and not self.google_photos_access_token:
                    self.google_photos_access_token = data["access_token"]
                if data.get("refresh_token") and not self.google_photos_refresh_token:
                    self.google_photos_refresh_token = data["refresh_token"]
                if data.get("client_id") and not self.google_client_id:
                    self.google_client_id = data["client_id"]
                if data.get("client_secret") and not self.google_client_secret:
                    self.google_client_secret = data["client_secret"]
                if data.get("last_picker_session_id"):
                    self.last_picker_session_id = data["last_picker_session_id"]
            except Exception:
                pass

    def save_oauth_tokens(
        self,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        last_picker_session_id: Optional[str] = None,
    ) -> None:
        import json

        if access_token:
            self.google_photos_access_token = access_token
        if refresh_token:
            self.google_photos_refresh_token = refresh_token
        if client_id:
            self.google_client_id = client_id
        if client_secret:
            self.google_client_secret = client_secret
        if last_picker_session_id:
            self.last_picker_session_id = last_picker_session_id

        payload = {
            "access_token": self.google_photos_access_token,
            "refresh_token": self.google_photos_refresh_token,
            "client_id": self.google_client_id,
            "client_secret": self.google_client_secret,
            "last_picker_session_id": self.last_picker_session_id,
        }
        self.oauth_tokens_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def refresh_google_access_token_if_needed(self) -> Optional[str]:
        """Uses the stored refresh_token to obtain a fresh Google OAuth access_token."""
        if not self.google_photos_refresh_token or not self.google_client_id or not self.google_client_secret:
            return self.google_photos_access_token
        try:
            import httpx

            resp = httpx.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.google_client_id,
                    "client_secret": self.google_client_secret,
                    "refresh_token": self.google_photos_refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=15.0,
            )
            if resp.status_code == 200:
                new_token = resp.json().get("access_token")
                if new_token:
                    self.save_oauth_tokens(access_token=new_token)
                    return new_token
        except Exception:
            pass
        return self.google_photos_access_token

    @property
    def capcut_drafts_dir(self) -> Path:
        """Detect macOS CapCut Desktop Drafts folder or fallback to standard path."""
        candidates = [
            Path.home() / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
            Path.home()
            / "Library"
            / "Containers"
            / "com.lemon.lvoverseas"
            / "Data"
            / "Movies"
            / "CapCut"
            / "User Data"
            / "Projects"
            / "com.lveditor.draft",
        ]
        for c in candidates:
            if c.exists():
                return c
        return candidates[0]


settings = Settings()
