"""EngineService — 명시 facade (Option C, seam 경계).

Design Ref: §2 (cmig-engine-service-facade.design). Plan SC: SC-S1·SC-S3·SC-S5.

**순수 위임**: 모든 메서드가 기존 core/io 함수를 동일 순서·동일 인자로 호출한다.
신규 계산·신규 run_hash 코드 0 — run_hash 는 write_solve_output 이 쓴 manifest 에서 read
([HASH-SINGLE]). Qt 비의존(NFR1): PySide6 미import.

CLI(_cmd_solve/_cmd_solve_fixture)·GUI·JobRunner 가 이 facade 를 공통 소비한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cmig.core.diagnostics import Diagnostic, DiagnosticCode, parse_diagnostic
from cmig.core.engine import MicomEngine
from cmig.core.interactions import build_tidy
from cmig.core.medium_spec import apply_medium_checked, load_medium, medium_checksum
from cmig.core.namespace import (
    NamespaceDecision,
    evaluate_gate,
    namespace_decision_keys,
)
from cmig.io.solve_output import build_run_components, write_solve_output
from cmig.service.outcome import SolveOutcome


class EngineService:
    """solve/sandbox/sweep/io 오케스트레이션의 단일 진입점. 단일 MicomEngine 보유(주입 가능)."""

    def __init__(self, engine: MicomEngine | None = None) -> None:
        self._engine = engine if engine is not None else MicomEngine()

    @property
    def engine(self) -> MicomEngine:
        return self._engine

    @property
    def micom_version(self) -> str:
        return self._engine.micom_version

    # ---- P0: fixture 경로 (_cmd_solve_fixture 본문 위임) ----
    def solve_fixture(
        self,
        *,
        solver: str = "gurobi",
        out_dir: str | Path,
        fva: bool = False,
        targets: str | None = None,
    ) -> SolveOutcome:
        """3-member 번들 fixture solve → parquet+manifest. components = fixture 고정 11구성.

        Plan SC: SC-S1. run_hash 는 manifest 에서 read(재계산 0).
        """
        from cmig.golden_fixture import (
            TRADEOFF_F,
            _run_hash_components,
            solve_with_community,
        )

        result, bundle, community = solve_with_community(solver)
        if fva:
            from cmig.core.fva import attach_community_fva_to_bundle, community_fva
            # AE-1: 실제 요청 solver 를 FVA 에 전달(미전달 시 gurobi 기본으로 community solver 와
            # 불일치 → osqp 경로가 time_limit→infeasible 로 오표기). osqp 는 community_fva 가
            # capability 부재로 사전 거부.
            ranges = community_fva(community, fraction_of_optimum=TRADEOFF_F, solver=solver)
            attach_community_fva_to_bundle(bundle, ranges)
        tsum = self._target_summary_or_none(bundle, targets)  # 미지 preset → ValueError
        # fixture 경로는 _run_hash_components(고정 11구성), build_run_components 아님.
        components = _run_hash_components(result)
        manifest_path = write_solve_output(
            bundle, components, out_dir, diagnostic=result.diagnostic, target_summary=tsum,
            flux_report_status=result.flux_report_status,
        )
        return SolveOutcome.from_manifest(
            result, bundle, components, manifest_path, community=community,
        )

    # ---- P1: 사용자 taxonomy(+medium) 경로 (_cmd_solve 본문 위임) ----
    def solve_community(
        self,
        *,
        taxonomy: Any,
        model_checksum: str,
        solver: str = "gurobi",
        tradeoff_f: float = 0.5,
        medium_path: str | None = None,
        namespace_decisions: list[NamespaceDecision] | None = None,
        strict_medium: bool = True,
        fva: bool = False,
        fva_metabolites: list[str] | None = None,
        targets: str | None = None,
        out_dir: str | Path,
        bounds: dict[str, list[float]] | None = None,
        env_lock: str | None = None,
    ) -> SolveOutcome:
        """임의 taxonomy(+medium) community solve → parquet+manifest.

        Plan SC: SC-S1·SC-S3. components = build_run_components(user 경로).
        `model_checksum` 은 호출자(CLI)가 file_checksum(tax_path)로 산출해 주입 — 파일 I/O 는 edge.
        `env_lock` 기본 None — CLI shim 은 전달하지 않음(manifest bytes 불변, §2.3).
        """
        decisions = namespace_decisions or []
        gate = evaluate_gate(decisions)
        gate.raise_if_blocked()

        spec = load_medium(medium_path) if medium_path else None
        community = self._engine.build_community(taxonomy, cmig_solver=solver)
        original_bounds = None
        unknown_medium: list[str] = []
        try:
            if spec is not None:
                _, unknown_medium = apply_medium_checked(
                    community, spec, strict=strict_medium
                )  # MICOM public API
            if bounds:
                from cmig.core.sandbox import BoundConstraint, apply_bounds

                original_bounds = apply_bounds(
                    community,
                    [
                        BoundConstraint(rid, float(pair[0]), float(pair[1]))
                        for rid, pair in sorted(bounds.items())
                    ],
                )
            result = self._engine.cooperative_tradeoff(community, tradeoff_f, cmig_solver=solver)
            bundle = build_tidy(result)
            if fva:
                from cmig.core.fva import attach_community_fva_to_bundle, community_fva
                # AE-1: 실제 요청 solver 전달(미전달 시 community solver 불일치 → 오표기).
                reactions = (
                    None if fva_metabolites is None
                    else [f"EX_{met}_m" for met in fva_metabolites]
                )
                ranges = community_fva(
                    community,
                    reactions=reactions,
                    fraction_of_optimum=tradeoff_f,
                    solver=solver,
                )
                attach_community_fva_to_bundle(bundle, ranges)
            tsum = self._target_summary_or_none(bundle, targets)
            components = build_run_components(
                result,
                model_checksum=model_checksum,
                medium_checksum=medium_checksum(spec),
                tradeoff_f=tradeoff_f,
                micom_version=self._engine.micom_version,
                bounds=bounds,
                namespace_decisions=namespace_decision_keys(decisions),
            )
            diagnostic = self._merge_run_diagnostic(result.diagnostic, unknown_medium)
            manifest_path = write_solve_output(
                bundle, components, out_dir,
                diagnostic=diagnostic, env_lock=env_lock, target_summary=tsum,
                flux_report_status=result.flux_report_status,
            )
            return SolveOutcome.from_manifest(
                result, bundle, components, manifest_path, community=community,
            )
        finally:
            if original_bounds:
                from cmig.core.sandbox import restore_bounds

                restore_bounds(community, original_bounds)

    @staticmethod
    def _merge_run_diagnostic(base: str | None, unknown_medium: list[str]) -> str | None:
        """solve diagnostic 에 non-fatal medium warning 을 구조화해 병합."""
        if not unknown_medium:
            return base
        warning = Diagnostic(
            DiagnosticCode.MEDIUM_UNAPPLIED,
            "medium exchange 일부가 community 에 없어 적용되지 않음",
            {"exchange_ids": unknown_medium},
        ).to_json()
        if base is None:
            return warning
        parsed = parse_diagnostic(base)
        if parsed is None:
            return warning
        return Diagnostic(
            DiagnosticCode(str(parsed.get("code") or DiagnosticCode.MEDIUM_UNAPPLIED.value)),
            str(parsed.get("message", "")),
            {"base": parsed, "warning": parse_diagnostic(warning)},
        ).to_json()

    # ---- AN-SINGLE (Phase 1.1): 단일-GEM FBA/pFBA 위임 (0.1 stub 대체) ----
    def solve_single(
        self, model: Any, *, method: str = "FBA", solver: str = "gurobi",
    ) -> Any:
        """단일 GEM(cobra Model) 분석 → SingleModelResult (core.single_model 위임).

        Plan SC: SC-AS1. LP capability 부재 → 정직한 capability_missing SingleModelResult
        (가짜 success 금지). model 은 필수(cobra Model).
        """
        from cmig.core.single_model import (
            SingleModelUnavailableError,
            capability_missing_result,
            solve_single_model,
        )
        try:
            return solve_single_model(model, method=method, solver=solver)
        except SingleModelUnavailableError:
            return capability_missing_result(solver)

    def sandbox_fixture(
        self,
        *,
        reaction_id: str,
        lower: float,
        upper: float,
        solver: str = "gurobi",
        tradeoff_f: float = 0.5,
        commit: bool = False,
        out_dir: str | Path | None = None,
    ) -> Any:
        """Fixture community constraint sandbox 제품 경로.

        baseline fixture를 풀고, 지정 reaction bound를 preview/commit으로 재solve한다.
        commit+out_dir이면 constrained tidy 산출과 manifest를 쓴다.

        [provenance] commit 의 run_hash 와 provenance 는 manifest.json 으로 영속된다. 이 facade
        seam 은 durable RunStore(sqlite) 인덱스에 등록하지 않는다(evaluate_sandbox store=None) —
        쿼리 가능한 store 인덱싱은 RunStore 통합 시점의 별도 작업이다(과대표기 방지).
        """
        from dataclasses import replace

        from cmig.core.manifest import compute_run_hash
        from cmig.core.sandbox import (
            BoundConstraint,
            SandboxState,
            apply_bounds,
            evaluate_sandbox,
            restore_bounds,
        )
        from cmig.golden_fixture import _run_hash_components, solve_with_community

        baseline, _base_bundle, community = solve_with_community(solver)
        original = apply_bounds(community, [BoundConstraint(reaction_id, lower, upper)])
        try:
            constrained = self._engine.cooperative_tradeoff(
                community, tradeoff_f, cmig_solver=solver
            )
        finally:
            restore_bounds(community, original)
        state = SandboxState.COMMITTED if commit else SandboxState.PREVIEW
        run_hash = None
        if commit:
            comps = _run_hash_components(constrained)
            comps = replace(comps, bounds={reaction_id: [lower, upper]})
            run_hash = compute_run_hash(comps)
        result = evaluate_sandbox(
            baseline,
            constrained,
            state=state,
            run_hash=run_hash,
        )
        if commit and out_dir is not None:
            from cmig.core.interactions import build_tidy
            comps = _run_hash_components(constrained)
            comps = replace(comps, bounds={reaction_id: [lower, upper]})
            write_solve_output(
                build_tidy(constrained),
                comps,
                out_dir,
                diagnostic=result.diagnostic,
                flux_report_status=constrained.flux_report_status,
            )
        return result

    @staticmethod
    def _target_summary_or_none(
        bundle: Any, targets: str | None,
    ) -> list[dict[str, Any]] | None:
        """F3: --targets preset → profile target summary (미지 preset → ValueError)."""
        if not targets:
            return None
        from cmig.core.targets import TARGET_PRESETS, target_summary
        if targets not in TARGET_PRESETS:
            raise ValueError(f"미지 target preset: {targets} (가능: {sorted(TARGET_PRESETS)})")
        return target_summary(bundle.profile.to_pylist(), TARGET_PRESETS[targets])
