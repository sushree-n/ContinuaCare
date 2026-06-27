import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from openai import AsyncOpenAI
from prompts import CALL_SUMMARY_PROMPT

client = AsyncOpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
)


async def run_summarizer(
    transcript: str,
    patient_name: str,
    age: int | None,
    diagnosis: str,
    discharge_date: datetime,
    attempt_number: int,
) -> dict:
    prompt = CALL_SUMMARY_PROMPT.format(
        patient_name=patient_name,
        age=age or "unknown",
        diagnosis=diagnosis,
        discharge_date=discharge_date.strftime("%Y-%m-%d") if discharge_date else "unknown",
        attempt_number=attempt_number,
        transcript=transcript,
    )

    response = await client.chat.completions.create(
        model="anthropic/claude-sonnet-4-5",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)
