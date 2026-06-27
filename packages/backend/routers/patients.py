from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime

from database import get_db
from models import Patient, TCMEpisode

router = APIRouter(prefix="/patients", tags=["patients"])


class PatientCreate(BaseModel):
    name: str
    age: Optional[int] = None
    phone: str
    diagnosis: str
    medications: Optional[list[str]] = None


class PatientResponse(BaseModel):
    id: str
    name: str
    age: Optional[int]
    phone: str
    diagnosis: str
    medications: Optional[list]
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("", response_model=PatientResponse, status_code=201)
async def create_patient(body: PatientCreate, db: AsyncSession = Depends(get_db)):
    patient = Patient(
        id=str(uuid.uuid4()),
        **body.model_dump(),
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return patient


@router.get("", response_model=list[PatientResponse])
async def list_patients(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Patient).order_by(Patient.created_at.desc()))
    return result.scalars().all()


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(patient_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.get("/{patient_id}/episode")
async def get_patient_active_episode(patient_id: str, db: AsyncSession = Depends(get_db)):
    """Returns the most recent active episode for a patient — used by the agent at call start."""
    result = await db.execute(
        select(TCMEpisode)
        .where(TCMEpisode.patient_id == patient_id)
        .order_by(TCMEpisode.created_at.desc())
    )
    episode = result.scalars().first()
    if not episode:
        raise HTTPException(status_code=404, detail="No episode found for patient")

    return {
        "id": episode.id,
        "patient_id": episode.patient_id,
        "state": episode.state.value if episode.state else None,
        "discharge_date": episode.discharge_date.isoformat() if episode.discharge_date else None,
        "discharge_notes": episode.discharge_notes,
        "complexity": episode.complexity.value if episode.complexity else None,
        "triage_rationale": episode.triage_rationale,
        "visit_window_days": episode.visit_window_days,
        "contact_deadline": episode.contact_deadline.isoformat() if episode.contact_deadline else None,
        "visit_deadline": episode.visit_deadline.isoformat() if episode.visit_deadline else None,
        "face_to_face_date": episode.face_to_face_date.isoformat() if episode.face_to_face_date else None,
        "cpt_code": episode.cpt_code,
        "ready_to_bill": episode.ready_to_bill,
    }
