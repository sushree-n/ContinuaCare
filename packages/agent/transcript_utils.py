"""Transcript-quality helpers for the ContinuaCare voice agent.

`handle_low_confidence` runs in the on_user_turn_completed hook: if Deepgram's
transcript confidence for the patient's last turn is below threshold, it drops
the turn and asks the patient to repeat instead of letting the LLM act on a
likely-misheard utterance — important on a medical follow-up call where a
mis-transcribed symptom could be acted on or missed.
"""

import logging

from livekit.agents import AgentSession, StopResponse, llm

logger = logging.getLogger("continuacare.agent")

# Deepgram per-utterance confidence below this is treated as "didn't catch it"
# and the patient is asked to repeat. Tune against real call audio.
CONFIDENCE_THRESHOLD = 0.8


async def handle_low_confidence(session: AgentSession, new_message: llm.ChatMessage) -> None:
    """Intercepts low confidence transcripts and asks user to repeat."""
    confidence: float | None = new_message.transcript_confidence

    if confidence is not None and confidence < CONFIDENCE_THRESHOLD:
        logger.info(f"Low transcript confidence: {confidence:.2f}, asking user to repeat")
        new_message.content = []
        await session.say("I'm sorry, I didn't quite catch that. Could you please repeat?")
        raise StopResponse()
