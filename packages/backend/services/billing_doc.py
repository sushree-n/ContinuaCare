import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from openai import AsyncOpenAI
from prompts import BILLING_DOC_PROMPT

client = AsyncOpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
)


async def run_billing_doc(
    patient_name: str,
    age: int | None,
    diagnosis: str,
    discharge_date,
    contact_deadline,
    face_to_face_date,
    visit_deadline,
    complexity: str,
    cpt_code: str,
    billing_date,
    med_rec_completed: bool,
    outreach_log: list[dict],
    escalations: list[dict],
) -> dict:
    def fmt(dt):
        return dt.strftime("%Y-%m-%d") if dt else "pending"

    prompt = BILLING_DOC_PROMPT.format(
        patient_name=patient_name,
        age=age or "unknown",
        diagnosis=diagnosis,
        discharge_date=fmt(discharge_date),
        contact_deadline=fmt(contact_deadline),
        face_to_face_date=fmt(face_to_face_date) if face_to_face_date else "not yet completed",
        visit_deadline=fmt(visit_deadline),
        complexity=complexity,
        cpt_code=cpt_code or "pending",
        billing_date=fmt(billing_date),
        med_rec_completed="Yes" if med_rec_completed else "No",
        outreach_log=json.dumps(outreach_log, default=str),
        escalations=json.dumps(escalations, default=str),
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
