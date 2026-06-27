from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

from database import get_db
from models import Escalation, EscalationStatus, TCMEpisode, EpisodeState

router = APIRouter(prefix="/escalations", tags=["escalations"])


class EscalationCreate(BaseModel):
    episode_id: str
    call_id: Optional[str] = None
    reason: str
    severity: str = "urgent"  # "urgent" | "monitor"


class EscalationResponse(BaseModel):
    id: str
    episode_id: str
    call_id: Optional[str]
    reason: str
    severity: str
    status: str
    created_at: datetime
    acknowledged_at: Optional[datetime]

    class Config:
        from_attributes = True


class EscalationPatch(BaseModel):
    status: str  # "resolved"


@router.post("", response_model=EscalationResponse, status_code=201)
async def create_escalation(body: EscalationCreate, db: AsyncSession = Depends(get_db)):
    # flip episode state to ESCALATED
    ep_result = await db.execute(select(TCMEpisode).where(TCMEpisode.id == body.episode_id))
    episode = ep_result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    episode.state = EpisodeState.ESCALATED

    escalation = Escalation(
        id=str(uuid.uuid4()),
        episode_id=body.episode_id,
        call_id=body.call_id,
        reason=body.reason,
        severity=body.severity,
        status=EscalationStatus.OPEN,
    )
    db.add(escalation)
    await db.commit()
    await db.refresh(escalation)
    return escalation


@router.get("/open", response_model=list[EscalationResponse])
async def get_open_escalations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Escalation)
        .where(Escalation.status == EscalationStatus.OPEN)
        .order_by(Escalation.created_at.desc())
    )
    return result.scalars().all()


@router.patch("/{escalation_id}", response_model=EscalationResponse)
async def update_escalation(
    escalation_id: str,
    body: EscalationPatch,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Escalation).where(Escalation.id == escalation_id))
    escalation = result.scalar_one_or_none()
    if not escalation:
        raise HTTPException(status_code=404, detail="Escalation not found")

    if body.status == "resolved":
        escalation.status = EscalationStatus.RESOLVED
        escalation.acknowledged_at = datetime.utcnow()
    else:
        raise HTTPException(status_code=400, detail="status must be 'resolved'")

    await db.commit()
    await db.refresh(escalation)
    return escalation
