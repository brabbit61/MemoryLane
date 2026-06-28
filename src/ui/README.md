# MemoryLane — Streamlit UI (`src/ui`)

Agentic photo search front-end. A user describes a memory in natural language; the
agent service retrieves matching photos. Photos enter the library via the Google
Photos **Picker** → the ingestion service downloads, embeds & indexes them.

Warm/minimal theme, amber accent (`#E8A838`), charcoal text, soft off-white background.

## Run

Demo mode (no infra — fully clickable on fake data):

```bash
cd src/ui
pip install -r requirements.txt
streamlit run app.py
```

Wired to the real services (set `MEMORYLANE_USE_HTTP=1`):

```bash
MEMORYLANE_USE_HTTP=1 \
MEMORYLANE_AGENT_URL=http://localhost:8003 \
MEMORYLANE_SEARCH_URL=http://localhost:8002 \
MEMORYLANE_INGESTION_URL=http://localhost:8001 \
streamlit run app.py
```

Or just `docker compose up -d` from the repo root — the `ui` service runs on
**http://localhost:8501**, already pointed at the in-network services.

## Architecture

```
src/ui/
├── app.py                       # flow + state only (login gate, sidebar, tabs)
├── .streamlit/config.toml       # theme (colors/font)
├── requirements.txt             # streamlit + requests
├── Dockerfile
├── tests/test_backend.py        # mocked-HTTP wiring checks for HttpBackend
└── memorylane/
    ├── backend.py               # ← THE SEAM: protocol + get_backend() + DemoBackend
    ├── integration_example.py   # HttpBackend — the real wiring to the services
    └── ui.py                    # CSS + render helpers (the look)
```

The UI never imports service internals — it only calls a `MemoryLaneBackend`
(`backend.py`). `get_backend()` returns the real `HttpBackend` when
`MEMORYLANE_USE_HTTP` is set, else the `DemoBackend`.

## How it maps to the real APIs

| Backend method | Service call |
| --- | --- |
| `sign_in(user_id, tenant_id)` | `GET ingestion /oauth/google/init?user_id=` — 404 ⇒ unknown user (no password; just an existence check). |
| `connect_url(user_id)` | same endpoint, returns the Google OAuth URL for the *Connect* link. |
| `library_count(user_id)` | `GET search /photos/count?tenant_id&user_id`. |
| `create_picker_session` / `poll_picker_session` | `POST ingestion /sync/google/{uid}/start`, `GET …/session/{sid}`. |
| `ingest(user_id, _)` | `POST ingestion /sync/google/{uid}/ingest/{sid}` (background job). |
| `search(user_id, query, limit)` | `POST agent /agent/search` → results grid + reasoning. |

Both `user_id` and `tenant_id` are entered on the login page (UUIDs); `tenant_id`
scopes every downstream query. Local dev seeds tenant
`00000000-0000-0000-0000-000000000001` / user `00000000-0000-0000-0000-000000000002`
(see `infra/db/init.sql`).

## Known gaps (honest, not faked)

- **Ingest progress** — the ingest endpoint is fire-and-forget, so the Photos tab
  shows "started in background" rather than a live per-photo bar. Add a status
  endpoint to make it live.
- **Picked-media preview** — the API ingests picked items server-side and doesn't
  list them back, so the per-photo ingest tiles are minimal on the live path.

## Theme

Colors live in `.streamlit/config.toml` and the matching constants/CSS at the top of
`memorylane/ui.py`. Fonts: Newsreader (headings), Inter (body), JetBrains Mono (scores/IDs).
