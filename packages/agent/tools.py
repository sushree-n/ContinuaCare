"""Function tools for the ContinuaCare voice agent.

Tools defined here are added to the Agent via `tools=[...]` in agent.py. The
`escalate`, `schedule_appointment`, and `end_call` tools live on the Agent class
itself; this module holds standalone, shared tools.
"""

import logging

from livekit.agents import RunContext, function_tool

logger = logging.getLogger("continuacare.agent")


async def perform_transfer_to_human(reason: str) -> str:
    """Core (mock) transfer logic, callable without a RunContext.

    Shared by the `transfer_to_human` tool and by agent.py's exception handler,
    which needs to bail out to a human on an unexpected error mid-call.

    Args:
        reason: Short factual summary of why we're transferring, e.g.
            "Fever 101.5 F post-pneumonia-discharge".
    """
    # MOCK implementation for the hackathon demo. In production this will perform
    # a real SIP transfer of the patient to the care-team line, e.g.:
    #
    #   from livekit import api, rtc
    #   from livekit.agents import get_job_context
    #   job_ctx = get_job_context()
    #   sip_participant = next(
    #       (p for p in job_ctx.room.remote_participants.values()
    #        if p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP),
    #       None,
    #   )
    #   await job_ctx.api.sip.transfer_sip_participant(
    #       api.TransferSIPParticipantRequest(
    #           room_name=job_ctx.room.name,
    #           participant_identity=sip_participant.identity,
    #           transfer_to="tel:+1XXXXXXXXXX",  # care-team line
    #       )
    #   )
    # The real transfer ends the agent's session once the patient is connected.
    logger.info("MOCK transfer_to_human invoked: %s", reason)
    return "A member of the care team is being connected now; please stay on the line."


@function_tool()
async def transfer_to_human(ctx: RunContext, reason: str) -> str:
    """Connect the patient to a live member of the care team after a red flag.

    Call this immediately after escalate() when the patient reports a warning
    sign. Tell the patient to stay on the line first.

    Args:
        reason: Short factual summary of the red flag, e.g.
            "Fever 101.5 F post-pneumonia-discharge".
    """
    return await perform_transfer_to_human(reason)
