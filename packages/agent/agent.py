"""ContinuaCare voice agent — outbound post-discharge follow-up call.

Runs one phone call with a recently-discharged patient: confirms identity, screens
for diagnosis-specific warning signs, and either escalates + transfers to a human on
a red flag or schedules the follow-up visit and closes out cleanly. The behavior is
driven entirely by the system prompt in `prompts.py`.

LiveKit Agents v1.5+ API (AgentServer / @server.rtc_session). See CLAUDE.md — verify
LiveKit code against the live docs (https://docs.livekit.io/mcp) before changing it.

This is the first runnable version:
  * Silero VAD is prewarmed once per process.
  * Patient data is a MOCK fetch (name only) against a hardcoded patient id.
  * escalate / schedule_appointment / end_call are MOCK tools (log + return).
  * Any unexpected error mid-call fails safe by transferring to the care team.
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit import api, rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    InterruptionOptions,
    JobContext,
    JobProcess,
    PreemptiveGenerationOptions,
    RunContext,
    TurnHandlingOptions,
    cli,
    function_tool,
)
from livekit.plugins import deepgram, elevenlabs, openai, silero

from prompts import build_agent_prompt, build_greeting
from tools import end_call, perform_transfer_to_human, transfer_to_human, escalate, schedule_appointment

# Load .env from the repo root by absolute path so the agent works no matter
# which directory it's launched from (this file lives at packages/agent/agent.py,
# so the root is two levels up). override=True so the file is authoritative for
# local dev — a stale/empty shell variable can't shadow it.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

logger = logging.getLogger("continuacare.agent")
logger.setLevel(logging.INFO)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DEFAULT_PATIENT_ID = "demo-patient-001"

# Stored outbound SIP trunk (ST_xxxx) created with `lk sip outbound create`.
# Used to dial the patient when the agent is dispatched for an outbound call.
OUTBOUND_TRUNK_ID = os.getenv("LIVEKIT_SIP_TRUNK_ID")

# Turn handling — let the STT (Deepgram) drive end-of-turn via its own
# end-of-speech signal instead of bare VAD silence, use the adaptive barge-in
# model so brief acknowledgements ("mm-hmm") don't interrupt the agent, and
# generate the reply preemptively to cut latency. VAD is still supplied to the
# session for responsive interruption handling. See LiveKit TurnHandlingOptions.
TURN_HANDLING = TurnHandlingOptions(
    interruption=InterruptionOptions(mode="adaptive"),
    turn_detection="stt",
    preemptive_generation=PreemptiveGenerationOptions(enabled=True),
)

server = AgentServer()


# ---------------------------------------------------------------------------
# Prewarm — load the Silero VAD weights once per process so each new call
# starts fast instead of loading the model on the hot path.
# ---------------------------------------------------------------------------

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


# ---------------------------------------------------------------------------
# Backend fetch (MOCK)
# ---------------------------------------------------------------------------

async def fetch_patient(patient_id: str) -> dict:
    """Fetch the patient record the agent needs for this call.

    MOCK for now — returns a hardcoded record (only the name matters at this
    stage). Later this will be a real call, roughly:

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BACKEND_URL}/patients/{patient_id}")
            resp.raise_for_status()
            return resp.json()

    `prompts.py` reads every field with `.get(..., default)`, so a name-only dict
    is enough to drive a coherent call until more fields (age, diagnosis,
    medications, discharge_date, complexity) are wired in.
    """
    logger.info("MOCK fetch_patient(%s) — would GET %s/patients/%s",
                patient_id, BACKEND_URL, patient_id)
    return {
        "id": patient_id,
        "name": "Jane Smith",
        # TODO: age, diagnosis, medications, discharge_date, complexity, ...
    }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class CareAgent(Agent):
    """Post-discharge follow-up agent for a single patient."""

    def __init__(self, patient: dict):
        super().__init__(
            instructions=build_agent_prompt(patient),
            tools=[transfer_to_human, escalate, schedule_appointment, end_call],
        )
        self.patient = patient
        # Set once the patient (SIP participant) joins on an outbound call;
        # a later real SIP REFER transfer to a human will need this reference.
        self.participant: rtc.RemoteParticipant | None = None

    async def on_enter(self):
        # Drive the opening turn from the kickoff prompt; the detailed rules live
        # in the system prompt (instructions).
        await self.session.generate_reply(instructions=build_greeting(self.patient))



# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

@server.rtc_session(agent_name="continuacare")
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    await ctx.connect()

    # When the agent is dispatched to place an outbound call, the dispatch
    # metadata carries the patient's phone number (E.164) and patient id, e.g.
    #   lk dispatch create --new-room --agent-name continuacare-agent \
    #       --metadata '{"phone_number": "+15105550123", "patient_id": "..."}'
    # When run in console/web mode there's no metadata, so we skip dialing and
    # just talk to whoever is already in the room.
    phone_number = None
    patient_id = DEFAULT_PATIENT_ID
    if ctx.job.metadata:
        try:
            dial_info = json.loads(ctx.job.metadata)
            phone_number = dial_info.get("phone_number")
            patient_id = dial_info.get("patient_id", DEFAULT_PATIENT_ID)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Could not parse job metadata: %r", ctx.job.metadata)

    patient = await fetch_patient(patient_id)
    agent = CareAgent(patient)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(model="nova-3-medical"),
        llm=openai.LLM(
            model="anthropic/claude-sonnet-4-5",
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        ),
        tts=elevenlabs.TTS(
            api_key=os.environ["ELEVENLABS_API_KEY"],
            voice_id=os.environ["ELEVENLABS_VOICE_ID"],
            model="eleven_turbo_v2",
        ),
        turn_handling=TURN_HANDLING,
    )

    # Place the outbound call and wait for the patient to actually pick up
    # before the agent starts speaking — otherwise the CareAgent.on_enter
    # greeting would play into a ringing line. `wait_until_answered=True`
    # blocks until the callee answers or the dial fails.
    if phone_number is not None:
        if not OUTBOUND_TRUNK_ID:
            logger.error("LIVEKIT_SIP_TRUNK_ID is not set — cannot place outbound call")
            ctx.shutdown()
            return
        try:
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=OUTBOUND_TRUNK_ID,
                    sip_call_to=phone_number,
                    participant_identity=phone_number,
                    wait_until_answered=True,
                )
            )
            logger.info("Outbound call to %s answered", phone_number)
            agent.participant = await ctx.wait_for_participant(identity=phone_number)
        except api.TwirpError as e:
            # No answer / busy / rejected / trunk failure — give up this job.
            logger.error(
                "Outbound call to %s failed: %s (SIP %s %s)",
                phone_number, e.message,
                e.metadata.get("sip_status_code"), e.metadata.get("sip_status"),
            )
            ctx.shutdown()
            return

    try:
        await session.start(agent=agent, room=ctx.room)
    except Exception:
        # Fail safe: if anything goes wrong mid-call, get a human on the line
        # rather than leaving the patient with a broken agent.
        logger.exception("Agent session error — transferring to care team")
        try:
            await session.say(
                "I'm sorry, I'm having a technical problem. Let me connect you "
                "to a member of the care team."
            )
        except Exception:
            pass
        await perform_transfer_to_human("Agent technical failure during call")


if __name__ == "__main__":
    cli.run_app(server)
