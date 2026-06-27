# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repo is currently a **skeleton**. Only [CONTINUACARE_MASTER.md](CONTINUACARE_MASTER.md) has real content; all source files under `packages/` are empty `.gitkeep` placeholders, and `.env.example`, `render.yaml`, and `README.md` are empty. `CONTINUACARE_MASTER.md` is the canonical technical spec — treat it as the source of truth for file layout, models, endpoints, prompts, and the demo flow, and keep it in sync when implementing. File/symbol names referenced below come from that spec, not from existing code, so verify a file exists before assuming its contents.

ContinuaCare is a hackathon (June 26–27, 2026) TCM (Transitions of Care Management) automation platform: it detects a hospital discharge, places automated voice follow-up calls to patients, escalates red-flag symptoms in real time, and generates CMS-compliant TCM billing documentation (CPT 99495/99496).

## Monorepo layout

Three independently-deployed packages (see `render.yaml` spec in the master doc, §12):

- `packages/backend/` — FastAPI + async SQLAlchemy + PostgreSQL. The orchestration brain: REST API, episode state machine, scheduling (APScheduler), and all Claude calls for non-realtime analysis (triage, summaries, billing docs). Entry: `main.py` (`uvicorn main:app`).
- `packages/agent/` — LiveKit voice agent worker (`agent.py`). Runs the live phone call: Deepgram STT (`nova-3-medical`) → Claude Sonnet (`claude-sonnet-4-6`) LLM → ElevenLabs TTS, dialed out over LiveKit SIP → Twilio. Talks back to the backend over HTTP (`BACKEND_URL`) to post escalations and call completions.
- `packages/frontend/` — React + TypeScript + Vite, Zustand store, axios client (`src/api.ts`), react-big-calendar. Dashboard polls `/escalations/open` every 3s so red-flag alerts surface live.

## Architecture: the episode state machine

Everything centers on `TCMEpisode.state` (`packages/backend/models.py`), which advances through:
`DISCHARGE_DETECTED → AWAITING_CALL → CALL_IN_PROGRESS → CALL_COMPLETE → ESCALATED → VISIT_SCHEDULED → READY_TO_BILL → VOIDED`.

The end-to-end flow (master doc §5 is the line-by-line reference):

1. `POST /patients` then `POST /episodes` (the discharge event). Episode creation synchronously runs `services/triage.py` (Claude discharge analysis → `structured_extract`, `complexity`), computes TCM deadlines, and `services/scheduler.py` enqueues `CallSchedule` rows. State → `AWAITING_CALL`.
2. APScheduler fires → `POST /calls/trigger/{episode_id}` → creates a `Call`, launches `place_outbound_call()`, state → `CALL_IN_PROGRESS`.
3. The agent runs the call. **Mid-call red flag → agent calls its `escalate()` tool → `POST /escalations` (severity `urgent`) → state `ESCALATED` → dashboard lights up red.** This escalation path is the most important behavior in the product. Normal completion → agent `end_call()` → `POST /calls/{id}/complete` → `services/summarizer.py` (Claude) → state `CALL_COMPLETE`.
4. No-answer → `POST /calls/{id}/no-answer`; `services/call_manager.py` retries up to `MAX_ATTEMPTS = 3`, then escalates `monitor` (3 attempts is still CMS-billable).
5. Visit scheduling (HIGH complexity = 7-day window/CPT 99496, MODERATE = 14-day/CPT 99495) → `VISIT_SCHEDULED` → `READY_TO_BILL`.
6. `POST /episodes/{id}/generate-billing` → `services/billing_doc.py` (Claude) produces the CPT recommendation, the 4 CMS required elements, and a draft clinician note.

Key coupling to preserve: the three Claude prompts live in `packages/backend/prompts.py` (master doc §6) and return **raw JSON only** — triage/summary/billing parsing depends on that. The agent's system prompt is built separately in `packages/agent/prompts.py` via `build_agent_prompt()`, which injects diagnosis-specific warning signs from the `WARNING_SIGNS` map.

## Writing LiveKit code

LiveKit Agents evolves fast and the spec's agent snippets (master doc §7) may be stale. **Before writing or editing any LiveKit-related code** (the `packages/agent/` worker, `AgentSession`/`Agent`, plugins, SIP/outbound dialing, dispatch), ground it against the live LiveKit MCP docs — see https://docs.livekit.io/mcp. Use the `claude.ai LiveKit` MCP tools (start with `docs_search`/`get_pages`, then `code_search` for SDK specifics) to confirm current APIs rather than relying on the spec or training memory.

## Complexity / billing rules (don't break these)

- `ComplexityLevel.HIGH` → CPT `99496`, face-to-face within **7 days**. `MODERATE` → CPT `99495`, within **14 days**. When triage is uncertain, classify **HIGH** (patient safety).
- Contact deadline = discharge + 2 **business days** (`add_business_days`, Mon–Fri). Billing date = discharge + 30 days (date of service).
- Call cadence by complexity is fixed in `CALL_SCHEDULE` (high `[0,2,6,13,20,29]`, moderate `[1,6,13,29]` day-offsets from discharge).

## Demo mode

`DEMO_MODE=true` compresses timing for live demos: `DEMO_CALL_DELAY_SECONDS` (default 5) before the first call, 10s retry delay (vs 60min in prod). Demo-only endpoints: `POST /demo/fast-forward/{episode_id}` and `GET /demo/reset` (wipe all data between demos). Build these — the Saturday demo depends on them (master doc §14).

## Commands

These come from the spec (master doc §13); adjust as real files land.

Backend (`packages/backend/`):
```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head                 # apply DB migrations
alembic revision --autogenerate -m "msg"   # create a migration after model changes
uvicorn main:app --reload --port 8000        # API at :8000, docs at :8000/docs
```

Agent (`packages/agent/`, separate venv):
```bash
pip install -r requirements.txt
python agent.py
```

Frontend (`packages/frontend/`):
```bash
npm install
npm run dev        # Vite dev server at :5173
npm run build      # production build to dist/
```

Local Postgres:
```bash
docker run --name continuacare-db -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=continuacare -p 5432:5432 -d postgres
```

No test suite or linter is defined in the spec yet; do not add test cases.

## Environment

Copy `.env.example` → `.env` (never commit `.env`). Required keys (master doc §2): `DATABASE_URL` (async — `postgresql+asyncpg://...`), `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID`, `LIVEKIT_URL`/`LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`/`LIVEKIT_SIP_TRUNK_ID`, `TWILIO_*`, `DEEPGRAM_API_KEY`, `BASETEN_API_KEY`/`BASETEN_WHISPER_URL`, `VITE_API_URL` (frontend), `BACKEND_URL` (agent). Patient phone numbers must be E.164 (`+1XXXXXXXXXX`).