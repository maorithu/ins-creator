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
        self.ai_music_api_key: Optional[str] = os.getenv("AI_MUSIC_API_KEY") or os.getenv("ELEVENLABS_API_KEY")
        self.ai_music_provider: str = os.getenv("AI_MUSIC_PROVIDER", "procedural_plus_api")
        self.local_photos_dirs: list[str] = [
            str(SAMPLE_DATA_DIR),
            str(UPLOADS_DIR),
            str(Path.home() / "Pictures"),
        ]

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
