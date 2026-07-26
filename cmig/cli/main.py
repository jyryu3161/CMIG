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
from cmig.core.manifest import DEFAULT_FLOAT_DECIMALS
from cmig.core.solver import capability_matrix
from cmig.core.targets import TARGET_PRESETS
from cmig.io.atomic import atomic_write_text

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
        "required_args": [
            "--host",
            "--model-dir or --taxonomy",
            "--microbial-biomass-gdw",
            "--host-biomass-gdw",
            "--biomass-basis-kind",
            "--biomass-basis-source",
            "--out",
        ],
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
            "--model-dir models --microbial-biomass-gdw \"$MICROBIAL_BIOMASS_GDW\" "
            "--host-biomass-gdw \"$HOST_BIOMASS_GDW\" --biomass-basis-kind measured "
            "--biomass-basis-source \"$BIOMASS_BASIS_SOURCE\" --recursive "
            "--out runs/host_microbe"
        ),
    },
    {
        "gui_surface": "Host / Knockout Impact",
        "cli_command": "cmig host-ko-impact",
        "purpose": (
            "Quantify how a microbial gene/reaction knockout changes the host objective, "
            "against an identically configured baseline."
        ),
        "required_args": [
            "--host", "--model-dir or --taxonomy", "--member",
            "--genes or --reactions", "--microbial-biomass-gdw", "--host-biomass-gdw",
            "--biomass-basis-kind", "--biomass-basis-source", "--out",
        ],
        "common_options": [
            "--ko-level", "--target", "--interface-map", "--host-medium", "--microbe-medium",
            "--host-objective", "--keep-host-uptake",
        ],
        "key_outputs": ["host_ko_impact_summary.json", "host_ko_impact.csv"],
        "example": (
            "uv run cmig host-ko-impact --host host.xml --model-dir models --member iHN637 "
            "--ko-level reaction --reactions ACKr,PTAr --target ac "
            "--microbial-biomass-gdw 1.0 --host-biomass-gdw 1.0 --biomass-basis-kind measured "
            "--biomass-basis-source \"$BIOMASS_BASIS_SOURCE\" --out runs/host_ko"
        ),
    },
    {
        "gui_surface": "Host / Rank Combinations",
        "cli_command": "cmig host-search-bigg",
        "purpose": "Rank microbial combinations by host objective and target transfer.",
        "required_args": [
            "--host",
            "--model-dir or --taxonomy",
            "--microbial-biomass-gdw",
            "--host-biomass-gdw",
            "--biomass-basis-kind",
            "--biomass-basis-source",
            "--out",
        ],
        "common_options": [
            "--min-size",
            "--max-size",
            "--target",
            "--metric",
            "--host-weight",
            "--target-weight",
            "--host-reference",
            "--target-reference",
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
            "--model-dir models --target ac --metric target_transfer "
            "--microbial-biomass-gdw \"$MICROBIAL_BIOMASS_GDW\" "
            "--host-biomass-gdw \"$HOST_BIOMASS_GDW\" --biomass-basis-kind measured "
            "--biomass-basis-source \"$BIOMASS_BASIS_SOURCE\" --out runs/host_search"
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
    ("host_ko_impact_summary.json", "host_ko_impact"),
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
    # B7: inspect-run 이 kind=unknown 을 돌려주던 워크플로 (검증 단계가 "이 run 이 뭔지 모름"을
    # 보고하면 안 된다).
    ("model_quality.json", "model_quality"),
    ("host_map_summary.json", "host_exchange_map"),
    ("dfba_sensitivity.json", "dfba_sensitivity"),
    ("publication_benchmark.json", "publication_benchmark"),
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
    try:
        payload = _inspect_run_dir(run_dir)
    except CorruptRunArtifactError as e:
        print(f"{e} (in {run_dir})", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False))
        return 0
    print(f"run_dir: {payload['run_dir']}")
    print(f"kind: {payload['kind']}")
    print(f"status: {payload['status']} (source: {payload['status_source']})")
    if payload["summary_file"]:
        print(f"summary_file: {payload['summary_file']}")
    if payload["run_hash"]:
        print(f"run_hash: {payload['run_hash']}")
    print("artifacts:")
    for artifact in payload["artifacts"]:
        print(f"  - {artifact}")
    return 0


def _inspect_run_dir(run_dir: Path) -> dict[str, Any]:
    manifest = _load_json_object(run_dir / "manifest.json") or {}
    # A workflow manifest names its own kind. Without this check the `manifest.json ->
    # community_solve` entry below would relabel every workflow run as a community solve, because
    # it is the first entry in RUN_SUMMARY_FILES.
    workflow_kind = (
        _string_or_none(manifest.get("workflow_kind"))
        if manifest.get("manifest_scope") == "workflow" else None
    )

    kind = "unknown"
    summary_file: str | None = None
    summary: dict[str, Any] = {}
    for filename, candidate_kind in RUN_SUMMARY_FILES:
        if filename == "manifest.json" and workflow_kind:
            continue          # not a community solve; the workflow manifest says what it is
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
    if workflow_kind:
        kind = workflow_kind

    status, status_source = _resolve_run_status(summary, manifest)
    run_hash = _string_or_none(summary.get("run_hash")) or _string_or_none(manifest.get("run_hash"))
    return {
        "schema_version": "1.0",
        "run_dir": str(run_dir),
        "kind": kind,
        "status": status,
        "status_source": status_source,
        "summary_file": summary_file,
        "run_hash": run_hash,
        "artifacts": _list_run_artifacts(run_dir),
        "manifest": _compact_manifest(manifest),
        "summary_keys": sorted(str(key) for key in summary.keys()),
    }


def _resolve_run_status(
    summary: dict[str, Any], manifest: dict[str, Any]
) -> tuple[str, str]:
    """(status, status_source) — 요약이 status 를 안 쓰더라도 "unknown" 으로 끝내지 않는다 (B7).

    inspect-run 은 SKILL.md 가 모든 run 에 요구하는 검증 단계다. 그 단계가 성공한 run 을
    "unknown" 으로 보고하면 검증이 성립하지 않는다. 명시 status 가 있으면 그대로 쓰고, 없으면
    요약/manifest 안의 하위 신호에서 **보수적으로** 파생한다(모르면 ok 라고 하지 않는다).
    """
    # A workflow manifest's status is the derived run-level tier (ok/degraded/failed), so it wins
    # over a summary's raw solve status. Round-2 F11 found `inspect-run` emitting "optimal" and
    # "completed" alongside that vocabulary, which breaks any gate written against it.
    if manifest.get("manifest_scope") == "workflow":
        manifest_status = _string_or_none(manifest.get("status"))
        if manifest_status:
            return manifest_status, "manifest"
    explicit = _string_or_none(summary.get("status")) or _string_or_none(manifest.get("status"))
    if explicit:
        return _normalize_run_status(explicit), "summary"

    ranked = summary.get("top_ranked")
    if isinstance(ranked, list):
        if not ranked:
            return "failed", "derived"
        bad = [
            row for row in ranked
            if isinstance(row, dict) and _string_or_none(row.get("status")) not in (None, "optimal")
        ]
        return ("degraded" if bad else "ok"), "derived"

    reports = summary.get("reports")
    if isinstance(reports, list) and reports:
        bad_reports = [
            row for row in reports
            if isinstance(row, dict)
            and _string_or_none(row.get("solve_status")) not in (None, "optimal")
        ]
        return ("degraded" if bad_reports else "ok"), "derived"

    if manifest:
        # solve manifest 는 status 대신 diagnostic 을 쓴다 (schema v2.0).
        return ("ok" if manifest.get("diagnostic") in (None, "") else "degraded"), "derived"

    if summary:
        return "ok", "derived"
    return "unknown", "unknown"


class CorruptRunArtifactError(ValueError):
    """A run artifact exists but cannot be read as the JSON object it is supposed to be."""


def _load_json_object(path: Path) -> dict[str, Any] | None:
    """Load a run artifact as a JSON object. ``None`` only when the file is absent.

    R5-P3 (codex F11): this used to collapse "absent", "unreadable", "syntactically invalid" and
    "valid JSON of the wrong type" into a single ``None``, so ``inspect-run`` reported a corrupt
    manifest as an unknown run and exited 0 — a directory that cannot be trusted looked exactly
    like one that simply predates manifests. Absence stays ``None`` because the caller genuinely
    probes for optional files; corruption is now an error.
    """
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise CorruptRunArtifactError(f"invalid {path.name}: {e}") from e
    if not isinstance(loaded, dict):
        raise CorruptRunArtifactError(
            f"invalid {path.name}: expected a JSON object, got {type(loaded).__name__}"
        )
    return loaded


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
        "manifest_scope",
        "workflow_kind",
        "run_hash",
        "status",
        "artifacts",
        "inputs",
        "solver",
        "software",
        # Workflow envelope: the ordered component names, and the determining values themselves.
        # Surfacing these is the point of the manifest — a reader must be able to see what the
        # answer depended on without opening the file.
        "hash_components",
        "components",
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
    try:
        taxonomy = _read_taxonomy_csv(pd, tax_path)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    # AF-5: taxonomy 필수 컬럼 검증(micom Community 입력 계약) — solve 전 fail-fast.
    missing_cols = {"id", "file"} - set(taxonomy.columns)
    if missing_cols:
        print(f"taxonomy 필수 컬럼 누락: {sorted(missing_cols)} (필요: id, file)", file=sys.stderr)
        return 2
    try:
        taxonomy = _resolve_taxonomy_model_paths(taxonomy, tax_path)
    except ValueError as e:
        print(str(e), file=sys.stderr)
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
            namespace_policy=(
                "assume_bigg" if args.assume_bigg_namespace else "require_reviewed"
            ),
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
    """MICOM-version + published-run_hash golden regression gate (SC-5)."""
    try:
        from cmig.golden_fixture import verify_golden_versions
    except ImportError:  # pragma: no cover
        print("golden verify 는 엔진 stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    report = verify_golden_versions()
    all_ok = True
    print("MICOM-version + run_hash golden regression (SC-5):")
    for solver, r in report.items():
        mark = "OK " if r["ok"] else "MISMATCH"
        all_ok = all_ok and bool(r["ok"])
        print(f"  [{mark}] {solver:24} golden={r['recorded']} installed={r['installed']}")
        # R5-P3: the hash is the thing the fixture exists to protect, so it is gated and shown.
        published = str(r["published_run_hash"] or "-")
        hash_mark = "OK " if r["hash_ok"] else "MOVED"
        print(f"      [{hash_mark}] run_hash {published[:16]}…")
        if not r["hash_ok"]:
            print(f"            recomputed {str(r['recomputed_run_hash'])[:16]}…")
    if not all_ok:
        print(
            "→ golden 재캡처/재검증 필요 (python -m cmig.golden_fixture)", file=sys.stderr
        )
        return 2
    print("→ 모든 golden 이 설치 MICOM 버전·published run_hash 와 일치 (승격 가능)")
    return 0


def _write_json_or_print(payload: dict[str, Any], out: str | None, filename: str) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
    if out is None:
        print(text)
        return
    d = Path(out)
    d.mkdir(parents=True, exist_ok=True)
    # R5-P3 V3: publish atomically so a failed re-run cannot truncate the previous artifact.
    atomic_write_text(d / filename, text + "\n")
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
        "lumen_uptake_ranges": result.lumen_uptake_ranges,
        "microbe_to_host": impact.microbe_to_host,
        "microbe_to_host_ranges": impact.microbe_to_host_ranges,
        "ambiguous_metabolites": impact.ambiguous_metabolites,
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
        interface_map = _load_host_interface_map(
            args.interface_map, accept_unreviewed=args.accept_unreviewed_map
        )
        exclude = set() if args.include_currency_metabolites else {"h", "h2o", "co2"}
        if args.exclude_metabolites:
            exclude.update(
                _parse_csv_strings(args.exclude_metabolites, flag="--exclude-metabolites")
            )
        result = run_bigg_host_microbe(
            taxonomy,
            host,
            microbial_biomass_gdw=args.microbial_biomass_gdw,
            host_biomass_gdw=args.host_biomass_gdw,
            biomass_basis_kind=args.biomass_basis_kind,
            biomass_basis_source=args.biomass_basis_source,
            solver=args.solver,
            tradeoff_f=args.tradeoff_f,
            microbe_medium=microbe_medium,
            host_medium=host_medium,
            interface_map=interface_map,
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
    host_run_status = _worst_status(
        _run_status_from_solve(str(result.community_status)),
        _run_status_from_solve(str(result.host_result.status)),
    )
    _emit_workflow_manifest(
        out,
        "host_microbe_bigg",
        lambda: {
            **_workflow_base(
                "host_microbe_bigg", args, taxonomy,
                medium=_host_medium_component(args),
            ),
            # R5-P3: NOT rounded. An earlier revision rounded this on the theory that
            # coupling_scale is solve-derived; it is not — core.host._coupling_scale builds it
            # from --microbial-biomass-gdw / --host-biomass-gdw before any solve runs, and
            # microbe_to_host_ratio is a pure function of those two. Rounding an argv-supplied,
            # answer-determining value is the CC-4 collision, not a fix for it.
            "abundances": {
                str(k): v
                for k, v in sorted((result.coupling_scale.__dict__ or {}).items())
                if isinstance(v, (int, float))
            } if result.coupling_scale else {},
            "tradeoff_f": float(args.tradeoff_f),
            "host_spec": _host_spec_component(args, interface_map),
            "biomass_basis": _biomass_basis_component(args),
            "flux_normalization_method": "pfba",
            "solve_run_hash": None,
        },
        status=host_run_status,
        artifacts=["host_microbe_bigg_summary.json", "interaction_edges.csv"],
        warnings=list(result.warnings),
        summary={
            "community_growth": _finite_or_none(float(result.community_growth)),
            "host_objective": _finite_or_none(float(result.host_result.biomass)),
            "host_status": result.host_result.status,
            "n_matched_exchanges": len(result.matched_exchanges),
        },
    )
    return _exit_code_for_status(host_run_status, args)


def _cmd_host_map(args: argparse.Namespace) -> int:
    """Host-microbe exchange mapping wizard: pre-flight matched/unmatched report."""
    try:
        import pandas as pd
        from cobra.io import read_sbml_model

        from cmig.core.host_map import build_host_map
        from cmig.core.model_pool import taxonomy_from_model_dir
    except ImportError:
        print("host-map requires the engine stack: uv sync --extra engine", file=sys.stderr)
        return 2
    try:
        host_path = Path(args.host)
        if not host_path.exists():
            raise ValueError(f"host model file not found: {host_path}")
        if bool(args.taxonomy) == bool(args.model_dir):
            raise ValueError("provide exactly one of --taxonomy or --model-dir")
        tax_dir: Path | None = None
        if args.taxonomy:
            tax_path = Path(args.taxonomy)
            if not tax_path.exists():
                raise ValueError(f"taxonomy file not found: {tax_path}")
            taxonomy = pd.read_csv(tax_path)
            tax_dir = tax_path.parent
        else:
            taxonomy = taxonomy_from_model_dir(args.model_dir, recursive=args.recursive)
        missing_cols = {"id", "file"} - set(taxonomy.columns)
        if missing_cols:
            raise ValueError(f"taxonomy missing required columns: {sorted(missing_cols)}")
        host = read_sbml_model(str(host_path))
        member_models = {}
        for rec in taxonomy.to_dict("records"):
            mp = Path(str(rec["file"]))
            if not mp.exists() and not mp.is_absolute() and tax_dir is not None:
                mp = tax_dir / mp
            if not mp.exists():
                raise ValueError(f"member model file not found: {rec['file']}")
            member_models[str(rec["id"])] = read_sbml_model(str(mp))
        result = build_host_map(host, member_models)
        out = Path(args.out)
        _write_host_map_outputs(result, out)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"failed to write host-map outputs: {e}", file=sys.stderr)
        return 2
    print(
        f"host-map complete: {result.n_exact} exact / {result.n_annotation} annotation / "
        f"{result.n_normalized} normalized / "
        f"{result.n_unmatched} unmatched (of {result.n_microbial_secretions} secretions) -> {out}"
    )
    return 0


def _write_host_map_outputs(result: Any, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "host_exchange_map.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "metabolite", "microbial_exchange", "secreting_members",
                "host_exchange", "match_type", "host_can_uptake", "suggestion",
            ],
        )
        writer.writeheader()
        for e in result.entries:
            writer.writerow({
                "metabolite": e.metabolite,
                "microbial_exchange": e.microbial_exchange,
                "secreting_members": ";".join(e.secreting_members),
                "host_exchange": e.host_exchange or "",
                "match_type": e.match_type,
                "host_can_uptake": e.host_can_uptake,
                "suggestion": e.suggestion,
            })
    # A-B8: only EXACT id matches go into interface_map. Annotation/normalized matches are
    # computational guesses — round-2 found three D<->L stereoisomer swaps among them
    # (arab__D_e -> EX_arab__L_e, glu__D_e -> EX_glu__L_e, pser__D_e -> EX_pser__L_e), which are
    # chemically distinct metabolites. Putting them in the same flat dict as the 170 exact matches
    # meant passing the file through unedited silently coupled the wrong molecules.
    interface_map = {
        e.metabolite: e.host_exchange for e in result.entries if e.match_type == "exact"
    }
    needs_review = {
        e.metabolite: {
            "host_exchange": e.host_exchange,
            "match_type": e.match_type,
            "reason": e.suggestion,
        }
        for e in result.entries if e.match_type in ("annotation", "normalized")
    }
    with open(out / "host_interface_map.json", "w") as f:
        json.dump(
            {
                "_comment": "interface_map holds EXACT id matches only and is safe to pass "
                "through. needs_review holds annotation/normalized guesses: confirm each one and "
                "move it into interface_map before coupling. Coupling commands refuse a map that "
                "still carries needs_review entries unless --accept-unreviewed-map is given.",
                "interface_map": interface_map,
                "needs_review": needs_review,
                "unmatched": [e.metabolite for e in result.entries
                              if e.match_type == "unmatched"],
            },
            f, indent=2, sort_keys=True,
        )
    summary = {
        "kind": "host_exchange_map",
        "n_microbial_secretions": result.n_microbial_secretions,
        "n_exact": result.n_exact,
        "n_annotation": result.n_annotation,
        "n_normalized": result.n_normalized,
        "n_unmatched": result.n_unmatched,
        "n_host_uptake_capable": result.n_host_uptake_capable,
        "entries": [
            {
                "metabolite": e.metabolite,
                "microbial_exchange": e.microbial_exchange,
                "secreting_members": e.secreting_members,
                "host_exchange": e.host_exchange,
                "match_type": e.match_type,
                "host_can_uptake": e.host_can_uptake,
                "suggestion": e.suggestion,
            }
            for e in result.entries
        ],
        "warnings": result.warnings,
    }
    with open(out / "host_map_summary.json", "w") as f:
        json.dump(summary, f, indent=2, allow_nan=False)


def _cmd_render_figure(args: argparse.Namespace) -> int:
    """Render a completed run's tidy profile to a publication figure via the R renderer.

    Renderer policy: `r` forces the R(ggplot2) path (hard error if R fails), `matplotlib`
    forces the Python fallback, `auto` (default) uses R when Rscript is available and falls
    back to matplotlib on any R failure (e.g. missing .Rlib packages).
    """
    try:
        from cmig.core.tidy import TidyBundle
        from cmig.render.client import (
            FigureSpec,
            RenderClient,
            RenderError,
            render_profile,
            rscript_available,
        )
    except ImportError:
        print("render-figure requires the render extra: uv sync --extra render", file=sys.stderr)
        return 2

    run_dir = Path(args.run_dir)
    if not (run_dir / "profile.parquet").exists():
        print(
            f"no profile.parquet in {run_dir} — render-figure needs a tidy-profile run "
            "(e.g. solve/solve-fixture output)",
            file=sys.stderr,
        )
        return 2
    try:
        bundle = TidyBundle.read(run_dir)
    except (OSError, ValueError) as e:
        # R5-P3 (codex F10): only OSError was caught, so a corrupt parquet (pyarrow.ArrowInvalid)
        # or a wrong schema (tidy.TidyContractError) reached the user as a raw traceback on a
        # default, non-debug path. Both subclass ValueError.
        print(f"failed to read run {run_dir}: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    spec = FigureSpec(
        title=args.title, width_in=args.width, height_in=args.height, dpi=args.dpi,
        format=args.format, seed=args.seed, journal_preset=args.journal_preset,
    )
    try:
        # P1-F: actually APPLY the preset (previously stored as metadata and ignored, so the
        # sidecar claimed e.g. "nature" while the figure stayed 6.0x4.0in at 600 dpi). An unknown
        # name now fails validation instead of being recorded verbatim.
        if args.journal_preset != "default":
            spec = spec.for_journal(args.journal_preset)
        spec.validate()
    except RenderError as e:
        print(str(e), file=sys.stderr)
        return 2

    out = Path(args.out)
    forced_matplotlib = RenderClient(rscript="")   # empty rscript → available() False → fallback
    try:
        if args.renderer == "matplotlib":
            render_profile(bundle, spec, out, client=forced_matplotlib)
            used = "matplotlib"
        elif args.renderer == "r":
            if not rscript_available():
                print("Rscript not found; install R or use --renderer matplotlib", file=sys.stderr)
                return 2
            render_profile(bundle, spec, out)
            used = "R (ggplot2)"
        else:  # auto
            if rscript_available():
                try:
                    render_profile(bundle, spec, out)
                    used = "R (ggplot2)"
                except RenderError as e:
                    print(f"R render failed ({e}); falling back to matplotlib", file=sys.stderr)
                    render_profile(bundle, spec, out, client=forced_matplotlib)
                    used = "matplotlib (R fallback)"
            else:
                render_profile(bundle, spec, out, client=forced_matplotlib)
                used = "matplotlib (no Rscript)"
    except RenderError as e:
        print(f"render failed: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"failed to write figure: {e}", file=sys.stderr)
        return 2
    print(f"render-figure complete [{used}, {spec.format}] -> {out}")
    return 0


def _weighted_host_search_score(
    host_objective: float,
    target_transfer: float,
    *,
    host_weight: float | None,
    target_weight: float | None,
    host_reference: float | None,
    target_reference: float | None,
) -> float:
    """Combine unlike host/flux quantities only after explicit nondimensionalization."""
    values = {
        "host_weight": host_weight,
        "target_weight": target_weight,
        "host_reference": host_reference,
        "target_reference": target_reference,
    }
    invalid = [
        name
        for name, value in values.items()
        if value is None or not math.isfinite(float(value)) or float(value) <= 0.0
    ]
    if invalid:
        raise ValueError(
            "weighted host search requires positive finite --host-weight, "
            "--target-weight, --host-reference, and --target-reference; invalid: "
            + ", ".join(invalid)
        )
    assert host_weight is not None
    assert target_weight is not None
    assert host_reference is not None
    assert target_reference is not None
    return (
        host_weight * host_objective / host_reference
        + target_weight * target_transfer / target_reference
    )


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
        if args.metric == "weighted":
            _weighted_host_search_score(
                0.0,
                0.0,
                host_weight=args.host_weight,
                target_weight=args.target_weight,
                host_reference=args.host_reference,
                target_reference=args.target_reference,
            )
        host_model = read_sbml_model(str(host_path))
        _apply_host_objective(host_model, args.host_objective)
        microbe_medium = load_medium(args.microbe_medium) if args.microbe_medium else None
        host_medium = load_medium(args.host_medium).uptake if args.host_medium else None
        interface_map = _load_host_interface_map(
            args.interface_map, accept_unreviewed=args.accept_unreviewed_map
        )
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
                    microbial_biomass_gdw=args.microbial_biomass_gdw,
                    host_biomass_gdw=args.host_biomass_gdw,
                    biomass_basis_kind=args.biomass_basis_kind,
                    biomass_basis_source=args.biomass_basis_source,
                    solver=args.solver,
                    tradeoff_f=args.tradeoff_f,
                    microbe_medium=microbe_medium,
                    host_medium=host_medium,
                    interface_map=interface_map,
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
                    score = _weighted_host_search_score(
                        host_objective,
                        target_transfer,
                        host_weight=args.host_weight,
                        target_weight=args.target_weight,
                        host_reference=args.host_reference,
                        target_reference=args.target_reference,
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
        # B1 (silent half): 평가 실패 후보는 score=0 으로 랭킹에 섞이면 "host objective 0" 이라는
        # 실재하는 생물학적 결과와 구별되지 않는다. 랭킹에서 분리해 별도 블록으로 보고한다.
        ranked_rows = [row for row in rows if row["evaluation_status"] == "ok"]
        unevaluated_rows = [row for row in rows if row["evaluation_status"] != "ok"]
        ranked_rows.sort(key=lambda row: (-float(row["score"]), tuple(row["members"])))
        unevaluated_rows.sort(key=lambda row: tuple(row["members"]))
        search_warnings: list[str] = []
        if unevaluated_rows:
            search_warnings.append(
                f"{len(unevaluated_rows)} of {len(candidates)} candidates could not be "
                "evaluated and are excluded from the ranking (see unevaluated): "
                + ", ".join("+".join(row["members"]) for row in unevaluated_rows)
            )
        if not ranked_rows:
            search_warnings.append("no candidate was evaluable; the ranking is empty")
        out = Path(args.out)
        _write_host_search_bigg_outputs(
            ranked_rows[: args.top_k],
            out,
            target=args.target,
            metric=args.metric,
            n_candidates_total=len(candidates),
            n_candidates_evaluated=len(ranked_rows),
            n_candidates_failed=len(unevaluated_rows),
            unevaluated=unevaluated_rows,
            warnings=search_warnings,
            ranking_parameters={
                "host_weight": args.host_weight,
                "target_weight": args.target_weight,
                "host_reference": args.host_reference,
                "target_reference": args.target_reference,
            },
            biomass_basis={
                "microbial_biomass_gdw": args.microbial_biomass_gdw,
                "host_biomass_gdw": args.host_biomass_gdw,
                "kind": args.biomass_basis_kind,
                "source": args.biomass_basis_source,
            },
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"failed to write host-search outputs: {e}", file=sys.stderr)
        return 2
    print(f"host-search BiGG complete ({args.metric}, target={args.target}) -> {out}")
    print(f"  ranked: {len(ranked_rows)}/{len(candidates)} candidates")
    if ranked_rows:
        best = ranked_rows[0]
        print(
            f"  best: {'+'.join(best['members'])} score={float(best['score']):.4g} "
            f"host_objective={float(best['host_objective_value']):.4g} "
            f"target_transfer={float(best['target_transfer']):.4g}"
        )
    for warning in search_warnings:
        print(f"  warning: {warning}")
    _emit_workflow_manifest(
        out,
        "host_search_bigg",
        lambda: {
            **_workflow_base(
                "host_search_bigg", args, taxonomy,
                medium=_host_medium_component(args),
            ),
            "tradeoff_f": float(args.tradeoff_f),
            "target_spec": {
                "target": args.target,
                "metric": args.metric,
                "host_weight": args.host_weight,
                "target_weight": args.target_weight,
                "host_reference": args.host_reference,
                "target_reference": args.target_reference,
            },
            "search_spec": {
                "min_size": args.min_size,
                "max_size": args.max_size,
                "top_k": args.top_k,
                "n_candidates_total": len(candidates),
            },
            "host_spec": _host_spec_component(args, interface_map),
            "biomass_basis": _biomass_basis_component(args),
        },
        status=_worst_status(
            "ok" if ranked_rows else "failed",
            "degraded" if unevaluated_rows else "ok",
        ),
        artifacts=["host_search_summary.json", "host_search_rankings.csv"],
        warnings=search_warnings,
        summary={
            "n_candidates_total": len(candidates),
            "n_candidates_ranked": len(ranked_rows),
            "n_candidates_failed": len(unevaluated_rows),
        },
    )
    return _exit_code_for_status(
        _worst_status(
            "ok" if ranked_rows else "failed",
            "degraded" if unevaluated_rows else "ok",
        ),
        args,
    )


def _cmd_host_ko_impact(args: argparse.Namespace) -> int:
    """P1-E: microbial gene/reaction knockout -> host objective delta, in one command.

    Baseline and every knockout arm go through the *same* ``run_bigg_host_microbe`` call with the
    identical medium, interface map, biomass basis, host objective, solver and tradeoff. Only the
    named member's SBML is swapped, and only for a knockout of the named gene/reaction — so the
    delta is attributable to the perturbation and not to a drifting setup.
    """
    try:
        import pandas as pd
        from cobra.io import read_sbml_model, write_sbml_model

        from cmig.core.host import run_bigg_host_microbe
        from cmig.core.host_ko_impact import arm_from_coupling, assemble_result
        from cmig.core.medium_spec import load_medium, medium_checksum
        from cmig.core.model_pool import taxonomy_from_model_dir
    except ImportError:
        print(
            "host-ko-impact requires the engine stack: uv sync --extra engine",
            file=sys.stderr,
        )
        return 2
    tmp_dir: tempfile.TemporaryDirectory[str] | None = None
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
        member_ids = [str(x) for x in taxonomy["id"]]
        if args.member not in member_ids:
            raise ValueError(f"--member {args.member!r} not in the pool: {member_ids}")
        ko_ids = _parse_csv_strings(
            args.reactions if args.ko_level == "reaction" else args.genes,
            flag="--reactions" if args.ko_level == "reaction" else "--genes",
        )
        if not ko_ids:
            raise ValueError(
                f"--{'reactions' if args.ko_level == 'reaction' else 'genes'} is required "
                "(the knockout set must be explicit so the comparison is reproducible)"
            )

        # 모든 arm 이 공유하는 설정 — 한 번만 만들어 baseline/KO 에 동일하게 넘긴다.
        microbe_medium = load_medium(args.microbe_medium) if args.microbe_medium else None
        host_medium = load_medium(args.host_medium).uptake if args.host_medium else None
        interface_map = _load_host_interface_map(
            args.interface_map, accept_unreviewed=args.accept_unreviewed_map
        )
        exclude = set() if args.include_currency_metabolites else {"h", "h2o", "co2"}
        if args.exclude_metabolites:
            exclude.update(
                _parse_csv_strings(args.exclude_metabolites, flag="--exclude-metabolites")
            )
        shared: dict[str, Any] = {
            "microbial_biomass_gdw": args.microbial_biomass_gdw,
            "host_biomass_gdw": args.host_biomass_gdw,
            "biomass_basis_kind": args.biomass_basis_kind,
            "biomass_basis_source": args.biomass_basis_source,
            "solver": args.solver,
            "tradeoff_f": args.tradeoff_f,
            "microbe_medium": microbe_medium,
            "host_medium": host_medium,
            "interface_map": interface_map,
            "exchange_suffix": args.exchange_suffix,
            "exclude_metabolites": exclude,
            "close_unlisted_host_uptake": not args.keep_host_uptake,
        }

        def _fresh_host() -> Any:
            """Each arm gets its own host copy — a coupled solve mutates bounds."""
            host = read_sbml_model(str(host_path))
            _apply_host_objective(host, args.host_objective)
            return host

        baseline_coupling = run_bigg_host_microbe(taxonomy.copy(), _fresh_host(), **shared)
        baseline = arm_from_coupling(
            baseline_coupling, label="baseline", target=args.target
        )

        base_model = read_sbml_model(
            str(taxonomy.loc[taxonomy["id"].astype(str) == args.member, "file"].iloc[0])
        )
        tmp_dir = tempfile.TemporaryDirectory(prefix="cmig_host_ko_")
        arms: list[Any] = []
        for index, ko_id in enumerate(ko_ids):
            label = f"{args.member}:{ko_id}"
            try:
                ko_model = base_model.copy()
                if args.ko_level == "reaction":
                    ko_model.reactions.get_by_id(ko_id).knock_out()
                else:
                    ko_model.genes.get_by_id(ko_id).knock_out()
                safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in ko_id)
                ko_file = Path(tmp_dir.name) / f"{args.member}_{index}_{safe}.xml"
                write_sbml_model(ko_model, str(ko_file))
                ko_taxonomy = taxonomy.copy()
                ko_taxonomy.loc[
                    ko_taxonomy["id"].astype(str) == args.member, "file"
                ] = str(ko_file)
                coupling = run_bigg_host_microbe(ko_taxonomy, _fresh_host(), **shared)
                arms.append(arm_from_coupling(
                    coupling,
                    label=label,
                    target=args.target,
                    member=args.member,
                    ko_id=ko_id,
                    ko_level=args.ko_level,
                ))
            except Exception as e:  # noqa: BLE001 - arm 하나의 실패가 나머지를 죽이지 않는다
                from cmig.core.host_ko_impact import HostArm

                arms.append(HostArm(
                    label=label, member=args.member, ko_id=ko_id, ko_level=args.ko_level,
                    run_status="failed", community_status="failed", community_growth=0.0,
                    host_status="failed", host_viable=False,
                    host_objective=float("nan"), target_transfer=float("nan"),
                    diagnostic=str(e),
                ))
        result = assemble_result(
            target=args.target,
            baseline=baseline,
            arms=arms,
            biomass_basis={
                "kind": args.biomass_basis_kind,
                "source": args.biomass_basis_source,
                "microbial_biomass_gdw": args.microbial_biomass_gdw,
                "host_biomass_gdw": args.host_biomass_gdw,
            },
            comparability={
                # 모든 arm 이 같은 설정을 썼다는 사실을 산출물에 기록한다 — 비교 가능성의 근거.
                "shared_across_arms": [
                    "host_model", "host_objective", "microbe_medium", "host_medium",
                    "interface_map", "biomass_basis", "solver", "tradeoff_f", "abundances",
                    "exchange_suffix", "exclude_metabolites",
                ],
                "host_model": str(host_path),
                "host_objective": args.host_objective,
                "microbe_medium_checksum": medium_checksum(microbe_medium),
                "host_medium": str(args.host_medium) if args.host_medium else None,
                "interface_map": str(args.interface_map) if args.interface_map else None,
                "solver": args.solver,
                "tradeoff_f": args.tradeoff_f,
                "ko_level": args.ko_level,
                "perturbed_member": args.member,
                "only_perturbed_member_model_differs": True,
            },
        )
        out = Path(args.out)
        _write_host_ko_impact_outputs(result, out)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"failed to write host-ko-impact outputs: {e}", file=sys.stderr)
        return 2
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()
    print(f"host-ko-impact complete (level={args.ko_level}, member={args.member}) -> {out}")
    print(
        f"  baseline: host_objective={_fmt_number(result.baseline.host_objective)} "
        f"host_status={result.baseline.host_status} "
        f"target_transfer={_fmt_number(result.baseline.target_transfer)}"
    )
    ranked = sorted(
        (d for d in result.deltas if d.delta_host_objective is not None),
        key=lambda d: d.delta_host_objective,
    )
    for delta in ranked[:5]:
        relative = (
            "" if delta.relative_host_objective is None
            else f" ({delta.relative_host_objective * 100:+.2f}%)"
        )
        print(
            f"  {delta.label}: delta_host_objective="
            f"{_fmt_number(delta.delta_host_objective)}{relative} "
            f"delta_target_transfer={_fmt_number(delta.delta_target_transfer)}"
        )
    for delta in result.deltas:
        if delta.delta_host_objective is None:
            print(f"  {delta.label}: no delta (host_status={delta.host_status})")
    for warning in result.warnings:
        print(f"  warning: {warning}")
    _emit_workflow_manifest(
        out,
        "host_ko_impact",
        lambda: {
            **_workflow_base(
                "host_ko_impact", args, taxonomy,
                medium=_host_medium_component(args),
            ),
            "abundances": {
                str(record["id"]): float(record.get("abundance", 1.0) or 1.0)
                for record in taxonomy.to_dict("records")
            },
            "tradeoff_f": float(args.tradeoff_f),
            "target_spec": {"target": args.target, "mode": "host_transfer"},
            "knockout_spec": {
                "ko_level": args.ko_level,
                "member": args.member,
                "ko_ids": list(ko_ids),
                "n_arms": len(ko_ids),
            },
            "host_spec": _host_spec_component(args, interface_map),
            "biomass_basis": _biomass_basis_component(args),
        },
        status=result.status,
        artifacts=["host_ko_impact_summary.json", "host_ko_impact.csv"],
        warnings=list(result.warnings),
        summary={
            "baseline_host_objective": _finite_or_none(result.baseline.host_objective),
            "n_knockouts": len(result.deltas),
            "n_comparable": sum(1 for d in result.deltas if d.comparable),
        },
    )
    return _exit_code_for_status(result.status, args)


def _fmt_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return "n/a" if not math.isfinite(value) else f"{value:.6g}"


def _write_host_ko_impact_outputs(result: Any, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "host_ko_impact.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "arm", "member", "ko_id", "ko_level", "comparable",
                "host_objective", "delta_host_objective", "relative_host_objective",
                "target_transfer", "delta_target_transfer",
                "community_growth", "community_status", "host_status", "diagnostic",
            ],
        )
        writer.writeheader()
        # baseline 을 첫 행으로 명시 — germ-free/no-KO 기준선이 항상 산출물에 존재한다.
        base = result.baseline
        writer.writerow({
            "arm": "baseline", "member": "", "ko_id": "", "ko_level": "",
            "comparable": base.is_comparable,
            "host_objective": _csv_float_or_blank(base.host_objective),
            "delta_host_objective": "", "relative_host_objective": "",
            "target_transfer": _csv_float_or_blank(base.target_transfer),
            "delta_target_transfer": "",
            "community_growth": _csv_float_or_blank(base.community_growth),
            "community_status": base.community_status,
            "host_status": base.host_status,
            "diagnostic": base.diagnostic or "",
        })
        by_label = {arm.label: arm for arm in result.arms}
        for delta in result.deltas:
            arm = by_label[delta.label]
            writer.writerow({
                "arm": delta.label,
                "member": delta.member or "",
                "ko_id": delta.ko_id or "",
                "ko_level": arm.ko_level or "",
                "comparable": delta.comparable,
                "host_objective": _csv_float_or_blank(arm.host_objective),
                "delta_host_objective": _csv_float_or_blank(delta.delta_host_objective),
                "relative_host_objective": _csv_float_or_blank(delta.relative_host_objective),
                "target_transfer": _csv_float_or_blank(arm.target_transfer),
                "delta_target_transfer": _csv_float_or_blank(delta.delta_target_transfer),
                "community_growth": _csv_float_or_blank(arm.community_growth),
                "community_status": delta.community_status,
                "host_status": delta.host_status,
                "diagnostic": delta.diagnostic or "",
            })
    payload = {
        "kind": "host_ko_impact",
        "status": result.status,
        "target": result.target,
        "biomass_basis": result.biomass_basis,
        "comparability": result.comparability,
        "baseline": {
            "host_objective": _finite_or_none(result.baseline.host_objective),
            "host_status": result.baseline.host_status,
            "host_viable": result.baseline.host_viable,
            "target_transfer": _finite_or_none(result.baseline.target_transfer),
            "community_growth": _finite_or_none(result.baseline.community_growth),
            "community_status": result.baseline.community_status,
            "matched_exchanges": result.baseline.matched_exchanges,
            "microbe_to_host": result.baseline.microbe_to_host,
            "warnings": result.baseline.warnings,
        },
        "knockouts": [
            {
                "arm": d.label,
                "member": d.member,
                "ko_id": d.ko_id,
                "comparable": d.comparable,
                "delta_host_objective": d.delta_host_objective,
                "relative_host_objective": d.relative_host_objective,
                "delta_target_transfer": d.delta_target_transfer,
                "delta_microbe_to_host": d.delta_microbe_to_host,
                "host_status": d.host_status,
                "community_status": d.community_status,
                "diagnostic": d.diagnostic,
            }
            for d in result.deltas
        ],
        "warnings": result.warnings,
        "artifacts": ["host_ko_impact.csv", "host_ko_impact_summary.json"],
    }
    atomic_write_text(
        out / "host_ko_impact_summary.json",
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )


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
        # Auto-enumeration skips boundary pseudo-reactions (EX_ exchange, DM_ demand, SK_ sink —
        # closing these is not a metabolic perturbation) and the objective/biomass reaction (its
        # KO trivially zeroes growth and would dominate the ranking with a non-informative
        # result). Use --reactions to target any of them explicitly.
        all_ids = sorted(
            str(r.id)
            for r in model.reactions
            if not str(r.id).startswith(("EX_", "DM_", "SK_"))
            and r.objective_coefficient == 0
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
        ko_result = search_model_pool(engine_factory(), ko_taxonomy, config)
        # P0-B: 평가 불가 후보는 이제 `ranks` 에 들어가지 않는다. KO 가 consortium 을 풀 수 없게
        # 만든 경우가 바로 그것이며, 그것은 0 이 아니라 "평가 불가" 로 보고해야 한다.
        if not ko_result.ranks:
            unevaluated = ko_result.unevaluated[0] if ko_result.unevaluated else None
            return {
                "gene": ko_id,
                "member": member_id,
                "evaluation_status": "failed",
                "score": float("nan"),
                "score_delta": float("nan"),
                "target_flux": float("nan"),
                "target_flux_delta": float("nan"),
                "community_growth": float("nan"),
                "community_growth_delta": float("nan"),
                "status": unevaluated.status if unevaluated else "failed",
                "diagnostic": (
                    unevaluated.diagnostic if unevaluated
                    else "knockout left no evaluable consortium"
                ),
            }
        rank = ko_result.ranks[0]
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
        # R5-P3 CC-2: same contract as the "knockout left no evaluable consortium" branch above.
        # `-baseline.score` is a finite, large-magnitude, entirely plausible effect size that was
        # never measured — and since _write_gene_ko_search_outputs numbers every row it is given,
        # it reached gene_ko_rankings.csv as the single largest suppression in the screen. A
        # knockout that could not be evaluated has no effect size; NaN says so, and _finite_csv
        # renders it as an empty cell.
        return {
            "gene": ko_id,
            "member": member_id,
            "evaluation_status": "failed",
            "score": float("nan"),
            "score_delta": float("nan"),
            "target_flux": float("nan"),
            "target_flux_delta": float("nan"),
            "community_growth": float("nan"),
            "community_growth_delta": float("nan"),
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


def _ko_sort_key(
    row: dict[str, Any], rank_by: str = "effect"
) -> tuple[int, int, float, str]:
    """Deterministic, NaN-safe ranking key.

    ``rank_by="effect"`` (default) orders by |score_delta| descending — the knockouts that move
    the target most, which is what a suppression screen is asking for. Round-2 found the previous
    absolute-score ordering put a zero-effect knockout at rank 1 and printed it as "best", while
    the genuinely suppressive knockouts sat at the bottom of the list.

    ``rank_by="remaining"`` keeps the old ordering (highest remaining target flux first) for
    callers who want "which knockout preserves production".

    ok before failed, finite delta before non-finite, then a ``member:gene`` tiebreak so a
    baseline-infeasible run (all-NaN deltas) stays stable.
    """
    delta = float(row["score_delta"])
    finite = math.isfinite(delta)
    if rank_by == "remaining":
        primary = -float(row["score"]) if math.isfinite(float(row["score"])) else 0.0
    else:
        primary = -abs(delta) if finite else 0.0
    return (
        0 if row["evaluation_status"] == "ok" else 1,
        0 if finite else 1,
        primary,
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
        from cmig.core.search_product import (
            SearchConfig,
            _ranking_degeneracy_warnings,
            search_model_pool,
        )
    except ImportError:
        print("gene-ko-search requires the engine stack: uv sync --extra engine", file=sys.stderr)
        return 2
    try:
        if args.jobs < 1:
            raise ValueError("--jobs must be >= 1")
        if args.top_k < 0:
            raise ValueError("--top-k must be >= 0")
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
        baseline_result = search_model_pool(MicomEngine(), sub, config)
        if not baseline_result.ranks:
            # P0-B: 기준선이 평가 불가면 어떤 KO delta 도 의미가 없다 — 0 을 만들어내지 않는다.
            reason = (
                baseline_result.unevaluated[0].diagnostic
                if baseline_result.unevaluated else "unknown"
            )
            raise ValueError(
                "baseline consortium is not evaluable for this target, so no knockout delta can "
                f"be computed: {reason}"
            )
        baseline = baseline_result.ranks[0]

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
        rows.sort(key=lambda row: _ko_sort_key(row, args.rank_by))
        # B12/F7: a screen where nothing moves, or where the top is tied, must not read as a
        # ranked hit list. `search` already owns this guard; point it at the KO deltas too.
        warnings.extend(_ranking_degeneracy_warnings(
            [
                ((f"{row['member']}:{row['gene']}",), abs(float(row["score_delta"])),
                 "optimal" if row["evaluation_status"] == "ok" else row["evaluation_status"])
                for row in rows
                if math.isfinite(float(row["score_delta"]))
            ],
            score_is_flux=False,
        ))
        out = Path(args.out)
        _write_gene_ko_search_outputs(
            rows[: args.top_k],
            out,
            baseline=baseline,
            members=members,
            target=args.target,
            member=args.member,
            # V4: "evaluated" means "produced a result". Attempts that raised are reported
            # separately rather than being folded into the evaluated count.
            n_genes_evaluated=_n_ko_evaluated(rows),
            n_genes_attempted=len(rows),
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
    # V4: only announce a rank 1 that was actually evaluated. A screen in which every knockout
    # failed used to print "rank 1 (largest effect)" for a gene that was never knocked out.
    ranked = [row for row in rows if row.get("evaluation_status") == "ok"]
    if ranked:
        best = ranked[0]
        label = "largest effect" if args.rank_by == "effect" else "highest remaining flux"
        print(
            f"  rank 1 ({label}): {best['member']}:{best['gene']} "
            f"delta={float(best['score_delta']):.4g} "
            f"remaining={float(best['score']):.4g}"
        )
    elif rows:
        print(
            f"  no knockout could be evaluated ({len(rows)} attempted); "
            "gene_ko_rankings.csv has no ranked rows"
        )
    _emit_workflow_manifest(
        out,
        "gene_ko_search",
        lambda: {
            **_workflow_base("gene_ko_search", args, sub, medium=_medium_component_for(args, None)),
            "target_spec": {
                "target": args.target,
                "direction": args.direction,
                "mode": "single_target",
            },
            "search_spec": {"members": list(members), "top_k": args.top_k},
            "growth_fraction": float(args.growth_fraction),
            "knockout_spec": {
                "ko_level": ko_level,
                "member": args.member,
                "explicit_ids": sorted(explicit_raw.split(",")) if explicit_raw else None,
                "gene_selection": args.gene_selection,
                "seed": args.seed,
                "max_genes": args.max_genes,
                # Which targets were actually screened is what the ranking is over; a truncated
                # screen is a different experiment from a complete one.
                "n_evaluated": len(rows),
                "n_total": sum(member_totals.values()),
                "screened_ids": sorted(
                    {f"{row['member']}:{row['gene']}" for row in rows}
                ),
            },
        },
        status=_worst_status(*[
            "ok" if row.get("evaluation_status") == "ok" else "degraded" for row in rows
        ] or ["failed"]),
        artifacts=["gene_ko_summary.json", "gene_ko_rankings.csv"],
        warnings=warnings,
        summary={
            "baseline_score": _finite_or_none(float(baseline.score)),
            "n_evaluated": len(rows),
            "n_total": sum(member_totals.values()),
        },
    )
    return 0


def _cmd_strain_growth(args: argparse.Namespace) -> int:
    """Estimate per-strain growth alone and inside the full community."""
    try:
        import pandas as pd
        from cobra.io import read_sbml_model

        from cmig.core.engine import MicomEngine
        from cmig.core.medium_spec import (
            MediumSpec,
            apply_medium_translated,
            compare_effective_media,
            effective_medium_by_metabolite,
            exchange_metabolite,
            load_medium,
            medium_checksum,
        )
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
            # P0-A: preset 은 EX_*_m 로 쓰여 있을 수도, EX_*_e 로 쓰여 있을 수도 있다. 대사체로
            # 매칭해 community 의 namespace 로 번역한 뒤 적용한다.
            apply_medium_translated(
                community, medium_spec, strict=not args.allow_unknown_medium
            )
        community_result = engine.cooperative_tradeoff(
            community, args.tradeoff_f, cmig_solver=args.solver
        )
        rows: list[dict[str, Any]] = []
        # P0-A: alone-vs-community 는 **동일한 실효 배지**에서만 상호작용으로 해석할 수 있다.
        # community 는 EX_*_m, 단일 모델은 EX_*_e 를 노출하므로 같은 MediumSpec 객체를 양쪽에
        # 그대로 넘기면 어느 쪽에도 적용되지 않는다. 따라서 (1) community 의 **실효** 배지를
        # 대사체 단위로 읽고, (2) 각 단일 모델의 namespace 로 번역해 적용하고, (3) 두 실효 배지를
        # 실제로 비교해서 동등성을 **측정**한다 — 결코 가정하지 않는다.
        community_medium = effective_medium_by_metabolite(community)
        controlled = args.single_medium == "community"
        community_offer = MediumSpec(uptake={
            f"EX_{metabolite}_e": limit for metabolite, limit in community_medium.items()
        })
        media_matched = True
        for record in taxonomy.to_dict("records"):
            member_id = str(record["id"])
            model_file = str(record["file"])
            single_growth: float | None = None
            single_status = "not_run"
            single_diag = None
            single_medium_applied = False
            n_objective_terms: int | None = None
            objective_note: str | None = None
            unavailable: tuple[str, ...] = ()
            single_effective: dict[str, float] = {}
            row_equal = False
            try:
                model = read_sbml_model(model_file)
                if controlled:
                    # community 의 실효 배지를 이 모델이 실제로 가진 exchange 로 번역해 **정확히**
                    # 적용한다(exact=True → 나머지 exchange 는 닫힘). exchange 가 없는 대사체는 이
                    # 균주가 애초에 쓸 수 없으므로 offer 에서 빠지며(생물학적 사실), 동등성 판정에서
                    # 면제된다. strict=False: 없는 exchange 는 오류가 아니라 기록 대상이다.
                    translation = apply_medium_translated(
                        model, community_offer, strict=False, exact=True
                    )
                    unavailable = tuple(
                        exchange_metabolite(ex) for ex in translation.unmatched
                    )
                    single_medium_applied = bool(translation.mapping)
                elif medium_spec is not None:
                    translation = apply_medium_translated(
                        model, medium_spec, strict=not args.allow_unknown_medium
                    )
                    unavailable = tuple(
                        exchange_metabolite(ex) for ex in translation.unmatched
                    )
                    single_medium_applied = bool(translation.mapping)
                    if translation.unmatched:
                        single_diag = (
                            f"{member_id} has no exchange for medium metabolites: "
                            f"{sorted(unavailable)}"
                        )
                single_effective = effective_medium_by_metabolite(model)
                row_equal, differences = compare_effective_media(
                    community_medium, single_effective, exempt=set(unavailable)
                )
                if not row_equal and single_diag is None:
                    changed = differences["bound_mismatch"] or differences["extra_in_candidate"] \
                        or differences["missing_from_candidate"]
                    single_diag = (
                        f"{member_id} effective medium differs from the community medium: "
                        f"{changed[:8]}"
                    )
                from cobra.util.solver import linear_reaction_coefficients

                from cmig.io.model_import import objective_structure_warning

                n_objective_terms = len(linear_reaction_coefficients(model))
                objective_note = objective_structure_warning(n_objective_terms)
                single = solve_single_model(model, solver=args.solver)
                single_growth = float(single.objective)
                single_status = single.status
                single_diag = single.diagnostic or objective_note or single_diag
            except Exception as e:
                single_status = "failed"
                single_diag = str(e)
                single_medium_applied = False
                row_equal = False
            media_matched = media_matched and row_equal
            rows.append({
                "member": member_id,
                "file": model_file,
                "abundance": community_result.abundances.get(member_id),
                "single_growth": single_growth,
                "single_status": single_status,
                "single_medium_applied": single_medium_applied,
                # A-B9: a multi-term objective is not a growth rate; carried so the figure and the
                # summary can say so instead of labelling it "Growth rate".
                "n_objective_terms": n_objective_terms,
                "objective_warning": objective_note,
                # 측정된 동등성 — 요청이 성공했다는 사실이 아니라 실효 배지 비교 결과.
                "single_medium_equals_community": row_equal,
                "medium_metabolites_unavailable_to_member": list(unavailable),
                "n_single_medium_metabolites": len(single_effective),
                "community_member_growth": community_result.member_growth.get(member_id),
                "community_status": community_result.status,
                "community_growth": community_result.objective,
                "diagnostic": single_diag,
            })
        warnings = list(community_result.warnings)
        if not media_matched:
            mismatched = [r["member"] for r in rows if not r["single_medium_equals_community"]]
            warnings.append(
                "single-model and community legs did not run on the same effective medium "
                f"({mismatched}); the alone-vs-community difference is NOT attributable to "
                "interaction and must not be reported as one"
            )
        if not controlled:
            warnings.append(
                "--single-medium model_default keeps each member on its own native bounds, which "
                "differ from the community medium; this reports native growth capability, not a "
                "controlled interaction effect"
            )
        failed_single = [r["member"] for r in rows if r["single_status"] != "optimal"]
        if failed_single:
            warnings.append(
                f"single-model leg did not solve for {failed_single}; no alone-vs-community "
                "comparison exists for those members"
            )
        out = Path(args.out)
        _write_strain_growth_outputs(
            rows,
            out,
            solver=args.solver,
            tradeoff_f=args.tradeoff_f,
            community_growth=community_result.objective,
            community_status=community_result.status,
            community_diagnostic=community_result.diagnostic,
            medium_basis={
                "medium_source": str(args.medium) if args.medium else "micom_default_medium",
                "medium_checksum": medium_checksum(medium_spec),
                "single_medium_mode": args.single_medium,
                "n_community_medium_metabolites": len(community_medium),
                # 이 필드는 이제 **측정값**이다 (P0-A). 모든 멤버에서 실효 배지가 일치할 때만 true.
                "single_medium_equals_community_medium": media_matched,
                "comparison_is_controlled": bool(media_matched and not failed_single),
            },
            warnings=warnings,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"failed to write strain-growth outputs: {e}", file=sys.stderr)
        return 2
    print(f"strain-growth complete ({len(rows)} members) -> {out}")
    for warning in warnings:
        print(f"  warning: {warning}")
    _emit_workflow_manifest(
        out,
        "strain_growth",
        lambda: _strain_growth_hash_components(
            args, taxonomy, medium_spec, community_result, community_medium, rows
        ),
        status=_worst_status(
            _run_status_from_solve(str(community_result.status)),
            "ok" if not failed_single else (
                "failed" if len(failed_single) == len(rows) else "degraded"
            ),
            "ok" if (media_matched and not failed_single) else "degraded",
        ),
        artifacts=["strain_growth_summary.json", "strain_growth.csv"],
        warnings=warnings,
        summary={
            "n_members": len(rows),
            "community_growth": _finite_or_none(float(community_result.objective)),
            "single_medium_equals_community_medium": media_matched,
        },
    )
    return 0


def _cmd_abundance_impact(args: argparse.Namespace) -> int:
    """Sweep one strain's abundance and report community/member/target impacts."""
    try:
        import pandas as pd

        from cmig.core.engine import MicomEngine
        from cmig.core.medium_spec import apply_medium_checked, load_medium
        from cmig.core.metrics import (
            community_contributions,
            target_secretion_share,
            target_turnover_share,
        )
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
                # F4: micom member_exchange is a PER-TAXON flux, so the community-level
                # contribution is flux x abundance. Omitting the weight inverts the trend exactly.
                # Two distinct questions are reported separately rather than conflated under one
                # ambiguous name (see cmig.core.metrics).
                # R2-A D4: the swept exchange flux is one LP vertex. --fva reports the interval
                # the growth floor actually permits at each point, so a 2.5x jump between
                # neighbouring abundances can be read as degeneracy rather than a dose response.
                target_lo = target_hi = None
                fva_status = "not_requested"
                if args.fva:
                    try:
                        from cmig.core.fva import community_fva

                        ranges = community_fva(
                            community,
                            reactions=[f"EX_{args.target}_m"],
                            fraction_of_optimum=args.tradeoff_f,
                            solver=args.solver,
                        )
                        interval = ranges.get(f"EX_{args.target}_m")
                        if interval is not None:
                            target_lo, target_hi = float(interval.lo), float(interval.hi)
                            fva_status = "ok"
                        else:
                            fva_status = "missing"
                    except Exception as fva_error:  # noqa: BLE001 - FVA is a diagnostic add-on
                        fva_status = f"failed: {type(fva_error).__name__}"
                contributions = community_contributions(
                    result.member_exchange, result.abundances, args.target
                )
                influence_share = target_turnover_share(contributions, args.member)
                secretion_share = target_secretion_share(contributions, args.member)
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
                    "target_secretion_share": secretion_share,
                    "target_member_contribution": contributions.get(args.member, 0.0),
                    "community_target_fva_lo": target_lo,
                    "community_target_fva_hi": target_hi,
                    "fva_status": fva_status,
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
                # R5-P3 CC-2: a sweep point that did not solve has no measurement. The previous
                # zeros were indistinguishable from a measured community collapse — and the figure
                # plotted them as exactly that, a clean line through a point nobody computed.
                # `None` propagates as a blank CSV cell, a null in the JSON, and (below) an
                # omitted point in the figure.
                rows.append({
                    "target_member": args.member,
                    "target_abundance": fraction,
                    "target": args.target,
                    "community_growth": None,
                    "target_member_growth": None,
                    "target_member_exchange": None,
                    "community_target_exchange": None,
                    "target_influence_share": None,
                    "target_secretion_share": None,
                    "target_member_contribution": None,
                    "community_target_fva_lo": None,
                    "community_target_fva_hi": None,
                    "fva_status": "not_run",
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
            warnings=[
                "abundance sweeps rescale one member under the same models and medium; report "
                "this as a sensitivity analysis, not ecological causation",
                "target_influence_share is the abundance-weighted share of the community's total "
                "|target| turnover (producers and consumers alike); target_secretion_share is the "
                "producer-only share. Both use flux x abundance, because member_exchange is a "
                "per-taxon flux",
                "the reported exchange flux is one LP vertex and is not necessarily unique",
            ],
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(f"failed to write abundance-impact outputs: {e}", file=sys.stderr)
        return 2
    print(f"abundance-impact complete ({args.member}, target={args.target}) -> {out}")
    _emit_workflow_manifest(
        out,
        "abundance_impact",
        lambda: _abundance_hash_components(args, taxonomy, medium_spec, fractions, rows),
        status=_worst_status(*[
            _run_status_from_solve(str(row.get("status"))) for row in rows
        ] or ["failed"]),
        artifacts=["abundance_impact_summary.json", "abundance_impact.csv"],
        summary={
            "n_points": len(rows),
            "target_member": args.member,
            "target": args.target,
        },
    )
    return 0


def _ko_ranks(rows: list[dict[str, Any]]) -> list[int | str]:
    """Ordinal rank per KO row — only for rows that were actually evaluated.

    R5-P3 V4: every row used to be numbered by ``enumerate(rows, start=1)``, so a knockout that
    raised still occupied an ordinal position, and a screen in which *everything* failed printed
    "rank 1 (largest effect)" for a gene nobody knocked out. Rank is a claim about a measured
    effect; a row with no effect size gets no rank. Ok rows keep consecutive numbering so a
    failure does not punch a hole in the ranking either.
    """
    ranks: list[int | str] = []
    evaluated = 0
    for row in rows:
        if row.get("evaluation_status") == "ok":
            evaluated += 1
            ranks.append(evaluated)
        else:
            ranks.append("")
    return ranks


def _n_ko_evaluated(rows: list[dict[str, Any]]) -> int:
    """How many knockouts actually produced a result (V4: failures are not evaluations)."""
    return sum(1 for row in rows if row.get("evaluation_status") == "ok")


def _gene_ko_summary_status(rows: list[dict[str, Any]]) -> str:
    """Run tier derived from the knockout rows.

    R5-P3 (opus F12a): the summary carried a literal ``"status": "ok"`` that was never
    reassigned, so a screen in which every knockout failed still published "ok" to anyone who
    opened the JSON directly.
    """
    if not rows:
        return "failed"
    n_ok = sum(1 for row in rows if row.get("evaluation_status") == "ok")
    if n_ok == 0:
        return "failed"
    return "ok" if n_ok == len(rows) else "degraded"


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
    n_genes_attempted: int | None = None,
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
        # V4: only evaluated knockouts get an ordinal; a failed row's rank cell stays blank.
        for rank, row in zip(_ko_ranks(rows), rows, strict=True):
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
        "status": _gene_ko_summary_status(rows),
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
        # V4: attempts that raised are not evaluations; both numbers are published so a screen
        # cannot look complete when part of it failed.
        "n_genes_attempted": (
            n_genes_evaluated if n_genes_attempted is None else n_genes_attempted
        ),
        "n_genes_total": n_genes_total,
        "ko_level": ko_level,
        "gene_selection": gene_selection,
        "seed": seed,
        "direction": direction,
        "warnings": list(warnings),
        "top_ranked": [
            {
                "rank": rank or None,          # V4: no ordinal for a knockout with no result
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
            for rank, row in zip(_ko_ranks(rows), rows, strict=True)
        ],
        "artifacts": [
            "gene_ko_rankings.csv",
            "gene_ko_summary.json",
            "gene_ko_plot.svg",
            "gene_ko_plot.tiff",
        ],
    }
    atomic_write_text(
        out / "gene_ko_summary.json",
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
    medium_basis: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
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
                "single_medium_applied",
                "single_medium_equals_community",
                "medium_metabolites_unavailable_to_member",
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
                "single_medium_applied": row.get("single_medium_applied"),
                "single_medium_equals_community": row.get("single_medium_equals_community"),
                "medium_metabolites_unavailable_to_member": ";".join(
                    row.get("medium_metabolites_unavailable_to_member") or []
                ),
                "community_member_growth": _csv_float_or_blank(
                    row.get("community_member_growth")
                ),
                "community_status": row["community_status"],
                "community_growth": _csv_float_or_blank(row.get("community_growth")),
                "diagnostic": row.get("diagnostic") or "",
            })
    # P0-D: 최상위 status 는 하위 상태 중 **최악**에서 파생된다. community 가 optimal 이어도
    # 단일 leg 이 전부 실패했다면 alone-vs-community 결과는 존재하지 않는다.
    # A-B9: a multi-term objective is not a growth rate; say so at run level too.
    multi_term = sorted(
        str(row["member"]) for row in rows if (row.get("n_objective_terms") or 1) > 1
    )
    if multi_term:
        warnings = list(warnings or []) + [
            f"objective is a multi-term linear combination for {multi_term}; the reported growth "
            "for those members is an objective value, not a growth rate"
        ]
    single_statuses = [str(row.get("single_status")) for row in rows]
    n_failed_single = sum(1 for status in single_statuses if status != "optimal")
    if not rows or n_failed_single == len(rows):
        single_tier = "failed"
    elif n_failed_single:
        single_tier = "degraded"
    else:
        single_tier = "ok"
    controlled = bool((medium_basis or {}).get("comparison_is_controlled", False))
    payload = {
        "status": _worst_status(
            _run_status_from_solve(str(community_status)),
            single_tier,
            "ok" if controlled else "degraded",
        ),
        "community_status": community_status,
        "diagnostic": community_diagnostic,
        "solver": solver,
        "tradeoff_f": tradeoff_f,
        "community_growth": _finite_or_none(float(community_growth)),
        # B5: 두 leg 이 같은 배지였는지를 결과에 명시한다 — 해석 가능성의 전제 조건.
        "medium_basis": medium_basis or {},
        "warnings": list(warnings or []),
        "members": [
            {
                "member": row["member"],
                "file": row["file"],
                "abundance": _optional_float(row.get("abundance")),
                "single_growth": _optional_float(row.get("single_growth")),
                "single_status": row["single_status"],
                "single_medium_applied": row.get("single_medium_applied"),
                "n_objective_terms": row.get("n_objective_terms"),
                "objective_warning": row.get("objective_warning"),
                "single_medium_equals_community": row.get("single_medium_equals_community"),
                "medium_metabolites_unavailable_to_member": list(
                    row.get("medium_metabolites_unavailable_to_member") or []
                ),
                "n_single_medium_metabolites": row.get("n_single_medium_metabolites"),
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
    atomic_write_text(
        out / "strain_growth_summary.json",
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
    warnings: list[str] | None = None,
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
                "target_secretion_share",
                "target_member_contribution",
                "community_target_fva_lo",
                "community_target_fva_hi",
                "fva_status",
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
                "target_secretion_share": _csv_float_or_blank(
                    row.get("target_secretion_share")
                ),
                "target_member_contribution": _csv_float_or_blank(
                    row.get("target_member_contribution")
                ),
                "community_target_fva_lo": _csv_float_or_blank(
                    row.get("community_target_fva_lo")
                ),
                "community_target_fva_hi": _csv_float_or_blank(
                    row.get("community_target_fva_hi")
                ),
                "fva_status": row.get("fva_status") or "",
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
    # P0-D: "any row optimal → ok" 는 최악 상태를 감춘다 (red-team F5). 최악에서 파생한다.
    sweep_statuses = [str(row.get("status")) for row in rows]
    n_bad = sum(1 for status in sweep_statuses if status != "optimal")
    if not rows or n_bad == len(rows):
        sweep_tier = "failed"
    elif n_bad:
        sweep_tier = "degraded"
    else:
        sweep_tier = "ok"
    # pFBA fallback 이 일부 지점에서만 발동하면 한 곡선 안에서 flux 정규화 기준이 섞인다.
    fallback_rows = [
        row for row in rows
        if "pFBA flux stage failed" in str(row.get("diagnostic") or "")
    ]
    sweep_warnings = list(warnings or [])
    if fallback_rows and len(fallback_rows) != len(rows):
        sweep_warnings.append(
            f"{len(fallback_rows)} of {len(rows)} sweep points fell back to a non-parsimonious "
            "(FBA) flux distribution while the rest are pFBA; the exchange-flux curve mixes two "
            "flux-selection rules and the points are not like-for-like"
        )
        sweep_tier = _worst_status(sweep_tier, "degraded")
    payload = {
        "status": sweep_tier,
        "warnings": sweep_warnings,
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
    atomic_write_text(
        out / "abundance_impact_summary.json",
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
    ranking_parameters: dict[str, float | None],
    biomass_basis: dict[str, Any],
    n_candidates_failed: int = 0,
    unevaluated: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    unevaluated = list(unevaluated or [])
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
    if unevaluated:
        with open(out / "host_search_unevaluated.csv", "w", newline="") as f:
            unevaluated_writer = csv.DictWriter(
                f, fieldnames=["members", "evaluation_status", "diagnostic"]
            )
            unevaluated_writer.writeheader()
            for row in unevaluated:
                unevaluated_writer.writerow({
                    "members": "+".join(row["members"]),
                    "evaluation_status": row["evaluation_status"],
                    "diagnostic": row["diagnostic"] or "",
                })
    payload = {
        # B6: 최상위 status 는 최악의 하위 상태에서 파생된다 — 일부 후보가 평가되지 않았다면 "ok" 가
        # 아니다(스크립트/에이전트가 status 로 성공을 게이팅한다).
        "status": _worst_status(
            "ok" if n_candidates_evaluated else "failed",
            "degraded" if n_candidates_failed else "ok",
        ),
        "metric": metric,
        "target": target,
        "n_candidates_total": n_candidates_total,
        "n_candidates_evaluated": n_candidates_evaluated,
        "n_candidates_failed": n_candidates_failed,
        "warnings": list(warnings or []),
        "unevaluated": [
            {
                "members": list(row["members"]),
                "evaluation_status": row["evaluation_status"],
                "diagnostic": row["diagnostic"],
            }
            for row in unevaluated
        ],
        "ranking_parameters": ranking_parameters,
        "biomass_basis": biomass_basis,
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
        ] + (["host_search_unevaluated.csv"] if unevaluated else []),
    }
    atomic_write_text(
        out / "host_search_summary.json",
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )
    _write_host_search_figures(rows, out, target=target, metric=metric)
    _prune_stale_workflow_artifacts(out, KNOWN_HOST_SEARCH_ARTIFACTS, payload["artifacts"])


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
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "metabolite", "community_flux", "host_scaled_availability",
                "host_exchange", "matched", "unit",
            ],
        )
        writer.writeheader()
        for metabolite, flux in sorted(result.microbial_secretion.items()):
            exchange = result.matched_exchanges.get(metabolite, "")
            writer.writerow({
                "metabolite": metabolite,
                "community_flux": _finite_csv(
                    float(result.community_secretion.get(metabolite, 0.0))
                ),
                "host_scaled_availability": _finite_csv(float(flux)),
                "host_exchange": exchange,
                "matched": bool(exchange),
                "unit": result.host_result.flux_unit,
            })
    with open(out / "host_uptake.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["metabolite", "uptake_flux", "minimum", "maximum", "unit"]
        )
        writer.writeheader()
        for metabolite, bounds in sorted(result.host_result.lumen_uptake_ranges.items()):
            point = result.host_result.lumen_uptake.get(metabolite)
            writer.writerow({
                "metabolite": metabolite,
                "uptake_flux": "" if point is None else _finite_csv(float(point)),
                "minimum": _finite_csv(float(bounds[0])),
                "maximum": _finite_csv(float(bounds[1])),
                "unit": result.host_result.flux_unit,
            })
    with open(out / "microbe_to_host.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["metabolite", "transfer_flux", "minimum", "maximum", "identifiable"]
        )
        writer.writeheader()
        for metabolite, bounds in sorted(result.impact.microbe_to_host_ranges.items()):
            point = result.impact.microbe_to_host.get(metabolite)
            writer.writerow({
                "metabolite": metabolite,
                "transfer_flux": "" if point is None else _finite_csv(float(point)),
                "minimum": _finite_csv(float(bounds[0])),
                "maximum": _finite_csv(float(bounds[1])),
                "identifiable": point is not None,
            })
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
    # F9: a complete interaction figure set written from a failed solve is indistinguishable
    # from a real result unless the figures themselves say otherwise.
    host_failed = str(result.host_result.status) != "optimal"
    community_failed = str(result.community_status) != "optimal"
    banner = None
    if community_failed:
        banner = (
            f"NOT A RESULT — community solve {result.community_status}; "
            "figures show inputs only"
        )
    elif host_failed:
        banner = (
            f"NOT A RESULT — host solve {result.host_result.status}; "
            "no metabolite reached the host"
        )
    elif not result.matched_exchanges:
        banner = "NO COUPLING — no microbial metabolite matched a host exchange"
    figure_artifacts = render_interaction_figures(out, failure_banner=banner)
    payload = {
        # B6: host LP 가 infeasible 인데 최상위가 "ok" 이면 스크립트가 실패를 성공으로 읽는다.
        # 최상위 status 는 community/host 하위 상태 중 최악에서 파생한다.
        "status": _worst_status(
            _run_status_from_solve(str(result.community_status)),
            _run_status_from_solve(str(result.host_result.status)),
        ),
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
            "lumen_uptake_ranges": result.host_result.lumen_uptake_ranges,
            "flux_unit": result.host_result.flux_unit,
        },
        "coupling_scale": (
            None if result.coupling_scale is None else result.coupling_scale.__dict__
        ),
        "matched_exchanges": result.matched_exchanges,
        "unmatched_metabolites": result.unmatched_metabolites,
        "microbial_secretion": result.microbial_secretion,
        "community_secretion": result.community_secretion,
        "member_secretion": result.member_secretion,
        "microbe_to_host": result.impact.microbe_to_host,
        "microbe_to_host_ranges": result.impact.microbe_to_host_ranges,
        "ambiguous_metabolites": result.impact.ambiguous_metabolites,
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
    atomic_write_text(
        out / "host_microbe_bigg_summary.json",
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
                close_untracked_uptake=args.close_untracked_uptake,
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
    # D5: an untracked-substrate warning invalidates any substrate/Km reading of the run, so it
    # must be impossible to miss.
    for warning in result.warnings:
        print(f"  warning: {warning}", file=sys.stderr)
    _emit_workflow_manifest(
        Path(args.out),
        "dfba",
        lambda: {
            **_single_model_workflow_base("dfba", args, model_path),
            "dfba_spec": {
                "t_end": args.t_end,
                "dt": args.dt,
                "min_dt": args.min_dt,
                "km": args.km,
                "vmax": vmax,
                "initial_biomass": args.initial_biomass,
                "initial_concentrations": concentrations,
                "default_initial_preset": args.initial_concentrations is None,
                "growth_floor": args.growth_floor,
                # D5: closing untracked uptake changes the trajectory entirely (completed ->
                # infeasible on iHN637), so it belongs in the reproducibility hash.
                "close_untracked_uptake": bool(args.close_untracked_uptake),
            },
        },
        # dFBA reports "completed", not "optimal" — mapping it through the solve vocabulary would
        # mark every successful integration as failed.
        status=_dfba_run_status(str(result.status)),
        artifacts=["dfba_summary.json", "timecourse.parquet"],
        summary={"status": result.status, "n_steps": len(getattr(result, "rows", []) or [])},
    )
    return _exit_code_for_status(_dfba_run_status(str(result.status)), args)


def _cmd_dfba_sensitivity(args: argparse.Namespace) -> int:
    """Run a numerical dt×Km sensitivity grid for one user model."""
    try:
        import cobra

        from cmig.core.dfba import DfbaConfig, run_dfba_sensitivity
        from cmig.io.dfba_output import write_dfba_sensitivity
        from cmig.io.solve_output import file_checksum, runtime_versions
    except ImportError:
        print("dfba-sensitivity requires the engine stack", file=sys.stderr)
        return 2
    model_path = Path(args.model)
    if not model_path.exists():
        print(f"model file not found: {model_path}", file=sys.stderr)
        return 2
    try:
        model = cobra.io.read_sbml_model(str(model_path))
        concentrations = _dfba_initial_concentrations(model, args.initial_concentrations)
        vmax = _parse_key_float_map(args.vmax, flag="--vmax") if args.vmax else None
        _require_model_exchanges(model, concentrations, flag="--initial")
        if vmax is not None:
            _require_model_exchanges(model, vmax, flag="--vmax")
        dts = _parse_csv_floats(args.dts, flag="--dts")
        kms = _parse_csv_floats(args.kms, flag="--kms")
        config = DfbaConfig(
            t_end=args.t_end,
            dt=min(dts),
            initial_biomass=args.initial_biomass,
            initial_concentrations=concentrations,
            km=min(kms),
            vmax=vmax,
            min_dt=min(args.min_dt, min(dts)),
            growth_floor=args.growth_floor,
        )
        result = run_dfba_sensitivity(
            model,
            config,
            dts=dts,
            kms=kms,
            solver=args.solver,
        )
        artifacts = write_dfba_sensitivity(
            result,
            args.out,
            provenance={
                "model_path": str(model_path.resolve()),
                "model_checksum": file_checksum(model_path),
                "dependency_versions": runtime_versions(),
                "solver": args.solver,
            },
        )
    except (KeyError, OSError, ValueError) as e:
        print(f"dfba-sensitivity input error: {e}", file=sys.stderr)
        return 2
    print(f"dfba-sensitivity complete ({len(result.rows)} runs) -> {args.out}")
    print(f"  artifacts: {', '.join(artifacts)}")
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
    if args.out:
        _emit_workflow_manifest(
            Path(args.out),
            "model_pool_search",
            lambda: {
                **_workflow_base(
                    "model_pool_search", args, taxonomy,
                    # The bundled fixture is identified by name, matching how golden_fixture
                    # fingerprints it — its bytes ship with the package, not with the run.
                    medium=_medium_component_for(args, None),
                ),
                "model_checksum": "micom_test_taxonomy_3",
                "target_spec": {
                    "target": args.metabolite,
                    "direction": spec.direction.value,
                    "mode": "single_target",
                    "fixture": "community_3_member",
                },
                "search_spec": {"sizes": [2], "top_k": args.top_k},
                "growth_fraction": float(args.growth_fraction),
            },
            status=_run_status_from_solve(str(result.status)),
            artifacts=["search_summary.json"],
            summary={"target": args.metabolite, "status": result.status},
        )
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
        # multi-target path (§14 다중 타깃). --target-preset scfa 는 문서화된 SCFA 6종으로 확장된다.
        if args.targets or args.target_preset:
            return _run_multi_target_search(args, taxonomy, medium_spec)
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
    print(
        f"  evaluated: {result.n_candidates_evaluated}/{result.n_candidates_total}"
        f" | ranked: {len(result.ranks)} | unevaluable: {len(result.unevaluated)}"
    )
    # P0-B: 실패했거나 target flux 가 0 인 후보를 "best" 로 인쇄하지 않는다. rank 목록에는 이미
    # 평가 가능한 행만 들어 있으므로, 남은 위험은 "전부 0" 인 경우다.
    if not result.ranks:
        print("  no evaluable candidate: there is no best producer for this target")
    elif abs(result.ranks[0].score) <= 1e-9:
        print(
            f"  no candidate produced {result.target}: top score is 0 "
            "(the order is arbitrary; see warnings)"
        )
    else:
        best = result.ranks[0]
        print(
            f"  best: {'+'.join(best.members)} "
            f"flux={best.target_flux:.4g} growth={best.community_growth:.4g}"
        )
    # B4: 전부-0 / 동점 랭킹에서 rank 1 을 "최고"로 읽지 않도록 경고를 stdout 에도 낸다.
    for warning in result.warnings:
        print(f"  warning: {warning}")
    _emit_workflow_manifest(
        out,
        "model_pool_search",
        lambda: _search_hash_components(
            "model_pool_search", args, taxonomy, medium_spec,
            target_spec={
                "target": result.target,
                "target_exchange": result.target_exchange,
                "direction": result.direction,
                "mode": "single_target",
            },
            search_spec={
                "min_size": args.min_size,
                "max_size": args.max_size,
                "strategy_requested": args.strategy,
                "strategy_resolved": result.strategy,
                "n_samples": args.n_samples,
                "seed": args.seed,
                "top_k": args.top_k,
                "robustness_fva": bool(args.robustness_fva),
            },
        ),
        status=_worst_status(
            "ok" if result.ranks else "failed",
            "degraded" if result.unevaluated else "ok",
        ),
        artifacts=["search_summary.json", "search_rankings.csv", "pool_taxonomy.csv"],
        warnings=list(result.warnings),
        summary={
            "n_candidates_total": result.n_candidates_total,
            "n_candidates_ranked": len(result.ranks),
            "n_candidates_failed": len(result.unevaluated),
            "best_members": list(result.ranks[0].members) if result.ranks else None,
            "best_target_flux": (
                _finite_or_none(result.ranks[0].target_flux) if result.ranks else None
            ),
        },
    )
    return _exit_code_for_status(
        _worst_status(
            "ok" if result.ranks else "failed",
            "degraded" if result.unevaluated else "ok",
        ),
        args,
    )


def _resolve_target_carbon_numbers(
    taxonomy: Any, targets: list[str]
) -> tuple[dict[str, int], dict[str, str]]:
    """target 별 탄소 수를 pool 모델의 metabolite formula 에서 읽는다 (carbon_equivalent 용).

    "SCFA 총량"을 mmol 단순합으로 더하면 아세트산(C2)과 부티르산(C4)을 같은 단위로 취급하게 되어
    화학적으로 의미가 없다. 탄소 수는 반드시 **모델의 화학식**에서 가져오고, 읽을 수 없으면
    조용히 1.0 을 쓰지 않고 ValueError 로 멈춘다(잘못된 총량을 만들지 않는다).

    Returns ``(carbon_number_by_target, source_model_by_target)``.
    """
    from cobra.io import read_sbml_model

    from cmig.core.targets import parse_carbon_number

    remaining = set(targets)
    carbon: dict[str, int] = {}
    sources: dict[str, str] = {}
    for record in taxonomy.to_dict("records"):
        if not remaining:
            break
        try:
            model = read_sbml_model(str(record["file"]))
        except Exception:  # noqa: BLE001 - 읽을 수 없는 모델은 다음 후보로 넘어간다
            continue
        by_id = {str(m.id): m for m in model.metabolites}
        for target in sorted(remaining):
            candidates = [f"{target}_e", f"{target}_c", f"{target}_p"]
            candidates += sorted(
                mid for mid in by_id if mid.rsplit("_", 1)[0] == target
            )
            for metabolite_id in candidates:
                metabolite = by_id.get(metabolite_id)
                if metabolite is None:
                    continue
                count = parse_carbon_number(getattr(metabolite, "formula", None))
                if count:
                    carbon[target] = count
                    sources[target] = f"{model.id}:{metabolite_id}"
                    break
        remaining = set(targets) - set(carbon)
    if remaining:
        raise ValueError(
            "--multi-metric carbon_equivalent needs a carbon number for every target, but the "
            f"pool models carry no readable formula for: {sorted(remaining)}. Supply "
            "--target-weights explicitly or use --multi-metric raw_sum."
        )
    return carbon, sources


def _run_multi_target_search(args: argparse.Namespace, taxonomy: Any, medium_spec: Any) -> int:
    """Multi-target model-pool search (§14). Raises ValueError on bad args (caught by caller)."""
    from cmig.core.engine import MicomEngine
    from cmig.core.model_pool import diagnose_model_pool
    from cmig.core.search import Direction
    from cmig.core.search_product import MultiTargetConfig, search_model_pool_multi
    from cmig.core.targets import preset_targets

    if args.targets and args.target_preset:
        raise ValueError("provide either --targets or --target-preset, not both")
    if args.target_preset:
        targets = preset_targets(args.target_preset)   # ValueError on unknown preset
    else:
        targets = [t.strip() for t in str(args.targets).split(",") if t.strip()]
    if len(targets) < 2:
        raise ValueError("--targets needs >= 2 comma-separated metabolites (use --target for one)")
    if len(set(targets)) != len(targets):
        raise ValueError(f"--targets has duplicates: {targets}")
    if args.target_weights:
        try:
            weights = [float(x) for x in str(args.target_weights).split(",")]
        except ValueError as e:
            raise ValueError("--target-weights must be comma-separated numbers") from e
        if len(weights) != len(targets):
            raise ValueError("--target-weights count must match --targets count")
    else:
        weights = [1.0] * len(targets)
    default_direction = Direction(args.direction)
    if args.target_directions:
        raw_dirs = [d.strip() for d in str(args.target_directions).split(",")]
        if len(raw_dirs) != len(targets):
            raise ValueError("--target-directions count must match --targets count")
        try:
            dir_list = [Direction(d) for d in raw_dirs]
        except ValueError as e:
            raise ValueError(
                "--target-directions values must be one of "
                "max_secretion,min_secretion,max_uptake,min_uptake"
            ) from e
    else:
        dir_list = [default_direction] * len(targets)
    effective_weights = dict(zip(targets, weights, strict=True))
    carbon_numbers: dict[str, int] = {}
    carbon_sources: dict[str, str] = {}
    if args.multi_metric == "carbon_equivalent":
        carbon_numbers, carbon_sources = _resolve_target_carbon_numbers(taxonomy, targets)
        # 사용자 가중치 × 탄소 수 → 점수 단위는 mmol C gDW^-1 h^-1.
        effective_weights = {
            target: effective_weights[target] * float(carbon_numbers[target])
            for target in targets
        }
    config = MultiTargetConfig(
        targets=targets,
        directions=dict(zip(targets, dir_list, strict=True)),
        weights=effective_weights,
        min_size=args.min_size,
        max_size=args.max_size,
        growth_fraction=args.growth_fraction,
        solver=args.solver,
        top_k=args.top_k,
        metric=args.multi_metric,
    )
    result = search_model_pool_multi(
        MicomEngine(), taxonomy, config,
        medium_spec=medium_spec, strict_medium=not args.allow_unknown_medium,
    )
    out = Path(args.out)
    _write_multi_target_outputs(
        result,
        taxonomy,
        out,
        diagnostics=diagnose_model_pool(taxonomy, targets[0]),
        target_preset=args.target_preset,
        user_weights=dict(zip(targets, weights, strict=True)),
        carbon_numbers=carbon_numbers,
        carbon_sources=carbon_sources,
    )
    print(f"multi-target search complete (targets={','.join(targets)}) -> {out}")
    print(f"  metric: {result.metric} [{result.score_unit}]")
    print(
        f"  evaluated: {result.n_candidates_evaluated}/{result.n_candidates_total}"
        f" | ranked: {len(result.ranks)} | unevaluable: {len(result.unevaluated)}"
    )
    if not result.ranks:
        print("  no evaluable candidate: there is no best combination for this target set")
    if result.ranks:
        best = result.ranks[0]
        flux_str = ", ".join(f"{m}={best.target_fluxes.get(m, 0.0):.4g}" for m in targets)
        print(
            f"  best: {'+'.join(best.members)} score={best.weighted_score:.4g} "
            f"pareto={best.pareto} ({flux_str})"
        )
        if best.missing_targets:
            print(f"  note: no exchange for {','.join(best.missing_targets)} (counted as 0)")
    for warning in result.warnings:
        print(f"  warning: {warning}")
    _emit_workflow_manifest(
        out,
        "multi_target_model_pool_search",
        lambda: _search_hash_components(
            "multi_target_model_pool_search", args, taxonomy, medium_spec,
            target_spec={
                "targets": list(targets),
                "target_preset": args.target_preset,
                "target_exchanges": result.target_exchanges,
                "directions": result.directions,
                "mode": "multi_target",
                "multi_metric": result.metric,
                "score_unit": result.score_unit,
                "normalizer": result.normalizer,
                # Effective weights are what the LP saw; user weights and the carbon numbers that
                # produced them are recorded separately so the derivation is auditable.
                "effective_weights": result.weights,
                "user_weights": dict(zip(targets, weights, strict=True)),
                "carbon_numbers": carbon_numbers,
                "carbon_number_sources": carbon_sources,
            },
            search_spec={
                "min_size": args.min_size,
                "max_size": args.max_size,
                "strategy_resolved": result.strategy,
                "top_k": args.top_k,
                "seed": args.seed,
                "exhaustive_max": config.exhaustive_max,
            },
        ),
        status=_worst_status(
            "ok" if result.ranks else "failed",
            "degraded" if result.unevaluated else "ok",
        ),
        artifacts=["search_summary.json", "search_rankings.csv", "pool_taxonomy.csv"],
        warnings=list(result.warnings),
        summary={
            "n_candidates_total": result.n_candidates_total,
            "n_candidates_ranked": len(result.ranks),
            "n_candidates_failed": len(result.unevaluated),
            "best_members": list(result.ranks[0].members) if result.ranks else None,
            "best_score": (
                _finite_or_none(result.ranks[0].weighted_score) if result.ranks else None
            ),
        },
    )
    return _exit_code_for_status(
        _worst_status(
            "ok" if result.ranks else "failed",
            "degraded" if result.unevaluated else "ok",
        ),
        args,
    )


def _write_multi_target_outputs(
    result: Any,
    taxonomy: Any,
    out: Path,
    *,
    diagnostics: list[Any] | None = None,
    target_preset: str | None = None,
    user_weights: dict[str, float] | None = None,
    carbon_numbers: dict[str, int] | None = None,
    carbon_sources: dict[str, str] | None = None,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    taxonomy.to_csv(out / "pool_taxonomy.csv", index=False)
    # D9: `cmig workflows` advertises pool_diagnostics.csv and figures for `cmig search`; the
    # multi-target path emitted neither.
    if diagnostics is not None:
        _write_pool_diagnostics_csv(diagnostics, out / "pool_diagnostics.csv")
    targets = list(result.targets)
    fieldnames = (
        ["rank", "members", "weighted_score", "pareto", "community_growth", "status"]
        + [f"flux_{t}" for t in targets]
        + [f"score_{t}" for t in targets]
        # B3: flux 열이 한 해에서 온 것인지(joint) 표적별 독립 해인지 반드시 함께 읽혀야 한다.
        + ["flux_basis", "missing_targets", "diagnostic"]
    )
    def _multi_record(row: Any) -> dict[str, Any]:
        record: dict[str, Any] = {
            "rank": row.rank if row.rank > 0 else "",
            "members": "+".join(row.members),
            "weighted_score": _finite_csv(row.weighted_score),
            "pareto": row.pareto,
            "community_growth": _finite_csv(row.community_growth),
            "status": row.status,
            "flux_basis": row.flux_basis,
            "missing_targets": ";".join(row.missing_targets),
            "diagnostic": row.diagnostic or "",
        }
        for t in targets:
            record[f"flux_{t}"] = _finite_csv(row.target_fluxes.get(t, float("nan")))
            record[f"score_{t}"] = _finite_csv(row.target_scores.get(t, float("nan")))
        return record

    with open(out / "search_rankings.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in result.ranks:
            writer.writerow(_multi_record(row))
    # P0-C: 평가 불가 후보는 랭킹 CSV 에서 완전히 빠지고 별도 파일로만 나간다.
    if result.unevaluated:
        with open(out / "search_unevaluated.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in result.unevaluated:
                writer.writerow(_multi_record(row))
    ranked_rows = list(result.ranks)
    summary = {
        "kind": "multi_target_model_pool_search",
        # B7: 요약이 status 를 쓰지 않아 inspect-run 이 "unknown" 을 돌려주던 자리.
        "status": _worst_status(
            "ok" if ranked_rows else "failed",
            "degraded" if result.unevaluated else "ok",
        ),
        "targets": targets,
        "target_preset": target_preset,
        "target_exchanges": result.target_exchanges,
        "directions": result.directions,
        # B3/P1-4: 점수 척도의 출처를 명시한다 — 무차원 정규화 점수와 실제 flux 합은 다른 물건이다.
        "metric": result.metric,
        "score_unit": result.score_unit,
        "weights": result.weights,
        "user_weights": user_weights or {},
        "carbon_numbers": carbon_numbers or {},
        "carbon_number_sources": carbon_sources or {},
        "strategy": result.strategy,
        "normalizer": result.normalizer,
        "solution_semantics": result.solution_semantics,
        "n_pool_members": result.n_pool_members,
        "n_candidates_total": result.n_candidates_total,
        "n_candidates_evaluated": result.n_candidates_evaluated,
        "n_candidates_ranked": len(ranked_rows),
        "n_candidates_failed": len(result.unevaluated),
        # P0-C: 평가 불가 후보는 rank 없이 여기에만 존재한다.
        "unevaluated": [
            {
                "members": list(r.members),
                "status": r.status,
                "target_fluxes": {k: _finite_or_none(v) for k, v in r.target_fluxes.items()},
                "missing_targets": list(r.missing_targets),
                "flux_basis": r.flux_basis,
                "diagnostic": r.diagnostic,
            }
            for r in result.unevaluated
        ],
        "top_ranked": [
            {
                "rank": r.rank,
                "members": list(r.members),
                "weighted_score": _finite_or_none(r.weighted_score),
                "pareto": r.pareto,
                "community_growth": _finite_or_none(r.community_growth),
                "status": r.status,
                "target_fluxes": {k: _finite_or_none(v) for k, v in r.target_fluxes.items()},
                "target_scores": {k: _finite_or_none(v) for k, v in r.target_scores.items()},
                "missing_targets": list(r.missing_targets),
                "flux_basis": r.flux_basis,
                "diagnostic": r.diagnostic,
            }
            for r in result.ranks
        ],
        "warnings": result.warnings,
    }
    summary["artifacts"] = sorted(
        ["pool_taxonomy.csv", "search_rankings.csv", "search_summary.json",
         "search_plot.svg", "search_plot.tiff"]
        + (["pool_diagnostics.csv"] if diagnostics is not None else [])
        + (["search_unevaluated.csv"] if result.unevaluated else [])
    )
    with open(out / "search_summary.json", "w") as f:
        json.dump(summary, f, indent=2, allow_nan=False)
    _write_multi_target_figure(result, out / "search_plot.svg")
    _prune_stale_workflow_artifacts(out, KNOWN_SEARCH_ARTIFACTS, summary["artifacts"])


def _search_hash_components(
    kind: str,
    args: argparse.Namespace,
    taxonomy: Any,
    medium_spec: Any,
    *,
    target_spec: dict[str, Any],
    search_spec: dict[str, Any],
) -> dict[str, Any]:
    """Determining inputs of a model-pool search: pool bytes, medium, target and search policy."""
    from cmig.core.workflow_manifest import base_components, pool_model_checksum

    components = base_components(
        kind,
        solver_setting=_pool_solver_setting(args),
        model_checksum=pool_model_checksum(taxonomy),
        medium=_medium_component_for(args, medium_spec),
    )
    components["target_spec"] = target_spec
    components["search_spec"] = search_spec
    components["growth_fraction"] = float(args.growth_fraction)
    return components


def _single_model_workflow_base(
    kind: str, args: argparse.Namespace, model_path: Any
) -> dict[str, Any]:
    """Base components for a single-model workflow (dfba), fingerprinting the model file itself."""
    from cmig.core.workflow_manifest import (
        base_components,
        medium_component,
        optional_file_checksum,
    )

    return base_components(
        kind,
        solver_setting=_pool_solver_setting(args),
        model_checksum=optional_file_checksum(model_path) or "unknown",
        medium=medium_component(None, "single_model_no_medium"),
    )


def _workflow_base(
    kind: str,
    args: argparse.Namespace,
    taxonomy: Any,
    *,
    medium: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The six base components, with the pool fingerprint taken from the taxonomy."""
    from cmig.core.workflow_manifest import base_components, pool_model_checksum

    return base_components(
        kind,
        solver_setting=_pool_solver_setting(args),
        model_checksum=pool_model_checksum(taxonomy),
        medium=medium if medium is not None else _medium_component_for(args, None),
    )


def _host_spec_component(args: argparse.Namespace, interface_map: Any = None) -> dict[str, Any]:
    """Everything about the host side that changes the host objective.

    The host model bytes, the reviewed interface map, the objective override and the exchange
    handling all move the answer, and round-2 found none of them recorded anywhere.
    """
    from cmig.core.workflow_manifest import (
        mapping_checksum,
        optional_file_checksum,
    )

    exclude = sorted(_parse_csv_strings(
        args.exclude_metabolites, flag="--exclude-metabolites"
    )) if getattr(args, "exclude_metabolites", None) else []
    return {
        "host_model": str(args.host),
        "host_model_checksum": optional_file_checksum(args.host),
        "host_objective": getattr(args, "host_objective", None),
        "host_medium": str(args.host_medium) if getattr(args, "host_medium", None) else None,
        "host_medium_checksum": optional_file_checksum(getattr(args, "host_medium", None)),
        "microbe_medium": (
            str(args.microbe_medium) if getattr(args, "microbe_medium", None) else None
        ),
        "microbe_medium_checksum": optional_file_checksum(getattr(args, "microbe_medium", None)),
        "interface_map": (
            str(args.interface_map) if getattr(args, "interface_map", None) else None
        ),
        "interface_map_checksum": mapping_checksum(interface_map),
        "exchange_suffix": getattr(args, "exchange_suffix", None),
        "exclude_metabolites": exclude,
        "include_currency_metabolites": bool(
            getattr(args, "include_currency_metabolites", False)
        ),
        "keep_host_uptake": bool(getattr(args, "keep_host_uptake", False)),
    }


def _biomass_basis_component(args: argparse.Namespace) -> dict[str, Any]:
    """The gDW scaling that makes host and microbial fluxes comparable at all."""
    return {
        "kind": args.biomass_basis_kind,
        "source": args.biomass_basis_source,
        "microbial_biomass_gdw": float(args.microbial_biomass_gdw),
        "host_biomass_gdw": float(args.host_biomass_gdw),
    }


def _host_medium_component(args: argparse.Namespace) -> dict[str, Any]:
    """Host workflows carry their media inside host_spec; the medium slot records the microbial
    side plus the fact that no separate --medium was applied."""
    from cmig.core.workflow_manifest import medium_component, optional_file_checksum

    return medium_component(
        getattr(args, "microbe_medium", None),
        optional_file_checksum(getattr(args, "microbe_medium", None)) or "no_microbe_medium",
    )


def _embedded_solve_run_hash(
    taxonomy: Any,
    medium_spec: Any,
    solve_result: Any,
    *,
    tradeoff_f: float,
    namespace_decisions: list[str] | None = None,
) -> str | None:
    """The community solve's own 11-component run_hash, for embedding in a workflow hash.

    [HASH-SINGLE]: this goes through the one canonical implementation
    (`build_run_components` -> `compute_run_hash`) — the workflow envelope never reimplements or
    extends the frozen 11-component contract, it just carries the resulting hash as one value.
    Returns None when the solve did not produce a usable result, so a failed solve cannot be
    fingerprinted as if it had succeeded.
    """
    from cmig.core.manifest import compute_run_hash
    from cmig.core.medium_spec import medium_checksum
    from cmig.io.solve_output import build_run_components, taxonomy_model_checksum

    if getattr(solve_result, "status", None) != "optimal":
        return None
    try:
        from cmig.core.engine import MicomEngine

        components = build_run_components(
            solve_result,
            model_checksum=taxonomy_model_checksum(taxonomy),
            medium_checksum=medium_checksum(medium_spec),
            tradeoff_f=float(tradeoff_f),
            micom_version=MicomEngine().micom_version,
            namespace_decisions=namespace_decisions or [],
        )
    except (ValueError, OSError, ImportError):
        return None
    return compute_run_hash(components)


def _strain_growth_hash_components(
    args: argparse.Namespace,
    taxonomy: Any,
    medium_spec: Any,
    community_result: Any,
    community_medium: dict[str, float],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Determining inputs of an alone-vs-community comparison.

    The namespace-bridge decisions belong in the hash: which metabolites the community offered,
    and which each member had no exchange for, is what makes the two legs comparable at all
    (phase-3 P0-A). Two runs that bridged differently are not the same experiment.
    """
    from cmig.core.workflow_manifest import base_components, pool_model_checksum

    components = base_components(
        "strain_growth",
        solver_setting=_pool_solver_setting(args),
        model_checksum=pool_model_checksum(taxonomy),
        medium=_medium_component_for(
            args, medium_spec,
            single_medium_mode=args.single_medium,
            community_medium_metabolites=sorted(community_medium),
            unavailable_per_member={
                str(row["member"]): list(
                    row.get("medium_metabolites_unavailable_to_member") or []
                )
                for row in rows
            },
        ),
    )
    # R5-P3 CC-4: these abundances come *out* of the solve, so they carry solver noise. The
    # canonicalizer no longer rounds (an input that determines the answer must not be blurred), so
    # noise absorption has to happen where the noise enters — exactly as
    # io.solve_output.build_run_components already does for the 11-component solve hash.
    components["abundances"] = {
        str(member): round(float(value), DEFAULT_FLOAT_DECIMALS)
        for member, value in sorted((community_result.abundances or {}).items())
        if value is not None
    }
    components["tradeoff_f"] = float(args.tradeoff_f)
    components["flux_normalization_method"] = getattr(
        community_result, "flux_normalization_method", "pfba"
    )
    components["solve_run_hash"] = _embedded_solve_run_hash(
        taxonomy, medium_spec, community_result, tradeoff_f=args.tradeoff_f
    )
    return components


def _abundance_hash_components(
    args: argparse.Namespace,
    taxonomy: Any,
    medium_spec: Any,
    fractions: list[float],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Determining inputs of an abundance sweep, including the swept grid itself."""
    from cmig.core.workflow_manifest import base_components, pool_model_checksum

    components = base_components(
        "abundance_impact",
        solver_setting=_pool_solver_setting(args),
        model_checksum=pool_model_checksum(taxonomy),
        medium=_medium_component_for(args, medium_spec),
    )
    components["abundances"] = {"swept_member": args.member, "fractions": list(fractions)}
    components["tradeoff_f"] = float(args.tradeoff_f)
    components["target_spec"] = {"target": args.target, "mode": "single_target"}
    components["sweep_spec"] = {"kind": "member_abundance", "n_points": len(fractions)}
    # Phase-3 found the pFBA fallback can fire on some sweep points and not others, which changes
    # the flux-selection rule mid-curve. Record what actually ran, per point.
    components["flux_normalization_method"] = sorted({
        "fba" if "pFBA flux stage failed" in str(row.get("diagnostic") or "") else "pfba"
        for row in rows
    })
    return components


def _pool_solver_setting(args: argparse.Namespace, **extra: Any) -> dict[str, Any]:
    """Solver-level knobs that change the numbers, recorded identically by every command."""
    setting: dict[str, Any] = {"solver": getattr(args, "solver", None)}
    setting.update({k: v for k, v in extra.items() if v is not None})
    return setting


def _medium_component_for(
    args: argparse.Namespace, medium_spec: Any, **bridge: Any
) -> dict[str, Any]:
    """Medium identity + namespace-bridge decisions for the workflow hash."""
    from cmig.core.medium_spec import medium_checksum
    from cmig.core.workflow_manifest import medium_component

    return medium_component(
        getattr(args, "medium", None),
        medium_checksum(medium_spec),
        namespace_bridge=bridge or None,
        allow_unknown=bool(getattr(args, "allow_unknown_medium", False)),
    )


def _emit_workflow_manifest(
    out: Path,
    kind: str,
    build_components: Callable[[], dict[str, Any]],
    *,
    status: str = "ok",
    artifacts: list[str] | None = None,
    warnings: list[str] | None = None,
    summary: dict[str, Any] | None = None,
    diagnostic: str | None = None,
) -> str | None:
    """Write the workflow manifest and echo its run_hash.

    Components are built lazily inside the guard: assembling them touches the filesystem
    (model/interface-map checksums), and a completed analysis must not be discarded because its
    provenance could not be gathered. Failures are reported; a hash is never fabricated.
    """
    from cmig.core.workflow_manifest import write_workflow_manifest

    try:
        run_hash = write_workflow_manifest(
            out, kind, build_components(),
            status=status, artifacts=artifacts, warnings=warnings,
            summary=summary, diagnostic=diagnostic,
        )
    except Exception as error:  # noqa: BLE001 - provenance must never destroy a finished result
        print(
            "  warning: analysis completed but its reproducibility manifest could not be written "
            f"({type(error).__name__}: {error}); this run has no run_hash",
            file=sys.stderr,
        )
        return None
    print(f"  run_hash: {run_hash[:16]}… (manifest.json)")
    return run_hash


# Documented exit contract (Codex D4).
#   0 — analysis ran and the scientific solve succeeded (status ok or degraded)
#   2 — usage/input error; no analysis was attempted
#   3 — artifacts were written but the SCIENTIFIC SOLVE FAILED (status failed)
# Exit 3 exists because "artifacts on disk" and "a result" are different claims: round-2 found a
# host-microbe run with an infeasible host, an empty transferred set and a complete figure set
# still exiting 0, so any shell pipeline gating on $? accepted it as a finding.
EXIT_ANALYSIS_FAILED = 3


def _exit_code_for_status(status: str, args: argparse.Namespace) -> int:
    """Map a run-level status onto the process exit code."""
    if status != "failed":
        return 0
    if getattr(args, "allow_failed_run", False):
        print(
            "  note: --allow-failed-run set; exiting 0 despite a failed solve "
            "(artifacts were written, but this run is not a result)",
            file=sys.stderr,
        )
        return 0
    print(
        f"  analysis failed: artifacts were written to {getattr(args, 'out', '?')} but the "
        f"scientific solve did not succeed (exit {EXIT_ANALYSIS_FAILED}); pass "
        "--allow-failed-run to exit 0 anyway",
        file=sys.stderr,
    )
    return EXIT_ANALYSIS_FAILED


# B6: run-level status 파생 — 하위 상태 중 최악을 최상위로 올린다. 순서가 곧 심각도이고,
# 미등재 문자열은 "알 수 없음"이 아니라 최악(failed)으로 취급한다(성공을 낙관하지 않는다).
_STATUS_SEVERITY: tuple[str, ...] = ("ok", "degraded", "failed")


def _run_status_from_solve(status: str) -> str:
    """solve status(optimal/infeasible/unbounded/solver_failed) → run-level status."""
    return "ok" if status == "optimal" else "failed"


# Legacy summaries wrote raw solve statuses where a run-level tier belongs. Map the known
# successes onto the gate vocabulary; anything unrecognized stays untouched so it is visible
# rather than silently coerced to "ok".
_LEGACY_STATUS_ALIASES: dict[str, str] = {"optimal": "ok", "completed": "ok"}


def _normalize_run_status(status: str) -> str:
    return _LEGACY_STATUS_ALIASES.get(status, status)


def _dfba_run_status(status: str) -> str:
    """dFBA outcome -> run-level tier.

    `stalled` is a real finding (the culture stopped growing), so it degrades rather than fails.
    `infeasible` means no trajectory was produced at all.
    """
    if status == "completed":
        return "ok"
    if status == "stalled":
        return "degraded"
    return "failed"


def _worst_status(*statuses: str) -> str:
    """여러 하위 status → 가장 심각한 것. 알 수 없는 값은 'failed' 로 보수적으로 승격."""
    worst = 0
    for status in statuses:
        worst = max(
            worst,
            _STATUS_SEVERITY.index(status) if status in _STATUS_SEVERITY
            else len(_STATUS_SEVERITY) - 1,
        )
    return _STATUS_SEVERITY[worst]


def _finite_or_none(value: float) -> float | None:
    return value if math.isfinite(value) else None


def _finite_csv(value: float) -> str:
    return "" if not math.isfinite(value) else f"{value:.12g}"


def _write_pool_diagnostics_csv(diagnostics: list[Any], path: Path) -> None:
    """Per-model import/target readiness table. Shared so the multi-target path emits it too (D9).

    `cmig workflows` advertises pool_diagnostics.csv under `cmig search`; the multi-target path
    produced none, so the documented contract was unmet on exactly the workflow the SCFA preset
    was added for.
    """
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "member_id", "file", "readable", "model_id", "n_reactions", "n_exchanges",
                "n_biomass", "n_objective_terms", "has_target_exchange", "matching_exchanges",
                "warnings", "error",
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
                "n_objective_terms": (
                    "" if row.n_objective_terms is None else row.n_objective_terms
                ),
                "has_target_exchange": row.has_target_exchange,
                "matching_exchanges": ";".join(row.matching_exchanges),
                "warnings": ";".join(row.warnings),
                "error": row.error or "",
            })


# R5-P3 CC-3: every artifact these writers may emit, including the conditional ones. A re-run
# into the same --out must not leave the previous run's copy behind to contradict it. Mirrors
# io.solve_output.KNOWN_SOLVE_ARTIFACTS and uses the same helper.
KNOWN_SEARCH_ARTIFACTS = frozenset({
    "pool_taxonomy.csv",
    "pool_diagnostics.csv",
    "search_rankings.csv",
    "search_member_matrix.csv",
    "search_unevaluated.csv",
    "search_summary.json",
    "search_plot.svg",
    "search_plot.tiff",
    "search_scatter.svg",
    "search_scatter.tiff",
})
KNOWN_HOST_SEARCH_ARTIFACTS = frozenset({
    "host_search_rankings.csv",
    "host_search_unevaluated.csv",
    "host_search_summary.json",
    "host_search_plot.svg",
    "host_search_plot.tiff",
})


def _prune_stale_workflow_artifacts(
    out: Path, known: frozenset[str], written: list[str]
) -> None:
    """Delete a previous run's conditional artifacts that this run did not produce."""
    from cmig.io.solve_output import prune_stale_artifacts

    removed = prune_stale_artifacts(out, known, written)
    if removed:
        print(f"  removed stale artifact(s) from a previous run: {', '.join(removed)}")


def _write_search_outputs(result: Any, taxonomy: Any, diagnostics: list[Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    taxonomy.to_csv(out / "pool_taxonomy.csv", index=False)
    _write_pool_diagnostics_csv(diagnostics, out / "pool_diagnostics.csv")
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
    # P0-B: 평가 불가 후보는 --top-k 와 무관하게 전량 별도 파일로 나간다. 랭킹 CSV 에서 잘려
    # 사라지면 "평가되지 않았다"는 사실 자체가 산출물에서 소멸한다(red-team F1).
    if result.unevaluated:
        with open(out / "search_unevaluated.csv", "w", newline="") as f:
            unevaluated_writer = csv.DictWriter(
                f, fieldnames=["members", "status", "diagnostic"]
            )
            unevaluated_writer.writeheader()
            for row in result.unevaluated:
                unevaluated_writer.writerow({
                    "members": "+".join(row.members),
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
    # A-B9: a model whose objective is a many-term combination does not report a growth rate.
    multi_term = sorted(
        row.member_id for row in diagnostics
        if row.n_objective_terms and row.n_objective_terms > 1
    )
    if n_readable != len(diagnostics):
        search_warnings.append("one or more pool models failed import diagnostics")
    if n_with_target == 0:
        search_warnings.append("target exchange was not detected in any individual pool model")
    if n_with_biomass != len(diagnostics):
        search_warnings.append("one or more pool models have no detected biomass objective")
    if multi_term:
        search_warnings.append(
            f"objective is a multi-term linear combination for {multi_term}; for those models the "
            "reported growth is an objective value, not a growth rate"
        )
    payload = {
        # P0-B: "ok" 리터럴 금지 — 평가 불가 후보가 있으면 degraded, 하나도 없으면 failed.
        "status": _worst_status(
            "ok" if result.ranks else "failed",
            "degraded" if result.unevaluated else "ok",
        ),
        "target": result.target,
        "target_exchange": result.target_exchange,
        "direction": result.direction,
        "strategy": result.strategy,
        "n_pool_members": result.n_pool_members,
        "n_candidates_total": result.n_candidates_total,
        "n_candidates_evaluated": result.n_candidates_evaluated,
        "n_candidates_ranked": len(result.ranks),
        "n_candidates_failed": len(result.unevaluated),
        "unevaluated": [
            {
                "members": list(row.members),
                "status": row.status,
                "diagnostic": row.diagnostic,
            }
            for row in result.unevaluated
        ],
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
        ] + (["search_unevaluated.csv"] if result.unevaluated else []),
    }
    atomic_write_text(
        out / "search_summary.json",
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )
    _write_search_svg(result, out / "search_plot.svg")
    _write_search_scatter_svg(result, out / "search_scatter.svg")
    _write_search_tiff(result, out / "search_plot.tiff")
    _write_search_scatter_tiff(result, out / "search_scatter.tiff")
    _prune_stale_workflow_artifacts(out, KNOWN_SEARCH_ARTIFACTS, payload["artifacts"])


# P1-F: publication figure constants, shared by every writer so the outputs agree.
#
# Okabe-Ito — the standard colourblind-safe qualitative palette. Round-2 measured the previous
# ColorBrewer mix and found #2b8cbe vs #756bb1 at ΔE(deuteranopia) = 4.7, below the legibility
# floor; every Okabe-Ito pair stays well clear of it under protan/deutan/tritan simulation.
OKABE_ITO: tuple[str, ...] = (
    "#0072B2",   # blue
    "#E69F00",   # orange
    "#009E73",   # bluish green
    "#CC79A7",   # reddish purple
    "#56B4E9",   # sky blue
    "#D55E00",   # vermillion
    "#F0E442",   # yellow
    "#000000",   # black
)
# A font *stack*: the R/ggplot path aborted on `unknown family 'Arial'` and matplotlib silently
# fell back to DejaVu, so the two backends disagreed. Naming the fallbacks makes them agree.
FONT_STACK: tuple[str, ...] = ("Arial", "Helvetica", "DejaVu Sans")
# Journals reject uncompressed RGBA TIFFs; 600 dpi is the line-art expectation.
FIGURE_TIFF_DPI = 600

# Units live in the JSON summaries already — these are the axis strings that carry them.
UNIT_GROWTH = "h$^{-1}$"
UNIT_FLUX = "mmol gDW$^{-1}$ h$^{-1}$"
UNIT_HOST_FLUX = "mmol gDW$_{host}^{-1}$ h$^{-1}$"
UNIT_CARBON = "mmol C gDW$^{-1}$ h$^{-1}$"


def _load_matplotlib_pyplot() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": list(FONT_STACK),
        "axes.titlesize": 14,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        # Keep SVG text as text so a figure can still be re-typeset; the previous default
        # outlined every glyph to a <path>, making half the figure set uneditable.
        "svg.fonttype": "none",
    })
    return plt


def _direction_phrase(direction: str) -> str:
    """`max_uptake` -> "uptake" so an uptake search is not titled a "production" search."""
    return "uptake" if "uptake" in str(direction) else "production"


def _polish_matplotlib_axes(ax: Any, *, grid_axis: str = "x") -> None:
    ax.grid(True, axis=grid_axis, color="#d9dee3", linewidth=0.7, alpha=0.85)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _add_panel_letters(axes: Any, *, start: int = 0) -> None:
    """A/B/C in the top-left of each panel — required on any composite figure."""
    for offset, ax in enumerate(axes):
        ax.text(
            -0.085, 1.06, chr(ord("A") + start + offset),
            transform=ax.transAxes, fontsize=13, fontweight="bold",
            va="bottom", ha="right",
        )


def save_publication_tiff(fig: Any, out_tiff: Path, *, dpi: int = FIGURE_TIFF_DPI) -> None:
    """TIFF at 600 dpi, RGB, LZW — the three things submission portals check.

    matplotlib writes RGBA with ``compression=raw`` by default, which produced 8.8-21.3 MB files
    with an alpha channel. Flattening onto white and LZW-compressing cuts that by ~10x and removes
    the alpha, without touching the rendered content.
    """
    fig.savefig(
        out_tiff,
        format="tiff",
        dpi=dpi,
        facecolor="white",
        pil_kwargs={"compression": "tiff_lzw"},
    )
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - PIL ships with matplotlib
        return
    with Image.open(out_tiff) as image:
        if image.mode == "RGB":
            return
        flattened = Image.new("RGB", image.size, (255, 255, 255))
        flattened.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
        info = dict(image.info)
    flattened.save(
        out_tiff, format="tiff", compression="tiff_lzw",
        dpi=info.get("dpi", (dpi, dpi)),
    )


def _save_screening_figure(fig: Any, out_svg: Path, out_tiff: Path) -> None:
    fig.tight_layout()
    fig.savefig(out_svg, format="svg")
    save_publication_tiff(fig, out_tiff)


def _write_dfba_outputs(
    result: Any,
    out: Path,
    *,
    model_path: Path,
    solver: str,
    config: dict[str, Any],
) -> None:
    from cmig.core.dfba import (
        audit_dfba_balance,
        build_timecourse,
        timecourse_rows,
        write_timecourse,
    )

    out.mkdir(parents=True, exist_ok=True)
    table = build_timecourse(result)
    write_timecourse(table, out / "timecourse.parquet")
    rows = timecourse_rows(result)
    with open(out / "dfba_timecourse.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["t", "series", "value"])
        writer.writeheader()
        writer.writerows(rows)
    final = result.timecourse[-1]
    balance_audit = audit_dfba_balance(result)
    payload = {
        "status": result.status,
        "diagnostic": result.diagnostic,
        "model": str(model_path),
        "solver": solver,
        "config": config,
        "managed_exchanges": result.managed_exchanges,
        # D5: what the run actually ate outside the tracked set, and why that matters.
        "untracked_uptake": result.untracked_uptake,
        "n_untracked_uptake": len(result.untracked_uptake),
        "warnings": list(result.warnings),
        "n_timepoints": len(result.timecourse),
        "final_t": final.t,
        "final_biomass": final.biomass,
        "final_growth_rate": final.growth_rate,
        "final_concentrations": final.concentrations,
        "integration_balance": balance_audit.__dict__,
        "artifacts": [
            "timecourse.parquet",
            "dfba_timecourse.csv",
            "dfba_timecourse.svg",
            "dfba_timecourse.tiff",
            "dfba_summary.json",
        ],
    }
    atomic_write_text(
        out / "dfba_summary.json",
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
        axes[0].plot(
            [x for x, _ in biomass], [y for _, y in biomass],
            color=OKABE_ITO[0], linewidth=2,
        )
        final_t, final_biomass = biomass[-1]
        axes[0].text(
            final_t,
            final_biomass,
            f" final {final_biomass:.3g}",
            va="center",
            ha="left",
            fontsize=9,
            color=OKABE_ITO[0],
        )
    axes[0].set_title("Dynamic FBA time course", loc="left", pad=10)
    axes[0].set_ylabel("Biomass (gDW L$^{-1}$)")
    _polish_matplotlib_axes(axes[0], grid_axis="y")
    growth = series.get("growth_rate", [])
    if growth:
        growth_plot = [(x, y) for x, y in growth if x > 0.0]
        if not growth_plot:
            growth_plot = growth
        axes[1].plot(
            [x for x, _ in growth_plot],
            [y for _, y in growth_plot],
            color=OKABE_ITO[7],
            linewidth=1.8,
            marker="o",
            markersize=3.8,
        )
        axes[1].ticklabel_format(axis="y", style="plain", useOffset=False)
    axes[1].set_ylabel(f"Growth rate ({UNIT_GROWTH})")
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
    axes[2].set_xlabel("Time (h)")
    axes[2].set_ylabel("Concentration (mmol L$^{-1}$)")
    if metabolites:
        axes[2].legend(loc="best", frameon=False, fontsize=9)
    _add_panel_letters(axes)
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
        color=OKABE_ITO[0],
        label="Single model",
    )
    ax.barh(
        [y - offset for y in positions],
        community,
        height=0.32,
        color=OKABE_ITO[2],
        label="Community",
    )
    ax.set_yticks(positions)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    # A-B9: iAF987 ships a 283-term objective, so its optimum is an objective value, not a growth
    # rate. Labelling the axis "Growth rate" regardless is the misleading part.
    multi_term_members = [
        str(row["member"]) for row in rows
        if (row.get("n_objective_terms") or 1) > 1
    ]
    if multi_term_members:
        ax.set_xlabel(
            f"Objective value ({UNIT_GROWTH}); not a growth rate for "
            f"{', '.join(multi_term_members)}"
        )
    else:
        ax.set_xlabel(f"Growth rate ({UNIT_GROWTH})")
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


def _abundance_impact_plot_series(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Sweep points that may be plotted, plus how many were dropped.

    R5-P3 CC-2: this used to filter on ``target_abundance`` alone and never consult ``status``,
    so a point whose solve raised was drawn as a genuine measurement. A point is plottable only
    if it actually solved.
    """
    plottable = sorted(
        (
            row for row in rows
            if _optional_float(row.get("target_abundance")) is not None
            and str(row.get("status")) == "optimal"
        ),
        key=lambda row: float(row["target_abundance"]),
    )
    return plottable, len(rows) - len(plottable)


def _write_abundance_impact_figures(
    rows: list[dict[str, Any]],
    out: Path,
    *,
    target_member: str,
    target: str,
) -> None:
    plt = _load_matplotlib_pyplot()
    valid_rows, n_dropped = _abundance_impact_plot_series(rows)
    x = [float(row["target_abundance"]) for row in valid_rows]
    # `or 0.0` would turn a legitimate None (or a non-finite value) back into a fabricated zero,
    # so every series is read through _optional_float and left as None; matplotlib renders None
    # as a gap in the line rather than a point on the axis.
    community_growth = [_optional_float(row.get("community_growth")) for row in valid_rows]
    member_growth = [_optional_float(row.get("target_member_growth")) for row in valid_rows]
    member_flux = [_optional_float(row.get("target_member_exchange")) for row in valid_rows]
    community_flux = [_optional_float(row.get("community_target_exchange")) for row in valid_rows]
    influence = [_optional_float(row.get("target_influence_share")) for row in valid_rows]
    fig, axes = plt.subplots(3, 1, figsize=(7.2, 7.4), dpi=300, sharex=True)
    axes[0].plot(x, community_growth, color=OKABE_ITO[0], marker="o", label="Community")
    axes[0].plot(x, member_growth, color=OKABE_ITO[2], marker="o", label=target_member)
    axes[0].set_ylabel(f"Growth rate ({UNIT_GROWTH})")
    # The omission must be visible on the figure itself. A reader who only ever sees the SVG has
    # no other way to learn that part of the sweep was never evaluated.
    title = f"Abundance sensitivity: {target_member}"
    if n_dropped:
        title += f"  —  {n_dropped} of {len(rows)} points not evaluable (omitted)"
    axes[0].set_title(title, loc="left", pad=10)
    axes[0].legend(frameon=False, loc="best")
    _polish_matplotlib_axes(axes[0], grid_axis="y")
    axes[1].plot(x, member_flux, color=OKABE_ITO[3], marker="o", label=f"{target_member} {target}")
    axes[1].plot(x, community_flux, color=OKABE_ITO[5], marker="o", label=f"Community {target}")
    axes[1].set_ylabel(f"Exchange flux ({UNIT_FLUX})")
    axes[1].legend(frameon=False, loc="best")
    _polish_matplotlib_axes(axes[1], grid_axis="y")
    axes[2].plot(x, influence, color=OKABE_ITO[7], marker="o")
    axes[2].set_xlabel(f"{target_member} abundance")
    axes[2].set_ylabel("Abundance-weighted\nsecretion share (fraction)")
    _add_panel_letters(axes)
    finite_influence = [value for value in influence if value is not None]
    axes[2].set_ylim(
        bottom=0.0, top=min(1.0, max(0.1, max(finite_influence, default=0.0) * 1.25))
    )
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
    atomic_write_text(
        out / "spatial_summary.json",
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
    cbar.set_label("Concentration (mmol L$^{-1}$)")
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
    axes[-1].plot(range(len(profile)), profile, color=OKABE_ITO[0], linewidth=2)
    axes[-1].set_title("Final centerline concentration", fontsize=11)
    axes[-1].set_xlabel("x")
    axes[-1].set_ylabel("")
    _polish_matplotlib_axes(axes[-1], grid_axis="y")
    fig.suptitle(f"Spatial medium dynamics: {metabolite}", x=0.02, ha="left", fontsize=14)
    if image is not None:
        cbar = fig.colorbar(image, ax=list(axes[:-1]), fraction=0.035, pad=0.02)
        cbar.set_label("Concentration (mmol L$^{-1}$)")
    fig.savefig(out_svg, format="svg", bbox_inches="tight")
    save_publication_tiff(fig, out_tiff)
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
    metric_unit = {
        "objective_value": UNIT_GROWTH,
        "target_transfer": UNIT_HOST_FLUX,
        "weighted": "dimensionless",
    }.get(metric, "")
    ax.set_xlabel(
        f"{metric.replace('_', ' ')}" + (f" ({metric_unit})" if metric_unit else "")
    )
    ax.margins(x=0.06)
    _polish_matplotlib_axes(ax, grid_axis="x")
    _save_screening_figure(fig, out / "host_search_plot.svg", out / "host_search_plot.tiff")
    plt.close(fig)


_KO_EFFECT_COLORS = {
    "improve": "#2ca25f",
    "worsen": "#e6550d",
    "neutral": "#969696",
    "failed": "#cfcfcf",
}


def _ko_effect_category(status: str, delta: float | None, score_delta: float | None) -> str:
    """Classify a KO row by its effect on the *objective* (direction-aware).

    The bar magnitude is the physical target-flux change, but desirability is direction-aware:
    `score_delta = rank.score - baseline.score` and `score` is already normalized so larger is
    better for every --direction (see score_target_result). So `score_delta > 0` means the
    knockout improves the objective whether the goal is to maximize OR minimize the target
    exchange — coloring by the raw flux-delta sign would invert min_secretion/max_uptake.
    Returns one of: improve | worsen | neutral | failed.
    """
    if status != "ok" or delta is None or not math.isfinite(delta):
        return "failed"
    if score_delta is None or math.isnan(score_delta) or abs(score_delta) <= 1e-12:
        return "neutral"
    return "improve" if score_delta > 0 else "worsen"


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

    direction_word = "secretion" if "secretion" in direction else "uptake"
    goal_word = "less" if direction.startswith("min_") else "more"

    top = rows[:12]
    # barh draws bottom-to-top, so reverse to keep rank #1 at the top.
    plot = list(reversed(top))
    labels = [f"{row['member']}:{row['gene']}" for row in plot]
    deltas = [_optional_float(row.get("target_flux_delta")) for row in plot]
    scores = [_optional_float(row.get("score_delta")) for row in plot]
    statuses = [str(row.get("evaluation_status", "ok")) for row in plot]

    categories = [
        _ko_effect_category(s, d, sc)
        for d, sc, s in zip(deltas, scores, statuses, strict=False)
    ]
    bar_values = [
        (d if (cat != "failed" and d is not None) else 0.0)
        for d, cat in zip(deltas, categories, strict=False)
    ]
    colors = [_KO_EFFECT_COLORS[cat] for cat in categories]

    height = max(3.4, 0.46 * max(len(plot), 1) + 2.1)
    fig, ax = plt.subplots(figsize=(7.8, height), dpi=300)
    if plot:
        ax.barh(labels, bar_values, color=colors, height=0.56)
        ax.axvline(0.0, color="#333333", linewidth=0.9)
        span = max([abs(v) for v in bar_values] + [1.0])
        for idx, (value, cat) in enumerate(zip(bar_values, categories, strict=False)):
            if cat == "failed":
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
        f"{ko_level}s · selection {selection} · goal: {direction}",
        transform=ax.transAxes, fontsize=9.5, color="#555555",
    )
    # Bar = physical flux change; color = effect on the objective (direction-aware).
    ax.set_xlabel(
        f"{target} {direction_word} flux delta vs baseline ({UNIT_FLUX}); colour = effect sign"
    )
    ax.margins(x=0.12)
    _polish_matplotlib_axes(ax, grid_axis="x")
    ax.legend(
        handles=[
            Patch(facecolor=_KO_EFFECT_COLORS["improve"],
                  label=f"improves objective ({goal_word} {direction_word})"),
            Patch(facecolor=_KO_EFFECT_COLORS["worsen"], label="worsens objective"),
            Patch(facecolor=_KO_EFFECT_COLORS["neutral"], label="no change"),
            Patch(facecolor=_KO_EFFECT_COLORS["failed"], label="failed"),
        ],
        loc="lower right", frameon=False, fontsize=8.5,
    )
    _save_screening_figure(fig, out / "gene_ko_plot.svg", out / "gene_ko_plot.tiff")
    plt.close(fig)


def _write_multi_target_figure(result: Any, svg_path: Path) -> None:
    """Stacked per-target contribution bars for a multi-target search (D9).

    Stacked rather than a single total, because the headline finding of the SCFA work is that a
    weighted-sum optimum concentrates on ONE acid — a single total bar would hide exactly that.
    """
    plt = _load_matplotlib_pyplot()
    rows = [row for row in result.ranks[:10] if math.isfinite(row.weighted_score)]
    if not rows:
        return
    targets = list(result.targets)
    labels = ["+".join(row.members) for row in rows]
    height = max(3.6, 0.5 * len(rows) + 1.9)
    fig, ax = plt.subplots(figsize=(8.4, height), dpi=300)
    positions = list(range(len(rows)))
    left = [0.0] * len(rows)
    for index, target in enumerate(targets):
        widths = [max(0.0, float(row.target_scores.get(target, 0.0))) for row in rows]
        ax.barh(
            positions, widths, left=left, height=0.62,
            color=OKABE_ITO[index % len(OKABE_ITO)], label=target,
        )
        left = [a + b for a, b in zip(left, widths, strict=True)]
    ax.set_yticks(positions)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel(f"Score contribution per target ({result.score_unit})")
    ax.set_title(
        f"Multi-target search: {', '.join(targets)} [{result.metric}]", loc="left", pad=10
    )
    ax.legend(
        loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=9,
        title="target",
    )
    _polish_matplotlib_axes(ax, grid_axis="x")
    _save_screening_figure(fig, svg_path, svg_path.with_suffix(".tiff"))
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
    ax.set_title(f"Target {_direction_phrase(result.direction)} search: {result.target}")
    ax.set_xlabel(f"Target exchange flux, {result.target_exchange} ({UNIT_FLUX})")
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
    save_publication_tiff(fig, path)
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
            color=OKABE_ITO[4],
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
    ax.set_xlabel(f"Community growth under target objective ({UNIT_GROWTH})")
    ax.set_ylabel(f"Target exchange flux ({UNIT_FLUX})")
    ax.text(0.0, -0.18, f"Target: {result.target_exchange}", transform=ax.transAxes,
            fontsize=9, color="#555555")
    if len(rows) == 1:
        ax.text(1.0, 1.02, "single candidate", transform=ax.transAxes, ha="right",
                fontsize=10, color="#555555")
    _polish_matplotlib_axes(ax, grid_axis="both")
    fig.tight_layout()
    save_publication_tiff(fig, path)
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
        f'font-weight="700">Target {html.escape(_direction_phrase(result.direction))} '
        f'search: {html.escape(result.target)}</text>',
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
        f'fill="#333">Target exchange flux, {html.escape(result.target_exchange)} '
        f'(mmol gDW⁻¹ h⁻¹); bar length = |flux|, '
        f'objective = {html.escape(result.direction)}</text>'
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
        "scope": "synthetic_demo_values_not_experimental_evidence",
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
    if bool(args.replicate_column) != bool(args.confirm_independent_replicates):
        print(
            "추론통계에는 --replicate-column과 --confirm-independent-replicates를 "
            "함께 지정해야 함",
            file=sys.stderr,
        )
        return 2
    inference_enabled = bool(args.replicate_column)
    try:
        groups = groups_from_sweep_rows(
            rows,
            metric=args.metric,
            group_axis=args.group_axis,
            replicate_column=args.replicate_column,
            replicate_aggregate=args.replicate_aggregate,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    names = sorted(groups)
    test = None
    inference_status = "not_run_no_independent_replicates"
    if inference_enabled and len(names) != 2:
        inference_status = "not_run_requires_exactly_two_groups"
    elif inference_enabled and any(len(groups[name]) < 2 for name in names):
        inference_status = "not_run_fewer_than_two_replicates"
    elif inference_enabled and len(names) == 2:
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
        inference_status = "completed"
    payload = {
        "metric": args.metric,
        "group_axis": args.group_axis,
        "groups": {name: len(groups[name]) for name in names},
        "summary": [s.__dict__ for s in distribution_summary(groups)],
        "test": test,
        "inference": {
            "status": inference_status,
            "replicate_column": args.replicate_column,
            "replicate_aggregate": args.replicate_aggregate,
            "confirmed_independent": bool(args.confirm_independent_replicates),
        },
        "warnings": stats_warnings(
            groups, independent_replicates=inference_enabled
        ),
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
        taxonomy = _read_taxonomy_csv(pd, path)
    else:
        taxonomy = taxonomy_from_model_dir(model_dir, recursive=recursive)
    missing_cols = {"id", "file"} - set(taxonomy.columns)
    if missing_cols:
        raise ValueError(f"taxonomy missing required columns: {sorted(missing_cols)}")
    ids = [str(x) for x in taxonomy["id"]]
    if len(ids) != len(set(ids)):
        raise ValueError("taxonomy id values must be unique")
    return taxonomy


def _read_taxonomy_csv(pd: Any, path: Path) -> Any:
    """Read a taxonomy CSV, turning pandas' parser errors into an actionable message.

    R5-P3 (codex F10): an empty or truncated taxonomy CSV used to reach the user as a raw
    ``pandas.errors.EmptyDataError`` traceback on a default, non-debug code path.
    """
    try:
        return pd.read_csv(path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as e:
        raise ValueError(f"taxonomy CSV 를 읽을 수 없음 ({path}): {type(e).__name__}: {e}") from e


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


def _load_host_interface_map(
    path: str | None, *, accept_unreviewed: bool = False
) -> dict[str, str] | None:
    """Load a reviewed metabolite -> host exchange map.

    A-B8: a map that still carries `needs_review` entries has unconfirmed annotation matches in
    it (including possible D/L stereoisomer swaps). Coupling against those silently is how a
    chemically wrong transfer becomes a published number, so it is refused by default and only
    proceeds — loudly — under an explicit flag.
    """
    if path is None:
        return None
    source = Path(path)
    raw = json.loads(source.read_text())
    if isinstance(raw, dict) and "interface_map" in raw:
        pending = raw.get("needs_review") or {}
        if pending:
            listing = ", ".join(
                f"{met} -> {info.get('host_exchange')} ({info.get('match_type')})"
                if isinstance(info, dict) else f"{met} -> {info}"
                for met, info in sorted(pending.items())
            )
            if not accept_unreviewed:
                raise ValueError(
                    f"interface map {source} still has {len(pending)} unreviewed entries: "
                    f"{listing}. Confirm each and move it into interface_map, or pass "
                    "--accept-unreviewed-map to couple anyway."
                )
            print(
                f"  warning: coupling with {len(pending)} UNREVIEWED interface-map entries "
                f"({listing}); annotation matches can pair chemically distinct metabolites",
                file=sys.stderr,
            )
            merged = dict(raw["interface_map"])
            for met, info in pending.items():
                target = info.get("host_exchange") if isinstance(info, dict) else info
                if target:
                    merged[met] = target
            raw = merged
        else:
            raw = raw["interface_map"]
    if not isinstance(raw, dict):
        raise ValueError("host interface map must be a JSON object")
    mapping: dict[str, str] = {}
    for metabolite, exchange in raw.items():
        if not isinstance(metabolite, str) or not metabolite.strip():
            raise ValueError("host interface map metabolite keys must be non-empty strings")
        if exchange is None:
            continue
        if not isinstance(exchange, str) or not exchange.strip():
            raise ValueError(f"invalid host exchange mapping: {metabolite} -> {exchange}")
        mapping[metabolite] = exchange
    return mapping


def _taxonomy_model_checksum(taxonomy: Any, tax_path: Path) -> str:
    """GEM 바이트와 solve 관련 taxonomy metadata의 결정적 checksum."""
    from cmig.io.solve_output import taxonomy_model_checksum

    return taxonomy_model_checksum(taxonomy, base_dir=tax_path.parent)


def _resolve_taxonomy_model_paths(taxonomy: Any, tax_path: Path) -> Any:
    """taxonomy CSV 기준 상대 경로를 절대 경로로 고정해 CWD 의존성을 제거한다."""
    resolved = taxonomy.copy(deep=True)
    for index in resolved.index:
        raw_path = Path(str(resolved.at[index, "file"]))
        candidates = [raw_path]
        if not raw_path.is_absolute():
            candidates.insert(0, tax_path.parent / raw_path)
        model_path = next((path for path in candidates if path.exists()), None)
        if model_path is None:
            raise ValueError(f"taxonomy model 파일 없음: {raw_path}")
        resolved.at[index, "file"] = str(model_path.resolve())
    return resolved


def _sweep_condition_content_key(
    *,
    model_checksum: str,
    taxonomy_variant: Any,
    solver: str,
    tradeoff_f: float,
    medium_path: str | None,
    bounds: dict[str, list[float]] | None,
    fva: bool,
    fva_metabolites: list[str] | None,
    namespace_decisions: Any,
) -> str:
    """Deterministic content signature for sweep-cache dedup (§10 G4 "동일 run_hash → 캐시 hit").

    Built from the same resolved inputs that determine the solve's run_hash: model bytes
    (`model_checksum` = member set + GEM files), abundance vector, solver, tradeoff_f, medium
    *content* (checksum, so two different paths with identical bytes collide), resolved bounds,
    and the fva flags (which change the recorded profile). Because this is a faithful superset
    of the run_hash components, two conditions sharing this key are guaranteed to produce an
    identical solve, so replaying the cached result is exact rather than an approximation.

    R5-P3 V2: that guarantee was false. ``tradeoff_f`` was rounded to 6 decimals and ``abundance``
    to 9, so `--tradeoff-fs 0.5000001,0.5000004` produced ONE key: the second point's solve was
    skipped and the first point's value *and run_hash* were republished under the second point's
    condition_id — a number attributed to inputs it was never computed for. A cache key for
    answer-determining inputs must be exact. It may be finer than the run_hash (that only costs a
    redundant solve); it must never be coarser (that publishes a wrong number). `json.dumps`
    serializes floats with `repr`, which round-trips exactly, so dropping the rounding is enough.
    """
    from cmig.io.solve_output import file_checksum

    abundance = None
    if "abundance" in getattr(taxonomy_variant, "columns", []):
        abundance = sorted(
            (str(r["id"]), float(r["abundance"]))
            for r in taxonomy_variant.to_dict("records")
        )
    parts = {
        "model_checksum": model_checksum,
        "abundance": abundance,
        "solver": solver,
        "tradeoff_f": float(tradeoff_f),
        "medium": None if medium_path is None else file_checksum(Path(medium_path)),
        "bounds": None if bounds is None else json.dumps(bounds, sort_keys=True),
        "fva": bool(fva),
        "fva_metabolites": None if fva_metabolites is None else sorted(fva_metabolites),
        "namespace": None if namespace_decisions is None else repr(namespace_decisions),
    }
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        taxonomy = _resolve_taxonomy_model_paths(taxonomy, tax_path)
    except ValueError as e:
        print(str(e), file=sys.stderr)
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
    # §10 G4 run-hash cache: content-identical conditions replay instead of re-solving.
    # Keyed by a faithful pre-solve signature of the run_hash components (see helper), so a
    # cache hit is an exact replay. Deterministic failures are cached too (누락 금지 계약 유지).
    cache: dict[str, dict[str, Any]] = {}

    def _emit_profiles(
        cond_id: str, medium_val: Any, solver_val: str, tradeoff_val: float,
        run_hash_val: str, status_val: str, profile_pylist: list[dict[str, Any]],
    ) -> None:
        for profile in profile_pylist:
            profile_rows.append({
                "condition_id": cond_id,
                "axis_medium_variant": None if medium_val is None else str(medium_val),
                "axis_tradeoff_f": float(tradeoff_val),
                "axis_solver": solver_val,
                "run_hash": run_hash_val,
                "status": status_val,
                "metabolite": str(profile.get("metabolite", "")),
                "net_flux": profile.get("net_flux"),
                "ui_flux": profile.get("ui_flux"),
                "label": profile.get("label"),
                "fva_lo": profile.get("fva_lo"),
                "fva_hi": profile.get("fva_hi"),
            })

    try:
        namespace_decisions = (
            load_namespace_decisions(args.namespace_decisions)
            if args.namespace_decisions else None
        )
        fva_enabled = args.fva or args.fva_metabolites is not None
        fva_metabolites = _parse_optional_csv_strings(args.fva_metabolites)
        for cond in enumerate_conditions(axes):
            # Per-condition failure isolation (sweep.py contract: a failed run is recorded with a
            # diagnostic, never dropped, and does not abort the batch). A solver failure on one
            # condition must not lose every other condition's results. Gate/OS errors stay fatal.
            content_key: str | None = None
            try:
                cond_dir = run_root / cond.condition_id
                solver = str(cond.axis_values["solver"])
                tradeoff_f = float(cond.axis_values["tradeoff_f"])
                medium = cond.axis_values.get("medium_variant")
                member_set = cond.axis_values.get("member_set")
                abundance = cond.axis_values.get("abundance")
                bounds_variant = cond.axis_values.get("bounds")
                medium_path = None if medium is None else str(medium)
                taxonomy_variant = _apply_abundance_variant(
                    _apply_member_set(taxonomy, None if member_set is None else str(member_set)),
                    None if abundance is None else str(abundance),
                )
                bounds = (
                    None if bounds_variant is None else _load_bounds_json(str(bounds_variant))
                )
                model_checksum = _taxonomy_model_checksum(taxonomy_variant, tax_path)
                content_key = _sweep_condition_content_key(
                    model_checksum=model_checksum,
                    taxonomy_variant=taxonomy_variant,
                    solver=solver,
                    tradeoff_f=tradeoff_f,
                    medium_path=medium_path,
                    bounds=bounds,
                    fva=fva_enabled,
                    fva_metabolites=fva_metabolites,
                    namespace_decisions=namespace_decisions,
                )
                cached = cache.get(content_key)
                if cached is not None:                       # replay — 재계산 회피 (SC-4)
                    rows.append(SweepRow(
                        condition_id=cond.condition_id,
                        axis_values=cond.axis_values,
                        metric=args.metric,
                        value=cached["value"],
                        run_hash=cached["run_hash"],
                        status=cached["status"],
                        diagnostic=cached["diagnostic"],
                        cache_hit=True,
                    ))
                    _emit_profiles(
                        cond.condition_id, medium, solver, tradeoff_f,
                        cached["run_hash"], cached["status"], cached["profile"],
                    )
                    continue
                outcome = service.solve_community(
                    taxonomy=taxonomy_variant,
                    model_checksum=model_checksum,
                    solver=solver,
                    tradeoff_f=tradeoff_f,
                    medium_path=medium_path,
                    namespace_decisions=namespace_decisions,
                    namespace_policy=(
                        "assume_bigg" if args.assume_bigg_namespace else "require_reviewed"
                    ),
                    strict_medium=not args.allow_unknown_medium,
                    out_dir=cond_dir,
                    bounds=bounds,
                    fva=fva_enabled,
                    fva_metabolites=fva_metabolites,
                )
                status = "ok" if outcome.status == "ok" else "failed"
                value = None if outcome.result is None else float(outcome.result.objective)
                run_hash = outcome.run_hash or ""
                profile_pylist = (
                    outcome.bundle.profile.to_pylist() if outcome.bundle is not None else []
                )
                rows.append(SweepRow(
                    condition_id=cond.condition_id,
                    axis_values=cond.axis_values,
                    metric=args.metric,
                    value=value,
                    run_hash=run_hash,
                    status=status,
                    diagnostic=outcome.diagnostic,
                    cache_hit=False,
                ))
                _emit_profiles(
                    cond.condition_id, medium, solver, tradeoff_f,
                    run_hash, status, profile_pylist,
                )
                cache[content_key] = {
                    "value": value, "run_hash": run_hash, "status": status,
                    "diagnostic": outcome.diagnostic, "profile": profile_pylist,
                }
            except (GateBlockedError, OSError):
                raise  # cross-condition / fatal -> abort the whole sweep
            except Exception as e:  # per-condition solve/data failure -> record and continue
                from cmig.core.diagnostics import Diagnostic

                diag = Diagnostic.from_exception(e).to_json()
                rows.append(SweepRow(
                    condition_id=cond.condition_id,
                    axis_values=cond.axis_values,
                    metric=args.metric,
                    value=None,
                    run_hash="",
                    status="failed",
                    diagnostic=diag,
                    cache_hit=False,
                ))
                if content_key is not None:   # deterministic failure → cache for replay
                    cache[content_key] = {
                        "value": None, "run_hash": "", "status": "failed",
                        "diagnostic": diag, "profile": [],
                    }
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
    _emit_workflow_manifest(
        out,
        "sweep",
        lambda: {
            **_workflow_base("sweep", args, taxonomy, medium=_medium_component_for(args, None)),
            # tradeoff_f is swept, so the axis grid carries it rather than a single value.
            "tradeoff_f": sorted({
                float(row.axis_values["tradeoff_f"]) for row in rows
                if row.axis_values.get("tradeoff_f") is not None
            }),
            "sweep_spec": {
                "kind": "taxonomy_condition_grid",
                "metric": args.metric,
                "fva": bool(args.fva or args.fva_metabolites is not None),
                "fva_metabolites": _parse_optional_csv_strings(args.fva_metabolites),
                "n_runs": len(rows),
                "condition_ids": sorted(str(row.condition_id) for row in rows),
                "namespace_decisions": str(args.namespace_decisions)
                if args.namespace_decisions else None,
                # The per-condition solve hashes ARE the sweep's provenance: each is a full
                # 11-component solve hash, embedded rather than recomputed ([HASH-SINGLE]).
                "condition_run_hashes": sorted(
                    str(row.run_hash) for row in rows if row.run_hash
                ),
            },
        },
        status="ok" if rows else "failed",
        artifacts=["sweep_summary.json", "sweep.parquet", "sweep_profiles.parquet"],
        summary={"n_runs": len(rows), "metric": args.metric},
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
    sv_namespace = sv.add_mutually_exclusive_group()
    sv_namespace.add_argument(
        "--namespace-decisions",
        default=None,
        help="namespace decision JSON; unresolved high-confidence mapping 이 있으면 solve 차단",
    )
    sv_namespace.add_argument(
        "--assume-bigg-namespace",
        action="store_true",
        help="입력 모델이 이미 BiGG namespace임을 명시적으로 확인(검토 파일 우회 audit)",
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
    hmb.add_argument(
        "--microbial-biomass-gdw", type=float, required=True,
        help="microbial community biomass represented by MICOM flux (gDW)",
    )
    hmb.add_argument(
        "--host-biomass-gdw", type=float, required=True,
        help="host biomass basis for host-specific uptake flux (gDW)",
    )
    hmb.add_argument(
        "--biomass-basis-kind",
        required=True,
        choices=["measured", "literature", "validation"],
        help="measured/literature for study results; validation is explicitly non-publication",
    )
    hmb.add_argument(
        "--biomass-basis-source",
        required=True,
        help="measurement method, sample record, or literature citation for both gDW bases",
    )
    hmb.add_argument("--microbe-medium", default=None, help="optional microbial medium csv/json")
    hmb.add_argument(
        "--host-medium",
        default=None,
        help="optional host background medium csv/json; keys may be EX_*_e or BiGG ids",
    )
    hmb.add_argument("--exchange-suffix", default="_e", help="host BiGG exchange suffix")
    hmb.add_argument(
        "--interface-map",
        default=None,
        help="reviewed JSON metabolite->host exchange map (e.g. host-map output)",
    )
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
    hmb.add_argument(
        "--accept-unreviewed-map", action="store_true", dest="accept_unreviewed_map",
        help="couple even though the interface map still has needs_review entries "
        "(annotation matches can pair chemically distinct metabolites, e.g. D/L "
        "stereoisomers); the run is warned and the entries are named",
    )
    hmb.add_argument(
        "--allow-failed-run", action="store_true", dest="allow_failed_run",
        help="exit 0 even when the scientific solve failed (default: exit 3, so a "
        "pipeline gating on $? cannot mistake written artifacts for a result)",
    )
    hmb.add_argument("--out", required=True, help="output directory")
    hmb.set_defaults(func=_cmd_host_microbe_bigg)

    # P1-E: microbial perturbation -> host effect, composed so the two arms cannot drift apart.
    hki = sub.add_parser(
        "host-ko-impact",
        help="microbial gene/reaction knockout -> host objective delta "
        "-> host_ko_impact_summary.json",
    )
    hki.add_argument("--host", required=True, help="host SBML/XML model path")
    hki_src = hki.add_mutually_exclusive_group(required=True)
    hki_src.add_argument("--taxonomy", default=None, help="microbial MICOM taxonomy csv")
    hki_src.add_argument("--model-dir", default=None, help="directory containing microbial GEMs")
    hki.add_argument("--recursive", action="store_true", help="scan --model-dir recursively")
    hki.add_argument(
        "--member", required=True,
        help="member whose gene/reaction is knocked out; every other arm input is held identical",
    )
    hki.add_argument(
        "--ko-level", default="reaction", dest="ko_level", choices=["gene", "reaction"],
        help="knock out reactions directly (default) or genes via GPR",
    )
    hki.add_argument("--genes", default=None, help="comma-separated gene ids (--ko-level gene)")
    hki.add_argument(
        "--reactions", default=None, help="comma-separated reaction ids (--ko-level reaction)"
    )
    hki.add_argument(
        "--target", default="ac",
        help="transferred metabolite whose host delivery delta is reported",
    )
    hki.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    hki.add_argument("--tradeoff-f", type=float, default=0.5, dest="tradeoff_f")
    hki.add_argument(
        "--microbial-biomass-gdw", type=float, required=True,
        help="microbial community biomass represented by MICOM flux (gDW)",
    )
    hki.add_argument(
        "--host-biomass-gdw", type=float, required=True,
        help="host biomass basis for host-specific uptake flux (gDW)",
    )
    hki.add_argument(
        "--biomass-basis-kind", required=True,
        choices=["measured", "literature", "validation"],
        help="measured/literature for study results; validation is explicitly non-publication",
    )
    hki.add_argument(
        "--biomass-basis-source", required=True,
        help="measurement method, sample record, or literature citation for both gDW bases",
    )
    hki.add_argument("--microbe-medium", default=None, help="optional microbial medium csv/json")
    hki.add_argument("--host-medium", default=None, help="optional host background medium csv/json")
    hki.add_argument("--exchange-suffix", default="_e", help="host BiGG exchange suffix")
    hki.add_argument(
        "--interface-map", default=None,
        help="reviewed JSON metabolite->host exchange map (shared by every arm)",
    )
    hki.add_argument(
        "--host-objective", default=None,
        help="optional host reaction id used as the host objective in every arm",
    )
    hki.add_argument("--exclude-metabolites", default=None)
    hki.add_argument("--include-currency-metabolites", action="store_true")
    hki.add_argument("--keep-host-uptake", action="store_true")
    hki.add_argument(
        "--accept-unreviewed-map", action="store_true", dest="accept_unreviewed_map",
        help="couple even though the interface map still has needs_review entries "
        "(annotation matches can pair chemically distinct metabolites, e.g. D/L "
        "stereoisomers); the run is warned and the entries are named",
    )
    hki.add_argument(
        "--allow-failed-run", action="store_true", dest="allow_failed_run",
        help="exit 0 even when the scientific solve failed (default: exit 3, so a "
        "pipeline gating on $? cannot mistake written artifacts for a result)",
    )
    hki.add_argument("--out", required=True, help="output directory")
    hki.set_defaults(func=_cmd_host_ko_impact)

    hm = sub.add_parser(
        "host-map",
        help="host-microbe exchange mapping wizard: matched/normalized/unmatched pre-flight",
    )
    hm.add_argument("--host", required=True, help="host GEM (SBML) path")
    hm_src = hm.add_mutually_exclusive_group(required=True)
    hm_src.add_argument("--taxonomy", default=None, help="MICOM-compatible pool taxonomy csv")
    hm_src.add_argument("--model-dir", default=None, help="directory of microbial GEM files")
    hm.add_argument("--recursive", action="store_true", help="scan --model-dir recursively")
    hm.add_argument("--out", required=True, help="output directory")
    hm.set_defaults(func=_cmd_host_map)

    rf = sub.add_parser(
        "render-figure",
        help="render a run's tidy profile to a publication figure (R ggplot2, matplotlib fallback)",
    )
    rf.add_argument("--run-dir", required=True, dest="run_dir", help="completed run directory")
    rf.add_argument("--out", required=True, help="output figure path (e.g. runs/x/profile.svg)")
    rf.add_argument(
        "--renderer", default="auto", choices=["auto", "r", "matplotlib"],
        help="auto (R if available, else/ on failure matplotlib) | r | matplotlib",
    )
    rf.add_argument("--format", default="svg", choices=["svg", "tiff", "pdf", "eps"])
    rf.add_argument("--title", default="External Profile")
    rf.add_argument("--width", type=float, default=6.0, help="figure width (inches)")
    rf.add_argument("--height", type=float, default=4.0, help="figure height (inches)")
    rf.add_argument("--dpi", type=int, default=600)
    rf.add_argument("--seed", type=int, default=42)
    rf.add_argument(
        "--journal-preset", default="default", dest="journal_preset",
        help="apply a journal's width/height/dpi (default, nature, nature_double, cell, science, "
        "plos); an unknown name is rejected with exit 2",
    )
    rf.set_defaults(func=_cmd_render_figure)

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
        default="target_transfer",
        choices=["weighted", "objective_value", "target_transfer"],
        help="ranking metric",
    )
    hs.add_argument("--host-weight", type=float, default=None, dest="host_weight")
    hs.add_argument("--target-weight", type=float, default=None, dest="target_weight")
    hs.add_argument(
        "--host-reference", type=float, default=None, dest="host_reference",
        help="positive host-objective reference used to make weighted scoring dimensionless",
    )
    hs.add_argument(
        "--target-reference", type=float, default=None, dest="target_reference",
        help="positive target-flux reference used to make weighted scoring dimensionless",
    )
    hs.add_argument("--tradeoff-f", type=float, default=0.5, dest="tradeoff_f")
    hs.add_argument(
        "--microbial-biomass-gdw", type=float, required=True,
        help="microbial community biomass represented by MICOM flux (gDW)",
    )
    hs.add_argument(
        "--host-biomass-gdw", type=float, required=True,
        help="host biomass basis for host-specific uptake flux (gDW)",
    )
    hs.add_argument(
        "--biomass-basis-kind",
        required=True,
        choices=["measured", "literature", "validation"],
        help="measured/literature for study results; validation is explicitly non-publication",
    )
    hs.add_argument(
        "--biomass-basis-source",
        required=True,
        help="measurement method, sample record, or literature citation for both gDW bases",
    )
    hs.add_argument("--microbe-medium", default=None, help="optional microbial medium csv/json")
    hs.add_argument("--host-medium", default=None, help="optional host background medium csv/json")
    hs.add_argument("--exchange-suffix", default="_e", help="host BiGG exchange suffix")
    hs.add_argument(
        "--interface-map", default=None,
        help="reviewed JSON metabolite->host exchange map",
    )
    hs.add_argument(
        "--host-objective",
        default=None,
        help="optional host reaction id to use as the host objective for this run",
    )
    hs.add_argument("--exclude-metabolites", default=None)
    hs.add_argument("--include-currency-metabolites", action="store_true")
    hs.add_argument("--keep-host-uptake", action="store_true")
    hs.add_argument(
        "--accept-unreviewed-map", action="store_true", dest="accept_unreviewed_map",
        help="couple even though the interface map still has needs_review entries "
        "(annotation matches can pair chemically distinct metabolites, e.g. D/L "
        "stereoisomers); the run is warned and the entries are named",
    )
    hs.add_argument(
        "--allow-failed-run", action="store_true", dest="allow_failed_run",
        help="exit 0 even when the scientific solve failed (default: exit 3, so a "
        "pipeline gating on $? cannot mistake written artifacts for a result)",
    )
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
        "--single-medium",
        default="community",
        dest="single_medium",
        choices=["community", "model_default"],
        help="medium for the alone leg: community (default) projects the community's effective "
        "medium onto each member so the comparison is controlled | model_default keeps each "
        "member's native SBML bounds, which reports native capability, NOT an interaction effect",
    )
    sg.add_argument(
        "--allow-unknown-medium",
        action="store_true",
        help="record medium ids absent from the community and continue",
    )
    sg.add_argument(
        "--allow-failed-run", action="store_true", dest="allow_failed_run",
        help="exit 0 even when the scientific solve failed (default: exit 3, so a "
        "pipeline gating on $? cannot mistake written artifacts for a result)",
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
    ai.add_argument(
        "--fva", action="store_true",
        help="report the FVA interval of the target exchange at each sweep point, so a jump "
        "between neighbouring abundances can be read as alternate-optima degeneracy rather "
        "than a dose response",
    )
    ai.add_argument(
        "--allow-failed-run", action="store_true", dest="allow_failed_run",
        help="exit 0 even when the scientific solve failed (default: exit 3, so a "
        "pipeline gating on $? cannot mistake written artifacts for a result)",
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
    gk.add_argument(
        "--rank-by", default="effect", dest="rank_by", choices=["effect", "remaining"],
        help="effect (default): |delta| descending — the knockouts that move the target most, "
        "which is what a suppression screen asks for | remaining: highest remaining target flux "
        "first (the previous ordering, in which a zero-effect KO could hold rank 1)",
    )
    gk.add_argument("--top-k", type=int, default=20, dest="top_k")
    gk.add_argument(
        "--allow-failed-run", action="store_true", dest="allow_failed_run",
        help="exit 0 even when the scientific solve failed (default: exit 3, so a "
        "pipeline gating on $? cannot mistake written artifacts for a result)",
    )
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
    df_user.add_argument(
        "--close-untracked-uptake", action="store_true", dest="close_untracked_uptake",
        help="close every uptake exchange outside --initial before integrating, so growth "
        "cannot be fed by an unconstrained default-medium substrate that is never "
        "depleted (without this, a substrate/Km experiment is not interpretable)",
    )
    df_user.add_argument("--out", required=True, help="output directory")
    df_user.set_defaults(func=_cmd_dfba)
    dfs = sub.add_parser(
        "dfba-sensitivity",
        help="numerical dt x Km sensitivity for a user SBML model",
    )
    dfs.add_argument("--model", required=True, help="SBML model file")
    dfs.add_argument("--solver", default="gurobi", choices=["gurobi", "osqp"])
    dfs.add_argument("--t-end", type=float, default=2.0, dest="t_end")
    dfs.add_argument("--dts", default="0.2,0.1,0.05")
    dfs.add_argument("--kms", default="0.005,0.01,0.02")
    dfs.add_argument("--initial-biomass", type=float, default=0.01, dest="initial_biomass")
    dfs.add_argument("--initial", default=None, dest="initial_concentrations")
    dfs.add_argument("--vmax", default=None)
    dfs.add_argument("--min-dt", type=float, default=1e-4, dest="min_dt")
    dfs.add_argument("--growth-floor", type=float, default=1e-6, dest="growth_floor")
    dfs.add_argument("--out", required=True, help="output directory")
    dfs.set_defaults(func=_cmd_dfba_sensitivity)
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
        "--targets",
        default=None,
        help="comma-separated targets (>=2) for multi-target search, e.g. ac,but — "
        "ranks by weighted-normalized score + Pareto flag (overrides --target)",
    )
    sp.add_argument(
        "--target-preset",
        default=None,
        dest="target_preset",
        choices=sorted(TARGET_PRESETS),
        help="documented target set for multi-target search (scfa = ac,but,lac__D,lac__L,ppa,succ)",
    )
    sp.add_argument(
        "--multi-metric",
        default="normalized_weighted",
        dest="multi_metric",
        choices=["normalized_weighted", "carbon_equivalent", "raw_sum", "pareto"],
        help="multi-target score: normalized_weighted (dimensionless min-max over the candidate "
        "set, not comparable across runs) | carbon_equivalent (weight each target by its carbon "
        "number from the model formula -> mmol C gDW^-1 h^-1) | raw_sum (mmol gDW^-1 h^-1, "
        "ignores that C2 and C4 acids differ) | pareto (epsilon-constraint sweep reporting the "
        "NON-DOMINATED trade-off set instead of one scalarised winner; the scalarised metrics "
        "are optimised at a vertex and therefore favour a single-metabolite specialist)",
    )
    sp.add_argument(
        "--target-weights",
        default=None,
        dest="target_weights",
        help="comma-separated weights matching --targets (default: equal weights)",
    )
    sp.add_argument(
        "--target-directions",
        default=None,
        dest="target_directions",
        help="comma-separated per-target directions matching --targets, e.g. "
        "max_secretion,min_secretion (default: every target uses --direction)",
    )
    sp.add_argument(
        "--direction",
        default="max_secretion",
        choices=["max_secretion", "min_secretion", "max_uptake", "min_uptake"],
        help="default target direction (per-target override via --target-directions)",
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
    sp.add_argument(
        "--allow-failed-run", action="store_true", dest="allow_failed_run",
        help="exit 0 even when the scientific solve failed (default: exit 3, so a "
        "pipeline gating on $? cannot mistake written artifacts for a result)",
    )
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
    ss.add_argument(
        "--replicate-column",
        default=None,
        help="독립 생물학적/실험 replicate ID column (미지정 시 p-value를 계산하지 않음)",
    )
    ss.add_argument(
        "--confirm-independent-replicates",
        action="store_true",
        help="지정한 replicate ID가 독립 반복임을 명시적으로 확인",
    )
    ss.add_argument(
        "--replicate-aggregate", default="mean", choices=["mean", "median"],
        help="같은 group×replicate의 여러 조건을 한 관측치로 집계",
    )
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
    from cmig.cli.publication import add_publication_parsers

    add_publication_parsers(sub)
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
    us_namespace = us.add_mutually_exclusive_group()
    us_namespace.add_argument("--namespace-decisions", default=None)
    us_namespace.add_argument(
        "--assume-bigg-namespace",
        action="store_true",
        help="입력 모델이 이미 BiGG namespace임을 명시적으로 확인",
    )
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

    gui = sub.add_parser("gui", help="launch the CMIG desktop GUI (requires --extra gui)")
    gui.add_argument("--lang", default="en", choices=["en", "ko"], help="UI language")
    gui.add_argument("--width", type=int, default=1500)
    gui.add_argument("--height", type=int, default=950)
    gui.set_defaults(func=_cmd_gui)
    return p


def _cmd_gui(args: argparse.Namespace) -> int:
    """Launch the desktop GUI. Lazy-imports the launcher so the base CLI stays light."""
    from cmig.gui.__main__ import main as gui_main

    return gui_main(
        ["--lang", args.lang, "--width", str(args.width), "--height", str(args.height)]
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
