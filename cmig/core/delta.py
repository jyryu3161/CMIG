"""AN-DELTA — baseline vs modified community 차이 산출.

Design Ref: §10 AN-DELTA / Plan FR-2.1 / glossary AN-DELTA.
Plan SC: SC-9 (tidy delta).

baseline 복제 → 멤버 추가/제약 변경 → 동일 조건 재solve → 차이(external profile delta·
member set 변화). 순수 로직(두 SolveResult → DeltaResult) — 엔진 비의존, 테스트 가능.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts
from cmig.core.engine import SolveResult


@dataclass(frozen=True)
class MetaboliteDelta:
    """external profile 한 대사체의 baseline→modified 변화."""

    metabolite: str
    baseline: float          # baseline net flux (raw, 부호 有)
    modified: float          # modified net flux (raw)
    delta: float             # modified − baseline


@dataclass(frozen=True)
class DeltaResult:
    """add-member/constraint delta 산출.

    status/diagnostic (TC-4·TC-5, §4.4 fail-explicit): 입력 중 하나라도 실패
    (status≠optimal 또는 growth 비유한)면 status='failed'+diagnostic 로 전파한다.
    실패한 solve 의 delta 를 정상 delta 와 구분 없이 산출하지 않는다.
    """

    profile: list[MetaboliteDelta]
    added_members: list[str] = field(default_factory=list)
    removed_members: list[str] = field(default_factory=list)
    growth_delta: float = 0.0          # community growth 변화 (실패 시 NaN 가능)
    status: str = "ok"                 # {ok, failed} — 입력 실패 전파
    diagnostic: str | None = None      # failed 면 ≠null (원인)

    def significant(self, threshold: float = 1e-6) -> list[MetaboliteDelta]:
        """변화 있는 대사체 (|delta| > threshold).

        TC-6: 비유한(NaN/inf) delta 는 **조용히 누락하지 않고 significant 로 본다**
        (infeasible 산물을 '변화 없음'으로 위장 금지, §4.4). 정상 비교는 |delta|>threshold.
        """
        return [
            d for d in self.profile
            if not math.isfinite(d.delta) or abs(d.delta) > threshold
        ]


def _solve_diag(result: SolveResult, role: str) -> tuple[DiagnosticCode, str] | None:
    """입력 SolveResult 가 실패면 (code, message), 정상이면 None (F4 구조화)."""
    if result.status != "optimal":
        return (DiagnosticCode.INFEASIBLE, f"{role} status={result.status}")
    if not math.isfinite(result.objective):
        return (DiagnosticCode.INFEASIBLE, f"{role} growth 비유한({result.objective})")
    return None


def compute_delta(baseline: SolveResult, modified: SolveResult) -> DeltaResult:
    """두 SolveResult(동일 조건) → DeltaResult. metabolite 합집합 기준 정렬.

    TC-4/TC-5: 입력 실패(status≠optimal/비유한 growth)를 status·diagnostic 으로 전파.
    """
    metabs = sorted(set(baseline.external_exchange) | set(modified.external_exchange))
    profile = [
        MetaboliteDelta(
            metabolite=m,
            baseline=(b := baseline.external_exchange.get(m, 0.0)),
            modified=(mod := modified.external_exchange.get(m, 0.0)),
            delta=mod - b,
        )
        for m in metabs
    ]
    base_members, mod_members = set(baseline.members), set(modified.members)
    diags = [d for d in (_solve_diag(baseline, "baseline"),
                         _solve_diag(modified, "modified")) if d]
    status = "failed" if diags else "ok"
    diagnostic = diagnostic_from_parts(diags)          # F4: 구조화 JSON
    return DeltaResult(
        profile=profile,
        added_members=sorted(mod_members - base_members),
        removed_members=sorted(base_members - mod_members),
        growth_delta=modified.objective - baseline.objective,
        status=status,
        diagnostic=diagnostic,
    )


def load_solve_result_from_run(run_dir: str | Path) -> SolveResult:
    """Reconstruct the solve fields needed by AN-DELTA from one tidy run directory.

    Community growth is the abundance-weighted sum of member growth stored in ``nodes.parquet``,
    matching MICOM's community objective. Missing member measurements or an empty member table
    produce a failed solve record; they are never filled with zero and compared as a result.
    """
    from cmig.core.tidy import TidyBundle

    source = Path(run_dir)
    bundle = TidyBundle.read(source)
    external_exchange = {
        str(row["metabolite"]): float(row["net_flux"])
        for row in bundle.profile.to_pylist()
    }
    members: list[str] = []
    member_growth: dict[str, float | None] = {}
    abundances: dict[str, float | None] = {}
    objective = 0.0
    status = "optimal"
    diagnostic: str | None = None
    for row in bundle.nodes.to_pylist():
        if row.get("node_type") != "member":
            continue
        member = str(row["node_id"])
        members.append(member)
        growth_raw, abundance_raw = row.get("growth"), row.get("abundance")
        growth = None if growth_raw is None else float(growth_raw)
        abundance = None if abundance_raw is None else float(abundance_raw)
        member_growth[member] = growth
        abundances[member] = abundance
        if (
            growth is None or abundance is None
            or not math.isfinite(growth) or not math.isfinite(abundance)
        ):
            status = "infeasible"
            continue
        objective += growth * abundance
    if not members:
        status = "solver_failed"
        diagnostic = f"{source} contains no member nodes"
    elif status != "optimal":
        diagnostic = f"{source} contains missing or non-finite member growth/abundance"
    return SolveResult(
        objective=objective,
        member_growth=member_growth,
        abundances=abundances,
        external_exchange=external_exchange,
        member_exchange={member: {} for member in members},
        status=status,  # type: ignore[arg-type]
        flux_report_status="none",
        growth_solver="reconstructed_from_nodes",
        flux_solver=None,
        diagnostic=diagnostic,
        members=members,
        flux_normalization_method="recorded_tidy_profile",
    )
