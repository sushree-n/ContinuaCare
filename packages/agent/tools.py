"""Function tools for the ContinuaCare voice agent.

Tools defined here are added to the Agent via `tools=[...]` in agent.py. The
`escalate`, `schedule_appointment`, and `end_call` tools live on the Agent class
itself; this module holds standalone, shared tools.
"""

import logging
import os

from livekit import api, rtc
from livekit.agents import RunContext, function_tool, get_job_context

logger = logging.getLogger("continuacare.agent")

# Spoken to the patient whenever a transfer can't be completed. Fixed wording —
# every error path plays this exact line rather than letting the LLM improvise.
FAILURE_LINE = "I'm unable to connect you right now; the care team will call you back."


async def _say_failure(session) -> str:
    """Speak the fixed failure line on any transfer error, then return a status.

    Used on every error path so the patient always hears the same words rather
    than a paraphrase from the LLM.
    """
    if session is not None:
        try:
            handle = await session.say(FAILURE_LINE, allow_interruptions=False)
            await handle.wait_for_playout()
        except Exception:
            logger.exception("Could not even speak the transfer-failure line")
    return FAILURE_LINE


async def perform_transfer_to_human(reason: str, session=None) -> str:
    """Cold-transfer the patient to the care-team line via SIP REFER.

    Issues a SIP REFER through the Twilio trunk the patient is already on, which
    forwards them to CARE_TEAM_PHONE_NUMBER on the PSTN and ends this LiveKit
    session (the agent drops off). Callable without a RunContext, so agent.py's
    exception handler can also bail out to a human on an unexpected error mid-call.

    On any failure — no destination configured, no SIP caller in the room, or a
    rejected/failed REFER — the patient hears FAILURE_LINE and the call stays up.

    Args:
        reason: Short factual summary of why we're transferring, e.g.
            "Fever 101.5 F post-pneumonia-discharge".
        session: The AgentSession, used to speak to the patient before the line
            drops. Optional so the function still works without one.
    """
    care_team_number = os.getenv("CARE_TEAM_PHONE_NUMBER")
    if not care_team_number:
        logger.error("CARE_TEAM_PHONE_NUMBER not set — cannot transfer")
        return await _say_failure(session)

    try:
        job_ctx = get_job_context()

        # Find the active SIP caller. Identity is assigned at dispatch time and
        # may not equal the phone number, so filter on participant kind instead.
        # Assumes a single SIP caller per room (true for our outbound calls).
        sip_participant = next(
            (p for p in job_ctx.room.remote_participants.values()
             if p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP),
            None,
        )
        if sip_participant is None:
            logger.error("No SIP participant to transfer (reason: %s)", reason)
            return await _say_failure(session)

        # Let the "stay on the line" message play fully BEFORE the REFER, because
        # a cold transfer disconnects the patient the moment it's accepted.
        if session is not None:
            handle = await session.say(
                "Please stay on the line — I'm connecting you to a member of the "
                "care team now.",
                allow_interruptions=False,
            )
            await handle.wait_for_playout()

        logger.info("Cold-transferring SIP %s to %s (reason: %s)",
                    sip_participant.identity, care_team_number, reason)
        await job_ctx.api.sip.transfer_sip_participant(
            api.TransferSIPParticipantRequest(
                room_name=job_ctx.room.name,
                participant_identity=sip_participant.identity,
                transfer_to=f"tel:{care_team_number}",
                play_dialtone=False,
            )
        )
    except api.TwirpError as e:
        logger.error("SIP transfer failed: %s (SIP %s %s)", e.message,
                     e.metadata.get("sip_status_code"), e.metadata.get("sip_status"))
        return await _say_failure(session)
    except Exception:
        # Safety-critical red-flag path: any unexpected failure still gets the
        # patient the spoken fallback rather than silence or a raw LLM apology.
        logger.exception("Unexpected error during transfer (reason: %s)", reason)
        return await _say_failure(session)

    return "A member of the care team is being connected now."


@function_tool()
async def transfer_to_human(ctx: RunContext, reason: str) -> str:
    """Connect the patient to a live member of the care team after a red flag.

    Call this immediately after escalate() when the patient reports a warning
    sign. This tool speaks the "stay on the line" message itself before
    connecting, so do not say it yourself first.

    Args:
        reason: Short factual summary of the red flag, e.g.
            "Fever 101.5 F post-pneumonia-discharge".
    """
    return await perform_transfer_to_human(reason, ctx.session)


@function_tool()
async def escalate(ctx: RunContext, reason: str, severity: str = "urgent") -> str:
    """Record a clinical red flag for the care team.

    Call this IMMEDIATELY when the patient reports a warning sign, before
    transferring. Do not wait until the end of the call.

    Args:
        reason: Short factual summary, e.g. "Chest tightness since yesterday".
        severity: "urgent" for emergencies, "monitor" for lower-acuity concerns.
    """
    # MOCK — later POSTs to {BACKEND_URL}/escalations.
    logger.info("MOCK escalate (%s): %s", severity, reason)
    return "Escalation recorded for the care team."


@function_tool()
async def schedule_appointment(ctx: RunContext, agreed: bool, slot: str = "", reason: str = "") -> str:
    """Log the outcome of offering a follow-up visit.

    Args:
        agreed: True if the patient accepted a time slot.
        slot: The agreed time, e.g. "Tuesday at 10 a.m." (when agreed=True).
        reason: Why the patient declined or wants to wait (when agreed=False).
    """
    # MOCK — later POSTs the scheduling decision back to the backend.
    if agreed:
        logger.info("MOCK schedule_appointment agreed: %s", slot)
        return f"Follow-up visit booked for {slot}."
    logger.info("MOCK schedule_appointment declined: %s", reason)
    return "Logged that the patient is not scheduling a visit right now."


@function_tool()
async def end_call(ctx: RunContext) -> str:
    """End the call once the conversation is complete."""
    # MOCK — later posts the transcript/summary to {BACKEND_URL}/calls/{id}/complete.
    logger.info("MOCK end_call — closing session")
    await ctx.session.aclose()
    return "Call ended."