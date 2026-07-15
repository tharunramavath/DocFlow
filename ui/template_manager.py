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
from pathlib import Path
from typing import List

import streamlit as st

from core import theme
from core.state import cfg, participants, persist_config, set_participants
from services import excel_reader
from services import asset_library
from services.certificate_generator import list_font_families, render_preview_image
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


# --------------------------------------------------------------------------
# Cached preview so dragging sliders stays responsive
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _cached_preview(template_path: str, mtime: float, position_json: str, name: str) -> bytes:
    import io

    position = json.loads(position_json)
    img = render_preview_image(name, Path(template_path), position, max_dimension=900)
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
            index=preset_opts.index(default_preset) if default_preset in preset_opts else 1,
            horizontal=True,
            key="preview_rows_preset",
        )
    with pc2:
        if preview_preset == "Custom":
            n_rows = st.number_input(
                "Exact row count", min_value=1, max_value=max(total_rows, 1),
                value=min(10, total_rows) or 1, key="preview_rows_custom",
            )
        else:
            n_rows = total_rows if preview_preset == "All" else int(preview_preset)
            st.caption(f"Showing {min(n_rows, total_rows)} of {total_rows} row(s)")

    st.dataframe(df.head(int(n_rows)), width='stretch', hide_index=True)

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
        email_guess = mapping["email_column"] if mapping["email_column"] in columns else (
            next((c for c in columns if "mail" in c.lower()), columns[min(1, len(columns) - 1)])
        )
        mapping["email_column"] = st.selectbox(
            "Email column", columns, index=columns.index(email_guess)
        )


    if st.button("Load participants", type="primary", key="load_participants"):
        try:
            result = excel_reader.build_participants(
                df,
                mapping["name_column"],
                mapping["email_column"],
                mapping.get("extra_fields", {}),
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
    theme.section("Text position & style", "6", f"Template is {w}×{h}px")

    pos = cfg()["text_position"]
    sample_default = participants()[0].name if participants() else "Alexandra Whitfield"
    sample = st.text_input("Preview name", value=sample_default, key="preview_name")

    editor, preview = st.columns([1, 1.3], gap="large")
    with editor:
        pos["x"] = st.slider("X position", 0, w, min(int(pos.get("x", w // 2)), w))
        pos["y"] = st.slider("Y position", 0, h, min(int(pos.get("y", h // 2)), h))
        c1, c2 = st.columns(2)
        with c1:
            pos["font_size"] = st.number_input(
                "Font size", 10, 400, int(pos.get("font_size", 90))
            )
            pos["min_font_size"] = st.number_input(
                "Min font size", 8, 400, int(pos.get("min_font_size", 40))
            )
        with c2:
            pos["max_text_width"] = st.number_input(
                "Max text width (px)", 100, w, min(int(pos.get("max_text_width", 1350)), w)
            )
            pos["dpi"] = st.number_input("Export DPI", 72, 600, int(pos.get("dpi", 300)))

        families = list_font_families()
        fam_idx = families.index(pos["font_family"]) if pos.get("font_family") in families else 0
        pos["font_family"] = st.selectbox("Font family", families, index=fam_idx)

        c3, c4, c5 = st.columns(3)
        with c3:
            pos["bold"] = st.checkbox("Bold", value=bool(pos.get("bold", False)))
        with c4:
            pos["italic"] = st.checkbox("Italic", value=bool(pos.get("italic", False)))
        with c5:
            pos["font_color"] = st.color_picker(
                "Colour", value=pos.get("font_color", "#141414")
            )

        align_opts = ["left", "center", "right"]
        pos["alignment"] = st.radio(
            "Alignment",
            align_opts,
            index=align_opts.index(pos.get("alignment", "center")),
            horizontal=True,
        )

        if st.button("Save text settings", type="primary", key="save_pos"):
            persist_config()
            st.session_state.toast = ("Text settings saved.", "✅")

    with preview:
        st.caption("Live preview")
        try:
            png = _cached_preview(
                str(chosen_path),
                chosen_path.stat().st_mtime,
                json.dumps(pos, sort_keys=True),
                sample or "Sample Name",
            )
            st.image(png, width='stretch')
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
        font_up = st.file_uploader(
            "Add a .ttf font", type=["ttf"], key="font_uploader"
        )
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
        c for c in ("image", "video", "audio", "spreadsheet", "document", "other")
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
                        "Download", fh.read(), file_name=asset.name,
                        key=f"dl_{asset.path}", width='stretch',
                    )
            with cols[4]:
                if st.button("Delete", key=f"del_{asset.path}", width='stretch'):
                    asset_library.delete_media(asset.path)
                    st.session_state.toast = (f"Deleted {asset.name}.", "🗑️")
                    st.rerun()

            if asset.category == "image":
                st.image(str(asset.path), width=280)
            elif asset.category == "video":
                st.video(str(asset.path))
            elif asset.category == "audio":
                st.audio(str(asset.path))
            elif asset.category == "spreadsheet" and asset.path.suffix.lower() in (".csv", ".xlsx", ".xls", ".tsv"):
                try:
                    df = excel_reader.load_dataframe(asset.path) if asset.path.suffix.lower() != ".csv" \
                        else __import__("pandas").read_csv(asset.path)
                    st.dataframe(df.head(5), width='stretch')
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
    t1, t2, t3 = st.tabs(["👥 Participants", "🖼️ Certificate & Text", "📁 Files & Media"])
    with t1:
        _participants_tab()
    with t2:
        _certificate_tab()
    with t3:
        _files_tab()
