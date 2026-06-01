"""CMIG CLI entry. Design Ref: §4.1 (EngineService facade 소비) / §5.

version·solvers·golden verify 동작. solve-fixture(C7/P0)=fixture solve→parquet+manifest 산출.
solve --taxonomy --medium 은 P1(후속).
"""

from __future__ import annotations

import argparse
import json
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
    from cmig.service import EngineService

    try:
        outcome = EngineService().solve_fixture(
            solver=args.solver, out_dir=args.out, fva=args.fva, targets=args.targets,
        )
    except ImportError:
        print("solve-fixture 는 엔진 stack 필요: uv sync --extra engine", file=sys.stderr)
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

        from cmig.core.namespace import GateBlockedError, load_namespace_decisions
        from cmig.io.solve_output import file_checksum
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
            model_checksum=file_checksum(tax_path),
            solver=args.solver,
            tradeoff_f=args.tradeoff_f,
            medium_path=args.medium,
            namespace_decisions=namespace_decisions,
            strict_medium=not args.allow_unknown_medium,
            fva=args.fva,
            targets=args.targets,
            out_dir=args.out,
        )
    except ImportError:
        print("solve 는 엔진 stack 필요: uv sync --extra engine", file=sys.stderr)
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


def _parse_csv_floats(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def _cmd_sweep_fixture(args: argparse.Namespace) -> int:
    """Fixture 기반 headless sweep 산출 경로."""
    try:
        from cmig.core.sweep import SweepAxis, run_sweep, write_sweep_parquet
        from cmig.golden_fixture import solve
    except ImportError:
        print("sweep-fixture 는 engine stack 필요: uv sync --extra engine", file=sys.stderr)
        return 2
    axes = [
        SweepAxis("tradeoff_f", _parse_csv_floats(args.tradeoff_fs)),
        SweepAxis("solver", [s.strip() for s in args.solvers.split(",") if s.strip()]),
    ]

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
    df = sub.add_parser("dfba-fixture", help="e_coli_core glucose dFBA → timecourse.parquet")
    df.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    df.add_argument("--t-end", type=float, default=1.0, dest="t_end")
    df.add_argument("--dt", type=float, default=0.1)
    df.add_argument("--initial-biomass", type=float, default=0.01, dest="initial_biomass")
    df.add_argument("--glucose", type=float, default=10.0)
    df.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout summary)")
    df.set_defaults(func=_cmd_dfba_fixture)
    se = sub.add_parser("search-fixture", help="3-member target-max search → search_summary.json")
    se.add_argument("--solver", default="gurobi", choices=["gurobi"], help="LP solver")
    se.add_argument("--metabolite", default="ac", help="target metabolite id")
    se.add_argument("--growth-fraction", type=float, default=0.5, dest="growth_fraction")
    se.add_argument("--top-k", type=int, default=3, dest="top_k")
    se.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout)")
    se.set_defaults(func=_cmd_search_fixture)
    st = sub.add_parser("stats-demo", help="deterministic stats demo → stats_summary.json")
    st.add_argument("--fdr-method", default="fdr_bh", choices=["fdr_bh", "fdr_by"])
    st.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout)")
    st.set_defaults(func=_cmd_stats_demo)
    ns = sub.add_parser("namespace-suggest", help="model exchange namespace decision 초안 생성")
    ns.add_argument("--model", required=True, help="SBML/JSON/MAT model path")
    ns.add_argument("--known-targets", default=None, help="known target metabolite id 목록(txt)")
    ns.add_argument("--source-namespace", default="model")
    ns.add_argument("--target-namespace", default="bigg")
    ns.add_argument("--out", default=None, help="산출 디렉터리(생략 시 stdout)")
    ns.set_defaults(func=_cmd_namespace_suggest)
    sw = sub.add_parser("sweep-fixture", help="fixture parameter sweep → sweep.parquet")
    sw.add_argument("--tradeoff-fs", default="0.3,0.5", dest="tradeoff_fs")
    sw.add_argument("--solvers", default="gurobi")
    sw.add_argument("--metric", default="growth")
    sw.add_argument("--out", required=True, help="산출 디렉터리")
    sw.set_defaults(func=_cmd_sweep_fixture)
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
