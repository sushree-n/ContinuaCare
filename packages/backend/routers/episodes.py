from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import asyncio
import os
import uuid

import httpx

from database import get_db
from models import TCMEpisode, Patient, Call, CallSchedule, EpisodeState, ComplexityLevel
from services.triage import run_triage

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
CALL_DELAY_SECONDS = int(os.environ.get("DEMO_CALL_DELAY_SECONDS", 15))

router = APIRouter(prefix="/episodes", tags=["episodes"])


def _business_days_from(start: datetime, days: int) -> datetime:
    """Advance `days` business days from start (skips Sat/Sun)."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


class EpisodeCreate(BaseModel):
    patient_id: str
    discharge_date: datetime
    discharge_notes: str


class EpisodeResponse(BaseModel):
    id: str
    patient_id: str
    state: str
    discharge_date: datetime
    discharge_notes: Optional[str]
    structured_extract: Optional[dict]
    complexity: Optional[str]
    triage_rationale: Optional[str]
    visit_window_days: Optional[int]
    contact_deadline: Optional[datetime]
    visit_deadline: Optional[datetime]
    billing_date: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

    def model_post_init(self, __context):
        # coerce enums to their string values for the response
        if hasattr(self, "state") and hasattr(self.state, "value"):
            object.__setattr__(self, "state", self.state.value)
        if hasattr(self, "complexity") and self.complexity and hasattr(self.complexity, "value"):
            object.__setattr__(self, "complexity", self.complexity.value)


async def _run_triage_and_update(episode_id: str, patient: Patient, discharge_notes: str):
    """Background task: call Claude triage and write results back to the episode."""
    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(TCMEpisode).where(TCMEpisode.id == episode_id))
        episode = result.scalar_one_or_none()
        if not episode:
            return

        try:
            triage = await run_triage(
                discharge_notes=discharge_notes,
                age=patient.age,
                known_medications=patient.medications,
            )

            complexity_str = triage.get("complexity", "moderate").lower()
            complexity = ComplexityLevel.HIGH if complexity_str == "high" else ComplexityLevel.MODERATE
            visit_window = triage.get("visit_window_days", 7 if complexity == ComplexityLevel.HIGH else 14)

            episode.structured_extract = triage
            episode.complexity = complexity
            episode.triage_rationale = triage.get("complexity_rationale")
            episode.visit_window_days = visit_window
            episode.contact_deadline = _business_days_from(episode.discharge_date, 2)
            episode.visit_deadline = episode.discharge_date + timedelta(days=visit_window)
            episode.billing_date = episode.discharge_date + timedelta(days=30)
            episode.cpt_code = triage.get("cpt_recommendation")
            episode.state = EpisodeState.AWAITING_CALL

        except Exception as e:
            # don't crash the background task — leave episode in DISCHARGE_DETECTED
            print(f"[triage] failed for episode {episode_id}: {e}")
            return

        await db.commit()

    # triage done — wait then auto-trigger the call
    await asyncio.sleep(CALL_DELAY_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{BACKEND_URL}/calls/trigger/{episode_id}")
        print(f"[auto-trigger] call triggered for episode {episode_id}")
    except Exception as e:
        print(f"[auto-trigger] failed for episode {episode_id}: {e}")


@router.post("", response_model=EpisodeResponse, status_code=201)
async def create_episode(
    body: EpisodeCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    # verify patient exists
    patient_result = await db.execute(select(Patient).where(Patient.id == body.patient_id))
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    episode = TCMEpisode(
        id=str(uuid.uuid4()),
        patient_id=body.patient_id,
        discharge_date=body.discharge_date,
        discharge_notes=body.discharge_notes,
        state=EpisodeState.DISCHARGE_DETECTED,
    )
    db.add(episode)
    await db.commit()
    await db.refresh(episode)

    # kick off triage in the background so POST returns immediately
    background_tasks.add_task(
        _run_triage_and_update, episode.id, patient, body.discharge_notes
    )

    return episode


@router.get("/{episode_id}", response_model=EpisodeResponse)
async def get_episode(episode_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TCMEpisode).where(TCMEpisode.id == episode_id))
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.patch("/{episode_id}/state")
async def update_episode_state(
    episode_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Manual state transition — for demo control and care coordinator overrides."""
    result = await db.execute(select(TCMEpisode).where(TCMEpisode.id == episode_id))
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    state_str = body.get("state")
    try:
        episode.state = EpisodeState(state_str)
    except ValueError:
        valid = [s.value for s in EpisodeState]
        raise HTTPException(status_code=400, detail=f"Invalid state. Must be one of: {valid}")

    await db.commit()
    return {"id": episode_id, "state": episode.state.value}


@router.get("/{episode_id}/schedule")
async def get_episode_schedule(episode_id: str, db: AsyncSession = Depends(get_db)):
    """Returns all calls and scheduled call slots for the calendar view."""
    ep_result = await db.execute(select(TCMEpisode).where(TCMEpisode.id == episode_id))
    episode = ep_result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    calls_result = await db.execute(
        select(Call).where(Call.episode_id == episode_id).order_by(Call.started_at)
    )
    calls = calls_result.scalars().all()

    schedules_result = await db.execute(
        select(CallSchedule).where(CallSchedule.episode_id == episode_id).order_by(CallSchedule.scheduled_for)
    )
    schedules = schedules_result.scalars().all()

    return {
        "episode_id": episode_id,
        "discharge_date": episode.discharge_date.isoformat() if episode.discharge_date else None,
        "contact_deadline": episode.contact_deadline.isoformat() if episode.contact_deadline else None,
        "visit_deadline": episode.visit_deadline.isoformat() if episode.visit_deadline else None,
        "billing_date": episode.billing_date.isoformat() if episode.billing_date else None,
        "face_to_face_date": episode.face_to_face_date.isoformat() if episode.face_to_face_date else None,
        "calls": [
            {
                "id": c.id,
                "attempt_number": c.attempt_number,
                "status": c.status.value if c.status else None,
                "started_at": c.started_at.isoformat() if c.started_at else None,
                "ended_at": c.ended_at.isoformat() if c.ended_at else None,
                "summary": c.summary,
            }
            for c in calls
        ],
        "scheduled_calls": [
            {
                "id": s.id,
                "scheduled_for": s.scheduled_for.isoformat(),
                "day_number": s.day_number,
                "completed": s.completed,
            }
            for s in schedules
        ],
    }
