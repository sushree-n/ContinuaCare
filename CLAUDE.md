# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repo is an **implemented hackathon build**, not a skeleton. All three packages under `packages/` have working code. Two reference docs sit at the root:

- [ARCHITECTURE.md](ARCHITECTURE.md) — diagrammed, code-grounded overview of the system as actually built (component map, state machine, sequence flow, agent pipeline, ERD, API surface). **Start here.**
- [CONTINUACARE_MASTER.md](CONTINUACARE_MASTER.md) — the original technical spec. It still carries useful design intent, but parts have drifted from the code; where they disagree, **the code wins** and `ARCHITECTURE.md` reflects it. Empty/unwritten files: `render.yaml` and the root `README.md`.

ContinuaCare is a hackathon (June 26–27, 2026) TCM (Transitions of Care Management) automation platform: it detects a hospital discharge, places automated voice follow-up calls to patients, escalates red-flag symptoms in real time, and generates CMS-compliant TCM billing documentation (CPT 99495/99496).

## Monorepo layout

Three independently-deployed packages:

- `packages/backend/` — FastAPI + async SQLAlchemy + PostgreSQL. The orchestration brain: REST API, episode state machine, and the non-realtime LLM calls. Triage runs on **DeepSeek-V4-Pro via BaseTen** (`services/triage.py`); the post-call summary and billing doc run on **Claude Sonnet 4.5 via OpenRouter** (`services/summarizer.py`, `services/billing_doc.py`). All three use the OpenAI-compatible SDK (`AsyncOpenAI`), not the Anthropic SDK. Entry: `main.py` (`uvicorn main:app`); on startup it `create_all`s the tables. Routers: `patients`, `episodes`, `calls`, `escalations`, `billing`, `demo`.
- `packages/agent/` — LiveKit voice agent worker (LiveKit Agents v1.5+, `AgentServer` / `@server.rtc_session(agent_name="continuacare")` in `agent.py`; `CareAgent` in `care_agent.py`; tools in `tools.py`; prompt builder in `prompts.py`). Runs the live phone call: Silero VAD + Deepgram STT (`nova-3-medical`) → **Claude Sonnet 4.5 via OpenRouter** (LiveKit `openai` plugin) → ElevenLabs TTS (`eleven_turbo_v2`). Talks back to the backend over HTTP (`BACKEND_URL`) to post escalations and call completions.
- `packages/frontend/` — React + TypeScript + Vite, Zustand store (`src/store/useStore.ts`), axios client (`src/api.ts`). Dashboard polls `/escalations/open` every 3s so red-flag alerts surface live. **Defaults to mock/seed data** (`USE_MOCK`); set `VITE_USE_MOCK=false` and point `VITE_API_URL` at the backend for live mode.

## Architecture: the episode state machine

Everything centers on `TCMEpisode.state` (`packages/backend/models.py`), which advances through:
`DISCHARGE_DETECTED → AWAITING_CALL → CALL_IN_PROGRESS → CALL_COMPLETE → ESCALATED → VISIT_SCHEDULED → READY_TO_BILL → VOIDED`.

The end-to-end flow (see [ARCHITECTURE.md](ARCHITECTURE.md) §3 for the sequence diagram):

1. `POST /patients`, then `POST /episodes` (the discharge event). `POST /episodes` returns immediately and a FastAPI **BackgroundTask** runs `services/triage.py` (DeepSeek discharge analysis → `structured_extract`, `complexity`, `cpt_code`), computes TCM deadlines inline (`_business_days_from`), and sets state → `AWAITING_CALL`. The same task then `asyncio.sleep`s `DEMO_CALL_DELAY_SECONDS` and POSTs `/calls/trigger/{episode_id}`.
2. `POST /calls/trigger/{episode_id}` creates a `Call`, sets state → `CALL_IN_PROGRESS`, and (background) calls `place_outbound_call()`, which **dispatches the LiveKit agent** (`agent_dispatch.create_dispatch`). The **agent itself** then places the SIP call (`create_sip_participant`, `wait_until_answered=True`) over LiveKit → Twilio.
3. The agent runs the call. **Mid-call red flag → agent calls its `escalate()` tool → `POST /escalations` (severity `urgent`) → state `ESCALATED` → dashboard lights up red**, then `transfer_to_human()` cold-transfers via SIP REFER. This escalation path is the most important behavior in the product. On any end path (agent `end_call()`, patient hangup, or error), the agent's `post_call_complete` shutdown hook POSTs `/calls/{id}/complete` with the transcript → `services/summarizer.py` (Claude via OpenRouter) → state `CALL_COMPLETE` (only if still `CALL_IN_PROGRESS`).
4. No-answer → `POST /calls/{id}/no-answer`; `services/call_manager.py` escalates `monitor` after `MAX_ATTEMPTS = 3` (3 attempts is still CMS-billable). **Note:** the between-attempt retry scheduler (`_schedule_retry`) is currently a logging stub.
5. Visit scheduling (HIGH complexity = 7-day window/CPT 99496, MODERATE = 14-day/CPT 99495). `VISIT_SCHEDULED`/`VOIDED` are reached only via the manual `PATCH /episodes/{id}/state` endpoint; the agent's `schedule_appointment` tool records the booking outcome but does not itself advance episode state.
6. `POST /episodes/{id}/generate-billing` → `services/billing_doc.py` (Claude via OpenRouter) produces the CPT claim, the CMS required elements, and a draft clinician note; sets `ready_to_bill` and state → `READY_TO_BILL`.

Key coupling to preserve: the three backend prompts live in `packages/backend/prompts.py` and return **raw JSON only** — triage/summary/billing parsing depends on that (the services strip code fences and `json.loads`). The agent's system prompt is built separately in `packages/agent/prompts.py` via `build_agent_prompt()`, which injects diagnosis-specific warning signs from the `WARNING_SIGNS` map.

## Writing LiveKit code

LiveKit Agents evolves fast and any agent snippets in the master doc (§7) are stale — the real worker is on the **v1.5+ `AgentServer` API**. **Before writing or editing any LiveKit-related code** (the `packages/agent/` worker, `AgentSession`/`Agent`, plugins, SIP/outbound dialing, dispatch), ground it against the live LiveKit MCP docs — see https://docs.livekit.io/mcp. Use the `claude.ai LiveKit` MCP tools (start with `docs_search`/`get_pages`, then `code_search` for SDK specifics) to confirm current APIs rather than relying on the spec or training memory.

## Complexity / billing rules (don't break these)

- `ComplexityLevel.HIGH` → CPT `99496`, face-to-face within **7 days**. `MODERATE` → CPT `99495`, within **14 days**. When triage is uncertain, classify **HIGH** (patient safety).
- Contact deadline = discharge + 2 **business days** (`_business_days_from` in `routers/episodes.py`, Mon–Fri). Visit deadline = discharge + `visit_window_days`. Billing date = discharge + 30 days (date of service).
- The multi-call cadence by complexity (`CALL_SCHEDULE`, high `[0,2,6,13,20,29]`, moderate `[1,6,13,29]`) is **design intent in the spec but not yet implemented** — there is no `scheduler.py`, and `CallSchedule` rows are not created by the current flow (the live flow triggers one call after triage, plus manual re-trigger / `/demo/fast-forward`).

## Demo mode

`DEMO_MODE=true` unlocks the demo-only endpoints `POST /demo/fast-forward/{episode_id}` and `GET /demo/reset` (wipe all data between demos), and is required for them (they 403 otherwise). Timing is compressed for live demos: `DEMO_CALL_DELAY_SECONDS` (code default 15) before the first call, and a 10s no-answer retry delay vs 3600s in prod (`services/call_manager.py`).

## Commands

Backend (`packages/backend/`):
```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000        # API at :8000, docs at :8000/docs
# tables are auto-created on startup; alembic is configured if you prefer migrations:
alembic upgrade head                 # apply DB migrations
alembic revision --autogenerate -m "msg"   # create a migration after model changes
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

No test suite or linter is defined; do not add test cases.

## Environment

Copy `.env.example` → `.env` (never commit `.env`). The keys the code actually reads: `DATABASE_URL` (async — `postgresql+asyncpg://...`), `BASETEN_API_KEY` (triage / DeepSeek-V4-Pro), `OPENROUTER_API_KEY` + optional `OPENROUTER_BASE_URL` (summary, billing, and the agent LLM — Claude Sonnet 4.5), `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID`, `LIVEKIT_URL`/`LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`/`LIVEKIT_SIP_TRUNK_ID` (outbound SIP trunk, `ST_…`), `CARE_TEAM_PHONE_NUMBER` (transfer target), `BACKEND_URL` (agent + demo), `VITE_API_URL`/`VITE_USE_MOCK` (frontend), `DEMO_MODE`/`DEMO_CALL_DELAY_SECONDS`. `TWILIO_*` configure the SIP trunk (telephony) but are not read directly by the Python. Note: `.env.example` still lists `ANTHROPIC_API_KEY` — the code does **not** use the Anthropic SDK (LLM traffic goes through BaseTen and OpenRouter). Patient phone numbers must be E.164 (`+1XXXXXXXXXX`).
