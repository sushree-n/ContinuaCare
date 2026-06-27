from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
import logging

from database import get_db
from models import Call, CallStatus, TCMEpisode, EpisodeState, Patient

logger = logging.getLogger("continuacare.calls")

router = APIRouter(prefix="/calls", tags=["calls"])


# ---------------------------------------------------------------------------
# Outbound call placement — swap in real Twilio SIP logic here
# ---------------------------------------------------------------------------

async def place_outbound_call(room_name: str, patient_phone: str, episode_id: str, call_id: str):
    """
    TODO (teammate): replace this stub with real LiveKit SIP dispatch.

    Real implementation will look roughly like:
        lk = api.LiveKitAPI(url=LIVEKIT_URL, api_key=..., api_secret=...)
        await lk.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=os.getenv("LIVEKIT_SIP_TRUNK_ID"),
                sip_call_to=patient_phone,
                room_name=room_name,
                participant_identity="care-agent",
                krisp_enabled=True,
            )
        )
    """
    logger.info("STUB place_outbound_call — room=%s phone=%s episode=%s call=%s",
                room_name, patient_phone, episode_id, call_id)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CallResponse(BaseModel):
    id: str
    episode_id: str
    patient_id: str
    livekit_room: Optional[str]
    attempt_number: int
    status: str
    scheduled_at: Optional[datetime]
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    transcript: Optional[str]
    summary: Optional[str]
    flags: Optional[list]
    structured_data: Optional[dict]

    class Config:
        from_attributes = True


class CallCompleteBody(BaseModel):
    transcript: str
    flags: Optional[list[str]] = []
    structured_data: Optional[dict] = {}


class CallNoAnswerBody(BaseModel):
    attempt_number: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/trigger/{episode_id}", response_model=CallResponse, status_code=201)
async def trigger_call(
    episode_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    ep_result = await db.execute(select(TCMEpisode).where(TCMEpisode.id == episode_id))
    episode = ep_result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    pt_result = await db.execute(select(Patient).where(Patient.id == episode.patient_id))
    patient = pt_result.scalar_one_or_none()

    # count existing attempts for this episode
    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count()).select_from(Call).where(Call.episode_id == episode_id)
    )
    attempt_number = (count_result.scalar() or 0) + 1

    room_name = f"continuacare-{episode_id[:8]}-{str(uuid.uuid4())[:8]}"

    call = Call(
        id=str(uuid.uuid4()),
        episode_id=episode_id,
        patient_id=episode.patient_id,
        livekit_room=room_name,
        attempt_number=attempt_number,
        status=CallStatus.IN_PROGRESS,
        started_at=datetime.utcnow(),
    )
    db.add(call)
    episode.state = EpisodeState.CALL_IN_PROGRESS
    await db.commit()
    await db.refresh(call)

    background_tasks.add_task(
        place_outbound_call,
        room_name,
        patient.phone if patient else "",
        episode_id,
        call.id,
    )

    return call


@router.post("/{call_id}/complete", response_model=CallResponse)
async def complete_call(
    call_id: str,
    body: CallCompleteBody,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    call.status = CallStatus.COMPLETED
    call.ended_at = datetime.utcnow()
    call.transcript = body.transcript
    call.flags = body.flags
    call.structured_data = body.structured_data

    ep_result = await db.execute(select(TCMEpisode).where(TCMEpisode.id == call.episode_id))
    episode = ep_result.scalar_one_or_none()
    if episode:
        episode.state = EpisodeState.CALL_COMPLETE

    await db.commit()
    await db.refresh(call)

    # run Claude summarizer in background
    background_tasks.add_task(_run_summarizer, call.id, call.episode_id, body.transcript)

    return call


@router.post("/{call_id}/no-answer", response_model=CallResponse)
async def no_answer(
    call_id: str,
    body: CallNoAnswerBody,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    call.status = CallStatus.NO_ANSWER
    call.ended_at = datetime.utcnow()
    await db.commit()
    await db.refresh(call)

    # retry or escalate after max attempts
    from services.call_manager import handle_no_answer
    await handle_no_answer(call.episode_id, call_id, body.attempt_number, db)

    return call


# ---------------------------------------------------------------------------
# Background: Claude post-call summarizer
# ---------------------------------------------------------------------------

async def _run_summarizer(call_id: str, episode_id: str, transcript: str):
    from database import AsyncSessionLocal
    from sqlalchemy import select as sa_select
    from services.summarizer import run_summarizer

    async with AsyncSessionLocal() as db:
        call_result = await db.execute(sa_select(Call).where(Call.id == call_id))
        call = call_result.scalar_one_or_none()

        ep_result = await db.execute(sa_select(TCMEpisode).where(TCMEpisode.id == episode_id))
        episode = ep_result.scalar_one_or_none()

        if not call or not episode:
            return

        pt_result = await db.execute(sa_select(Patient).where(Patient.id == episode.patient_id))
        patient = pt_result.scalar_one_or_none()

        try:
            summary = await run_summarizer(
                transcript=transcript,
                patient_name=patient.name if patient else "unknown",
                age=patient.age if patient else None,
                diagnosis=patient.diagnosis if patient else "unknown",
                discharge_date=episode.discharge_date,
                attempt_number=call.attempt_number,
            )
            call.summary = summary.get("summary")
            call.structured_data = summary
        except Exception as e:
            logger.error("Summarizer failed for call %s: %s", call_id, e)

        await db.commit()
