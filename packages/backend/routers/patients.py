from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime

from database import get_db
from models import Patient

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
