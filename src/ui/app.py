"""
MemoryLane — agentic photo search (Streamlit UI)

Run:   streamlit run app.py

This file is intentionally thin: it owns *flow & state* and delegates all
look-and-feel to ``memorylane.ui`` and all data to ``memorylane.backend``.
Swap the demo backend for yours in ``memorylane/backend.py::get_backend``.
"""

from __future__ import annotations

import time

import streamlit as st
import streamlit.components.v1 as components
from memorylane import ui
from memorylane.backend import get_backend

st.set_page_config(page_title="MemoryLane", page_icon="🖼️", layout="wide")
ui.inject_css()

ss = st.session_state
# Persist ONE backend across reruns — Streamlit re-executes this whole script on
# every interaction, and HttpBackend caches the signed-in user's tenant_id and
# picker session in-instance. A fresh instance per rerun would lose both.
if "backend" not in ss:
    ss.backend = get_backend()
backend = ss.backend
ss.setdefault("authenticated", False)
ss.setdefault("user_id", "")
ss.setdefault("tenant_id", "")
ss.setdefault("display_name", "")
ss.setdefault("photo_phase", "launch")  # launch | picking | ingesting | done
ss.setdefault("picker", None)  # PickerSession
ss.setdefault("selected_media", [])
ss.setdefault("last_progress", None)
ss.setdefault("search", None)  # SearchResult


# --------------------------------------------------------------------------- #
#  LOGIN PAGE  (gate — separate "page" via session_state, no main UI yet)     #
# --------------------------------------------------------------------------- #
def render_login() -> None:
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.markdown("<div style='height:8vh'></div>", unsafe_allow_html=True)
        st.markdown("# MemoryLane")
        st.caption("Sign in to search your memories with AI.")
        user_id = st.text_input("User ID", placeholder="your-user-id", key="login_user")
        tenant_id = st.text_input("Tenant ID", placeholder="your-tenant-id", key="login_tenant")
        st.caption(
            "You'll link your Google Photos library through the Picker so the agent can search it."
        )
        if st.button("Sign in & connect Photos", type="primary", use_container_width=True):
            if backend.sign_in(user_id, tenant_id):
                ss.authenticated = True
                ss.user_id = user_id
                ss.tenant_id = tenant_id
                # TODO: map user_id -> real display name from your user service.
                ss.display_name = user_id.replace("-", " ").replace("_", " ").title() or "User"
                st.rerun()
            else:
                st.error("Enter a valid User ID and Tenant ID to continue.")
        st.markdown(
            "<div style='text-align:center;margin-top:18px;font-size:11.5px;color:rgba(28,28,30,.4);"
            "font-family:JetBrains Mono,monospace;'>dev mode · no password required</div>",
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------- #
#  SIDEBAR  (persistent across tabs)                                          #
# --------------------------------------------------------------------------- #
def render_sidebar() -> int:
    with st.sidebar:
        st.markdown("## MemoryLane")
        ui.account_chip(ss.display_name, ss.user_id, backend.library_count(ss.user_id))
        st.divider()
        st.markdown("**Settings**")
        limit = st.slider("Result limit", 1, 50, 12)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        if st.button("↩ Sign out", use_container_width=True):
            for k in ("authenticated", "user_id", "tenant_id", "search", "photo_phase"):
                ss.pop(k, None)
            st.rerun()
    return limit


# --------------------------------------------------------------------------- #
#  SEARCH TAB                                                                 #
# --------------------------------------------------------------------------- #
def render_search_tab(limit: int) -> None:
    query = st.text_input("What are you looking for?", placeholder="sunsets at the beach")
    go = st.button("Search", type="primary")

    if go:
        with st.spinner("Agent reasoning…"):
            ss.search = backend.search(ss.user_id, query, limit)

    result = ss.search
    if result is not None:
        if result.results:
            ui.render_results(result.results)
        else:
            ui.render_empty()
        ui.render_reasoning(result.reasoning)


# --------------------------------------------------------------------------- #
#  PHOTOS TAB  (Picker → redirect → ingest with live progress)                #
# --------------------------------------------------------------------------- #
def render_photos_tab() -> None:
    st.caption("Pick photos from Google Photos to ingest into your searchable library.")
    phase = ss.photo_phase

    # ---- launch ----------------------------------------------------------- #
    if phase == "launch":
        # Real backends need a one-time Google OAuth grant before the Picker works.
        connect = backend.connect_url(ss.user_id)
        if connect:
            st.link_button("Connect Google Photos ↗", connect)
            st.caption("Connect once (opens Google in a new tab), then open the Picker below.")
        with st.container(border=True):
            st.markdown("#### Select from Google Photos")
            st.write(
                "Opening the Picker takes you to Google Photos. After you choose "
                "your photos, you'll be brought back here automatically to ingest them."
            )
            if st.button("Open Google Photos Picker ↗", type="primary"):
                try:
                    ss.picker = backend.create_picker_session(ss.user_id)
                    ss.photo_phase = "picking"
                    st.rerun()
                except Exception as exc:  # surface any wiring error to the user
                    st.error(str(exc))
        st.write(
            f"**{backend.library_count(ss.user_id):,}** photos already ingested in your library."
        )

    # ---- picking (open google + poll the session) ------------------------- #
    elif phase == "picking":
        picker = ss.picker
        # Auto-open the Picker URL in a new tab on first arrival here.
        components.html(
            f"<script>window.open('{picker.picker_uri}', '_blank');</script>",
            height=0,
        )
        st.link_button("Open Google Photos Picker ↗", picker.picker_uri, type="primary")
        st.info("Waiting for you to finish selecting in Google Photos…")
        # Poll: when the user is done, advance automatically.
        session = backend.poll_picker_session(picker.id)
        if session.media_items_set:
            ss.selected_media = backend.list_picked_media(picker.id)
            ss.photo_phase = "ingesting"
            st.rerun()
        time.sleep(2)
        st.rerun()

    # ---- ingesting (blocking progress) ------------------------------------ #
    elif phase == "ingesting":
        media = ss.selected_media
        st.markdown(
            '<div class="ml-banner ok"><div style="width:20px;height:20px;border-radius:50%;'
            "background:#3a9b6e;color:#fff;display:flex;align-items:center;justify-content:center;"
            'font-weight:700;">✓</div> Imported your selection from Google Photos.</div>',
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        m_sel = c1.empty()
        m_tot = c2.empty()
        m_pct = c3.empty()
        bar = st.progress(0, text=f"Ingesting 0 of {len(media)}…")
        tiles = st.empty()

        for p in backend.ingest(ss.user_id, media):
            pct = int(p.done / p.total * 100)
            m_sel.metric("Selected to ingest", p.total)
            m_tot.metric("Total ingested", f"{p.library_total:,}")
            m_pct.metric("This batch", f"{pct}%")
            bar.progress(p.done / p.total, text=f"Ingesting {p.done} of {p.total}…")
            with tiles.container():
                ui.render_ingest_tiles(p, media)
            ss.last_progress = p

        ss.photo_phase = "done"
        st.rerun()

    # ---- done ------------------------------------------------------------- #
    elif phase == "done":
        p = ss.last_progress
        st.markdown(
            f'<div class="ml-banner ok"><div><b>Ingestion complete</b><br>'
            f'<span style="font-weight:400;color:rgba(28,28,30,.6)">{p.total} new photos are now searchable.</span></div></div>',
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Selected to ingest", p.total)
        c2.metric("Total ingested", f"{p.library_total:,}")
        c3.metric("This batch", "100%")
        ui.render_ingest_tiles(p, ss.selected_media)
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        if st.button("Add more"):
            ss.photo_phase = "launch"
            ss.selected_media = []
            st.rerun()


# --------------------------------------------------------------------------- #
#  ROUTER                                                                     #
# --------------------------------------------------------------------------- #
if not ss.authenticated:
    render_login()
    st.stop()

st.markdown("# MemoryLane")
st.caption("Agentic photo search")

limit = render_sidebar()
search_tab, photos_tab = st.tabs(["Search", "Photos"])
with search_tab:
    render_search_tab(limit)
with photos_tab:
    render_photos_tab()
