"""Unit tests for mapping.plan_actions — pure logic, no network."""

from classifier import Classification, Disposition, Priority, SubType
from mapping import plan_actions


def _support(sub_type, priority):
    return Classification(disposition=Disposition.support, sub_type=sub_type,
                          priority=priority, confidence=0.95, reasoning="x")


def test_support_incident_p1():
    p = plan_actions(_support(SubType.incident, Priority.P1))
    assert p.field_updates == {"category": "Support", "classification": "Problem", "priority": "P1"}
    assert p.tags == ["ai-classified", "ai-support"]
    assert p.needs_review is False
    assert p.pending_decision is False
    assert p.comment  # always leaves an audit note


def test_support_service_request_is_others_p4():
    p = plan_actions(_support(SubType.service_request, Priority.P4))
    assert p.field_updates["classification"] == "Others"
    assert p.field_updates["priority"] == "P4"


def test_support_question_is_question():
    p = plan_actions(_support(SubType.question, Priority.P4))
    assert p.field_updates["classification"] == "Question"


def test_priority_is_exact_p_level_not_high_low():
    # regression: P1 and P2 must stay distinct (not collapsed to "High")
    assert plan_actions(_support(SubType.incident, Priority.P1)).field_updates["priority"] == "P1"
    assert plan_actions(_support(SubType.incident, Priority.P2)).field_updates["priority"] == "P2"


def test_support_routing_by_priority():
    # urgent (P1/P2) -> support_high; routine (P3/P4) -> support_low
    assert plan_actions(_support(SubType.incident, Priority.P1)).assignee_role == "support_high"
    assert plan_actions(_support(SubType.incident, Priority.P2)).assignee_role == "support_high"
    assert plan_actions(_support(SubType.question, Priority.P3)).assignee_role == "support_low"
    assert plan_actions(_support(SubType.question, Priority.P4)).assignee_role == "support_low"


def test_redirect():
    c = Classification(disposition=Disposition.redirect, redirect_to="hello@zenalyst.ai",
                       confidence=0.9, reasoning="x")
    p = plan_actions(c)
    assert p.field_updates == {"category": "Redirect"}
    assert "redirect" in p.tags
    assert p.redirect_to == "hello@zenalyst.ai"
    assert p.needs_review is False


def test_review():
    c = Classification(disposition=Disposition.review, confidence=0.3, reasoning="x")
    p = plan_actions(c)
    assert p.field_updates == {"category": "Needs Review"}
    assert "needs-review" in p.tags
    assert p.needs_review is True


def test_enhancement_flagged_for_product_review():
    # enhancements go to product review, NOT the support queue, and get no SLA
    c = Classification(disposition=Disposition.enhancement, confidence=0.95, reasoning="x")
    p = plan_actions(c)
    assert p.field_updates == {"category": "Enhancement"}
    assert "needs-product-review" in p.tags
    assert "priority" not in p.field_updates  # no support SLA
    assert p.assignee_role == "reviewer"      # handed to the product reviewer
    assert p.comment


def test_redirect_and_review_have_no_assignee():
    for disp in (Disposition.redirect, Disposition.review):
        c = Classification(disposition=disp, confidence=0.9, reasoning="x")
        assert plan_actions(c).assignee_role is None
