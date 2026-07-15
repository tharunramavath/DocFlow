"""
services/certificate_generator.py
=================================
Generates a personalized certificate for a participant by drawing their name
onto a template image and exporting the result as a high-quality PDF.

Refactored from the original project's certificate_generator.py. The
name-fitting / auto-shrink logic is preserved exactly; what's new is that
placement and styling now come from a plain settings dict (so the UI can
drive them live) and the renderer additionally supports font-family
selection, bold/italic variants, text alignment and hex colours.

The same rendering routine powers both the on-screen live preview
(``render_preview_image``) and the final PDF export
(``generate_certificate``), so what the user previews is exactly what gets
sent.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

from core.utils import hex_to_rgb, sanitize_filename
from services.config_manager import FONTS_DIR, GENERATED_DIR

logger = logging.getLogger(__name__)


class CertificateGenerationError(Exception):
    """Raised when a certificate cannot be generated for a participant."""


# ---------------------------------------------------------------------------
# Font discovery & resolution
# ---------------------------------------------------------------------------
def list_font_families() -> List[str]:
    """
    Return the sorted list of base font family names available in the fonts
    folder. Variant suffixes (-Bold, -Italic, -Oblique, -BoldItalic ...) are
    stripped so the UI shows one entry per family.
    """
    families = set()
    for ttf in FONTS_DIR.glob("*.ttf"):
        stem = ttf.stem
        for suffix in ("-BoldOblique", "-BoldItalic", "-Oblique", "-Italic", "-Bold"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        families.add(stem)
    return sorted(families) or ["DejaVuSerif"]


def _font_candidates(family: str, bold: bool, italic: bool) -> List[str]:
    """Ordered list of candidate filenames, most-specific variant first."""
    italic_names = ("Italic", "Oblique")
    candidates: List[str] = []

    if bold and italic:
        candidates += [f"{family}-Bold{i}" for i in italic_names]
        candidates += [f"{family}-{i}" for i in italic_names]
        candidates.append(f"{family}-Bold")
    elif bold:
        candidates.append(f"{family}-Bold")
    elif italic:
        candidates += [f"{family}-{i}" for i in italic_names]

    candidates.append(family)  # always fall back to the regular face
    return candidates


def resolve_font_path(family: str, bold: bool, italic: bool) -> Path | None:
    """Find the best available .ttf for the requested style, or None."""
    for name in _font_candidates(family, bold, italic):
        candidate = FONTS_DIR / f"{name}.ttf"
        if candidate.exists():
            return candidate
    # Last resort: any ttf that starts with the family name.
    matches = sorted(FONTS_DIR.glob(f"{family}*.ttf"))
    return matches[0] if matches else None


def _stem_has(path: Path | None, tokens: Tuple[str, ...]) -> bool:
    if path is None:
        return False
    stem = path.stem.lower()
    return any(tok.lower() in stem for tok in tokens)


def resolve_style(family: str, bold: bool, italic: bool):
    """
    Resolve the requested style to a concrete font file and report whether
    bold / italic are satisfied by a *true* font face. Whatever isn't
    satisfied is synthesized at render time (faux bold via stroke, faux
    italic via shear) so bold and italic always have a visible effect — even
    for uploaded fonts that ship only a regular face.
    """
    path = resolve_font_path(family, bold, italic)
    true_bold = bold and _stem_has(path, ("Bold",))
    true_italic = italic and _stem_has(path, ("Italic", "Oblique"))
    return path, true_bold, true_italic


def _load_font(family: str, bold: bool, italic: bool, size: int) -> ImageFont.FreeTypeFont:
    path = resolve_font_path(family, bold, italic)
    if path is not None:
        try:
            return ImageFont.truetype(str(path), size)
        except (OSError, IOError):
            pass
    logger.warning("Could not load font '%s' — using Pillow default.", family)
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Text fitting (behaviour preserved from the original project)
# ---------------------------------------------------------------------------
def _fit_text_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    start_size: int,
    min_size: int,
    step: int,
    family: str,
    bold: bool,
    italic: bool,
) -> Tuple[ImageFont.FreeTypeFont, int]:
    font_size = max(int(start_size), int(min_size))
    font = _load_font(family, bold, italic, font_size)

    while font_size > min_size:
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            break
        font_size -= max(1, int(step))
        font = _load_font(family, bold, italic, font_size)

    return font, font_size


# ---------------------------------------------------------------------------
# Core rendering
# ---------------------------------------------------------------------------
_ITALIC_SHEAR = 0.24  # ~13.5° lean for synthesized italic


def _shear_italic(tile: Image.Image, shear: float = _ITALIC_SHEAR) -> Tuple[Image.Image, float]:
    """Slant a transparent text tile to the right (faux italic). Returns the
    sheared tile and the horizontal shift applied so callers can re-centre."""
    w, h = tile.size
    xshift = shear * h
    sheared = tile.transform(
        (w + int(round(xshift)), h),
        Image.AFFINE,
        (1, shear, -xshift, 0, 1, 0),
        resample=Image.BICUBIC,
    )
    return sheared, xshift


def _place_name(image: Image.Image, name: str, position: Dict) -> Image.Image:
    """
    Draw ``name`` onto ``image`` honouring family, bold, italic, colour and
    alignment. Bold/italic that the chosen font can't provide natively are
    synthesized (stroke / shear) so the style is always visible. Shared by the
    live preview and the final PDF export, so what you preview is what you get.
    """
    draw = ImageDraw.Draw(image)

    family = position.get("font_family", "DejaVuSerif")
    bold = bool(position.get("bold", False))
    italic = bool(position.get("italic", False))
    color = hex_to_rgb(position.get("font_color", "#141414"))
    alignment = position.get("alignment", "center")

    font, used_size = _fit_text_to_width(
        draw=draw,
        text=name,
        max_width=int(position.get("max_text_width", 1350)),
        start_size=int(position.get("font_size", 90)),
        min_size=int(position.get("min_font_size", 40)),
        step=int(position.get("font_size_step", 2)),
        family=family,
        bold=bold,
        italic=italic,
    )

    _, true_bold, true_italic = resolve_style(family, bold, italic)
    faux_bold = bold and not true_bold
    faux_italic = italic and not true_italic
    stroke = max(1, round(used_size * 0.035)) if faux_bold else 0

    if used_size == int(position.get("min_font_size", 40)):
        probe = draw.textbbox((0, 0), name, font=font, stroke_width=stroke)
        if (probe[2] - probe[0]) > int(position.get("max_text_width", 1350)):
            logger.warning(
                "Name '%s' still exceeds max width at minimum font size.", name
            )

    # Render the name onto its own transparent tile so we can shear it.
    bbox = draw.textbbox((0, 0), name, font=font, stroke_width=stroke)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = max(6, used_size // 6)

    fill = (color[0], color[1], color[2], 255)
    tile = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text(
        (pad - bbox[0], pad - bbox[1]),
        name,
        font=font,
        fill=fill,
        stroke_width=stroke,
        stroke_fill=fill,
    )

    xshift = 0.0
    if faux_italic:
        tile, xshift = _shear_italic(tile)

    anchor_x = int(position.get("x", image.width // 2))
    anchor_y = int(position.get("y", image.height // 2))
    if alignment == "left":
        x = anchor_x
    elif alignment == "right":
        x = anchor_x - tw
    else:  # center
        x = anchor_x - tw / 2
    y = anchor_y - th / 2

    paste_x = int(round(x - pad - xshift / 2))
    paste_y = int(round(y - pad))
    image.paste(tile, (paste_x, paste_y), tile)
    return image


def render_certificate_image(
    name: str,
    template_path: Path,
    position: Dict,
) -> Image.Image:
    """
    Draw ``name`` onto the template and return the resulting PIL image (RGB).
    Shared by the live preview and the PDF export.
    """
    template_path = Path(template_path)
    if not template_path.exists():
        raise CertificateGenerationError(
            f"Certificate template not found: {template_path}"
        )

    with Image.open(template_path) as template:
        image = template.convert("RGB")

    return _place_name(image, name, position)


def generate_certificate(
    name: str,
    template_path: Path,
    position: Dict,
    output_dir: Path = GENERATED_DIR,
) -> Path:
    """
    Generate a personalized certificate PDF for ``name`` and return its path.
    Raises ``CertificateGenerationError`` on failure.
    """
    try:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        image = render_certificate_image(name, template_path, position)

        output_path = output_dir / f"{sanitize_filename(name)}.pdf"
        image.save(
            output_path,
            "PDF",
            resolution=float(position.get("dpi", 300)),
            quality=95,
        )
        return output_path
    except CertificateGenerationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CertificateGenerationError(
            f"Failed to generate certificate for '{name}': {exc}"
        ) from exc


def render_preview_image(
    name: str,
    template_path: Path,
    position: Dict,
    max_dimension: int = 1000,
) -> Image.Image:
    """
    Render a downscaled preview image suitable for the UI. Scaling the
    coordinates keeps the preview faithful to the full-size output.
    """
    with Image.open(template_path) as template:
        full_w, full_h = template.size

    scale = min(1.0, max_dimension / max(full_w, full_h))

    if scale >= 1.0:
        return render_certificate_image(name, template_path, position)

    scaled = dict(position)
    for key in ("x", "y", "font_size", "min_font_size", "max_text_width"):
        if key in scaled:
            scaled[key] = max(1, int(scaled[key] * scale))

    # Render onto a downscaled copy of the template using the same routine as
    # the full-size export, so the preview faithfully reflects the output.
    with Image.open(template_path) as template:
        small = template.convert("RGB").resize(
            (max(1, int(full_w * scale)), max(1, int(full_h * scale)))
        )

    return _place_name(small, name, scaled)
