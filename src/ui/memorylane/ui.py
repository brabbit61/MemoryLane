"""UI helpers + CSS that make Streamlit match the MemoryLane mockup.

Keep all look-and-feel here so ``app.py`` stays about flow & wiring.
"""

from __future__ import annotations

import streamlit as st

from .backend import IngestProgress, PhotoResult, ReasoningStep

# Colors (single source of truth — keep in sync with .streamlit/config.toml)
AMBER = "#E8A838"
INK = "#1C1C1E"
GREEN = "#3a9b6e"


def inject_css() -> None:
    """Fonts + component overrides. Call once at the top of the app."""
    # NB: plain str.replace, not %-formatting — the CSS is full of literal `%`
    # (e.g. border-radius:50%) which would break a % / .format() substitution.
    css = """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,500;6..72,600&family=JetBrains+Mono:wght@400;500&display=swap');

        html, body, [class*="css"] { font-family: 'Inter', system-ui, sans-serif; }
        h1, h2, h3 { font-family: 'Newsreader', serif !important; letter-spacing: -.01em; }

        /* tighter, calmer page */
        .block-container { padding-top: 2rem; max-width: 980px; }

        /* tabs */
        button[data-baseweb="tab"] { font-weight: 600; }
        div[data-baseweb="tab-highlight"] { background-color: %(amber)s !important; }

        /* primary buttons */
        .stButton > button[kind="primary"] {
            background: %(amber)s; color: %(ink)s; border: none; border-radius: 11px;
            font-weight: 600; box-shadow: 0 2px 8px rgba(232,168,56,.35);
        }
        .stButton > button { border-radius: 10px; }

        /* photo result grid */
        .ml-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
        .ml-card { background:#fff; border-radius:11px; box-shadow:0 2px 10px rgba(28,28,30,.07); padding:8px; }
        .ml-thumb { height:152px; border-radius:8px; position:relative; }
        .ml-thumb::after { content:''; position:absolute; inset:0; border-radius:8px;
            background: radial-gradient(circle at 30% 22%, rgba(255,255,255,.35), transparent 45%); }
        .ml-score { padding:9px 4px 4px; font:500 12px 'JetBrains Mono',monospace; color:rgba(28,28,30,.5); }

        /* ingest tiles */
        .ml-tiles { display:grid; grid-template-columns:repeat(6,1fr); gap:8px; }
        .ml-tile { position:relative; aspect-ratio:1; border-radius:8px; overflow:hidden; }
        .ml-badge { position:absolute; bottom:5px; right:5px; width:17px; height:17px; border-radius:50%;
            background:%(green)s; color:#fff; font:700 9px 'Inter'; display:flex; align-items:center;
            justify-content:center; box-shadow:0 1px 3px rgba(0,0,0,.25); }

        /* callouts */
        .ml-banner { display:flex; gap:10px; align-items:center; padding:13px 16px; border-radius:11px;
            font-size:13.5px; font-weight:500; }
        .ml-banner.ok { background:rgba(58,155,110,.1); border:1px solid rgba(58,155,110,.3); color:#2c7a55; }
        .ml-banner.warn { background:rgba(232,168,56,.12); border:1px solid rgba(232,168,56,.4); color:%(ink)s; }

        /* reasoning steps */
        .ml-step { display:flex; gap:13px; align-items:flex-start; margin-bottom:14px; font-size:14px; line-height:1.5; }
        .ml-num { flex:0 0 24px; width:24px; height:24px; border-radius:50%; background:%(ink)s; color:#fff;
            font:700 12px 'Inter'; display:flex; align-items:center; justify-content:center; }
        code.ml-tool { font-family:'JetBrains Mono',monospace; font-size:12.5px; background:rgba(232,168,56,.18);
            padding:1px 6px; border-radius:5px; color:#8a5a00; }

        /* account chip in sidebar */
        .ml-chip { display:flex; align-items:center; gap:10px; padding:9px 11px; border-radius:10px;
            background:#fff; border:1px solid rgba(28,28,30,.1); }
        .ml-avatar { flex:0 0 32px; width:32px; height:32px; border-radius:50%;
            background:linear-gradient(150deg,%(amber)s,#c46a3a); display:flex; align-items:center;
            justify-content:center; font:600 12px 'Inter'; color:#fff; }
        .ml-status { display:flex; align-items:center; gap:7px; margin-top:9px; padding:7px 10px;
            border-radius:8px; background:rgba(58,155,110,.1); font-size:11.5px; font-weight:500; color:#2c7a55; }
        </style>
        """
    css = css.replace("%(amber)s", AMBER).replace("%(ink)s", INK).replace("%(green)s", GREEN)
    st.markdown(css, unsafe_allow_html=True)


def account_chip(name: str, user_id: str, library_total: int) -> None:
    initials = "".join(p[0] for p in name.split()[:2]).upper()
    st.markdown(
        f"""
        <div style="font-size:11px;font-weight:500;color:rgba(28,28,30,.45);margin-bottom:8px;">Signed in as</div>
        <div class="ml-chip">
          <div class="ml-avatar">{initials}</div>
          <div style="min-width:0;">
            <div style="font-size:13.5px;font-weight:600;color:{INK};line-height:1.2;">{name}</div>
            <div style="font-size:11px;color:rgba(28,28,30,.45);font-family:'JetBrains Mono',monospace;">{user_id}</div>
          </div>
        </div>
        <div class="ml-status">
          <div style="width:6px;height:6px;border-radius:50%;background:{GREEN};"></div>
          Photos connected · {library_total:,}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _thumb_style(r: PhotoResult) -> str:
    if r.thumbnail_url:
        return f"background-image:url('{r.thumbnail_url}');background-size:cover;background-position:center;"
    return f"background:{r.gradient or '#ddd'};"


def render_results(results: list[PhotoResult]) -> None:
    cards = "".join(
        f'<div class="ml-card"><div class="ml-thumb" style="{_thumb_style(r)}"></div>'
        f'<div class="ml-score">score {r.score:.3f}</div></div>'
        for r in results
    )
    st.markdown(f'<div class="ml-grid">{cards}</div>', unsafe_allow_html=True)


def render_empty() -> None:
    st.markdown(
        '<div class="ml-banner warn"><b>No results found for this query.</b>'
        "&nbsp;Try rewording your search.</div>",
        unsafe_allow_html=True,
    )


def render_reasoning(steps: list[ReasoningStep]) -> None:
    with st.expander("Agent reasoning", expanded=True):
        if not steps:
            st.markdown(
                '<div style="font-style:italic;color:rgba(28,28,30,.4);">No reasoning recorded.</div>',
                unsafe_allow_html=True,
            )
            return
        html = ""
        for i, s in enumerate(steps, start=1):
            html += (
                f'<div class="ml-step"><div class="ml-num">{i}</div>'
                f'<div><code class="ml-tool">{s.tool}</code> {s.detail}</div></div>'
            )
        st.markdown(html, unsafe_allow_html=True)


def render_ingest_tiles(progress: IngestProgress, sample: list) -> None:
    """Small status grid (12 representative tiles)."""
    n = 12
    done_count = round(progress.done / max(progress.total, 1) * n)
    tiles = ""
    for i in range(n):
        grad = sample[i].gradient if i < len(sample) and sample[i].gradient else "#ddd"
        badge = '<div class="ml-badge">✓</div>' if i < done_count else ""
        veil = (
            ""
            if i < done_count
            else '<div style="position:absolute;inset:0;background:rgba(250,250,248,.55);"></div>'
        )
        tiles += f'<div class="ml-tile" style="background:{grad};">{veil}{badge}</div>'
    st.markdown(f'<div class="ml-tiles">{tiles}</div>', unsafe_allow_html=True)
