"""SC-01: actual host FVA plus host-search CLI null/range serialization."""

from __future__ import annotations

import csv
import json
from types import SimpleNamespace

import cobra
import pandas as pd
import pytest

from cmig.cli.main import _write_host_ko_impact_outputs, main
from cmig.core.host_coupling import solve_bigg_host
from cmig.core.host_impact import host_impact
from cmig.core.host_ko_impact import arm_from_coupling, assemble_result, compute_host_ko_delta


def alternative_host() -> cobra.Model:
    model = cobra.Model("alternative_host_fuels")
    a = cobra.Metabolite("ac_e", compartment="e")
    b = cobra.Metabolite("but_e", compartment="e")
    p = cobra.Metabolite("p_c", compartment="c")
    for rid, stoich, bounds in [
        ("EX_ac_e", {a: -1}, (-10, 1000)),
        ("EX_but_e", {b: -1}, (-10, 1000)),
        ("acT", {a: -1, p: 1}, (0, 1000)),
        ("butT", {b: -1, p: 1}, (0, 1000)),
        ("BIOMASS", {p: -1}, (0, 5)),
    ]:
        reaction = cobra.Reaction(rid)
        reaction.add_metabolites(stoich)
        reaction.bounds = bounds
        model.add_reactions([reaction])
    model.objective = "BIOMASS"
    return model


def coupling(model: cobra.Model, available: dict[str, float]):
    host = solve_bigg_host(model, available)
    impact = host_impact(available, host)
    return SimpleNamespace(
        host_result=host,
        impact=impact,
        community_status="optimal",
        community_growth=1.0,
        matched_exchanges={m: f"EX_{m}_e" for m in available},
        microbial_secretion=available,
        unmatched_metabolites=[],
        warnings=[],
        unapplied_medium_exchanges=(),
    )


def test_optimal_objective_with_ambiguous_transfer_has_no_point_delta():
    model = alternative_host()
    before = arm_from_coupling(coupling(model, {"ac": 5, "but": 5}), label="before", target="ac")
    after = arm_from_coupling(coupling(model, {"ac": 5, "but": 0}), label="after", target="ac")
    delta = compute_host_ko_delta(before, after)
    assert before.target_identifiability == "ambiguous"
    assert before.target_transfer is None
    assert before.target_transfer_range == pytest.approx((0, 5))
    assert delta.comparable and not delta.target_comparable
    assert delta.delta_host_objective == pytest.approx(0)
    assert delta.delta_target_transfer is None
    assert delta.delta_target_transfer_range == pytest.approx((0, 5))
    assert compute_host_ko_delta(after, before).delta_target_transfer_range == pytest.approx(
        (-5, 0)
    )


def test_fva_readout_failure_retains_objective_without_fabricating_transfer(monkeypatch):
    import cmig.core.host_coupling as host_coupling

    def unavailable(*args, **kwargs):
        raise RuntimeError("injected FVA failure")

    monkeypatch.setattr(host_coupling, "_uptake_fva_ranges", unavailable)
    arm = arm_from_coupling(
        coupling(alternative_host(), {"ac": 5, "but": 5}), label="baseline", target="ac"
    )
    assert arm.host_objective == pytest.approx(5)
    assert arm.target_transfer is None
    assert arm.target_transfer_range is None
    assert arm.target_identifiability == "unavailable"


def test_host_ko_json_and_csv_preserve_null_and_range(tmp_path):
    model = alternative_host()
    before = arm_from_coupling(coupling(model, {"ac": 5, "but": 5}), label="before", target="ac")
    after = arm_from_coupling(coupling(model, {"ac": 5, "but": 0}), label="after", target="ac")
    result = assemble_result(
        target="ac", baseline=before, arms=[after], biomass_basis={"kind": "measured"},
        comparability={},
    )
    assert result.status == "degraded"
    _write_host_ko_impact_outputs(result, tmp_path)
    payload = json.loads((tmp_path / "host_ko_impact_summary.json").read_text())
    assert payload["baseline"]["target_transfer"] is None
    assert payload["baseline"]["target_transfer_range"] == pytest.approx([0, 5])
    assert payload["knockouts"][0]["delta_target_transfer"] is None
    assert payload["knockouts"][0]["delta_target_transfer_range"] == pytest.approx([0, 5])
    with (tmp_path / "host_ko_impact.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["target_transfer"] == ""
    assert float(rows[0]["target_transfer_hi"]) == pytest.approx(5)
    assert rows[1]["delta_target_transfer"] == ""


def test_actual_collapsed_zero_to_five_is_identified_in_per_metabolite_delta(tmp_path):
    model = alternative_host()
    with model:
        model.reactions.acT.upper_bound = 0
        zero = arm_from_coupling(
            coupling(model, {"ac": 5, "but": 5}), label="zero", target="ac"
        )
    five = arm_from_coupling(
        coupling(model, {"ac": 5, "but": 0}), label="five", target="ac"
    )
    assert zero.target_transfer_range == pytest.approx((0, 0))
    assert zero.metabolite_identifiability["ac"] == "identified"
    forward = compute_host_ko_delta(zero, five)
    reverse = compute_host_ko_delta(five, zero)
    assert forward.delta_microbe_to_host["ac"] == pytest.approx(5)
    assert forward.delta_microbe_to_host_ranges["ac"] == pytest.approx((5, 5))
    assert forward.metabolite_identifiability["ac"] == "identified"
    assert reverse.delta_microbe_to_host["ac"] == pytest.approx(-5)
    structurally_zero = arm_from_coupling(
        coupling(model, {"ac": 0, "but": 5}), label="structural_zero", target="ac"
    )
    assert structurally_zero.metabolite_identifiability["ac"] == "identified"
    assert structurally_zero.microbe_to_host_ranges["ac"] == pytest.approx((0, 0))
    assert compute_host_ko_delta(structurally_zero, five).delta_microbe_to_host[
        "ac"
    ] == pytest.approx(5)
    result = assemble_result(
        target="ac", baseline=zero, arms=[five], biomass_basis={"kind": "measured"},
        comparability={},
    )
    _write_host_ko_impact_outputs(result, tmp_path)
    payload = json.loads((tmp_path / "host_ko_impact_summary.json").read_text())
    assert payload["knockouts"][0]["delta_microbe_to_host"]["ac"] == pytest.approx(5)
    with (tmp_path / "host_ko_impact.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert float(rows[0]["target_transfer"]) == pytest.approx(0)
    assert float(rows[1]["delta_target_transfer"]) == pytest.approx(5)


@pytest.mark.parametrize(
    "metric,expected_rc,ranked",
    [
        ("objective_value", 0, 1),
        ("target_transfer", 3, 0),
        ("weighted", 3, 0),
    ],
)
def test_host_search_cli_all_metrics_keep_ambiguous_readout(
    metric,
    expected_rc,
    ranked,
    monkeypatch,
    tmp_path,
):
    import cmig.core.host_coupling as host_coupling

    host_file = tmp_path / "host.xml"
    cobra.io.write_sbml_model(alternative_host(), str(host_file))
    member_file = tmp_path / "member.xml"
    cobra.io.write_sbml_model(alternative_host(), str(member_file))
    tax_file = tmp_path / "taxonomy.csv"
    pd.DataFrame([{"id": "A", "file": str(member_file), "abundance": 1.0}]).to_csv(
        tax_file, index=False
    )
    monkeypatch.setattr(
        host_coupling,
        "run_bigg_host_microbe",
        lambda _tax, host, **kw: coupling(host, {"ac": 5, "but": 5}),
    )
    out = tmp_path / metric
    argv = [
        "host-search-bigg",
        "--host",
        str(host_file),
        "--taxonomy",
        str(tax_file),
        "--min-size",
        "1",
        "--max-size",
        "1",
        "--target",
        "ac",
        "--metric",
        metric,
        "--microbial-biomass-gdw",
        "1",
        "--host-biomass-gdw",
        "1",
        "--biomass-basis-kind",
        "validation",
        "--biomass-basis-source",
        "toy",
        "--out",
        str(out),
    ]
    if metric == "weighted":
        argv += [
            "--host-weight",
            "1",
            "--target-weight",
            "1",
            "--host-reference",
            "5",
            "--target-reference",
            "5",
        ]
    rc = main(argv)
    assert rc == expected_rc
    summary = json.loads((out / "host_search_summary.json").read_text())
    assert summary["n_candidates_evaluated"] == ranked
    row = (summary["top_ranked"] if ranked else summary["unevaluated"])[0]
    assert row["host_objective_value"] == pytest.approx(5)
    assert row["target_transfer"] is None
    assert row["target_transfer_range"] == pytest.approx([0, 5])
    assert row["target_identifiability"] == "ambiguous"
    csv_file = out / ("host_search_rankings.csv" if ranked else "host_search_unevaluated.csv")
    with csv_file.open(newline="") as stream:
        csv_row = next(csv.DictReader(stream))
    assert csv_row["target_transfer"] == ""
    assert float(csv_row["target_transfer_hi"]) == pytest.approx(5)
