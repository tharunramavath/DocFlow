"""
ui/presets_panel.py
===================
Preset manager (requirement 10). A preset captures the entire configuration —
certificate template, email template, sender settings, organization, text
positions, delay settings, column mapping, retry settings and campaign
settings — so a whole workflow can be saved, reused and shared.
"""

from __future__ import annotations

import streamlit as st

from core import theme
from core.state import cfg, persist_config, set_config
from services import preset_manager as pm


def render() -> None:
    theme.hero("Presets", "Save an entire setup once, reuse it forever")

    presets = pm.list_presets()
    active = st.session_state.get("active_preset", pm.DEFAULT_PRESET_NAME)

    theme.section("Your presets", "10", f"{len(presets)} available")

    c1, c2 = st.columns([2, 1])
    with c1:
        idx = presets.index(active) if active in presets else 0
        selected = st.selectbox("Select a preset", presets, index=idx)
    with c2:
        st.write("")
        st.write("")
        if st.button("Load into editor", type="primary", width='stretch'):
            set_config(pm.load_preset(selected))
            st.session_state.active_preset = selected
            persist_config()
            st.session_state.toast = (f"Loaded preset '{selected}'.", "📂")
            st.rerun()

    is_builtin = selected == pm.DEFAULT_PRESET_NAME
    if is_builtin:
        st.caption("This is the built-in default. Duplicate it to make an editable copy.")

    st.divider()
    theme.section("Manage", "", "")

    a, b = st.columns(2)

    with a:
        st.markdown("**Save current setup as a preset**")
        new_name = st.text_input("Preset name", key="new_preset_name", placeholder="Spring 2026 Workshop")
        if st.button("Save preset", width='stretch'):
            try:
                name = pm.save_preset(new_name, cfg(), overwrite=True)
                st.session_state.active_preset = name
                st.session_state.toast = (f"Saved preset '{name}'.", "✅")
                st.rerun()
            except pm.PresetError as exc:
                st.error(str(exc))

        st.markdown("**Duplicate**")
        dup_name = st.text_input("New name", key="dup_name", placeholder=f"{selected} copy")
        if st.button("Duplicate selected", width='stretch'):
            try:
                name = pm.duplicate_preset(selected, dup_name or f"{selected} copy")
                st.session_state.toast = (f"Duplicated to '{name}'.", "🗂️")
                st.rerun()
            except pm.PresetError as exc:
                st.error(str(exc))

    with b:
        st.markdown("**Rename**")
        rename_to = st.text_input("Rename to", key="rename_to", disabled=is_builtin)
        if st.button("Rename selected", width='stretch', disabled=is_builtin):
            try:
                name = pm.rename_preset(selected, rename_to)
                if st.session_state.get("active_preset") == selected:
                    st.session_state.active_preset = name
                st.session_state.toast = (f"Renamed to '{name}'.", "✏️")
                st.rerun()
            except pm.PresetError as exc:
                st.error(str(exc))

        st.markdown("**Delete**")
        st.caption("This can't be undone.")
        if st.button("Delete selected", width='stretch', disabled=is_builtin):
            try:
                pm.delete_preset(selected)
                st.session_state.toast = (f"Deleted '{selected}'.", "🗑️")
                st.rerun()
            except pm.PresetError as exc:
                st.error(str(exc))

    st.divider()
    theme.section("Import & export", "", "Share presets as files")
    i1, i2 = st.columns(2)
    with i1:
        st.download_button(
            "Export selected preset",
            data=pm.export_preset(selected),
            file_name=f"{selected.replace(' ', '_')}.preset.json",
            mime="application/json",
            width='stretch',
        )
    with i2:
        up = st.file_uploader("Import a preset file", type=["json"], key="preset_import")
        if up is not None:
            try:
                name = pm.import_preset(up.getvalue())
                st.success(f"Imported preset '{name}'.")
            except pm.PresetError as exc:
                st.error(str(exc))
