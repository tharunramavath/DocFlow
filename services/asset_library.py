"""
services/asset_library.py
==========================
General-purpose file library for supporting material that rides alongside a
campaign — event photos or a highlight video, a briefing audio clip, extra
attendee spreadsheets, sponsor documents, and so on. These are stored
separately from the certificate-specific assets (fonts, template, logo,
signature) that ``services.image_converter`` and ``services.config_manager``
already manage.

Files are auto-sorted into a category subfolder by extension purely for tidy
browsing; nothing here is business logic the certificate/email pipeline
depends on.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from services.config_manager import MEDIA_CATEGORY_DIRS

# Extension → category, and a human label + icon per category for the UI.
_EXTENSION_MAP: Dict[str, str] = {
    # images
    "png": "image", "jpg": "image", "jpeg": "image", "gif": "image",
    "webp": "image", "bmp": "image", "svg": "image", "heic": "image",
    # video
    "mp4": "video", "mov": "video", "webm": "video", "avi": "video",
    "mkv": "video", "m4v": "video",
    # audio
    "mp3": "audio", "wav": "audio", "m4a": "audio", "ogg": "audio",
    "aac": "audio", "flac": "audio",
    # spreadsheets
    "xlsx": "spreadsheet", "xls": "spreadsheet", "csv": "spreadsheet",
    "tsv": "spreadsheet",
    # documents
    "pdf": "document", "docx": "document", "doc": "document",
    "pptx": "document", "txt": "document",
}

CATEGORY_LABELS = {
    "image": ("🖼️", "Images"),
    "video": ("🎬", "Videos"),
    "audio": ("🎵", "Audio"),
    "spreadsheet": ("📊", "Spreadsheets"),
    "document": ("📄", "Documents"),
    "other": ("📦", "Other"),
}

# A generous default allow-list. "other" catches anything not recognised
# above rather than rejecting the upload outright.
ALL_EXTENSIONS = sorted(_EXTENSION_MAP.keys())


def categorize(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    return _EXTENSION_MAP.get(ext, "other")


@dataclass
class MediaAsset:
    path: Path
    category: str
    size_bytes: int
    modified: float

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def size_human(self) -> str:
        size = float(self.size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"


def save_media(uploaded_file, category: str | None = None) -> MediaAsset:
    """Save an uploaded file into its category folder (auto-detected from the
    filename if ``category`` isn't given) and return its MediaAsset record."""
    cat = category or categorize(uploaded_file.name)
    if cat not in MEDIA_CATEGORY_DIRS:
        cat = "other"
    dest_dir = MEDIA_CATEGORY_DIRS[cat]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / uploaded_file.name

    # Avoid clobbering an existing file with the same name.
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        dest = dest_dir / f"{stem}_{int(time.time())}{suffix}"

    with open(dest, "wb") as f:
        f.write(uploaded_file.getvalue())

    stat = dest.stat()
    return MediaAsset(path=dest, category=cat, size_bytes=stat.st_size, modified=stat.st_mtime)


def list_media(category: str | None = None) -> List[MediaAsset]:
    """List all stored media, optionally filtered to one category, newest first."""
    assets: List[MediaAsset] = []
    for cat, d in (
        [(category, MEDIA_CATEGORY_DIRS[category])] if category
        else MEDIA_CATEGORY_DIRS.items()
    ):
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.is_file() and not f.name.startswith("."):
                stat = f.stat()
                assets.append(MediaAsset(path=f, category=cat, size_bytes=stat.st_size, modified=stat.st_mtime))
    assets.sort(key=lambda a: a.modified, reverse=True)
    return assets


def delete_media(path: Path) -> None:
    p = Path(path)
    if p.exists() and p.is_file():
        p.unlink()


def total_size() -> int:
    return sum(a.size_bytes for a in list_media())
