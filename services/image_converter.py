"""
services/image_converter.py
===========================
Normalises an uploaded certificate template to PNG.

Accepts PNG, JPG, JPEG and PDF. Anything that is not already a PNG is
converted internally:

    - JPG / JPEG      -> re-encoded as PNG
    - PDF             -> first page rasterised to PNG at high DPI (PyMuPDF)

A stable, content-addressed filename is used so re-uploading the same file
does not create duplicates and lets the rest of the app cache aggressively.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - optional dependency guard
    fitz = None  # type: ignore

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}

# DPI used when rasterising a PDF template to a crisp PNG.
PDF_RENDER_DPI = 200


class TemplateConversionError(Exception):
    """Raised when an uploaded template cannot be converted to PNG."""


def _digest(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:12]


def convert_to_png(source_bytes: bytes, original_name: str, dest_dir: Path) -> Path:
    """
    Convert ``source_bytes`` (an uploaded PNG/JPG/JPEG/PDF) to a PNG saved in
    ``dest_dir`` and return the resulting path.

    The output filename is derived from the original stem plus a short hash
    of the content, so identical uploads map to the same file.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(original_name).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise TemplateConversionError(
            f"Unsupported template type '{ext}'. Use PNG, JPG, JPEG or PDF."
        )

    stem = Path(original_name).stem or "template"
    safe_stem = "".join(c for c in stem if c.isalnum() or c in ("-", "_", " ")).strip()
    safe_stem = safe_stem.replace(" ", "_") or "template"
    out_path = dest_dir / f"{safe_stem}_{_digest(source_bytes)}.png"

    if out_path.exists():
        return out_path

    try:
        if ext == ".pdf":
            _pdf_to_png(source_bytes, out_path)
        else:
            _raster_to_png(source_bytes, out_path)
    except TemplateConversionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TemplateConversionError(
            f"Could not convert '{original_name}' to PNG: {exc}"
        ) from exc

    return out_path


def _raster_to_png(source_bytes: bytes, out_path: Path) -> None:
    import io

    with Image.open(io.BytesIO(source_bytes)) as img:
        img.convert("RGB").save(out_path, "PNG")


def _pdf_to_png(source_bytes: bytes, out_path: Path) -> None:
    if fitz is None:
        raise TemplateConversionError(
            "PDF support requires PyMuPDF. Install it with 'pip install PyMuPDF'."
        )
    doc = fitz.open(stream=source_bytes, filetype="pdf")
    try:
        if doc.page_count == 0:
            raise TemplateConversionError("The PDF has no pages.")
        page = doc.load_page(0)
        zoom = PDF_RENDER_DPI / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pix.save(out_path)
    finally:
        doc.close()


def get_dimensions(png_path: Path) -> tuple[int, int]:
    """Return the (width, height) in pixels of a PNG template."""
    with Image.open(png_path) as img:
        return img.size
