"""G1 Constraint Sandbox — bound 제약 변경 + 재최적화, preview/commit 분리.

Design Ref: §10 AN-SANDBOX·§11 / A11 / schema §8.5 [PREVIEW-NOWRITE·RUNHASH-COMMIT].
Plan SC: SC-8 (sandbox preview 비오염).

**reaction flux 를 직접 바꾸지 않고**, reaction bound constraint 를 변경하고 community 를
재최적화한다. preview(기본·임시)는 store/cache/sweep 에 **비기록**; Apply/Save(commit)
시에만 Scenario/Run artifact 로 승격(run_hash 산출). 보상 우회로 변화 미미 시
`no_significant_change` 진단(FVA 는 §10; 여기선 delta 임계로 판정).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from cmig.core.delta import DeltaResult, compute_delta
from cmig.core.diagnostics import Diagnostic, DiagnosticCode
from cmig.core.engine import SolveResult
from cmig.core.fva import FVARange
from cmig.core.run_store import RunStore  # canonical 정의는 core/run_store (back-compat re-export)

__all__ = [
    "RunStore", "InMemoryRunStore", "SandboxState", "BoundConstraint",
    "SandboxResult", "evaluate_sandbox", "apply_bounds", "restore_bounds",
]


class SandboxState(enum.Enum):
    PREVIEW = "preview"      # 기본·임시 (store 비기록)
    COMMITTED = "committed"  # Apply/Save → artifact 승격


@dataclass(frozen=True)
class BoundConstraint:
    """멤버 reaction bound 제약 (sandbox 슬라이더 = 이 제약 변경)."""

    reaction_id: str
    lower: float
    upper: float


class InMemoryRunStore:
    """테스트/검증용 store — record_run 호출 횟수로 preview 비오염 입증 (SC-8)."""

    def __init__(self) -> None:
        self.records: list[tuple[str, SolveResult]] = []

    def record_run(self, run_hash: str, result: SolveResult) -> None:
        self.records.append((run_hash, result))

    @property
    def count(self) -> int:
        return len(self.records)


@dataclass(frozen=True)
class SandboxResult:
    """sandbox 산출. preview 면 run_hash=None·committed=False (ephemeral).

    status/diagnostic (TC-1, §4.4 fail-explicit): constrained 재solve 가 infeasible/실패면
    status='failed'+diagnostic 으로 노출한다. 실패를 no_significant_change=True 로 위장 금지.

    fva_ranges (C3/R4): no_significant_change=True 일 때(보상 우회로 변화 미미), 호출자가
    제공한 **단일-GEM FVA range** 를 동반해 '허용 변동 범위'를 제시한다. community-level FVA
    아님(설계 §6.1) — fva 는 cmig.core.fva.flux_variability(단일 cobra 모델)로 산출·주입.
    """

    delta: DeltaResult
    state: SandboxState
    no_significant_change: bool
    run_hash: str | None = None       # commit 에서만 채워짐
    committed: bool = False
    status: str = "ok"                # {ok, failed} — constrained solve 실패 전파
    diagnostic: str | None = None     # failed 면 ≠null
    fva_ranges: dict[str, FVARange] | None = None  # no-change 시 단일-GEM FVA (C3)


def evaluate_sandbox(
    baseline: SolveResult,
    constrained: SolveResult,
    *,
    state: SandboxState = SandboxState.PREVIEW,
    store: RunStore | None = None,
    run_hash: str | None = None,
    threshold: float = 1e-6,
    fva: dict[str, FVARange] | None = None,
) -> SandboxResult:
    """baseline vs constrained(=bound 제약 후 재solve) → SandboxResult.

    [PREVIEW-NOWRITE] state=PREVIEW 이면 store 를 호출하지 않는다(비오염).
    [RUNHASH-COMMIT] state=COMMITTED 이면 store.record_run + run_hash 승격.
    보상 우회로 external-profile delta 가 임계 이하면 no_significant_change=True.

    TC-1 (fail-explicit): constrained 재solve 가 infeasible/실패면 status='failed'+diagnostic
    으로 노출하고 no_significant_change=False — '변화 없음' 위장 금지(design E-1·ERR-NO-SILENT).

    C3 (R4): no_significant_change=True 이고 fva(단일-GEM FVA range)가 제공되면 SandboxResult
    에 동반 — '변화 없음'을 '허용 변동 범위'와 함께 제시. 변화가 유의하거나 실패면 미동반.
    """
    delta = compute_delta(baseline, constrained)
    # constrained solve 실패는 delta.status 로 전파됨 (compute_delta) — 직접 status 도 확인.
    failed = delta.status == "failed" or constrained.status != "optimal"
    diagnostic = delta.diagnostic                       # F4: delta 가 이미 구조화 JSON
    if constrained.status != "optimal" and not diagnostic:
        diagnostic = Diagnostic(
            DiagnosticCode.INFEASIBLE, f"constrained status={constrained.status}"
        ).to_json()
    status = "failed" if failed else "ok"
    # 실패면 '변화 없음' 판정 금지(위장 방지). 정상일 때만 delta 임계로 판정.
    no_sig = (not failed) and len(delta.significant(threshold)) == 0
    # C3: no-change 일 때만 FVA range 동반(허용 변동 범위 제시).
    fva_ranges = fva if (no_sig and fva) else None

    if state is SandboxState.COMMITTED:
        if run_hash is None:
            raise ValueError("commit 시 run_hash 필요 ([RUNHASH-COMMIT], schema §8.5)")
        if store is not None:
            store.record_run(run_hash, constrained)
        return SandboxResult(
            delta=delta, state=state, no_significant_change=no_sig,
            run_hash=run_hash, committed=True, status=status, diagnostic=diagnostic,
            fva_ranges=fva_ranges,
        )

    # PREVIEW: store 비기록·run_hash 없음 (ephemeral)
    return SandboxResult(
        delta=delta, state=SandboxState.PREVIEW, no_significant_change=no_sig,
        run_hash=None, committed=False, status=status, diagnostic=diagnostic,
        fva_ranges=fva_ranges,
    )


def apply_bounds(
    community: object, bounds: list[BoundConstraint]
) -> dict[str, tuple[float, float]]:
    """community(cobra model) reaction bound 변경. 원래 bound 반환(undo 용).

    Design Ref: §10 — flux 직접 변경이 아니라 bound constraint 변경.
    """
    original: dict[str, tuple[float, float]] = {}
    reactions = community.reactions  # type: ignore[attr-defined]
    for b in bounds:
        rxn = reactions.get_by_id(b.reaction_id)
        original[b.reaction_id] = (rxn.lower_bound, rxn.upper_bound)
        rxn.lower_bound, rxn.upper_bound = b.lower, b.upper
    return original


def restore_bounds(community: object, original: dict[str, tuple[float, float]]) -> None:
    """apply_bounds 의 역연산 (취소·되돌리기)."""
    reactions = community.reactions  # type: ignore[attr-defined]
    for rid, (lo, hi) in original.items():
        rxn = reactions.get_by_id(rid)
        rxn.lower_bound, rxn.upper_bound = lo, hi
