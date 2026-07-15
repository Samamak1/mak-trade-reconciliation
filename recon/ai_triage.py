"""Break triage: deterministic rules by default, optional LLM assist.

The DEFAULT and always-available path is a rule-based classifier that is
fully deterministic and unit-tested. If (and only if) ANTHROPIC_API_KEY
or GROQ_API_KEY is present in the environment AND the caller passes
``use_llm=True``, breaks are sent to the corresponding API for a
second-opinion classification. No key ships with this repo; the value is
read from the environment only, and every result is labeled with its
source ("rules" or "llm:<provider>") so the two are never conflated.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional

from .models import Break

_RULES = {
    "MISSING_INTERNAL": (
        "booking_gap",
        "Confirm with counterparty; if valid, book the trade internally today.",
    ),
    "MISSING_COUNTERPARTY": (
        "confirmation_gap",
        "Chase counterparty confirmation; escalate if unconfirmed by T+1.",
    ),
    "QUANTITY": (
        "economic_mismatch",
        "Freeze allocation; verify executed quantity against venue fill report.",
    ),
    "SETTLEMENT_DATE": (
        "lifecycle_mismatch",
        "Check holiday calendars and confirm intended settlement cycle.",
    ),
}


@dataclass(frozen=True)
class TriageResult:
    category: str
    suggested_action: str
    source: str


def triage_rules(b: Break) -> TriageResult:
    """Deterministic rule-based triage (the default path)."""
    if b.break_type == "PRICE":
        if b.severity == "HIGH":
            return TriageResult(
                "likely_bad_fill_or_fat_finger",
                "Verify execution price against venue/exchange print before amending.",
                "rules",
            )
        return TriageResult(
            "minor_price_tolerance_breach",
            "Compare fee/commission treatment; amend the smaller-confidence side.",
            "rules",
        )
    cat, action = _RULES.get(
        b.break_type,
        ("unclassified", "Route to reconciliation analyst for manual review."),
    )
    return TriageResult(cat, action, "rules")


def _llm_provider() -> Optional[str]:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    return None


def _triage_llm(b: Break, provider: str) -> TriageResult:
    """Classify one break via an LLM API. Requires httpx and a key."""
    import httpx  # imported lazily; not needed for the default path

    prompt = (
        "Classify this trade reconciliation break and suggest one action. "
        "Reply as JSON with keys category and action.\n"
        + json.dumps(b.to_dict())
    )
    if provider == "anthropic":
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"]
    else:
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(text[text.index("{"): text.rindex("}") + 1])
        return TriageResult(
            str(parsed.get("category", "unclassified")),
            str(parsed.get("action", "manual review")),
            f"llm:{provider}",
        )
    except (ValueError, KeyError):
        return triage_rules(b)  # fall back rather than fail the run


def triage_breaks(breaks: List[Break], use_llm: bool = False) -> List[Break]:
    """Annotate breaks in place with triage fields; returns the same list.

    Rules are the default. LLM path runs only when explicitly requested
    AND a key exists in the environment; any API failure falls back to
    rules so the pipeline never depends on network access.
    """
    provider = _llm_provider() if use_llm else None
    for b in breaks:
        if provider is not None:
            try:
                t = _triage_llm(b, provider)
            except Exception:
                t = triage_rules(b)
        else:
            t = triage_rules(b)
        b.triage_category = t.category
        b.triage_action = t.suggested_action
        b.triage_source = t.source
    return breaks
