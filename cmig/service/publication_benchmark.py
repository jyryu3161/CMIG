"""Integrated real-model benchmark package for publication preflight."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cmig.core.dfba import DfbaConfig, run_dfba_sensitivity
from cmig.core.engine import MicomEngine
from cmig.core.host import benchmark_generic_host, run_bigg_host_microbe
from cmig.core.host_map import build_host_map, host_map_policy
from cmig.core.model_quality import ModelQualityReport, audit_model_quality
from cmig.core.namespace import (
    NamespaceDecision,
    evaluate_gate,
    mapped_taxonomy,
    namespace_decision_keys,
)
from cmig.core.search import Direction
from cmig.core.search_product import SearchConfig, search_model_pool
from cmig.core.workflow_manifest import (
    base_components,
    bundle_component,
    host_spec_component,
    mapping_checksum,
    medium_component,
    write_workflow_manifest,
)
from cmig.io.dfba_output import write_dfba_sensitivity
from cmig.io.model_import import load_cobra_model
from cmig.io.quality_output import write_model_quality_reports
from cmig.io.solve_output import (
    file_checksum,
    runtime_versions,
    taxonomy_model_checksum,
)
from cmig.service.engine_service import EngineService


@dataclass(frozen=True)
class PublicationBenchmarkConfig:
    taxonomy: Any
    taxonomy_base_dir: Path
    out_dir: Path
    solver: str = "gurobi"
    tradeoff_f: float = 0.5
    namespace_policy: Literal["require_reviewed", "assume_bigg"] = "require_reviewed"
    namespace_decisions: list[NamespaceDecision] = field(default_factory=list)
    search_target: str = "ac"
    search_direction: Direction = Direction.MAX_SECRETION
    search_min_size: int = 2
    search_max_size: int = 2
    search_top_k: int = 10
    check_blocked_reactions: bool = False
    dfba_model: Path | None = None
    dfba_config: DfbaConfig | None = None
    dfba_dts: list[float] = field(default_factory=lambda: [0.2, 0.1, 0.05])
    dfba_kms: list[float] = field(default_factory=lambda: [0.005, 0.01, 0.02])
    host_model: Path | None = None
    host_source: dict[str, str] = field(default_factory=dict)
    host_interface_map: dict[str, str] | None = None
    microbial_biomass_gdw: float | None = None
    host_biomass_gdw: float | None = None
    biomass_basis_kind: str | None = None
    biomass_basis_source: str | None = None
    host_medium: dict[str, float] | None = None
    keep_host_uptake: bool = False


def _resolve_taxonomy(taxonomy: Any, base_dir: Path) -> Any:
    resolved = taxonomy.copy(deep=True)
    for index in resolved.index:
        source = Path(str(resolved.at[index, "file"]))
        if not source.is_absolute():
            source = base_dir / source
        if not source.exists():
            raise ValueError(f"benchmark taxonomy model file not found: {source}")
        resolved.at[index, "file"] = str(source.resolve())
    return resolved


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            _json_safe(payload),
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )


def _artifact_checksums(out: Path) -> dict[str, str]:
    return {
        str(path.relative_to(out)): file_checksum(path)
        for path in sorted(out.rglob("*"))
        if path.is_file() and path.name != "publication_benchmark.json"
    }


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class _BundleRecorder:
    """Writes each sub-run's own workflow manifest and remembers what it certified.

    `publication-benchmark` is the surface that claims to bundle the whole audit, so a reader must
    be able to go from the bundle to the individual runs. Each sub-run therefore gets a real
    `manifest.json` next to its artifacts (so `cmig inspect-run <sub-dir>` works on it), and the
    bundle records the resulting (kind, run_hash) pairs.

    Manifest failures follow the same rule as `cli.main._emit_workflow_manifest`: report and
    record no hash, never fabricate one and never destroy a finished analysis. A child that could
    not be fingerprinted is kept in the bundle with ``run_hash: None`` so the bundle hash reflects
    that it certifies less, rather than silently pretending the child was never run.
    """

    def __init__(self, out: Path) -> None:
        self._out = out
        self.children: list[dict[str, Any]] = []
        self.warnings: list[str] = []

    def emit(
        self,
        kind: str,
        rel_dir: str,
        build_components: Callable[[], dict[str, Any]],
        *,
        status: str = "ok",
        artifacts: list[str] | None = None,
        summary: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
    ) -> str | None:
        try:
            run_hash: str | None = write_workflow_manifest(
                self._out / rel_dir, kind, build_components(),
                status=status, artifacts=artifacts, summary=summary, warnings=warnings,
            )
        except Exception as error:  # noqa: BLE001 - provenance must not destroy a finished result
            message = (
                f"sub-run {kind!r} ({rel_dir}) completed but its reproducibility manifest could "
                f"not be written ({type(error).__name__}: {error}); it is bundled without a "
                "run_hash"
            )
            print(f"  warning: {message}", file=sys.stderr)
            self.warnings.append(message)
            run_hash = None
        self.record(kind, rel_dir, run_hash, status=status)
        return run_hash

    def record(
        self, kind: str, rel_dir: str, run_hash: str | None, *, status: str = "ok"
    ) -> None:
        """Record a child whose hash was produced elsewhere (e.g. the 11-component solve)."""
        self.children.append({
            "kind": kind, "artifacts_dir": rel_dir, "run_hash": run_hash, "status": status,
        })


def _child_solve_run_hash(community_dir: Path) -> str | None:
    """The community sub-run's own 11-component run_hash, read from the manifest it already wrote.

    [HASH-SINGLE]: carried, never recomputed. Returns None if the solve wrote no usable manifest,
    so a bundle cannot claim to certify a solve it cannot identify.

    The scope check is not decorative. A workflow envelope and a solve manifest are both
    `manifest.json` with a 64-hex `run_hash`, and they are *different* hashes over different
    component sets. If this directory ever comes to hold a workflow-scope manifest, carrying its
    hash would label a workflow fingerprint `community_solve` in the bundle and void [HASH-SINGLE]
    silently. Manifests written before `manifest_scope` existed carry no key and are accepted:
    only a positively workflow-scoped one is refused.
    """
    manifest = community_dir / "manifest.json"
    if not manifest.exists():
        return None
    try:
        payload = json.loads(manifest.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("manifest_scope") == "workflow":
        return None
    value = payload.get("run_hash")
    return None if value is None else str(value)


def _quality_child_spec(
    sources: list[Path], *, scope: str, check_blocked_reactions: bool
) -> dict[str, Any]:
    return {
        "n_models": len(sources),
        "check_blocked_reactions": bool(check_blocked_reactions),
        "sources": sorted(str(path) for path in sources),
        "scope": scope,
    }


def _quality_model_checksum(sources: list[Path]) -> str:
    """The model-bytes fingerprint shape a standalone `model-quality` run records."""
    return json.dumps(
        {str(path): file_checksum(path) for path in sorted(sources, key=str)},
        sort_keys=True, separators=(",", ":"),
    )


def _dfba_spec_component(config: PublicationBenchmarkConfig) -> dict[str, Any] | None:
    """The dFBA sensitivity grid, or None when the bundle ran no dFBA leg."""
    if config.dfba_model is None or config.dfba_config is None:
        return None
    return {
        "mode": "sensitivity",
        "model": str(config.dfba_model),
        "model_checksum": file_checksum(config.dfba_model),
        "config": asdict(config.dfba_config),
        "dts": [float(value) for value in config.dfba_dts],
        "kms": [float(value) for value in config.dfba_kms],
    }


def _benchmark_host_spec(config: PublicationBenchmarkConfig) -> dict[str, Any] | None:
    """The host side of the bundle, or None when no host leg ran."""
    if config.host_model is None:
        return None
    return host_spec_component(
        host_model=config.host_model,
        host_model_checksum=file_checksum(config.host_model),
        host_medium_checksum=mapping_checksum(
            None if config.host_medium is None
            else {key: float(value) for key, value in config.host_medium.items()}
        ),
        interface_map_checksum=mapping_checksum(config.host_interface_map),
        keep_host_uptake=config.keep_host_uptake,
    )


def _benchmark_biomass_basis(config: PublicationBenchmarkConfig) -> dict[str, Any] | None:
    """The gDW scaling that makes host and microbial fluxes comparable, or None if uncoupled."""
    if config.host_interface_map is None:
        return None
    return {
        "kind": config.biomass_basis_kind,
        "source": config.biomass_basis_source,
        "microbial_biomass_gdw": (
            None if config.microbial_biomass_gdw is None
            else float(config.microbial_biomass_gdw)
        ),
        "host_biomass_gdw": (
            None if config.host_biomass_gdw is None else float(config.host_biomass_gdw)
        ),
    }


def _benchmark_run_status(checks: dict[str, bool]) -> str:
    """Map the check set onto the ok/degraded/failed vocabulary every CMIG run reports."""
    if not checks:
        return "failed"
    computational = {
        key: value for key, value in checks.items()
        if key != "host_coupling_has_study_biomass_basis"
    }
    if not all(computational.values()):
        return "failed"
    return "ok" if all(checks.values()) else "degraded"


def _quality_reports(
    taxonomy: Any, *, solver: str, check_blocked_reactions: bool
) -> list[ModelQualityReport]:
    return [
        audit_model_quality(
            load_cobra_model(str(record["file"])),
            source_path=str(record["file"]),
            solver=solver,
            check_blocked_reactions=check_blocked_reactions,
        )
        for record in taxonomy.to_dict("records")
    ]


def run_publication_benchmark(config: PublicationBenchmarkConfig) -> Path:
    """Run the configured benchmark and return the final manifest path."""
    if config.host_interface_map is not None and config.host_model is None:
        raise ValueError("host_interface_map requires host_model")
    coupling_basis: tuple[float, float, str, str] | None = None
    if config.host_interface_map is not None:
        missing = [
            name
            for name, value in {
                "microbial_biomass_gdw": config.microbial_biomass_gdw,
                "host_biomass_gdw": config.host_biomass_gdw,
                "biomass_basis_kind": config.biomass_basis_kind,
                "biomass_basis_source": config.biomass_basis_source,
            }.items()
            if value is None or (isinstance(value, str) and not value.strip())
        ]
        if missing:
            raise ValueError(
                "reviewed host coupling requires explicit biomass values and provenance: "
                + ", ".join(missing)
            )
        assert config.microbial_biomass_gdw is not None
        assert config.host_biomass_gdw is not None
        assert config.biomass_basis_kind is not None
        assert config.biomass_basis_source is not None
        coupling_basis = (
            float(config.microbial_biomass_gdw),
            float(config.host_biomass_gdw),
            str(config.biomass_basis_kind),
            str(config.biomass_basis_source),
        )
    elif any(
        value is not None
        for value in (
            config.microbial_biomass_gdw,
            config.host_biomass_gdw,
            config.biomass_basis_kind,
            config.biomass_basis_source,
        )
    ):
        raise ValueError("biomass coupling inputs require host_interface_map")
    if config.namespace_policy == "require_reviewed":
        evaluate_gate(config.namespace_decisions).raise_if_blocked()
    elif config.namespace_decisions:
        raise ValueError("assume_bigg benchmark cannot also receive namespace decisions")
    taxonomy = _resolve_taxonomy(config.taxonomy, config.taxonomy_base_dir)
    out = config.out_dir
    out.mkdir(parents=True, exist_ok=True)
    engine = MicomEngine()
    dependencies = runtime_versions()
    model_fingerprint = taxonomy_model_checksum(taxonomy)
    timings: dict[str, float] = {}
    checks: dict[str, bool] = {}
    warnings: list[str] = []
    bundle = _BundleRecorder(out)
    pool_sources = [Path(str(record["file"])) for record in taxonomy.to_dict("records")]
    namespace_bridge = {
        "namespace_policy": config.namespace_policy,
        "namespace_decisions": namespace_decision_keys(config.namespace_decisions),
    }

    started = time.perf_counter()
    quality = _quality_reports(
        taxonomy,
        solver=config.solver,
        check_blocked_reactions=config.check_blocked_reactions,
    )
    quality_artifacts = write_model_quality_reports(quality, out / "model_quality")
    timings["model_quality_seconds"] = time.perf_counter() - started
    checks["all_microbial_models_solve"] = all(
        report.solve_status == "optimal" for report in quality
    )
    bundle.emit(
        "model_quality", "model_quality",
        lambda: {
            **base_components(
                "model_quality",
                solver_setting={"solver": config.solver},
                model_checksum=_quality_model_checksum(pool_sources),
                medium=medium_component(None, "model_quality_no_medium"),
                dependency_versions=dependencies,
            ),
            "quality_spec": _quality_child_spec(
                pool_sources, scope="microbial_pool",
                check_blocked_reactions=config.check_blocked_reactions,
            ),
        },
        status="ok" if checks["all_microbial_models_solve"] else "degraded",
        artifacts=list(quality_artifacts),
        summary={"n_models": len(quality)},
    )

    started = time.perf_counter()
    community = EngineService(engine).solve_community(
        taxonomy=taxonomy,
        model_checksum=model_fingerprint,
        solver=config.solver,
        tradeoff_f=config.tradeoff_f,
        namespace_decisions=config.namespace_decisions,
        namespace_policy=config.namespace_policy,
        out_dir=out / "community",
    )
    timings["community_seconds"] = time.perf_counter() - started
    checks["community_optimal"] = community.status == "ok"
    # The community leg already wrote the frozen 11-component solve manifest; carry its hash
    # ([HASH-SINGLE]) instead of wrapping it in a second envelope.
    bundle.record(
        "community_solve", "community", _child_solve_run_hash(out / "community"),
        status="ok" if checks["community_optimal"] else "failed",
    )

    mapping_decisions = (
        config.namespace_decisions if config.namespace_policy == "require_reviewed" else []
    )
    with mapped_taxonomy(taxonomy, mapping_decisions) as (search_taxonomy, applied):
        started = time.perf_counter()
        search = search_model_pool(
            engine,
            search_taxonomy,
            SearchConfig(
                target=config.search_target,
                direction=config.search_direction,
                min_size=config.search_min_size,
                max_size=config.search_max_size,
                strategy="exhaustive",
                top_k=config.search_top_k,
                solver=config.solver,
            ),
        )
        timings["search_seconds"] = time.perf_counter() - started
    search_payload = {
        **asdict(search),
        "namespace_applied_mappings": [asdict(item) for item in applied],
    }
    _write_json(out / "search" / "search_benchmark.json", search_payload)
    checks["search_has_optimal_candidate"] = any(
        rank.status == "optimal" for rank in search.ranks
    )
    search_defaults = SearchConfig(target=config.search_target)
    bundle.emit(
        "model_pool_search", "search",
        lambda: {
            **base_components(
                "model_pool_search",
                solver_setting={"solver": config.solver},
                model_checksum=model_fingerprint,
                medium=medium_component(
                    None, "micom_default_medium", namespace_bridge=namespace_bridge,
                ),
                dependency_versions=dependencies,
            ),
            "target_spec": {
                "target": config.search_target,
                "direction": config.search_direction.value,
                "mode": "single_target",
            },
            "search_spec": {
                "min_size": int(config.search_min_size),
                "max_size": int(config.search_max_size),
                "strategy": "exhaustive",
                "top_k": int(config.search_top_k),
                "n_samples": int(search_defaults.n_samples),
                "seed": int(search_defaults.seed),
                "robustness_fva": bool(search_defaults.robustness_fva),
                "namespace_applied_mappings": sorted(
                    f"{item.model_id}:{item.source_metabolite_id}->{item.target_metabolite_id}"
                    for item in applied
                ),
            },
            # The benchmark does not expose --growth-fraction; record the default that actually
            # constrained the search rather than omitting it.
            "growth_fraction": float(search_defaults.growth_fraction),
        },
        status="ok" if checks["search_has_optimal_candidate"] else "degraded",
        artifacts=["search_benchmark.json"],
        summary={"n_ranks": len(search.ranks), "target": config.search_target},
    )

    if config.dfba_model is not None:
        if config.dfba_config is None:
            raise ValueError("dfba_model requires dfba_config")
        started = time.perf_counter()
        dfba_model = load_cobra_model(config.dfba_model)
        dfba = run_dfba_sensitivity(
            dfba_model,
            config.dfba_config,
            dts=config.dfba_dts,
            kms=config.dfba_kms,
            solver=config.solver,
        )
        write_dfba_sensitivity(
            dfba,
            out / "dfba",
            provenance={
                "model_path": str(config.dfba_model.resolve()),
                "model_checksum": file_checksum(config.dfba_model),
                "dependency_versions": dependencies,
            },
        )
        timings["dfba_seconds"] = time.perf_counter() - started
        checks["dfba_completed"] = all(row.status == "completed" for row in dfba.rows)
        checks["dfba_balance_passed"] = all(
            row.max_concentration_residual <= 1e-9
            and row.max_biomass_residual <= 1e-9
            for row in dfba.rows
        )
        dfba_model_path = config.dfba_model
        bundle.emit(
            "dfba", "dfba",
            lambda: {
                **base_components(
                    "dfba",
                    solver_setting={"solver": config.solver},
                    model_checksum=file_checksum(dfba_model_path),
                    medium=medium_component(None, "single_model_no_medium"),
                    dependency_versions=dependencies,
                ),
                "dfba_spec": _dfba_spec_component(config),
            },
            status="ok" if checks["dfba_completed"] and checks["dfba_balance_passed"] else (
                "degraded" if checks["dfba_completed"] else "failed"
            ),
            artifacts=["dfba_sensitivity.json"],
            summary={"n_conditions": len(dfba.rows)},
        )

    if config.host_model is not None:
        host_model_path = config.host_model
        started = time.perf_counter()
        host = load_cobra_model(config.host_model)
        host_benchmark = benchmark_generic_host(host, solver=config.solver)
        host_quality = audit_model_quality(
            host,
            source_path=config.host_model,
            solver=config.solver,
            check_blocked_reactions=config.check_blocked_reactions,
        )
        host_quality_artifacts = write_model_quality_reports(
            [host_quality], out / "host" / "model_quality"
        )
        bundle.emit(
            "model_quality", "host/model_quality",
            lambda: {
                **base_components(
                    "model_quality",
                    solver_setting={"solver": config.solver},
                    model_checksum=_quality_model_checksum([host_model_path]),
                    medium=medium_component(None, "model_quality_no_medium"),
                    dependency_versions=dependencies,
                ),
                "quality_spec": _quality_child_spec(
                    [host_model_path], scope="host_model",
                    check_blocked_reactions=config.check_blocked_reactions,
                ),
            },
            status="ok" if host_quality.solve_status == "optimal" else "degraded",
            artifacts=list(host_quality_artifacts),
            summary={"n_models": 1},
        )
        _write_json(
            out / "host" / "host_benchmark.json",
            {
                "source": {
                    **config.host_source,
                    "path": str(config.host_model.resolve()),
                    "checksum": file_checksum(config.host_model),
                },
                "benchmark": asdict(host_benchmark),
            },
        )
        checks["host_model_optimal"] = host_benchmark.solve.status == "optimal"
        member_models = {
            str(record["id"]): load_cobra_model(str(record["file"]))
            for record in taxonomy.to_dict("records")
        }
        host_map = build_host_map(host, member_models)
        suggested_map = {
            entry.metabolite: entry.host_exchange
            for entry in host_map.entries
            if entry.match_type in {"exact", "annotation", "normalized"}
            and entry.host_exchange is not None
        }
        _write_json(
            out / "host" / "host_map_benchmark.json",
            {**asdict(host_map), "suggested_interface_map": suggested_map},
        )
        checks["host_mapping_has_matches"] = bool(suggested_map)
        # The interface-map pre-flight the whole host leg rests on gets its own manifest, in its
        # own directory: `out/host` already holds two other sub-runs' artifacts and a directory
        # can only carry one manifest.json.
        bundle.emit(
            "host_map", "host/host_map",
            lambda: {
                **base_components(
                    "host_map",
                    # host-map never invokes a solver, so the solver is not a determining input.
                    # Recorded as None here and by `cmig host-map`, so the same host + pool
                    # fingerprints identically on both surfaces.
                    solver_setting={"solver": None},
                    model_checksum=model_fingerprint,
                    medium=medium_component(None, "host_map_no_medium"),
                    dependency_versions=dependencies,
                ),
                "host_spec": host_spec_component(
                    host_model=host_model_path,
                    host_model_checksum=file_checksum(host_model_path),
                ),
                "map_spec": host_map_policy(),
            },
            status="ok" if suggested_map else "degraded",
            artifacts=["../host_map_benchmark.json"],
            summary={
                "n_microbial_secretions": host_map.n_microbial_secretions,
                "n_exact": host_map.n_exact,
                "n_annotation": host_map.n_annotation,
                "n_normalized": host_map.n_normalized,
                "n_unmatched": host_map.n_unmatched,
                "suggested_interface_map_checksum": mapping_checksum(suggested_map),
            },
        )
        if config.host_interface_map is not None:
            assert coupling_basis is not None
            microbial_biomass_gdw, host_biomass_gdw, basis_kind, basis_source = (
                coupling_basis
            )
            mapping_decisions = (
                config.namespace_decisions
                if config.namespace_policy == "require_reviewed" else []
            )
            with mapped_taxonomy(taxonomy, mapping_decisions) as (host_taxonomy, _applied):
                coupling = run_bigg_host_microbe(
                    host_taxonomy,
                    host,
                    microbial_biomass_gdw=microbial_biomass_gdw,
                    host_biomass_gdw=host_biomass_gdw,
                    biomass_basis_kind=basis_kind,
                    biomass_basis_source=basis_source,
                    solver=config.solver,
                    tradeoff_f=config.tradeoff_f,
                    host_medium=config.host_medium,
                    interface_map=config.host_interface_map,
                    close_unlisted_host_uptake=not config.keep_host_uptake,
                    engine=engine,
                )
            _write_json(
                out / "host" / "host_coupling_benchmark.json", asdict(coupling)
            )
            checks["host_coupling_community_optimal"] = coupling.community_status == "optimal"
            checks["host_coupling_host_optimal"] = coupling.host_result.status == "optimal"
            checks["host_coupling_has_matched_exchange"] = bool(coupling.matched_exchanges)
            checks["host_coupling_has_study_biomass_basis"] = (
                coupling.coupling_scale is not None
                and coupling.coupling_scale.basis_kind in {"measured", "literature"}
            )
            coupling_ok = (
                checks["host_coupling_community_optimal"]
                and checks["host_coupling_host_optimal"]
            )
            bundle.emit(
                "host_microbe_bigg", "host/coupling",
                lambda: {
                    **base_components(
                        "host_microbe_bigg",
                        solver_setting={"solver": config.solver},
                        model_checksum=model_fingerprint,
                        medium=medium_component(
                            None, "no_microbe_medium", namespace_bridge=namespace_bridge,
                        ),
                        dependency_versions=dependencies,
                    ),
                    "abundances": {
                        str(key): value
                        for key, value in sorted(
                            (coupling.coupling_scale.__dict__ or {}).items()
                        )
                        if isinstance(value, (int, float))
                    } if coupling.coupling_scale else {},
                    "tradeoff_f": float(config.tradeoff_f),
                    "host_spec": _benchmark_host_spec(config),
                    "biomass_basis": _benchmark_biomass_basis(config),
                    "flux_normalization_method": "pfba",
                    "solve_run_hash": None,
                },
                status="ok" if coupling_ok else "failed",
                artifacts=["../host_coupling_benchmark.json"],
                warnings=list(coupling.warnings),
                summary={
                    "community_growth": _json_safe(float(coupling.community_growth)),
                    "host_objective": _json_safe(float(coupling.host_result.biomass)),
                    "host_status": coupling.host_result.status,
                    "n_matched_exchanges": len(coupling.matched_exchanges),
                },
            )
        elif not host_benchmark.quantitative_coupling_ready:
            warnings.append(
                "real host scale benchmark passed, but quantitative microbe-host coupling "
                "requires a reviewed exchange/interface mapping; annotation suggestions are "
                "reported but not auto-applied"
            )
        timings["host_seconds"] = time.perf_counter() - started

    scientific_inputs = {
        "model_fingerprint": model_fingerprint,
        "host_checksum": (
            None if config.host_model is None else file_checksum(config.host_model)
        ),
        "host_coupling": {
            "interface_map": config.host_interface_map,
            "microbial_biomass_gdw": config.microbial_biomass_gdw,
            "host_biomass_gdw": config.host_biomass_gdw,
            "biomass_basis_kind": config.biomass_basis_kind,
            "biomass_basis_source": config.biomass_basis_source,
            "host_medium": config.host_medium,
            "keep_host_uptake": config.keep_host_uptake,
        },
        "dfba_checksum": (
            None if config.dfba_model is None else file_checksum(config.dfba_model)
        ),
        "solver": config.solver,
        "tradeoff_f": config.tradeoff_f,
        "namespace_policy": config.namespace_policy,
        "namespace_decisions": namespace_decision_keys(config.namespace_decisions),
        "search": {
            "target": config.search_target,
            "direction": config.search_direction.value,
            "min_size": config.search_min_size,
            "max_size": config.search_max_size,
            "top_k": config.search_top_k,
        },
        "dfba": {
            "config": None if config.dfba_config is None else asdict(config.dfba_config),
            "dts": config.dfba_dts,
            "kms": config.dfba_kms,
        },
        "dependencies": dependencies,
    }
    warnings.extend(bundle.warnings)
    artifacts = _artifact_checksums(out)
    computational_checks = {
        key: value
        for key, value in checks.items()
        if key != "host_coupling_has_study_biomass_basis"
    }
    manifest = {
        "publication_benchmark_schema_version": "1.1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_hash": _canonical_hash(scientific_inputs),
        "scientific_inputs": scientific_inputs,
        "checks": checks,
        "computational_checks_passed": all(computational_checks.values()),
        "publication_ready": all(checks.values()),
        "overall_passed": all(checks.values()),
        "timings": timings,
        "warnings": warnings,
        "artifacts": artifacts,
        "limitations": [
            "constraint-based predictions are model- and medium-dependent",
            "deterministic sensitivity conditions are not biological replicates",
            "member-level transfer allocation is not causal attribution",
        ],
    }
    manifest_path = out / "publication_benchmark.json"
    _write_json(manifest_path, manifest)
    _emit_bundle_manifest(config, out, bundle, checks, model_fingerprint, dependencies, warnings)
    return manifest_path


def _emit_bundle_manifest(
    config: PublicationBenchmarkConfig,
    out: Path,
    bundle: _BundleRecorder,
    checks: dict[str, bool],
    model_fingerprint: str,
    dependencies: dict[str, str],
    warnings: list[str],
) -> str | None:
    """The bundle's own workflow manifest, written last so it is not one of its own artifacts.

    Its hash covers this command's arguments *and* `bundle_spec` — the kind and run_hash of every
    sub-run it certified (see `workflow_manifest.bundle_component` for why the child hashes are
    inside the hash rather than beside it).
    """
    n_models = len(config.taxonomy.index)

    def _components() -> dict[str, Any]:
        components = base_components(
            "publication_benchmark",
            solver_setting={"solver": config.solver},
            model_checksum=model_fingerprint,
            medium=medium_component(
                None, "publication_benchmark_no_shared_medium",
                namespace_bridge={
                    "namespace_policy": config.namespace_policy,
                    "namespace_decisions": namespace_decision_keys(config.namespace_decisions),
                },
            ),
            dependency_versions=dependencies,
        )
        host_spec = _benchmark_host_spec(config)
        components["tradeoff_f"] = float(config.tradeoff_f)
        components["target_spec"] = {
            "target": config.search_target,
            "direction": config.search_direction.value,
            "mode": "single_target",
        }
        components["search_spec"] = {
            "min_size": int(config.search_min_size),
            "max_size": int(config.search_max_size),
            "strategy": "exhaustive",
            "top_k": int(config.search_top_k),
        }
        components["quality_spec"] = {
            "check_blocked_reactions": bool(config.check_blocked_reactions),
            "n_microbial_models": int(n_models),
        }
        components["dfba_spec"] = _dfba_spec_component(config)
        components["host_spec"] = (
            None if host_spec is None
            else {**host_spec, "host_source": dict(sorted(config.host_source.items()))}
        )
        components["biomass_basis"] = _benchmark_biomass_basis(config)
        components["bundle_spec"] = bundle_component(bundle.children)
        return components

    try:
        return write_workflow_manifest(
            out, "publication_benchmark", _components(),
            status=_benchmark_run_status(checks),
            artifacts=["publication_benchmark.json"],
            warnings=list(warnings),
            summary={
                "overall_passed": all(checks.values()),
                "publication_ready": all(checks.values()),
                "n_certified_sub_runs": len(bundle.children),
                "checks": dict(sorted(checks.items())),
            },
        )
    except Exception as error:  # noqa: BLE001 - provenance must not destroy a finished result
        print(
            "  warning: publication-benchmark completed but its reproducibility manifest could "
            f"not be written ({type(error).__name__}: {error}); this bundle has no run_hash",
            file=sys.stderr,
        )
        return None
