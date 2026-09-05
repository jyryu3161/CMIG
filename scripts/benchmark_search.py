"""Run equal-budget multi-seed search benchmarks, optionally against a small real GEM pool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cmig.core.search_benchmark import benchmark_search, synthetic_landscapes
from cmig.core.search_product import _json_safe
from cmig.io.atomic import atomic_write_text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--taxonomy", type=Path)
    source.add_argument("--model-dir", type=Path)
    parser.add_argument("--medium", type=Path)
    parser.add_argument("--target", default="ac")
    parser.add_argument("--size", type=int, default=3)
    parser.add_argument("--pool-size", type=int, default=20)
    parser.add_argument("--budget", type=int, default=100)
    parser.add_argument("--seeds", default="0,1,2,3,4,5,6,7,8,9")
    parser.add_argument("--exhaustive-max", type=int, default=10_000)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    seeds = [int(seed) for seed in args.seeds.split(",")]
    if args.taxonomy or args.model_dir:
        import pandas as pd

        from cmig.core.engine import MicomEngine
        from cmig.core.medium_spec import cli_exact_medium, load_medium
        from cmig.core.model_pool import taxonomy_from_model_dir
        from cmig.core.search import TargetSpec
        from cmig.core.search_product import SearchConfig, _evaluate_members
        from cmig.service.search_service import (
            ConfiguredEngine,
            SearchRequest,
            SearchService,
            search_identity,
        )

        if args.taxonomy:
            taxonomy = pd.read_csv(args.taxonomy)
            taxonomy["file"] = [
                str((args.taxonomy.parent / path).resolve())
                if not Path(path).is_absolute()
                else path
                for path in taxonomy["file"]
            ]
        else:
            taxonomy = taxonomy_from_model_dir(args.model_dir)
        medium = load_medium(args.medium) if args.medium else None
        base_engine = MicomEngine()
        base_engine.cache_models = True
        engine = ConfiguredEngine(base_engine, 1, None)
        request = SearchRequest(taxonomy, SearchConfig(target=args.target, min_size=args.size,
                                                     max_size=args.size), medium)
        SearchService.preflight(request)
        with cli_exact_medium(True):
            result = benchmark_search(
                list(taxonomy["id"].astype(str)),
                lambda members: (
                    _evaluate_members(
                        engine,
                        taxonomy,
                        members,
                        TargetSpec(args.target),
                        growth_fraction=0.5,
                        solver="gurobi",
                        medium_spec=medium,
                        strict_medium=True,
                    ).score
                ),
                min_size=args.size,
                max_size=args.size,
                budget=args.budget,
                seeds=seeds,
                exhaustive_max=args.exhaustive_max,
            )
            result["input_identity"] = search_identity(request)
        payload = {"gem_pool": result}
    else:
        ids = [f"s{index:02}" for index in range(args.pool_size)]
        payload = {
            name: benchmark_search(
                ids,
                fitness,
                min_size=args.size,
                max_size=args.size,
                budget=args.budget,
                seeds=seeds,
                exhaustive_max=args.exhaustive_max,
            )
            for name, fitness in synthetic_landscapes(ids).items()
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(args.out, json.dumps(_json_safe(payload), indent=2, allow_nan=False) + "\n")
    print(f"benchmark saved: {args.out}")


if __name__ == "__main__":
    main()
