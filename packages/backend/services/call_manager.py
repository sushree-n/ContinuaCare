import logging
import os
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("continuacare.call_manager")

MAX_ATTEMPTS = 3
RETRY_DELAY_DEMO = 10   # seconds
RETRY_DELAY_PROD = 3600  # 60 minutes in seconds
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"


async def handle_no_answer(episode_id: str, call_id: str, attempt: int, db: AsyncSession):
    if attempt < MAX_ATTEMPTS:
        delay = RETRY_DELAY_DEMO if DEMO_MODE else RETRY_DELAY_PROD
        run_at = datetime.utcnow() + timedelta(seconds=delay)
        logger.info(
            "No answer on attempt %d/%d for episode %s — scheduling retry at %s",
            attempt, MAX_ATTEMPTS, episode_id, run_at.isoformat(),
        )
        _schedule_retry(episode_id, run_at)
    else:
        logger.info(
            "No answer after %d attempts for episode %s — escalating to monitor",
            MAX_ATTEMPTS, episode_id,
        )
        await _escalate_no_answer(episode_id, call_id, db)


def _schedule_retry(episode_id: str, run_at: datetime):
    """Schedule a retry call via APScheduler.

    TODO: wire up once scheduler.py is implemented. For now logs the intent.
    """
    logger.info("STUB _schedule_retry — episode=%s run_at=%s", episode_id, run_at)


async def _escalate_no_answer(episode_id: str, call_id: str, db: AsyncSession):
    from models import Escalation, EscalationStatus, TCMEpisode, EpisodeState
    from sqlalchemy import select
    import uuid

    ep_result = await db.execute(select(TCMEpisode).where(TCMEpisode.id == episode_id))
    episode = ep_result.scalar_one_or_none()
    if episode:
        episode.state = EpisodeState.ESCALATED

    escalation = Escalation(
        id=str(uuid.uuid4()),
        episode_id=episode_id,
        call_id=call_id,
        reason=f"No answer after {MAX_ATTEMPTS} attempts. Human follow-up required to preserve TCM billability.",
        severity="monitor",
        status=EscalationStatus.OPEN,
    )
    db.add(escalation)
    await db.commit()
