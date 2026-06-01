"""SolverBackend seam — solver **capability 보고 + selection**.

Design Ref: §4.2 (seam) / schema §5 [SOLVER-SPLIT] / Plan §7.2 (Gurobi 기본).
Plan SC: SC-1 (solver별 golden), SC-6 (OSQP→LP 재계산).

이 seam 의 책임은 **(1) solver capability 보고**(LP/QP/MILP·가용성)와 **(2) solver 선택**이다.
실제 community solve·pFBA·OSQP(QP)→LP 재계산은 **MICOM(optlang)이 내부 수행**하며,
CMIG 는 `engine.SOLVER_MAP` 으로 cmig solver 이름을 MICOM optlang solver 로 매핑한다
(solve 는 MICOM 이 수행; CMIG 는 capability 보고·선택만, §4.2).
즉 이 seam 은 solve_* 를 직접 호출하지 않는다 — solver 교체(golden 변형·OSQP→LP swap)는
optlang solver 이름 선택으로 실현된다(Check G-1 동기화).

capability 부재 시 해당 분석만 비활성화([disable_analysis_on_missing], §2·schema §5.3) —
앱 전체 강등이 아니다. GLPK 는 미번들(GPL) → 전 role 제외.
역할별 enum(§4.2 노트): growth_solver∋osqp, flux_solver∌osqp, 모두 ∌glpk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, cast, runtime_checkable

ProblemClass = Literal["LP", "QP", "MILP"]
SolverName = Literal["gurobi", "highs", "osqp", "cplex"]  # glpk=GPL 미번들 제외


@dataclass(frozen=True)
class SolverCapability:
    """solver 의 problem class 지원 (schema §5.1)."""

    name: str
    lp: bool
    qp: bool
    milp: bool
    available: bool          # 라이브러리 import/라이선스 가용
    experimental: frozenset[ProblemClass] = frozenset()

    def supports(self, problem: ProblemClass) -> bool:
        return self.available and {"LP": self.lp, "QP": self.qp, "MILP": self.milp}[problem]


@runtime_checkable
class SolverBackend(Protocol):
    """solver capability/selection seam (외부 의존). solve 는 MICOM optlang 이 수행."""

    name: SolverName

    def capability(self) -> SolverCapability: ...


def _importable(module: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(module) is not None


class GurobiBackend:
    """Gurobi (기본 solver, Plan §7.2). LP·QP·MILP 전부 지원 (§2). gurobipy lazy probe."""

    name: SolverName = "gurobi"

    def capability(self) -> SolverCapability:
        return SolverCapability(
            name="gurobi", lp=True, qp=True, milp=True, available=_importable("gurobipy")
        )


class HighsBackend:
    """HiGHS — LP/MILP (MIT). QP=experimental (§2·A6)."""

    name: SolverName = "highs"

    def capability(self) -> SolverCapability:
        return SolverCapability(
            name="highs", lp=True, qp=False, milp=True,
            available=_importable("highspy"), experimental=frozenset({"QP"}),
        )


class OsqpBackend:
    """OSQP — QP 전용 (Apache). flux 는 LP solver 로 재계산해야 함 (SC-6·§4.2).

    LP 미지원(`lp=False`)은 capability 로 표현 — solve 는 MICOM 이 OSQP-QP 후
    HiGHS-LP 로 flux 를 재계산한다(engine SOLVER_MAP).
    """

    name: SolverName = "osqp"

    def capability(self) -> SolverCapability:
        return SolverCapability(
            name="osqp", lp=False, qp=True, milp=False, available=_importable("osqp")
        )


_REGISTRY: dict[str, type] = {
    "gurobi": GurobiBackend,
    "highs": HighsBackend,
    "osqp": OsqpBackend,
}


def get_backend(name: SolverName) -> SolverBackend:
    if name not in _REGISTRY:
        raise ValueError(f"미지원 solver: {name} (지원: {sorted(_REGISTRY)})")
    return cast(SolverBackend, _REGISTRY[name]())


def capability_matrix() -> dict[str, SolverCapability]:
    """현재 환경의 solver capability 매트릭스 (§5.1)."""
    return {name: get_backend(cast("SolverName", name)).capability() for name in _REGISTRY}
