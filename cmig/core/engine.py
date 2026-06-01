"""EngineWrapper seam — MICOM 위임 단일 진입점 (2b 실제 통합).

Design Ref: §4.1·§4.2 / schema §8.6 [MICOM-PIN] / glossary §1.D.
Plan SC: SC-5 (MICOM-version golden regression), SC-6 (OSQP→LP), SC-7 (튜토리얼 재현).

MICOM 호출은 이 wrapper 한 곳만 경유 (public API + documented flux:
`cooperative_tradeoff(fraction=..., fluxes=True, pfba=True)`). internal API 금지.
이 단일 격리점 덕에 micom_version pin 변경이 한 곳에 국한된다 (SC-5).

CMIG solver 이름 → MICOM(optlang) solver 매핑 (F1: hybrid 폐기, gurobi-only full):
  gurobi  → gurobi   (QP+LP 모두 Gurobi → flux_report_status=full, canonical full-flux)
  osqp    → osqp     (QP only; LP flux 부재 → qp_only_approximate, flux_solver=None, 무라이선스)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts

# 직렬화 canonical 값 (OD-19). UI 표시 라벨 = "QP-only approximate".
FluxReportStatus = Literal["full", "qp_only_approximate"]
FLUX_REPORT_LABEL = {"full": "Full (LP pFBA)", "qp_only_approximate": "QP-only approximate"}

# CMIG solver 이름 → MICOM optlang solver (schema §5.2 / golden 변형 §16).
# F1: golden 변형 2종 = gurobi / osqp. (osqp_growth_highs_flux=hybrid 폐기 — HiGHS 제거,
# 실 LP full-flux 는 gurobi 전용. osqp 는 qp_only_approximate 무라이선스 정직 경로.)
SOLVER_MAP: dict[str, str] = {
    "gurobi": "gurobi",
    "osqp": "osqp",
}
# F1: 허용 cmig solver — gurobi(full) / osqp(qp_only_approximate). 그 외(예: highs)는 거부
# (CLI choices 뿐 아니라 라이브러리 레벨에서도 강제 — 'full=gurobi 전용' 불변).
ALLOWED_CMIG_SOLVERS = frozenset(SOLVER_MAP)


def _require_allowed_solver(cmig_solver: str) -> None:
    if cmig_solver not in ALLOWED_CMIG_SOLVERS:
        raise ValueError(
            f"미지원 cmig solver: {cmig_solver!r} (허용: {sorted(ALLOWED_CMIG_SOLVERS)}). "
            f"full-flux 는 gurobi 전용·osqp 는 qp_only_approximate. [F1]"
        )


class EngineUnavailableError(RuntimeError):
    """엔진(MICOM) 미설치/미가용 — capability 강등 (§4.4·schema §5.3)."""


@dataclass(frozen=True)
class SolveResult:
    """community solve 산출 (engine 경계, pandas 비의존 — dict 로 노출).

    부호는 raw (MICOM): + = pool/환경으로 분비, − = 흡수 (§4.3 일치).
    """

    objective: float                                   # community growth rate
    member_growth: dict[str, float | None]          # member_id → μ (None=summary 누락)
    abundances: dict[str, float | None]              # member_id → abundance (None=누락)
    external_exchange: dict[str, float]                 # metabolite → raw net (medium pool)
    member_exchange: dict[str, dict[str, float]]        # member_id → {metabolite: raw}
    status: Literal["optimal", "infeasible", "unbounded"]
    flux_report_status: FluxReportStatus
    growth_solver: str                                  # QP
    flux_solver: str | None                             # LP (None → qp_only_approximate)
    diagnostic: str | None = None
    members: list[str] = field(default_factory=list)


@runtime_checkable
class EngineWrapper(Protocol):
    """community FBA 엔진 추상 (외부 의존 seam). MICOM public API only."""

    micom_version: str

    def cooperative_tradeoff(
        self, community: object, tradeoff_f: float, *, cmig_solver: str = "gurobi"
    ) -> SolveResult: ...


def _met_from_exchange(rxn_id: str, suffix: str) -> str:
    """'EX_ac_m'/'EX_ac_e' → 'ac' (EX_ prefix + suffix 제거)."""
    name = rxn_id[3:] if rxn_id.startswith("EX_") else rxn_id
    if name.endswith(suffix):
        name = name[: -len(suffix)]
    return name


class MicomEngine:
    """MICOM wrapper (정확 pin·public API only). OD-51: micom==0.39.0 (pyproject)."""

    def __init__(self) -> None:
        self._micom: Any = None

    def _load(self) -> Any:
        if self._micom is None:
            try:
                import micom
            except ImportError as e:  # pragma: no cover - 2a 환경
                raise EngineUnavailableError(
                    "micom 미설치 — `uv sync --extra engine` (OD-51 micom==0.39.0)."
                ) from e
            self._micom = micom
        return self._micom

    @property
    def micom_version(self) -> str:
        return str(getattr(self._load(), "__version__", "unknown"))

    def build_community(self, taxonomy: object, cmig_solver: str = "gurobi") -> object:
        """taxonomy(DataFrame) → micom Community. solver 매핑 적용 (F1: gurobi/osqp 만)."""
        _require_allowed_solver(cmig_solver)        # 라이브러리 레벨 강제(임의 solver 우회 차단)
        micom = self._load()
        return micom.Community(taxonomy, solver=SOLVER_MAP[cmig_solver], progress=False)

    def cooperative_tradeoff(
        self, community: object, tradeoff_f: float, *, cmig_solver: str = "gurobi"
    ) -> SolveResult:
        """MICOM cooperative_tradeoff(fraction=f, fluxes=True, pfba=True) 위임 + dict 변환.

        eps 0 처리는 하위 sign 계층이 담당; 여기선 raw flux 만 추출한다.
        """
        _require_allowed_solver(cmig_solver)        # F1: gurobi/osqp 만 (라이브러리 강제)
        # tradeoff f 범위 검증 (§4.2 [TRADEOFF-RANGE]: 0 < f ≤ 1) — MICOM 위임 전 fail-fast.
        if not (0.0 < tradeoff_f <= 1.0):
            raise ValueError(f"tradeoff_f 는 0 < f ≤ 1 이어야 함 (받음: {tradeoff_f}) [§4.2]")

        sol = community.cooperative_tradeoff(  # type: ignore[attr-defined]
            fraction=tradeoff_f, fluxes=True, pfba=True
        )
        members_df = sol.members
        fluxes = sol.fluxes
        member_ids = [str(i) for i in fluxes.index if str(i) != "medium"]

        # member growth/abundance — 모든 member_id 에 대해 기록(누락 silent-drop 금지, §4.4).
        has_abundance = "abundance" in members_df.columns
        member_growth = {
            m: (float(members_df.loc[m, "growth_rate"]) if m in members_df.index else None)
            for m in member_ids
        }
        abundances = {
            m: (float(members_df.loc[m, "abundance"])
                if (m in members_df.index and has_abundance) else None)
            for m in member_ids
        }
        missing = [m for m in member_ids if m not in members_df.index]

        # external profile: medium 행, EX_*_m 컬럼 (net 환경 exchange).
        external: dict[str, float] = {}
        if "medium" in fluxes.index:
            for col in fluxes.columns:
                if col.startswith("EX_") and col.endswith("_m"):
                    v = float(fluxes.loc["medium", col])
                    external[_met_from_exchange(col, "_m")] = v

        # per-member exchange: 각 taxon 행, EX_*_e 컬럼 (멤버↔pool).
        member_exchange: dict[str, dict[str, float]] = {}
        for m in member_ids:
            row: dict[str, float] = {}
            for col in fluxes.columns:
                if col.startswith("EX_") and col.endswith("_e"):
                    row[_met_from_exchange(col, "_e")] = float(fluxes.loc[m, col])
            member_exchange[m] = row

        # solver 분리 기록 (§4.2 [SOLVER-SPLIT]): flux(LP) 부재 시 qp_only_approximate.
        flux_solver: str | None
        flux_report: FluxReportStatus
        # F4: 진단을 (DiagnosticCode, message) 로 수집 → diagnostic_from_parts 구조화.
        diag_parts: list[tuple[DiagnosticCode, str]] = []
        if cmig_solver == "osqp":
            # OSQP=QP 전용, LP solver 부재 → flux LP 재계산 불가 (schema §5.2·design §4.2).
            growth_solver, flux_solver, flux_report = "osqp", None, "qp_only_approximate"
        else:
            # gurobi = LP+QP 동일 solver → full (canonical full-flux). gurobi 만 'full' (F1).
            growth_solver = flux_solver = "gurobi"
            flux_report = "full"

        # status — growth 비유한(infeasible) 가드 + 멤버 누락 진단 (§4.4).
        objective = float(sol.growth_rate)
        status: Literal["optimal", "infeasible", "unbounded"] = "optimal"
        if math.isnan(objective):
            status = "infeasible"
            diag_parts.append((DiagnosticCode.INFEASIBLE, "community growth NaN (infeasible)"))
        if missing:
            diag_parts.append(
                (DiagnosticCode.MEMBERS_MISSING, f"MICOM summary 누락 멤버: {sorted(missing)}")
            )
        diagnostic = diagnostic_from_parts(diag_parts)

        return SolveResult(
            objective=objective,
            member_growth=member_growth,
            abundances=abundances,
            external_exchange=external,
            member_exchange=member_exchange,
            status=status,
            flux_report_status=flux_report,
            growth_solver=growth_solver,
            flux_solver=flux_solver,
            diagnostic=diagnostic,
            members=member_ids,
        )
