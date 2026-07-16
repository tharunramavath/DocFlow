"""
services/certificate_generator.py
=================================
Generates a personalized certificate for a participant by drawing multiple
dynamic elements (text and images) onto a template image and exporting the
result as a high-quality PDF.

Refactored from the original project's certificate_generator.py. The
name-fitting / auto-shrink logic is preserved exactly; what's new is that
placement and styling now come from a list of element dicts (so the UI can
drive them live) and the renderer additionally supports font-family
selection, bold/italic variants, text alignment, hex colours, and image
elements (logos, signatures, etc.).

The same rendering routine powers both the on-screen live preview
(``render_preview_image``) and the final PDF export
(``generate_certificate``), so what the user previews is exactly what gets
sent.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

from core.utils import hex_to_rgb, sanitize_filename
from services.config_manager import BASE_DIR, FONTS_DIR, GENERATED_DIR, resolve_path
from services.placeholder_service import replace_placeholders

logger = logging.getLogger(__name__)


class CertificateGenerationError(Exception):
    """Raised when a certificate cannot be generated for a participant."""


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------
def build_certificate_context(participant, config: Dict[str, Any]) -> Dict[str, str]:
    """Assemble the placeholder-substitution context for one participant."""
    context = {
        "{{Name}}": participant.name,
        "{{Email}}": participant.email,
        "{{Date}}": date.today().strftime("%B %d, %Y"),
        "{{Organization}}": config.get("email_settings", {}).get(
            "organization_name", ""
        ),
        "{{CertificateName}}": config.get("campaign_settings", {}).get(
            "certificate_name", "Certificate of Participation"
        ),
    }
    if participant.extras:
        context.update(participant.extras)
    return context


# ---------------------------------------------------------------------------
# Font discovery & resolution (unchanged from original)
# ---------------------------------------------------------------------------
def list_font_families() -> List[str]:
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
    candidates.append(family)
    return candidates


def resolve_font_path(family: str, bold: bool, italic: bool) -> Path | None:
    for name in _font_candidates(family, bold, italic):
        candidate = FONTS_DIR / f"{name}.ttf"
        if candidate.exists():
            return candidate
    matches = sorted(FONTS_DIR.glob(f"{family}*.ttf"))
    return matches[0] if matches else None


def _stem_has(path: Path | None, tokens: Tuple[str, ...]) -> bool:
    if path is None:
        return False
    stem = path.stem.lower()
    return any(tok.lower() in stem for tok in tokens)


def resolve_style(family: str, bold: bool, italic: bool):
    path = resolve_font_path(family, bold, italic)
    true_bold = bold and _stem_has(path, ("Bold",))
    true_italic = italic and _stem_has(path, ("Italic", "Oblique"))
    return path, true_bold, true_italic


def _load_font(
    family: str, bold: bool, italic: bool, size: int
) -> ImageFont.FreeTypeFont:
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
_ITALIC_SHEAR = 0.24


def _shear_italic(
    tile: Image.Image, shear: float = _ITALIC_SHEAR
) -> Tuple[Image.Image, float]:
    w, h = tile.size
    xshift = shear * h
    sheared = tile.transform(
        (w + int(round(xshift)), h),
        Image.AFFINE,
        (1, shear, -xshift, 0, 1, 0),
        resample=Image.BICUBIC,
    )
    return sheared, xshift


def _place_text_element(
    image: Image.Image, element: Dict, context: Dict[str, str]
) -> Image.Image:
    """
    Draw a single text element onto ``image``.
    ``element`` holds position and styling; ``context`` provides placeholder values.
    """
    text = replace_placeholders(element.get("content_source", ""), context)
    if not text:
        return image

    draw = ImageDraw.Draw(image)

    family = element.get("font_family", "DejaVuSerif")
    bold = bool(element.get("bold", False))
    italic = bool(element.get("italic", False))
    color = hex_to_rgb(element.get("font_color", "#141414"))
    alignment = element.get("alignment", "center")

    font, used_size = _fit_text_to_width(
        draw=draw,
        text=text,
        max_width=int(element.get("max_text_width", 1350)),
        start_size=int(element.get("font_size", 90)),
        min_size=int(element.get("min_font_size", 40)),
        step=int(element.get("font_size_step", 2)),
        family=family,
        bold=bold,
        italic=italic,
    )

    _, true_bold, true_italic = resolve_style(family, bold, italic)
    faux_bold = bold and not true_bold
    faux_italic = italic and not true_italic
    stroke = max(1, round(used_size * 0.035)) if faux_bold else 0

    if used_size == int(element.get("min_font_size", 40)):
        probe = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
        if (probe[2] - probe[0]) > int(element.get("max_text_width", 1350)):
            logger.warning(
                "Text '%s' still exceeds max width at minimum font size.", text
            )

    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = max(6, used_size // 6)

    fill = (color[0], color[1], color[2], 255)
    tile = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text(
        (pad - bbox[0], pad - bbox[1]),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke,
        stroke_fill=fill,
    )

    xshift = 0.0
    if faux_italic:
        tile, xshift = _shear_italic(tile)

    anchor_x = int(element.get("x", image.width // 2))
    anchor_y = int(element.get("y", image.height // 2))
    if alignment == "left":
        x = anchor_x
    elif alignment == "right":
        x = anchor_x - tw
    else:
        x = anchor_x - tw / 2
    y = anchor_y - th / 2

    paste_x = int(round(x - pad - xshift / 2))
    paste_y = int(round(y - pad))
    image.paste(tile, (paste_x, paste_y), tile)
    return image


def _place_image_element(image: Image.Image, element: Dict) -> Image.Image:
    """
    Paste an image element (logo, signature, etc.) onto the certificate.
    Resolves the path via ``resolve_path``; optionally resizes to width/height.
    """
    source = element.get("content_source", "")
    if not source:
        return image

    img_path = resolve_path(source)
    if not img_path or not img_path.exists():
        logger.warning(
            "Image element '%s' not found at '%s'", element.get("label", ""), img_path
        )
        return image

    try:
        overlay = Image.open(img_path).convert("RGBA")
    except Exception as exc:
        logger.warning("Failed to open image '%s': %s", img_path, exc)
        return image

    # Optional resize
    w = element.get("width")
    h = element.get("height")
    if w and h:
        overlay = overlay.resize((int(w), int(h)), Image.LANCZOS)
    elif w:
        ratio = float(w) / overlay.width
        overlay = overlay.resize((int(w), int(overlay.height * ratio)), Image.LANCZOS)
    elif h:
        ratio = float(h) / overlay.height
        overlay = overlay.resize((int(overlay.width * ratio), int(h)), Image.LANCZOS)

    # Opacity / alpha blending
    opacity = float(element.get("opacity", 1.0))
    if opacity < 1.0:
        r, g, b, a = overlay.split()
        a = a.point(lambda x: int(x * opacity))
        overlay = Image.merge("RGBA", (r, g, b, a))

    x = int(element.get("x", 0))
    y = int(element.get("y", 0))
    image.paste(overlay, (x, y), overlay)
    return image


def _render_elements(
    image: Image.Image, elements: List[Dict], context: Dict[str, str]
) -> Image.Image:
    """
    Iterate through all elements in order and render each onto the image.
    Text elements get placeholder substitution; image elements are pasted directly.
    """
    for element in elements:
        etype = element.get("type", "text")
        if etype == "image":
            image = _place_image_element(image, element)
        else:
            image = _place_text_element(image, element, context)
    return image


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def render_certificate_image(
    template_path: Path,
    elements: List[Dict],
    context: Dict[str, str],
) -> Image.Image:
    """Draw all elements onto the template and return the resulting PIL image (RGB)."""
    template_path = Path(template_path)
    if not template_path.exists():
        raise CertificateGenerationError(
            f"Certificate template not found: {template_path}"
        )

    with Image.open(template_path) as template:
        image = template.convert("RGB")

    return _render_elements(image, elements, context)


def generate_certificate(
    participant,
    template_path: Path,
    elements: List[Dict],
    config: Dict[str, Any],
    output_dir: Path = GENERATED_DIR,
) -> Path:
    """
    Generate a personalized certificate PDF for a participant and return its path.
    Builds context from participant data, renders all elements, saves as PDF.
    Raises ``CertificateGenerationError`` on failure.
    """
    try:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        context = build_certificate_context(participant, config)
        image = render_certificate_image(template_path, elements, context)

        output_path = output_dir / f"{sanitize_filename(participant.name)}.pdf"
        dpi = float(config.get("dpi", 300))
        image.save(output_path, "PDF", resolution=dpi, quality=95)
        return output_path
    except CertificateGenerationError:
        raise
    except Exception as exc:
        raise CertificateGenerationError(
            f"Failed to generate certificate for '{getattr(participant, 'name', '?')}': {exc}"
        ) from exc


def render_preview_image(
    template_path: Path,
    elements: List[Dict],
    context: Dict[str, str],
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
        return render_certificate_image(template_path, elements, context)

    # Scale elements
    scaled_elements = []
    for el in elements:
        sel = dict(el)
        for key in ("x", "y", "font_size", "min_font_size", "max_text_width"):
            if key in sel:
                sel[key] = max(1, int(sel[key] * scale))
        if sel.get("type") == "image":
            for key in ("width", "height"):
                if key in sel and sel[key]:
                    sel[key] = max(1, int(sel[key] * scale))
        scaled_elements.append(sel)

    with Image.open(template_path) as template:
        small = template.convert("RGB").resize(
            (max(1, int(full_w * scale)), max(1, int(full_h * scale)))
        )

    return _render_elements(small, scaled_elements, context)
