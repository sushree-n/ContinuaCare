import json
import os
from openai import AsyncOpenAI
from prompts import DISCHARGE_ANALYSIS_PROMPT

client = AsyncOpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
)


async def run_triage(
    discharge_notes: str,
    age: int | None,
    known_medications: list[str] | None,
) -> dict:
    prompt = DISCHARGE_ANALYSIS_PROMPT.format(
        age=age or "unknown",
        known_medications=", ".join(known_medications) if known_medications else "none on file",
        discharge_notes=discharge_notes,
    )

    response = await client.chat.completions.create(
        model="anthropic/claude-sonnet-4-5",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    # strip markdown code fences if model wraps output
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)
