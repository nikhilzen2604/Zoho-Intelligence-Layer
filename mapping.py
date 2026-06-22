"""mapping.py — translate a Classification into a Zoho action plan.

Pure functions only: this module decides WHAT should be written to a ticket and
returns a plan. It performs no network calls — poller.py executes the plan via
zoho_client. That keeps routing logic fully unit-testable with no Zoho access.

Free-tier-safe by design: the decision is written into Zoho's BUILT-IN ticket
fields (priority, classification, category) plus a private comment. Built-in fields
are reliable, readable, and survive when the Enterprise trial downgrades to free.
(Tags were tried first and silently failed to persist, so they are not used.)
"""

from dataclasses import dataclass, field
from typing import Optional

from classifier import Classification, Disposition, Priority, SubType

# Our SLA priority (P1-P4) -> Zoho's built-in priority picklist (High/Medium/Low).
# Exact P1-P4 is never lost: it is also written into the audit comment.
_ZOHO_PRIORITY = {
    Priority.P1: "High",
    Priority.P2: "High",
    Priority.P3: "Medium",
    Priority.P4: "Low",
}

# Our sub_type -> Zoho's built-in classification picklist.
_ZOHO_CLASSIFICATION = {
    SubType.incident: "Problem",
    SubType.question: "Question",
    SubType.service_request: "Others",
}


@dataclass
class ActionPlan:
    """What poller.py should do to a ticket. Empty fields = leave that aspect alone."""
    field_updates: dict = field(default_factory=dict)   # built-in fields to PATCH
    comment: Optional[str] = None                        # private audit note
    redirect_to: Optional[str] = None                    # forward target (intent only)
    needs_review: bool = False                           # park for a human
    pending_decision: bool = False                       # handling deliberately undecided


def _audit_comment(c: Classification) -> str:
    """Human/auditable record of the decision, posted as a private note."""
    lines = [
        "[AI classification]",
        f"disposition: {c.disposition.value}",
    ]
    if c.sub_type:
        lines.append(f"sub_type: {c.sub_type.value}")
    if c.priority:
        lines.append(f"priority: {c.priority.value}")
    if c.redirect_to:
        lines.append(f"redirect_to: {c.redirect_to}")
    lines.append(f"confidence: {c.confidence:.2f}")
    lines.append(f"reasoning: {c.reasoning}")
    return "\n".join(lines)


def plan_actions(c: Classification) -> ActionPlan:
    """Turn a Classification into a concrete Zoho ActionPlan."""
    comment = _audit_comment(c)

    if c.disposition == Disposition.support:
        updates = {"category": "Support"}
        if c.sub_type:
            updates["classification"] = _ZOHO_CLASSIFICATION[c.sub_type]
        if c.priority:
            updates["priority"] = _ZOHO_PRIORITY[c.priority]
        return ActionPlan(field_updates=updates, comment=comment)

    if c.disposition == Disposition.redirect:
        return ActionPlan(
            field_updates={"category": "Redirect"},
            comment=comment,
            redirect_to=c.redirect_to,
        )

    if c.disposition == Disposition.review:
        return ActionPlan(
            field_updates={"category": "Needs Review"},
            comment=comment,
            needs_review=True,
        )

    # --- enhancement ---------------------------------------------------------
    # TODO(decide): the enhancement flow is intentionally NOT implemented yet —
    # the user wants to revisit it. We touch NO fields here. We only leave a record
    # so the ticket is never silently dropped (rule #1). Revisit before go-live.
    if c.disposition == Disposition.enhancement:
        return ActionPlan(comment=comment, pending_decision=True)

    # unreachable, but stay safe: anything unexpected goes to a human
    return ActionPlan(field_updates={"category": "Needs Review"},
                      comment=comment, needs_review=True)


if __name__ == "__main__":
    # offline self-test: build sample Classifications and print their plans (no network)
    samples = [
        Classification(disposition=Disposition.support, sub_type=SubType.incident,
                       priority=Priority.P1, confidence=0.95, reasoning="outage"),
        Classification(disposition=Disposition.support, sub_type=SubType.service_request,
                       priority=Priority.P4, confidence=0.9, reasoning="csv export"),
        Classification(disposition=Disposition.redirect,
                       redirect_to="hello@zenalyst.ai", confidence=0.9, reasoning="pricing"),
        Classification(disposition=Disposition.review, confidence=0.3, reasoning="ambiguous"),
        Classification(disposition=Disposition.enhancement, confidence=0.95, reasoning="slack alerts"),
    ]
    for c in samples:
        p = plan_actions(c)
        print(f"\n[{c.disposition.value}] -> fields={p.field_updates} "
              f"redirect={p.redirect_to} review={p.needs_review} pending={p.pending_decision}")
        print("  comment:")
        for line in p.comment.splitlines():
            print(f"    {line}")
