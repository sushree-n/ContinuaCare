import os
import logging
import httpx

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from database import get_db
from models import Patient, TCMEpisode, Call, CallSchedule, Escalation

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
