"""Integrated real-model benchmark package for publication preflight."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cmig.core.dfba import DfbaConfig, run_dfba_sensitivity
from cmig.core.engine import MicomEngine
from cmig.core.host import benchmark_generic_host, run_bigg_host_microbe
from cmig.core.host_map import build_host_map
from cmig.core.model_quality import ModelQualityReport, audit_model_quality
from cmig.core.namespace import (
    NamespaceDecision,
    evaluate_gate,
    mapped_taxonomy,
    namespace_decision_keys,
)
from cmig.core.search import Direction
from cmig.core.search_product import SearchConfig, search_model_pool
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

    started = time.perf_counter()
    quality = _quality_reports(
        taxonomy,
        solver=config.solver,
        check_blocked_reactions=config.check_blocked_reactions,
    )
    write_model_quality_reports(quality, out / "model_quality")
    timings["model_quality_seconds"] = time.perf_counter() - started
    checks["all_microbial_models_solve"] = all(
        report.solve_status == "optimal" for report in quality
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

    if config.host_model is not None:
        started = time.perf_counter()
        host = load_cobra_model(config.host_model)
        host_benchmark = benchmark_generic_host(host, solver=config.solver)
        host_quality = audit_model_quality(
            host,
            source_path=config.host_model,
            solver=config.solver,
            check_blocked_reactions=config.check_blocked_reactions,
        )
        write_model_quality_reports([host_quality], out / "host" / "model_quality")
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
    return manifest_path
