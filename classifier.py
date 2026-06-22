"""The brain: schema, prompt, and classify().

Provider-agnostic in spirit, but wired to DeepSeek via its OpenAI-compatible API.
Knows nothing about Zoho — it only reads a message and returns a decision.
"""

import json
import os
from enum import Enum
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ValidationError

load_dotenv()

MODEL = os.getenv("CLASSIFIER_MODEL", "deepseek-chat")
MIN_CONFIDENCE = float(os.getenv("CLASSIFIER_MIN_CONFIDENCE", "0.6"))
DEFAULT_REDIRECT = os.getenv("DEFAULT_REDIRECT", "hello@zenalyst.ai")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
API_KEY = os.getenv("DEEPSEEK_API_KEY")


# --- schema -----------------------------------------------------------------

class Disposition(str, Enum):
    support = "support"          # a real support request -> support queue
    enhancement = "enhancement"  # new-feature request -> separate review gate
    redirect = "redirect"        # misdirected but legitimate -> forward elsewhere
    review = "review"            # uncertain / needs a human. NEVER closed.


class SubType(str, Enum):
    incident = "incident"                # something is broken
    service_request = "service_request"  # a standard ask (access, export, config)
    question = "question"                # how-to / clarification


class Priority(str, Enum):
    P1 = "P1"  # production down / critical / data loss
    P2 = "P2"  # major function impaired, no workaround
    P3 = "P3"  # minor issue or workaround exists
    P4 = "P4"  # trivial / cosmetic / low urgency


class Classification(BaseModel):
    disposition: Disposition
    sub_type: Optional[SubType] = None
    priority: Optional[Priority] = None
    redirect_to: Optional[str] = None
    confidence: float
    reasoning: str


# --- prompt -----------------------------------------------------------------

SYSTEM_PROMPT = f"""You are the routing brain for Zenalyst's customer support, which runs on Zoho Desk.
You read one incoming message and decide what should happen to it. You output JSON only.

Pick exactly one `disposition`:
- "support": a genuine support request from a customer. Then you MUST also set:
    - "sub_type": one of "incident" (something is broken), "service_request"
      (a standard operational ask like access/export/config), "question" (how-to).
    - "priority": one of "P1" (production down/critical/data loss), "P2" (major
      function impaired, no workaround), "P3" (minor or workaround exists),
      "P4" (trivial/cosmetic/low urgency).
- "enhancement": a request for a NEW feature or capability that does not exist yet.
    Do NOT set priority or sub_type. This goes to a separate product review gate, not support.
- "redirect": legitimate mail that was sent to the wrong place (e.g. pricing, sales,
    partnership, billing-account questions). Set "redirect_to" to the right inbox
    (default "{DEFAULT_REDIRECT}"). Never treat misdirected legitimate mail as spam.
- "review": you are not confident, or the message is ambiguous/empty/spam-like.
    A human will look at it.

HARD RULES:
- Never invent a "close" or "spam-delete" outcome. The lowest action is "review".
- Only "support" gets sub_type and priority. Only "redirect" gets redirect_to.
- "confidence" is your own 0.0-1.0 certainty in this decision.
- "reasoning" is ONE short line.

Return JSON with exactly these keys:
{{"disposition", "sub_type", "priority", "redirect_to", "confidence", "reasoning"}}
Use null for keys that do not apply."""


def _build_user_prompt(subject: str, body: str, from_email: str) -> str:
    return (
        f"From: {from_email}\n"
        f"Subject: {subject}\n\n"
        f"{body}\n\n"
        "Classify this message. Respond with JSON only."
    )


# --- client -----------------------------------------------------------------

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not API_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY is not set (see .env.example)")
        _client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return _client


# --- public API -------------------------------------------------------------

def classify(subject: str, body: str, from_email: str) -> Classification:
    """Read one message, return a routing Classification.

    Applies the two structural guarantees after the model answers:
      1. confidence below the threshold is downgraded to "review" (nothing slips
         through silently);
      2. a redirect with no target falls back to DEFAULT_REDIRECT.
    """
    client = _get_client()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(subject, body, from_email)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    raw = resp.choices[0].message.content
    result = _parse(raw)
    return _apply_guarantees(result)


def _parse(raw: str) -> Classification:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return Classification(
            disposition=Disposition.review,
            confidence=0.0,
            reasoning="model returned unparseable output; parked for review",
        )
    # normalize empty strings to None so optional enums validate
    for k in ("sub_type", "priority", "redirect_to"):
        if data.get(k) in ("", "null", "none", "N/A"):
            data[k] = None
    try:
        return Classification(**data)
    except ValidationError:
        return Classification(
            disposition=Disposition.review,
            confidence=0.0,
            reasoning="model output failed schema validation; parked for review",
        )


def _apply_guarantees(c: Classification) -> Classification:
    # rule 1: low confidence -> review, and strip support-only fields
    if c.confidence < MIN_CONFIDENCE and c.disposition != Disposition.review:
        return Classification(
            disposition=Disposition.review,
            confidence=c.confidence,
            reasoning=f"low confidence ({c.confidence:.2f}); downgraded to review. "
                      f"original: {c.reasoning}",
        )
    # rule 2: redirect must have a target
    if c.disposition == Disposition.redirect and not c.redirect_to:
        c.redirect_to = DEFAULT_REDIRECT
    # keep support-only fields off non-support dispositions
    if c.disposition != Disposition.support:
        c.sub_type = None
        c.priority = None
    return c
