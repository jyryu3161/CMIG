"""F4 — engine/delta/sandbox diagnostic 전면 구조화. Plan SC: SC-C1.

자유 문자열 diagnostic 이 {code,message,detail} JSON 으로 통일됐는지(파싱 가능) + 다중 원인
primary code 우선순위 + 기존 substring 호환을 검증한다.
"""

from __future__ import annotations

import json
import math

from cmig.core.delta import compute_delta
from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts, parse_diagnostic
from cmig.core.engine import SolveResult
from cmig.core.sandbox import SandboxState, evaluate_sandbox


def _sr(obj, status="optimal", members=("A", "B"), ext=None):
    return SolveResult(
        objective=obj, member_growth={m: 0.1 for m in members},
        abundances={m: 0.5 for m in members},
        external_exchange=ext or {"ac": 1.0}, member_exchange={m: {} for m in members},
        status=status, flux_report_status="full",
        growth_solver="gurobi", flux_solver="gurobi", members=list(members),
    )


def test_from_parts_primary_priority():
    """다중 원인 → INFEASIBLE 이 MEMBERS_MISSING 보다 primary."""
    js = diagnostic_from_parts([
        (DiagnosticCode.MEMBERS_MISSING, "missing X"),
        (DiagnosticCode.INFEASIBLE, "growth NaN"),
    ])
    obj = json.loads(js)
    assert obj["code"] == "infeasible"                      # 우선순위 최상
    assert len(obj["detail"]["causes"]) == 2                # 모든 원인 보존
    assert diagnostic_from_parts([]) is None


def test_delta_diagnostic_is_structured_json():
    """F4: delta 실패 diagnostic 이 구조화 JSON (parse 가능)."""
    d = compute_delta(_sr(0.5), _sr(math.nan, status="infeasible"))
    assert d.status == "failed"
    parsed = parse_diagnostic(d.diagnostic)
    assert parsed["code"] == "infeasible"                   # 구조화
    assert "infeasible" in d.diagnostic                     # 기존 substring 호환


def test_sandbox_diagnostic_is_structured_json():
    """F4: sandbox 실패 diagnostic 구조화 JSON."""
    r = evaluate_sandbox(
        _sr(0.5), _sr(math.nan, status="infeasible"), state=SandboxState.PREVIEW
    )
    assert r.status == "failed"
    assert parse_diagnostic(r.diagnostic)["code"] == "infeasible"


def test_ok_solve_has_no_diagnostic():
    """정상 입력 → diagnostic None (거짓 진단 없음)."""
    d = compute_delta(_sr(0.5), _sr(0.6))
    assert d.status == "ok" and d.diagnostic is None
