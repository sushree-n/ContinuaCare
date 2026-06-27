"""CareAgent — the post-discharge follow-up agent for a single patient.

Defines the LiveKit `Agent` subclass that drives one outbound call: its behavior
is set by the system prompt in `prompts.py`, with TTS pronunciation fixes and
low-confidence transcript handling layered on via the node/callback overrides.

Kept separate from `agent.py` (the worker entrypoint and session wiring) so the
agent's conversational behavior lives apart from process/dispatch plumbing.
"""

from collections.abc import AsyncIterable

from livekit import rtc
from livekit.agents import Agent, ChatContext, ModelSettings, llm

import transcript_utils
import tts_utils
from prompts import build_agent_prompt, build_greeting
from tools import transfer_to_human, escalate, schedule_appointment, end_call


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

    async def tts_node(
        self, text: AsyncIterable[str], model_settings: ModelSettings
    ) -> AsyncIterable[rtc.AudioFrame]:
        # Apply pronunciation fixes before synthesis (e.g. "/" -> "slash").
        async for frame in tts_utils.adjusted_pronunciation_tts_node(
            self, text, model_settings
        ):
            yield frame

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: llm.ChatMessage
    ) -> None:
        # Drop low-confidence transcripts and ask the patient to repeat rather
        # than letting the LLM act on a likely-misheard symptom report.
        await transcript_utils.handle_low_confidence(self.session, new_message)
