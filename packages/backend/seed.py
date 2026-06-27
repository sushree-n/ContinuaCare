"""Wipe all data and reseed the database with demo-ready patients and episodes.

Run from packages/backend/ with the venv active:
    python seed.py
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

from sqlalchemy import text
from database import AsyncSessionLocal, engine, Base
from models import (
    Patient, TCMEpisode, Call, Escalation, CallSchedule,
    EpisodeState, ComplexityLevel, CallStatus, EscalationStatus,
)

TODAY = datetime(2026, 6, 27)

def uid(): return str(uuid.uuid4())

# ---------------------------------------------------------------------------
# Patient + episode definitions
# ---------------------------------------------------------------------------

PATIENTS = [
    {
        "patient": {
            "id": uid(),
            "name": "Margaret Chen",
            "age": 74,
            "phone": "+17165073866",   # ← replace with a real number for live calls
            "diagnosis": "Heart Failure",
            "medications": ["Furosemide 40mg daily", "Metoprolol 25mg twice daily", "Lisinopril 10mg daily"],
        },
        "episode": {
            "discharge_date": TODAY - timedelta(days=1),
            "discharge_notes": "Patient discharged after acute heart failure exacerbation. BNP normalized on diuretics. Volume overload resolved. Resume home medications. Strict 2-pound weight rule.",
            "state": EpisodeState.AWAITING_CALL,
            "complexity": ComplexityLevel.HIGH,
            "cpt_code": "99496",
            "visit_window_days": 7,
        },
    },
    {
        "patient": {
            "id": uid(),
            "name": "Robert Williams",
            "age": 68,
            "phone": "+17165073866",
            "diagnosis": "COPD",
            "medications": ["Tiotropium inhaler daily", "Albuterol inhaler as needed", "Prednisone 40mg 5-day taper"],
        },
        "episode": {
            "discharge_date": TODAY - timedelta(days=2),
            "discharge_notes": "COPD exacerbation, admitted for 3 days. Responded well to steroids and bronchodilators. O2 sats stable at 94% on room air at discharge. Complete steroid taper at home.",
            "state": EpisodeState.ESCALATED,
            "complexity": ComplexityLevel.HIGH,
            "cpt_code": "99496",
            "visit_window_days": 7,
        },
        "escalation": {
            "reason": "Patient reported increased breathlessness and yellow-green sputum since discharge — possible re-exacerbation",
            "severity": "urgent",
        },
    },
    {
        "patient": {
            "id": uid(),
            "name": "Dorothy Martinez",
            "age": 79,
            "phone": "+17165073866",
            "diagnosis": "Hip Replacement",
            "medications": ["Aspirin 81mg daily", "Oxycodone 5mg every 6h as needed", "Enoxaparin 40mg daily"],
        },
        "episode": {
            "discharge_date": TODAY - timedelta(days=3),
            "discharge_notes": "Right total hip arthroplasty. Uncomplicated post-op course. Weight-bearing as tolerated. PT/OT initiated. DVT prophylaxis with enoxaparin for 28 days.",
            "state": EpisodeState.CALL_COMPLETE,
            "complexity": ComplexityLevel.MODERATE,
            "cpt_code": "99495",
            "visit_window_days": 14,
        },
        "call": {
            "status": CallStatus.COMPLETED,
            "attempt_number": 1,
            "summary": "Patient doing well at home. Mild pain controlled with medications. No fever, no wound discharge, bearing weight with walker. Follow-up visit confirmed for Thursday.",
            "transcript": "Agent: Hi Dorothy, this is Aria from Dr. Smith's care team. How are you feeling since your hip surgery?\nPatient: Pretty good actually, just a little sore.\nAgent: That's expected. Any fever, redness at the wound, or trouble bearing weight?\nPatient: No, none of that. I'm using my walker like they told me.\nAgent: Wonderful. Let's get you scheduled for your follow-up. Does Thursday at 2pm work?\nPatient: Yes, Thursday works perfectly.\nAgent: Great, you're all set for Thursday at 2pm. Call us if anything changes before then.",
        },
    },
    {
        "patient": {
            "id": uid(),
            "name": "James Thompson",
            "age": 62,
            "phone": "+17165073866",
            "diagnosis": "AMI",
            "medications": ["Aspirin 81mg daily", "Atorvastatin 80mg daily", "Metoprolol 50mg twice daily", "Clopidogrel 75mg daily"],
        },
        "episode": {
            "discharge_date": TODAY - timedelta(days=5),
            "discharge_notes": "STEMI with successful PCI to LAD. EF 45% on discharge echo. Dual antiplatelet therapy started. Cardiac rehab referral placed. No chest pain at discharge.",
            "state": EpisodeState.VISIT_SCHEDULED,
            "complexity": ComplexityLevel.HIGH,
            "cpt_code": "99496",
            "visit_window_days": 7,
            "face_to_face_date": TODAY + timedelta(days=1),
        },
        "call": {
            "status": CallStatus.COMPLETED,
            "attempt_number": 1,
            "summary": "Patient recovery on track. Denies chest pain, shortness of breath, or dizziness. Taking all medications. Confirmed cardiology follow-up appointment.",
            "transcript": "Agent: Hi James, this is Aria from Dr. Smith's care team checking in after your recent hospitalization.\nPatient: Oh yes, hello.\nAgent: How have you been feeling since coming home?\nPatient: Pretty good, no chest pain or anything like that.\nAgent: Great. Any shortness of breath, dizziness, or left arm pain?\nPatient: No, none of that.\nAgent: Excellent. You're scheduled for your cardiology follow-up tomorrow — does that still work?\nPatient: Yes, I'll be there.\nAgent: Perfect. Don't forget all four of your heart medications.",
        },
    },
    {
        "patient": {
            "id": uid(),
            "name": "Patricia Johnson",
            "age": 71,
            "phone": "+17165073866",
            "diagnosis": "Diabetes",
            "medications": ["Metformin 1000mg twice daily", "Glipizide 10mg daily", "Lisinopril 5mg daily"],
        },
        "episode": {
            "discharge_date": TODAY - timedelta(days=8),
            "discharge_notes": "Diabetic ketoacidosis, precipitated by infection. Blood sugars stabilized on insulin drip then transitioned to oral agents. Infection treated with antibiotics. Discharged with home glucose monitoring instructions.",
            "state": EpisodeState.READY_TO_BILL,
            "complexity": ComplexityLevel.MODERATE,
            "cpt_code": "99495",
            "visit_window_days": 14,
            "face_to_face_date": TODAY - timedelta(days=2),
            "med_rec_completed": True,
        },
        "call": {
            "status": CallStatus.COMPLETED,
            "attempt_number": 1,
            "summary": "Patient managing well. Blood sugars in range (120-160). Completed antibiotic course. Attended face-to-face visit with PCP. Medication reconciliation completed.",
            "transcript": "Agent: Hi Patricia, this is Aria calling to check in after your hospital stay.\nPatient: Hi, yes.\nAgent: How are your blood sugars running at home?\nPatient: Pretty good, mostly between 120 and 160.\nAgent: That's great. Any confusion, chest pain, or foot sores?\nPatient: No, feeling much better.\nAgent: Wonderful. You saw your doctor two days ago — how did that go?\nPatient: It went well, she adjusted my Metformin dose slightly.\nAgent: Perfect. Everything looks on track.",
        },
    },
]


async def reseed():
    # Drop and recreate all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("✓ Tables wiped and recreated")

    async with AsyncSessionLocal() as db:
        for entry in PATIENTS:
            p_data = entry["patient"]
            ep_data = entry["episode"]

            # Patient
            patient = Patient(**p_data)
            db.add(patient)
            await db.flush()

            # Compute deadlines
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
            await db.flush()  # ensure episode id is in DB before call FK references it

            # Call (if defined)
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

            # Escalation (if defined)
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

    print("\n✓ Seed complete — 5 patients inserted")
    print("  Margaret Chen    — AWAITING_CALL (Heart Failure, HIGH)")
    print("  Robert Williams  — ESCALATED (COPD, HIGH)")
    print("  Dorothy Martinez — CALL_COMPLETE (Hip Replacement, MODERATE)")
    print("  James Thompson   — VISIT_SCHEDULED (AMI, HIGH)")
    print("  Patricia Johnson — READY_TO_BILL (Diabetes, MODERATE)")


if __name__ == "__main__":
    asyncio.run(reseed())
