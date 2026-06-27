"""TTS-node helpers for the ContinuaCare voice agent.

`adjusted_pronunciation_tts_node` wraps the default TTS node to rewrite text
before synthesis so the ElevenLabs voice pronounces certain tokens correctly
(e.g. a literal "/" read as "slash"). Wired in via CareAgent.tts_node.
"""

import re
from collections.abc import AsyncIterable

from livekit import rtc
from livekit.agents import Agent, ModelSettings

PRONUNCIATIONS: dict[str, str] = {
    r"/": "slash",
}


async def adjusted_pronunciation_tts_node(
    agent: Agent,
    text: AsyncIterable[str],
    model_settings: ModelSettings,
) -> AsyncIterable[rtc.AudioFrame]:
    """TTS node that applies pronunciation substitutions before synthesis."""

    async def apply_pronunciations(in_text: AsyncIterable[str]) -> AsyncIterable[str]:
        async for chunk in in_text:
            modified = chunk
            for pattern, replacement in PRONUNCIATIONS.items():
                modified = re.sub(pattern, replacement, modified, flags=re.IGNORECASE)
            yield modified

    async for frame in Agent.default.tts_node(
        agent, apply_pronunciations(text), model_settings
    ):
        yield frame
