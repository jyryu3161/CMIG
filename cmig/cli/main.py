"""CMIG CLI entry. Design Ref: §4.1 (EngineService facade 소비) / §5.

version·solvers·golden verify 동작. solve-fixture(C7/P0)=fixture solve→parquet+manifest 산출.
solve --taxonomy --medium 은 P1(후속).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
import random
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cmig import CMIG_CORE_VERSION
from cmig.core.solver import capability_matrix

DEFAULT_DFBA_INITIAL_CONCENTRATIONS = {
    "EX_glc__D_e": 10.0,
    "EX_o2_e": 20.0,
    "EX_ac_e": 0.0,
    "EX_lac__D_e": 0.0,
}

GUI_CLI_WORKFLOWS: list[dict[str, Any]] = [
    {
        "gui_surface": "Models / Import Model",
        "cli_command": "cmig model-review",
        "purpose": "Review a user-provided GEM and generate namespace/import diagnostics.",
        "required_args": ["--model", "--out"],
        "common_options": ["--known-targets", "--source-namespace", "--target-namespace"],
        "key_outputs": ["model_review.json"],
        "example": "uv run cmig model-review --model models/iML1515.xml --out runs/model_review",
    },
    {
        "gui_surface": "Toolbar / Run Fixture",
        "cli_command": "cmig solve-fixture",
        "purpose": "Run the bundled fixture community solve used by the GUI smoke workflow.",
        "required_args": ["--out"],
        "common_options": ["--solver", "--targets", "--fva"],
        "key_outputs": ["manifest.json", "nodes.parquet", "edges.parquet", "profile.parquet"],
        "example": "uv run cmig solve-fixture --solver gurobi --out runs/solve_fixture",
    },
    {
        "gui_surface": "Community / MICOM Taxonomy Solve",
        "cli_command": "cmig solve",
        "purpose": "Run a user-provided MICOM taxonomy community solve.",
        "required_args": ["--taxonomy", "--out"],
        "common_options": [
            "--medium",
            "--namespace-decisions",
            "--allow-unknown-medium",
            "--solver",
            "--tradeoff-f",
            "--targets",
            "--fva",
            "--fva-metabolites",
            "--bounds",
        ],
        "key_outputs": ["manifest.json", "nodes.parquet", "edges.parquet", "profile.parquet"],
        "example": (
            "uv run cmig solve --taxonomy taxonomy.csv --medium medium_presets/western_diet.csv "
            "--solver gurobi --tradeoff-f 0.5 --out runs/solve"
        ),
    },
    {
        "gui_surface": "Search / Find Best Model Combination",
        "cli_command": "cmig search",
        "purpose": "Rank microbial model combinations by target exchange production or uptake.",
        "required_args": ["--model-dir or --taxonomy", "--target", "--out"],
        "common_options": [
            "--min-size",
            "--max-size",
            "--strategy",
            "--n-samples",
            "--seed",
            "--top-k",
            "--robustness-fva",
            "--medium",
            "--recursive",
        ],
        "key_outputs": [
            "search_summary.json",
            "search_rankings.csv",
            "search_member_matrix.csv",
            "pool_diagnostics.csv",
            "search_plot.svg",
            "search_scatter.svg",
        ],
        "example": (
            "uv run cmig search --model-dir models --target but --min-size 2 "
            "--max-size 2 --top-k 10 --out runs/search_but"
        ),
    },
    {
        "gui_surface": "Search / Strain Growth",
        "cli_command": "cmig strain-growth",
        "purpose": "Compare each strain's single-model growth with its community growth.",
        "required_args": ["--model-dir or --taxonomy", "--out"],
        "common_options": ["--medium", "--tradeoff-f", "--recursive"],
        "key_outputs": [
            "strain_growth_summary.json",
            "strain_growth.csv",
            "strain_growth_plot.svg",
        ],
        "example": "uv run cmig strain-growth --model-dir models --out runs/strain_growth",
    },
    {
        "gui_surface": "Search / Ratio Impact",
        "cli_command": "cmig abundance-impact",
        "purpose": "Sweep one member abundance and quantify growth and target flux changes.",
        "required_args": ["--model-dir or --taxonomy", "--member", "--out"],
        "common_options": ["--fractions", "--target", "--medium", "--tradeoff-f", "--recursive"],
        "key_outputs": [
            "abundance_impact_summary.json",
            "abundance_impact.csv",
            "member_growth_by_abundance.csv",
            "abundance_impact_plot.svg",
        ],
        "example": (
            "uv run cmig abundance-impact --model-dir models --member iML1515 "
            "--fractions 0.1,0.25,0.5,0.75 --target ac --out runs/iML1515_ac_ratio"
        ),
    },
    {
        "gui_surface": "Search / Rank Gene KOs",
        "cli_command": "cmig gene-ko-search",
        "purpose": "Rank single-gene knockout targets for a fixed microbial combination.",
        "required_args": ["--model-dir or --taxonomy", "--members", "--target", "--out"],
        "common_options": [
            "--member",
            "--ko-level",
            "--genes",
            "--reactions",
            "--gene-selection",
            "--seed",
            "--max-genes",
            "--jobs",
            "--direction",
            "--growth-fraction",
            "--top-k",
            "--recursive",
        ],
        "key_outputs": ["gene_ko_summary.json", "gene_ko_rankings.csv", "gene_ko_plot.svg"],
        "example": (
            "uv run cmig gene-ko-search --model-dir models --members iML1515,iHN637 "
            "--target but --max-genes 0 --top-k 20 --out runs/gene_ko_but"
        ),
    },
    {
        "gui_surface": "Host / Run Host-Microbe",
        "cli_command": "cmig host-microbe-bigg",
        "purpose": "Run direct BiGG-style host-microbe exchange coupling.",
        "required_args": ["--host", "--model-dir or --taxonomy", "--out"],
        "common_options": [
            "--host-objective",
            "--microbe-medium",
            "--host-medium",
            "--exclude-metabolites",
            "--include-currency-metabolites",
            "--recursive",
        ],
        "key_outputs": [
            "host_microbe_bigg_summary.json",
            "interaction_edges.csv",
            "interaction_matrix.csv",
            "interaction_circle.svg",
            "interaction_heatmap.svg",
            "interaction_bubble.svg",
        ],
        "example": (
            "uv run cmig host-microbe-bigg --host models_human/Recon3D.xml "
            "--model-dir models --recursive --out runs/host_microbe"
        ),
    },
    {
        "gui_surface": "Host / Rank Combinations",
        "cli_command": "cmig host-search-bigg",
        "purpose": "Rank microbial combinations by host objective and target transfer.",
        "required_args": ["--host", "--model-dir or --taxonomy", "--out"],
        "common_options": [
            "--min-size",
            "--max-size",
            "--target",
            "--metric",
            "--host-weight",
            "--target-weight",
            "--host-objective",
            "--recursive",
        ],
        "key_outputs": [
            "host_search_summary.json",
            "host_search_rankings.csv",
            "host_search_plot.svg",
        ],
        "example": (
            "uv run cmig host-search-bigg --host models_human/Recon3D.xml "
            "--model-dir models --target ac --out runs/host_search"
        ),
    },
    {
        "gui_surface": "Dynamics / Run dFBA",
        "cli_command": "cmig dfba",
        "purpose": "Run well-mixed single-model dynamic FBA.",
        "required_args": ["--model", "--out"],
        "common_options": ["--initial", "--t-end", "--dt", "--initial-biomass", "--vmax", "--km"],
        "key_outputs": ["dfba_summary.json", "timecourse.parquet", "dfba_timecourse.svg"],
        "example": "uv run cmig dfba --model models/iML1515.xml --dt 0.1 --out runs/dfba_iML1515",
    },
    {
        "gui_surface": "Dynamics / Preview Spatial Medium",
        "cli_command": "cmig spatial-preview",
        "purpose": "Preview a 2D source/sink diffusion medium gradient.",
        "required_args": ["--out"],
        "common_options": [
            "--metabolite",
            "--width",
            "--height",
            "--steps",
            "--dt",
            "--diffusion",
            "--source-edge",
            "--sink-edge",
        ],
        "key_outputs": ["spatial_summary.json", "spatial_frames.csv", "spatial_heatmap.svg"],
        "example": (
            "uv run cmig spatial-preview --metabolite EX_glc__D_e --width 48 "
            "--height 48 --source-edge left --sink-edge right --out runs/spatial_glucose"
        ),
    },
    {
        "gui_surface": "Profile / Open Run",
        "cli_command": "cmig inspect-run",
        "purpose": "Inspect a completed CMIG run directory and report its summary/artifacts.",
        "required_args": ["--run-dir"],
        "common_options": ["--format json", "--format text"],
        "key_outputs": ["stdout JSON or text"],
        "example": "uv run cmig inspect-run --run-dir runs/search_but --format json",
    },
    {
        "gui_surface": "Advanced / Sweep",
        "cli_command": "cmig sweep",
        "purpose": (
            "Run taxonomy-based parameter sweeps over solver, medium, members, "
            "abundance, and bounds."
        ),
        "required_args": ["--taxonomy", "--out"],
        "common_options": [
            "--tradeoff-fs",
            "--solvers",
            "--mediums",
            "--member-sets",
            "--abundance-variants",
            "--bounds-variants",
            "--fva",
            "--fva-metabolites",
        ],
        "key_outputs": ["sweep_summary.json", "sweep.parquet", "sweep_profiles.parquet", "runs/"],
        "example": (
            "uv run cmig sweep --taxonomy taxonomy.csv --tradeoff-fs 0.3,0.5 "
            "--mediums medium_presets/western_diet.csv --out runs/sweep"
        ),
    },
    {
        "gui_surface": "Advanced / Sandbox Fixture",
        "cli_command": "cmig sandbox-fixture",
        "purpose": "Preview or commit a reaction bound edit on the bundled fixture community.",
        "required_args": ["--reaction", "--lower", "--upper"],
        "common_options": ["--commit", "--solver", "--out"],
        "key_outputs": ["sandbox_summary.json", "manifest.json when committed"],
        "example": (
            "uv run cmig sandbox-fixture --reaction EX_glc__D_e__Escherichia_coli_1 "
            "--lower -1 --upper 1000 --out runs/sandbox_preview"
        ),
    },
]

RUN_SUMMARY_FILES: list[tuple[str, str]] = [
    ("manifest.json", "community_solve"),
    ("search_summary.json", "model_pool_search"),
    ("host_microbe_bigg_summary.json", "host_microbe_bigg"),
    ("host_search_summary.json", "host_search_bigg"),
    ("strain_growth_summary.json", "strain_growth"),
    ("abundance_impact_summary.json", "abundance_impact"),
    ("gene_ko_summary.json", "gene_ko_search"),
    ("dfba_summary.json", "dfba"),
    ("spatial_summary.json", "spatial_preview"),
    ("model_review.json", "model_review"),
    ("sweep_summary.json", "sweep"),
    ("stats_summary.json", "stats_demo"),
    ("stats_sweep_summary.json", "stats_sweep"),
    ("sandbox_summary.json", "sandbox_fixture"),
    ("host_summary.json", "host_fixture"),
    ("host_generic_summary.json", "host_generic"),
    ("host_benchmark.json", "host_benchmark"),
    ("search_advanced_summary.json", "advanced_search_fixture"),
]


def _cmd_version(_: argparse.Namespace) -> int:
    print(f"cmig {CMIG_CORE_VERSION}")
    return 0


def _cmd_solvers(_: argparse.Namespace) -> int:
    print("Solver capability matrix (§5.1):")
    print(f"  {'solver':8} {'LP':>3} {'QP':>3} {'MILP':>5} {'available':>10}")
    for name, cap in capability_matrix().items():
        print(
            f"  {name:8} {str(cap.lp):>3} {str(cap.qp):>3} "
            f"{str(cap.milp):>5} {str(cap.available):>10}"
        )
    return 0


def _cmd_workflows(args: argparse.Namespace) -> int:
    """Print the GUI-to-CLI workflow map for LLM agents and automation."""
    payload = {
        "schema_version": "1.0",
        "purpose": "Map CMIG GUI analysis surfaces to equivalent CLI workflows.",
        "workflows": GUI_CLI_WORKFLOWS,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False))
        return 0
    print("CMIG GUI-to-CLI workflow map")
    for item in GUI_CLI_WORKFLOWS:
        print(f"\n[{item['gui_surface']}]")
        print(f"  command: {item['cli_command']}")
        print(f"  purpose: {item['purpose']}")
        print(f"  required: {', '.join(item['required_args'])}")
        print(f"  outputs: {', '.join(item['key_outputs'])}")
        print(f"  example: {item['example']}")
    return 0


def _cmd_inspect_run(args: argparse.Namespace) -> int:
    """Inspect a completed CMIG run directory in a machine-readable form."""
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists() or not run_dir.is_dir():
        print(f"run directory not found: {run_dir}", file=sys.stderr)
        return 2
    payload = _inspect_run_dir(run_dir)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False))
        return 0
    print(f"run_dir: {payload['run_dir']}")
    print(f"kind: {payload['kind']}")
    print(f"status: {payload['status']}")
    if payload["summary_file"]:
        print(f"summary_file: {payload['summary_file']}")
    if payload["run_hash"]:
        print(f"run_hash: {payload['run_hash']}")
    print("artifacts:")
    for artifact in payload["artifacts"]:
        print(f"  - {artifact}")
    return 0


def _inspect_run_dir(run_dir: Path) -> dict[str, Any]:
    kind = "unknown"
    summary_file: str | None = None
    summary: dict[str, Any] = {}
    for filename, candidate_kind in RUN_SUMMARY_FILES:
        path = run_dir / filename
        if not path.exists():
            continue
        loaded = _load_json_object(path)
        if loaded is None:
            continue
        kind = candidate_kind
        summary_file = filename
        summary = loaded
        break

    manifest = _load_json_object(run_dir / "manifest.json") or {}
    status = _string_or_none(summary.get("status")) or _string_or_none(manifest.get("status"))
    run_hash = _string_or_none(summary.get("run_hash")) or _string_or_none(manifest.get("run_hash"))
    return {
        "schema_version": "1.0",
        "run_dir": str(run_dir),
        "kind": kind,
        "status": status or "unknown",
        "summary_file": summary_file,
        "run_hash": run_hash,
        "artifacts": _list_run_artifacts(run_dir),
        "manifest": _compact_manifest(manifest),
        "summary_keys": sorted(str(key) for key in summary.keys()),
    }


def _load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _list_run_artifacts(run_dir: Path, *, limit: int = 200) -> list[str]:
    artifacts: list[str] = []
    for path in sorted(run_dir.rglob("*")):
        if path == run_dir:
            continue
        rel = path.relative_to(run_dir).as_posix()
        artifacts.append(rel + "/" if path.is_dir() else rel)
        if len(artifacts) >= limit:
            artifacts.append(f"... truncated after {limit} entries")
            break
    return artifacts


def _compact_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "manifest_schema_version",
        "run_hash",
        "status",
        "artifacts",
        "inputs",
        "solver",
        "software",
    ]
    return {key: manifest[key] for key in keys if key in manifest}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _cmd_solve_fixture(args: argparse.Namespace) -> int:
    """C7 (P0): 번들 3-member fixture 를 solve → parquet + manifest 산출 (facade 경유).

    Design Ref: §2 (EngineService.solve_fixture 위임). run_hash 는 facade 가 manifest 에서
    read([HASH-SINGLE]) — CLI 는 더 이상 오케스트레이션하지 않는다.
    """
    from cmig.core.fva import FVAUnavailableError
    from cmig.service import EngineService

    try:
        outcome = EngineService().solve_fixture(
            solver=args.solver, out_dir=args.out, fva=args.fva, targets=args.targets,
        )
    except ImportError:
        print("solve-fixture 는 엔진 stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    except FVAUnavailableError as e:              # AE-1: FVA capability 부재 → 깔끔한 rc2
        print(f"FVA 미지원: {e}", file=sys.stderr)
        return 2
    except ValueError as e:                       # F3: 미지 target preset
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:                           # A1: 산출 쓰기 실패 → 깔끔한 rc2
        print(f"산출 쓰기 실패: {e}", file=sys.stderr)
        return 2
    # A2: facade 성공 계약 명시 가드(Design §3.3, python -O 에서도 유효 — assert 아님).
    if outcome.status != "ok" or outcome.run_hash is None or outcome.manifest_path is None:
        print(f"solve-fixture 실패: {outcome.diagnostic}", file=sys.stderr)
        return 1
    extra = " + target_summary.json" if args.targets else ""
    print(f"solve-fixture 완료 (solver={args.solver}) → {outcome.manifest_path.parent}")
    print(f"  run_hash: {outcome.run_hash[:16]}…  artifacts: parquet+manifest{extra}")
    return 0


def _cmd_solve(args: argparse.Namespace) -> int:
    """C6/C7 (P1): 사용자 taxonomy(+medium) → community solve → parquet+manifest (facade 경유).

    Design Ref: §2 (EngineService.solve_community 위임). argparse 검증은 CLI 유지,
    오케스트레이션은 facade 위임. model_checksum 은 CLI 가 산출해 주입(I/O edge).
    """
    try:
        import pandas as pd

        from cmig.core.fva import FVAUnavailableError
        from cmig.core.namespace import GateBlockedError, load_namespace_decisions
        from cmig.service import EngineService
    except ImportError:
        print("solve 는 엔진 stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2

    tax_path = Path(args.taxonomy)
    if not tax_path.exists():
        print(f"taxonomy 파일 없음: {tax_path}", file=sys.stderr)
        return 2
    if not (0.0 < args.tradeoff_f <= 1.0):
        print(f"--tradeoff-f 는 0<f≤1 (받음: {args.tradeoff_f})", file=sys.stderr)
        return 2
    taxonomy = pd.read_csv(tax_path)
    # AF-5: taxonomy 필수 컬럼 검증(micom Community 입력 계약) — solve 전 fail-fast.
    missing_cols = {"id", "file"} - set(taxonomy.columns)
    if missing_cols:
        print(f"taxonomy 필수 컬럼 누락: {sorted(missing_cols)} (필요: id, file)", file=sys.stderr)
        return 2

    try:
        namespace_decisions = (
            load_namespace_decisions(args.namespace_decisions)
            if args.namespace_decisions else None
        )
        outcome = EngineService().solve_community(
            taxonomy=taxonomy,
            model_checksum=_taxonomy_model_checksum(taxonomy, tax_path),
            solver=args.solver,
            tradeoff_f=args.tradeoff_f,
            medium_path=args.medium,
            namespace_decisions=namespace_decisions,
            strict_medium=not args.allow_unknown_medium,
            fva=args.fva or args.fva_metabolites is not None,
            fva_metabolites=_parse_optional_csv_strings(args.fva_metabolites),
            targets=args.targets,
            out_dir=args.out,
            bounds=_load_bounds_json(args.bounds) if args.bounds else None,
        )
    except ImportError:
        print("solve 는 엔진 stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    except FVAUnavailableError as e:              # AE-1: FVA capability 부재 → 깔끔한 rc2
        print(f"FVA 미지원: {e}", file=sys.stderr)
        return 2
    except ValueError as e:                       # F3 미지 preset · medium 입력 오류
        print(str(e), file=sys.stderr)
        return 2
    except GateBlockedError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:                           # A1: 산출 쓰기 실패 → 깔끔한 rc2
        print(f"산출 쓰기 실패: {e}", file=sys.stderr)
        return 2
    # A2: facade 성공 계약 명시 가드(Design §3.3, python -O 에서도 유효).
    if (outcome.status != "ok" or outcome.run_hash is None
            or outcome.manifest_path is None or outcome.result is None):
        print(f"solve 실패: {outcome.diagnostic}", file=sys.stderr)
        return 1
    medium_label = "custom" if args.medium else "default"
    print(f"solve 완료 (solver={args.solver}, medium={medium_label}) "
          f"→ {outcome.manifest_path.parent}")
    print(f"  run_hash: {outcome.run_hash[:16]}…  growth: {outcome.result.objective:.4f}")
    return 0


def _cmd_golden_verify(_: argparse.Namespace) -> int:
    """MICOM-version golden regression gate (SC-5)."""
    try:
        from cmig.golden_fixture import verify_golden_versions
    except ImportError:  # pragma: no cover
        print("golden verify 는 엔진 stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    report = verify_golden_versions()
    all_ok = True
    print("MICOM-version golden regression (SC-5):")
    for solver, r in report.items():
        mark = "OK " if r["ok"] else "MISMATCH"
        all_ok = all_ok and bool(r["ok"])
        print(f"  [{mark}] {solver:24} golden={r['recorded']} installed={r['installed']}")
    if not all_ok:
        print("→ golden 재캡처 필요 (python -m cmig.golden_fixture)", file=sys.stderr)
        return 2
    print("→ 모든 golden 이 설치 MICOM 버전과 일치 (승격 가능)")
    return 0


def _write_json_or_print(payload: dict[str, Any], out: str | None, filename: str) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
    if out is None:
        print(text)
        return
    d = Path(out)
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text(text + "\n")
    print(f"{filename} → {d}")


def _cmd_host_fixture(args: argparse.Namespace) -> int:
    """Synthetic host-microbe fixture solve. 정량 Human-GEM 검증이 아니라 wiring smoke."""
    try:
        from cmig.core.host import solve_host
        from cmig.core.host_impact import host_impact
        from cmig.synthetic_host import build_host_model, lumen_availability_from_pair
    except ImportError:
        print("host-fixture 는 engine stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    host = build_host_model()
    lumen = lumen_availability_from_pair()
    result = solve_host(host, lumen, maintenance_flux=args.maintenance_flux, solver=args.solver)
    impact = host_impact(lumen, result)
    payload = {
        "status": result.status,
        "viable": result.viable,
        "biomass": result.biomass,
        "lumen_uptake": result.lumen_uptake,
        "microbe_to_host": impact.microbe_to_host,
        "unused_secretion": impact.unused_secretion,
        "diagnostic": result.diagnostic,
        "scope": "synthetic_toy_host_not_human_gem_quantitative",
    }
    _write_json_or_print(payload, args.out, "host_summary.json")
    return 0


def _cmd_host_generic(args: argparse.Namespace) -> int:
    """Generic cobra-compatible host GEM smoke solve (Recon3D/Human-GEM style)."""
    try:
        from cobra.io import read_sbml_model

        from cmig.core.host import solve_generic_host, summarize_host_model
    except ImportError:
        print("host-generic 는 engine stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    model_path = Path(args.model)
    if not model_path.exists():
        print(f"host model 파일 없음: {model_path}", file=sys.stderr)
        return 2
    model = read_sbml_model(str(model_path))
    summary = summarize_host_model(model)
    result = solve_generic_host(model, solver=args.solver)
    payload = {
        "model": {
            "id": summary.model_id,
            "n_reactions": summary.n_reactions,
            "n_metabolites": summary.n_metabolites,
            "n_genes": summary.n_genes,
            "n_exchanges": summary.n_exchanges,
            "compartments": summary.compartments,
            "objective_reactions": summary.objective_reactions,
            "exchange_examples": summary.exchange_examples,
            "has_lumen_blood_interfaces": summary.has_lumen_blood_interfaces,
        },
        "solve": {
            "status": result.status,
            "viable": result.viable,
            "objective_value": result.biomass,
            "interface_fluxes": [f.__dict__ for f in result.interface_fluxes],
            "lumen_uptake": result.lumen_uptake,
            "diagnostic": result.diagnostic,
        },
        "scope": "generic_human_gem_smoke_not_cmig_lumen_blood_coupling",
    }
    _write_json_or_print(payload, args.out, "host_generic_summary.json")
    return 0


def _cmd_host_benchmark(args: argparse.Namespace) -> int:
    """Generic Human-GEM/Recon3D host scale benchmark."""
    try:
        from cobra.io import read_sbml_model

        from cmig.core.host import benchmark_generic_host
    except ImportError:
        print("host-benchmark 는 engine stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    model_path = Path(args.model)
    if not model_path.exists():
        print(f"host model 파일 없음: {model_path}", file=sys.stderr)
        return 2
    result = benchmark_generic_host(read_sbml_model(str(model_path)), solver=args.solver)
    payload = {
        "model": result.summary.__dict__,
        "solve": {
            "status": result.solve.status,
            "viable": result.solve.viable,
            "objective_value": result.solve.biomass,
            "n_interface_fluxes": len(result.solve.interface_fluxes),
            "diagnostic": result.solve.diagnostic,
        },
        "benchmark": {
            "solve_seconds": result.solve_seconds,
            "peak_memory_mb": result.peak_memory_mb,
        },
        "quantitative_coupling_ready": result.quantitative_coupling_ready,
        "warnings": result.warnings,
    }
    _write_json_or_print(payload, args.out, "host_benchmark.json")
    return 0


def _apply_host_objective(host: Any, reaction_id: str | None) -> None:
    if not reaction_id:
        return
    if reaction_id not in host.reactions:
        raise ValueError(f"host objective reaction not found: {reaction_id}")
    host.objective = reaction_id


def _cmd_host_microbe_bigg(args: argparse.Namespace) -> int:
    """BiGG direct host-microbe coupling: microbial secretion -> host EX_<met>_e."""
    try:
        import pandas as pd
        from cobra.io import read_sbml_model

        from cmig.core.host import run_bigg_host_microbe
        from cmig.core.medium_spec import load_medium
        from cmig.core.model_pool import taxonomy_from_model_dir
    except ImportError:
        print(
            "host-microbe-bigg requires the engine stack: uv sync --extra engine",
            file=sys.stderr,
        )
        return 2
    try:
        host_path = Path(args.host)
        if not host_path.exists():
            raise ValueError(f"host model file not found: {host_path}")
        if bool(args.taxonomy) == bool(args.model_dir):
            raise ValueError("provide exactly one of --taxonomy or --model-dir")
        if args.taxonomy:
            taxonomy_path = Path(args.taxonomy)
            if not taxonomy_path.exists():
                raise ValueError(f"taxonomy file not found: {taxonomy_path}")
            taxonomy = pd.read_csv(taxonomy_path)
        else:
            taxonomy = taxonomy_from_model_dir(args.model_dir, recursive=args.recursive)
        missing_cols = {"id", "file"} - set(taxonomy.columns)
        if missing_cols:
            raise ValueError(f"taxonomy missing required columns: {sorted(missing_cols)}")
        host = read_sbml_model(str(host_path))
        _apply_host_objective(host, args.host_objective)
        microbe_medium = load_medium(args.microbe_medium) if args.microbe_medium else None
        host_medium = load_medium(args.host_medium).uptake if args.host_medium else None
        exclude = set() if args.include_currency_metabolites else {"h", "h2o", "co2"}
        if args.exclude_metabolites:
            exclude.update(
                _parse_csv_strings(args.exclude_metabolites, flag="--exclude-metabolites")
            )
        result = run_bigg_host_microbe(
            taxonomy,
            host,
            solver=args.solver,
            tradeoff_f=args.tradeoff_f,
            microbe_medium=microbe_medium,
            host_medium=host_medium,
            exchange_suffix=args.exchange_suffix,
            exclude_metabolites=exclude,
            close_unlisted_host_uptake=not args.keep_host_uptake,
        )
        out = Path(args.out)
        _write_host_microbe_bigg_outputs(result, taxonomy, out)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"failed to write host-microbe outputs: {e}", file=sys.stderr)
        return 2
    print(f"host-microbe BiGG coupling complete -> {out}")
    print(
        f"  community_growth={result.community_growth:.4g} "
        f"host_objective={result.host_result.biomass:.4g} "
        f"host_status={result.host_result.status}"
    )
    return 0


def _cmd_host_search_bigg(args: argparse.Namespace) -> int:
    """Rank microbial combinations by host objective and/or target transfer."""
    try:
        import pandas as pd
        from cobra.io import read_sbml_model

        from cmig.core.host import run_bigg_host_microbe
        from cmig.core.medium_spec import load_medium
        from cmig.core.model_pool import taxonomy_from_model_dir
        from cmig.core.search_product import candidate_combinations
    except ImportError:
        print(
            "host-search-bigg requires the engine stack: uv sync --extra engine",
            file=sys.stderr,
        )
        return 2
    try:
        host_path = Path(args.host)
        if not host_path.exists():
            raise ValueError(f"host model file not found: {host_path}")
        if bool(args.taxonomy) == bool(args.model_dir):
            raise ValueError("provide exactly one of --taxonomy or --model-dir")
        if args.taxonomy:
            taxonomy_path = Path(args.taxonomy)
            if not taxonomy_path.exists():
                raise ValueError(f"taxonomy file not found: {taxonomy_path}")
            taxonomy = pd.read_csv(taxonomy_path)
        else:
            taxonomy = taxonomy_from_model_dir(args.model_dir, recursive=args.recursive)
        missing_cols = {"id", "file"} - set(taxonomy.columns)
        if missing_cols:
            raise ValueError(f"taxonomy missing required columns: {sorted(missing_cols)}")
        ids = [str(x) for x in taxonomy["id"]]
        candidates = candidate_combinations(ids, args.min_size, args.max_size)
        if not candidates:
            raise ValueError("no candidate combinations generated")
        host_model = read_sbml_model(str(host_path))
        _apply_host_objective(host_model, args.host_objective)
        microbe_medium = load_medium(args.microbe_medium) if args.microbe_medium else None
        host_medium = load_medium(args.host_medium).uptake if args.host_medium else None
        exclude = set() if args.include_currency_metabolites else {"h", "h2o", "co2"}
        if args.exclude_metabolites:
            exclude.update(
                _parse_csv_strings(args.exclude_metabolites, flag="--exclude-metabolites")
            )
        rows: list[dict[str, Any]] = []
        for members in candidates:
            sub = taxonomy[taxonomy["id"].astype(str).isin(members)].copy()
            try:
                result = run_bigg_host_microbe(
                    sub,
                    host_model.copy(),
                    solver=args.solver,
                    tradeoff_f=args.tradeoff_f,
                    microbe_medium=microbe_medium,
                    host_medium=host_medium,
                    exchange_suffix=args.exchange_suffix,
                    exclude_metabolites=exclude,
                    close_unlisted_host_uptake=not args.keep_host_uptake,
                )
                host_objective = float(result.host_result.biomass)
                target_transfer = float(result.impact.microbe_to_host.get(args.target, 0.0))
                if args.metric == "objective_value":
                    score = host_objective
                elif args.metric == "target_transfer":
                    score = target_transfer
                else:
                    score = (
                        args.host_weight * host_objective
                        + args.target_weight * target_transfer
                    )
                rows.append({
                    "members": members,
                    "evaluation_status": "ok",
                    "score": score,
                    "host_objective_value": host_objective,
                    "host_status": result.host_result.status,
                    "host_viable": result.host_result.viable,
                    "target": args.target,
                    "target_transfer": target_transfer,
                    "community_growth": float(result.community_growth),
                    "community_status": result.community_status,
                    "warnings": result.warnings,
                    "diagnostic": None,
                })
            except Exception as e:
                rows.append({
                    "members": members,
                    "evaluation_status": "failed",
                    "score": 0.0,
                    "host_objective_value": 0.0,
                    "host_status": "failed",
                    "host_viable": False,
                    "target": args.target,
                    "target_transfer": 0.0,
                    "community_growth": 0.0,
                    "community_status": "failed",
                    "warnings": [],
                    "diagnostic": str(e),
                })
        rows.sort(key=lambda row: (
            row["evaluation_status"] != "ok",
            -float(row["score"]),
            tuple(row["members"]),
        ))
        out = Path(args.out)
        _write_host_search_bigg_outputs(
            rows[: args.top_k],
            out,
            target=args.target,
            metric=args.metric,
            n_candidates_total=len(candidates),
            n_candidates_evaluated=len(candidates),
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"failed to write host-search outputs: {e}", file=sys.stderr)
        return 2
    print(f"host-search BiGG complete ({args.metric}, target={args.target}) -> {out}")
    if rows:
        best = rows[0]
        print(
            f"  best: {'+'.join(best['members'])} score={float(best['score']):.4g} "
            f"host_objective={float(best['host_objective_value']):.4g} "
            f"target_transfer={float(best['target_transfer']):.4g}"
        )
    return 0


def _select_ko_targets(
    model: Any,
    *,
    ko_level: str,
    explicit: list[str] | None,
    max_n: int,
    selection: str,
    seed: int,
) -> tuple[list[str], int, str]:
    """Resolve knockout-target ids for one member.

    Returns ``(selected_ids, total_available, method_label)``. Explicit ids are used verbatim
    (method ``explicit``). Otherwise all gene/reaction ids are enumerated, optionally sampled
    (``selection="random"``, deterministic by ``seed``) or kept in id order (``"id"``), then
    capped to ``max_n`` (0 = no cap). Truncation is surfaced by the caller as an explicit
    warning so a screen never silently inspects an arbitrary subset.
    """
    if explicit is not None:
        return list(explicit), len(explicit), "explicit"
    if ko_level == "reaction":
        # Auto-enumeration skips exchange reactions (closing an exchange is not a metabolic
        # perturbation) and the objective/biomass reaction (its KO trivially zeroes growth and
        # would dominate the ranking with a non-informative result). Use --reactions to target
        # them explicitly.
        all_ids = sorted(
            str(r.id)
            for r in model.reactions
            if not str(r.id).startswith("EX_") and r.objective_coefficient == 0
        )
    else:
        all_ids = sorted(str(g.id) for g in model.genes)
    total = len(all_ids)
    if selection == "random":
        pool = list(all_ids)
        random.Random(seed).shuffle(pool)
        chosen = pool if max_n <= 0 else pool[:max_n]
        return sorted(chosen), total, f"random(seed={seed})"
    chosen = all_ids if max_n <= 0 else all_ids[:max_n]
    return chosen, total, "id"


def _evaluate_ko_target(
    item: tuple[int, str, str],
    *,
    ko_level: str,
    base_models: dict[str, Any],
    sub_taxonomy: Any,
    config: Any,
    baseline: Any,
    tmp_dir: Path,
    write_sbml_model: Any,
    search_model_pool: Any,
    engine_factory: Callable[[], Any],
) -> dict[str, Any]:
    """Knock out one gene/reaction in one member, re-rank the fixed consortium, return a row.

    Safe to map across a thread pool: reads (never mutates) ``base_models``, writes a uniquely
    named SBML into ``tmp_dir``, and builds a fresh engine per call.
    """
    index, member_id, ko_id = item
    try:
        ko_model = base_models[member_id].copy()
        if ko_level == "reaction":
            ko_model.reactions.get_by_id(ko_id).knock_out()
        else:
            ko_model.genes.get_by_id(ko_id).knock_out()
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in ko_id)
        ko_file = tmp_dir / f"{member_id}_{index}_{safe}.xml"
        write_sbml_model(ko_model, str(ko_file))
        ko_taxonomy = sub_taxonomy.copy()
        ko_taxonomy.loc[ko_taxonomy["id"].astype(str) == member_id, "file"] = str(ko_file)
        rank = search_model_pool(engine_factory(), ko_taxonomy, config).ranks[0]
        return {
            "gene": ko_id,
            "member": member_id,
            "evaluation_status": "ok",
            "score": rank.score,
            "score_delta": rank.score - baseline.score,
            "target_flux": rank.target_flux,
            "target_flux_delta": rank.target_flux - baseline.target_flux,
            "community_growth": rank.community_growth,
            "community_growth_delta": rank.community_growth - baseline.community_growth,
            "status": rank.status,
            "diagnostic": rank.diagnostic,
        }
    except Exception as e:
        return {
            "gene": ko_id,
            "member": member_id,
            "evaluation_status": "failed",
            "score": 0.0,
            "score_delta": -baseline.score,
            "target_flux": 0.0,
            "target_flux_delta": -baseline.target_flux,
            "community_growth": 0.0,
            "community_growth_delta": -baseline.community_growth,
            "status": "failed",
            "diagnostic": str(e),
        }


def _map_ko_evaluations(
    items: list[Any],
    evaluate: Callable[[Any], dict[str, Any]],
    *,
    jobs: int,
) -> list[dict[str, Any]]:
    """Map KO evaluations serially (``jobs<=1``) or via a thread pool, preserving input order.

    Solver work releases the GIL, so a thread pool can overlap MICOM solves; ``executor.map``
    keeps input order so ranking is independent of ``--jobs``.
    """
    if jobs <= 1:
        return [evaluate(item) for item in items]
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=jobs) as executor:
        return list(executor.map(evaluate, items))


def _ko_sort_key(row: dict[str, Any]) -> tuple[int, int, float, str]:
    """Deterministic, NaN-safe ranking key.

    ok before failed, finite delta before non-finite, larger ``score_delta`` first, then
    ``member:gene`` tiebreak so a baseline-infeasible run (all-NaN deltas) stays stable.
    """
    delta = float(row["score_delta"])
    finite = math.isfinite(delta)
    return (
        0 if row["evaluation_status"] == "ok" else 1,
        0 if finite else 1,
        -delta if finite else 0.0,
        f"{row['member']}:{row['gene']}",
    )


def _cmd_gene_ko_search(args: argparse.Namespace) -> int:
    """Rank single gene/reaction knockouts in one or more members for a selected consortium."""
    try:
        import pandas as pd
        from cobra.io import read_sbml_model, write_sbml_model

        from cmig.core.engine import MicomEngine
        from cmig.core.model_pool import taxonomy_from_model_dir
        from cmig.core.search import Direction
        from cmig.core.search_product import SearchConfig, search_model_pool
    except ImportError:
        print("gene-ko-search requires the engine stack: uv sync --extra engine", file=sys.stderr)
        return 2
    try:
        if args.jobs < 1:
            raise ValueError("--jobs must be >= 1")
        if bool(args.taxonomy) == bool(args.model_dir):
            raise ValueError("provide exactly one of --taxonomy or --model-dir")
        if args.taxonomy:
            taxonomy_path = Path(args.taxonomy)
            if not taxonomy_path.exists():
                raise ValueError(f"taxonomy file not found: {taxonomy_path}")
            taxonomy = pd.read_csv(taxonomy_path)
        else:
            taxonomy = taxonomy_from_model_dir(args.model_dir, recursive=args.recursive)
        missing_cols = {"id", "file"} - set(taxonomy.columns)
        if missing_cols:
            raise ValueError(f"taxonomy missing required columns: {sorted(missing_cols)}")
        members = tuple(_parse_csv_strings(args.members, flag="--members"))
        if args.member and args.member not in members:
            raise ValueError("--member must be one of --members")
        member_files = {
            str(row["id"]): str(row["file"])
            for row in taxonomy.to_dict("records")
        }
        missing_members = [member for member in members if member not in member_files]
        if missing_members:
            raise ValueError(f"--members not found in taxonomy: {missing_members}")
        target_members = (args.member,) if args.member else members

        ko_level = args.ko_level
        if ko_level == "reaction" and args.genes:
            raise ValueError("--genes pairs with --ko-level gene; use --reactions for reactions")
        if ko_level == "gene" and args.reactions:
            raise ValueError("--reactions pairs with --ko-level reaction; use --genes for genes")
        explicit_raw = args.reactions if ko_level == "reaction" else args.genes
        explicit_flag = "--reactions" if ko_level == "reaction" else "--genes"
        if explicit_raw and len(target_members) != 1:
            raise ValueError(f"{explicit_flag} requires --member so ids are unambiguous")
        explicit = _parse_csv_strings(explicit_raw, flag=explicit_flag) if explicit_raw else None

        member_models: dict[str, Any] = {}
        member_target_sets: dict[str, list[str]] = {}
        member_totals: dict[str, int] = {}
        member_methods: dict[str, str] = {}
        for member_id in target_members:
            model = read_sbml_model(member_files[member_id])
            member_models[member_id] = model
            selected, total, method = _select_ko_targets(
                model,
                ko_level=ko_level,
                explicit=explicit,
                max_n=args.max_genes,
                selection=args.gene_selection,
                seed=args.seed,
            )
            if not selected:
                raise ValueError(f"no {ko_level}s selected for member {member_id}")
            member_target_sets[member_id] = selected
            member_totals[member_id] = total
            member_methods[member_id] = method

        sub = taxonomy[taxonomy["id"].astype(str).isin(members)].copy()
        config = SearchConfig(
            target=args.target,
            direction=Direction(args.direction),
            min_size=len(members),
            max_size=len(members),
            strategy="exhaustive",
            top_k=1,
            growth_fraction=args.growth_fraction,
            solver=args.solver,
        )
        baseline = search_model_pool(MicomEngine(), sub, config).ranks[0]

        warnings: list[str] = []
        for member_id in target_members:
            selected = member_target_sets[member_id]
            total = member_totals[member_id]
            method = member_methods[member_id]
            if total > len(selected):
                warnings.append(
                    f"{member_id}: evaluated {len(selected)} of {total} {ko_level}s "
                    f"(selection={method}); raise --max-genes (0=all) for full coverage"
                )
            elif method.startswith("random"):
                warnings.append(
                    f"{member_id}: {ko_level} set sampled deterministically ({method})"
                )

        pairs = [
            (member_id, ko_id)
            for member_id in target_members
            for ko_id in member_target_sets[member_id]
        ]
        items: list[tuple[int, str, str]] = [
            (index, member_id, ko_id) for index, (member_id, ko_id) in enumerate(pairs)
        ]
        with tempfile.TemporaryDirectory(prefix="cmig-gene-ko-") as tmp:
            tmp_dir = Path(tmp)

            def _evaluate(item: tuple[int, str, str]) -> dict[str, Any]:
                return _evaluate_ko_target(
                    item,
                    ko_level=ko_level,
                    base_models=member_models,
                    sub_taxonomy=sub,
                    config=config,
                    baseline=baseline,
                    tmp_dir=tmp_dir,
                    write_sbml_model=write_sbml_model,
                    search_model_pool=search_model_pool,
                    engine_factory=MicomEngine,
                )

            rows = _map_ko_evaluations(items, _evaluate, jobs=args.jobs)
        rows.sort(key=_ko_sort_key)
        out = Path(args.out)
        _write_gene_ko_search_outputs(
            rows[: args.top_k],
            out,
            baseline=baseline,
            members=members,
            target=args.target,
            member=args.member,
            n_genes_evaluated=len(rows),
            n_genes_total=sum(member_totals.values()),
            ko_level=ko_level,
            gene_selection=args.gene_selection,
            seed=args.seed,
            direction=args.direction,
            warnings=warnings,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"failed to write gene KO outputs: {e}", file=sys.stderr)
        return 2
    member_label = args.member if args.member else "all members"
    print(
        f"gene KO search complete (level={ko_level}, member={member_label}, "
        f"target={args.target}) -> {out}"
    )
    for warning in warnings:
        print(f"  warning: {warning}")
    if rows:
        best = rows[0]
        print(
            f"  best: {best['member']}:{best['gene']} "
            f"delta={float(best['score_delta']):.4g} score={float(best['score']):.4g}"
        )
    return 0


def _cmd_strain_growth(args: argparse.Namespace) -> int:
    """Estimate per-strain growth alone and inside the full community."""
    try:
        import pandas as pd
        from cobra.io import read_sbml_model

        from cmig.core.engine import MicomEngine
        from cmig.core.medium_spec import apply_medium_checked, load_medium
        from cmig.core.model_pool import taxonomy_from_model_dir
        from cmig.core.single_model import solve_single_model
    except ImportError:
        print("strain-growth requires the engine stack: uv sync --extra engine", file=sys.stderr)
        return 2
    try:
        taxonomy = _load_pool_taxonomy(
            taxonomy_path=args.taxonomy,
            model_dir=args.model_dir,
            recursive=args.recursive,
            pd=pd,
            taxonomy_from_model_dir=taxonomy_from_model_dir,
        )
        medium_spec = load_medium(args.medium) if args.medium else None
        engine = MicomEngine()
        community = engine.build_community(taxonomy, cmig_solver=args.solver)
        if medium_spec is not None:
            apply_medium_checked(community, medium_spec, strict=not args.allow_unknown_medium)
        community_result = engine.cooperative_tradeoff(
            community, args.tradeoff_f, cmig_solver=args.solver
        )
        rows: list[dict[str, Any]] = []
        for record in taxonomy.to_dict("records"):
            member_id = str(record["id"])
            model_file = str(record["file"])
            single_growth: float | None = None
            single_status = "not_run"
            single_diag = None
            try:
                model = read_sbml_model(model_file)
                single = solve_single_model(model, solver=args.solver)
                single_growth = float(single.objective)
                single_status = single.status
                single_diag = single.diagnostic
            except Exception as e:
                single_status = "failed"
                single_diag = str(e)
            rows.append({
                "member": member_id,
                "file": model_file,
                "abundance": community_result.abundances.get(member_id),
                "single_growth": single_growth,
                "single_status": single_status,
                "community_member_growth": community_result.member_growth.get(member_id),
                "community_status": community_result.status,
                "community_growth": community_result.objective,
                "diagnostic": single_diag,
            })
        out = Path(args.out)
        _write_strain_growth_outputs(
            rows,
            out,
            solver=args.solver,
            tradeoff_f=args.tradeoff_f,
            community_growth=community_result.objective,
            community_status=community_result.status,
            community_diagnostic=community_result.diagnostic,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"failed to write strain-growth outputs: {e}", file=sys.stderr)
        return 2
    print(f"strain-growth complete ({len(rows)} members) -> {out}")
    return 0


def _cmd_abundance_impact(args: argparse.Namespace) -> int:
    """Sweep one strain's abundance and report community/member/target impacts."""
    try:
        import pandas as pd

        from cmig.core.engine import MicomEngine
        from cmig.core.medium_spec import apply_medium_checked, load_medium
        from cmig.core.model_pool import taxonomy_from_model_dir
    except ImportError:
        print("abundance-impact requires the engine stack: uv sync --extra engine", file=sys.stderr)
        return 2
    try:
        taxonomy = _load_pool_taxonomy(
            taxonomy_path=args.taxonomy,
            model_dir=args.model_dir,
            recursive=args.recursive,
            pd=pd,
            taxonomy_from_model_dir=taxonomy_from_model_dir,
        )
        ids = [str(x) for x in taxonomy["id"]]
        if args.member not in ids:
            raise ValueError(f"--member not found in taxonomy: {args.member}")
        fractions = _parse_csv_floats(args.fractions, flag="--fractions")
        if len(ids) > 1 and any(v <= 0.0 or v >= 1.0 for v in fractions):
            raise ValueError("--fractions must satisfy 0<f<1 for multi-member communities")
        medium_spec = load_medium(args.medium) if args.medium else None
        engine = MicomEngine()
        rows: list[dict[str, Any]] = []
        member_growth_rows: list[dict[str, Any]] = []
        for fraction in fractions:
            variant = _taxonomy_with_member_fraction(taxonomy, args.member, fraction)
            community = engine.build_community(variant, cmig_solver=args.solver)
            if medium_spec is not None:
                apply_medium_checked(community, medium_spec, strict=not args.allow_unknown_medium)
            try:
                result = engine.cooperative_tradeoff(
                    community, args.tradeoff_f, cmig_solver=args.solver
                )
                target_member_exchange = float(
                    result.member_exchange.get(args.member, {}).get(args.target, 0.0)
                )
                total_member_abs = sum(
                    abs(float(exchanges.get(args.target, 0.0)))
                    for exchanges in result.member_exchange.values()
                )
                influence_share = (
                    abs(target_member_exchange) / total_member_abs
                    if total_member_abs > 1e-12 else 0.0
                )
                rows.append({
                    "target_member": args.member,
                    "target_abundance": fraction,
                    "target": args.target,
                    "community_growth": result.objective,
                    "target_member_growth": result.member_growth.get(args.member),
                    "target_member_exchange": target_member_exchange,
                    "community_target_exchange": float(
                        result.external_exchange.get(args.target, 0.0)
                    ),
                    "target_influence_share": influence_share,
                    "status": result.status,
                    "diagnostic": result.diagnostic,
                })
                for member_id in ids:
                    member_growth_rows.append({
                        "target_abundance": fraction,
                        "member": member_id,
                        "abundance": result.abundances.get(member_id),
                        "growth": result.member_growth.get(member_id),
                    })
            except Exception as e:
                rows.append({
                    "target_member": args.member,
                    "target_abundance": fraction,
                    "target": args.target,
                    "community_growth": 0.0,
                    "target_member_growth": None,
                    "target_member_exchange": 0.0,
                    "community_target_exchange": 0.0,
                    "target_influence_share": 0.0,
                    "status": "failed",
                    "diagnostic": str(e),
                })
        out = Path(args.out)
        _write_abundance_impact_outputs(
            rows,
            member_growth_rows,
            out,
            target_member=args.member,
            target=args.target,
            solver=args.solver,
            tradeoff_f=args.tradeoff_f,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"failed to write abundance-impact outputs: {e}", file=sys.stderr)
        return 2
    print(f"abundance-impact complete ({args.member}, target={args.target}) -> {out}")
    return 0


def _write_gene_ko_search_outputs(
    rows: list[dict[str, Any]],
    out: Path,
    *,
    baseline: Any,
    members: tuple[str, ...],
    target: str,
    member: str | None,
    n_genes_evaluated: int,
    n_genes_total: int,
    ko_level: str,
    gene_selection: str,
    seed: int,
    direction: str,
    warnings: list[str],
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "gene_ko_rankings.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "rank",
                "member",
                "gene",
                "score",
                "score_delta",
                "target_flux",
                "target_flux_delta",
                "community_growth",
                "community_growth_delta",
                "status",
                "evaluation_status",
                "diagnostic",
            ],
        )
        writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            writer.writerow({
                "rank": rank,
                "member": row["member"],
                "gene": row["gene"],
                "score": _finite_csv(float(row["score"])),
                "score_delta": _finite_csv(float(row["score_delta"])),
                "target_flux": _finite_csv(float(row["target_flux"])),
                "target_flux_delta": _finite_csv(float(row["target_flux_delta"])),
                "community_growth": _finite_csv(float(row["community_growth"])),
                "community_growth_delta": _finite_csv(float(row["community_growth_delta"])),
                "status": row["status"],
                "evaluation_status": row["evaluation_status"],
                "diagnostic": row["diagnostic"] or "",
            })
    payload = {
        "status": "ok",
        "members": list(members),
        "member": member,
        "screening_scope": "single_member" if member else "all_members",
        "target": target,
        "baseline": {
            "score": _finite_or_none(float(baseline.score)),
            "target_flux": _finite_or_none(float(baseline.target_flux)),
            "community_growth": _finite_or_none(float(baseline.community_growth)),
            "status": baseline.status,
            "diagnostic": baseline.diagnostic,
        },
        "n_genes_evaluated": n_genes_evaluated,
        "n_genes_total": n_genes_total,
        "ko_level": ko_level,
        "gene_selection": gene_selection,
        "seed": seed,
        "direction": direction,
        "warnings": list(warnings),
        "top_ranked": [
            {
                "rank": rank,
                "member": row["member"],
                "gene": row["gene"],
                "score": _finite_or_none(float(row["score"])),
                "score_delta": _finite_or_none(float(row["score_delta"])),
                "target_flux": _finite_or_none(float(row["target_flux"])),
                "target_flux_delta": _finite_or_none(float(row["target_flux_delta"])),
                "community_growth": _finite_or_none(float(row["community_growth"])),
                "community_growth_delta": _finite_or_none(
                    float(row["community_growth_delta"])
                ),
                "status": row["status"],
                "evaluation_status": row["evaluation_status"],
                "diagnostic": row["diagnostic"],
            }
            for rank, row in enumerate(rows, start=1)
        ],
        "artifacts": [
            "gene_ko_rankings.csv",
            "gene_ko_summary.json",
            "gene_ko_plot.svg",
            "gene_ko_plot.tiff",
        ],
    }
    (out / "gene_ko_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )
    _write_gene_ko_figures(
        rows,
        out,
        target=target,
        ko_level=ko_level,
        direction=direction,
        baseline=baseline,
        n_evaluated=n_genes_evaluated,
        n_total=n_genes_total,
        selection=gene_selection,
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return _finite_or_none(number)


def _csv_float_or_blank(value: Any) -> str:
    number = _optional_float(value)
    return "" if number is None else _finite_csv(number)


def _write_strain_growth_outputs(
    rows: list[dict[str, Any]],
    out: Path,
    *,
    solver: str,
    tradeoff_f: float,
    community_growth: float,
    community_status: str,
    community_diagnostic: str | None,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "strain_growth.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "member",
                "file",
                "abundance",
                "single_growth",
                "single_status",
                "community_member_growth",
                "community_status",
                "community_growth",
                "diagnostic",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "member": row["member"],
                "file": row["file"],
                "abundance": _csv_float_or_blank(row.get("abundance")),
                "single_growth": _csv_float_or_blank(row.get("single_growth")),
                "single_status": row["single_status"],
                "community_member_growth": _csv_float_or_blank(
                    row.get("community_member_growth")
                ),
                "community_status": row["community_status"],
                "community_growth": _csv_float_or_blank(row.get("community_growth")),
                "diagnostic": row.get("diagnostic") or "",
            })
    payload = {
        "status": community_status,
        "diagnostic": community_diagnostic,
        "solver": solver,
        "tradeoff_f": tradeoff_f,
        "community_growth": _finite_or_none(float(community_growth)),
        "members": [
            {
                "member": row["member"],
                "file": row["file"],
                "abundance": _optional_float(row.get("abundance")),
                "single_growth": _optional_float(row.get("single_growth")),
                "single_status": row["single_status"],
                "community_member_growth": _optional_float(
                    row.get("community_member_growth")
                ),
                "community_status": row["community_status"],
                "community_growth": _optional_float(row.get("community_growth")),
                "diagnostic": row.get("diagnostic"),
            }
            for row in rows
        ],
        "artifacts": [
            "strain_growth.csv",
            "strain_growth_summary.json",
            "strain_growth_plot.svg",
            "strain_growth_plot.tiff",
        ],
    }
    (out / "strain_growth_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )
    _write_strain_growth_figures(rows, out)


def _write_abundance_impact_outputs(
    rows: list[dict[str, Any]],
    member_growth_rows: list[dict[str, Any]],
    out: Path,
    *,
    target_member: str,
    target: str,
    solver: str,
    tradeoff_f: float,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "abundance_impact.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "target_member",
                "target_abundance",
                "target",
                "community_growth",
                "target_member_growth",
                "target_member_exchange",
                "community_target_exchange",
                "target_influence_share",
                "status",
                "diagnostic",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "target_member": row["target_member"],
                "target_abundance": _csv_float_or_blank(row.get("target_abundance")),
                "target": row["target"],
                "community_growth": _csv_float_or_blank(row.get("community_growth")),
                "target_member_growth": _csv_float_or_blank(
                    row.get("target_member_growth")
                ),
                "target_member_exchange": _csv_float_or_blank(
                    row.get("target_member_exchange")
                ),
                "community_target_exchange": _csv_float_or_blank(
                    row.get("community_target_exchange")
                ),
                "target_influence_share": _csv_float_or_blank(
                    row.get("target_influence_share")
                ),
                "status": row["status"],
                "diagnostic": row.get("diagnostic") or "",
            })
    with open(out / "member_growth_by_abundance.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["target_abundance", "member", "abundance", "growth"],
        )
        writer.writeheader()
        for row in member_growth_rows:
            writer.writerow({
                "target_abundance": _csv_float_or_blank(row.get("target_abundance")),
                "member": row["member"],
                "abundance": _csv_float_or_blank(row.get("abundance")),
                "growth": _csv_float_or_blank(row.get("growth")),
            })
    payload = {
        "status": "ok" if any(row["status"] == "optimal" for row in rows) else "failed",
        "target_member": target_member,
        "target": target,
        "solver": solver,
        "tradeoff_f": tradeoff_f,
        "rows": [
            {
                key: _optional_float(value) if key not in {"target_member", "target", "status",
                                                           "diagnostic"} else value
                for key, value in row.items()
            }
            for row in rows
        ],
        "member_growth_rows": [
            {
                "target_abundance": _optional_float(row.get("target_abundance")),
                "member": row["member"],
                "abundance": _optional_float(row.get("abundance")),
                "growth": _optional_float(row.get("growth")),
            }
            for row in member_growth_rows
        ],
        "artifacts": [
            "abundance_impact.csv",
            "member_growth_by_abundance.csv",
            "abundance_impact_summary.json",
            "abundance_impact_plot.svg",
            "abundance_impact_plot.tiff",
        ],
    }
    (out / "abundance_impact_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )
    _write_abundance_impact_figures(rows, out, target_member=target_member, target=target)


def _write_host_search_bigg_outputs(
    rows: list[dict[str, Any]],
    out: Path,
    *,
    target: str,
    metric: str,
    n_candidates_total: int,
    n_candidates_evaluated: int,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "host_search_rankings.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "rank",
                "members",
                "score",
                "host_objective_value",
                "host_status",
                "host_viable",
                "target",
                "target_transfer",
                "community_growth",
                "community_status",
                "warnings",
                "evaluation_status",
                "diagnostic",
            ],
        )
        writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            writer.writerow({
                "rank": rank,
                "members": "+".join(row["members"]),
                "score": _finite_csv(float(row["score"])),
                "host_objective_value": _finite_csv(float(row["host_objective_value"])),
                "host_status": row["host_status"],
                "host_viable": row["host_viable"],
                "target": row["target"],
                "target_transfer": _finite_csv(float(row["target_transfer"])),
                "community_growth": _finite_csv(float(row["community_growth"])),
                "community_status": row["community_status"],
                "warnings": ";".join(str(x) for x in row["warnings"]),
                "evaluation_status": row["evaluation_status"],
                "diagnostic": row["diagnostic"] or "",
            })
    payload = {
        "status": "ok",
        "metric": metric,
        "target": target,
        "n_candidates_total": n_candidates_total,
        "n_candidates_evaluated": n_candidates_evaluated,
        "top_ranked": [
            {
                "rank": rank,
                "members": list(row["members"]),
                "score": _finite_or_none(float(row["score"])),
                "host_objective_value": _finite_or_none(float(row["host_objective_value"])),
                "host_status": row["host_status"],
                "host_viable": row["host_viable"],
                "target": row["target"],
                "target_transfer": _finite_or_none(float(row["target_transfer"])),
                "community_growth": _finite_or_none(float(row["community_growth"])),
                "community_status": row["community_status"],
                "warnings": row["warnings"],
                "evaluation_status": row["evaluation_status"],
                "diagnostic": row["diagnostic"],
            }
            for rank, row in enumerate(rows, start=1)
        ],
        "artifacts": [
            "host_search_rankings.csv",
            "host_search_summary.json",
            "host_search_plot.svg",
            "host_search_plot.tiff",
        ],
    }
    (out / "host_search_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )
    _write_host_search_figures(rows, out, target=target, metric=metric)


def _write_host_microbe_bigg_outputs(result: Any, taxonomy: Any, out: Path) -> None:
    from cmig.core.interaction_figures import (
        contribution_rows,
        host_microbe_interaction_rows,
        matrix_rows,
        render_interaction_figures,
        write_interaction_artifacts,
    )

    out.mkdir(parents=True, exist_ok=True)
    taxonomy.to_csv(out / "microbe_taxonomy.csv", index=False)
    with open(out / "microbial_secretion.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["metabolite", "flux", "host_exchange", "matched"])
        writer.writeheader()
        for metabolite, flux in sorted(result.microbial_secretion.items()):
            exchange = result.matched_exchanges.get(metabolite, "")
            writer.writerow({
                "metabolite": metabolite,
                "flux": _finite_csv(float(flux)),
                "host_exchange": exchange,
                "matched": bool(exchange),
            })
    with open(out / "host_uptake.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["metabolite", "uptake_flux"])
        writer.writeheader()
        for metabolite, flux in sorted(result.host_result.lumen_uptake.items()):
            writer.writerow({"metabolite": metabolite, "uptake_flux": _finite_csv(float(flux))})
    with open(out / "microbe_to_host.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["metabolite", "transfer_flux"])
        writer.writeheader()
        for metabolite, flux in sorted(result.impact.microbe_to_host.items()):
            writer.writerow({"metabolite": metabolite, "transfer_flux": _finite_csv(float(flux))})
    edge_rows = host_microbe_interaction_rows(
        microbial_secretion=result.microbial_secretion,
        host_uptake=result.host_result.lumen_uptake,
        microbe_to_host=result.impact.microbe_to_host,
        member_secretion=result.member_secretion,
    )
    contributions = contribution_rows(result.member_secretion, result.impact.microbe_to_host)
    matrix = matrix_rows(edge_rows)
    figure_manifest = {
        "figure_schema_version": "1.0",
        "source": "host-microbe-bigg",
        "figure_modes": ["network", "circle", "heatmap", "bubble", "contribution"],
        "edge_width": "normalized_flux",
        "node_size": "aggregate flux",
        "hidden_by_default": ["h", "h2o", "co2"],
        "artifacts": [
            "interaction_edges.csv",
            "interaction_matrix.csv",
            "member_contribution.csv",
            "figure_manifest.json",
            "interaction_circle.svg",
            "interaction_circle.tiff",
            "interaction_heatmap.svg",
            "interaction_heatmap.tiff",
            "interaction_bubble.svg",
            "interaction_bubble.tiff",
            "member_contribution.svg",
            "member_contribution.tiff",
        ],
    }
    interaction_artifacts = write_interaction_artifacts(
        out,
        edge_rows=edge_rows,
        matrix=matrix,
        contributions=contributions,
        figure_manifest=figure_manifest,
    )
    figure_artifacts = render_interaction_figures(out)
    payload = {
        "status": "ok",
        "coupling": "bigg_direct_exchange",
        "community": {
            "status": result.community_status,
            "growth": _finite_or_none(float(result.community_growth)),
            "n_members": int(len(taxonomy)),
        },
        "host": {
            "status": result.host_result.status,
            "viable": result.host_result.viable,
            "objective_value": _finite_or_none(float(result.host_result.biomass)),
            "diagnostic": result.host_result.diagnostic,
            "lumen_uptake": result.host_result.lumen_uptake,
        },
        "matched_exchanges": result.matched_exchanges,
        "unmatched_metabolites": result.unmatched_metabolites,
        "microbial_secretion": result.microbial_secretion,
        "member_secretion": result.member_secretion,
        "microbe_to_host": result.impact.microbe_to_host,
        "unused_secretion": result.impact.unused_secretion,
        "warnings": result.warnings,
        "artifacts": [
            "microbe_taxonomy.csv",
            "microbial_secretion.csv",
            "host_uptake.csv",
            "microbe_to_host.csv",
            "host_microbe_bigg_summary.json",
        ] + interaction_artifacts + figure_artifacts,
    }
    (out / "host_microbe_bigg_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )


def _cmd_dfba_fixture(args: argparse.Namespace) -> int:
    """e_coli_core glucose-batch dFBA fixture → optional timecourse.parquet."""
    try:
        import os

        import cobra
        import micom

        from cmig.core.dfba import DfbaConfig, build_timecourse, simulate_dfba, write_timecourse
    except ImportError:
        print("dfba-fixture 는 engine stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    model_path = os.path.join(os.path.dirname(micom.__file__), "data", "e_coli_core.xml.gz")
    model = cobra.io.read_sbml_model(model_path)
    result = simulate_dfba(
        model,
        DfbaConfig(
            t_end=args.t_end,
            dt=args.dt,
            initial_biomass=args.initial_biomass,
            initial_concentrations={"EX_glc__D_e": args.glucose},
        ),
        solver=args.solver,
    )
    table = build_timecourse(result)
    if args.out is not None:
        out = Path(args.out)
        write_timecourse(table, out / "timecourse.parquet")
    final = result.timecourse[-1]
    payload = {
        "status": result.status,
        "n_timepoints": len(result.timecourse),
        "final_t": final.t,
        "final_biomass": final.biomass,
        "final_concentrations": final.concentrations,
        "diagnostic": result.diagnostic,
    }
    _write_json_or_print(payload, args.out, "dfba_summary.json")
    return 0


def _cmd_dfba(args: argparse.Namespace) -> int:
    """Run well-mixed dFBA on a user-supplied SBML model."""
    try:
        import cobra

        from cmig.core.dfba import DfbaConfig, simulate_dfba
    except ImportError:
        print("dfba requires the engine stack: uv sync --extra engine", file=sys.stderr)
        return 2
    model_path = Path(args.model)
    if not model_path.exists():
        print(f"model file not found: {model_path}", file=sys.stderr)
        return 2
    try:
        model = cobra.io.read_sbml_model(str(model_path))
        concentrations = _dfba_initial_concentrations(
            model,
            args.initial_concentrations,
        )
        vmax = (
            _parse_key_float_map(args.vmax, flag="--vmax")
            if args.vmax is not None else None
        )
        _require_model_exchanges(model, concentrations, flag="--initial")
        if vmax is not None:
            _require_model_exchanges(model, vmax, flag="--vmax")
        result = simulate_dfba(
            model,
            DfbaConfig(
                t_end=args.t_end,
                dt=args.dt,
                initial_biomass=args.initial_biomass,
                initial_concentrations=concentrations,
                km=args.km,
                vmax=vmax,
                min_dt=args.min_dt,
                growth_floor=args.growth_floor,
            ),
            solver=args.solver,
        )
    except (KeyError, ValueError, OSError) as e:
        print(f"dfba input error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"dfba failed: {e}", file=sys.stderr)
        return 1
    _write_dfba_outputs(
        result,
        Path(args.out),
        model_path=model_path,
        solver=args.solver,
        config={
            "t_end": args.t_end,
            "dt": args.dt,
            "initial_biomass": args.initial_biomass,
            "initial_concentrations": concentrations,
            "km": args.km,
            "vmax": vmax,
            "min_dt": args.min_dt,
            "growth_floor": args.growth_floor,
            "default_initial_preset": args.initial_concentrations is None,
        },
    )
    print(f"dfba complete ({result.status}) -> {args.out}")
    return 0


def _cmd_spatial_preview(args: argparse.Namespace) -> int:
    """Run a lightweight 2D medium diffusion/source-sink preview."""
    from cmig.core.spatial import SpatialPreviewConfig, run_spatial_preview

    try:
        config = SpatialPreviewConfig(
            width=args.width,
            height=args.height,
            steps=args.steps,
            dt=args.dt,
            diffusion=args.diffusion,
            initial_value=args.initial_value,
            source_edge=args.source_edge,
            source_value=args.source_value,
            sink_edge=args.sink_edge,
            sink_value=args.sink_value,
            store_every=args.store_every,
        )
        result = run_spatial_preview(config)
    except ValueError as e:
        print(f"spatial-preview input error: {e}", file=sys.stderr)
        return 2
    _write_spatial_preview_outputs(
        result, Path(args.out), metabolite=args.metabolite, config=config
    )
    print(f"spatial-preview complete ({args.metabolite}) -> {args.out}")
    return 0


def _cmd_search_fixture(args: argparse.Namespace) -> int:
    """3-member MICOM fixture target-max search smoke."""
    try:
        from cmig.core.engine import MicomEngine
        from cmig.core.search import TargetSpec, rank_consortia, target_max_solve
        from cmig.golden_fixture import build_taxonomy
    except ImportError:
        print("search-fixture 는 engine stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    taxonomy = build_taxonomy()
    engine = MicomEngine()
    community = engine.build_community(taxonomy, cmig_solver=args.solver)
    spec = TargetSpec(args.metabolite)
    result = target_max_solve(
        community, spec, growth_fraction=args.growth_fraction, solver=args.solver
    )
    ranked = rank_consortia(
        engine,
        taxonomy,
        spec,
        sizes=(2,),
        growth_fraction=args.growth_fraction,
        solver=args.solver,
        n_max=20,
    )
    payload = {
        "target": result.target,
        "status": result.status,
        "target_flux": result.target_flux,
        "community_growth": result.community_growth,
        "top_ranked": [
            {
                "members": list(r.members),
                "score": r.score,
                "target_flux": r.target_flux,
                "community_growth": r.community_growth,
                "status": r.status,
            }
            for r in ranked[: args.top_k]
        ],
        "diagnostic": result.diagnostic,
    }
    _write_json_or_print(payload, args.out, "search_summary.json")
    return 0


def _cmd_search_advanced_fixture(args: argparse.Namespace) -> int:
    """Fixture-backed advanced search: strategy dispatch + Pareto/GA surface."""
    try:
        import itertools

        from cmig.core.engine import MicomEngine
        from cmig.core.search import TargetSpec, rank_consortia
        from cmig.core.search_advanced import (
            Strategy,
            explain_consortium,
            pareto_frontier,
            select_strategy,
        )
        from cmig.core.search_ga import GAConfig, genetic_search
        from cmig.golden_fixture import build_taxonomy
    except ImportError:
        print(
            "search-advanced-fixture 는 engine stack 필요: uv sync --extra engine",
            file=sys.stderr,
        )
        return 2
    taxonomy: Any = build_taxonomy()
    ids = [str(x) for x in taxonomy["id"]]
    targets = [TargetSpec(m.strip()) for m in args.metabolites.split(",") if m.strip()]
    if not targets:
        print("--metabolites 값이 비어 있음", file=sys.stderr)
        return 2
    combos = [
        tuple(c)
        for k in range(args.min_size, args.max_size + 1)
        for c in itertools.combinations(ids, k)
    ]
    strategy = (
        select_strategy(len(combos))
        if args.strategy == "auto" else
        Strategy(args.strategy)
    )
    engine = MicomEngine()

    def score_members(members: tuple[str, ...], spec: TargetSpec) -> float:
        sub = taxonomy[taxonomy["id"].isin(members)].copy()
        ranked = rank_consortia(
            engine,
            sub,
            spec,
            sizes=(len(members),),
            growth_fraction=args.growth_fraction,
            solver=args.solver,
            n_max=max(20, len(combos)),
        )
        return ranked[0].score if ranked else float("-inf")

    warning = None
    if strategy is Strategy.GA:
        warning = "GA approximate search; not globally optimal"
        ga = genetic_search(
            ids,
            lambda g: score_members(g, targets[0]),
            GAConfig(min_size=args.min_size, max_size=args.max_size, seed=args.seed),
            top_k=args.top_k,
        )
        top = [
            {"members": list(members), "score": _finite_or_none(score)}
            for members, score in ga.top_k
        ]
        payload = {
            "strategy": strategy.value,
            "target": targets[0].metabolite,
            "top_ranked": top,
            "ga": {
                "best_members": list(ga.best_members),
                "best_fitness": _finite_or_none(ga.best_fitness),
                "evaluations": ga.evaluations,
                "generations_run": ga.generations_run,
            },
            "warnings": [warning, ga.warning],
        }
        _write_json_or_print(payload, args.out, "search_advanced_summary.json")
        return 0

    ranked_by_target = []
    for spec in targets:
        ranked = rank_consortia(
            engine,
            taxonomy,
            spec,
            sizes=tuple(range(args.min_size, args.max_size + 1)),
            growth_fraction=args.growth_fraction,
            solver=args.solver,
            n_max=max(20, len(combos)),
        )
        ranked_by_target.append((spec, ranked[: args.top_k]))
    pareto = None
    if len(ranked_by_target) >= 2:
        first = {r.members: r.score for r in ranked_by_target[0][1]}
        second = {r.members: r.score for r in ranked_by_target[1][1]}
        members = sorted(set(first) & set(second))
        points = [(first[m], second[m]) for m in members]
        keep = pareto_frontier(points)
        pareto = [
            {
                "members": list(members[i]),
                targets[0].metabolite: _finite_or_none(points[i][0]),
                targets[1].metabolite: _finite_or_none(points[i][1]),
            }
            for i in keep
        ]
    payload = {
        "strategy": strategy.value,
        "targets": [s.metabolite for s in targets],
        "top_ranked": {
            spec.metabolite: [
                {
                    "members": list(r.members),
                    "score": _finite_or_none(r.score),
                    "target_flux": _finite_or_none(r.target_flux),
                    "community_growth": _finite_or_none(r.community_growth),
                    "status": r.status,
                    "explain": explain_consortium(r, spec),
                }
                for r in ranked
            ]
            for spec, ranked in ranked_by_target
        },
        "pareto_frontier": pareto,
        "warnings": [] if warning is None else [warning],
    }
    _write_json_or_print(payload, args.out, "search_advanced_summary.json")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    """User model-pool search for target metabolite production."""
    try:
        import pandas as pd

        from cmig.core.engine import MicomEngine
        from cmig.core.medium_spec import load_medium
        from cmig.core.model_pool import diagnose_model_pool, taxonomy_from_model_dir
        from cmig.core.search import Direction
        from cmig.core.search_product import SearchConfig, search_model_pool
    except ImportError:
        print("search requires the engine stack: uv sync --extra engine", file=sys.stderr)
        return 2
    try:
        if bool(args.taxonomy) == bool(args.model_dir):
            raise ValueError("provide exactly one of --taxonomy or --model-dir")
        if args.taxonomy:
            tax_path = Path(args.taxonomy)
            if not tax_path.exists():
                raise ValueError(f"taxonomy file not found: {tax_path}")
            taxonomy = pd.read_csv(tax_path)
        else:
            taxonomy = taxonomy_from_model_dir(args.model_dir, recursive=args.recursive)
        missing_cols = {"id", "file"} - set(taxonomy.columns)
        if missing_cols:
            raise ValueError(f"taxonomy missing required columns: {sorted(missing_cols)}")
        medium_spec = load_medium(args.medium) if args.medium else None
        diagnostics = diagnose_model_pool(taxonomy, args.target)
        config = SearchConfig(
            target=args.target,
            direction=Direction(args.direction),
            min_size=args.min_size,
            max_size=args.max_size,
            strategy=args.strategy,
            n_samples=args.n_samples,
            seed=args.seed,
            top_k=args.top_k,
            growth_fraction=args.growth_fraction,
            solver=args.solver,
            robustness_fva=args.robustness_fva,
        )
        result = search_model_pool(
            MicomEngine(),
            taxonomy,
            config,
            medium_spec=medium_spec,
            strict_medium=not args.allow_unknown_medium,
        )
        out = Path(args.out)
        _write_search_outputs(result, taxonomy, diagnostics, out)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"failed to write search outputs: {e}", file=sys.stderr)
        return 2
    print(f"search complete ({result.strategy}, target={result.target}) -> {out}")
    print(f"  evaluated: {result.n_candidates_evaluated}/{result.n_candidates_total}")
    if result.ranks:
        best = result.ranks[0]
        print(
            f"  best: {'+'.join(best.members)} "
            f"flux={best.target_flux:.4g} growth={best.community_growth:.4g}"
        )
    return 0


def _finite_or_none(value: float) -> float | None:
    return value if math.isfinite(value) else None


def _finite_csv(value: float) -> str:
    return "" if not math.isfinite(value) else f"{value:.12g}"


def _write_search_outputs(result: Any, taxonomy: Any, diagnostics: list[Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    taxonomy.to_csv(out / "pool_taxonomy.csv", index=False)
    with open(out / "pool_diagnostics.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "member_id",
                "file",
                "readable",
                "model_id",
                "n_reactions",
                "n_exchanges",
                "n_biomass",
                "has_target_exchange",
                "matching_exchanges",
                "warnings",
                "error",
            ],
        )
        writer.writeheader()
        for row in diagnostics:
            writer.writerow({
                "member_id": row.member_id,
                "file": row.file,
                "readable": row.readable,
                "model_id": row.model_id or "",
                "n_reactions": "" if row.n_reactions is None else row.n_reactions,
                "n_exchanges": "" if row.n_exchanges is None else row.n_exchanges,
                "n_biomass": "" if row.n_biomass is None else row.n_biomass,
                "has_target_exchange": row.has_target_exchange,
                "matching_exchanges": ";".join(row.matching_exchanges),
                "warnings": ";".join(row.warnings),
                "error": row.error or "",
            })
    ranking_path = out / "search_rankings.csv"
    with open(ranking_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "rank",
                "members",
                "score",
                "target_flux",
                "community_growth",
                "robustness_fva_lo",
                "robustness_fva_hi",
                "robustness_width",
                "robustness_status",
                "status",
                "diagnostic",
            ],
        )
        writer.writeheader()
        for row in result.ranks:
            writer.writerow({
                "rank": row.rank,
                "members": "+".join(row.members),
                "score": _finite_csv(row.score),
                "target_flux": _finite_csv(row.target_flux),
                "community_growth": _finite_csv(row.community_growth),
                "robustness_fva_lo": (
                    "" if row.robustness_fva_lo is None else _finite_csv(row.robustness_fva_lo)
                ),
                "robustness_fva_hi": (
                    "" if row.robustness_fva_hi is None else _finite_csv(row.robustness_fva_hi)
                ),
                "robustness_width": (
                    "" if row.robustness_width is None else _finite_csv(row.robustness_width)
                ),
                "robustness_status": row.robustness_status or "",
                "status": row.status,
                "diagnostic": row.diagnostic or "",
            })
    member_ids = [str(x) for x in taxonomy["id"]]
    with open(out / "search_member_matrix.csv", "w", newline="") as f:
        fieldnames = ["rank", "members", "target_flux", "community_growth"] + member_ids
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in result.ranks:
            present = set(row.members)
            record: dict[str, object] = {
                "rank": row.rank,
                "members": "+".join(row.members),
                "target_flux": _finite_csv(row.target_flux),
                "community_growth": _finite_csv(row.community_growth),
            }
            record.update({member_id: int(member_id in present) for member_id in member_ids})
            writer.writerow(record)
    search_warnings = list(result.warnings)
    n_readable = sum(1 for row in diagnostics if row.readable)
    n_with_target = sum(1 for row in diagnostics if row.has_target_exchange)
    n_with_biomass = sum(1 for row in diagnostics if row.n_biomass and row.n_biomass > 0)
    if n_readable != len(diagnostics):
        search_warnings.append("one or more pool models failed import diagnostics")
    if n_with_target == 0:
        search_warnings.append("target exchange was not detected in any individual pool model")
    if n_with_biomass != len(diagnostics):
        search_warnings.append("one or more pool models have no detected biomass objective")
    payload = {
        "status": "ok",
        "target": result.target,
        "target_exchange": result.target_exchange,
        "direction": result.direction,
        "strategy": result.strategy,
        "n_pool_members": result.n_pool_members,
        "n_candidates_total": result.n_candidates_total,
        "n_candidates_evaluated": result.n_candidates_evaluated,
        "pool_diagnostics": {
            "n_readable": n_readable,
            "n_with_target_exchange": n_with_target,
            "n_with_biomass": n_with_biomass,
        },
        "top_ranked": [
            {
                "rank": row.rank,
                "members": list(row.members),
                "score": _finite_or_none(row.score),
                "target_flux": _finite_or_none(row.target_flux),
                "community_growth": _finite_or_none(row.community_growth),
                "robustness_fva_lo": (
                    None if row.robustness_fva_lo is None
                    else _finite_or_none(row.robustness_fva_lo)
                ),
                "robustness_fva_hi": (
                    None if row.robustness_fva_hi is None
                    else _finite_or_none(row.robustness_fva_hi)
                ),
                "robustness_width": (
                    None if row.robustness_width is None else _finite_or_none(row.robustness_width)
                ),
                "robustness_status": row.robustness_status,
                "status": row.status,
                "diagnostic": row.diagnostic,
            }
            for row in result.ranks
        ],
        "warnings": search_warnings,
        "artifacts": [
            "pool_taxonomy.csv",
            "pool_diagnostics.csv",
            "search_rankings.csv",
            "search_member_matrix.csv",
            "search_plot.svg",
            "search_plot.tiff",
            "search_scatter.svg",
            "search_scatter.tiff",
            "search_summary.json",
        ],
    }
    (out / "search_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )
    _write_search_svg(result, out / "search_plot.svg")
    _write_search_scatter_svg(result, out / "search_scatter.svg")
    _write_search_tiff(result, out / "search_plot.tiff")
    _write_search_scatter_tiff(result, out / "search_scatter.tiff")


def _load_matplotlib_pyplot() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "Arial",
        "axes.titlesize": 14,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
    })
    return plt


def _polish_matplotlib_axes(ax: Any, *, grid_axis: str = "x") -> None:
    ax.grid(True, axis=grid_axis, color="#d9dee3", linewidth=0.7, alpha=0.85)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _save_screening_figure(fig: Any, out_svg: Path, out_tiff: Path) -> None:
    fig.tight_layout()
    fig.savefig(out_svg, format="svg")
    fig.savefig(out_tiff, format="tiff", dpi=300)


def _write_dfba_outputs(
    result: Any,
    out: Path,
    *,
    model_path: Path,
    solver: str,
    config: dict[str, Any],
) -> None:
    from cmig.core.dfba import build_timecourse, timecourse_rows, write_timecourse

    out.mkdir(parents=True, exist_ok=True)
    table = build_timecourse(result)
    write_timecourse(table, out / "timecourse.parquet")
    rows = timecourse_rows(result)
    with open(out / "dfba_timecourse.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["t", "series", "value"])
        writer.writeheader()
        writer.writerows(rows)
    final = result.timecourse[-1]
    payload = {
        "status": result.status,
        "diagnostic": result.diagnostic,
        "model": str(model_path),
        "solver": solver,
        "config": config,
        "managed_exchanges": result.managed_exchanges,
        "n_timepoints": len(result.timecourse),
        "final_t": final.t,
        "final_biomass": final.biomass,
        "final_growth_rate": final.growth_rate,
        "final_concentrations": final.concentrations,
        "artifacts": [
            "timecourse.parquet",
            "dfba_timecourse.csv",
            "dfba_timecourse.svg",
            "dfba_timecourse.tiff",
            "dfba_summary.json",
        ],
    }
    (out / "dfba_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )
    _write_dfba_figure(rows, out / "dfba_timecourse.svg", out / "dfba_timecourse.tiff")


def _write_dfba_figure(rows: list[dict[str, Any]], out_svg: Path, out_tiff: Path) -> None:
    plt = _load_matplotlib_pyplot()
    series: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        series.setdefault(str(row["series"]), []).append((float(row["t"]), float(row["value"])))
    fig, axes = plt.subplots(
        3, 1, figsize=(7.4, 7.2), dpi=300, sharex=True,
        gridspec_kw={"height_ratios": [1.1, 0.8, 1.1]},
    )
    biomass = series.get("biomass", [])
    if biomass:
        axes[0].plot([x for x, _ in biomass], [y for _, y in biomass], color="#2b8cbe", linewidth=2)
        final_t, final_biomass = biomass[-1]
        axes[0].text(
            final_t,
            final_biomass,
            f" final {final_biomass:.3g}",
            va="center",
            ha="left",
            fontsize=9,
            color="#2b8cbe",
        )
    axes[0].set_title("Dynamic FBA time course", loc="left", pad=10)
    axes[0].set_ylabel("Biomass")
    _polish_matplotlib_axes(axes[0], grid_axis="y")
    growth = series.get("growth_rate", [])
    if growth:
        growth_plot = [(x, y) for x, y in growth if x > 0.0]
        if not growth_plot:
            growth_plot = growth
        axes[1].plot(
            [x for x, _ in growth_plot],
            [y for _, y in growth_plot],
            color="#636363",
            linewidth=1.8,
            marker="o",
            markersize=3.8,
        )
        axes[1].ticklabel_format(axis="y", style="plain", useOffset=False)
    axes[1].set_ylabel("Growth rate")
    _polish_matplotlib_axes(axes[1], grid_axis="y")
    palette = ["#d95f0e", "#31a354", "#756bb1", "#636363", "#e7298a", "#1b9e77"]
    metabolites = [name for name in series if name not in {"biomass", "growth_rate"}]
    for idx, name in enumerate(metabolites):
        values = series[name]
        axes[2].plot(
            [x for x, _ in values],
            [y for _, y in values],
            label=name,
            color=palette[idx % len(palette)],
            linewidth=1.8,
        )
        final_t, final_value = values[-1]
        axes[2].text(
            final_t,
            final_value,
            f" {final_value:.3g}",
            va="center",
            ha="left",
            fontsize=9,
            color=palette[idx % len(palette)],
        )
    axes[2].set_xlabel("Time")
    axes[2].set_ylabel("Concentration")
    if metabolites:
        axes[2].legend(loc="best", frameon=False, fontsize=9)
    _polish_matplotlib_axes(axes[2], grid_axis="y")
    _save_screening_figure(fig, out_svg, out_tiff)
    plt.close(fig)


def _write_strain_growth_figures(rows: list[dict[str, Any]], out: Path) -> None:
    plt = _load_matplotlib_pyplot()
    labels = [str(row["member"]) for row in rows]
    single = [_optional_float(row.get("single_growth")) or 0.0 for row in rows]
    community = [_optional_float(row.get("community_member_growth")) or 0.0 for row in rows]
    height = max(3.4, 1.4 + 0.48 * max(len(rows), 1))
    fig, ax = plt.subplots(figsize=(7.2, height), dpi=300)
    positions = list(range(len(labels)))
    offset = 0.18
    ax.barh(
        [y + offset for y in positions],
        single,
        height=0.32,
        color="#2b8cbe",
        label="Single model",
    )
    ax.barh(
        [y - offset for y in positions],
        community,
        height=0.32,
        color="#31a354",
        label="Community",
    )
    ax.set_yticks(positions)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("Growth rate")
    ax.set_title("Strain growth profile", loc="left", pad=10)
    max_value = max(single + community, default=0.0)
    if max_value > 0.0:
        ax.set_xlim(right=max_value * 1.08)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.12), ncol=2, frameon=False)
    _polish_matplotlib_axes(ax, grid_axis="x")
    _save_screening_figure(
        fig,
        out / "strain_growth_plot.svg",
        out / "strain_growth_plot.tiff",
    )
    plt.close(fig)


def _write_abundance_impact_figures(
    rows: list[dict[str, Any]],
    out: Path,
    *,
    target_member: str,
    target: str,
) -> None:
    plt = _load_matplotlib_pyplot()
    valid_rows = sorted(
        (row for row in rows if _optional_float(row.get("target_abundance")) is not None),
        key=lambda row: float(row["target_abundance"]),
    )
    x = [float(row["target_abundance"]) for row in valid_rows]
    community_growth = [_optional_float(row.get("community_growth")) or 0.0 for row in valid_rows]
    member_growth = [
        _optional_float(row.get("target_member_growth")) or 0.0 for row in valid_rows
    ]
    member_flux = [
        _optional_float(row.get("target_member_exchange")) or 0.0 for row in valid_rows
    ]
    community_flux = [
        _optional_float(row.get("community_target_exchange")) or 0.0 for row in valid_rows
    ]
    influence = [
        _optional_float(row.get("target_influence_share")) or 0.0 for row in valid_rows
    ]
    fig, axes = plt.subplots(3, 1, figsize=(7.2, 7.4), dpi=300, sharex=True)
    axes[0].plot(x, community_growth, color="#2b8cbe", marker="o", label="Community")
    axes[0].plot(x, member_growth, color="#31a354", marker="o", label=target_member)
    axes[0].set_ylabel("Growth")
    axes[0].set_title(
        f"Abundance sensitivity: {target_member}",
        loc="left",
        pad=10,
    )
    axes[0].legend(frameon=False, loc="best")
    _polish_matplotlib_axes(axes[0], grid_axis="y")
    axes[1].plot(x, member_flux, color="#756bb1", marker="o", label=f"{target_member} {target}")
    axes[1].plot(x, community_flux, color="#d95f0e", marker="o", label=f"Community {target}")
    axes[1].set_ylabel("Exchange flux")
    axes[1].legend(frameon=False, loc="best")
    _polish_matplotlib_axes(axes[1], grid_axis="y")
    axes[2].plot(x, influence, color="#636363", marker="o")
    axes[2].set_xlabel(f"{target_member} abundance")
    axes[2].set_ylabel("Target share")
    axes[2].set_ylim(bottom=0.0, top=min(1.0, max(0.1, max(influence, default=0.0) * 1.25)))
    _polish_matplotlib_axes(axes[2], grid_axis="y")
    _save_screening_figure(
        fig,
        out / "abundance_impact_plot.svg",
        out / "abundance_impact_plot.tiff",
    )
    plt.close(fig)


def _write_spatial_preview_outputs(
    result: Any,
    out: Path,
    *,
    metabolite: str,
    config: Any,
) -> None:
    from cmig.core.spatial import spatial_rows

    out.mkdir(parents=True, exist_ok=True)
    rows = spatial_rows(result)
    with open(out / "spatial_frames.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["step", "t", "x", "y", "value"])
        writer.writeheader()
        writer.writerows(rows)
    final = result.final
    payload = {
        "status": result.status,
        "diagnostic": result.diagnostic,
        "metabolite": metabolite,
        "config": {
            "width": config.width,
            "height": config.height,
            "steps": config.steps,
            "dt": config.dt,
            "diffusion": config.diffusion,
            "initial_value": config.initial_value,
            "source_edge": config.source_edge,
            "source_value": config.source_value,
            "sink_edge": config.sink_edge,
            "sink_value": config.sink_value,
            "store_every": config.store_every,
        },
        "n_frames": len(result.frames),
        "final_step": final.step,
        "final_t": final.t,
        "final_min": min(min(row) for row in final.values),
        "final_max": max(max(row) for row in final.values),
        "artifacts": [
            "spatial_frames.csv",
            "spatial_heatmap.svg",
            "spatial_heatmap.tiff",
            "spatial_snapshots.svg",
            "spatial_snapshots.tiff",
            "spatial_summary.json",
        ],
    }
    (out / "spatial_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )
    _write_spatial_heatmap(
        final.values,
        out / "spatial_heatmap.svg",
        out / "spatial_heatmap.tiff",
        metabolite=metabolite,
        step=final.step,
    )
    _write_spatial_snapshots(
        result.frames,
        out / "spatial_snapshots.svg",
        out / "spatial_snapshots.tiff",
        metabolite=metabolite,
    )


def _write_spatial_heatmap(
    values: list[list[float]],
    out_svg: Path,
    out_tiff: Path,
    *,
    metabolite: str,
    step: int,
) -> None:
    plt = _load_matplotlib_pyplot()
    fig, ax = plt.subplots(figsize=(6.2, 5.4), dpi=300)
    image = ax.imshow(values, cmap="viridis", origin="lower", interpolation="nearest")
    ax.set_title(f"Spatial medium preview: {metabolite}", loc="left", pad=10, fontsize=14)
    ax.set_xlabel("x grid")
    ax.set_ylabel("y grid")
    ax.text(0.99, 0.99, f"step {step}", transform=ax.transAxes, va="top", ha="right",
            fontsize=9, color="#222222",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 3})
    cbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Concentration")
    _save_screening_figure(fig, out_svg, out_tiff)
    plt.close(fig)


def _write_spatial_snapshots(
    frames: list[Any],
    out_svg: Path,
    out_tiff: Path,
    *,
    metabolite: str,
) -> None:
    plt = _load_matplotlib_pyplot()
    selected = _select_spatial_frames(frames)
    vmax = max(max(max(row) for row in frame.values) for frame in selected)
    vmin = min(min(min(row) for row in frame.values) for frame in selected)
    fig, axes = plt.subplots(
        1, len(selected) + 1, figsize=(10.2, 3.4), dpi=300, constrained_layout=True
    )
    image = None
    for ax, frame in zip(axes[:-1], selected, strict=False):
        image = ax.imshow(
            frame.values,
            cmap="viridis",
            origin="lower",
            interpolation="nearest",
            vmin=vmin,
            vmax=vmax,
        )
        ax.set_title(f"t={frame.t:.3g}", fontsize=11)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
    final = selected[-1]
    mid_y = len(final.values) // 2
    profile = final.values[mid_y]
    axes[-1].plot(range(len(profile)), profile, color="#2b8cbe", linewidth=2)
    axes[-1].set_title("Final centerline concentration", fontsize=11)
    axes[-1].set_xlabel("x")
    axes[-1].set_ylabel("")
    _polish_matplotlib_axes(axes[-1], grid_axis="y")
    fig.suptitle(f"Spatial medium dynamics: {metabolite}", x=0.02, ha="left", fontsize=14)
    if image is not None:
        cbar = fig.colorbar(image, ax=list(axes[:-1]), fraction=0.035, pad=0.02)
        cbar.set_label("Grid concentration")
    fig.savefig(out_svg, format="svg", bbox_inches="tight")
    fig.savefig(out_tiff, format="tiff", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _select_spatial_frames(frames: list[Any]) -> list[Any]:
    if len(frames) <= 3:
        return frames
    return [frames[0], frames[len(frames) // 2], frames[-1]]


def _write_host_search_figures(
    rows: list[dict[str, Any]], out: Path, *, target: str, metric: str
) -> None:
    plt = _load_matplotlib_pyplot()
    top = rows[:10]
    labels = ["+".join(str(x) for x in row["members"]) for row in top]
    values = [float(row["score"]) for row in top]
    height = max(3.4, 0.45 * max(len(top), 1) + 1.8)
    fig, ax = plt.subplots(figsize=(7.4, height), dpi=300)
    if top:
        colors = [
            "#3182bd" if row["evaluation_status"] == "ok" else "#bdbdbd"
            for row in top
        ]
        ax.barh(labels[::-1], values[::-1], color=colors[::-1], height=0.56)
        for idx, value in enumerate(values[::-1]):
            if abs(value) > 1e-12:
                ax.text(value, idx, f" {value:.3g}", va="center", fontsize=10)
    ax.set_title(f"Host-microbe combination ranking: {target}", loc="left", pad=12)
    ax.set_xlabel(metric.replace("_", " "))
    ax.margins(x=0.06)
    _polish_matplotlib_axes(ax, grid_axis="x")
    _save_screening_figure(fig, out / "host_search_plot.svg", out / "host_search_plot.tiff")
    plt.close(fig)


def _write_gene_ko_figures(
    rows: list[dict[str, Any]],
    out: Path,
    *,
    target: str,
    ko_level: str,
    direction: str,
    baseline: Any,
    n_evaluated: int,
    n_total: int,
    selection: str,
) -> None:
    plt = _load_matplotlib_pyplot()
    from matplotlib.patches import Patch

    improve, worsen, neutral, failed = "#2ca25f", "#e6550d", "#969696", "#cfcfcf"
    direction_word = "secretion" if "secretion" in direction else "uptake"

    top = rows[:12]
    # barh draws bottom-to-top, so reverse to keep rank #1 at the top.
    plot = list(reversed(top))
    labels = [f"{row['member']}:{row['gene']}" for row in plot]
    deltas = [_optional_float(row.get("target_flux_delta")) for row in plot]
    statuses = [str(row.get("evaluation_status", "ok")) for row in plot]

    def _classify(delta: float | None, status: str) -> tuple[float, str, bool]:
        """Return (bar_value, color, is_real). Failed/non-finite render as a zero-width marker."""
        if status != "ok" or delta is None or not math.isfinite(delta):
            return 0.0, failed, False
        if delta > 0:
            return delta, improve, True
        if delta < 0:
            return delta, worsen, True
        return 0.0, neutral, True

    classified = [_classify(d, s) for d, s in zip(deltas, statuses, strict=False)]
    bar_values = [c[0] for c in classified]

    height = max(3.4, 0.46 * max(len(plot), 1) + 2.1)
    fig, ax = plt.subplots(figsize=(7.8, height), dpi=300)
    if plot:
        ax.barh(labels, bar_values, color=[c[1] for c in classified], height=0.56)
        ax.axvline(0.0, color="#333333", linewidth=0.9)
        span = max([abs(v) for v in bar_values] + [1.0])
        for idx, (value, _color, is_real) in enumerate(classified):
            if not is_real:
                ax.text(0.0, idx, "  failed", va="center", ha="left",
                        fontsize=9, color="#737373", style="italic")
            elif abs(value) > 1e-12:
                offset = 0.01 * span * (1 if value >= 0 else -1)
                ax.text(value + offset, idx, f"{value:.3g}", va="center",
                        ha="left" if value >= 0 else "right", fontsize=10)

    base_flux = _optional_float(getattr(baseline, "target_flux", None))
    base_txt = "n/a" if base_flux is None else f"{base_flux:.3g}"
    ax.set_title(
        f"Single-{ko_level} KO effect on {target} {direction_word}", loc="left", pad=24
    )
    ax.text(
        0.0, 1.02,
        f"baseline {target} flux {base_txt} · evaluated {n_evaluated}/{n_total} "
        f"{ko_level}s · selection {selection}",
        transform=ax.transAxes, fontsize=9.5, color="#555555",
    )
    ax.set_xlabel(f"{target} flux delta vs baseline (positive = more {direction_word})")
    ax.margins(x=0.12)
    _polish_matplotlib_axes(ax, grid_axis="x")
    ax.legend(
        handles=[
            Patch(facecolor=improve, label="improves target"),
            Patch(facecolor=worsen, label="reduces target"),
            Patch(facecolor=failed, label="failed / no change"),
        ],
        loc="lower right", frameon=False, fontsize=9,
    )
    _save_screening_figure(fig, out / "gene_ko_plot.svg", out / "gene_ko_plot.tiff")
    plt.close(fig)


def _write_search_tiff(result: Any, path: Path) -> None:
    plt = _load_matplotlib_pyplot()
    rows = [row for row in result.ranks[:10] if math.isfinite(row.target_flux)]
    labels = ["+".join(row.members) for row in rows]
    values = [row.target_flux for row in rows]
    height = max(3.4, 0.45 * max(len(rows), 1) + 1.7)
    fig, ax = plt.subplots(figsize=(7.2, height), dpi=300)
    if rows:
        colors = ["#2ca25f" if value >= 0 else "#e6550d" for value in values]
        ax.barh(labels[::-1], values[::-1], color=colors[::-1], height=0.56)
        for idx, value in enumerate(values[::-1]):
            ax.text(value, idx, f" {value:.3g}", va="center", fontsize=10)
    ax.set_title(f"Target production search: {result.target}")
    ax.set_xlabel(f"Target exchange flux ({result.target_exchange})")
    ax.text(
        0.0,
        1.01,
        f"{result.strategy} · evaluated {result.n_candidates_evaluated}/"
        f"{result.n_candidates_total} candidates",
        transform=ax.transAxes,
        fontsize=10,
        color="#555555",
    )
    if len(rows) == 1:
        ax.text(1.0, 1.01, "single candidate", transform=ax.transAxes, ha="right",
                fontsize=10, color="#555555")
    _polish_matplotlib_axes(ax, grid_axis="x")
    fig.tight_layout()
    fig.savefig(path, format="tiff", dpi=300)
    plt.close(fig)


def _write_search_scatter_tiff(result: Any, path: Path) -> None:
    plt = _load_matplotlib_pyplot()
    rows = [
        row for row in result.ranks
        if math.isfinite(row.target_flux) and math.isfinite(row.community_growth)
    ]
    fig, ax = plt.subplots(figsize=(6.8, 4.8), dpi=300)
    if rows:
        ax.scatter(
            [row.community_growth for row in rows],
            [row.target_flux for row in rows],
            s=56,
            color="#3182bd",
            alpha=0.9,
            edgecolor="white",
            linewidth=0.8,
        )
        for row in rows:
            ax.annotate(
                f"#{row.rank}",
                (row.community_growth, row.target_flux),
                xytext=(6, 4),
                textcoords="offset points",
                fontsize=9,
            )
    ax.set_title("Growth-production tradeoff")
    ax.set_xlabel("Community growth under target objective")
    ax.set_ylabel("Target exchange flux")
    ax.text(0.0, -0.18, f"Target: {result.target_exchange}", transform=ax.transAxes,
            fontsize=9, color="#555555")
    if len(rows) == 1:
        ax.text(1.0, 1.02, "single candidate", transform=ax.transAxes, ha="right",
                fontsize=10, color="#555555")
    _polish_matplotlib_axes(ax, grid_axis="both")
    fig.tight_layout()
    fig.savefig(path, format="tiff", dpi=300)
    plt.close(fig)


def _write_search_svg(result: Any, path: Path) -> None:
    rows = [r for r in result.ranks[:10] if math.isfinite(r.target_flux)]
    labels = ["+".join(r.members) for r in rows]
    width, height = 980, 420
    margin_left = min(300, max(120, 7 * max([len(label) for label in labels] + [8]) + 32))
    margin_top, margin_bottom = 54, 95
    plot_w = width - margin_left - 40
    plot_h = height - margin_top - margin_bottom
    max_flux = max([abs(r.target_flux) for r in rows] + [1.0])
    bar_gap = 8
    bar_h = min(34, max(14, int((plot_h - bar_gap * max(len(rows) - 1, 0)) / max(len(rows), 1))))
    total_bar_h = len(rows) * bar_h + max(len(rows) - 1, 0) * bar_gap
    y0 = margin_top + max(0, (plot_h - total_bar_h) / 2)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{margin_left}" y="30" font-family="Arial" font-size="22" '
        f'font-weight="700">Target production search: {html.escape(result.target)}</text>',
        f'<text x="{margin_left}" y="52" font-family="Arial" font-size="13" fill="#555">'
        f'{html.escape(result.strategy)} · evaluated {result.n_candidates_evaluated}/'
        f'{result.n_candidates_total} candidates</text>',
    ]
    axis_x = margin_left
    axis_y = margin_top + plot_h
    for frac in (0.25, 0.5, 0.75, 1.0):
        gx = axis_x + plot_w * frac
        parts.append(
            f'<line x1="{gx:.1f}" y1="{margin_top}" x2="{gx:.1f}" y2="{axis_y}" '
            'stroke="#d9dee3" stroke-width="1"/>'
        )
    parts.append(
        f'<line x1="{axis_x}" y1="{axis_y}" x2="{axis_x + plot_w}" y2="{axis_y}" '
        'stroke="#222" stroke-width="1"/>'
    )
    for i, row in enumerate(rows):
        y = y0 + i * (bar_h + bar_gap)
        bar_w = int((abs(row.target_flux) / max_flux) * plot_w)
        label = html.escape("+".join(row.members))
        color = "#2ca25f" if row.target_flux >= 0 else "#e6550d"
        parts.extend([
            f'<text x="{axis_x - 12}" y="{y + bar_h * 0.72:.1f}" font-family="Arial" '
            f'font-size="13" text-anchor="end">{label}</text>',
            f'<rect x="{axis_x}" y="{y}" width="{bar_w}" height="{bar_h}" '
            f'fill="{color}" opacity="0.88"/>',
            f'<text x="{axis_x + bar_w + 8}" y="{y + bar_h * 0.72:.1f}" '
            f'font-family="Arial" font-size="13">{row.target_flux:.3g}</text>',
        ])
    parts.append(
        f'<text x="{axis_x}" y="{height - 28}" font-family="Arial" font-size="13" '
        f'fill="#333">Target exchange flux ({html.escape(result.target_exchange)}), '
        'larger is better for max secretion</text>'
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n")


def _write_search_scatter_svg(result: Any, path: Path) -> None:
    width, height = 760, 520
    left, top, right, bottom = 82, 50, 32, 78
    plot_w = width - left - right
    plot_h = height - top - bottom
    rows = [
        row for row in result.ranks
        if math.isfinite(row.target_flux) and math.isfinite(row.community_growth)
    ]
    max_flux = float(max([row.target_flux for row in rows] + [1.0]))
    min_flux = float(min([row.target_flux for row in rows] + [0.0]))
    max_growth = float(max([row.community_growth for row in rows] + [1.0]))
    min_growth = float(min([row.community_growth for row in rows] + [0.0]))
    flux_span = max(max_flux - min_flux, 1e-9)
    growth_span = max(max_growth - min_growth, 1e-9)

    def x(value: float) -> float:
        return left + ((value - min_growth) / growth_span) * plot_w

    def y(value: float) -> float:
        return top + plot_h - ((value - min_flux) / flux_span) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{left}" y="30" font-family="Arial" font-size="22" '
        f'font-weight="700">Growth-production tradeoff</text>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" '
        'stroke="#222"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#222"/>',
        f'<text x="{left + plot_w / 2:.1f}" y="{height - 25}" font-family="Arial" '
        'font-size="14" text-anchor="middle">Community growth under target objective</text>',
        f'<text x="20" y="{top + plot_h / 2:.1f}" font-family="Arial" font-size="14" '
        'transform="rotate(-90 20 '
        f'{top + plot_h / 2:.1f})" text-anchor="middle">Target exchange flux</text>',
    ]
    for frac in (0.25, 0.5, 0.75):
        gx = left + plot_w * frac
        gy = top + plot_h * frac
        parts.extend([
            f'<line x1="{gx:.1f}" y1="{top}" x2="{gx:.1f}" y2="{top + plot_h}" '
            'stroke="#d9dee3" stroke-width="1"/>',
            f'<line x1="{left}" y1="{gy:.1f}" x2="{left + plot_w}" y2="{gy:.1f}" '
            'stroke="#d9dee3" stroke-width="1"/>',
        ])
    if len(rows) == 1:
        parts.append(
            f'<text x="{left + plot_w - 4}" y="{top + 18}" font-family="Arial" '
            'font-size="12" text-anchor="end" fill="#555">single candidate</text>'
        )
    for row in rows:
        px, py = x(row.community_growth), y(row.target_flux)
        label = html.escape(str(row.rank))
        title = html.escape("+".join(row.members))
        parts.extend([
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="8" fill="#3182bd" opacity="0.9"/>',
            f'<text x="{px + 10:.1f}" y="{py + 4:.1f}" font-family="Arial" '
            f'font-size="12">#{label}</text>',
            f'<title>{title}: flux={row.target_flux:.4g}, '
            f'growth={row.community_growth:.4g}</title>',
        ])
    parts.append(
        f'<text x="{left}" y="{height - 8}" font-family="Arial" font-size="12" '
        f'fill="#555">Target: {html.escape(result.target_exchange)}</text>'
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n")


def _cmd_stats_demo(args: argparse.Namespace) -> int:
    """Small deterministic stats demo exposing §15 helpers from CLI."""
    try:
        from cmig.core.stats import (
            distribution_summary,
            fdr_correct,
            stats_warnings,
            two_group_test,
        )
    except ImportError:
        print("stats-demo 는 stats extra 필요: uv sync --extra stats", file=sys.stderr)
        return 2
    groups = {"western": [1.0, 1.2, 1.1, 1.3], "fiber": [2.0, 2.3, 2.1, 2.4]}
    test = two_group_test(groups["western"], groups["fiber"])
    payload = {
        "summary": [s.__dict__ for s in distribution_summary(groups)],
        "test": test.__dict__,
        "fdr_qvalues": fdr_correct([test.pvalue], method=args.fdr_method),
        "warnings": stats_warnings(groups),
    }
    _write_json_or_print(payload, args.out, "stats_summary.json")
    return 0


def _cmd_stats_sweep(args: argparse.Namespace) -> int:
    """sweep.parquet 결과를 stats summary 로 변환."""
    try:
        import pyarrow.parquet as pq

        from cmig.core.stats import (
            distribution_summary,
            groups_from_sweep_rows,
            stats_warnings,
            two_group_test,
        )
    except ImportError:
        print("stats-sweep 는 stats extra 필요: uv sync --extra stats", file=sys.stderr)
        return 2
    sweep_path = Path(args.sweep)
    if not sweep_path.exists():
        print(f"sweep 파일 없음: {sweep_path}", file=sys.stderr)
        return 2
    rows = pq.read_table(sweep_path).to_pylist()  # type: ignore[no-untyped-call]
    groups = groups_from_sweep_rows(rows, metric=args.metric, group_axis=args.group_axis)
    names = sorted(groups)
    test = None
    if len(names) == 2:
        result = two_group_test(
            groups[names[0]],
            groups[names[1]],
            parametric=args.parametric,
        )
        test = {
            "groups": names,
            "test": result.test,
            "statistic": result.statistic,
            "pvalue": result.pvalue,
            "effect_size": result.effect_size,
            "effect_name": result.effect_name,
        }
    payload = {
        "metric": args.metric,
        "group_axis": args.group_axis,
        "groups": {name: len(groups[name]) for name in names},
        "summary": [s.__dict__ for s in distribution_summary(groups)],
        "test": test,
        "warnings": stats_warnings(groups),
        "source": str(sweep_path),
    }
    _write_json_or_print(payload, args.out, "stats_sweep_summary.json")
    return 0


def _cmd_namespace_suggest(args: argparse.Namespace) -> int:
    """Model import 후 namespace decision 초안 생성."""
    try:
        from cmig.core.namespace import decisions_to_jsonable, suggest_namespace_decisions
        from cmig.io.model_import import exchange_metabolite_ids, import_model
    except ImportError:
        print("namespace-suggest 는 engine stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    try:
        summary = import_model(args.model)
        known = None
        if args.known_targets:
            known = {
                line.strip()
                for line in Path(args.known_targets).read_text().splitlines()
                if line.strip() and not line.startswith("#")
            }
        decisions = suggest_namespace_decisions(
            exchange_metabolite_ids(summary),
            known_targets=known,
            source_namespace=args.source_namespace,
            target_namespace=args.target_namespace,
        )
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 2
    payload = {
        "model": summary.as_dict(),
        "decisions": decisions_to_jsonable(decisions),
    }
    _write_json_or_print(payload, args.out, "namespace_decisions.json")
    return 0


def _cmd_model_review(args: argparse.Namespace) -> int:
    """User-provided GEM import review + namespace audit payload."""
    try:
        from cmig.io.model_import import build_import_review, import_model
    except ImportError:
        print("model-review 는 engine stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    try:
        known = None
        if args.known_targets:
            known = {
                line.strip()
                for line in Path(args.known_targets).read_text().splitlines()
                if line.strip() and not line.startswith("#")
            }
        review = build_import_review(
            import_model(args.model),
            known_targets=known,
            source_namespace=args.source_namespace,
            target_namespace=args.target_namespace,
        )
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 2
    payload = {
        "model": review.model,
        "inferred_origin": review.inferred_origin,
        "namespace": review.namespace,
        "warnings": review.warnings,
        "next_actions": review.next_actions,
    }
    _write_json_or_print(payload, args.out, "model_review.json")
    return 0


def _parse_csv_floats(raw: str, *, flag: str) -> list[float]:
    try:
        values = [float(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError as e:
        raise ValueError(f"{flag} 는 comma-separated float 이어야 함: {raw}") from e
    if not values:
        raise ValueError(f"{flag} 값이 비어 있음")
    if any(not math.isfinite(v) for v in values):
        raise ValueError(f"{flag} 는 finite float 이어야 함")
    return values


def _parse_csv_strings(raw: str, *, flag: str) -> list[str]:
    values = [x.strip() for x in raw.split(",") if x.strip()]
    if not values:
        raise ValueError(f"{flag} 값이 비어 있음")
    return values


def _load_pool_taxonomy(
    *,
    taxonomy_path: str | None,
    model_dir: str | None,
    recursive: bool,
    pd: Any,
    taxonomy_from_model_dir: Any,
) -> Any:
    if bool(taxonomy_path) == bool(model_dir):
        raise ValueError("provide exactly one of --taxonomy or --model-dir")
    if taxonomy_path:
        path = Path(taxonomy_path)
        if not path.exists():
            raise ValueError(f"taxonomy file not found: {path}")
        taxonomy = pd.read_csv(path)
    else:
        taxonomy = taxonomy_from_model_dir(model_dir, recursive=recursive)
    missing_cols = {"id", "file"} - set(taxonomy.columns)
    if missing_cols:
        raise ValueError(f"taxonomy missing required columns: {sorted(missing_cols)}")
    ids = [str(x) for x in taxonomy["id"]]
    if len(ids) != len(set(ids)):
        raise ValueError("taxonomy id values must be unique")
    return taxonomy


def _taxonomy_with_member_fraction(taxonomy: Any, member_id: str, fraction: float) -> Any:
    variant = taxonomy.copy()
    ids = [str(x) for x in variant["id"]]
    if len(ids) == 1:
        variant["abundance"] = 1.0
        return variant
    if "abundance" in variant.columns:
        base = [max(float(v), 0.0) for v in variant["abundance"]]
    else:
        base = [1.0 for _ in ids]
    other_total = sum(value for mid, value in zip(ids, base, strict=False) if mid != member_id)
    if other_total <= 0.0:
        other_total = float(len(ids) - 1)
        base = [1.0 for _ in ids]
    abundances = []
    for mid, value in zip(ids, base, strict=False):
        if mid == member_id:
            abundances.append(fraction)
        else:
            abundances.append((1.0 - fraction) * value / other_total)
    variant["abundance"] = abundances
    return variant


def _parse_key_float_map(raw: str, *, flag: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for item in _parse_csv_strings(raw, flag=flag):
        if "=" not in item:
            raise ValueError(f"{flag} entries must be key=value, got {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"{flag} contains an empty key")
        try:
            number = float(value)
        except ValueError as e:
            raise ValueError(f"{flag} value for {key!r} is not numeric: {value!r}") from e
        if number < 0.0 or not math.isfinite(number):
            raise ValueError(f"{flag} value for {key!r} must be finite and non-negative")
        values[key] = number
    return values


def _dfba_initial_concentrations(model: Any, raw: str | None) -> dict[str, float]:
    if raw is not None:
        return _parse_key_float_map(raw, flag="--initial")
    concentrations = {
        rid: value
        for rid, value in DEFAULT_DFBA_INITIAL_CONCENTRATIONS.items()
        if rid in model.reactions
    }
    if not concentrations:
        defaults = ", ".join(DEFAULT_DFBA_INITIAL_CONCENTRATIONS)
        raise ValueError(
            "no default dFBA exchange ids were found in the model; "
            f"provide --initial explicitly (default candidates: {defaults})"
        )
    return concentrations


def _require_model_exchanges(model: Any, values: dict[str, float], *, flag: str) -> None:
    missing = [rid for rid in values if rid not in model.reactions]
    if missing:
        raise ValueError(f"{flag} exchange ids not found in model: {missing}")


def _parse_optional_csv_strings(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return _parse_csv_strings(raw, flag="comma-separated values")


def _parse_optional_paths(raw: str | None, *, flag: str) -> list[str | None]:
    if raw is None:
        return [None]
    paths = _parse_csv_strings(raw, flag=flag)
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        raise ValueError(f"{flag} 파일 없음: {missing}")
    return list(paths)


def _load_bounds_json(path: str) -> dict[str, list[float]]:
    p = Path(path)
    if not p.exists():
        raise ValueError(f"bounds 파일 없음: {p}")
    raw = json.loads(p.read_text())
    if not isinstance(raw, dict):
        raise ValueError("bounds JSON 은 {reaction_id: [lower, upper]} 객체여야 함")
    out: dict[str, list[float]] = {}
    for rid, pair in raw.items():
        if (
            not isinstance(rid, str)
            or not isinstance(pair, (list, tuple))
            or len(pair) != 2
        ):
            raise ValueError("bounds JSON 항목은 reaction_id: [lower, upper] 형식이어야 함")
        if isinstance(pair[0], bool) or isinstance(pair[1], bool):
            raise ValueError(f"bounds 값 오류: {rid} -> {pair}")
        try:
            lo, hi = float(pair[0]), float(pair[1])
        except (TypeError, ValueError) as e:
            raise ValueError(f"bounds 값 오류: {rid} -> {pair}") from e
        if not (math.isfinite(lo) and math.isfinite(hi)) or lo > hi:
            raise ValueError(f"bounds 값 오류: {rid} -> {pair}")
        out[rid] = [lo, hi]
    return out


def _taxonomy_model_checksum(taxonomy: Any, tax_path: Path) -> str:
    """taxonomy file 컬럼이 가리키는 GEM 파일 바이트 집합의 결정적 checksum."""
    from cmig.io.solve_output import file_checksum

    rows: list[dict[str, str]] = []
    for record in taxonomy.to_dict("records"):
        member_id = str(record["id"])
        raw_path = Path(str(record["file"]))
        model_path = raw_path
        if not model_path.exists() and not model_path.is_absolute():
            model_path = tax_path.parent / raw_path
        if not model_path.exists():
            raise ValueError(f"taxonomy model 파일 없음: {raw_path}")
        rows.append({"id": member_id, "file_checksum": file_checksum(model_path)})
    payload = json.dumps(
        sorted(rows, key=lambda row: row["id"]),
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_member_sets(raw: str | None) -> list[str | None]:
    if raw is None:
        return [None]
    sets: list[str | None] = [x.strip() for x in raw.split(";") if x.strip()]
    if not sets:
        raise ValueError("--member-sets 값이 비어 있음")
    return sets


def _apply_member_set(taxonomy: Any, member_set: str | None) -> Any:
    if member_set is None:
        return taxonomy.copy()
    ids = [x.strip() for x in member_set.replace("+", ",").split(",") if x.strip()]
    if not ids:
        raise ValueError(f"member_set 값이 비어 있음: {member_set}")
    available = {str(x) for x in taxonomy["id"]}
    missing = sorted(set(ids) - available)
    if missing:
        raise ValueError(f"member_set 에 taxonomy 미존재 id 포함: {missing}")
    return taxonomy[taxonomy["id"].astype(str).isin(ids)].copy()


def _apply_abundance_variant(taxonomy: Any, path: str | None) -> Any:
    if path is None:
        return taxonomy
    import pandas as pd

    p = Path(path)
    if p.suffix.lower() == ".json":
        raw = json.loads(p.read_text())
        if not isinstance(raw, dict):
            raise ValueError("abundance JSON 은 {member_id: abundance} 객체여야 함")
        mapping = {str(k): float(v) for k, v in raw.items()}
    else:
        df = pd.read_csv(p)
        missing_cols = {"id", "abundance"} - set(df.columns)
        if missing_cols:
            raise ValueError(f"abundance csv 필수 컬럼 누락: {sorted(missing_cols)}")
        mapping = {str(r["id"]): float(r["abundance"]) for r in df.to_dict("records")}
    missing = sorted(set(mapping) - {str(x) for x in taxonomy["id"]})
    if missing:
        raise ValueError(f"abundance variant 에 taxonomy 미존재 id 포함: {missing}")
    out = taxonomy.copy()
    if "abundance" not in out.columns:
        out["abundance"] = 1.0
    out["abundance"] = [mapping.get(str(mid), float(cur)) for mid, cur in zip(
        out["id"], out["abundance"], strict=True
    )]
    if any(float(v) < 0 or not math.isfinite(float(v)) for v in out["abundance"]):
        raise ValueError("abundance 값은 finite non-negative 이어야 함")
    return out


def _cmd_sweep_fixture(args: argparse.Namespace) -> int:
    """Fixture 기반 headless sweep 산출 경로."""
    try:
        from cmig.core.sweep import SweepAxis, run_sweep, write_sweep_parquet
        from cmig.golden_fixture import solve
    except ImportError:
        print("sweep-fixture 는 engine stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    try:
        axes = [
            SweepAxis("tradeoff_f", _parse_csv_floats(args.tradeoff_fs, flag="--tradeoff-fs")),
            SweepAxis("solver", _parse_csv_strings(args.solvers, flag="--solvers")),
        ]
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    def run_hash_fn(cond: Any) -> str:
        import hashlib

        return hashlib.sha256(json.dumps(cond.axis_values, sort_keys=True).encode()).hexdigest()

    def solve_fn(cond: Any) -> float:
        result, _bundle = solve(str(cond.axis_values["solver"]))
        return float(result.objective)

    rows = run_sweep(axes, run_hash_fn=run_hash_fn, solve_fn=solve_fn, metric=args.metric)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_sweep_parquet(rows, out / "sweep.parquet")
    _write_json_or_print(
        {
            "status": "ok",
            "n_runs": len(rows),
            "metric": args.metric,
            "artifacts": ["sweep.parquet", "sweep_summary.json"],
        },
        args.out,
        "sweep_summary.json",
    )
    return 0


def _cmd_sweep(args: argparse.Namespace) -> int:
    """사용자 taxonomy 기반 headless sweep."""
    try:
        import pandas as pd

        from cmig.core.namespace import GateBlockedError, load_namespace_decisions
        from cmig.core.sweep import SweepAxis, SweepRow, enumerate_conditions, write_sweep_parquet
        from cmig.service import EngineService
    except ImportError:
        print("sweep 는 engine stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2

    tax_path = Path(args.taxonomy)
    if not tax_path.exists():
        print(f"taxonomy 파일 없음: {tax_path}", file=sys.stderr)
        return 2
    taxonomy = pd.read_csv(tax_path)
    missing_cols = {"id", "file"} - set(taxonomy.columns)
    if missing_cols:
        print(f"taxonomy 필수 컬럼 누락: {sorted(missing_cols)} (필요: id, file)", file=sys.stderr)
        return 2
    try:
        tradeoff_fs = _parse_csv_floats(args.tradeoff_fs, flag="--tradeoff-fs")
        bad_tradeoffs = [v for v in tradeoff_fs if not (0.0 < v <= 1.0)]
        if bad_tradeoffs:
            raise ValueError(f"--tradeoff-fs 는 0<f≤1 이어야 함: {bad_tradeoffs}")
        axes = [
            SweepAxis("tradeoff_f", tradeoff_fs),
            SweepAxis("solver", _parse_csv_strings(args.solvers, flag="--solvers")),
            SweepAxis("medium_variant", _parse_optional_paths(args.mediums, flag="--mediums")),
            SweepAxis("member_set", _parse_member_sets(args.member_sets)),
            SweepAxis(
                "abundance",
                _parse_optional_paths(args.abundance_variants, flag="--abundance-variants"),
            ),
            SweepAxis(
                "bounds",
                _parse_optional_paths(args.bounds_variants, flag="--bounds-variants"),
            ),
        ]
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    out = Path(args.out)
    run_root = out / "runs"
    rows: list[SweepRow] = []
    profile_rows: list[dict[str, Any]] = []
    service = EngineService()
    try:
        namespace_decisions = (
            load_namespace_decisions(args.namespace_decisions)
            if args.namespace_decisions else None
        )
        for cond in enumerate_conditions(axes):
            cond_dir = run_root / cond.condition_id
            solver = str(cond.axis_values["solver"])
            medium = cond.axis_values.get("medium_variant")
            member_set = cond.axis_values.get("member_set")
            abundance = cond.axis_values.get("abundance")
            bounds_variant = cond.axis_values.get("bounds")
            medium_path = None if medium is None else str(medium)
            taxonomy_variant = _apply_abundance_variant(
                _apply_member_set(taxonomy, None if member_set is None else str(member_set)),
                None if abundance is None else str(abundance),
            )
            bounds = None if bounds_variant is None else _load_bounds_json(str(bounds_variant))
            outcome = service.solve_community(
                taxonomy=taxonomy_variant,
                model_checksum=_taxonomy_model_checksum(taxonomy_variant, tax_path),
                solver=solver,
                tradeoff_f=float(cond.axis_values["tradeoff_f"]),
                medium_path=medium_path,
                namespace_decisions=namespace_decisions,
                strict_medium=not args.allow_unknown_medium,
                out_dir=cond_dir,
                bounds=bounds,
                fva=args.fva or args.fva_metabolites is not None,
                fva_metabolites=_parse_optional_csv_strings(args.fva_metabolites),
            )
            status = "ok" if outcome.status == "ok" else "failed"
            rows.append(
                SweepRow(
                    condition_id=cond.condition_id,
                    axis_values=cond.axis_values,
                    metric=args.metric,
                    value=None if outcome.result is None else float(outcome.result.objective),
                    run_hash=outcome.run_hash or "",
                    status=status,
                    diagnostic=outcome.diagnostic,
                    cache_hit=False,
                )
            )
            if outcome.bundle is not None:
                for profile in outcome.bundle.profile.to_pylist():
                    profile_rows.append({
                        "condition_id": cond.condition_id,
                        "axis_medium_variant": None if medium is None else str(medium),
                        "axis_tradeoff_f": float(cond.axis_values["tradeoff_f"]),
                        "axis_solver": solver,
                        "run_hash": outcome.run_hash or "",
                        "status": status,
                        "metabolite": str(profile.get("metabolite", "")),
                        "net_flux": profile.get("net_flux"),
                        "ui_flux": profile.get("ui_flux"),
                        "label": profile.get("label"),
                        "fva_lo": profile.get("fva_lo"),
                        "fva_hi": profile.get("fva_hi"),
                    })
    except (ValueError, GateBlockedError, OSError) as e:
        print(str(e), file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    write_sweep_parquet(rows, out / "sweep.parquet")
    _write_sweep_profiles(profile_rows, out / "sweep_profiles.parquet")
    _write_medium_summary(rows, out / "medium_summary.csv")
    _write_json_or_print(
        {
            "status": "ok",
            "n_runs": len(rows),
            "metric": args.metric,
            "fva": bool(args.fva or args.fva_metabolites is not None),
            "artifacts": [
                "sweep.parquet",
                "sweep_profiles.parquet",
                "medium_summary.csv",
                "sweep_summary.json",
                "runs/",
            ],
        },
        args.out,
        "sweep_summary.json",
    )
    return 0


def _write_sweep_profiles(rows: list[dict[str, Any]], path: Path) -> None:
    """Condition-level profile long table for medium/diet sweep and FVA review."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    schema = pa.schema([
        ("condition_id", pa.string()),
        ("axis_medium_variant", pa.string()),
        ("axis_tradeoff_f", pa.float64()),
        ("axis_solver", pa.string()),
        ("run_hash", pa.string()),
        ("status", pa.string()),
        ("metabolite", pa.string()),
        ("net_flux", pa.float64()),
        ("ui_flux", pa.float64()),
        ("label", pa.string()),
        ("fva_lo", pa.float64()),
        ("fva_hi", pa.float64()),
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)  # type: ignore[no-untyped-call]


def _write_medium_summary(rows: list[Any], path: Path) -> None:
    """Small CSV index for quickly plotting medium/diet growth responses."""
    import pandas as pd

    records = [
        {
            "condition_id": row.condition_id,
            "medium_variant": row.axis_values.get("medium_variant"),
            "tradeoff_f": row.axis_values.get("tradeoff_f"),
            "solver": row.axis_values.get("solver"),
            "value": row.value,
            "metric": row.metric,
            "run_hash": row.run_hash,
            "status": row.status,
            "cache_hit": row.cache_hit,
        }
        for row in rows
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame.from_records(records).to_csv(path, index=False)


def _cmd_sandbox_fixture(args: argparse.Namespace) -> int:
    """Fixture community sandbox preview/commit 제품 경로."""
    try:
        from cmig.service import EngineService
    except ImportError:
        print("sandbox-fixture 는 engine stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    try:
        res = EngineService().sandbox_fixture(
            reaction_id=args.reaction,
            lower=args.lower,
            upper=args.upper,
            solver=args.solver,
            commit=args.commit,
            out_dir=args.out if args.commit else None,
        )
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 2
    payload = {
        "status": res.status,
        "state": res.state.value,
        "committed": res.committed,
        "run_hash": res.run_hash,
        "no_significant_change": res.no_significant_change,
        "diagnostic": res.diagnostic,
        "growth_delta": res.delta.growth_delta,
    }
    _write_json_or_print(payload, args.out, "sandbox_summary.json")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cmig", description="CMIG headless community metabolic core")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="버전 출력").set_defaults(func=_cmd_version)
    sub.add_parser("solvers", help="solver capability matrix").set_defaults(func=_cmd_solvers)
    wf = sub.add_parser("workflows", help="print GUI-to-CLI workflow map for LLM/automation")
    wf.add_argument("--format", default="json", choices=["json", "text"])
    wf.set_defaults(func=_cmd_workflows)
    ir = sub.add_parser("inspect-run", help="inspect a completed CMIG run directory")
    ir.add_argument("--run-dir", required=True, help="completed CMIG run directory")
    ir.add_argument("--format", default="json", choices=["json", "text"])
    ir.set_defaults(func=_cmd_inspect_run)
    sf = sub.add_parser("solve-fixture", help="fixture community solve → parquet+manifest (C7/P0)")
    sf.add_argument(
        "--solver", default="gurobi",
        choices=["gurobi", "osqp"], help="cmig solver 변형 (default: gurobi)",
    )
    sf.add_argument("--out", required=True, help="산출 디렉터리")
    sf.add_argument("--targets", default=None, help="target preset(scfa) → target_summary.json")
    sf.add_argument("--fva", action="store_true", help="community FVA → fva_lo/hi(gurobi)")
    sf.set_defaults(func=_cmd_solve_fixture)
    sv = sub.add_parser("solve", help="community solve --taxonomy [--medium] (C6/C7, P1)")
    sv.add_argument("--taxonomy", required=True, help="taxonomy csv (micom Community 입력)")
    sv.add_argument("--medium", default=None, help="medium spec csv/json (생략 시 default medium)")
    sv.add_argument(
        "--namespace-decisions",
        default=None,
        help="namespace decision JSON; unresolved high-confidence mapping 이 있으면 solve 차단",
    )
    sv.add_argument(
        "--allow-unknown-medium",
        action="store_true",
        help="community에 없는 medium exchange를 diagnostic에 기록하고 계속 진행",
    )
    sv.add_argument(
        "--solver", default="gurobi",
        choices=["gurobi", "osqp"], help="solver (default: gurobi)",
    )
    sv.add_argument("--tradeoff-f", type=float, default=0.5, dest="tradeoff_f", help="0<f≤1")
    sv.add_argument("--targets", default=None, help="target preset(scfa) → target_summary.json")
    sv.add_argument("--fva", action="store_true", help="community FVA → fva_lo/hi(gurobi)")
    sv.add_argument(
        "--fva-metabolites",
        default=None,
        help="comma-separated metabolites for targeted FVA, e.g. ac,etoh,glc__D",
    )
    sv.add_argument("--bounds", default=None, help="reaction bounds JSON {reaction_id: [lo, hi]}")
    sv.add_argument("--out", required=True, help="산출 디렉터리")
    sv.set_defaults(func=_cmd_solve)
    golden = sub.add_parser("golden", help="golden fixture 관리").add_subparsers(
        dest="golden_cmd", required=True
    )
    golden.add_parser("verify", help="MICOM-version golden regression gate (SC-5)").set_defaults(
        func=_cmd_golden_verify
    )
    hf = sub.add_parser("host-fixture", help="synthetic host-microbe fixture → host_summary.json")
    hf.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    hf.add_argument("--maintenance-flux", type=float, default=1.0, dest="maintenance_flux")
    hf.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout)")
    hf.set_defaults(func=_cmd_host_fixture)
    hg = sub.add_parser(
        "host-generic", help="generic host GEM smoke solve → host_generic_summary.json"
    )
    hg.add_argument(
        "--model",
        default=os.environ.get("CMIG_RECON3D_PATH", "Recon3D.xml"),
        help="SBML/XML host model path (default: $CMIG_RECON3D_PATH or ./Recon3D.xml)",
    )
    hg.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    hg.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout)")
    hg.set_defaults(func=_cmd_host_generic)
    hb = sub.add_parser(
        "host-benchmark", help="generic Human-GEM/Recon3D benchmark → host_benchmark.json"
    )
    hb.add_argument(
        "--model",
        default=os.environ.get("CMIG_RECON3D_PATH", "Recon3D.xml"),
        help="SBML/XML host model path (default: $CMIG_RECON3D_PATH or ./Recon3D.xml)",
    )
    hb.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    hb.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout)")
    hb.set_defaults(func=_cmd_host_benchmark)
    hmb = sub.add_parser(
        "host-microbe-bigg",
        help="BiGG direct host-microbe coupling -> host_microbe_bigg_summary.json",
    )
    hmb.add_argument("--host", required=True, help="host SBML/XML model path")
    hmb_src = hmb.add_mutually_exclusive_group(required=True)
    hmb_src.add_argument("--taxonomy", default=None, help="microbial MICOM taxonomy csv")
    hmb_src.add_argument("--model-dir", default=None, help="directory containing microbial GEMs")
    hmb.add_argument("--recursive", action="store_true", help="scan --model-dir recursively")
    hmb.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    hmb.add_argument("--tradeoff-f", type=float, default=0.5, dest="tradeoff_f")
    hmb.add_argument("--microbe-medium", default=None, help="optional microbial medium csv/json")
    hmb.add_argument(
        "--host-medium",
        default=None,
        help="optional host background medium csv/json; keys may be EX_*_e or BiGG ids",
    )
    hmb.add_argument("--exchange-suffix", default="_e", help="host BiGG exchange suffix")
    hmb.add_argument(
        "--host-objective",
        default=None,
        help="optional host reaction id to use as the host objective for this run",
    )
    hmb.add_argument(
        "--exclude-metabolites",
        default=None,
        help="comma-separated BiGG metabolite ids to exclude from coupling",
    )
    hmb.add_argument(
        "--include-currency-metabolites",
        action="store_true",
        help="allow h/h2o/co2 direct coupling; off by default",
    )
    hmb.add_argument(
        "--keep-host-uptake",
        action="store_true",
        help="do not close pre-existing host exchange uptake bounds before coupling",
    )
    hmb.add_argument("--out", required=True, help="output directory")
    hmb.set_defaults(func=_cmd_host_microbe_bigg)
    hs = sub.add_parser(
        "host-search-bigg",
        help="rank microbial combinations by host objective and target transfer",
    )
    hs.add_argument("--host", required=True, help="host SBML/XML model path")
    hs_src = hs.add_mutually_exclusive_group(required=True)
    hs_src.add_argument("--taxonomy", default=None, help="microbial MICOM taxonomy csv")
    hs_src.add_argument("--model-dir", default=None, help="directory containing microbial GEMs")
    hs.add_argument("--recursive", action="store_true", help="scan --model-dir recursively")
    hs.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    hs.add_argument("--min-size", type=int, default=2, dest="min_size")
    hs.add_argument("--max-size", type=int, default=2, dest="max_size")
    hs.add_argument("--top-k", type=int, default=10, dest="top_k")
    hs.add_argument("--target", default="ac", help="target transferred metabolite id")
    hs.add_argument(
        "--metric",
        default="weighted",
        choices=["weighted", "objective_value", "target_transfer"],
        help="ranking metric",
    )
    hs.add_argument("--host-weight", type=float, default=1.0, dest="host_weight")
    hs.add_argument("--target-weight", type=float, default=1.0, dest="target_weight")
    hs.add_argument("--tradeoff-f", type=float, default=0.5, dest="tradeoff_f")
    hs.add_argument("--microbe-medium", default=None, help="optional microbial medium csv/json")
    hs.add_argument("--host-medium", default=None, help="optional host background medium csv/json")
    hs.add_argument("--exchange-suffix", default="_e", help="host BiGG exchange suffix")
    hs.add_argument(
        "--host-objective",
        default=None,
        help="optional host reaction id to use as the host objective for this run",
    )
    hs.add_argument("--exclude-metabolites", default=None)
    hs.add_argument("--include-currency-metabolites", action="store_true")
    hs.add_argument("--keep-host-uptake", action="store_true")
    hs.add_argument("--out", required=True, help="output directory")
    hs.set_defaults(func=_cmd_host_search_bigg)
    sg = sub.add_parser(
        "strain-growth",
        help="estimate per-strain growth alone and inside the full community",
    )
    sg_src = sg.add_mutually_exclusive_group(required=True)
    sg_src.add_argument("--taxonomy", default=None, help="MICOM-compatible pool taxonomy csv")
    sg_src.add_argument("--model-dir", default=None, help="directory containing microbial GEMs")
    sg.add_argument("--recursive", action="store_true", help="scan --model-dir recursively")
    sg.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    sg.add_argument("--tradeoff-f", type=float, default=0.5, dest="tradeoff_f")
    sg.add_argument("--medium", default=None, help="optional community medium csv/json")
    sg.add_argument(
        "--allow-unknown-medium",
        action="store_true",
        help="record medium ids absent from the community and continue",
    )
    sg.add_argument("--out", required=True, help="output directory")
    sg.set_defaults(func=_cmd_strain_growth)
    ai = sub.add_parser(
        "abundance-impact",
        help="sweep one strain abundance and quantify growth/target exchange impact",
    )
    ai_src = ai.add_mutually_exclusive_group(required=True)
    ai_src.add_argument("--taxonomy", default=None, help="MICOM-compatible pool taxonomy csv")
    ai_src.add_argument("--model-dir", default=None, help="directory containing microbial GEMs")
    ai.add_argument("--recursive", action="store_true", help="scan --model-dir recursively")
    ai.add_argument("--member", required=True, help="member id whose abundance is swept")
    ai.add_argument(
        "--fractions",
        default="0.1,0.25,0.5,0.75",
        help="comma-separated target-member abundances",
    )
    ai.add_argument("--target", default="ac", help="target metabolite id")
    ai.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    ai.add_argument("--tradeoff-f", type=float, default=0.5, dest="tradeoff_f")
    ai.add_argument("--medium", default=None, help="optional community medium csv/json")
    ai.add_argument(
        "--allow-unknown-medium",
        action="store_true",
        help="record medium ids absent from the community and continue",
    )
    ai.add_argument("--out", required=True, help="output directory")
    ai.set_defaults(func=_cmd_abundance_impact)
    gk = sub.add_parser(
        "gene-ko-search",
        help="rank single-gene knockouts for a selected microbial combination",
    )
    gk_src = gk.add_mutually_exclusive_group(required=True)
    gk_src.add_argument("--taxonomy", default=None, help="MICOM-compatible pool taxonomy csv")
    gk_src.add_argument("--model-dir", default=None, help="directory containing microbial GEMs")
    gk.add_argument("--recursive", action="store_true", help="scan --model-dir recursively")
    gk.add_argument(
        "--members",
        required=True,
        help="comma-separated member ids in the fixed consortium to test",
    )
    gk.add_argument(
        "--member",
        default=None,
        help="member id whose genes will be knocked out; omitted screens every --members model",
    )
    gk.add_argument("--target", default="ac", help="target metabolite id")
    gk.add_argument(
        "--direction",
        default="max_secretion",
        choices=["max_secretion", "min_secretion", "max_uptake", "min_uptake"],
    )
    gk.add_argument("--growth-fraction", type=float, default=0.5, dest="growth_fraction")
    gk.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    gk.add_argument(
        "--ko-level",
        default="gene",
        choices=["gene", "reaction"],
        dest="ko_level",
        help="knock out genes via GPR (default) or reactions directly",
    )
    gk.add_argument(
        "--genes",
        default=None,
        help="comma-separated gene ids to evaluate; requires --member and --ko-level gene",
    )
    gk.add_argument(
        "--reactions",
        default=None,
        help="comma-separated reaction ids to evaluate; requires --member and --ko-level reaction",
    )
    gk.add_argument(
        "--gene-selection",
        default="id",
        choices=["id", "random"],
        dest="gene_selection",
        help="how to pick targets when not listed: id order (default) or deterministic random",
    )
    gk.add_argument("--seed", type=int, default=0, help="seed for --gene-selection random")
    gk.add_argument(
        "--max-genes",
        type=int,
        default=20,
        dest="max_genes",
        help="max knockout targets per member when not listed explicitly; 0 means all "
        "(truncation is reported as a warning, never silent)",
    )
    gk.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="parallel evaluation workers (default 1; >1 speedup depends on solver thread-safety)",
    )
    gk.add_argument("--top-k", type=int, default=20, dest="top_k")
    gk.add_argument("--out", required=True, help="output directory")
    gk.set_defaults(func=_cmd_gene_ko_search)
    df = sub.add_parser("dfba-fixture", help="e_coli_core glucose dFBA → timecourse.parquet")
    df.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    df.add_argument("--t-end", type=float, default=1.0, dest="t_end")
    df.add_argument("--dt", type=float, default=0.1)
    df.add_argument("--initial-biomass", type=float, default=0.01, dest="initial_biomass")
    df.add_argument("--glucose", type=float, default=10.0)
    df.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout summary)")
    df.set_defaults(func=_cmd_dfba_fixture)
    df_user = sub.add_parser(
        "dfba",
        help="run well-mixed dFBA on a user SBML model -> timecourse/figure/summary",
    )
    df_user.add_argument("--model", required=True, help="SBML model file")
    df_user.add_argument("--solver", default="gurobi", choices=["gurobi", "osqp"], help="LP solver")
    df_user.add_argument("--t-end", type=float, default=5.0, dest="t_end")
    df_user.add_argument("--dt", type=float, default=0.1)
    df_user.add_argument("--initial-biomass", type=float, default=0.01, dest="initial_biomass")
    df_user.add_argument(
        "--initial",
        default=None,
        dest="initial_concentrations",
        help=(
            "comma-separated exchange concentrations, e.g. EX_glc__D_e=10,EX_o2_e=20; "
            "default tracks glucose, oxygen, acetate, and D-lactate when present"
        ),
    )
    df_user.add_argument(
        "--vmax",
        default=None,
        help="optional comma-separated uptake maxima, e.g. EX_glc__D_e=10",
    )
    df_user.add_argument("--km", type=float, default=0.01)
    df_user.add_argument("--min-dt", type=float, default=1e-4, dest="min_dt")
    df_user.add_argument("--growth-floor", type=float, default=1e-6, dest="growth_floor")
    df_user.add_argument("--out", required=True, help="output directory")
    df_user.set_defaults(func=_cmd_dfba)
    spatial = sub.add_parser(
        "spatial-preview",
        help="COMETS-inspired 2D medium source/sink diffusion preview -> heatmap",
    )
    spatial.add_argument("--metabolite", default="EX_glc__D_e")
    spatial.add_argument("--width", type=int, default=32)
    spatial.add_argument("--height", type=int, default=32)
    spatial.add_argument("--steps", type=int, default=80)
    spatial.add_argument("--dt", type=float, default=0.1)
    spatial.add_argument("--diffusion", type=float, default=0.15)
    spatial.add_argument("--initial-value", type=float, default=0.0, dest="initial_value")
    spatial.add_argument(
        "--source-edge",
        default="left",
        choices=["left", "right", "top", "bottom", "center", "none"],
        dest="source_edge",
    )
    spatial.add_argument("--source-value", type=float, default=10.0, dest="source_value")
    spatial.add_argument(
        "--sink-edge",
        default="right",
        choices=["left", "right", "top", "bottom", "center", "none"],
        dest="sink_edge",
    )
    spatial.add_argument("--sink-value", type=float, default=0.0, dest="sink_value")
    spatial.add_argument("--store-every", type=int, default=10, dest="store_every")
    spatial.add_argument("--out", required=True, help="output directory")
    spatial.set_defaults(func=_cmd_spatial_preview)
    sp = sub.add_parser(
        "search",
        help="user model-pool target production search -> rankings/plot/summary",
    )
    src = sp.add_mutually_exclusive_group(required=True)
    src.add_argument("--taxonomy", default=None, help="MICOM-compatible pool taxonomy csv")
    src.add_argument(
        "--model-dir",
        default=None,
        help="directory containing SBML/JSON/MAT GEM files",
    )
    sp.add_argument("--recursive", action="store_true", help="scan --model-dir recursively")
    sp.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    sp.add_argument("--target", default="but", help="target metabolite id, e.g. but")
    sp.add_argument(
        "--direction",
        default="max_secretion",
        choices=["max_secretion", "min_secretion", "max_uptake", "min_uptake"],
    )
    sp.add_argument("--growth-fraction", type=float, default=0.5, dest="growth_fraction")
    sp.add_argument("--min-size", type=int, default=2, dest="min_size")
    sp.add_argument("--max-size", type=int, default=2, dest="max_size")
    sp.add_argument("--strategy", default="auto", choices=["auto", "exhaustive", "random", "ga"])
    sp.add_argument("--n-samples", type=int, default=100, dest="n_samples")
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--top-k", type=int, default=10, dest="top_k")
    sp.add_argument(
        "--robustness-fva",
        action="store_true",
        help="add target FVA range for each evaluated candidate",
    )
    sp.add_argument("--medium", default=None, help="optional medium csv/json")
    sp.add_argument("--allow-unknown-medium", action="store_true")
    sp.add_argument("--out", required=True, help="output directory")
    sp.set_defaults(func=_cmd_search)
    se = sub.add_parser("search-fixture", help="3-member target-max search → search_summary.json")
    se.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    se.add_argument("--metabolite", default="ac", help="target metabolite id")
    se.add_argument("--growth-fraction", type=float, default=0.5, dest="growth_fraction")
    se.add_argument("--top-k", type=int, default=3, dest="top_k")
    se.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout)")
    se.set_defaults(func=_cmd_search_fixture)
    sa = sub.add_parser(
        "search-advanced-fixture",
        help="fixture advanced search with strategy/Pareto/GA → search_advanced_summary.json",
    )
    sa.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    sa.add_argument("--metabolites", default="ac,but", help="comma-separated target metabolites")
    sa.add_argument("--growth-fraction", type=float, default=0.5, dest="growth_fraction")
    sa.add_argument("--min-size", type=int, default=2, dest="min_size")
    sa.add_argument("--max-size", type=int, default=2, dest="max_size")
    sa.add_argument("--strategy", default="auto", choices=["auto", "exhaustive", "ga"])
    sa.add_argument("--seed", type=int, default=0)
    sa.add_argument("--top-k", type=int, default=3, dest="top_k")
    sa.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout)")
    sa.set_defaults(func=_cmd_search_advanced_fixture)
    st = sub.add_parser("stats-demo", help="deterministic stats demo → stats_summary.json")
    st.add_argument("--fdr-method", default="fdr_bh", choices=["fdr_bh", "fdr_by"])
    st.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout)")
    st.set_defaults(func=_cmd_stats_demo)
    ss = sub.add_parser("stats-sweep", help="sweep.parquet → stats_sweep_summary.json")
    ss.add_argument("--sweep", required=True, help="sweep.parquet path")
    ss.add_argument("--metric", default="growth")
    ss.add_argument("--group-axis", default="solver", dest="group_axis")
    ss.add_argument("--parametric", action="store_true")
    ss.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout)")
    ss.set_defaults(func=_cmd_stats_sweep)
    ns = sub.add_parser("namespace-suggest", help="model exchange namespace decision 초안 생성")
    ns.add_argument("--model", required=True, help="SBML/JSON/MAT model path")
    ns.add_argument("--known-targets", default=None, help="known target metabolite id 목록(txt)")
    ns.add_argument("--source-namespace", default="model")
    ns.add_argument("--target-namespace", default="bigg")
    ns.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout)")
    ns.set_defaults(func=_cmd_namespace_suggest)
    mr = sub.add_parser("model-review", help="user-provided GEM import review")
    mr.add_argument("--model", required=True, help="SBML/JSON/MAT model path")
    mr.add_argument("--known-targets", default=None, help="known target metabolite id 목록(txt)")
    mr.add_argument("--source-namespace", default="model")
    mr.add_argument("--target-namespace", default="bigg")
    mr.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout)")
    mr.set_defaults(func=_cmd_model_review)
    sw = sub.add_parser("sweep-fixture", help="fixture parameter sweep → sweep.parquet")
    sw.add_argument("--tradeoff-fs", default="0.3,0.5", dest="tradeoff_fs")
    sw.add_argument("--solvers", default="gurobi")
    sw.add_argument("--metric", default="growth")
    sw.add_argument("--out", required=True, help="산출 디렉터리")
    sw.set_defaults(func=_cmd_sweep_fixture)
    us = sub.add_parser("sweep", help="taxonomy 기반 parameter sweep → sweep.parquet + runs/")
    us.add_argument("--taxonomy", required=True, help="taxonomy csv (micom Community 입력)")
    us.add_argument("--tradeoff-fs", default="0.3,0.5", dest="tradeoff_fs")
    us.add_argument("--solvers", default="gurobi")
    us.add_argument("--mediums", default=None, help="comma-separated medium csv/json paths")
    us.add_argument(
        "--member-sets",
        default=None,
        help="semicolon-separated member sets, e.g. 'A+B;A+C' (default: full taxonomy)",
    )
    us.add_argument(
        "--abundance-variants",
        default=None,
        help="comma-separated csv/json files with id,abundance overrides",
    )
    us.add_argument(
        "--bounds-variants",
        default=None,
        help="comma-separated JSON files {reaction_id: [lo, hi]}",
    )
    us.add_argument("--namespace-decisions", default=None)
    us.add_argument("--allow-unknown-medium", action="store_true")
    us.add_argument("--fva", action="store_true", help="include community FVA for each condition")
    us.add_argument(
        "--fva-metabolites",
        default=None,
        help="comma-separated metabolites for targeted FVA, e.g. ac,etoh,glc__D",
    )
    us.add_argument("--metric", default="growth")
    us.add_argument("--out", required=True, help="산출 디렉터리")
    us.set_defaults(func=_cmd_sweep)
    sb = sub.add_parser("sandbox-fixture", help="fixture bound sandbox preview/commit")
    sb.add_argument("--reaction", required=True, help="reaction id to constrain")
    sb.add_argument("--lower", type=float, required=True)
    sb.add_argument("--upper", type=float, required=True)
    sb.add_argument("--solver", default="gurobi", choices=["gurobi", "osqp"])
    sb.add_argument("--commit", action="store_true")
    sb.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout)")
    sb.set_defaults(func=_cmd_sandbox_fixture)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
