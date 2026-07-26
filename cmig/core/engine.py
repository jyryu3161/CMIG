"""EngineWrapper seam — MICOM 위임 단일 진입점 (2b 실제 통합).

Design Ref: §4.1·§4.2 / schema §8.6 [MICOM-PIN] / glossary §1.D.
Plan SC: SC-5 (MICOM-version golden regression), SC-6 (OSQP→LP), SC-7 (튜토리얼 재현).

MICOM 호출은 이 wrapper 한 곳만 경유 (public API + documented flux:
`cooperative_tradeoff(fraction=..., fluxes=True, pfba=True)`). internal API 금지.
이 단일 격리점 덕에 micom_version pin 변경이 한 곳에 국한된다 (SC-5).

CMIG solver 이름 → MICOM(optlang) solver 매핑:
  gurobi  → gurobi   (QP+LP 모두 Gurobi → flux_report_status=full, canonical full-flux)
  osqp    → osqp     (OSQP growth 경로, flux_report_status=qp_only_approximate)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts

# 직렬화 canonical 값 (OD-19). UI 표시 라벨 = "QP-only approximate".
# round 5 F5: "full" 의 라벨은 문자 그대로 "Full (LP pFBA)" 다. 그런데 이 값은 solver 이름만으로
# 정해졌기 때문에 (a) pFBA stage 가 실패해 비-parsimonious FBA 로 재시도된 run 과 (b) solve 자체가
# 실패해 flux 가 하나도 없는 run 까지 "pFBA flux 분포"라고 주장했다. 비-parsimonious community FBA
# 벡터는 고도로 축퇴된 최적면 위의 임의의 한 꼭짓점이므로 — 거기서 파생된 모든 member↔pool
# exchange 와 cross-feeding edge 가 임의의 대표값이다 — 이를 pFBA 로 표기하면 run 전체의 방법을
# 잘못 기술하게 된다. 이제 실제로 생산된 flux 를 따라간다.
FluxReportStatus = Literal["full", "fba_non_parsimonious", "qp_only_approximate", "none"]
FLUX_REPORT_LABEL = {
    "full": "Full (LP pFBA)",
    "fba_non_parsimonious": "Full flux, NON-parsimonious (pFBA stage failed)",
    "qp_only_approximate": "QP-only approximate",
    "none": "No flux (solve failed)",
}

# B1: MICOM 은 stage 가 non-optimal 로 끝나도 primal 을 무조건 읽으므로(micom/solution.py) 위임이
# status 대신 예외를 던진다. pFBA stage 만 실패하는 경우가 있어 pfba=False 로 1회 재시도하고,
# 그 사실을 warning 으로 노출한다(조용한 강등 금지).
PFBA_FALLBACK_WARNING = "pfba_stage_failed; reporting non-parsimonious flux distribution"

# CMIG solver 이름 → MICOM optlang solver (schema §5.2 / golden 변형 §16).
# 루트 명세 기준: baseline에서 OSQP는 QP-only approximate 로 보고한다.
SOLVER_MAP: dict[str, str] = {
    "gurobi": "gurobi",
    "osqp": "osqp",
}
# F1: 허용 cmig solver — gurobi(full) / osqp(qp_only_approximate).
# (CLI choices 뿐 아니라 라이브러리 레벨에서도 강제).
ALLOWED_CMIG_SOLVERS = frozenset(SOLVER_MAP)


def _require_allowed_solver(cmig_solver: str) -> None:
    if cmig_solver not in ALLOWED_CMIG_SOLVERS:
        raise ValueError(
            f"미지원 cmig solver: {cmig_solver!r} (허용: {sorted(ALLOWED_CMIG_SOLVERS)}). "
            f"지원 solver 는 gurobi 또는 osqp입니다. [F1]"
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
    status: Literal["optimal", "infeasible", "unbounded", "solver_failed"]
    flux_report_status: FluxReportStatus
    growth_solver: str                                  # QP
    flux_solver: str | None                             # LP (None → qp_only_approximate)
    diagnostic: str | None = None
    members: list[str] = field(default_factory=list)
    # B1: 조용한 강등 금지 — pFBA fallback 등 결과 해석을 바꾸는 사건은 여기에 노출된다.
    warnings: list[str] = field(default_factory=list)
    # manifest 가 실제 flux 정규화를 사실대로 기록하도록 solve 결과가 스스로 들고 다닌다.
    flux_normalization_method: str = "pfba"


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


def _solver_split(cmig_solver: str) -> tuple[str, str | None, FluxReportStatus]:
    """(growth_solver, flux_solver, flux_report_status) — §4.2 [SOLVER-SPLIT] 단일 정의."""
    if cmig_solver == "osqp":
        return "osqp", None, "qp_only_approximate"
    # gurobi = LP+QP 동일 solver → full (canonical full-flux). gurobi 만 'full' (F1).
    return "gurobi", "gurobi", "full"


def solver_failed_result(
    cmig_solver: str,
    causes: list[tuple[DiagnosticCode, str]],
    *,
    warnings: list[str] | None = None,
) -> SolveResult:
    """예외로 끝난 solve → 구조화 실패 SolveResult (B1: raw traceback 유출 금지).

    호출자가 이미 가진 `status != "optimal"` 분기를 그대로 태울 수 있게 빈 flux dict 를 돌려준다.
    """
    growth_solver, flux_solver, _report = _solver_split(cmig_solver)
    # No flux vector was produced at all, so no flux-report tier can honestly be claimed.
    flux_report: FluxReportStatus = "none"
    return SolveResult(
        objective=0.0,
        member_growth={},
        abundances={},
        external_exchange={},
        member_exchange={},
        status="solver_failed",
        flux_report_status=flux_report,
        growth_solver=growth_solver,
        flux_solver=flux_solver,
        diagnostic=diagnostic_from_parts(causes),
        members=[],
        warnings=list(warnings or []),
        flux_normalization_method="none",
    )


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

    @staticmethod
    def _delegate_cooperative_tradeoff(
        community: Any, tradeoff_f: float
    ) -> tuple[Any | None, str, list[str], list[tuple[DiagnosticCode, str]]]:
        """MICOM 위임 (pFBA → 실패 시 non-pFBA 1회 재시도). 예외를 밖으로 흘리지 않는다.

        MICOM 은 `CommunitySolution` 생성 시 solver status 확인 없이 primal 을 읽으므로, stage 가
        non-optimal 로 끝나면 status 대신 solver 예외가 올라온다(관측: gurobipy GurobiError
        "Unable to retrieve attribute 'X'" — pFBA stage). pFBA stage 만 실패하는 community 가
        실제로 존재하므로 pfba=False 로 한 번 재시도하고, 성공 시 비-절약 flux 라는 사실을
        warning + diagnostic 양쪽에 남긴다.

        Returns ``(solution|None, flux_normalization_method, warnings, causes)``.
        """
        causes: list[tuple[DiagnosticCode, str]] = []
        try:
            return (
                community.cooperative_tradeoff(fraction=tradeoff_f, fluxes=True, pfba=True),
                "pfba",
                [],
                causes,
            )
        except Exception as pfba_error:  # noqa: BLE001 - solver 백엔드 예외는 타입이 열려 있다
            causes.append((
                DiagnosticCode.SOLVER_ERROR,
                f"pFBA flux stage failed: {type(pfba_error).__name__}: {pfba_error}",
            ))
        try:
            sol = community.cooperative_tradeoff(fraction=tradeoff_f, fluxes=True, pfba=False)
        except Exception as retry_error:  # noqa: BLE001 - 위와 동일
            causes.append((
                DiagnosticCode.SOLVER_ERROR,
                f"non-parsimonious retry failed: {type(retry_error).__name__}: {retry_error}",
            ))
            return None, "none", [], causes
        return sol, "fba", [PFBA_FALLBACK_WARNING], causes

    def cooperative_tradeoff(
        self, community: object, tradeoff_f: float, *, cmig_solver: str = "gurobi"
    ) -> SolveResult:
        """MICOM cooperative_tradeoff(fraction=f, fluxes=True, pfba=True) 위임 + dict 변환.

        eps 0 처리는 하위 sign 계층이 담당; 여기선 raw flux 만 추출한다. 위임이 예외로 끝나면
        (B1) status="solver_failed" SolveResult 로 구조화한다 — 호출자는 이미 status 를 분기한다.
        """
        _require_allowed_solver(cmig_solver)        # F1: gurobi/osqp 만 (라이브러리 강제)
        # tradeoff f 범위 검증 (§4.2 [TRADEOFF-RANGE]: 0 < f ≤ 1) — MICOM 위임 전 fail-fast.
        if not (0.0 < tradeoff_f <= 1.0):
            raise ValueError(f"tradeoff_f 는 0 < f ≤ 1 이어야 함 (받음: {tradeoff_f}) [§4.2]")

        sol, flux_normalization, solve_warnings, solve_causes = (
            self._delegate_cooperative_tradeoff(community, tradeoff_f)
        )
        if sol is None:
            return solver_failed_result(cmig_solver, solve_causes, warnings=solve_warnings)
        try:
            return self._solve_result_from_solution(
                sol,
                cmig_solver=cmig_solver,
                flux_normalization=flux_normalization,
                solve_warnings=solve_warnings,
                solve_causes=solve_causes,
            )
        except Exception as convert_error:  # noqa: BLE001 - 부분 해 판독 실패도 구조화한다
            solve_causes.append((
                DiagnosticCode.SOLVER_ERROR,
                f"solution readout failed: {type(convert_error).__name__}: {convert_error}",
            ))
            return solver_failed_result(cmig_solver, solve_causes, warnings=solve_warnings)

    def _solve_result_from_solution(
        self,
        sol: Any,
        *,
        cmig_solver: str,
        flux_normalization: str = "pfba",
        solve_warnings: list[str] | None = None,
        solve_causes: list[tuple[DiagnosticCode, str]] | None = None,
    ) -> SolveResult:
        """MICOM CommunitySolution → SolveResult (순수 판독; solver 호출 없음)."""
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

        # solver 분리 기록 (§4.2 [SOLVER-SPLIT]).
        growth_solver, flux_solver, flux_report = _solver_split(cmig_solver)
        # F5: the report tier must describe the flux that actually exists, not the solver name.
        # `_solver_split` cannot know that the pFBA stage fell back to plain FBA.
        if flux_report == "full" and flux_normalization != "pfba":
            flux_report = "fba_non_parsimonious"
        # F4: 진단을 (DiagnosticCode, message) 로 수집 → diagnostic_from_parts 구조화.
        # 위임 단계에서 이미 수집된 원인(pFBA fallback 등)을 앞에 유지한다.
        diag_parts: list[tuple[DiagnosticCode, str]] = list(solve_causes or [])

        # status — growth 비유한(infeasible) 가드 + 멤버 누락 진단 (§4.4).
        objective = float(sol.growth_rate)
        status: Literal["optimal", "infeasible", "unbounded", "solver_failed"] = "optimal"
        if not math.isfinite(objective):
            if math.isinf(objective):
                status = "unbounded"
                diag_parts.append(
                    (DiagnosticCode.UNBOUNDED, "community growth is infinite (unbounded)")
                )
            else:
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
            warnings=list(solve_warnings or []),
            flux_normalization_method=flux_normalization,
        )
