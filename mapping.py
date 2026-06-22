"""mapping.py — translate a Classification into a Zoho action plan.

Pure functions only: this module decides WHAT should be written to a ticket and
returns a plan. It performs no network calls — poller.py executes the plan via
zoho_client. That keeps routing logic fully unit-testable with no Zoho access.

Free-tier-safe by design: the authoritative record is tags + a private comment
(both survive when the Enterprise trial downgrades to free). The built-in priority
field is set only for human visibility; exact P1-P4 is preserved in tags/comment.
"""

from dataclasses import dataclass, field
from typing import Optional

from classifier import Classification, Disposition, Priority

# Our SLA priority (P1-P4) -> Zoho's built-in priority picklist (High/Medium/Low).
# Exact P1-P4 is never lost: it is also written as a tag and into the audit comment.
_ZOHO_PRIORITY = {
    Priority.P1: "High",
    Priority.P2: "High",
    Priority.P3: "Medium",
    Priority.P4: "Low",
}


@dataclass
class ActionPlan:
    """What poller.py should do to a ticket. Empty fields = leave that aspect alone."""
    field_updates: dict = field(default_factory=dict)   # built-in fields to PATCH
    tags: list[str] = field(default_factory=list)        # tags to associate
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
        tags = ["ai:classified", "ai:support"]
        if c.sub_type:
            tags.append(f"ai:{c.sub_type.value}")
        updates = {}
        if c.priority:
            tags.append(f"ai:{c.priority.value}")
            updates["priority"] = _ZOHO_PRIORITY[c.priority]
        return ActionPlan(field_updates=updates, tags=tags, comment=comment)

    if c.disposition == Disposition.redirect:
        return ActionPlan(
            tags=["ai:classified", "ai:redirect"],
            comment=comment,
            redirect_to=c.redirect_to,
        )

    if c.disposition == Disposition.review:
        return ActionPlan(
            tags=["ai:classified", "needs-review"],
            comment=comment,
            needs_review=True,
        )

    # --- enhancement ---------------------------------------------------------
    # TODO(decide): the enhancement flow is intentionally NOT implemented yet —
    # the user wants to revisit it. We do NO routing here. We only leave a record
    # so the ticket is never silently dropped (rule #1). Revisit before go-live.
    if c.disposition == Disposition.enhancement:
        return ActionPlan(comment=comment, pending_decision=True)

    # unreachable, but stay safe: anything unexpected goes to a human
    return ActionPlan(tags=["needs-review"], comment=comment, needs_review=True)


if __name__ == "__main__":
    # offline self-test: build sample Classifications and print their plans (no network)
    from classifier import SubType

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
        print(f"\n[{c.disposition.value}] -> "
              f"fields={p.field_updates} tags={p.tags} "
              f"redirect={p.redirect_to} review={p.needs_review} pending={p.pending_decision}")
        print("  comment:")
        for line in p.comment.splitlines():
            print(f"    {line}")
