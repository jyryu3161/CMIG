"""Publication model-quality preflight."""

from __future__ import annotations

import csv
import json

import pytest

cobra = pytest.importorskip("cobra")

from cmig.cli.main import main  # noqa: E402
from cmig.core.model_quality import audit_model_quality  # noqa: E402
from cmig.io.quality_output import write_model_quality_reports  # noqa: E402


def _quality_model():
    from cobra import Metabolite, Model, Reaction

    model = Model("quality_fixture")
    a = Metabolite("a_c", compartment="c", formula="C", charge=0)
    b = Metabolite("b_c", compartment="c", formula="C", charge=0)
    x = Metabolite("x_c", compartment="c", formula="C2", charge=0)
    exchange = Reaction("EX_a_e")
    exchange.add_metabolites({a: -1})
    exchange.bounds = (-10, 1000)
    balanced = Reaction("R_BALANCED")
    balanced.add_metabolites({a: -1, b: 1})
    balanced.gene_reaction_rule = "gene1"
    balanced.annotation = {"doi": "10.0/example"}
    bad = Reaction("R_IMBALANCED")
    bad.add_metabolites({a: -1, x: 1})
    model.add_reactions([exchange, balanced, bad])
    demand_b = model.add_boundary(b, type="demand", reaction_id="DM_b_c")
    model.add_boundary(x, type="demand", reaction_id="DM_x_c")
    model.objective = demand_b
    return model


def test_quality_audit_separates_balanced_imbalanced_and_uncheckable():
    report = audit_model_quality(_quality_model(), solver="gurobi")
    assert report.solve_status == "optimal"
    assert report.objective_value is not None and report.objective_value > 0.0
    assert report.n_mass_checkable == 2
    assert report.n_mass_balanced == 1
    assert report.n_mass_imbalanced == 1
    assert report.n_mass_uncheckable == 0
    assert report.imbalanced_reactions[0].reaction_id == "R_IMBALANCED"
    assert report.gene_association_coverage == 0.5


def test_quality_audit_does_not_count_missing_formula_as_balanced():
    model = _quality_model()
    model.metabolites.get_by_id("b_c").formula = None
    report = audit_model_quality(model, solver="gurobi")
    assert report.n_mass_uncheckable == 1
    assert report.n_mass_balanced == 0
    assert any("not classified as mass balanced" in warning for warning in report.warnings)


def test_quality_writer_and_cli_emit_lossless_json_and_flat_csv(tmp_path):
    model = _quality_model()
    source = tmp_path / "quality.xml"
    cobra.io.write_sbml_model(model, str(source))
    report = audit_model_quality(model, source_path=source, solver="gurobi")
    artifacts = write_model_quality_reports([report], tmp_path / "direct")
    assert artifacts == ["model_quality.json", "model_quality.csv"]

    out = tmp_path / "cli"
    rc = main(["model-quality", "--model", str(source), "--out", str(out)])
    assert rc == 0
    payload = json.loads((out / "model_quality.json").read_text())
    assert payload["n_models"] == 1
    assert payload["reports"][0]["source_checksum"].startswith("sha256:")
    with open(out / "model_quality.csv", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["model_id"] == "quality_fixture"
