"""audit.py — append-only log of every classifier decision.

One JSON object per line in audit.jsonl: the input, the classification, the plan,
and whether it was actually written to Zoho. This is the trail that lets you answer
"why did ticket #X get priority Y?" after the fact. Never committed (gitignored).

    python audit.py            # print a summary of the log
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from classifier import Classification
from mapping import ActionPlan

AUDIT_FILE = Path(__file__).with_name("audit.jsonl")


def _from_email(ticket: dict) -> str:
    return ticket.get("email") or (ticket.get("contact") or {}).get("email") or ""


def log_decision(ticket: dict, c: Classification, plan: ActionPlan,
                 mode: str, applied: bool) -> dict:
    """Append one decision record. mode is 'dry-run' or 'live'; applied is whether
    the writes were actually sent to Zoho."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "applied": applied,
        "ticket_id": str(ticket.get("id")),
        "ticket_number": ticket.get("ticketNumber"),
        "subject": ticket.get("subject"),
        "from_email": _from_email(ticket),
        "classification": {
            "disposition": c.disposition.value,
            "sub_type": c.sub_type.value if c.sub_type else None,
            "priority": c.priority.value if c.priority else None,
            "redirect_to": c.redirect_to,
            "confidence": c.confidence,
            "reasoning": c.reasoning,
        },
        "plan": {
            "field_updates": plan.field_updates,
            "redirect_to": plan.redirect_to,
            "needs_review": plan.needs_review,
            "pending_decision": plan.pending_decision,
            "comment": plan.comment,
        },
    }
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_all() -> list[dict]:
    if not AUDIT_FILE.exists():
        return []
    return [json.loads(line) for line in AUDIT_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


def summary() -> None:
    records = read_all()
    if not records:
        print("audit.jsonl is empty (no decisions logged yet)")
        return
    print(f"{len(records)} decision(s) logged in {AUDIT_FILE.name}\n")
    by_disp: dict[str, int] = {}
    live = 0
    for r in records:
        d = r["classification"]["disposition"]
        by_disp[d] = by_disp.get(d, 0) + 1
        if r.get("applied"):
            live += 1
    print("by disposition:")
    for d, n in sorted(by_disp.items()):
        print(f"  {d:12} {n}")
    print(f"\napplied to Zoho: {live} / {len(records)}")
    print("\nlast 5:")
    for r in records[-5:]:
        cl = r["classification"]
        pr = f"/{cl['priority']}" if cl["priority"] else ""
        flag = "live" if r.get("applied") else r.get("mode")
        print(f"  [{flag}] #{r['ticket_number']} {cl['disposition']}{pr} "
              f"(conf {cl['confidence']:.2f}) - {r['subject']!r}")


if __name__ == "__main__":
    summary()
