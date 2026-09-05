"""Opt-in, checkpointable post-search perturbations; never part of the GA fitness budget."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from typing import Any

from cmig.core.search import TargetSpec
from cmig.core.search_product import (
    MultiTargetConfig,
    _evaluate_members,
    _evaluate_members_multi_joint,
    _json_safe,
    rank_multi_target,
)


class _ScaledDefaultMedium:
    def __init__(self, engine: Any, factor: float) -> None:
        self.engine, self.factor = engine, factor

    def build_community(self, taxonomy: Any, cmig_solver: str = "gurobi") -> Any:
        community = self.engine.build_community(taxonomy, cmig_solver=cmig_solver)
        community.medium = {key: value * self.factor for key, value in community.medium.items()}
        return community


def validate_top_candidates(request: Any, result: Any, engine: Any, control: Any) -> dict[str, Any]:
    """Compare reoptimised scenarios at fixed units/scales and the same growth policy.

    Removed members' abundances are renormalised by MICOM. Relative growth floors
    are recomputed in each scenario. These are sensitivity analyses, not causal
    contributions or an abundance global optimum. Multi-target validation uses a
    fresh joint weighted baseline, not independently maximised capability values.
    """
    config = request.config
    if config.validation_top < 0:
        raise ValueError("validation_top must be >= 0")
    selected = list(dict.fromkeys(row.members for row in result.ranks))[: config.validation_top]
    records: dict[str, dict[str, Any]] = control.validation_records if control else {}
    used: set[str] = set()
    multi = isinstance(config, MultiTargetConfig)
    specs = (
        [
            TargetSpec(target, config.directions[target], config.weights[target])
            for target in config.targets
        ]
        if multi
        else [TargetSpec(config.target, config.direction)]
    )
    ranges = getattr(result, "normalization_ranges", {})

    def evaluate(
        taxonomy: Any, label: str, parent: tuple[str, ...], *, factor: float = 1.0
    ) -> dict[str, Any]:
        members = tuple(sorted(str(member) for member in taxonomy["id"]))
        key = hashlib.sha256(json.dumps([parent, label], sort_keys=True).encode()).hexdigest()
        used.add(key)
        if key in records:
            return records[key]
        if control:
            control.check()
        medium = request.medium
        chosen_engine = engine
        if factor != 1.0:
            if medium is not None:
                medium = replace(
                    medium, uptake={key: value * factor for key, value in medium.uptake.items()}
                )
            else:
                chosen_engine = _ScaledDefaultMedium(engine, factor)
        common = dict(
            growth_fraction=config.growth_fraction,
            solver=config.solver,
            medium_spec=medium,
            strict_medium=request.strict_medium,
            growth_policy=config.growth_policy,
        )
        if multi:
            point = _evaluate_members_multi_joint(
                chosen_engine,
                taxonomy,
                members,
                specs,
                metric=config.metric,
                normalization_ranges=ranges,
                **common,
            )
            ranks, _ = rank_multi_target(
                [point], specs, metric=config.metric, normalization_ranges=ranges
            )
            row = asdict(ranks[0])
            row["score"] = row.pop("weighted_score")
        else:
            row = asdict(_evaluate_members(chosen_engine, taxonomy, members, specs[0], **common))
        row["scenario"] = label
        records[key] = _json_safe(row)
        if control:
            control.save()
        return records[key]

    reports = []
    for members in selected:
        sub = request.taxonomy[request.taxonomy["id"].astype(str).isin(members)].copy()
        if "abundance" not in sub:
            sub["abundance"] = 1.0
        baseline = evaluate(sub, "baseline", members)
        scenarios = []
        for member in members:
            if len(members) > 1:
                scenarios.append(
                    evaluate(
                        sub[sub["id"].astype(str) != member].copy(), f"leave_out:{member}", members
                    )
                )
                scenarios.append(
                    evaluate(
                        sub[sub["id"].astype(str) == member].copy(),
                        f"monoculture:{member}",
                        members,
                    )
                )
            for factor in (0.5, 2.0):
                perturbed = sub.copy()
                perturbed.loc[perturbed["id"].astype(str) == member, "abundance"] *= factor
                scenarios.append(evaluate(perturbed, f"abundance:{member}*{factor:g}", members))
        for factor in (0.5, 2.0):
            scenarios.append(evaluate(sub, f"medium*{factor:g}", members, factor=factor))
        compared = [
            dict(
                row,
                score_delta=(
                    row["score"] - baseline["score"]
                    if row["score"] is not None and baseline["score"] is not None
                    else None
                ),
            )
            for row in scenarios
        ]
        abundance_trials = [
            row
            for row in [baseline, *scenarios]
            if row["status"] == "optimal"
            and row["score"] is not None
            and (row["scenario"] == "baseline" or row["scenario"].startswith("abundance:"))
        ]
        reports.append(
            {
                "members": list(members),
                "baseline": baseline,
                "scenarios": compared,
                "best_tested_abundance": max(abundance_trials, key=lambda row: row["score"])
                if abundance_trials
                else None,
            }
        )
    return {
        "policy": "post_search_sensitivity_v1",
        "additional_evaluations": len(used),
        "budget_scope": "additional to search unique-consortium budget",
        "abundance_policy": "relative abundance renormalised after removal or perturbation",
        "growth_policy": "scenario-specific maximum and unchanged relative/absolute floors",
        "multi_target_basis": "joint weighted solve at fixed search scales" if multi else None,
        "medium_scope": "declared uptake limits" if request.medium else "model-default uptakes",
        "warnings": [
            "Reoptimised sensitivities are not causal member contributions.",
            "The best tested abundance is a local sensitivity sample, not a global optimum.",
            "Changing medium recomputes the relative growth floor; compare growth as well.",
        ],
        "combinations": reports,
    }
