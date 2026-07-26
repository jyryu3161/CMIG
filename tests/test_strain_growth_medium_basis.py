"""P0-A / P0-D at the CLI level — strain-growth's controlled comparison and run status.

Supersedes the round-1 version of this file, whose contract three independent round-2 evaluators
falsified: it asserted `single_medium_equals_community_medium: true` from the *request* rather than
from the two effective media, so the flag read `true` when the medium had reached neither leg.
What is pinned now:

- the community's effective medium is projected onto each member across the `_m`/`_e` namespace,
  and the equality flag is computed from the resulting media (P0-A);
- `--single-medium model_default` opts out, and then honestly reports the comparison as
  uncontrolled rather than claiming equality (P0-A);
- run status is derived from the worst sub-status, so failed single legs cannot report `optimal`
  (P0-D).

The community is a double, but the member models are real cobra Models — the bridge is exactly the
part that a too-thin fake let through last time.
"""

from __future__ import annotations

import argparse
import csv
import json

import pytest

cobra = pytest.importorskip("cobra")
pytest.importorskip("pandas")

from cmig.cli import main as cli  # noqa: E402
from cmig.core.engine import SolveResult  # noqa: E402
from cmig.core.single_model import SingleModelResult  # noqa: E402

# The community offers glucose and oxygen; every member exposes the `_e` counterpart.
COMMUNITY_MEDIUM = {"EX_glc__D_m": 10.0, "EX_o2_m": 20.0}


def _member_model(name: str, *, exchanges: dict[str, float]) -> cobra.Model:
    model = cobra.Model(name)
    reactions = []
    for exchange_id, open_uptake in exchanges.items():
        metabolite = cobra.Metabolite(exchange_id.removeprefix("EX_"), compartment="e")
        reaction = cobra.Reaction(exchange_id)
        reaction.add_metabolites({metabolite: -1})
        reaction.bounds = (-open_uptake, 1000.0)
        reactions.append(reaction)
    model.add_reactions(reactions)
    return model


def _community_model() -> cobra.Model:
    """The community stand-in, in the `_m` namespace — a REAL cobra model, not a medium dict.

    Round 6 (track B): this was a hand-rolled double exposing a settable ``medium`` dict and
    metabolite-less ``exchanges``. Both are fictions. ``medium`` is a *derived* view of the
    reaction bounds in cobra, and a boundary reaction with no metabolites has no supplying
    direction at all — so the double could not represent the thing the medium code manipulates,
    and it accepted an application that moved no bound. This file's own preamble already records
    that "a too-thin fake let through last time"; the same lesson applies one layer down.
    """
    model = cobra.Model("community")
    reactions = []
    for exchange_id, open_uptake in COMMUNITY_MEDIUM.items():
        metabolite = cobra.Metabolite(exchange_id.removeprefix("EX_"), compartment="m")
        reaction = cobra.Reaction(exchange_id)
        reaction.add_metabolites({metabolite: -1})
        reaction.bounds = (-open_uptake, 1000.0)
        reactions.append(reaction)
    model.add_reactions(reactions)
    return model


class _FakeEngine:
    def __init__(self, *, single_status: str = "optimal") -> None:
        self.community = _community_model()

    def build_community(self, _taxonomy, cmig_solver="gurobi"):
        return self.community

    def cooperative_tradeoff(self, _community, _tradeoff_f, *, cmig_solver="gurobi"):
        return SolveResult(
            objective=0.4,
            member_growth={"A": 0.5, "B": 0.3},
            abundances={"A": 0.5, "B": 0.5},
            external_exchange={},
            member_exchange={"A": {}, "B": {}},
            status="optimal",
            flux_report_status="full",
            growth_solver="gurobi",
            flux_solver="gurobi",
            members=["A", "B"],
            warnings=["pfba_stage_failed; reporting non-parsimonious flux distribution"],
        )


def _args(out, *, medium=None, single_medium="community"):
    return argparse.Namespace(
        taxonomy=None, model_dir="unused", recursive=False, solver="gurobi",
        tradeoff_f=0.5, medium=medium, single_medium=single_medium,
        allow_unknown_medium=False, out=str(out),
    )


@pytest.fixture
def patched(monkeypatch):
    """Real member models + a community double; single-model solve is stubbed."""
    import cobra.io
    import pandas as pd

    import cmig.core.engine as engine_mod
    import cmig.core.single_model as sm

    models = {
        # A can take up both offered nutrients.
        "A.xml": _member_model("A", exchanges={"EX_glc__D_e": 5.0, "EX_o2_e": 1.0}),
        # B has no oxygen exchange at all — it cannot be offered o2, which is biology.
        "B.xml": _member_model("B", exchanges={"EX_glc__D_e": 5.0}),
    }

    def fake_read(path):
        return models[str(path)]

    def fake_solve(model, *, solver="gurobi", method="FBA"):
        return SingleModelResult(
            objective=0.2, status="optimal", method=method, solver=solver, fluxes={}
        )

    taxonomy = pd.DataFrame({"id": ["A", "B"], "file": ["A.xml", "B.xml"]})
    monkeypatch.setattr(cli, "_load_pool_taxonomy", lambda **_kw: taxonomy)
    monkeypatch.setattr(cli, "_write_strain_growth_figures", lambda *_a, **_kw: None)
    monkeypatch.setattr(cobra.io, "read_sbml_model", fake_read)
    monkeypatch.setattr(sm, "solve_single_model", fake_solve)
    monkeypatch.setattr(engine_mod, "MicomEngine", _FakeEngine)
    return models


def _summary(out):
    return json.loads((out / "strain_growth_summary.json").read_text())


# ── P0-A: the projection actually happens, across namespaces ─────────────────────

def test_community_medium_is_projected_onto_each_member_across_namespaces(patched, tmp_path):
    assert cli._cmd_strain_growth(_args(tmp_path / "run")) == 0
    # The `_m` community offer reached the `_e` member exchanges, at the community's bounds.
    assert patched["A.xml"].reactions.EX_glc__D_e.lower_bound == pytest.approx(-10.0)
    assert patched["A.xml"].reactions.EX_o2_e.lower_bound == pytest.approx(-20.0)
    assert patched["B.xml"].reactions.EX_glc__D_e.lower_bound == pytest.approx(-10.0)


def test_equality_is_measured_and_exempts_only_what_a_member_cannot_exchange(patched, tmp_path):
    assert cli._cmd_strain_growth(_args(tmp_path / "run")) == 0
    summary = _summary(tmp_path / "run")
    basis = summary["medium_basis"]
    assert basis["single_medium_equals_community_medium"] is True
    assert basis["comparison_is_controlled"] is True
    assert basis["single_medium_mode"] == "community"
    assert basis["n_community_medium_metabolites"] == 2
    by_member = {row["member"]: row for row in summary["members"]}
    assert by_member["A"]["medium_metabolites_unavailable_to_member"] == []
    # B has no o2 exchange: recorded as unavailable, and exempt from the equality decision.
    assert by_member["B"]["medium_metabolites_unavailable_to_member"] == ["o2"]
    assert by_member["B"]["single_medium_equals_community"] is True


def test_a_user_medium_reaches_both_legs(patched, tmp_path):
    medium = tmp_path / "medium.csv"
    medium.write_text("exchange_id,uptake_limit\nEX_glc__D_m,3.0\n")
    assert cli._cmd_strain_growth(_args(tmp_path / "run", medium=str(medium))) == 0
    # community got it, and the projection carried the same value to the member models
    assert patched["A.xml"].reactions.EX_glc__D_e.lower_bound == pytest.approx(-3.0)
    basis = _summary(tmp_path / "run")["medium_basis"]
    assert basis["medium_source"].endswith("medium.csv")
    assert basis["medium_checksum"].startswith("medium:")
    assert basis["single_medium_equals_community_medium"] is True


# ── P0-A: the opt-out tells the truth instead of asserting control ───────────────

def test_model_default_mode_reports_the_comparison_as_uncontrolled(patched, tmp_path):
    assert cli._cmd_strain_growth(
        _args(tmp_path / "run", single_medium="model_default")
    ) == 0
    summary = _summary(tmp_path / "run")
    basis = summary["medium_basis"]
    # Native bounds (glc 5.0 vs the community's 10.0) are NOT the community medium.
    assert basis["single_medium_equals_community_medium"] is False
    assert basis["comparison_is_controlled"] is False
    assert summary["status"] == "degraded"
    assert any("NOT attributable to interaction" in w for w in summary["warnings"])
    assert any("native growth capability" in w for w in summary["warnings"])


def test_model_default_mode_leaves_native_bounds_untouched(patched, tmp_path):
    assert cli._cmd_strain_growth(
        _args(tmp_path / "run", single_medium="model_default")
    ) == 0
    assert patched["A.xml"].reactions.EX_glc__D_e.lower_bound == pytest.approx(-5.0)


# ── P0-D: worst sub-status wins ──────────────────────────────────────────────────

def test_failed_single_legs_cannot_report_a_healthy_run(patched, tmp_path, monkeypatch):
    import cmig.core.single_model as sm

    monkeypatch.setattr(
        sm, "solve_single_model", lambda *_a, **_kw: (_ for _ in ()).throw(
            RuntimeError("single solve exploded")
        )
    )
    assert cli._cmd_strain_growth(_args(tmp_path / "run")) == 0
    summary = _summary(tmp_path / "run")
    # Community was optimal, but every alone leg failed → there is no comparison.
    assert summary["community_status"] == "optimal"
    assert summary["status"] == "failed"
    assert any("did not solve" in w for w in summary["warnings"])
    assert all(row["single_status"] == "failed" for row in summary["members"])


def test_one_failed_leg_degrades_rather_than_fails(patched, tmp_path, monkeypatch):
    import cmig.core.single_model as sm

    calls = {"n": 0}

    def flaky(model, *, solver="gurobi", method="FBA"):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first member failed")
        return SingleModelResult(
            objective=0.2, status="optimal", method=method, solver=solver, fluxes={}
        )

    monkeypatch.setattr(sm, "solve_single_model", flaky)
    assert cli._cmd_strain_growth(_args(tmp_path / "run")) == 0
    assert _summary(tmp_path / "run")["status"] == "degraded"


def test_engine_warnings_reach_the_summary(patched, tmp_path):
    """The pFBA fallback must not vanish on this path."""
    assert cli._cmd_strain_growth(_args(tmp_path / "run")) == 0
    assert any("pfba_stage_failed" in w for w in _summary(tmp_path / "run")["warnings"])


def test_csv_carries_the_measured_equality_columns(patched, tmp_path):
    assert cli._cmd_strain_growth(_args(tmp_path / "run")) == 0
    rows = list(csv.DictReader((tmp_path / "run" / "strain_growth.csv").read_text().splitlines()))
    assert [row["member"] for row in rows] == ["A", "B"]
    assert all(row["single_medium_equals_community"] == "True" for row in rows)
    unavailable = {row["member"]: row["medium_metabolites_unavailable_to_member"] for row in rows}
    assert unavailable == {"A": "", "B": "o2"}
