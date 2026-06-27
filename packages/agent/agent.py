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
from livekit import api
from livekit.agents import (
    AgentServer,
    AgentSession,
    InterruptionOptions,
    JobContext,
    JobProcess,
    PreemptiveGenerationOptions,
    TurnHandlingOptions,
    cli,
    room_io,
)
from livekit.plugins import deepgram, elevenlabs, noise_cancellation, openai, silero

from care_agent import CareAgent
from tools import perform_transfer_to_human

# Load .env from the repo root by absolute path so the agent works no matter
# which directory it's launched from (this file lives at packages/agent/agent.py,
# so the root is two levels up). override=True so the file is authoritative for
# local dev — a stale/empty shell variable can't shadow it.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

logger = logging.getLogger("continuacare.agent")
logger.setLevel(logging.INFO)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DEFAULT_PATIENT_ID = "232d80d2-9ce2-45ee-b2a9-ae843019f38e"
DEFAULT_EPISODE_ID = "90c838cd-bdc9-4ce7-bddb-e5d8230524e0"
DEFAULT_CALL_ID = "9521eb60-b1f6-437a-a4d0-9712476818a0"

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
# Call completion (shutdown hook)
# ---------------------------------------------------------------------------

async def post_call_complete(session: AgentSession, call_context: dict) -> None:
    """Post the call transcript + outcome to the backend when the session ends.

    Registered as a job shutdown callback so it runs on every end path: the agent
    calling end_call, the patient hanging up, or a mid-call error. The backend
    marks the Call complete, advances the episode, and runs the Claude summarizer.

    Skips the POST when there's no transcript (session never really got going), to
    avoid recording an empty completion for a call that didn't happen.
    """
    import httpx

    call_id = call_context.get("call_id")
    # history.items is a union (messages, function calls, …); keep only chat
    # messages and use text_content, which joins the message's text parts.
    transcript = "\n".join(
        f"{item.role}: {item.text_content}"
        for item in session.history.items
        if item.type == "message" and item.text_content
    )
    if not transcript:
        logger.info("post_call_complete — empty transcript, skipping (call=%s)", call_id)
        return

    # Visit outcome stashed by the schedule_appointment tool (if it ran).
    structured_data = session.userdata.get("visit_outcome") or {}

    logger.info("post_call_complete — call=%s chars=%d", call_id, len(transcript))
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{BACKEND_URL}/calls/{call_id}/complete", json={
                "transcript": transcript,
                "flags": [],
                "structured_data": structured_data,
            })
    except Exception as e:
        logger.error("Failed to POST call complete to backend: %s", e)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

@server.rtc_session(agent_name="continuacare")
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    await ctx.connect()

    # Parse dispatch metadata — carries phone_number, patient_id, episode_id, call_id.
    # Falls back to demo defaults so the agent still works from the playground.
    phone_number = None
    meta = {}
    if ctx.job.metadata:
        try:
            meta = json.loads(ctx.job.metadata)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Could not parse job metadata: %r", ctx.job.metadata)

    logger.info("parsed meta: %s", meta)

    phone_number = meta.get("phone_number")
    call_context = {
        "patient_id": meta.get("patient_id", DEFAULT_PATIENT_ID),
        "episode_id": meta.get("episode_id", DEFAULT_EPISODE_ID),
        "call_id": meta.get("call_id", DEFAULT_CALL_ID),
    }

    patient = await fetch_patient(call_context["patient_id"])
    agent = CareAgent(patient)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        userdata=call_context,
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

    # Post the call completion on EVERY end path — agent end_call, patient hangup,
    # or mid-call error — by registering it as a job shutdown hook. Registered only
    # after the dial succeeded, so the no-answer / no-trunk paths above (which
    # ctx.shutdown() and return) never post a spurious completion.
    ctx.add_shutdown_callback(lambda: post_call_complete(session, call_context))

    try:
        # Clean the patient's inbound audio before STT/turn detection with Krisp's
        # telephony-tuned background voice cancellation (removes background voices
        # and noise on the line). Improves transcript confidence on noisy calls —
        # see transcript_utils.handle_low_confidence. Requires LiveKit Cloud.
        #
        # delete_room_on_close: when the session closes (end_call shutdown or patient
        # hangup), delete the room so the SIP patient is disconnected instead of left
        # on a silent line until they hang up themselves.
        await session.start(
            agent=agent,
            room=ctx.room,
            room_options=room_io.RoomOptions(
                audio_input=room_io.AudioInputOptions(
                    noise_cancellation=noise_cancellation.BVCTelephony(),
                ),
                delete_room_on_close=True,
            ),
        )
    except Exception:
        # Fail safe: if anything goes wrong mid-call, get a human on the line
        # rather than leaving the patient with a broken agent. perform_transfer
        # owns the spoken announcement (and the failure fallback) itself.
        logger.exception("Agent session error — transferring to care team")
        await perform_transfer_to_human("Agent technical failure during call", session)


if __name__ == "__main__":
    cli.run_app(server)
