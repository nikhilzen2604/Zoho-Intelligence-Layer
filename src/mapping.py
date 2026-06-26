"""mapping.py — translate a Classification into a Zoho action plan.

Pure functions only: this module decides WHAT should be written to a ticket and
returns a plan. It performs no network calls — poller.py executes the plan via
zoho_client. That keeps routing logic fully unit-testable with no Zoho access.

Free-tier-safe by design: the decision is written into Zoho's BUILT-IN ticket
fields (priority, classification, category) plus a private comment. Built-in fields
are reliable, code-readable, and survive when the Enterprise trial downgrades to free.

Tags are ALSO written, but only as human-facing routing labels: Zoho does not expose
`category` as a custom-view filter, whereas Tags IS filterable. So the team builds
views like "Needs Review" on the `needs-review` tag. Tags are not code-readable, so
they are never relied on as the machine record — that is the built-in fields' job.
"""

from dataclasses import dataclass, field
from typing import Optional

from classifier import Classification, Disposition, Priority, SubType

# Priority is written into Zoho's built-in Priority field as the exact P1-P4 value.
# The field accepts these directly, so P1 vs P2 stays distinct and filterable in the
# UI (Zoho's default High/Medium/Low would collapse P1 and P2 into "High").

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
    tags: list[str] = field(default_factory=list)        # human-facing routing labels
    comment: Optional[str] = None                        # private audit note
    redirect_to: Optional[str] = None                    # forward target (intent only)
    needs_review: bool = False                           # park for a human
    pending_decision: bool = False                       # handling deliberately undecided
    assignee_role: Optional[str] = None                  # logical owner role; poller maps to an email
    github_issue: bool = False                           # mirror to the GitHub backlog
    github_labels: list[str] = field(default_factory=list)


def _audit_comment(c: Classification) -> str:
    """Human/auditable record of the decision, posted as a private note.

    Formatted as HTML: Zoho renders comments as HTML and collapses plain
    newlines, so we use <br> to keep each field on its own readable line.
    """
    rows = [("Disposition", c.disposition.value)]
    if c.sub_type:
        rows.append(("Sub-type", c.sub_type.value))
    if c.priority:
        rows.append(("Priority", c.priority.value))
    if c.redirect_to:
        rows.append(("Redirect to", c.redirect_to))
    rows.append(("Confidence", f"{c.confidence:.2f}"))
    rows.append(("Reasoning", c.reasoning))
    body = "<br>".join(f"<b>{label}:</b> {value}" for label, value in rows)
    return f"<b>AI classification</b><br><br>{body}"


def plan_actions(c: Classification) -> ActionPlan:
    """Turn a Classification into a concrete Zoho ActionPlan."""
    comment = _audit_comment(c)

    if c.disposition == Disposition.support:
        updates = {"category": "Support"}
        if c.sub_type:
            updates["classification"] = _ZOHO_CLASSIFICATION[c.sub_type]
        role = None
        if c.priority:
            updates["priority"] = c.priority.value
            # urgent (P1/P2) -> a dedicated owner; routine (P3/P4) -> the shared queue
            role = "support_high" if c.priority in (Priority.P1, Priority.P2) else "support_low"
        # only incidents (bugs) go to the engineering backlog; service requests and
        # questions are support work, not code work.
        is_bug = c.sub_type == SubType.incident
        return ActionPlan(field_updates=updates,
                          tags=["ai-classified", "ai-support"], comment=comment,
                          assignee_role=role,
                          github_issue=is_bug,
                          github_labels=["bug", "unreviewed"] if is_bug else [])

    if c.disposition == Disposition.redirect:
        return ActionPlan(
            field_updates={"category": "Redirect"},
            tags=["ai-classified", "redirect"],
            comment=comment,
            redirect_to=c.redirect_to,
        )

    if c.disposition == Disposition.review:
        return ActionPlan(
            field_updates={"category": "Needs Review"},
            tags=["ai-classified", "needs-review"],
            comment=comment,
            needs_review=True,
        )

    # --- enhancement ---------------------------------------------------------
    # Feature requests do NOT enter the support queue and get NO SLA (no priority).
    # They are flagged for product review and surfaced in the "Enhancements" view.
    # Phase 2 (once the reviewer's agent account is active) adds auto-assign to the
    # reviewer and an auto-acknowledgement reply to the customer.
    if c.disposition == Disposition.enhancement:
        return ActionPlan(
            field_updates={"category": "Enhancement"},
            tags=["ai-classified", "needs-product-review"],
            comment=comment,
            assignee_role="reviewer",
            github_issue=True,
            github_labels=["enhancement", "unreviewed"],
        )

    # unreachable, but stay safe: anything unexpected goes to a human
    return ActionPlan(field_updates={"category": "Needs Review"},
                      tags=["ai-classified", "needs-review"],
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
        print(f"\n[{c.disposition.value}] -> fields={p.field_updates} tags={p.tags} "
              f"redirect={p.redirect_to} review={p.needs_review} pending={p.pending_decision}")
        print("  comment:")
        for line in p.comment.splitlines():
            print(f"    {line}")
