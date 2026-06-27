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

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
)
from livekit.plugins import anthropic, deepgram, elevenlabs, silero

from prompts import build_agent_prompt, build_greeting
from tools import perform_transfer_to_human, transfer_to_human

# Load .env.local from the repo root by absolute path so the agent works no
# matter which directory it's launched from (this file lives at
# packages/agent/agent.py, so the root is two levels up).
load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")

logger = logging.getLogger("continuacare.agent")
logger.setLevel(logging.INFO)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DEFAULT_PATIENT_ID = "demo-patient-001"

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
            tools=[transfer_to_human],
        )
        self.patient = patient

    async def on_enter(self):
        # Drive the opening turn from the kickoff prompt; the detailed rules live
        # in the system prompt (instructions).
        await self.session.generate_reply(instructions=build_greeting(self.patient))

    @function_tool()
    async def escalate(self, ctx: RunContext, reason: str,
                       severity: str = "urgent") -> str:
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
    async def schedule_appointment(self, ctx: RunContext, agreed: bool,
                                   slot: str = "", reason: str = "") -> str:
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
    async def end_call(self, ctx: RunContext) -> str:
        """End the call once the conversation is complete."""
        # MOCK — later posts the transcript/summary to {BACKEND_URL}/calls/{id}/complete.
        logger.info("MOCK end_call — closing session")
        await self.session.aclose()
        return "Call ended."


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

@server.rtc_session(agent_name="continuacare-agent")
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    patient = await fetch_patient(DEFAULT_PATIENT_ID)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(model="nova-3-medical"),
        llm=anthropic.LLM(model="claude-sonnet-4-6"),
        tts=elevenlabs.TTS(
            voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
            model="eleven_turbo_v2",
        ),
    )

    try:
        await session.start(agent=CareAgent(patient), room=ctx.room)
        await ctx.connect()
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
