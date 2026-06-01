"""Namespace hard gate — exchange 대사체 정합 + 차단 게이트.

Design Ref: §4.8·§6 / glossary §1.B / schema §7 [GATE-BLOCK].
Plan SC: SC-3 (namespace gate 차단 동작).

규칙:
  unresolved + high-confidence  → solve 차단(block)·해소 요구
  low-confidence                → 경고(warn) 후 진행·**자동병합 금지**·audit
  resolved                      → 통과
gate 통과는 MICOM solve·run_hash 산출의 선행조건(precondition)이다.
namespace mapping decisions 는 run_hash 11구성요소 #10 (schema §4.2).
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class Confidence(enum.Enum):
    HIGH = "high"
    LOW = "low"


class DecisionStatus(enum.Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    WARNED = "warned"   # low-confidence, 경고 후 진행 (자동병합 아님)


@dataclass(frozen=True)
class NamespaceDecision:
    """exchange 대사체 매핑 결정 레코드 (audit trail 단위). schema §7.1."""

    metabolite: str
    source_id: str
    target_id: str | None       # unresolved 이면 None (OD-37)
    confidence: Confidence
    status: DecisionStatus
    rationale: str = ""
    audit_ts: str | None = None  # UTC ISO-8601 ms (OD-38) — gate 평가 시점엔 None 가능


class GateBlockedError(RuntimeError):
    """unresolved high-confidence mapping 존재 → solve 차단 (§4.8)."""

    def __init__(self, unresolved_high: list[NamespaceDecision]):
        self.unresolved_high = unresolved_high
        names = ", ".join(sorted(d.metabolite for d in unresolved_high))
        super().__init__(
            f"namespace gate blocked: unresolved high-confidence exchange mapping "
            f"[{names}] — 해소(resolution) 필요 (§4.8). community solve 차단됨."
        )


@dataclass(frozen=True)
class NamespaceGateResult:
    """gate 평가 산출 (in-memory). schema §7.2.

    blocked=True 이면 어떤 MICOM solve 도 호출되지 않는다 ([GATE-BLOCK]).
    """

    blocked: bool
    coverage_pct: float
    unresolved_high: list[NamespaceDecision] = field(default_factory=list)
    warned_low: list[NamespaceDecision] = field(default_factory=list)
    decisions: list[NamespaceDecision] = field(default_factory=list)

    def raise_if_blocked(self) -> None:
        if self.blocked:
            raise GateBlockedError(self.unresolved_high)


def evaluate_gate(decisions: list[NamespaceDecision]) -> NamespaceGateResult:
    """namespace 결정 목록 → gate 결과.

    - blocked := ∃ (confidence=HIGH ∧ status=UNRESOLVED)
    - warned_low := low-confidence 이며 진행(자동병합 금지)
    - coverage_pct := resolved / total × 100  (OD-40: 분모=평가된 exchange 매핑 수)
    """
    unresolved_high = [
        d for d in decisions
        if d.confidence is Confidence.HIGH and d.status is DecisionStatus.UNRESOLVED
    ]
    warned_low = [d for d in decisions if d.confidence is Confidence.LOW]
    resolved = sum(1 for d in decisions if d.status is DecisionStatus.RESOLVED)
    total = len(decisions)
    coverage = 100.0 if total == 0 else (resolved / total) * 100.0
    return NamespaceGateResult(
        blocked=len(unresolved_high) > 0,
        coverage_pct=coverage,
        unresolved_high=unresolved_high,
        warned_low=warned_low,
        decisions=list(decisions),
    )


def namespace_decision_key(decision: NamespaceDecision) -> str:
    """run_hash 용 결정적 namespace decision 키.

    audit timestamp 는 재현 입력이 아니라 감사 메타데이터라 제외한다. 같은 수동 매핑 결정은
    실행 시점과 무관하게 같은 run_hash 구성요소가 되어야 한다.
    """
    payload = {
        "metabolite": decision.metabolite,
        "source_id": decision.source_id,
        "target_id": decision.target_id,
        "confidence": decision.confidence.value,
        "status": decision.status.value,
        "rationale": decision.rationale,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def namespace_decision_keys(decisions: list[NamespaceDecision]) -> list[str]:
    """run_hash 구성요소 #10 용 결정적 decision key 목록."""
    return sorted(namespace_decision_key(d) for d in decisions)


def _decision_from_obj(obj: dict[str, Any]) -> NamespaceDecision:
    try:
        return NamespaceDecision(
            metabolite=str(obj["metabolite"]),
            source_id=str(obj["source_id"]),
            target_id=None if obj.get("target_id") is None else str(obj["target_id"]),
            confidence=Confidence(str(obj["confidence"])),
            status=DecisionStatus(str(obj["status"])),
            rationale=str(obj.get("rationale", "")),
            audit_ts=None if obj.get("audit_ts") is None else str(obj["audit_ts"]),
        )
    except KeyError as e:
        raise ValueError(f"namespace decision 필수 필드 누락: {e.args[0]}") from e
    except ValueError as e:
        raise ValueError(f"namespace decision 값 오류: {obj}") from e


def load_namespace_decisions(path: str | Path) -> list[NamespaceDecision]:
    """JSON namespace decision 파일 로드.

    형식은 `[{metabolite, source_id, target_id, confidence, status, rationale?}]`.
    confidence={high,low}, status={resolved,unresolved,warned}.
    """
    p = Path(path)
    raw = json.loads(p.read_text())
    if not isinstance(raw, list):
        raise ValueError("namespace decision JSON 은 list 여야 함")
    out = []
    for obj in raw:
        if not isinstance(obj, dict):
            raise ValueError("namespace decision 항목은 object 여야 함")
        out.append(_decision_from_obj(obj))
    return out
