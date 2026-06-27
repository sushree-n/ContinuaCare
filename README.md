# ContinuaCare

**Agentic AI for Transitional Care Management (TCM)**

ContinuaCare automates the post-discharge follow-up workflow that Medicare requires but most small practices can't staff. When a patient is discharged from the hospital, ContinuaCare detects the discharge, places an AI-powered voice call to the patient, screens for clinical red flags in real time, escalates to a human care coordinator if needed, books the follow-up visit, and generates CMS-compliant billing documentation — all without manual intervention.

Built at the **Healthcare AI Hackathon, June 2026**.

---

## The Problem

Medicare's Transitional Care Management (TCM) program pays primary care physicians $200–$275 per patient to coordinate care in the 30 days following a hospital discharge. The requirements: contact the patient within 2 business days, see them face-to-face within 7–14 days, and document everything.

The reality: 85% of eligible discharges go unbilled nationally. Most small practices have no dedicated care coordinator. The process is entirely manual, and patients slip through.

**1 in 5 Medicare patients is readmitted within 30 days.** ContinuaCare closes that gap.

---

## How It Works

1. **Discharge detected** — a patient is registered and a discharge is initiated from the care console
2. **Triage** — Claude analyzes the discharge notes and classifies complexity (HIGH → CPT 99496, MODERATE → CPT 99495)
3. **Outbound call** — Aria, the AI care coordinator, calls the patient via SIP/Twilio within 2 business days
4. **Symptom screening** — Aria asks about diagnosis-specific warning signs in a natural, conversational way
5. **Red flag escalation** — if the patient reports a warning sign, Aria escalates immediately and cold-transfers the call to the care team
6. **Visit scheduling** — if the patient is doing well, Aria offers available slots and books the follow-up
7. **Billing doc generation** — Claude produces a CMS-compliant note with CPT code, complexity rationale, and the 4 required documentation elements
8. **Care console** — the clinical team sees live status, escalation alerts, call transcripts, and billing readiness for every patient

---

## Architecture

```
packages/
├── backend/     FastAPI + PostgreSQL — episode state machine, REST API, triage, summarizer, billing
├── agent/       LiveKit voice agent — Deepgram STT → Claude LLM → ElevenLabs TTS → Twilio SIP
└── frontend/    React + TypeScript + Vite — live care console with escalation polling
```

**Episode states:** `DISCHARGE_DETECTED → AWAITING_CALL → CALL_IN_PROGRESS → CALL_COMPLETE → ESCALATED → VISIT_SCHEDULED → READY_TO_BILL`

**Key integrations:**
- **LiveKit** — real-time voice agent orchestration and SIP outbound dialing
- **Twilio** — SIP trunk for PSTN calls and cold transfer to care team
- **Deepgram** (`nova-3-medical`) — medical-grade speech-to-text
- **ElevenLabs** — natural TTS voice synthesis
- **Anthropic Claude** — LLM backbone for the voice agent, call summarizer, and billing doc generator
- **DeepSeek V4 Pro via BaseTen** — triage classification from discharge notes
- **OpenRouter** — LLM proxy for the voice agent

---

## Running Locally

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker (for local Postgres)
- LiveKit account with SIP trunk configured
- Twilio account with verified phone number

### 1. Environment
```bash
cp .env.example .env
# Fill in all keys — see .env.example for required variables
```

### 2. Database
```bash
docker run --name continuacare-db \
  -e POSTGRES_PASSWORD=pass \
  -e POSTGRES_DB=continuacare \
  -p 5432:5432 -d postgres
```

### 3. Backend
```bash
cd packages/backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload --port 8000
# API docs at http://localhost:8000/docs
```

Seed demo patients:
```bash
python seed.py
```

### 4. Voice Agent
```bash
cd packages/agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python agent.py dev
```

### 5. Frontend
```bash
cd packages/frontend
npm install
npm run dev
# Console at http://localhost:5173
```

---

## Demo Flow

1. Open the care console at `http://localhost:5173`
2. Click a patient → **Initiate Discharge** → enter discharge notes → submit
3. The backend triages the notes (DeepSeek) and schedules a call
4. After ~15 seconds, Aria calls the patient's phone
5. Answer and speak with Aria — she will screen for symptoms, offer appointment slots, and end the call
6. The call transcript and Claude-generated summary appear in the console
7. To test escalation: mention a warning sign (e.g. "I've had chest pain since yesterday")
8. Aria escalates immediately and transfers the call to the care team number
9. The dashboard flashes red and the episode moves to **Action Required**

Demo endpoints:
- `POST /demo/fast-forward/{episode_id}` — skip to billing-ready state
- `GET /demo/reset` — wipe all data between demos

---

## TCM Billing Rules

| Complexity | CPT Code | Face-to-face window | Reimbursement |
|---|---|---|---|
| High | 99496 | Within 7 days | ~$272.68 |
| Moderate | 99495 | Within 14 days | ~$201.20 |

Contact deadline: discharge + 2 business days (Mon–Fri).
Billing date: discharge + 30 days.

When triage is uncertain, ContinuaCare classifies **HIGH** — patient safety over billing optimization.

---

## Team

Ganesh Kudtarkar  
Sushree Nadiminty  
Titiksha Wagh  
Neil Noronha  
Giuliana Wladessa Manca  
Palak Majmudar

Built at the Healthcare AI Hackathon, June 26–27, 2026.
