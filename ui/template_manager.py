"""
ui/template_manager.py
======================
The "Data & Template" workspace. Three tabs:

    1. Participants     — upload Excel, preview, map columns, load records
    2. Certificate      — upload/convert template + live text-position editor
    3. Files            — manage fonts, logo and signature uploads

Covers requirements 4 (Excel import), 5 (certificate import), 6 (text
position editor) and 14 (file management).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Dict, List

import streamlit as st

from core import theme
from core.state import cfg, participants, persist_config, set_participants
from services import excel_reader
from services import asset_library
from services.certificate_generator import (
    build_certificate_context,
    list_font_families,
    render_preview_image,
)
from services.config_manager import (
    FONTS_DIR,
    TEMPLATES_DIR,
    UPLOADS_DIR,
    resolve_path,
    to_relative,
)
from services.image_converter import (
    TemplateConversionError,
    convert_to_png,
    get_dimensions,
)
from services.placeholder_service import extract_placeholders


# --------------------------------------------------------------------------
# Cached preview so dragging sliders stays responsive
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _cached_preview(
    template_path: str, mtime: float, elements_json: str, context_json: str
) -> bytes:
    import io

    elements = json.loads(elements_json)
    context = json.loads(context_json)
    img = render_preview_image(
        Path(template_path), elements, context, max_dimension=900
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _save_upload(uploaded, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / uploaded.name
    with open(dest, "wb") as f:
        f.write(uploaded.getvalue())
    return dest


# --------------------------------------------------------------------------
# Tab 1 — Participants
# --------------------------------------------------------------------------
def _participants_tab() -> None:
    theme.section("Participant spreadsheet", "4", "Upload · preview · map columns")

    up = st.file_uploader(
        "Upload an Excel file (.xlsx or .xls)",
        type=["xlsx", "xls"],
        key="excel_uploader",
        help="Your sheet needs at least a name column and an email column.",
    )

    if up is not None:
        saved = _save_upload(up, UPLOADS_DIR)
        try:
            st.session_state.excel_df = excel_reader.load_dataframe(saved)
            st.session_state.participants_source = up.name
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not read the spreadsheet: {exc}")
            st.session_state.excel_df = None

    df = st.session_state.get("excel_df")
    if df is None:
        st.info("No spreadsheet loaded yet. Upload one above to get started.")
        with st.expander("Don't have a file handy? Use the bundled sample"):
            if st.button("Load sample participants", key="load_sample"):
                sample = resolve_path("assets/sample_participants.xlsx")
                st.session_state.excel_df = excel_reader.load_dataframe(sample)
                st.session_state.participants_source = "sample_participants.xlsx"
                st.rerun()
        return

    st.caption(f"Preview — first rows of **{st.session_state.participants_source}**")

    total_rows = len(df)
    pc1, pc2 = st.columns([2, 1])
    with pc1:
        preset_opts = ["5", "10", "20", "50", "100", "All", "Custom"]
        default_preset = st.session_state.get("preview_rows_preset", "10")
        preview_preset = st.radio(
            "Rows to preview",
            preset_opts,
            index=preset_opts.index(default_preset)
            if default_preset in preset_opts
            else 1,
            horizontal=True,
            key="preview_rows_preset",
        )
    with pc2:
        if preview_preset == "Custom":
            n_rows = st.number_input(
                "Exact row count",
                min_value=1,
                max_value=max(total_rows, 1),
                value=min(10, total_rows) or 1,
                key="preview_rows_custom",
            )
        else:
            n_rows = total_rows if preview_preset == "All" else int(preview_preset)
            st.caption(f"Showing {min(n_rows, total_rows)} of {total_rows} row(s)")

    st.dataframe(df.head(int(n_rows)), width="stretch", hide_index=True)

    columns = excel_reader.get_columns(df)
    mapping = cfg()["column_mapping"]

    theme.section("Column mapping", "", "Tell us which column is which")
    c1, c2 = st.columns(2)
    with c1:
        name_default = (
            columns.index(mapping["name_column"])
            if mapping["name_column"] in columns
            else 0
        )
        mapping["name_column"] = st.selectbox(
            "Participant name column", columns, index=name_default
        )
    with c2:
        email_guess = (
            mapping["email_column"]
            if mapping["email_column"] in columns
            else (
                next(
                    (c for c in columns if "mail" in c.lower()),
                    columns[min(1, len(columns) - 1)],
                )
            )
        )
        mapping["email_column"] = st.selectbox(
            "Email column", columns, index=columns.index(email_guess)
        )

    # Certificate ID column (optional)
    st.caption("Optional: Certificate ID column")
    c3, c4 = st.columns([3, 1])
    with c3:
        cert_id_options = [""] + columns
        cert_id_default = (
            columns.index(mapping["certificate_id_column"])
            if mapping.get("certificate_id_column") in columns
            else 0
        )
        mapping["certificate_id_column"] = st.selectbox(
            "Certificate ID column",
            cert_id_options,
            index=cert_id_default,
            help="Optional: select the column containing certificate IDs. "
            "This adds {{CertificateID}} as a placeholder for certificates and emails.",
        )

    # Auto-update any existing Certificate ID elements to use canonical placeholder
    if mapping.get("certificate_id_column"):
        for el in cfg().get("certificate_elements", []):
            src = el.get("content_source", "")
            if (
                src
                and "certificate" in src.lower()
                and "id" in src.lower().replace(" ", "")
            ):
                if el.get("content_source") != "{{CertificateID}}":
                    el["content_source"] = "{{CertificateID}}"
                    el["label"] = "Certificate ID"

    if st.button("Load participants", type="primary", key="load_participants"):
        try:
            result = excel_reader.build_participants(
                df,
                mapping["name_column"],
                mapping["email_column"],
                mapping.get("extra_fields", {}),
                mapping.get("certificate_id_column") or None,
            )
            set_participants(result.participants, st.session_state.participants_source)
            persist_config()
            msg = f"Loaded {result.valid_count} valid participant(s)."
            if result.skipped_invalid or result.skipped_missing:
                msg += (
                    f" Skipped {result.skipped_invalid} invalid email(s) and "
                    f"{result.skipped_missing} incomplete row(s)."
                )
            st.session_state.toast = (msg, "✅")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not load participants: {exc}")

    loaded = participants()
    if loaded:
        st.markdown(
            theme.status_badge(f"{len(loaded)} participants ready", "success"),
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------
# Tab 2 — Certificate & text position
# --------------------------------------------------------------------------
def _available_templates() -> List[Path]:
    return sorted(TEMPLATES_DIR.glob("*.png"))


def _available_placeholders() -> List[str]:
    """Return the list of all available placeholders for content_source."""
    builtins = [
        "{{Name}}",
        "{{Email}}",
        "{{Date}}",
        "{{Organization}}",
        "{{CertificateName}}",
        "{{CertificateID}}",
    ]
    df = st.session_state.get("excel_df")
    if df is not None:
        cols = [f"{{{{{c.strip()}}}}}" for c in df.columns if c.strip()]
        # Skip certificate ID variations - use canonical {{CertificateID}} only
        for c in cols:
            if c not in builtins and not (
                "certificate" in c.lower() and "id" in c.lower().replace(" ", "")
            ):
                builtins.append(c)
    extra = cfg().get("column_mapping", {}).get("extra_fields", {})
    for k in extra:
        if k not in builtins:
            builtins.append(k)
    # Ensure CertificateID is always available if certificate_id_column is configured
    cert_id_col = cfg().get("column_mapping", {}).get("certificate_id_column", "")
    if cert_id_col and "{{CertificateID}}" not in builtins:
        builtins.append("{{CertificateID}}")
    return builtins


def _available_images() -> List[Path]:
    """Return paths of images in uploads and media directories."""
    paths = []
    for d in [UPLOADS_DIR, resolve_path("assets/media/images")]:
        if d and d.exists():
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp"):
                paths.extend(d.glob(ext))
    return sorted(paths)


def _build_sample_context() -> Dict[str, str]:
    """Build a sample context dict for the live preview."""
    people = participants()
    if people:
        return build_certificate_context(people[0], cfg())
    email_settings = cfg().get("email_settings", {})
    campaign = cfg().get("campaign_settings", {})
    return {
        "{{Name}}": "Alexandra Whitfield",
        "{{Email}}": "alex@example.com",
        "{{Date}}": "July 16, 2026",
        "{{Organization}}": email_settings.get("organization_name", "Our Team"),
        "{{CertificateName}}": campaign.get(
            "certificate_name", "Certificate of Participation"
        ),
        "{{CertificateID}}": "CERT-2026-001",
    }


def _element_editor(elements: List[Dict], w: int, h: int) -> None:
    """Render the dynamic element list editor."""
    if not elements:
        st.info("No elements yet. Add one below.")
        return

    delete_keys = []
    move_up_keys = []
    move_down_keys = []

    for i, el in enumerate(elements):
        el_id = el.get("id", f"el_{i}")
        etype = el.get("type", "text")
        label = el.get("label", f"Element {i + 1}")
        type_icon = "📷" if etype == "image" else "Aa"
        type_label = "Image" if etype == "image" else "Text"

        cols = st.columns([0.5, 0.5, 3, 1.5, 0.5, 0.5])
        with cols[0]:
            if st.button("⬆", key=f"up_{el_id}", help="Move up"):
                move_up_keys.append(i)
        with cols[1]:
            if st.button("⬇", key=f"down_{el_id}", help="Move down"):
                move_down_keys.append(i)
        with cols[2]:
            st.markdown(f"**{label}**")
        with cols[3]:
            st.markdown(
                f"<span style='font-size:12px'>{type_icon} {type_label}</span>",
                unsafe_allow_html=True,
            )
        with cols[5]:
            if st.button("🗑", key=f"del_{el_id}", help="Delete element"):
                delete_keys.append(i)

        with st.expander(f"Edit {label}", expanded=False):
            el["label"] = st.text_input(
                "Label", value=el.get("label", ""), key=f"label_{el_id}"
            )

            if etype == "text":
                _text_element_fields(el, el_id, w, h)
            else:
                _image_element_fields(el, el_id, w, h)

        st.divider()

    # Apply moves and deletes (outside the loop to avoid index shifting)
    if move_up_keys:
        for idx in move_up_keys:
            if idx > 0:
                elements[idx], elements[idx - 1] = elements[idx - 1], elements[idx]
        cfg()["certificate_elements"] = elements
        st.rerun()
    if move_down_keys:
        for idx in reversed(move_down_keys):
            if idx < len(elements) - 1:
                elements[idx], elements[idx + 1] = elements[idx + 1], elements[idx]
        cfg()["certificate_elements"] = elements
        st.rerun()
    if delete_keys:
        for idx in reversed(sorted(delete_keys)):
            elements.pop(idx)
        cfg()["certificate_elements"] = elements
        st.rerun()


def _text_element_fields(el: Dict, el_id: str, w: int, h: int) -> None:
    """Render editor fields for a text element."""
    # Force Certificate ID elements to use canonical placeholder
    if el.get("label") == "Certificate ID":
        el["content_source"] = "{{CertificateID}}"

    placeholders = _available_placeholders()
    current_src = el.get("content_source", "")
    is_custom = current_src and current_src not in placeholders

    src_opts = ["Custom text..."] + placeholders
    src_idx = (
        0
        if is_custom
        else (src_opts.index(current_src) if current_src in src_opts else 0)
    )
    chosen = st.selectbox("Content source", src_opts, index=src_idx, key=f"src_{el_id}")
    if chosen == "Custom text...":
        el["content_source"] = st.text_input(
            "Custom text",
            value=current_src if is_custom else "",
            key=f"custom_src_{el_id}",
            placeholder="Type your text here...",
        )
    else:
        el["content_source"] = chosen

    c1, c2 = st.columns(2)
    with c1:
        el["x"] = st.slider(
            "X position", 0, w, min(int(el.get("x", w // 2)), w), key=f"x_{el_id}"
        )
    with c2:
        el["y"] = st.slider(
            "Y position", 0, h, min(int(el.get("y", h // 2)), h), key=f"y_{el_id}"
        )

    c3, c4 = st.columns(2)
    with c3:
        el["font_size"] = st.number_input(
            "Font size", 10, 400, int(el.get("font_size", 90)), key=f"fs_{el_id}"
        )
        el["min_font_size"] = st.number_input(
            "Min font size",
            8,
            400,
            int(el.get("min_font_size", 40)),
            key=f"mfs_{el_id}",
        )
    with c4:
        el["max_text_width"] = st.number_input(
            "Max text width (px)",
            100,
            w,
            min(int(el.get("max_text_width", 1350)), w),
            key=f"mtw_{el_id}",
        )

    families = list_font_families()
    fam_idx = (
        families.index(el.get("font_family", "DejaVuSerif"))
        if el.get("font_family") in families
        else 0
    )
    el["font_family"] = st.selectbox(
        "Font family", families, index=fam_idx, key=f"ff_{el_id}"
    )

    c5, c6, c7 = st.columns(3)
    with c5:
        el["bold"] = st.checkbox(
            "Bold", value=bool(el.get("bold", False)), key=f"bold_{el_id}"
        )
    with c6:
        el["italic"] = st.checkbox(
            "Italic", value=bool(el.get("italic", False)), key=f"italic_{el_id}"
        )
    with c7:
        el["font_color"] = st.color_picker(
            "Colour", value=el.get("font_color", "#141414"), key=f"color_{el_id}"
        )

    align_opts = ["left", "center", "right"]
    el["alignment"] = st.radio(
        "Alignment",
        align_opts,
        index=align_opts.index(el.get("alignment", "center")),
        horizontal=True,
        key=f"align_{el_id}",
    )


def _image_element_fields(el: Dict, el_id: str, w: int, h: int) -> None:
    """Render editor fields for an image element."""
    available = _available_images()
    img_labels = [p.name for p in available]
    current_src = el.get("content_source", "")

    st.markdown("**Image source**")
    up = st.file_uploader(
        "Upload new image",
        type=["png", "jpg", "jpeg", "gif", "webp"],
        key=f"img_up_{el_id}",
        label_visibility="collapsed",
    )
    if up is not None:
        dest = UPLOADS_DIR / up.name
        with open(dest, "wb") as f:
            f.write(up.getvalue())
        el["content_source"] = to_relative(dest)
        st.success(f"Uploaded {up.name}")
        st.rerun()

    if img_labels:
        idx = (
            img_labels.index(Path(current_src).name)
            if current_src and Path(current_src).name in img_labels
            else 0
        )
        chosen_img = st.selectbox(
            "Or select existing", img_labels, index=idx, key=f"img_sel_{el_id}"
        )
        if chosen_img:
            matched = next((p for p in available if p.name == chosen_img), None)
            if matched:
                el["content_source"] = to_relative(matched)

    c1, c2 = st.columns(2)
    with c1:
        el["x"] = st.slider(
            "X position", 0, w, min(int(el.get("x", 0)), w), key=f"ix_{el_id}"
        )
    with c2:
        el["y"] = st.slider(
            "Y position", 0, h, min(int(el.get("y", 0)), h), key=f"iy_{el_id}"
        )

    c3, c4 = st.columns(2)
    with c3:
        el["width"] = st.number_input(
            "Width (px, optional)",
            0,
            w,
            int(el.get("width", 0) or 0),
            key=f"iw_{el_id}",
        )
        if el["width"] == 0:
            el["width"] = None
    with c4:
        el["height"] = st.number_input(
            "Height (px, optional)",
            0,
            h,
            int(el.get("height", 0) or 0),
            key=f"ih_{el_id}",
        )
        if el["height"] == 0:
            el["height"] = None

    el["opacity"] = st.slider(
        "Opacity", 0.0, 1.0, float(el.get("opacity", 1.0)), key=f"iop_{el_id}"
    )


def _certificate_tab() -> None:
    theme.section("Certificate template", "5", "PNG · JPG · JPEG · PDF")

    up = st.file_uploader(
        "Upload a certificate template",
        type=["png", "jpg", "jpeg", "pdf"],
        key="cert_uploader",
        help="Non-PNG files are converted to PNG automatically.",
    )
    if up is not None:
        try:
            png_path = convert_to_png(up.getvalue(), up.name, TEMPLATES_DIR)
            cfg()["certificate_template"] = to_relative(png_path)
            persist_config()
            if up.name.lower().endswith((".pdf", ".jpg", ".jpeg")):
                st.success(f"Converted **{up.name}** to PNG.")
            else:
                st.success(f"Loaded **{up.name}**.")
        except TemplateConversionError as exc:
            st.error(str(exc))

    templates = _available_templates()
    if not templates:
        st.info("No templates yet. Upload one above.")
        return

    labels = [t.name for t in templates]
    current = resolve_path(cfg().get("certificate_template", ""))
    idx = labels.index(current.name) if current.name in labels else 0
    chosen = st.selectbox("Active template", labels, index=idx, key="template_select")
    chosen_path = TEMPLATES_DIR / chosen
    cfg()["certificate_template"] = to_relative(chosen_path)

    try:
        w, h = get_dimensions(chosen_path)
    except Exception:  # noqa: BLE001
        w, h = 2000, 1414

    st.divider()
    theme.section("Certificate elements", "6", f"Template is {w}×{h}px")

    # Ensure certificate_elements exists in config
    if "certificate_elements" not in cfg():
        cfg()["certificate_elements"] = []

    elements = cfg()["certificate_elements"]

    # Add element buttons
    col_add, col_save, _ = st.columns([2, 1, 2])
    with col_add:
        st.markdown("**Add element**")
        if st.button("+ Text", key="add_text_btn", use_container_width=True):
            elements.append(
                {
                    "id": "el_" + uuid.uuid4().hex[:8],
                    "type": "text",
                    "label": "New Text",
                    "content_source": "{{Name}}",
                    "x": w // 2,
                    "y": h // 2,
                    "font_size": 90,
                    "min_font_size": 40,
                    "font_size_step": 2,
                    "max_text_width": min(1350, w),
                    "font_color": "#141414",
                    "font_family": "DejaVuSerif",
                    "bold": False,
                    "italic": False,
                    "alignment": "center",
                }
            )
            cfg()["certificate_elements"] = elements
            st.rerun()
        if st.button("+ Image", key="add_image_btn", use_container_width=True):
            elements.append(
                {
                    "id": "el_" + uuid.uuid4().hex[:8],
                    "type": "image",
                    "label": "New Image",
                    "content_source": "",
                    "x": 0,
                    "y": 0,
                    "width": None,
                    "height": None,
                    "opacity": 1.0,
                }
            )
            cfg()["certificate_elements"] = elements
            st.rerun()
        if st.button(
            "+ Certificate ID", key="add_cert_id_btn", use_container_width=True
        ):
            elements.append(
                {
                    "id": "el_" + uuid.uuid4().hex[:8],
                    "type": "text",
                    "label": "Certificate ID",
                    "content_source": "{{CertificateID}}",
                    "x": w // 2,
                    "y": h // 2 + 150,
                    "font_size": 60,
                    "min_font_size": 30,
                    "font_size_step": 2,
                    "max_text_width": min(1000, w),
                    "font_color": "#141414",
                    "font_family": "DejaVuSerif",
                    "bold": False,
                    "italic": False,
                    "alignment": "center",
                }
            )
            cfg()["certificate_elements"] = elements
            st.rerun()
    with col_save:
        if st.button("Save elements", type="primary", key="save_elements"):
            persist_config()
            st.session_state.toast = ("Elements saved.", "✅")

    # Element editor list
    _element_editor(elements, w, h)

    # DPI setting (document-level)
    dpi_val = cfg().get("dpi", 300)
    cfg()["dpi"] = st.number_input(
        "Export DPI", 72, 600, int(dpi_val), key="dpi_setting"
    )

    # Preview
    st.divider()
    theme.section("Live preview", "", "All elements rendered together")
    sample_context = _build_sample_context()
    sample_name = sample_context.get("{{Name}}", "Sample")
    st.caption(f"Preview context: **{sample_name}** — {len(elements)} element(s)")

    try:
        png = _cached_preview(
            str(chosen_path),
            chosen_path.stat().st_mtime,
            json.dumps(elements, sort_keys=True),
            json.dumps(sample_context, sort_keys=True),
        )
        st.image(png, width="stretch")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Preview failed: {exc}")


# --------------------------------------------------------------------------
# Tab 3 — Files & Media
# --------------------------------------------------------------------------
def _files_tab() -> None:
    theme.section("File management", "14", "Fonts · logo · signature · media library")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Fonts**")
        font_up = st.file_uploader("Add a .ttf font", type=["ttf"], key="font_uploader")
        if font_up is not None:
            _save_upload(font_up, FONTS_DIR)
            st.success(f"Added font {font_up.name}")
            st.cache_data.clear()
        for f in sorted(FONTS_DIR.glob("*.ttf")):
            st.markdown(f"• `{f.name}`")

    with c2:
        st.markdown("**Logo & signature**")
        logo_up = st.file_uploader(
            "Logo image", type=["png", "jpg", "jpeg"], key="logo_uploader"
        )
        if logo_up is not None:
            path = _save_upload(logo_up, UPLOADS_DIR)
            st.success(f"Saved logo → {path.name}")
            st.image(path, width=160)
        sig_up = st.file_uploader(
            "Signature image", type=["png", "jpg", "jpeg"], key="sig_uploader"
        )
        if sig_up is not None:
            path = _save_upload(sig_up, UPLOADS_DIR)
            st.success(f"Saved signature → {path.name}")
            st.image(path, width=160)

    st.divider()
    theme.section("Media library", "", "Photos · video · audio · spreadsheets · docs")
    st.caption(
        "Supporting files for the event or campaign — highlight reels, event "
        "photos, briefing audio, extra attendee sheets, sponsor docs — kept "
        "separate from the certificate template and fonts above."
    )

    uploads = st.file_uploader(
        "Add media files",
        type=asset_library.ALL_EXTENSIONS,
        accept_multiple_files=True,
        key="media_uploader",
        help="Images, video, audio, spreadsheets and documents are all accepted "
        "and sorted automatically by type.",
    )
    if uploads:
        sig = tuple((uf.name, uf.size) for uf in uploads)
        if st.session_state.get("_media_last_sig") != sig:
            added = [asset_library.save_media(uf).name for uf in uploads]
            st.session_state["_media_last_sig"] = sig
            st.success(f"Added {len(added)} file(s): {', '.join(added)}")

    all_media = asset_library.list_media()
    if not all_media:
        st.info("No media files yet — upload something above to build your library.")
        return

    total = asset_library.total_size()
    total_mb = total / (1024 * 1024)
    st.caption(f"**{len(all_media)}** file(s) · {total_mb:.1f} MB total")

    categories = ["All"] + [
        c
        for c in ("image", "video", "audio", "spreadsheet", "document", "other")
        if any(a.category == c for a in all_media)
    ]
    labels = ["All"] + [
        f"{asset_library.CATEGORY_LABELS[c][0]} {asset_library.CATEGORY_LABELS[c][1]}"
        for c in categories[1:]
    ]
    choice = st.radio("Filter", labels, horizontal=True, label_visibility="collapsed")
    active_cat = None if choice == "All" else categories[labels.index(choice)]

    shown = [a for a in all_media if active_cat is None or a.category == active_cat]

    for asset in shown:
        icon, _ = asset_library.CATEGORY_LABELS[asset.category]
        with st.container():
            cols = st.columns([0.5, 3, 1, 1, 1])
            cols[0].markdown(f"### {icon}")
            cols[1].markdown(f"**{asset.name}**")
            cols[2].caption(asset.size_human)
            with cols[3]:
                with open(asset.path, "rb") as fh:
                    st.download_button(
                        "Download",
                        fh.read(),
                        file_name=asset.name,
                        key=f"dl_{asset.path}",
                        width="stretch",
                    )
            with cols[4]:
                if st.button("Delete", key=f"del_{asset.path}", width="stretch"):
                    asset_library.delete_media(asset.path)
                    st.session_state.toast = (f"Deleted {asset.name}.", "🗑️")
                    st.rerun()

            if asset.category == "image":
                st.image(str(asset.path), width=280)
            elif asset.category == "video":
                st.video(str(asset.path))
            elif asset.category == "audio":
                st.audio(str(asset.path))
            elif asset.category == "spreadsheet" and asset.path.suffix.lower() in (
                ".csv",
                ".xlsx",
                ".xls",
                ".tsv",
            ):
                try:
                    df = (
                        excel_reader.load_dataframe(asset.path)
                        if asset.path.suffix.lower() != ".csv"
                        else __import__("pandas").read_csv(asset.path)
                    )
                    st.dataframe(df.head(5), width="stretch")
                except Exception:  # noqa: BLE001
                    pass
        st.divider()

    st.caption(
        f"Templates → `templates/` &nbsp;·&nbsp; Fonts → `assets/fonts/` "
        f"&nbsp;·&nbsp; Logo/signature → `assets/uploads/` &nbsp;·&nbsp; "
        f"Media library → `assets/media/`"
    )


def render() -> None:
    theme.hero("Data & Template", "Bring in your people and design the certificate")
    t1, t2, t3 = st.tabs(
        ["👥 Participants", "🖼️ Certificate & Text", "📁 Files & Media"]
    )
    with t1:
        _participants_tab()
    with t2:
        _certificate_tab()
    with t3:
        _files_tab()
