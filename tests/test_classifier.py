"""Unit tests for the classifier's deterministic safety logic — no network.

These cover the structural guarantees behind the core rules: nothing risky is
auto-routed, redirects always have a target, and malformed output fails safe.
"""

import json

from classifier import (Classification, DEFAULT_REDIRECT, Disposition, Priority,
                        SubType, _apply_guarantees, _parse)


def test_low_confidence_downgraded_to_review():
    c = Classification(disposition=Disposition.support, sub_type=SubType.incident,
                       priority=Priority.P1, confidence=0.4, reasoning="x")
    out = _apply_guarantees(c)
    assert out.disposition == Disposition.review


def test_high_confidence_support_is_kept():
    c = Classification(disposition=Disposition.support, sub_type=SubType.incident,
                       priority=Priority.P1, confidence=0.95, reasoning="x")
    out = _apply_guarantees(c)
    assert out.disposition == Disposition.support
    assert out.sub_type == SubType.incident
    assert out.priority == Priority.P1


def test_redirect_without_target_gets_default():
    c = Classification(disposition=Disposition.redirect, confidence=0.9, reasoning="x")
    out = _apply_guarantees(c)
    assert out.redirect_to == DEFAULT_REDIRECT


def test_non_support_strips_subtype_and_priority():
    c = Classification(disposition=Disposition.redirect, sub_type=SubType.incident,
                       priority=Priority.P1, redirect_to="a@b.c", confidence=0.9, reasoning="x")
    out = _apply_guarantees(c)
    assert out.sub_type is None
    assert out.priority is None


def test_parse_invalid_json_falls_back_to_review():
    out = _parse("this is not json")
    assert out.disposition == Disposition.review
    assert out.confidence == 0.0


def test_parse_valid_json():
    raw = json.dumps({"disposition": "support", "sub_type": "incident", "priority": "P1",
                      "redirect_to": None, "confidence": 0.9, "reasoning": "x"})
    out = _parse(raw)
    assert out.disposition == Disposition.support
    assert out.priority == Priority.P1


def test_parse_normalizes_empty_strings_to_none():
    raw = json.dumps({"disposition": "review", "sub_type": "", "priority": "",
                      "redirect_to": "", "confidence": 0.2, "reasoning": "x"})
    out = _parse(raw)
    assert out.sub_type is None
    assert out.priority is None
    assert out.redirect_to is None
