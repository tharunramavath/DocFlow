"""
core/theme.py
=============
Visual identity for the app: a fully **light** "ink & brass" certificate
aesthetic — deep ink-navy text and antique-brass accents on warm paper.

Every interactive element pins an explicit text colour in *all* states
(normal / hover / active / focus / selected) so nothing ever turns
invisible on hover.

Exposes ``inject_theme()`` (call once at startup) plus small helper
components (hero, section headers, status badges, stat cards) so the UI
modules stay declarative and consistent.
"""

from __future__ import annotations

import streamlit as st

# --- Design tokens (single source of colour truth) -------------------------
INK = "#1B2440"          # primary ink navy — headers, body text
INK_SOFT = "#3A466A"     # secondary ink
BRASS = "#A9791F"        # antique brass accent — seals, emphasis, CTAs
BRASS_DEEP = "#8A6216"   # darker brass for text/borders on light
BRASS_SOFT = "#E7CF95"   # pale brass for gradients / hovers
PAPER = "#FBFAF6"        # warm paper canvas (app background)
SIDEBAR_BG = "#F3EFE5"   # light warm sidebar surface
SURFACE = "#FFFFFF"      # card surface
SURFACE_ALT = "#F6F2E9"  # subtle warm hover surface
LINE = "#E4DCC9"         # warm hairline border
MUTED = "#6B7280"        # muted slate text
SUCCESS = "#1F7A4D"
WARNING = "#9A6410"
ERROR = "#B4322E"
INFO = "#2C5DAA"

LEVEL_COLORS = {
    "success": SUCCESS,
    "warning": WARNING,
    "error": ERROR,
    "info": INFO,
}
LEVEL_ICONS = {
    "success": "✓",
    "warning": "!",
    "error": "✕",
    "info": "•",
}


def inject_theme() -> None:
    """Inject the global stylesheet. Safe to call on every rerun."""
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Inter:wght@400;500;600;700&display=swap');

        :root {{
            --ink: {INK};
            --brass: {BRASS};
            --paper: {PAPER};
            --line: {LINE};
            --muted: {MUTED};
        }}

        /* ---- Canvas & typography (light) -------------------------------- */
        .stApp {{ background: {PAPER}; color: {INK}; }}

        html, body, [class*="css"], .stMarkdown, p, span, label, div, li {{
            font-family: 'Inter', -apple-system, system-ui, sans-serif;
            color: {INK};
        }}
        .stApp p, .stApp li, .stApp label {{ color: {INK}; }}
        small, .stCaption, [data-testid="stCaptionContainer"] {{ color: {MUTED} !important; }}

        h1, h2, h3, h4 {{
            font-family: 'Fraunces', 'Georgia', serif !important;
            color: {INK} !important;
            letter-spacing: -0.01em;
        }}

        /* ---- Sidebar (now light) ---------------------------------------- */
        section[data-testid="stSidebar"] {{
            background: {SIDEBAR_BG};
            border-right: 1px solid {LINE};
        }}
        section[data-testid="stSidebar"] * {{ color: {INK}; }}
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {{ color: {INK} !important; }}

        /* Sidebar navigation radio — readable in every state */
        section[data-testid="stSidebar"] div[role="radiogroup"] label {{
            border-radius: 8px;
            padding: 7px 10px;
            margin: 1px 0;
            transition: background .12s ease, color .12s ease;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label p {{
            color: {INK} !important; font-weight: 600; font-size: 14px;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{
            background: {SURFACE};
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label:hover p {{
            color: {BRASS_DEEP} !important;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{
            background: {SURFACE};
            box-shadow: inset 3px 0 0 {BRASS};
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {{
            color: {INK} !important;
        }}
        /* hide the round radio dot in the nav for a cleaner menu look */
        section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {{
            display: none;
        }}

        /* ---- Buttons: pin text colour in every state -------------------- */
        .stButton > button, .stDownloadButton > button {{
            border-radius: 8px;
            font-weight: 600;
            background: {SURFACE};
            color: {INK} !important;
            border: 1px solid {LINE};
            transition: all .15s ease;
        }}
        .stButton > button p, .stDownloadButton > button p {{ color: {INK} !important; }}
        .stButton > button:hover, .stDownloadButton > button:hover {{
            background: {SURFACE_ALT};
            border-color: {BRASS};
            color: {INK} !important;
        }}
        .stButton > button:hover p, .stDownloadButton > button:hover p {{ color: {INK} !important; }}
        .stButton > button:active, .stButton > button:focus,
        .stDownloadButton > button:active, .stDownloadButton > button:focus {{
            color: {INK} !important; border-color: {BRASS};
        }}
        .stButton > button:disabled, .stButton > button:disabled p {{
            color: {MUTED} !important; opacity: .55;
        }}

        /* Primary CTA — white text on brass, in every state */
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, {BRASS}, #C79A3B);
            color: #ffffff !important;
            border: none;
        }}
        .stButton > button[kind="primary"] p {{ color: #ffffff !important; }}
        .stButton > button[kind="primary"]:hover {{
            filter: brightness(1.06);
            transform: translateY(-1px);
            color: #ffffff !important;
        }}
        .stButton > button[kind="primary"]:hover p {{ color: #ffffff !important; }}

        /* ---- Inputs, selects, sliders ----------------------------------- */
        .stTextInput input, .stNumberInput input, .stTextArea textarea {{
            color: {INK} !important;
            background: {SURFACE};
        }}
        div[data-baseweb="select"] > div {{
            background: {SURFACE};
            border-color: {LINE};
        }}
        div[data-baseweb="select"] * {{ color: {INK} !important; }}

        /* Dropdown popover options — the classic invisible-on-hover spot */
        ul[data-baseweb="menu"], div[data-baseweb="popover"] ul {{
            background: {SURFACE} !important;
        }}
        ul[data-baseweb="menu"] li {{ color: {INK} !important; }}
        ul[data-baseweb="menu"] li:hover,
        ul[data-baseweb="menu"] li[aria-selected="true"] {{
            background: {SURFACE_ALT} !important;
            color: {BRASS_DEEP} !important;
        }}

        /* Current Streamlit combobox/listbox internals (react-aria-components).
           Text colour is always pinned; hovered/focused/selected options get a
           visible highlight so keyboard and mouse users can see where they are. */
        .react-aria-ComboBox input {{ color: {INK} !important; }}
        [role="option"] {{ color: {INK} !important; }}
        [role="option"][data-hovered="true"],
        [role="option"][data-focused="true"] {{
            background: {SURFACE_ALT} !important;
            color: {BRASS_DEEP} !important;
        }}
        [role="option"][aria-selected="true"] {{
            font-weight: 600;
        }}

        /* Horizontal radios / toggles keep dark labels on hover */
        div[role="radiogroup"] label p {{ color: {INK} !important; }}
        div[role="radiogroup"] label:hover p {{ color: {INK} !important; }}
        .stSlider label, .stSlider [data-testid="stTickBar"] {{ color: {MUTED} !important; }}
        .stSlider [data-baseweb="slider"] div[role="slider"] {{ background: {BRASS}; }}

        /* ---- Metrics / cards -------------------------------------------- */
        div[data-testid="stMetric"] {{
            background: {SURFACE};
            border: 1px solid {LINE};
            border-radius: 12px;
            padding: 16px 18px;
            box-shadow: 0 1px 2px rgba(27,36,64,0.04);
        }}
        div[data-testid="stMetricValue"] {{
            color: {INK} !important;
            font-family: 'Fraunces', serif;
        }}
        div[data-testid="stMetricLabel"] {{ color: {MUTED} !important; }}

        /* ---- Tabs -------------------------------------------------------- */
        .stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid {LINE}; }}
        .stTabs [data-baseweb="tab"] {{
            border-radius: 8px 8px 0 0;
            font-weight: 600;
            color: {MUTED} !important;
        }}
        .stTabs [data-baseweb="tab"] p {{ color: {MUTED} !important; }}
        .stTabs [data-baseweb="tab"]:hover p {{ color: {INK} !important; }}
        .stTabs [aria-selected="true"] {{
            color: {INK} !important;
            border-bottom: 2px solid {BRASS};
        }}
        .stTabs [aria-selected="true"] p {{ color: {INK} !important; }}

        /* ---- Expanders --------------------------------------------------- */
        div[data-testid="stExpander"] {{
            border: 1px solid {LINE};
            border-radius: 10px;
            background: {SURFACE};
        }}
        div[data-testid="stExpander"] summary {{ color: {INK} !important; }}
        div[data-testid="stExpander"] summary:hover {{ color: {BRASS_DEEP} !important; }}

        /* ---- File uploader ---------------------------------------------- */
        section[data-testid="stFileUploaderDropzone"] {{
            background: {SURFACE};
            border: 1px dashed {LINE};
        }}
        section[data-testid="stFileUploaderDropzone"] * {{ color: {INK} !important; }}

        /* ---- Progress bar in brass -------------------------------------- */
        .stProgress > div > div > div > div {{
            background: linear-gradient(90deg, {BRASS}, #C79A3B);
        }}

        /* ---- Dataframe --------------------------------------------------- */
        div[data-testid="stDataFrame"] {{ border: 1px solid {LINE}; border-radius: 10px; }}

        /* ---- Alerts keep dark, readable text ---------------------------- */
        div[data-testid="stAlert"] p {{ color: {INK} !important; }}

        /* ---- Custom components ------------------------------------------ */
        .cm-hero {{ display:flex; align-items:center; gap:14px; padding: 4px 0 2px 0; }}
        .cm-seal {{
            width:44px; height:44px; border-radius:50%;
            background: radial-gradient(circle at 35% 30%, {BRASS_SOFT}, {BRASS});
            display:flex; align-items:center; justify-content:center;
            color:#fff; font-family:'Fraunces',serif; font-weight:700; font-size:20px;
            box-shadow: inset 0 0 0 3px rgba(255,255,255,.5), 0 2px 6px rgba(27,36,64,.15);
        }}
        .cm-eyebrow {{
            text-transform: uppercase; letter-spacing: .16em;
            font-size: 11px; font-weight: 700; color: {BRASS_DEEP};
        }}
        .cm-section {{
            display:flex; align-items:center; gap:10px;
            margin: 6px 0 14px 0; padding-bottom: 8px;
            border-bottom: 1px solid {LINE};
        }}
        .cm-section .num {{
            font-family:'Fraunces',serif; font-weight:700; color:{BRASS_DEEP};
            font-size: 15px; min-width: 26px;
        }}
        .cm-section .title {{ font-family:'Fraunces',serif; font-weight:600; color:{INK}; font-size:20px; }}
        .cm-section .sub {{ color:{MUTED}; font-size:13px; margin-left:auto; }}

        .cm-card {{
            background:{SURFACE}; border:1px solid {LINE}; border-radius:12px;
            padding:16px 18px; margin-bottom:12px;
            box-shadow: 0 1px 2px rgba(27,36,64,0.04);
        }}
        .cm-stat {{
            background:{SURFACE}; border:1px solid {LINE}; border-radius:12px;
            padding:14px 16px; height:100%;
        }}
        .cm-stat .k {{ color:{MUTED}; font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.06em; }}
        .cm-stat .v {{ color:{INK}; font-size:26px; font-weight:700; font-family:'Fraunces',serif; line-height:1.1; margin-top:4px; }}
        .cm-stat .v.accent {{ color:{BRASS_DEEP}; }}

        .cm-badge {{
            display:inline-flex; align-items:center; gap:6px;
            padding:4px 12px; border-radius:999px; font-size:12px; font-weight:700;
            border:1px solid transparent;
        }}

        /* Light log panel with colour-coded rows */
        .cm-log {{
            font-family:'SF Mono',ui-monospace,Menlo,monospace; font-size:12.5px;
            background:{SURFACE}; border-radius:10px; padding:12px 14px;
            max-height:420px; overflow-y:auto; border:1px solid {LINE};
        }}
        .cm-log .row {{ padding:2px 0; display:flex; gap:10px; align-items:baseline; }}
        .cm-log .t {{ color:{MUTED}; flex:0 0 62px; }}
        .cm-log .m {{ color:{INK}; }}
        .cm-log .who {{ color:{BRASS_DEEP}; font-weight:600; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# --- Component helpers -----------------------------------------------------
def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="cm-hero">
          <div class="cm-seal">✦</div>
          <div>
            <div class="cm-eyebrow">Certificate Studio</div>
            <div style="font-family:'Fraunces',serif;font-size:26px;font-weight:700;color:{INK};line-height:1.1;">{title}</div>
            <div style="color:{MUTED};font-size:13px;">{subtitle}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, number: str = "", sub: str = "") -> None:
    num = f'<span class="num">{number}</span>' if number else ""
    subhtml = f'<span class="sub">{sub}</span>' if sub else ""
    st.markdown(
        f'<div class="cm-section">{num}<span class="title">{title}</span>{subhtml}</div>',
        unsafe_allow_html=True,
    )


def status_badge(label: str, kind: str = "info") -> str:
    color = LEVEL_COLORS.get(kind, INFO)
    bg = {
        "success": "#E7F3EC",
        "warning": "#FBF1DF",
        "error": "#FBEAE9",
        "info": "#E9F0FA",
    }.get(kind, "#E9F0FA")
    icon = LEVEL_ICONS.get(kind, "•")
    return (
        f'<span class="cm-badge" style="background:{bg};color:{color};">'
        f"{icon} {label}</span>"
    )


def stat_card(label: str, value, accent: bool = False) -> str:
    cls = "v accent" if accent else "v"
    return f'<div class="cm-stat"><div class="k">{label}</div><div class="{cls}">{value}</div></div>'
