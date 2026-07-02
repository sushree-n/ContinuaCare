import os
import uuid
import logging
import httpx

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime

from database import get_db
from models import Patient, TCMEpisode, Call, CallStatus, CallSchedule, Escalation

logger = logging.getLogger("continuacare.demo")

DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

router = APIRouter(prefix="/demo", tags=["demo"])


def _require_demo_mode():
    if not DEMO_MODE:
        raise HTTPException(status_code=403, detail="Demo endpoints are disabled (DEMO_MODE is not set).")


@router.post("/fast-forward/{episode_id}")
async def fast_forward(episode_id: str, db: AsyncSession = Depends(get_db)):
    """Skip the call delay and trigger an outbound call immediately."""
    _require_demo_mode()

    result = await db.execute(select(TCMEpisode).where(TCMEpisode.id == episode_id))
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    logger.info("fast-forward: triggering call for episode %s (state=%s)", episode_id, episode.state)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{BACKEND_URL}/calls/trigger/{episode_id}")
        resp.raise_for_status()

    return {"episode_id": episode_id, "triggered": True, "call": resp.json()}


@router.post("/web-call/{episode_id}")
async def start_web_call(episode_id: str, db: AsyncSession = Depends(get_db)):
    """Create a LiveKit room, dispatch the agent (no SIP), return a browser token."""
    ep_result = await db.execute(select(TCMEpisode).where(TCMEpisode.id == episode_id))
    episode = ep_result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    pt_result = await db.execute(select(Patient).where(Patient.id == episode.patient_id))
    patient = pt_result.scalar_one_or_none()

    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count()).select_from(Call).where(Call.episode_id == episode_id)
    )
    attempt_number = (count_result.scalar() or 0) + 1

    room_name = f"continuacare-web-{episode_id[:8]}-{str(uuid.uuid4())[:8]}"
    call_id = str(uuid.uuid4())

    call = Call(
        id=call_id,
        episode_id=episode_id,
        patient_id=episode.patient_id,
        livekit_room=room_name,
        attempt_number=attempt_number,
        status=CallStatus.IN_PROGRESS,
        started_at=datetime.utcnow(),
    )
    db.add(call)
    from models import EpisodeState
    episode.state = EpisodeState.CALL_IN_PROGRESS
    await db.commit()

    lk_url = os.environ["LIVEKIT_URL"]
    lk_key = os.environ["LIVEKIT_API_KEY"]
    lk_secret = os.environ["LIVEKIT_API_SECRET"]

    import json
    from livekit import api as lkapi

    metadata = json.dumps({
        "patient_id": episode.patient_id,
        "episode_id": episode_id,
        "call_id": call_id,
    })

    async with lkapi.LiveKitAPI(url=lk_url, api_key=lk_key, api_secret=lk_secret) as lk:
        await lk.agent_dispatch.create_dispatch(
            lkapi.CreateAgentDispatchRequest(
                agent_name="continuacare",
                room=room_name,
                metadata=metadata,
            )
        )

    token = (
        lkapi.AccessToken(api_key=lk_key, api_secret=lk_secret)
        .with_identity("browser-user")
        .with_name(patient.name if patient else "Demo User")
        .with_grants(lkapi.VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )

    return {
        "token": token,
        "room": room_name,
        "ws_url": lk_url,
        "call_id": call_id,
    }


@router.get("/reset")
async def reset(db: AsyncSession = Depends(get_db)):
    """Wipe all data so a fresh demo can be run."""
    _require_demo_mode()

    # Delete in FK-safe order: child tables first
    esc   = await db.execute(delete(Escalation))
    sched = await db.execute(delete(CallSchedule))
    calls = await db.execute(delete(Call))
    eps   = await db.execute(delete(TCMEpisode))
    pts   = await db.execute(delete(Patient))
    await db.commit()

    counts = {
        "escalations":    esc.rowcount,
        "call_schedules": sched.rowcount,
        "calls":          calls.rowcount,
        "episodes":       eps.rowcount,
        "patients":       pts.rowcount,
    }
    logger.info("demo reset — deleted: %s", counts)
    return {"reset": True, "deleted": counts}
