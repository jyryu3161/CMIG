"""R5 — 구조화 Diagnostic. Plan SC: SC-F8. (Qt/engine 비의존 순수 테스트)"""

import json
import math

import pytest

from cmig.core.diagnostics import Diagnostic, DiagnosticCode, parse_diagnostic


def test_to_json_is_structured_and_sorted():
    d = Diagnostic(DiagnosticCode.INFEASIBLE, "growth NaN", detail={"x": 1})
    obj = json.loads(d.to_json())
    assert obj == {"code": "infeasible", "message": "growth NaN", "detail": {"x": 1}}
    # sorted keys (결정적)
    assert d.to_json() == json.dumps(obj, sort_keys=True, ensure_ascii=True)


def test_to_json_rejects_non_finite():
    """allow_nan=False — 비유한 detail 은 직렬화 거부(I-6 일관)."""
    d = Diagnostic(DiagnosticCode.SOLVER_ERROR, "bad", detail={"v": math.nan})
    with pytest.raises(ValueError):
        d.to_json()


def test_from_exception_maps_infeasible():
    d = Diagnostic.from_exception(RuntimeError("model is infeasible"))
    assert d.code is DiagnosticCode.INFEASIBLE
    assert "infeasible" in d.to_json()


def test_from_exception_defaults_solver_error():
    d = Diagnostic.from_exception(ValueError("weird"))
    assert d.code is DiagnosticCode.SOLVER_ERROR
    assert d.detail == {"exc_type": "ValueError"}


def test_parse_diagnostic_roundtrip_and_legacy():
    structured = Diagnostic(DiagnosticCode.GATE_BLOCKED, "blocked").to_json()
    assert parse_diagnostic(structured)["code"] == "gate_blocked"
    # legacy 자유 문자열 → message wrap (code=None)
    legacy = parse_diagnostic("RuntimeError: infeasible")
    assert legacy["code"] is None and "infeasible" in legacy["message"]
    assert parse_diagnostic(None) is None


def test_all_codes_present():
    assert {c.value for c in DiagnosticCode} == {
        "infeasible", "solver_error", "capability_missing",
        "gate_blocked", "medium_unapplied", "members_missing",
    }
