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

# Load .env.local from the repo root by absolute path so the agent works no
# matter which directory it's launched from (this file lives at
# packages/agent/agent.py, so the root is two levels up).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger("continuacare.agent")
logger.setLevel(logging.INFO)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DEFAULT_PATIENT_ID = "demo-patient-001"

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
    """Fetch the patient + active episode data the agent needs for this call."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{BACKEND_URL}/patients/{patient_id}")
            resp.raise_for_status()
            patient = resp.json()

        # also pull the active episode for discharge_date + complexity
        async with httpx.AsyncClient(timeout=10) as client:
            ep_resp = await client.get(f"{BACKEND_URL}/patients/{patient_id}/episode")
            if ep_resp.status_code == 200:
                episode = ep_resp.json()
                patient["discharge_date"] = episode.get("discharge_date")
                patient["complexity"] = episode.get("complexity")

        logger.info("fetch_patient(%s) — name=%s diagnosis=%s",
                    patient_id, patient.get("name"), patient.get("diagnosis"))
        return patient

    except Exception as e:
        logger.error("fetch_patient(%s) failed: %s — using fallback", patient_id, e)
        return {"id": patient_id, "name": "the patient"}


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

    async def on_enter(self):
        # Drive the opening turn from the kickoff prompt; the detailed rules live
        # in the system prompt (instructions).
        await self.session.generate_reply(instructions=build_greeting(self.patient))



# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

@server.rtc_session(agent_name="continuacare-agent")
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    # Pull call context from room metadata (set by backend when dispatching).
    # Falls back to demo defaults so the agent still works from the playground.
    import json as _json
    try:
        meta = _json.loads(ctx.room.metadata or "{}")
    except Exception:
        meta = {}

    ctx.userdata["episode_id"] = meta.get("episode_id", "demo-episode")
    ctx.userdata["call_id"] = meta.get("call_id", "demo-call")
    ctx.userdata["patient_id"] = meta.get("patient_id", DEFAULT_PATIENT_ID)

    patient = await fetch_patient(ctx.userdata["patient_id"])

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
