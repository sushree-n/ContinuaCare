# ContinuaCare — Master Technical Spec
> TCM Automation Platform | NYC Healthcare x AI Hackathon | June 26–27, 2026

> **Status:** this document is the original spec, now reconciled with the implemented code. Where the
> running system differs from the early design, the doc has been updated to match the code and the
> remaining design-only items are flagged inline. For a diagrammed overview see
> [ARCHITECTURE.md](ARCHITECTURE.md). When code and doc disagree, **the code wins**.

---

## 0. Quick Reference

| Item | Value |
|---|---|
| Repo | `continuacare` (monorepo) |
| Backend URL (local) | `http://localhost:8000` |
| Frontend URL (local) | `http://localhost:5173` |
| API Docs (auto) | `http://localhost:8000/docs` |
| Voice Agent | LiveKit Agents v1.5+ + Deepgram + ElevenLabs + Twilio SIP |
| Triage LLM | DeepSeek-V4-Pro via **BaseTen** (`services/triage.py`) |
| Summary / Billing / Agent LLM | Claude Sonnet 4.5 (`anthropic/claude-sonnet-4-5`) via **OpenRouter** |
| LLM SDK | OpenAI-compatible (`AsyncOpenAI`) + LiveKit `openai` plugin — **no Anthropic SDK** |
| DB | PostgreSQL (Docker local, Render managed in prod) |

---

## 1. Monorepo Structure

Actual on-disk layout (files that exist today):

```
continuacare/
├── packages/
│   ├── backend/
│   │   ├── main.py                 ← FastAPI app, lifespan create_all, CORS, routers
│   │   ├── database.py             ← async engine + AsyncSessionLocal
│   │   ├── models.py
│   │   ├── prompts.py              ← DISCHARGE_ANALYSIS / CALL_SUMMARY / BILLING_DOC
│   │   ├── routers/
│   │   │   ├── patients.py
│   │   │   ├── episodes.py         ← create + triage background task + deadlines
│   │   │   ├── calls.py            ← trigger / complete / no-answer + summarizer
│   │   │   ├── escalations.py
│   │   │   ├── billing.py          ← generate-billing + billing-doc edits
│   │   │   └── demo.py             ← fast-forward + reset (DEMO_MODE only)
│   │   ├── services/
│   │   │   ├── triage.py           ← BaseTen DeepSeek-V4-Pro: discharge analysis + complexity
│   │   │   ├── summarizer.py       ← OpenRouter Claude: post-call summary
│   │   │   ├── billing_doc.py      ← OpenRouter Claude: claim documentation
│   │   │   └── call_manager.py     ← no-answer handling (retry scheduler is a stub)
│   │   ├── alembic/                ← migrations (tables also auto-created on startup)
│   │   └── requirements.txt
│   ├── agent/
│   │   ├── agent.py                ← LiveKit AgentServer worker + entrypoint + SIP dial
│   │   ├── care_agent.py           ← CareAgent(Agent): greeting, tts/transcript hooks
│   │   ├── tools.py                ← escalate / transfer_to_human / schedule_appointment / end_call
│   │   ├── prompts.py              ← build_agent_prompt + WARNING_SIGNS + build_greeting
│   │   ├── transcript_utils.py     ← low-confidence transcript handling
│   │   ├── tts_utils.py            ← pronunciation fixes before TTS
│   │   └── requirements.txt
│   └── frontend/
│       ├── src/
│       │   ├── api.ts              ← axios client + view-model adapter (mock by default)
│       │   ├── types.ts
│       │   ├── mockData.ts         ← seed roster for mock mode
│       │   ├── App.tsx / main.tsx
│       │   ├── pages/              ← Landing.tsx, Demo.tsx
│       │   ├── lib/                ← view-model helpers
│       │   └── store/useStore.ts   ← Zustand state + 3s escalation polling
│       └── package.json
├── ARCHITECTURE.md
├── CLAUDE.md
├── CONTINUACARE_MASTER.md
├── .env.example
├── .gitignore
├── render.yaml                     ← not yet written (deployment intent in §12)
└── README.md                       ← empty
```

> **Drift from the early design:** there is **no** `backend/schemas.py` (Pydantic models live inside the
> routers) and **no** `backend/services/scheduler.py` (see §9). The frontend uses `pages/Landing.tsx` +
> `pages/Demo.tsx` rather than the originally-planned Dashboard/PatientDetail/BillingDoc component tree.

---

## 2. Environment Variables

Copy `.env.example` → `.env`; never commit `.env`. The keys **the code actually reads**:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:pass@localhost:5432/continuacare

# BaseTen — triage via DeepSeek-V4-Pro (OpenAI-compatible endpoint)
BASETEN_API_KEY=

# OpenRouter — summary, billing, and the live agent LLM (Claude Sonnet 4.5)
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1   # optional, this is the default

# ElevenLabs TTS
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=                # warm voice for patient calls

# Deepgram STT
DEEPGRAM_API_KEY=

# LiveKit
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
LIVEKIT_SIP_TRUNK_ID=               # outbound SIP trunk (ST_…), created via `lk sip outbound create`

# Twilio — configures the SIP trunk / telephony (not read directly by the Python)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=                # e.g. +1XXXXXXXXXX

# Care team transfer target (agent transfer_to_human SIP REFER)
CARE_TEAM_PHONE_NUMBER=             # e.g. +1XXXXXXXXXX

# Agent + demo
BACKEND_URL=http://localhost:8000

# Frontend
VITE_API_URL=http://localhost:8000
VITE_USE_MOCK=true                  # mock/seed data unless set to "false"

# Demo
DEMO_MODE=true                      # unlocks /demo/* endpoints
DEMO_CALL_DELAY_SECONDS=15          # delay after triage before the first call (code default 15)
```

> **Note:** `.env.example` currently also lists `ANTHROPIC_API_KEY` and omits `OPENROUTER_API_KEY` /
> `CARE_TEAM_PHONE_NUMBER` / `VITE_USE_MOCK`. The code does **not** use the Anthropic SDK — LLM traffic
> goes through BaseTen (triage) and OpenRouter (everything else). Update `.env.example` to the set above.

---

## 3. Database Models (`packages/backend/models.py`)

### Enums

```python
class EpisodeState(enum.Enum):
    DISCHARGE_DETECTED  = "discharge_detected"
    AWAITING_CALL       = "awaiting_call"
    CALL_IN_PROGRESS    = "call_in_progress"
    CALL_COMPLETE       = "call_complete"
    ESCALATED           = "escalated"
    VISIT_SCHEDULED     = "visit_scheduled"
    READY_TO_BILL       = "ready_to_bill"
    VOIDED              = "voided"

class ComplexityLevel(enum.Enum):
    HIGH     = "high"      # CPT 99496 — 7-day visit window
    MODERATE = "moderate"  # CPT 99495 — 14-day visit window

class CallStatus(enum.Enum):
    SCHEDULED   = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    NO_ANSWER   = "no_answer"
    FAILED      = "failed"

class EscalationStatus(enum.Enum):
    OPEN           = "open"
    RESOLVED       = "resolved"
```

### Patient

```python
class Patient(Base):
    __tablename__ = "patients"
    id                  = Column(String, primary_key=True, default=uuid4)
    name                = Column(String, nullable=False)
    age                 = Column(Integer)
    phone               = Column(String, nullable=False)   # E.164 format: +1XXXXXXXXXX
    diagnosis           = Column(String, nullable=False)
    medications         = Column(JSON)                     # list[str]
    created_at          = Column(DateTime, default=datetime.utcnow)
```

> A `patient_history` / `prior_readmissions` / `lives_alone` column existed in early drafts but was
> removed (see the alembic migration `…remove_lives_alone_prior_readmissions`). Don't reintroduce them.

### TCMEpisode

```python
class TCMEpisode(Base):
    __tablename__ = "episodes"
    id                  = Column(String, primary_key=True, default=uuid4)
    patient_id          = Column(String, ForeignKey("patients.id"))

    # State
    state               = Column(Enum(EpisodeState), default=EpisodeState.DISCHARGE_DETECTED)

    # Discharge (Day 0)
    discharge_date      = Column(DateTime, nullable=False)
    discharge_notes     = Column(Text)

    # Triage output (DeepSeek)
    structured_extract  = Column(JSON)    # full triage JSON: diagnoses, medications, flags, follow_up, …
    complexity          = Column(Enum(ComplexityLevel))
    triage_rationale    = Column(Text)                     # NOTE: field name is triage_rationale
    visit_window_days   = Column(Integer)                   # 7 or 14
    contact_deadline    = Column(DateTime)                  # Day 0 + 2 business days
    visit_deadline      = Column(DateTime)                  # Day 0 + 7 or 14
    billing_date        = Column(DateTime)                  # Day 0 + 30

    # Visit tracking
    face_to_face_date   = Column(DateTime)
    med_rec_completed   = Column(Boolean, default=False)
    med_rec_date        = Column(DateTime)

    # Billing
    cpt_code            = Column(String)                    # "99495" or "99496"
    billing_doc         = Column(Text)                      # JSON string of the generated claim packet
    ready_to_bill       = Column(Boolean, default=False)

    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, onupdate=datetime.utcnow)
```

### Call

```python
class Call(Base):
    __tablename__ = "calls"
    id              = Column(String, primary_key=True, default=uuid4)
    episode_id      = Column(String, ForeignKey("episodes.id"))
    patient_id      = Column(String, ForeignKey("patients.id"))
    livekit_room    = Column(String)                        # room name for this call
    attempt_number  = Column(Integer, default=1)            # 1, 2, or 3
    scheduled_at    = Column(DateTime)
    started_at      = Column(DateTime)
    ended_at        = Column(DateTime)
    status          = Column(Enum(CallStatus), default=CallStatus.SCHEDULED)
    transcript      = Column(Text)
    summary         = Column(Text)                          # summarizer output
    flags           = Column(JSON)                          # list[str] detected symptoms
    structured_data = Column(JSON)                          # summarizer fields + agent visit outcome
```

### Escalation + CallSchedule

```python
class Escalation(Base):
    __tablename__ = "escalations"
    id              = Column(String, primary_key=True, default=uuid4)
    episode_id      = Column(String, ForeignKey("episodes.id"))
    call_id         = Column(String, ForeignKey("calls.id"), nullable=True)
    reason          = Column(Text, nullable=False)
    severity        = Column(String)                        # "urgent" | "monitor"
    status          = Column(Enum(EscalationStatus), default=EscalationStatus.OPEN)
    created_at      = Column(DateTime, default=datetime.utcnow)
    acknowledged_at = Column(DateTime)

class CallSchedule(Base):
    __tablename__ = "call_schedules"
    id              = Column(String, primary_key=True, default=uuid4)
    episode_id      = Column(String, ForeignKey("episodes.id"))
    patient_id      = Column(String, ForeignKey("patients.id"))
    scheduled_for   = Column(DateTime, nullable=False)
    day_number      = Column(Integer)
    completed       = Column(Boolean, default=False)
```

> `CallSchedule` is defined and read by the calendar (`GET /episodes/{id}/schedule`) and demo-reset
> endpoints, but **no rows are created** by the current flow — it backs the unbuilt multi-call cadence (§9).

---

## 4. API Endpoints (`packages/backend/routers/`)

#### Patients (`patients.py`)

```
POST   /patients                    Create patient
GET    /patients                    List all patients (dashboard roster)
GET    /patients/{id}               Single patient
GET    /patients/{id}/episode       Most recent active episode (agent reads this at call start)
```

#### Episodes (`episodes.py`)

```
POST   /episodes                    Create TCM episode (discharge event) → triage + auto-trigger (background)
GET    /episodes/{id}               Episode detail + state
PATCH  /episodes/{id}/state         Manual state transition (demo / coordinator override)
GET    /episodes/{id}/schedule      Calendar view — calls + scheduled slots
```

#### Calls (`calls.py`)

```
POST   /calls/trigger/{episode_id}  Create Call, dispatch agent, state → CALL_IN_PROGRESS
POST   /calls/{id}/complete         Agent posts transcript + structured_data → summarizer (no summary in body)
POST   /calls/{id}/no-answer        Agent reports no answer → retry / escalate
GET    /calls/episode/{episode_id}  All calls for an episode
```

#### Escalations (`escalations.py`)

```
POST   /escalations                 Agent posts red flag mid-call ← MOST IMPORTANT (state → ESCALATED)
GET    /escalations/open            Dashboard polls for active alerts (every 3s)
PATCH  /escalations/{id}            Resolve (body: { "status": "resolved" })
```

#### Billing (`billing.py`)

```
POST   /episodes/{id}/generate-billing   Claude (via OpenRouter) generates claim packet, state → READY_TO_BILL
PATCH  /episodes/{id}/billing-doc         Save clinician note edits / face-to-face date / med-rec
```

#### Demo (`demo.py`) + health (`main.py`)

```
POST   /demo/fast-forward/{episode_id}   Skip the call delay, trigger now (DEMO_MODE only)
GET    /demo/reset                        Wipe all data between demos (DEMO_MODE only)
GET    /health                            Liveness check
```

---

## 5. The Flow — Step by Step

This is the canonical flow as implemented (see [ARCHITECTURE.md](ARCHITECTURE.md) §3 for the sequence diagram).

```
1. DISCHARGE EVENT
   POST /patients          → creates Patient row
   POST /episodes          → creates TCMEpisode (state: DISCHARGE_DETECTED), returns immediately
                           → FastAPI BackgroundTask:
                               services/triage.py (DeepSeek-V4-Pro via BaseTen)
                               → structured_extract + complexity + cpt_code set on episode
                               → contact_deadline (+2 business days), visit_deadline, billing_date (+30d)
                               → episode state → AWAITING_CALL

2. AUTO-TRIGGER (same background task)
   asyncio.sleep(DEMO_CALL_DELAY_SECONDS)   → POST /calls/trigger/{episode_id}
   (or POST /demo/fast-forward/{episode_id} to skip the wait)

3. OUTBOUND CALL PLACED
   calls/trigger           → creates Call row (status: IN_PROGRESS), attempt_number counted
                           → episode state → CALL_IN_PROGRESS
                           → background place_outbound_call(): agent_dispatch.create_dispatch
                             dispatches the LiveKit agent into a room with metadata
                           → the AGENT then dials: create_sip_participant(wait_until_answered=True)
                             over LiveKit SIP → Twilio → patient's real phone rings

   NO ANSWER PATH:
   POST /calls/{id}/no-answer
                           → Call status → NO_ANSWER
                           → services/call_manager.handle_no_answer:
                               attempt < 3: _schedule_retry (STUB — logs only, not yet wired)
                               attempt == 3: create Escalation (severity: monitor), state → ESCALATED

4. CALL ANSWERED — AGENT RUNS
   care_agent.py CareAgent → greeting via session.say, then structured Q&A from the system prompt
                           → Deepgram nova-3-medical STT → Claude Sonnet 4.5 (OpenRouter) → ElevenLabs TTS
                           → Krisp BVCTelephony noise cancellation, STT-driven turn taking

   RED FLAG PATH (mid-call):
   agent calls escalate()  → POST /escalations (severity: urgent) → episode state → ESCALATED
                           → dashboard lights up red immediately (3s poll)
   agent calls transfer_to_human()
                           → SIP REFER cold-transfer to CARE_TEAM_PHONE_NUMBER

   NORMAL COMPLETION (any end path — agent end_call(), patient hangup, or error):
   post_call_complete shutdown hook → POST /calls/{id}/complete { transcript, flags, structured_data }
                           → Call status → COMPLETED
                           → episode state → CALL_COMPLETE (only if still CALL_IN_PROGRESS)
                           → background services/summarizer.py (Claude via OpenRouter) generates summary,
                             merged into Call.structured_data (agent's visit outcome wins on overlap)

5. VISIT SCHEDULING
   agent schedule_appointment(agreed, slot/reason) records the booking outcome (stashed in structured_data).
   VISIT_SCHEDULED / VOIDED are reached via the manual PATCH /episodes/{id}/state endpoint;
   the tool does not itself advance episode state.

6. BILLING SUMMARY
   POST /episodes/{id}/generate-billing
                           → services/billing_doc.py (Claude via OpenRouter)
                           → returns: claim (CPT, date of service, ready_to_submit, blocking_flags),
                             CMS required elements, outreach summary, draft clinician note
                           → episode.billing_doc (JSON string) + cpt_code + ready_to_bill saved
                           → episode state → READY_TO_BILL
```

---

## 6. Backend Prompts (`packages/backend/prompts.py`)

All three return **raw JSON only**; the services strip code fences and `json.loads` the result.

| Prompt | Service | Provider / model |
|---|---|---|
| `DISCHARGE_ANALYSIS_PROMPT` | `triage.py` | BaseTen `deepseek-ai/DeepSeek-V4-Pro` |
| `CALL_SUMMARY_PROMPT` | `summarizer.py` | OpenRouter `anthropic/claude-sonnet-4-5` |
| `BILLING_DOC_PROMPT` | `billing_doc.py` | OpenRouter `anthropic/claude-sonnet-4-5` |

### Prompt 1 — Discharge Analysis + Complexity Triage

Inputs: `age`, `known_medications`, `discharge_notes`. (Earlier drafts also fed `prior_readmissions`; that
input was removed.)

```python
DISCHARGE_ANALYSIS_PROMPT = """
You are a clinical AI assistant for a primary care practice running a
Transitions of Care (TCM) program under CMS guidelines.

Analyze the discharge summary below and return structured JSON only.
No preamble, no markdown, no explanation — raw JSON only.

Patient info:
- Age: {age}
- Known medications: {known_medications}

Discharge notes:
{discharge_notes}

Return this exact JSON structure:
{{
  "diagnoses": ["list of discharge diagnoses"],
  "medications": ["list of discharge medications"],
  "pending_results": ["list of pending labs or tests"],
  "follow_up_instructions": "plain text follow-up instructions",
  "high_risk_flags": ["any high-risk conditions: heart failure, COPD, AMI, etc."],
  "complexity": "high",
  "complexity_rationale": "2-3 sentence explanation citing Problems, Data, Risk per 2023 CPT E/M guidelines",
  "visit_window_days": 7,
  "cpt_recommendation": "99496",
  "priority_outreach": true
}}

Complexity rules:
- HIGH (99496): high-complexity MDM, face-to-face within 7 days
- MODERATE (99495): moderate-complexity MDM, face-to-face within 14 days
- When in doubt, classify HIGH to protect the patient

The complexity field must be exactly "high" or "moderate".
The visit_window_days field must be exactly 7 or 14.
The cpt_recommendation field must be exactly "99496" or "99495".
"""
```

### Prompt 2 — Post-Call Summary

Inputs: `patient_name`, `age`, `diagnosis`, `discharge_date`, `attempt_number`, `transcript`.

```python
CALL_SUMMARY_PROMPT = """
You are a clinical documentation assistant generating a structured
post-call summary for a care coordinator at a primary care practice.

Patient: {patient_name}, {age}yo
Diagnosis: {diagnosis}
Discharge date: {discharge_date}
Call attempt: {attempt_number} of 3

Transcript:
{transcript}

Return this exact JSON structure. Raw JSON only, no markdown:
{{
  "summary": "2-3 sentence plain English summary of the call",
  "medications_confirmed": true,
  "medication_concerns": null,
  "visit_scheduled": false,
  "visit_date": null,
  "patient_understanding": "good",
  "red_flags": [],
  "escalate": false,
  "escalation_reason": null,
  "escalation_severity": null,
  "patient_sentiment": "positive",
  "next_action": "recommended next step for care coordinator"
}}

Escalate as URGENT if patient mentions: chest pain, shortness of breath
at rest, confusion, inability to obtain medications, fall, wound changes,
fever, or states something feels wrong.

Escalate as MONITOR if: patient sounds confused, missed multiple
medication doses, unable to schedule visit, or expresses significant anxiety.
"""
```

### Prompt 3 — Billing Documentation

Inputs: `patient_name`, `age`, `diagnosis`, `discharge_date`, `contact_deadline`, `face_to_face_date`,
`visit_deadline`, `complexity`, `cpt_code`, `billing_date`, `med_rec_completed`, `outreach_log`,
`escalations`. Returns a structured claim packet whose top-level keys are `claim`, `patient_summary`,
`cms_required_elements`, `outreach_summary`, and `clinician_note`:

```python
BILLING_DOC_PROMPT = """
You are a medical billing assistant for a primary care practice.
Generate a CMS-compliant Transitional Care Management (TCM) billing document
that can be reviewed, edited, and submitted for claim reimbursement.

Episode data:
- Patient: {patient_name}, {age}yo
- Diagnosis: {diagnosis}
- Discharge date: {discharge_date}
- Contact deadline (2 business days): {contact_deadline}
- Face-to-face visit date: {face_to_face_date}
- Visit deadline: {visit_deadline}
- MDM complexity: {complexity}
- CPT code: {cpt_code}
- Date of service (Day 30): {billing_date}
- Medications reconciled: {med_rec_completed}
- Outreach log: {outreach_log}
- Escalations: {escalations}

Return this exact JSON structure. Raw JSON only, no markdown:
{{
  "claim": { "cpt_code", "date_of_service", "complexity_level", "ready_to_submit", "blocking_flags" },
  "patient_summary": { "name", "age", "diagnosis", "discharge_date", "medications_reconciled" },
  "cms_required_elements": {
    "interactive_contact": { "completed", "date", "description" },
    "medication_reconciliation": { "completed", "date", "description" },
    "face_to_face_visit": { "completed", "date", "description" },
    "care_coordination": { "completed", "description" }
  },
  "outreach_summary": { "total_attempts", "successful_contact", "contact_date", "call_outcomes", "escalations" },
  "clinician_note": "SUBJECTIVE / OBJECTIVE / ASSESSMENT / PLAN / TCM ATTESTATION draft"
}}

Rules:
- Set ready_to_submit to false and add a blocking_flags entry if any CMS required element is missing.
- Use actual dates from the episode data where available, otherwise use "pending".
- The clinician_note must be a complete draft ready for physician review and signature.
"""
```

> The exact in-code prompt expands every JSON field with example values and full `description` text;
> the shape above is condensed for readability. The router reads `doc["claim"]["cpt_code"]` and
> `doc["claim"]["ready_to_submit"]`, so keep those keys stable.

---

## 7. Voice Agent (`packages/agent/`)

Built on **LiveKit Agents v1.5+** (`AgentServer` + `@server.rtc_session`). The backend dispatches the
agent; the **agent itself** places the outbound SIP call and waits for pickup before speaking. Verify any
LiveKit API against the live docs (https://docs.livekit.io/mcp) before editing — these snippets can age.

### System prompt builder (`prompts.py`)

`build_agent_prompt(patient)` produces the agent persona **"Aria"** and a fixed call flow, injecting
diagnosis-specific warning signs from `WARNING_SIGNS` (heart failure, COPD, hip/knee replacement,
pneumonia, diabetes, AMI, default). `build_greeting(patient)` is the literal opening line spoken via
`session.say` in `CareAgent.on_enter`.

```python
WARNING_SIGNS = {
    "heart failure":    "weight gain over 2 pounds overnight, swelling in legs or ankles, shortness of breath at rest, inability to lie flat",
    "copd":             "increased breathlessness beyond baseline, change in mucus color to yellow or green, fever, reduced effectiveness of inhaler",
    "hip replacement":  "severe increase in pain, redness or discharge from wound, fever above 101, inability to bear any weight",
    "knee replacement": "severe swelling, wound opening, fever, inability to bend knee at all",
    "pneumonia":        "return of fever, increased shortness of breath, chest pain, confusion",
    "diabetes":         "blood sugar consistently above 300 or below 70, confusion, chest pain, foot wounds or sores",
    "ami":              "any chest pain, shortness of breath, dizziness, left arm pain",
    "default":          "chest pain, difficulty breathing, confusion, sudden weakness, high fever, or if you feel something is seriously wrong",
}

def get_warning_signs(diagnosis: str) -> str:
    diagnosis_lower = (diagnosis or "").lower()
    for key, signs in WARNING_SIGNS.items():
        if key in diagnosis_lower:
            return signs
    return WARNING_SIGNS["default"]
```

The system prompt's call flow: **1) confirm identity → 2) wellbeing + a single warning-sign screen →
3) medications → 4) schedule the follow-up visit → 5) close warmly**. On any warning sign it instructs the
model to call `escalate(severity="urgent")` then `transfer_to_human()` immediately.

### Agent worker (`agent.py`) — the real wiring

```python
from livekit.agents import AgentServer, AgentSession, cli, room_io
from livekit.plugins import deepgram, elevenlabs, noise_cancellation, openai, silero
from livekit import api
from care_agent import CareAgent

server = AgentServer()
server.setup_fnc = prewarm          # loads Silero VAD once per process

@server.rtc_session(agent_name="continuacare")
async def entrypoint(ctx):
    await ctx.connect()
    meta = json.loads(ctx.job.metadata or "{}")   # phone_number, patient_id, episode_id, call_id
    patient = await fetch_patient(meta["patient_id"])   # GET /patients/{id} (+ /episode)
    agent = CareAgent(patient)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        userdata=meta,
        stt=deepgram.STT(model="nova-3-medical"),
        llm=openai.LLM(                              # Claude Sonnet 4.5 via OpenRouter
            model="anthropic/claude-sonnet-4-5",
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        ),
        tts=elevenlabs.TTS(
            api_key=os.environ["ELEVENLABS_API_KEY"],
            voice_id=os.environ["ELEVENLABS_VOICE_ID"],
            model="eleven_turbo_v2",
        ),
        turn_handling=TURN_HANDLING,                # STT-driven turn detection, adaptive barge-in
    )

    # The AGENT dials out and waits for pickup before greeting.
    await ctx.api.sip.create_sip_participant(api.CreateSIPParticipantRequest(
        room_name=ctx.room.name,
        sip_trunk_id=os.environ["LIVEKIT_SIP_TRUNK_ID"],
        sip_call_to=meta["phone_number"],
        participant_identity=meta["phone_number"],
        wait_until_answered=True,
    ))

    # Completion is posted on EVERY end path via a shutdown hook (not from end_call directly).
    ctx.add_shutdown_callback(lambda: post_call_complete(session, meta))

    await session.start(agent=agent, room=ctx.room, room_options=room_io.RoomOptions(
        audio_input=room_io.AudioInputOptions(noise_cancellation=noise_cancellation.BVCTelephony()),
        delete_room_on_close=True,
    ))
```

`CareAgent` (`care_agent.py`) subclasses `Agent` with `tools=[transfer_to_human, escalate,
schedule_appointment, end_call]`, speaks the greeting in `on_enter`, applies pronunciation fixes in
`tts_node`, and drops low-confidence transcripts in `on_user_turn_completed`.

### Tools (`tools.py`)

- `escalate(reason, severity="urgent")` → `POST {BACKEND_URL}/escalations`. Called the instant a red flag
  is heard, before anything else.
- `transfer_to_human(reason)` → SIP REFER cold-transfer to `CARE_TEAM_PHONE_NUMBER` (speaks a fixed
  "stay on the line" message first; plays a fixed failure line on any error).
- `schedule_appointment(agreed, slot, reason)` → stashes the visit outcome on `session.userdata`; it is
  **not** posted here — `post_call_complete` folds it into the single `/complete` POST.
- `end_call()` → speaks a fixed farewell, then `session.shutdown(drain=True)`; the shutdown hook posts
  completion.

---

## 8. Retry Logic (`packages/backend/services/call_manager.py`)

```python
MAX_ATTEMPTS     = 3
RETRY_DELAY_DEMO = 10     # seconds
RETRY_DELAY_PROD = 3600   # seconds (60 minutes)

async def handle_no_answer(episode_id, call_id, attempt, db):
    if attempt < MAX_ATTEMPTS:
        run_at = datetime.utcnow() + timedelta(seconds=RETRY_DELAY_DEMO if DEMO_MODE else RETRY_DELAY_PROD)
        _schedule_retry(episode_id, run_at)   # STUB: logs intent; real scheduler not yet wired (§9)
    else:
        # 3 attempts — still billable per CMS, flag for human follow-up
        await _escalate_no_answer(episode_id, call_id, db)   # Escalation severity="monitor", state → ESCALATED
```

> **Status:** the escalate-after-3-attempts path works end-to-end. The automatic **retry between**
> attempts (`_schedule_retry`) is a logging stub pending the scheduler in §9.

---

## 9. Scheduling Logic — design intent (NOT YET IMPLEMENTED)

There is **no `scheduler.py`** and **no APScheduler wiring** in the running code. APScheduler is listed in
`requirements.txt` but unused. The live system instead:

- Auto-triggers the **first** call from a FastAPI `BackgroundTask` (`asyncio.sleep(DEMO_CALL_DELAY_SECONDS)`
  then `POST /calls/trigger`), and
- Computes deadlines inline in `routers/episodes.py` via `_business_days_from` (Mon–Fri aware).

The original multi-call cadence below remains the **design target** for a future scheduler that would
create `CallSchedule` rows and fire repeat calls:

```python
# DESIGN INTENT — not implemented
CALL_SCHEDULE = {
    "high":     [0, 2, 6, 13, 20, 29],   # day offsets from discharge
    "moderate": [1, 6, 13, 29],
}
```

Deadline rules that ARE implemented (in `routers/episodes.py`):

```python
contact_deadline = _business_days_from(discharge_date, 2)         # +2 business days
visit_deadline   = discharge_date + timedelta(days=visit_window)  # +7 (HIGH) or +14 (MODERATE)
billing_date     = discharge_date + timedelta(days=30)            # date of service
```

---

## 10. Frontend (`packages/frontend/src/`)

Runs on **mock/seed data by default** (`USE_MOCK`, true unless `VITE_USE_MOCK="false"`). In live mode the
same helpers hit the backend; no component changes.

### API Client (`api.ts`)

```typescript
export const API_URL  = import.meta.env.VITE_API_URL || 'http://localhost:8000'
export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false'

export const getPatients        = ()        => api.get('/patients')
export const getPatient         = (id)      => api.get(`/patients/${id}`)
export const getPatientEpisode  = (pid)     => api.get(`/patients/${pid}/episode`)
export const getEpisode         = (id)      => api.get(`/episodes/${id}`)
export const createEpisode      = (body)    => api.post('/episodes', body)   // {patient_id, discharge_date, discharge_notes}
export const triggerCall        = (id)      => api.post(`/calls/trigger/${id}`)
export const getCallsForEpisode = (id)      => api.get(`/calls/episode/${id}`)
export const getOpenEscalations = ()        => api.get('/escalations/open')
export const acknowledgeAlert   = (id)      => api.patch(`/escalations/${id}`, { status: 'resolved' })
export const generateBilling    = (id)      => api.post(`/episodes/${id}/generate-billing`)
export const setEpisodeState    = (id, s)   => api.patch(`/episodes/${id}/state`, { state: s })
export const fastForward        = (id)      => api.post(`/demo/fast-forward/${id}`)
```

### Escalation polling — Zustand store (`store/useStore.ts`)

`startEscalationPolling()` is started from `pages/Demo.tsx` on mount; it polls `/escalations/open` every
3 seconds and flips any matching patient's `statusKind` to `'flag'` so the dashboard lights up red live:

```typescript
startEscalationPolling: () => {
  const poll = async () => {
    const { data } = await getOpenEscalations()
    set({ openEscalationIds: new Set(data.map(e => e.id)) /* …flag patients… */ })
  }
  const interval = setInterval(poll, 3000)
  return () => clearInterval(interval)
}
```

---

## 11. BaseTen Integration

BaseTen is used for **one** thing in the running code: the **triage LLM**. `services/triage.py` calls it
through the OpenAI-compatible SDK:

```python
from openai import AsyncOpenAI
client = AsyncOpenAI(
    api_key=os.environ["BASETEN_API_KEY"],
    base_url="https://inference.baseten.co/v1",
)
response = await client.chat.completions.create(
    model="deepseek-ai/DeepSeek-V4-Pro",
    messages=[{"role": "user", "content": prompt}],
    temperature=0,
)
```

> The earlier design mentioned a BaseTen **Whisper** fallback STT and a **BioMistral** symptom classifier
> (`baseten_client.py`). Neither exists in the code — the agent uses Deepgram STT only, and there is no
> `baseten_client.py`. Treat those as future ideas, not current behavior.

---

## 12. Render Deployment (`render.yaml`) — not yet written

`render.yaml` is empty on disk. The deployment intent: three services (backend `web`, agent `worker`,
frontend `web`) plus a managed Postgres. When authoring it, set env vars to the **actual** keys the code
reads (§2) — notably `BASETEN_API_KEY`, `OPENROUTER_API_KEY`, `CARE_TEAM_PHONE_NUMBER`,
`LIVEKIT_SIP_TRUNK_ID` — and drop `ANTHROPIC_API_KEY` / `BASETEN_WHISPER_URL`.

```yaml
databases:
  - name: continuacare-db
    databaseName: continuacare
    plan: free

services:
  - type: web
    name: continuacare-backend
    runtime: python
    rootDir: packages/backend
    buildCommand: pip install -r requirements.txt && alembic upgrade head
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    envVars: [DATABASE_URL (fromDatabase), BASETEN_API_KEY, OPENROUTER_API_KEY,
              ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, DEEPGRAM_API_KEY,
              LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_SIP_TRUNK_ID,
              CARE_TEAM_PHONE_NUMBER, DEMO_MODE]

  - type: worker
    name: continuacare-agent
    runtime: python
    rootDir: packages/agent
    buildCommand: pip install -r requirements.txt
    startCommand: python agent.py
    envVars: [BACKEND_URL, OPENROUTER_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID,
              DEEPGRAM_API_KEY, LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET,
              LIVEKIT_SIP_TRUNK_ID, CARE_TEAM_PHONE_NUMBER]

  - type: web
    name: continuacare-frontend
    runtime: node
    rootDir: packages/frontend
    buildCommand: npm install && npm run build
    startCommand: npx serve dist
    envVars: [VITE_API_URL, VITE_USE_MOCK]
```

---

## 13. Local Dev Setup

```bash
# 1. Start Postgres
docker run --name continuacare-db \
  -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=continuacare \
  -p 5432:5432 -d postgres

# 2. Backend (tables auto-create on startup; alembic optional)
cd packages/backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 3. Agent (new terminal, separate venv)
cd packages/agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python agent.py

# 4. Frontend (new terminal)
cd packages/frontend
npm install
npm run dev        # http://localhost:5173 (mock data unless VITE_USE_MOCK=false)

# 5. Verify
#   http://localhost:5173        dashboard
#   http://localhost:8000/docs   API explorer
```

---

## 14. Demo Script (Saturday 3pm)

```
[Setup: DEMO_MODE=true, patient pre-created, Twilio number verified on the doctor's phone]

STEP 1 — Discharge (30 seconds)
  Create patient + episode (e.g. Jane Smith, 67yo, Heart Failure)
  → Triage returns: Complexity HIGH, CPT 99496, 7-day window
  → Contact deadline (+2 business days) appears

STEP 2 — Call triggers
  After DEMO_CALL_DELAY_SECONDS (or POST /demo/fast-forward/{episode_id})
  → Doctor's phone rings with your Twilio number

STEP 3A — Normal path (2 minutes)
  Doctor plays the patient, answers questions; visit scheduled
  Click "Generate Billing Summary" → CPT 99496 claim packet appears

STEP 3B — Escalation path (1 minute) [USE THIS FOR DEMO]
  Doctor says: "Actually I've had some chest tightness since yesterday"
  → Agent calls escalate(urgent) + transfer_to_human()
  → Dashboard IMMEDIATELY shows a red URGENT escalation card (3s poll)
  → Patient is cold-transferred to the care team line

  Pause. Let the room sit with it.
  "This patient would have gone two weeks without follow-up.
   This call took seconds to detect it."
```

---

*Last updated: June 27, 2026 — reconciled with the implemented build. See [ARCHITECTURE.md](ARCHITECTURE.md).*
