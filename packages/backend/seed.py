"""Wipe all data and reseed the database with demo-ready patients and episodes.

Run from packages/backend/ with the venv active:
    python seed.py
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

from database import AsyncSessionLocal, engine, Base
from models import (
    Patient, TCMEpisode, Call, Escalation, CallSchedule,
    EpisodeState, ComplexityLevel, CallStatus, EscalationStatus,
)

TODAY = datetime(2026, 7, 2)

def uid(): return str(uuid.uuid4())

PATIENTS = [
    # ── Ready to discharge (no episode) — for live web demo calls ────────────
    {
        "patient": {
            "id": uid(),
            "name": "Eleanor Vasquez",
            "age": 67,
            "phone": "",
            "diagnosis": "Congestive Heart Failure",
            "medications": ["Torsemide 20mg daily", "Lisinopril 10mg daily", "Carvedilol 6.25mg twice daily"],
        },
    },
    {
        "patient": {
            "id": uid(),
            "name": "Frank Delgado",
            "age": 58,
            "phone": "",
            "diagnosis": "COPD Exacerbation",
            "medications": ["Tiotropium inhaler daily", "Albuterol inhaler as needed", "Prednisone 40mg taper"],
        },
    },
    {
        "patient": {
            "id": uid(),
            "name": "Beverly Kim",
            "age": 72,
            "phone": "",
            "diagnosis": "Diabetes with infected foot wound",
            "medications": ["Metformin 1000mg twice daily", "Insulin glargine 18 units nightly", "Augmentin 875mg twice daily"],
        },
    },
    {
        "patient": {
            "id": uid(),
            "name": "Arthur Patel",
            "age": 64,
            "phone": "",
            "diagnosis": "Pneumonia",
            "medications": ["Azithromycin 250mg daily", "Guaifenesin 400mg every 4h", "Albuterol inhaler as needed"],
        },
    },
    {
        "patient": {
            "id": uid(),
            "name": "Diane Kowalski",
            "age": 70,
            "phone": "",
            "diagnosis": "Hip Replacement",
            "medications": ["Aspirin 81mg daily", "Oxycodone 5mg every 6h as needed", "Enoxaparin 40mg daily"],
        },
    },
    {
        "patient": {
            "id": uid(),
            "name": "Marcus Bell",
            "age": 55,
            "phone": "",
            "diagnosis": "AMI — STEMI",
            "medications": ["Aspirin 81mg daily", "Clopidogrel 75mg daily", "Atorvastatin 80mg daily", "Metoprolol 50mg twice daily"],
        },
    },
    # ── Active episodes at various pipeline stages ────────────────────────────
    {
        "patient": {
            "id": uid(),
            "name": "Thomas Brennan",
            "age": 76,
            "phone": "",
            "diagnosis": "Sepsis",
            "medications": ["Vancomycin 1g every 12h", "Piperacillin-tazobactam 3.375g every 6h", "Metoprolol 25mg daily"],
        },
        "episode": {
            "discharge_date": TODAY - timedelta(days=1),
            "discharge_notes": "76M admitted for sepsis secondary to UTI. Blood cultures positive for E. coli, sensitivities pending. IV antibiotics transitioned to oral at discharge. Foley catheter removed. Follow-up urine culture needed in 5 days.",
            "state": EpisodeState.AWAITING_CALL,
            "complexity": ComplexityLevel.HIGH,
            "cpt_code": "99496",
            "visit_window_days": 7,
        },
    },
    {
        "patient": {
            "id": uid(),
            "name": "Gloria Washington",
            "age": 63,
            "phone": "",
            "diagnosis": "AMI — STEMI",
            "medications": ["Aspirin 81mg daily", "Clopidogrel 75mg daily", "Atorvastatin 80mg daily", "Metoprolol 50mg twice daily"],
        },
        "episode": {
            "discharge_date": TODAY - timedelta(days=2),
            "discharge_notes": "63F STEMI with successful PCI to LAD. Drug-eluting stent placed. EF 42% on discharge echo. Dual antiplatelet therapy started — do NOT stop without cardiology approval. Cardiac rehab referral placed.",
            "state": EpisodeState.ESCALATED,
            "complexity": ComplexityLevel.HIGH,
            "cpt_code": "99496",
            "visit_window_days": 7,
        },
        "escalation": {
            "reason": "Patient reported brief chest tightness and shortness of breath when climbing stairs — possible post-MI angina",
            "severity": "urgent",
        },
    },
    {
        "patient": {
            "id": uid(),
            "name": "Raymond Foster",
            "age": 71,
            "phone": "",
            "diagnosis": "Knee Replacement",
            "medications": ["Aspirin 81mg daily", "Oxycodone 5mg every 6h as needed", "Enoxaparin 40mg daily"],
        },
        "episode": {
            "discharge_date": TODAY - timedelta(days=4),
            "discharge_notes": "Left total knee arthroplasty. Uncomplicated post-op course. ROM 0-90 degrees at discharge. PT twice weekly arranged. DVT prophylaxis 28 days. Wound dry and intact.",
            "state": EpisodeState.CALL_COMPLETE,
            "complexity": ComplexityLevel.MODERATE,
            "cpt_code": "99495",
            "visit_window_days": 14,
        },
        "call": {
            "status": CallStatus.COMPLETED,
            "attempt_number": 1,
            "summary": "Patient recovering well. Pain managed with medication. No wound issues, no fever. Attending PT sessions. Follow-up visit scheduled for next Tuesday.",
            "transcript": "Agent: Hi Raymond, this is Aria from Dr. Smith's care team. How are you feeling since your knee surgery?\nPatient: Better than expected honestly. A bit sore but managing.\nAgent: Good to hear. Any fever, swelling beyond what's expected, or wound opening?\nPatient: No, the wound looks clean. Just the normal swelling my PT mentioned.\nAgent: Great. Are you making it to your PT sessions?\nPatient: Yes, twice this week already.\nAgent: Excellent. Let's get your follow-up visit on the books. We have Tuesday at 9am — does that work?\nPatient: Tuesday at 9 is perfect.\nAgent: You're all set. Call us if anything changes before then.",
        },
    },
    {
        "patient": {
            "id": uid(),
            "name": "Sandra Okafor",
            "age": 64,
            "phone": "",
            "diagnosis": "Pneumonia",
            "medications": ["Azithromycin 250mg daily x5 days", "Guaifenesin 400mg every 4h", "Albuterol inhaler as needed"],
        },
        "episode": {
            "discharge_date": TODAY - timedelta(days=9),
            "discharge_notes": "Community-acquired pneumonia, right lower lobe. Responded to IV ceftriaxone, transitioned to oral azithromycin. O2 sats 97% on room air at discharge. Complete antibiotic course at home. Follow-up CXR in 6 weeks.",
            "state": EpisodeState.READY_TO_BILL,
            "complexity": ComplexityLevel.MODERATE,
            "cpt_code": "99495",
            "visit_window_days": 14,
            "face_to_face_date": TODAY - timedelta(days=3),
            "med_rec_completed": True,
        },
        "call": {
            "status": CallStatus.COMPLETED,
            "attempt_number": 1,
            "summary": "Patient fully recovered. No fever, no shortness of breath. Completed antibiotic course. Attended face-to-face visit, chest X-ray follow-up scheduled in 6 weeks. Ready to bill CPT 99495.",
            "transcript": "Agent: Hi Sandra, this is Aria from Dr. Smith's care team. How are you feeling after your hospital stay?\nPatient: Much better, thank you. Back to normal almost.\nAgent: Wonderful. Any return of fever, chest pain, or increased breathlessness?\nPatient: No, none of that. I finished all the antibiotics.\nAgent: Perfect. Did you make it to your doctor's appointment last week?\nPatient: Yes, she said my lungs sound clear.\nAgent: That's great news. You're all set. We'll follow up about the chest X-ray in about six weeks.",
        },
    },
]


async def reseed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("✓ Tables wiped and recreated")

    async with AsyncSessionLocal() as db:
        for entry in PATIENTS:
            p_data = entry["patient"]
            ep_data = entry.get("episode")

            patient = Patient(**p_data)
            db.add(patient)
            await db.flush()

            if not ep_data:
                print(f"  + {p_data['name']} (no episode — ready to discharge)")
                continue

            discharge = ep_data["discharge_date"]
            visit_window = ep_data.get("visit_window_days", 14)

            def add_biz(start, days):
                cur, added = start, 0
                while added < days:
                    cur += timedelta(days=1)
                    if cur.weekday() < 5:
                        added += 1
                return cur

            episode = TCMEpisode(
                id=uid(),
                patient_id=p_data["id"],
                discharge_date=discharge,
                discharge_notes=ep_data["discharge_notes"],
                state=ep_data["state"],
                complexity=ep_data.get("complexity"),
                cpt_code=ep_data.get("cpt_code"),
                visit_window_days=visit_window,
                contact_deadline=add_biz(discharge, 2),
                visit_deadline=discharge + timedelta(days=visit_window),
                billing_date=discharge + timedelta(days=30),
                face_to_face_date=ep_data.get("face_to_face_date"),
                med_rec_completed=ep_data.get("med_rec_completed", False),
            )
            db.add(episode)
            await db.flush()

            call_data = entry.get("call")
            call = None
            if call_data:
                call = Call(
                    id=uid(),
                    episode_id=episode.id,
                    patient_id=p_data["id"],
                    attempt_number=call_data.get("attempt_number", 1),
                    status=call_data["status"],
                    started_at=discharge + timedelta(hours=6),
                    ended_at=discharge + timedelta(hours=6, minutes=8),
                    summary=call_data.get("summary"),
                    transcript=call_data.get("transcript"),
                    flags=[],
                    structured_data={},
                )
                db.add(call)

            esc_data = entry.get("escalation")
            if esc_data:
                esc = Escalation(
                    id=uid(),
                    episode_id=episode.id,
                    call_id=call.id if call else None,
                    reason=esc_data["reason"],
                    severity=esc_data["severity"],
                    status=EscalationStatus.OPEN,
                    created_at=discharge + timedelta(hours=6),
                )
                db.add(esc)

            print(f"  + {p_data['name']} ({ep_data['state'].value})")

        await db.commit()

    print("\n✓ Seed complete — 10 patients inserted")
    print("  Eleanor Vasquez   — ready to discharge (CHF)")
    print("  Frank Delgado     — ready to discharge (COPD)")
    print("  Beverly Kim       — ready to discharge (Diabetes/foot wound)")
    print("  Arthur Patel      — ready to discharge (Pneumonia)")
    print("  Diane Kowalski    — ready to discharge (Hip Replacement)")
    print("  Marcus Bell       — ready to discharge (STEMI)")
    print("  Thomas Brennan    — AWAITING_CALL (Sepsis)")
    print("  Gloria Washington — ESCALATED (STEMI)")
    print("  Raymond Foster    — CALL_COMPLETE (Knee Replacement)")
    print("  Sandra Okafor     — READY_TO_BILL (Pneumonia)")


if __name__ == "__main__":
    asyncio.run(reseed())
