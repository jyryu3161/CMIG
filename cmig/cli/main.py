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
import sys
from pathlib import Path
from typing import Any

from cmig import CMIG_CORE_VERSION
from cmig.core.solver import capability_matrix


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
        f"host_biomass={result.host_result.biomass:.4g} "
        f"host_status={result.host_result.status}"
    )
    return 0


def _write_host_microbe_bigg_outputs(result: Any, taxonomy: Any, out: Path) -> None:
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
        "microbe_to_host": result.impact.microbe_to_host,
        "unused_secretion": result.impact.unused_secretion,
        "warnings": result.warnings,
        "artifacts": [
            "microbe_taxonomy.csv",
            "microbial_secretion.csv",
            "host_uptake.csv",
            "microbe_to_host.csv",
            "host_microbe_bigg_summary.json",
        ],
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
            "search_scatter.svg",
            "search_summary.json",
        ],
    }
    (out / "search_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )
    _write_search_svg(result, out / "search_plot.svg")
    _write_search_scatter_svg(result, out / "search_scatter.svg")


def _write_search_svg(result: Any, path: Path) -> None:
    width, height = 900, 420
    margin_left, margin_top, margin_bottom = 90, 54, 95
    plot_w = width - margin_left - 40
    plot_h = height - margin_top - margin_bottom
    rows = [r for r in result.ranks[:10] if math.isfinite(r.target_flux)]
    max_flux = max([abs(r.target_flux) for r in rows] + [1.0])
    bar_gap = 8
    bar_h = max(12, int((plot_h - bar_gap * max(len(rows) - 1, 0)) / max(len(rows), 1)))
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
    parts.append(
        f'<line x1="{axis_x}" y1="{axis_y}" x2="{axis_x + plot_w}" y2="{axis_y}" '
        'stroke="#222" stroke-width="1"/>'
    )
    for i, row in enumerate(rows):
        y = margin_top + i * (bar_h + bar_gap)
        bar_w = int((abs(row.target_flux) / max_flux) * plot_w)
        label = html.escape("+".join(row.members))
        color = "#0b9e77" if row.target_flux >= 0 else "#d95f02"
        parts.extend([
            f'<text x="12" y="{y + bar_h * 0.72:.1f}" font-family="Arial" '
            f'font-size="13">{label}</text>',
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
    for row in rows:
        px, py = x(row.community_growth), y(row.target_flux)
        label = html.escape(str(row.rank))
        title = html.escape("+".join(row.members))
        parts.extend([
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="7" fill="#2b8cbe" opacity="0.86"/>',
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
    df = sub.add_parser("dfba-fixture", help="e_coli_core glucose dFBA → timecourse.parquet")
    df.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    df.add_argument("--t-end", type=float, default=1.0, dest="t_end")
    df.add_argument("--dt", type=float, default=0.1)
    df.add_argument("--initial-biomass", type=float, default=0.01, dest="initial_biomass")
    df.add_argument("--glucose", type=float, default=10.0)
    df.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout summary)")
    df.set_defaults(func=_cmd_dfba_fixture)
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
