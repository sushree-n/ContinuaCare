from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from database import get_db
from models import TCMEpisode, Patient, Call, Escalation, EpisodeState

router = APIRouter(prefix="/episodes", tags=["billing"])


class BillingDocUpdate(BaseModel):
    clinician_note: Optional[str] = None
    face_to_face_date: Optional[datetime] = None
    med_rec_completed: Optional[bool] = None


@router.post("/{episode_id}/generate-billing")
async def generate_billing(episode_id: str, db: AsyncSession = Depends(get_db)):
    ep_result = await db.execute(select(TCMEpisode).where(TCMEpisode.id == episode_id))
    episode = ep_result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    pt_result = await db.execute(select(Patient).where(Patient.id == episode.patient_id))
    patient = pt_result.scalar_one_or_none()

    # build outreach log from all calls
    calls_result = await db.execute(
        select(Call).where(Call.episode_id == episode_id).order_by(Call.started_at)
    )
    calls = calls_result.scalars().all()
    outreach_log = [
        {
            "attempt": c.attempt_number,
            "date": c.started_at.strftime("%Y-%m-%d") if c.started_at else None,
            "status": c.status.value if c.status else None,
            "summary": c.summary,
        }
        for c in calls
    ]

    # fetch escalations
    esc_result = await db.execute(
        select(Escalation).where(Escalation.episode_id == episode_id)
    )
    escalations = [
        {
            "reason": e.reason,
            "severity": e.severity,
            "date": e.created_at.strftime("%Y-%m-%d") if e.created_at else None,
            "status": e.status.value if e.status else None,
        }
        for e in esc_result.scalars().all()
    ]

    from services.billing_doc import run_billing_doc
    doc = await run_billing_doc(
        patient_name=patient.name if patient else "unknown",
        age=patient.age if patient else None,
        diagnosis=patient.diagnosis if patient else "unknown",
        discharge_date=episode.discharge_date,
        contact_deadline=episode.contact_deadline,
        face_to_face_date=episode.face_to_face_date,
        visit_deadline=episode.visit_deadline,
        complexity=episode.complexity.value if episode.complexity else "unknown",
        cpt_code=episode.cpt_code,
        billing_date=episode.billing_date,
        med_rec_completed=episode.med_rec_completed or False,
        outreach_log=outreach_log,
        escalations=escalations,
    )

    # persist the doc and update episode state
    import json
    episode.billing_doc = json.dumps(doc)
    episode.cpt_code = doc.get("claim", {}).get("cpt_code", episode.cpt_code)
    episode.ready_to_bill = doc.get("claim", {}).get("ready_to_submit", False)
    if episode.state not in (EpisodeState.READY_TO_BILL, EpisodeState.VOIDED):
        episode.state = EpisodeState.READY_TO_BILL

    await db.commit()
    return doc


@router.patch("/{episode_id}/billing-doc")
async def update_billing_doc(
    episode_id: str,
    body: BillingDocUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Frontend calls this when the care practitioner edits the billing doc."""
    ep_result = await db.execute(select(TCMEpisode).where(TCMEpisode.id == episode_id))
    episode = ep_result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    if body.face_to_face_date is not None:
        episode.face_to_face_date = body.face_to_face_date
    if body.med_rec_completed is not None:
        episode.med_rec_completed = body.med_rec_completed
        if body.med_rec_completed:
            episode.med_rec_date = datetime.utcnow()

    # merge clinician note edit back into stored billing_doc JSON
    if body.clinician_note is not None and episode.billing_doc:
        import json
        try:
            doc = json.loads(episode.billing_doc)
            doc["clinician_note"] = body.clinician_note
            episode.billing_doc = json.dumps(doc)
        except Exception:
            pass

    await db.commit()
    return {"status": "updated"}
