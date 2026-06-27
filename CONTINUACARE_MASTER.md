# ContinuaCare — Master Technical Spec
> TCM Automation Platform | NYC Healthcare x AI Hackathon | June 26–27, 2026

---

## 0. Quick Reference

| Item | Value |
|---|---|
| Repo | `continuacare` (monorepo) |
| Backend URL (local) | `http://localhost:8000` |
| Frontend URL (local) | `http://localhost:5173` |
| API Docs (auto) | `http://localhost:8000/docs` |
| Voice Agent | LiveKit + Deepgram + ElevenLabs + Twilio SIP |
| LLM | Claude Sonnet (`claude-sonnet-4-6`) via Anthropic API |
| DB | PostgreSQL (Docker local, Render managed in prod) |
| Inference | Baseten (Whisper fallback STT + BioMistral symptoms) |

---

## 1. Monorepo Structure

```
continuacare/
├── packages/
│   ├── backend/
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── prompts.py
│   │   ├── routers/
│   │   │   ├── patients.py
│   │   │   ├── episodes.py
│   │   │   ├── calls.py
│   │   │   └── escalations.py
│   │   ├── services/
│   │   │   ├── triage.py          ← Claude: discharge analysis + complexity
│   │   │   ├── summarizer.py      ← Claude: post-call summary
│   │   │   ├── billing_doc.py     ← Claude: claim documentation
│   │   │   ├── call_manager.py    ← retry logic, no-answer handling
│   │   │   └── scheduler.py       ← APScheduler job management
│   │   ├── alembic/
│   │   └── requirements.txt
│   ├── agent/
│   │   ├── agent.py               ← LiveKit voice agent (core)
│   │   ├── prompts.py             ← agent system prompt builder
│   │   └── requirements.txt
│   └── frontend/
│       ├── src/
│       │   ├── api.ts
│       │   ├── App.tsx
│       │   ├── pages/
│       │   │   ├── Dashboard.tsx
│       │   │   ├── PatientDetail.tsx
│       │   │   └── BillingDoc.tsx
│       │   ├── components/
│       │   │   ├── PatientCard.tsx
│       │   │   ├── EpisodeTimeline.tsx
│       │   │   ├── EscalationAlert.tsx
│       │   │   ├── CallLog.tsx
│       │   │   └── CalendarView.tsx
│       │   └── store/
│       │       └── useStore.ts    ← Zustand global state
│       └── package.json
├── .env.example
├── .gitignore
├── render.yaml
└── README.md
```

---

## 2. Environment Variables

**`.env.example`** — copy to `.env`, never commit `.env`

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:pass@localhost/continuacare

# Anthropic
ANTHROPIC_API_KEY=

# ElevenLabs
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=                # warm female voice for patient calls

# LiveKit
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
LIVEKIT_SIP_TRUNK_ID=               # created via lk cli

# Twilio
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=                # e.g. +1XXXXXXXXXX

# Deepgram
DEEPGRAM_API_KEY=

# Baseten
BASETEN_API_KEY=
BASETEN_WHISPER_URL=                # model endpoint URL

# Frontend
VITE_API_URL=http://localhost:8000

# Demo
DEMO_MODE=true                      # enables fast-forward endpoints
DEMO_CALL_DELAY_SECONDS=5           # delay before agent places call
```

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
    patient_history     = Column(String, nullable=False)
    created_at          = Column(DateTime, default=datetime.utcnow)
```

### TCMEpisode

```python
class TCMEpisode(Base):
    __tablename__ = "episodes"
    id                  = Column(String, primary_key=True, default=uuid4)
    patient_id          = Column(String, ForeignKey("patients.id"))

    # State
    state               = Column(Enum(EpisodeState), default=EpisodeState.DISCHARGE_DETECTED)

    # F1 — Discharge
    discharge_date      = Column(DateTime, nullable=False)  # Day 0
    discharge_notes     = Column(Text)

    # F2 — Structured extract (Claude output)
    structured_extract  = Column(JSON)    # {diagnoses, medications, flags, follow_up}

    # F3 — Complexity triage (Claude output)
    complexity          = Column(Enum(ComplexityLevel))
    triage_reason       = Column(Text)
    visit_window_days   = Column(Integer)                   # 7 or 14
    contact_deadline    = Column(DateTime)                  # Day 0 + 2 business days
    visit_deadline      = Column(DateTime)                  # Day 0 + 7 or 14
    billing_date        = Column(DateTime)                  # Day 0 + 30

    # F5 — Visit tracking
    face_to_face_date   = Column(DateTime)
    med_rec_completed   = Column(Boolean, default=False)
    med_rec_date        = Column(DateTime)

    # F8 — Billing
    cpt_code            = Column(String)                    # "99495" or "99496"
    billing_doc         = Column(Text)                      # Claude-generated summary
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
    summary         = Column(Text)                          # Claude F5 output
    flags           = Column(JSON)                          # list[str] detected symptoms
    structured_data = Column(JSON)                          # meds confirmed, visit scheduled etc.
```

### Escalation

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

---

## 4. API Endpoints (`packages/backend/routers/`)

### Priority Order — Build in This Order

#### Priority 1 — Core Demo Flow

```
POST   /patients                    Create patient
GET    /patients                    List all patients (dashboard)
GET    /patients/{id}               Single patient + episode

POST   /episodes                    Create TCM episode (discharge event)
GET    /episodes/{id}               Episode detail + state

POST   /calls/trigger/{episode_id}  Trigger outbound call (Twilio SIP)
POST   /calls/{id}/complete         Agent posts transcript + summary
POST   /calls/{id}/no-answer        Agent reports no answer → retry logic

POST   /escalations                 Agent posts red flag mid-call ← MOST IMPORTANT
GET    /escalations/open            Dashboard polls for active alerts
PATCH  /escalations/{id}            Acknowledge / resolve
```

#### Priority 2 — Billing + Calendar

```
POST   /episodes/{id}/generate-billing    Claude generates billing doc
GET    /episodes/{id}/schedule            Calendar view — all scheduled calls
PATCH  /episodes/{id}/state               Manual state transition (demo use)
```

#### Priority 3 — Demo Helpers

```
POST   /demo/fast-forward/{episode_id}    Simulate time passing, trigger call now
GET    /demo/reset                        Wipe all data, start fresh between demos
```

---

## 5. The Flow — Step by Step

This is the canonical flow. Every line maps to code.

```
1. DISCHARGE EVENT
   POST /patients          → creates Patient row
   POST /episodes          → creates TCMEpisode (state: DISCHARGE_DETECTED)
                           → calls services/triage.py (Claude)
                           → structured_extract + complexity set on episode
                           → contact_deadline, visit_deadline, billing_date computed
                           → scheduler.py creates CallSchedule rows
                           → episode state → AWAITING_CALL

2. WAIT PERIOD (demo: DEMO_CALL_DELAY_SECONDS from .env, default 5s)
   APScheduler fires       → POST /calls/trigger/{episode_id}

3. OUTBOUND CALL PLACED
   calls/trigger           → creates Call row (status: IN_PROGRESS)
                           → asyncio.create_task(place_outbound_call())
                           → LiveKit SIP → Twilio → patient's real phone rings
                           → episode state → CALL_IN_PROGRESS

   NO ANSWER PATH:
   POST /calls/{id}/no-answer
                           → Call status → NO_ANSWER
                           → attempt_number < 3: schedule retry in 10s (demo)
                           → attempt_number == 3: POST /escalations (severity: monitor)
                                                   episode state → ESCALATED

4. CALL ANSWERED — AGENT RUNS
   agent.py CareAgent      → structured Q&A using system prompt
                           → Claude Sonnet as LLM brain
                           → ElevenLabs TTS for voice
                           → Deepgram Nova-3 for STT

   RED FLAG PATH (mid-call):
   agent calls escalate()  → POST /escalations (severity: urgent)
                           → episode state → ESCALATED
                           → dashboard lights up red immediately
                           → call logs partial transcript and ends

   NORMAL COMPLETION:
   agent calls end_call()  → POST /calls/{id}/complete
                              {transcript, flags, structured_data}
                           → services/summarizer.py (Claude) generates summary
                           → Call status → COMPLETED
                           → episode state → CALL_COMPLETE

5. POST-CALL PROCESSING
   /calls/{id}/complete    → structured_data extracted:
                              {medications_confirmed, visit_scheduled,
                               visit_date, red_flags, patient_sentiment}
                           → dashboard updated with call outcome

6. COMPLEXITY + SCHEDULING
   (already run at step 1, surfaces here)
                           → complexity HIGH → 7-day window
                           → complexity MODERATE → 14-day window
                           → next open slot found within window
                           → CallSchedule row created for face-to-face visit
                           → episode state → VISIT_SCHEDULED
                           → dashboard shows "Visit scheduled: [date]"

7. READY FOR BILLING
                           → episode state → READY_TO_BILL
                           → dashboard shows "Generate Billing Summary" button

8. BILLING SUMMARY
   POST /episodes/{id}/generate-billing
                           → services/billing_doc.py (Claude)
                           → returns: CPT code, date of service (day 30),
                             4 CMS required elements, draft clinician note
                           → episode.billing_doc saved
                           → episode.cpt_code saved
```

---

## 6. Claude Prompts (`packages/backend/prompts.py`)

### Prompt 1 — Discharge Analysis + Complexity Triage (F2 + F3)
Runs immediately after discharge event.

```python
DISCHARGE_ANALYSIS_PROMPT = """
You are a clinical AI assistant for a primary care practice running a 
Transitions of Care (TCM) program under CMS guidelines.

Analyze the discharge summary below and return structured JSON only.
No preamble, no markdown, no explanation — raw JSON only.

Patient info:
- Age: {age}
- Prior readmissions: {prior_readmissions}
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
  "complexity": "high" | "moderate",
  "complexity_rationale": "2-3 sentence explanation citing Problems, Data, Risk per 2023 CPT E/M guidelines",
  "visit_window_days": 7 | 14,
  "cpt_recommendation": "99496" | "99495",
  "priority_outreach": true | false
}}

Complexity rules:
- HIGH (99496): high-complexity MDM, face-to-face within 7 days
- MODERATE (99495): moderate-complexity MDM, face-to-face within 14 days
- When in doubt, classify HIGH to protect the patient
"""
```

### Prompt 2 — Post-Call Summary (F5)
Runs after each completed call.

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
  "medications_confirmed": true | false,
  "medication_concerns": "describe any concerns" | null,
  "visit_scheduled": true | false,
  "visit_date": "YYYY-MM-DD" | null,
  "patient_understanding": "good" | "partial" | "poor",
  "red_flags": ["list any concerning symptoms mentioned"],
  "escalate": true | false,
  "escalation_reason": "specific reason" | null,
  "escalation_severity": "urgent" | "monitor" | null,
  "patient_sentiment": "positive" | "neutral" | "concerning",
  "next_action": "recommended next step for care coordinator"
}}

Escalate as URGENT if patient mentions: chest pain, shortness of breath 
at rest, confusion, inability to obtain medications, fall, wound changes,
fever, or states something feels wrong.

Escalate as MONITOR if: patient sounds confused, missed multiple 
medication doses, unable to schedule visit, or expresses significant anxiety.
"""
```

### Prompt 3 — Billing Documentation (F8)
Runs when staff clicks "Generate Billing Summary".

```python
BILLING_DOC_PROMPT = """
You are a clinical billing assistant generating a TCM claim documentation 
packet for a primary care practice per CMS guidelines (MLN908628).

Episode data:
- Patient: {patient_name}, {age}yo
- Diagnosis: {diagnosis}
- Discharge date: {discharge_date}
- First contact date: {first_contact_date}
- Face-to-face visit date: {visit_date}
- MDM complexity: {complexity}
- CPT code: {cpt_code}
- Date of service (Day 30): {billing_date}
- Medications reconciled: {med_rec_completed}
- Call summaries: {call_summaries}
- Escalations: {escalations}

Generate a complete claim documentation packet with these sections:

1. CLAIM RECOMMENDATION
   - CPT code and rationale
   - Date of service
   - Any flags that would block the claim

2. CMS REQUIRED ELEMENTS (all 4 must be present)
   - Patient discharge date
   - First interactive contact date
   - Face-to-face visit date
   - Medical decision-making level

3. SUPPORTING DOCUMENTATION
   - Contact attempt log
   - Medication reconciliation record
   - Call outcomes summary

4. DRAFT CLINICIAN NOTE
   - For clinician review and signature
   - Covers the TCM period
   - Documents MDM level

Flag INCOMPLETE if any of the 4 required elements are missing.
Flag WARNING for: same-day discharge management conflicts, 
possible duplicate claims, or missing medication reconciliation.
"""
```

---

## 7. Voice Agent (`packages/agent/agent.py`)

### System Prompt Builder

```python
# packages/agent/prompts.py

WARNING_SIGNS = {
    "heart failure":    "weight gain over 2 pounds overnight, swelling in legs or ankles, shortness of breath at rest, inability to lie flat",
    "copd":             "increased breathlessness beyond baseline, change in mucus color to yellow or green, fever, reduced effectiveness of inhaler",
    "hip replacement":  "severe increase in pain, redness or discharge from wound, fever above 101, inability to bear any weight",
    "knee replacement": "severe swelling, wound opening, fever, inability to bend knee at all",
    "pneumonia":        "return of fever, increased shortness of breath, chest pain, confusion",
    "diabetes":         "blood sugar consistently above 300 or below 70, confusion, chest pain, foot wounds or sores",
    "ami":              "any chest pain, shortness of breath, dizziness, left arm pain",
    "default":          "chest pain, difficulty breathing, confusion, sudden weakness, high fever, or if you feel something is seriously wrong"
}

def get_warning_signs(diagnosis: str) -> str:
    diagnosis_lower = diagnosis.lower()
    for key, signs in WARNING_SIGNS.items():
        if key in diagnosis_lower:
            return signs
    return WARNING_SIGNS["default"]

def build_agent_prompt(patient: dict) -> str:
    return f"""
You are ContinuaCare, a warm and calm post-discharge follow-up assistant 
calling on behalf of Dr. [Name]'s care team at [Practice Name].

PATIENT CONTEXT:
- Name: {patient['name']}
- Age: {patient['age']}
- Diagnosis: {patient['diagnosis']}
- Discharge date: {patient['discharge_date']}
- Medications: {', '.join(patient.get('medications', []))}
- Complexity: {patient.get('complexity', 'unknown')}

YOUR GOALS FOR THIS CALL:
1. Confirm the patient got home safely
2. Check how they are feeling overall
3. Review their medications — are they taking them as prescribed?
4. Ask condition-specific check-in questions (see below)
5. Schedule the follow-up visit if not yet booked
6. Screen for warning signs and escalate immediately if found

CONDITION-SPECIFIC QUESTIONS FOR {patient['diagnosis'].upper()}:
Ask about: {get_warning_signs(patient['diagnosis'])}

CONVERSATION STYLE:
- Be warm, calm, and unhurried
- Use plain language — avoid medical jargon
- Keep responses SHORT — 1-2 sentences max per turn
- Do not diagnose or give medical advice
- If the patient asks a clinical question beyond your scope, 
  say you will have a nurse call them back

ESCALATION RULES — call escalate() IMMEDIATELY if patient mentions:
{get_warning_signs(patient['diagnosis'])}
...or says anything that sounds like an emergency.
Do NOT wait until end of call. Do NOT ask follow-up questions first.

CALL FLOW:
1. Greeting + identity confirmation
2. General well-being check
3. Medication review
4. Condition-specific questions
5. Visit scheduling (if needed)
6. Closing — confirm they have the practice phone number

Keep the total call under 5 minutes.
"""
```

### Agent Core

```python
# packages/agent/agent.py

from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import deepgram, elevenlabs, anthropic
from livekit import api
import httpx, asyncio, os
from prompts import build_agent_prompt

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

class CareAgent(Agent):
    def __init__(self, patient: dict, call_id: str, episode_id: str):
        super().__init__(instructions=build_agent_prompt(patient))
        self.patient    = patient
        self.call_id    = call_id
        self.episode_id = episode_id
        self.flags      = []

    async def escalate(self, reason: str, severity: str = "urgent"):
        """
        Call this tool IMMEDIATELY when a red flag is detected.
        Do not wait until end of call.
        """
        self.flags.append(reason)
        async with httpx.AsyncClient() as client:
            await client.post(f"{BACKEND_URL}/escalations", json={
                "episode_id": self.episode_id,
                "call_id":    self.call_id,
                "reason":     reason,
                "severity":   severity
            })

    async def end_call(self, summary: str, transcript: str, 
                        structured_data: dict):
        """Call when conversation completes normally."""
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{BACKEND_URL}/calls/{self.call_id}/complete",
                json={
                    "transcript":      transcript,
                    "summary":         summary,
                    "flags":           self.flags,
                    "structured_data": structured_data
                }
            )


async def place_outbound_call(patient: dict, call_id: str, 
                               episode_id: str):
    lk = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET")
    )

    room_name = f"continuacare-{episode_id}-{call_id[:8]}"

    # Place real outbound call via Twilio SIP
    await lk.sip.create_sip_participant(
        api.CreateSIPParticipantRequest(
            sip_trunk_id=os.getenv("LIVEKIT_SIP_TRUNK_ID"),
            sip_call_to=patient["phone"],
            room_name=room_name,
            participant_name="ContinuaCare",
            participant_identity="care-agent",
            krisp_enabled=True               # noise cancellation
        )
    )

    session = AgentSession(
        stt=deepgram.STT(model="nova-3-medical"),
        llm=anthropic.LLM(model="claude-sonnet-4-6"),
        tts=elevenlabs.TTS(
            voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
            model="eleven_turbo_v2"          # lowest latency
        ),
    )

    await session.start(
        agent=CareAgent(patient, call_id, episode_id),
        room_input_options=RoomInputOptions()
    )


async def run_agent():
    """Entry point — agent listens for dispatch from backend."""
    pass  # wired via LiveKit dispatch API
```

---

## 8. Retry Logic (`packages/backend/services/call_manager.py`)

```python
MAX_ATTEMPTS     = 3
RETRY_DELAY_DEMO = 10   # seconds (demo mode)
RETRY_DELAY_PROD = 60   # minutes (production)

async def handle_no_answer(episode_id: str, call_id: str, 
                             attempt: int, db: AsyncSession):
    if attempt < MAX_ATTEMPTS:
        delay = RETRY_DELAY_DEMO if DEMO_MODE else RETRY_DELAY_PROD * 60
        scheduler.add_job(
            trigger_outbound_call,
            trigger=DateTrigger(run_date=now() + timedelta(seconds=delay)),
            args=[episode_id, attempt + 1]
        )
    else:
        # 3 attempts — still billable per CMS, flag for human
        await create_escalation(
            episode_id=episode_id,
            call_id=call_id,
            reason=f"No answer after {MAX_ATTEMPTS} attempts. Human follow-up required to preserve TCM billability.",
            severity="monitor",
            db=db
        )
```

---

## 9. Scheduling Logic (`packages/backend/services/scheduler.py`)

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta

scheduler = AsyncIOScheduler()

# Call cadence by complexity
CALL_SCHEDULE = {
    "high":     [0, 2, 6, 13, 20, 29],   # day offsets from discharge
    "moderate": [1, 6, 13, 29],
}

def schedule_episode_calls(episode_id: str, 
                            discharge_date: datetime,
                            complexity: str):
    """Called once on episode creation."""
    days = CALL_SCHEDULE.get(complexity, CALL_SCHEDULE["moderate"])
    for day in days:
        run_at = discharge_date + timedelta(days=day)
        scheduler.add_job(
            trigger_outbound_call,
            trigger=DateTrigger(run_date=run_at),
            args=[episode_id, 1],
            id=f"{episode_id}_day_{day}",
            replace_existing=True
        )

def compute_deadlines(discharge_date: datetime, 
                       complexity: str) -> dict:
    """Compute all TCM timing deadlines."""
    return {
        "contact_deadline": add_business_days(discharge_date, 2),
        "visit_deadline":   discharge_date + timedelta(
                                days=7 if complexity == "high" else 14
                            ),
        "billing_date":     discharge_date + timedelta(days=30)
    }

def add_business_days(start: datetime, days: int) -> datetime:
    """Business-day aware deadline computation (Mon-Fri)."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:   # Monday=0, Friday=4
            added += 1
    return current
```

---

## 10. Frontend (`packages/frontend/src/`)

### API Client (`api.ts`)

```typescript
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000'
})

export default api

// Typed helpers
export const getPatients        = ()     => api.get('/patients')
export const getEpisode         = (id)   => api.get(`/episodes/${id}`)
export const triggerCall        = (id)   => api.post(`/calls/trigger/${id}`)
export const getOpenEscalations = ()     => api.get('/escalations/open')
export const acknowledgeAlert   = (id)   => api.patch(`/escalations/${id}`, { status: 'acknowledged' })
export const generateBilling    = (id)   => api.post(`/episodes/${id}/generate-billing`)
export const fastForward        = (id)   => api.post(`/demo/fast-forward/${id}`)
```

### Zustand Store (`store/useStore.ts`)

```typescript
import { create } from 'zustand'

interface Store {
  patients:    Patient[]
  escalations: Escalation[]
  setPatients: (p: Patient[]) => void
  addEscalation: (e: Escalation) => void
  acknowledgeEscalation: (id: string) => void
}

export const useStore = create<Store>((set) => ({
  patients: [],
  escalations: [],
  setPatients: (patients) => set({ patients }),
  addEscalation: (e) => set(s => ({ 
    escalations: [e, ...s.escalations] 
  })),
  acknowledgeEscalation: (id) => set(s => ({
    escalations: s.escalations.map(e => 
      e.id === id ? { ...e, status: 'acknowledged' } : e
    )
  }))
}))
```

### Polling for Escalations

Poll every 3 seconds so the dashboard lights up red in real time during demo:

```typescript
// In Dashboard.tsx
useEffect(() => {
  const poll = setInterval(async () => {
    const { data } = await getOpenEscalations()
    if (data.length > 0) {
      data.forEach(addEscalation)
    }
  }, 3000)
  return () => clearInterval(poll)
}, [])
```

### Calendar View — react-big-calendar

```bash
npm install react-big-calendar date-fns
```

```typescript
// components/CalendarView.tsx
import { Calendar, dateFnsLocalizer } from 'react-big-calendar'
import 'react-big-calendar/lib/css/react-big-calendar.css'

// Color coding
const eventColor = (event) => {
  if (event.resource.status === 'completed')   return '#10b981'  // green
  if (event.resource.escalated)                return '#ef4444'  // red
  if (event.resource.status === 'no_answer')   return '#f59e0b'  // amber
  return '#3b82f6'                                                // blue — upcoming
}
```

---

## 11. Baseten Integration (`packages/backend/baseten_client.py`)

Two uses:
1. **Whisper** — fallback STT if Deepgram fails mid-call
2. **BioMistral** (optional) — medically-tuned symptom classifier

```python
import httpx, os

async def transcribe_audio_fallback(audio_bytes: bytes) -> str:
    """Fallback STT via Baseten Whisper endpoint."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            os.getenv("BASETEN_WHISPER_URL"),
            headers={"Authorization": f"Api-Key {os.getenv('BASETEN_API_KEY')}"},
            content=audio_bytes
        )
        return resp.json().get("transcription", "")

async def classify_symptoms(transcript: str) -> dict:
    """
    Optional: run transcript through BioMistral for 
    medical symptom classification as a second opinion.
    Deploy BioMistral from HuggingFace via Baseten Truss.
    """
    pass
```

---

## 12. Render Deployment (`render.yaml`)

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
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: continuacare-db
          property: connectionString
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: ELEVENLABS_API_KEY
        sync: false
      - key: ELEVENLABS_VOICE_ID
        sync: false
      - key: LIVEKIT_URL
        sync: false
      - key: LIVEKIT_API_KEY
        sync: false
      - key: LIVEKIT_API_SECRET
        sync: false
      - key: LIVEKIT_SIP_TRUNK_ID
        sync: false
      - key: TWILIO_ACCOUNT_SID
        sync: false
      - key: TWILIO_AUTH_TOKEN
        sync: false
      - key: TWILIO_PHONE_NUMBER
        sync: false
      - key: DEEPGRAM_API_KEY
        sync: false
      - key: BASETEN_API_KEY
        sync: false
      - key: BASETEN_WHISPER_URL
        sync: false
      - key: DEMO_MODE
        value: "true"

  - type: worker
    name: continuacare-agent
    runtime: python
    rootDir: packages/agent
    buildCommand: pip install -r requirements.txt
    startCommand: python agent.py
    envVars:
      - key: BACKEND_URL
        value: https://continuacare-backend.onrender.com
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: ELEVENLABS_API_KEY
        sync: false
      - key: ELEVENLABS_VOICE_ID
        sync: false
      - key: LIVEKIT_URL
        sync: false
      - key: LIVEKIT_API_KEY
        sync: false
      - key: LIVEKIT_API_SECRET
        sync: false
      - key: LIVEKIT_SIP_TRUNK_ID
        sync: false
      - key: DEEPGRAM_API_KEY
        sync: false

  - type: web
    name: continuacare-frontend
    runtime: node
    rootDir: packages/frontend
    buildCommand: npm install && npm run build
    startCommand: npx serve dist
    envVars:
      - key: VITE_API_URL
        value: https://continuacare-backend.onrender.com
```

---

## 13. Local Dev Setup (Run Once Together)

```bash
# 1. Clone and install
git clone https://github.com/yourname/continuacare
cd continuacare

# 2. Start Postgres
docker run --name continuacare-db \
  -e POSTGRES_PASSWORD=pass \
  -e POSTGRES_DB=continuacare \
  -p 5432:5432 -d postgres

# 3. Backend
cd packages/backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload --port 8000

# 4. Agent (new terminal)
cd packages/agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python agent.py

# 5. Frontend (new terminal)
cd packages/frontend
npm install
npm run dev

# 6. Verify
open http://localhost:5173      # dashboard
open http://localhost:8000/docs # API explorer
```

---

## 14. Demo Script (Saturday 3pm)

```
[Setup: patient pre-created, Twilio number verified on doctor's phone]

STEP 1 — Discharge (30 seconds)
  Click "Discharge Patient: Jane Smith, 67yo, Heart Failure"
  → Dashboard shows: Complexity HIGH, CPT 99496, 7-day window
  → Contact deadline: [date] appears

STEP 2 — Call triggers (5 seconds)
  Demo delay fires
  → Doctor's phone rings with your Twilio number
  "Would you like to answer this?"

STEP 3A — Normal path (2 minutes)
  Doctor plays patient, answers questions
  Call completes → dashboard updates → visit scheduled
  Click "Generate Billing Summary" → CPT 99496 doc appears

STEP 3B — Escalation path (1 minute) [USE THIS FOR DEMO]
  Doctor says: "Actually I've had some chest tightness since yesterday"
  → Dashboard IMMEDIATELY shows red URGENT escalation card
  → "Chest tightness reported — Day 1 post-discharge heart failure patient"
  → Call ends, partial transcript logged

  Pause. Let the room sit with it.
  "This patient would have gone 2 weeks without follow-up.
   This call took 45 seconds to detect it."
```

*Last updated: June 26, 2026 — ContinuaCare Hackathon Build*
