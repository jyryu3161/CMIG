"""AN-SINGLE FVA — Flux Variability Analysis (단일 GEM). closes G-3.

Design Ref: §10 AN-SINGLE / glossary FVA·AN-SINGLE (MVP-0) / schema profile fva_lo·fva_hi.
Plan SC(hardening): SC-H4.

objective 제약(fraction_of_optimum) 하에서 각 reaction flux 의 최소/최대 가능 범위를 계산한다.
cobra.flux_analysis.flux_variability_analysis 위임 (MICOM/cobra 위임 철학 일관 — 자체 LP 미구현).
loopless 옵션(thermodynamically infeasible loop 제거) 지원. infeasible 은 명시적 에러.

profile fva_lo/fva_hi 실채움: exchange reaction FVA 범위를 metabolite 키로 매핑하는 helper 제공.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


class FVAUnavailableError(RuntimeError):
    """cobra/LP solver 부재 → FVA 비활성화 (§2 capability degrade)."""


class FVAInfeasibleError(RuntimeError):
    """FVA 가 infeasible — objective 제약 만족 불가 (§4.4 수치 거동, capability 부재와 별개)."""


@dataclass(frozen=True)
class FVARange:
    """한 reaction 의 FVA 범위. lo ≤ hi 불변(보장)."""

    reaction_id: str
    lo: float
    hi: float


def _load_cobra() -> Any:
    try:
        import cobra
    except ImportError as e:  # pragma: no cover - 2a 환경
        raise FVAUnavailableError(
            "cobra 미설치 — FVA 비활성화 (`uv sync --extra engine`)."
        ) from e
    return cobra


def flux_variability(
    model: Any,
    *,
    reactions: list[str] | None = None,
    fraction_of_optimum: float = 1.0,
    loopless: bool = False,
    solver: str = "gurobi",
) -> dict[str, FVARange]:
    """AN-SINGLE FVA — reaction별 (lo, hi) flux 범위.

    model: cobra Model. reactions=None → 전체. fraction_of_optimum∈(0,1].
    LP capability 부재 → FVAUnavailableError; infeasible → FVAInfeasibleError.
    """
    if not (0.0 < fraction_of_optimum <= 1.0):
        raise ValueError(
            f"fraction_of_optimum ∈ (0,1] (받음: {fraction_of_optimum}) [§10]"
        )
    _load_cobra()
    from cobra.flux_analysis import flux_variability_analysis

    # LP capability 단일 진입점(solver seam) 경유 — 부재 시 fail-fast (TC-9 일관).
    from cmig.core.solver import capability_matrix
    cap = capability_matrix().get(solver)
    if cap is None or not cap.supports("LP"):
        raise FVAUnavailableError(
            f"solver '{solver}' LP capability 부재/미가용 (§2). "
            f"가용 LP solver: {[n for n, c in capability_matrix().items() if c.supports('LP')]}"
        )
    from cmig.core.single_model import set_model_solver
    set_model_solver(model, solver)
    rxn_list = reactions if reactions is not None else [r.id for r in model.reactions]
    # cobra ≥0.29: loopless 는 None|'fastSNP'|'cycleFreeFlux' (bool deprecated).
    loopless_arg = "cycleFreeFlux" if loopless else None
    try:
        df = flux_variability_analysis(
            model, reaction_list=rxn_list,
            fraction_of_optimum=fraction_of_optimum, loopless=loopless_arg,
        )
    except Exception as e:  # cobra Infeasible 등 → 명시적 에러 (silent 금지)
        raise FVAInfeasibleError(f"FVA infeasible (fraction={fraction_of_optimum}): {e}") from e

    out: dict[str, FVARange] = {}
    for rid, row in df.iterrows():
        lo, hi = float(row["minimum"]), float(row["maximum"])
        if not (math.isfinite(lo) and math.isfinite(hi)):
            raise FVAInfeasibleError(f"FVA 비유한 범위 ({rid}: {lo},{hi}) — infeasible/unbounded")
        if lo > hi:                       # 수치 잡음 보정 (lo ≤ hi 불변 보장)
            lo, hi = hi, lo
        out[str(rid)] = FVARange(reaction_id=str(rid), lo=lo, hi=hi)
    return out


def community_fva(
    community: Any,
    *,
    reactions: list[str] | None = None,
    fraction_of_optimum: float = 1.0,
    solver: str = "gurobi",
) -> dict[str, FVARange]:
    """F2 — community-level FVA (gurobi). micom Community 는 cobra Model 서브클래스이므로
    cobra FVA 를 위임한다.

    **processes=1 고정**: 병렬 worker 가 community 직렬화에서 RuntimeError(pickling) → 단일
    프로세스로 회피(probe 검증). reactions=None → 환경 exchange(`EX_*_m`) 전체.
    LP capability 부재 → FVAUnavailableError; infeasible → FVAInfeasibleError.
    """
    if not (0.0 < fraction_of_optimum <= 1.0):
        raise ValueError(f"fraction_of_optimum ∈ (0,1] (받음: {fraction_of_optimum}) [§10]")
    _load_cobra()
    from cobra.flux_analysis import flux_variability_analysis

    from cmig.core.solver import capability_matrix
    cap = capability_matrix().get(solver)
    if cap is None or not cap.supports("LP"):
        raise FVAUnavailableError(
            f"solver '{solver}' LP capability 부재/미가용 (§2). community FVA 는 gurobi-only."
        )
    # AE-1: osqp 는 community 경로에서 QP-only approximate(§4.2) — 명목상 LP 하이브리드가
    # FVA 반복 재최적화에서 time_limit 으로 퇴화해 InfeasibleError 로 *오표기*된다.
    # solver 런타임 실패(time_limit)를 진짜 infeasible 로 오분류하지 않도록 capability 단계에서
    # 사전 거부한다(정직성: capability 부재 ≠ 제약 infeasible).
    if solver == "osqp":
        raise FVAUnavailableError(
            "community FVA 는 osqp 미지원 — osqp 는 QP-only approximate(§4.2)이며 FVA 반복 "
            "재최적화에서 time_limit 으로 퇴화한다. --solver gurobi 를 사용하라."
        )
    from cmig.core.single_model import set_model_solver
    set_model_solver(community, solver)
    rxn_list = (
        reactions if reactions is not None
        else [r.id for r in community.reactions if r.id.startswith("EX_") and r.id.endswith("_m")]
    )
    try:
        df = flux_variability_analysis(
            community, reaction_list=rxn_list,
            fraction_of_optimum=fraction_of_optimum, processes=1,   # F2: 단일 프로세스 고정
        )
    except Exception as e:  # cobra Infeasible 등 → 명시적 에러 (silent 금지)
        raise FVAInfeasibleError(
            f"community FVA infeasible (fraction={fraction_of_optimum}): {e}"
        ) from e

    out: dict[str, FVARange] = {}
    for rid, row in df.iterrows():
        lo, hi = float(row["minimum"]), float(row["maximum"])
        if not (math.isfinite(lo) and math.isfinite(hi)):
            raise FVAInfeasibleError(f"community FVA 비유한 범위 ({rid}: {lo},{hi})")
        if lo > hi:
            lo, hi = hi, lo
        out[str(rid)] = FVARange(reaction_id=str(rid), lo=lo, hi=hi)
    return out


def attach_community_fva_to_profile(
    profile_rows: list[dict[str, Any]],
    community_fva_ranges: dict[str, FVARange],
) -> list[dict[str, Any]]:
    """F2 — community FVA(`EX_*_m` reaction id 기준)를 profile metabolite 행에 부착.

    매핑: `_met_from_exchange(reaction_id, "_m")`(engine 외부 profile 추출과 동일 규약)로
    `EX_ac_m → ac`. profile metabolite 와 매칭되면 fva_lo/fva_hi 채움, 없으면 None(강제 0 금지).
    member `EX_*_e` 는 out-of-scope. 불변식: fva_lo ≤ net_flux ≤ fva_hi(매칭 행).
    """
    from cmig.core.engine import _met_from_exchange

    # metabolite → FVARange (reaction id 를 metabolite 로 환산)
    by_met = {_met_from_exchange(rid, "_m"): rng for rid, rng in community_fva_ranges.items()}
    out = []
    for r in profile_rows:
        row = dict(r)
        rng = by_met.get(str(r.get("metabolite", "")))
        row["fva_lo"] = rng.lo if rng else None
        row["fva_hi"] = rng.hi if rng else None
        out.append(row)
    return out


def attach_community_fva_to_bundle(bundle: Any, community_fva_ranges: dict[str, FVARange]) -> Any:
    """F2 wiring: community FVA 를 bundle.profile 의 fva_lo/hi 에 실제로 채워 넣는다(in-place).

    profile rows → attach → PROFILE_SCHEMA 로 재구성. 산출(parquet/CLI) 경로에서 사용.
    """
    import pyarrow as pa

    from cmig.core.tidy import PROFILE_SCHEMA

    rows = attach_community_fva_to_profile(bundle.profile.to_pylist(), community_fva_ranges)
    bundle.profile = pa.Table.from_pylist(rows, schema=PROFILE_SCHEMA)
    return bundle


def attach_fva_to_profile(
    profile_rows: list[dict[str, Any]],
    fva: dict[str, FVARange],
    *,
    exchange_of: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """profile rows 에 fva_lo/fva_hi 실채움 (schema profile).

    exchange_of: metabolite → exchange reaction id 매핑(미지정 시 metabolite==reaction_id 가정).
    매칭 없으면 fva_lo/hi=None (결측 — 강제 0 금지, fail-explicit 일관).
    불변식: fva_lo ≤ net_flux ≤ fva_hi (해당 행에 FVA 있을 때).
    """
    mapping = exchange_of or {}
    out = []
    for r in profile_rows:
        row = dict(r)
        metab = str(r.get("metabolite", ""))
        rid = mapping.get(metab, metab)
        rng = fva.get(rid)
        row["fva_lo"] = rng.lo if rng else None
        row["fva_hi"] = rng.hi if rng else None
        out.append(row)
    return out
