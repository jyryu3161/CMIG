"""CLI commands for publication quality and integrated benchmarks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def cmd_model_quality(args: argparse.Namespace) -> int:
    """Audit one model or every model in a directory for publication preflight."""
    try:
        from cmig.core.model_pool import taxonomy_from_model_dir
        from cmig.core.model_quality import audit_model_quality
        from cmig.io.model_import import ModelImportError, load_cobra_model
        from cmig.io.quality_output import write_model_quality_reports
    except ImportError:
        print("model-quality requires the engine stack: uv sync --extra engine", file=sys.stderr)
        return 2
    try:
        if args.model:
            paths = [Path(args.model)]
        else:
            taxonomy = taxonomy_from_model_dir(args.model_dir, recursive=args.recursive)
            paths = [Path(str(path)) for path in taxonomy["file"]]
        missing = [str(path) for path in paths if not path.exists()]
        if missing:
            raise ValueError(f"model files not found: {missing}")
        reports = [
            audit_model_quality(
                load_cobra_model(path),
                source_path=path,
                solver=args.solver,
                check_blocked_reactions=args.check_blocked_reactions,
            )
            for path in sorted(paths, key=lambda item: str(item))
        ]
        artifacts = write_model_quality_reports(reports, args.out)
    except (ModelImportError, OSError, ValueError) as error:
        print(f"model-quality failed: {error}", file=sys.stderr)
        return 2
    print(f"model-quality complete ({len(reports)} models) -> {args.out}")
    print(f"  artifacts: {', '.join(artifacts)}")
    return 0


def cmd_publication_benchmark(args: argparse.Namespace) -> int:
    """Run the integrated real-model publication preflight package."""
    try:
        import pandas as pd

        from cmig.core.dfba import DfbaConfig
        from cmig.core.medium_spec import load_medium
        from cmig.core.model_pool import taxonomy_from_model_dir
        from cmig.core.namespace import GateBlockedError, load_namespace_decisions
        from cmig.core.search import Direction
        from cmig.io.model_import import ModelImportError, load_cobra_model
        from cmig.service.publication_benchmark import (
            PublicationBenchmarkConfig,
            run_publication_benchmark,
        )
    except ImportError:
        print("publication-benchmark requires the engine and stats stack", file=sys.stderr)
        return 2
    from cmig.cli.main import (
        _dfba_initial_concentrations,
        _load_host_interface_map,
        _parse_csv_floats,
        _require_model_exchanges,
    )

    try:
        if args.taxonomy:
            taxonomy_path = Path(args.taxonomy)
            if not taxonomy_path.exists():
                raise ValueError(f"taxonomy file not found: {taxonomy_path}")
            taxonomy = pd.read_csv(taxonomy_path)
            base_dir = taxonomy_path.parent
        else:
            taxonomy = taxonomy_from_model_dir(args.model_dir, recursive=args.recursive)
            base_dir = Path(".")
        missing_columns = {"id", "file"} - set(taxonomy.columns)
        if missing_columns:
            raise ValueError(f"taxonomy missing required columns: {sorted(missing_columns)}")
        decisions = (
            load_namespace_decisions(args.namespace_decisions)
            if args.namespace_decisions else []
        )
        dts = _parse_csv_floats(args.dfba_dts, flag="--dfba-dts")
        kms = _parse_csv_floats(args.dfba_kms, flag="--dfba-kms")
        dfba_model_path = None if args.dfba_model is None else Path(args.dfba_model)
        dfba_config = None
        if dfba_model_path is not None:
            if not dfba_model_path.exists():
                raise ValueError(f"dFBA model file not found: {dfba_model_path}")
            dfba_model = load_cobra_model(dfba_model_path)
            concentrations = _dfba_initial_concentrations(
                dfba_model, args.dfba_initial_concentrations
            )
            _require_model_exchanges(dfba_model, concentrations, flag="--dfba-initial")
            dfba_config = DfbaConfig(
                t_end=args.dfba_t_end,
                dt=min(dts),
                initial_biomass=args.dfba_initial_biomass,
                initial_concentrations=concentrations,
                km=min(kms),
                min_dt=min(args.dfba_min_dt, min(dts)),
            )
        host_path = None if args.host is None else Path(args.host)
        if host_path is not None and not host_path.exists():
            raise ValueError(f"host model file not found: {host_path}")
        config = PublicationBenchmarkConfig(
            taxonomy=taxonomy,
            taxonomy_base_dir=base_dir,
            out_dir=Path(args.out),
            solver=args.solver,
            tradeoff_f=args.tradeoff_f,
            namespace_policy=(
                "assume_bigg" if args.assume_bigg_namespace else "require_reviewed"
            ),
            namespace_decisions=decisions,
            search_target=args.search_target,
            search_direction=Direction(args.search_direction),
            search_min_size=args.search_min_size,
            search_max_size=args.search_max_size,
            search_top_k=args.search_top_k,
            check_blocked_reactions=args.check_blocked_reactions,
            dfba_model=dfba_model_path,
            dfba_config=dfba_config,
            dfba_dts=dts,
            dfba_kms=kms,
            host_model=host_path,
            host_source=_host_source(args),
            host_interface_map=_load_host_interface_map(args.host_interface_map),
            microbial_biomass_gdw=args.microbial_biomass_gdw,
            host_biomass_gdw=args.host_biomass_gdw,
            biomass_basis_kind=args.biomass_basis_kind,
            biomass_basis_source=args.biomass_basis_source,
            host_medium=(
                None if args.host_medium is None else load_medium(args.host_medium).uptake
            ),
            keep_host_uptake=args.keep_host_uptake,
        )
        manifest = run_publication_benchmark(config)
    except (GateBlockedError, ModelImportError, OSError, ValueError) as error:
        print(f"publication-benchmark failed: {error}", file=sys.stderr)
        return 2
    payload = json.loads(manifest.read_text())
    print(f"publication-benchmark complete -> {manifest}")
    print(f"  overall_passed: {payload['overall_passed']}")
    return 0 if payload["overall_passed"] else 1


def _host_source(args: argparse.Namespace) -> dict[str, str]:
    return {
        key: value
        for key, value in {
            "name": args.host_name,
            "version": args.host_version,
            "url": args.host_source_url,
            "doi": args.host_doi,
        }.items()
        if value
    }


def add_publication_parsers(sub: Any) -> None:
    """Register publication-oriented subcommands on an argparse subparser collection."""
    mq = sub.add_parser(
        "model-quality", help="GEM quality audit -> model_quality.json + model_quality.csv"
    )
    mq_source = mq.add_mutually_exclusive_group(required=True)
    mq_source.add_argument("--model", default=None, help="single SBML/JSON/MAT model")
    mq_source.add_argument("--model-dir", default=None, help="directory containing GEM files")
    mq.add_argument("--recursive", action="store_true")
    mq.add_argument("--solver", default="gurobi", choices=["gurobi"])
    mq.add_argument("--check-blocked-reactions", action="store_true")
    mq.add_argument("--out", required=True, help="output directory")
    mq.set_defaults(func=cmd_model_quality)

    pb = sub.add_parser(
        "publication-benchmark",
        help="integrated real-GEM quality/community/search/dFBA/host preflight",
    )
    source = pb.add_mutually_exclusive_group(required=True)
    source.add_argument("--taxonomy", default=None)
    source.add_argument("--model-dir", default=None)
    pb.add_argument("--recursive", action="store_true")
    namespace = pb.add_mutually_exclusive_group()
    namespace.add_argument("--namespace-decisions", default=None)
    namespace.add_argument("--assume-bigg-namespace", action="store_true")
    pb.add_argument("--solver", default="gurobi", choices=["gurobi"])
    pb.add_argument("--tradeoff-f", type=float, default=0.5, dest="tradeoff_f")
    pb.add_argument("--search-target", default="ac")
    pb.add_argument(
        "--search-direction",
        default="max_secretion",
        choices=["max_secretion", "min_secretion", "max_uptake", "min_uptake"],
    )
    pb.add_argument("--search-min-size", type=int, default=2)
    pb.add_argument("--search-max-size", type=int, default=2)
    pb.add_argument("--search-top-k", type=int, default=10)
    pb.add_argument("--check-blocked-reactions", action="store_true")
    pb.add_argument("--dfba-model", default=None)
    pb.add_argument("--dfba-t-end", type=float, default=2.0)
    pb.add_argument("--dfba-dts", default="0.2,0.1,0.05")
    pb.add_argument("--dfba-kms", default="0.005,0.01,0.02")
    pb.add_argument("--dfba-initial", default=None, dest="dfba_initial_concentrations")
    pb.add_argument("--dfba-initial-biomass", type=float, default=0.01)
    pb.add_argument("--dfba-min-dt", type=float, default=1e-4)
    pb.add_argument("--host", default=None)
    pb.add_argument("--host-name", default=None)
    pb.add_argument("--host-version", default=None)
    pb.add_argument("--host-source-url", default=None)
    pb.add_argument("--host-doi", default=None)
    pb.add_argument("--host-interface-map", default=None)
    pb.add_argument("--host-medium", default=None)
    pb.add_argument(
        "--microbial-biomass-gdw",
        type=float,
        default=None,
        help="required with --host-interface-map; study-specific microbial biomass (gDW)",
    )
    pb.add_argument(
        "--host-biomass-gdw",
        type=float,
        default=None,
        help="required with --host-interface-map; study-specific host biomass basis (gDW)",
    )
    pb.add_argument(
        "--biomass-basis-kind",
        default=None,
        choices=["measured", "literature", "validation"],
        help="required with --host-interface-map; validation makes publication_ready false",
    )
    pb.add_argument(
        "--biomass-basis-source",
        default=None,
        help="required with --host-interface-map; measurement record or literature citation",
    )
    pb.add_argument("--keep-host-uptake", action="store_true")
    pb.add_argument("--out", required=True)
    pb.set_defaults(func=cmd_publication_benchmark)
