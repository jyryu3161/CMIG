"""R5 — 구조화 Diagnostic (code·message·detail). Design Ref(foundations): §9.

Plan SC: SC-F8. 자유 문자열 진단(`RuntimeError: infeasible`)을 기계 판독 가능한
`{code, message, detail}` JSON 으로 통일 → GUI 필터·batch summary·실패 원인 통계 기반.
canonical JSON(sorted·allow_nan=False) — 비유한 float 직렬화 비결정성 차단(I-6 일관).
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from typing import Any


class DiagnosticCode(enum.Enum):
    """진단 코드 폐쇄 enum (§9). value = 직렬화/필터 키."""

    INFEASIBLE = "infeasible"                 # solve infeasible (§4.4)
    SOLVER_ERROR = "solver_error"             # solver 예외/실패
    CAPABILITY_MISSING = "capability_missing"  # solver/cobra capability 부재 (§2)
    GATE_BLOCKED = "gate_blocked"             # namespace hard gate 차단 (§4.8)
    MEDIUM_UNAPPLIED = "medium_unapplied"     # medium exchange 가 community 에 없음
    MEMBERS_MISSING = "members_missing"       # MICOM summary 멤버 누락 (I-1)


@dataclass(frozen=True)
class Diagnostic:
    """구조화 진단. to_json() 은 결정적 canonical 문자열(string 컬럼에 저장)."""

    code: DiagnosticCode
    message: str
    detail: dict[str, Any] | None = None

    def to_json(self) -> str:
        return json.dumps(
            {"code": self.code.value, "message": self.message, "detail": self.detail},
            sort_keys=True, ensure_ascii=True, allow_nan=False,
        )

    @classmethod
    def from_exception(cls, exc: BaseException) -> Diagnostic:
        """예외 → Diagnostic. 'infeasible' 메시지는 INFEASIBLE, 그 외 SOLVER_ERROR."""
        msg = f"{type(exc).__name__}: {exc}"
        code = (
            DiagnosticCode.INFEASIBLE
            if "infeasible" in str(exc).lower()
            else DiagnosticCode.SOLVER_ERROR
        )
        return cls(code=code, message=msg, detail={"exc_type": type(exc).__name__})


# F4: 다중 원인 → primary code 우선순위(앞일수록 우선). 미등재 code 는 후순위.
_PRIORITY: tuple[DiagnosticCode, ...] = (
    DiagnosticCode.INFEASIBLE,
    DiagnosticCode.SOLVER_ERROR,
    DiagnosticCode.CAPABILITY_MISSING,
    DiagnosticCode.GATE_BLOCKED,
    DiagnosticCode.MEDIUM_UNAPPLIED,
    DiagnosticCode.MEMBERS_MISSING,
)


def diagnostic_from_parts(parts: list[tuple[DiagnosticCode, str]]) -> str | None:
    """여러 (code, message) → primary(우선순위 최상) code + detail.causes 의 canonical JSON.

    F4: engine/delta/sandbox 의 자유 문자열 다중 진단을 구조화 단일 진입점으로 통일.
    빈 리스트 → None.
    """
    if not parts:
        return None

    def _rank(c: DiagnosticCode) -> int:
        return _PRIORITY.index(c) if c in _PRIORITY else len(_PRIORITY)

    primary = min(parts, key=lambda p: _rank(p[0]))[0]
    return Diagnostic(
        code=primary,
        message="; ".join(m for _, m in parts),
        detail={"causes": [{"code": c.value, "message": m} for c, m in parts]},
    ).to_json()


def parse_diagnostic(raw: str | None) -> dict[str, Any] | None:
    """저장된 diagnostic 문자열 → dict (구조화면 파싱, 자유문자열이면 message wrap)."""
    if raw is None:
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "code" in obj:
            return obj
    except (json.JSONDecodeError, ValueError):
        pass
    return {"code": None, "message": raw, "detail": None}
