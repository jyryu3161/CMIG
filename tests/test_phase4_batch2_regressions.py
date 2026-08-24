"""Phase-4 batch 2 — one regression per known-open item, each written to fail on the old code.

Items, in the order the brief lists them:

1. abundance-impact `target_influence_share` omitted the abundance weight and so reported an
   EXACTLY INVERTED trend (0.75/0.50/0.25 as abundance rose) where the truth is a flat 0.50.
2. A failed scientific solve still exited 0, and a complete interaction figure set was written
   from a failed host solve with no annotation.
3. Cross-feeding edges carried no allocation_method / identifiable and no FVA interval.
4. dFBA could grow on untracked default-medium substrates while the tracked one sat untouched.
5. The multi-target search path emitted neither figures nor pool_diagnostics.csv.
6. gene-ko-search ranked by absolute post-KO score, so a zero-effect KO could hold rank 1.
7. host-map wrote D/L stereoisomer swaps into the same flat dict as the exact matches.
8. n_biomass counted objective TERMS, so a 283-term objective read as "283 biomass reactions"
   and its optimum was plotted under the label "Growth rate".
9. A weighted-sum scalarisation is optimised at a vertex, so it collapses onto one metabolite.

No solver required.
"""

from __future__ import annotations

import json

import pytest

# ── item 1: abundance-weighted shares ────────────────────────────────────────────
from cmig.core.metrics import (  # noqa: E402
    community_contributions,
    target_secretion_share,
    target_turnover_share,
)

# The red-team's measured per-taxon fluxes, with the partner consuming at the matching rate.
_F4_SWEEP = [(0.25, 7.14445047716), (0.50, 3.80404525211), (0.75, 2.71113283097)]


def _f4_case(abundance: float, member_flux: float):
    partner_flux = -member_flux * abundance / (1.0 - abundance)
    exchange = {"iHN637": {"ac": member_flux}, "iYO844": {"ac": partner_flux}}
    abundances = {"iHN637": abundance, "iYO844": 1.0 - abundance}
    return community_contributions(exchange, abundances, "ac")


@pytest.mark.parametrize(("abundance", "member_flux"), _F4_SWEEP)
def test_influence_share_is_flat_across_the_sweep(abundance, member_flux):
    """F4: the abundance-weighted truth is a flat 0.50, not 0.75 -> 0.50 -> 0.25."""
    contributions = _f4_case(abundance, member_flux)
    assert target_turnover_share(contributions, "iHN637") == pytest.approx(0.50, abs=1e-9)


def test_the_old_unweighted_share_would_have_been_inverted():
    """Pins the defect itself: without the abundance weight the trend runs backwards."""
    unweighted = [
        abs(flux) / (abs(flux) + abs(-flux * a / (1 - a)))
        for a, flux in _F4_SWEEP
    ]
    assert unweighted[0] > unweighted[1] > unweighted[2]      # 0.75 -> 0.50 -> 0.25
    weighted = [target_turnover_share(_f4_case(a, f), "iHN637") for a, f in _F4_SWEEP]
    assert weighted[0] == pytest.approx(weighted[2], abs=1e-9)


def test_a_consumer_is_never_credited_as_a_producer():
    """The second half of F4: abs() put consumers in the production numerator."""
    contributions = _f4_case(0.25, 7.14445047716)
    assert target_secretion_share(contributions, "iHN637") == pytest.approx(1.0)
    assert target_secretion_share(contributions, "iYO844") == pytest.approx(0.0)


def test_shares_are_zero_when_nothing_moves():
    contributions = community_contributions({"a": {"ac": 0.0}}, {"a": 1.0}, "ac")
    assert target_turnover_share(contributions, "a") == 0.0
    assert target_secretion_share(contributions, "a") == 0.0


def test_missing_abundance_falls_back_to_unit_weight_not_a_crash():
    contributions = community_contributions({"a": {"ac": 2.0}}, {"a": None}, "ac")
    assert contributions["a"] == pytest.approx(2.0)


# ── item 2: exit contract ────────────────────────────────────────────────────────

import argparse  # noqa: E402

from cmig.cli.main import EXIT_ANALYSIS_FAILED, _exit_code_for_status  # noqa: E402


def _args(**kwargs):
    return argparse.Namespace(out="runs/x", **kwargs)


def test_failed_solve_exits_non_zero():
    """D4: artifacts on disk and a result are different claims."""
    assert _exit_code_for_status("failed", _args(allow_failed_run=False)) == EXIT_ANALYSIS_FAILED
    assert EXIT_ANALYSIS_FAILED != 0


def test_ok_and_degraded_exit_zero():
    for status in ("ok", "degraded"):
        assert _exit_code_for_status(status, _args(allow_failed_run=False)) == 0


def test_allow_failed_run_is_an_explicit_opt_out():
    assert _exit_code_for_status("failed", _args(allow_failed_run=True)) == 0


def test_exit_code_is_distinct_from_the_usage_error_code():
    """2 means 'bad input, nothing ran'; 3 means 'it ran and the science failed'."""
    assert EXIT_ANALYSIS_FAILED != 2


# ── item 3: edge identifiability + FVA ───────────────────────────────────────────

from cmig.core.engine import SolveResult  # noqa: E402
from cmig.core.interactions import (  # noqa: E402
    CROSS_FEEDING_ALLOCATION_METHOD,
    DIRECT_ALLOCATION_METHOD,
    build_tidy,
)
from cmig.core.tidy import EDGES_SCHEMA, TIDY_SCHEMA_VERSION  # noqa: E402


def _crossfeed_result() -> SolveResult:
    return SolveResult(
        objective=0.9,
        member_growth={"A": 0.5, "B": 0.4},
        abundances={"A": 0.5, "B": 0.5},
        external_exchange={"ac": 3.0},
        member_exchange={"A": {"ac": 8.0}, "B": {"ac": -5.0}},
        status="optimal",
        flux_report_status="full",
        growth_solver="gurobi",
        flux_solver="gurobi",
        members=["A", "B"],
    )


def test_edge_schema_carries_identifiability_and_interval_columns():
    names = set(EDGES_SCHEMA.names)
    assert {"allocation_method", "identifiable", "weight_lo", "weight_hi"} <= names
    assert TIDY_SCHEMA_VERSION == "1.3"


def test_cross_feeding_edges_are_marked_unidentifiable():
    """A-B15/B-D6: a shared pool does not identify donor->recipient attribution."""
    edges = build_tidy(_crossfeed_result()).edges.to_pylist()
    cross = [e for e in edges if e["edge_type"] == "cross_feeding"]
    assert cross, "fixture must produce a cross-feeding edge"
    for edge in cross:
        assert edge["allocation_method"] == CROSS_FEEDING_ALLOCATION_METHOD
        assert edge["identifiable"] is False


def test_direct_edges_are_marked_identifiable():
    """Member<->pool edges ARE read off the flux vector; only the attribution is allocated."""
    edges = build_tidy(_crossfeed_result()).edges.to_pylist()
    direct = [e for e in edges if e["edge_type"] in ("secretion", "uptake")]
    assert direct
    for edge in direct:
        assert edge["allocation_method"] == DIRECT_ALLOCATION_METHOD
        assert edge["identifiable"] is True


def test_fva_interval_reaches_direct_edges_when_supplied():
    bundle = build_tidy(_crossfeed_result(), edge_fva={("A", "ac"): (1.0, 9.0)})
    direct = [
        e for e in bundle.edges.to_pylist()
        if e["source_id"] == "A" and e["edge_type"] == "secretion"
    ]
    # tidy 1.3: FVA bounds share the community basis — per-taxon (1.0, 9.0) × abundance 0.5.
    assert direct and direct[0]["weight_lo"] == 0.5 and direct[0]["weight_hi"] == 4.5


def test_an_allocated_weight_never_gets_a_determined_looking_interval():
    """The interval belongs to the exchange flux, not to the pairwise attribution."""
    bundle = build_tidy(_crossfeed_result(), edge_fva={("A", "ac"): (1.0, 9.0)})
    cross = [e for e in bundle.edges.to_pylist() if e["edge_type"] == "cross_feeding"]
    assert cross
    for edge in cross:
        assert edge["weight_lo"] is None and edge["weight_hi"] is None


@pytest.mark.parametrize("golden", [
    "fixtures/pair_acetate_butyrate/expected",
    "fixtures/community_3_member/expected/gurobi",
    "fixtures/community_3_member/expected/osqp",
])
def test_committed_goldens_carry_the_current_schema_version(golden):
    """Bumping TIDY_SCHEMA_VERSION silently invalidates every committed golden.

    schema_version is a hashed column, so a bump makes the golden tests fail with an opaque
    hash mismatch that looks like a numeric regression. This fails first, and says why.
    """
    import pathlib

    import pyarrow.parquet as pq

    root = pathlib.Path(__file__).resolve().parent.parent / golden
    for table in ("nodes", "edges", "profile"):
        stamped = pq.read_table(root / f"{table}.parquet").column("schema_version")[0].as_py()
        assert stamped == TIDY_SCHEMA_VERSION, (
            f"{golden}/{table}.parquet is stamped {stamped} but the code emits "
            f"{TIDY_SCHEMA_VERSION} — regenerate the goldens for the schema bump"
        )


def test_legacy_edge_parquet_upgrades_with_null_identifiability():
    """An old artifact did not record attribution, so "unknown" is the honest upgrade value."""
    import pyarrow as pa

    from cmig.core.tidy import EDGES_SCHEMA_V11, read_legacy_or_upgrade

    legacy = pa.table({
        "schema_version": ["1.1"], "source_id": ["A"], "target_id": ["B"],
        "metabolite": ["ac"], "edge_type": ["cross_feeding"], "weight": [5.0],
        "label": ["secretion"],
    }, schema=EDGES_SCHEMA_V11)
    upgraded = read_legacy_or_upgrade(legacy, "edges").to_pylist()[0]
    assert upgraded["allocation_method"] is None
    assert upgraded["identifiable"] is None
    assert upgraded["schema_version"] == TIDY_SCHEMA_VERSION


# ── item 4: dFBA untracked substrates ────────────────────────────────────────────

from cmig.core.dfba import DfbaConfig, _untracked_warnings  # noqa: E402


def test_untracked_uptake_is_warned_about():
    """D5: biomass rose while managed glucose stayed at exactly 10.0 — it ate something else."""
    warnings = _untracked_warnings({"EX_fru_e": 5.0, "EX_nh4_e": 1.7}, ["EX_glc__D_e"], [])
    assert len(warnings) == 1
    assert "UNCONSTRAINED default-medium substrates" in warnings[0]
    assert "EX_fru_e" in warnings[0]
    assert "NOT interpretable" in warnings[0]
    assert "--close-untracked-uptake" in warnings[0]


def test_no_untracked_uptake_means_no_warning():
    assert _untracked_warnings({}, ["EX_glc__D_e"], []) == []


def test_closing_untracked_uptake_is_reported():
    warnings = _untracked_warnings({}, ["EX_glc__D_e"], ["EX_fru_e", "EX_nh4_e"])
    assert any("closed 2 untracked uptake exchanges" in w for w in warnings)


class _NoExchanges:
    """A model that cannot enumerate its exchanges (cobra's `.exchanges` absent).

    Mirrors the minimal stub `tests/test_dfba.py` uses for the emergency-clamp path — which
    is precisely the shape that crashed the untracked-uptake loop.
    """

    id = "stub"

    class _Reaction:
        lower_bound = -1000.0

    class _Reactions:
        def get_by_id(self, rid):
            return _NoExchanges._Reaction()

    def __init__(self) -> None:
        self.reactions = self._Reactions()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_the_untracked_diagnostic_never_aborts_a_run():
    """The detection loop assumed `model.exchanges` and crashed the emergency-clamp path."""
    from cmig.core.dfba import _record_untracked_uptake

    found: dict[str, float] = {}
    _record_untracked_uptake(_NoExchanges(), object(), ["EX_s"], found)
    assert found == {}


def test_a_flux_vector_missing_an_exchange_is_skipped_not_fatal():
    class _Rxn:
        id = "EX_absent"

    class _Model:
        exchanges = [_Rxn()]

    class _Sol:
        fluxes: dict[str, float] = {}

    from cmig.core.dfba import _record_untracked_uptake

    found: dict[str, float] = {}
    _record_untracked_uptake(_Model(), _Sol(), [], found)
    assert found == {}


def test_an_uncloseable_control_is_refused_rather_than_faked(monkeypatch):
    """Opposite of the diagnostic: if the user asked for the control and we cannot apply it,
    reporting a controlled experiment that never happened would be worse than failing."""
    from cmig.core import single_model
    from cmig.core.dfba import simulate_dfba

    monkeypatch.setattr(single_model, "_require_lp", lambda solver: None)
    monkeypatch.setattr(single_model, "set_model_solver", lambda model, solver: None)

    config = DfbaConfig(
        t_end=0.1, dt=0.1, initial_concentrations={"EX_s": 1.0},
        close_untracked_uptake=True,
    )
    with pytest.raises(ValueError, match="close-untracked-uptake"):
        simulate_dfba(_NoExchanges(), config, solver="gurobi")


def test_close_untracked_uptake_is_a_config_field_defaulting_off():
    """Default off: closing bounds silently would change every existing dFBA result."""
    config = DfbaConfig(t_end=1.0, initial_concentrations={"EX_glc__D_e": 10.0})
    assert config.close_untracked_uptake is False


# ── item 6: KO ranking by effect ─────────────────────────────────────────────────

from cmig.cli.main import _ko_sort_key  # noqa: E402


def _ko(gene: str, score: float, delta: float) -> dict:
    return {
        "member": "iHN637", "gene": gene, "evaluation_status": "ok",
        "score": score, "score_delta": delta,
    }


def test_effect_ranking_puts_the_strongest_suppressor_first():
    """B12/F7: absolute-score ranking put a zero-effect KO at rank 1 and called it 'best'."""
    rows = [
        _ko("LDH_D", 12.11, -9.3e-05),     # no real effect
        _ko("PTAr", 11.38, -0.7346),       # the actual suppressor
        _ko("PTA2", 12.11, -0.000131),
    ]
    rows.sort(key=lambda r: _ko_sort_key(r, "effect"))
    assert rows[0]["gene"] == "PTAr"


def test_remaining_ranking_reproduces_the_old_order():
    rows = [
        _ko("LDH_D", 12.11, -9.3e-05),
        _ko("PTAr", 11.38, -0.7346),
        _ko("PTA2", 12.11, -0.000131),
    ]
    rows.sort(key=lambda r: _ko_sort_key(r, "remaining"))
    assert rows[0]["gene"] == "LDH_D"      # the zero-effect KO, i.e. the reported defect


def test_effect_ranking_treats_a_large_increase_as_a_large_effect():
    """|delta|: a KO that raises the target is as interesting as one that suppresses it."""
    rows = [_ko("a", 1.0, -0.1), _ko("b", 20.0, +9.0)]
    rows.sort(key=lambda r: _ko_sort_key(r, "effect"))
    assert rows[0]["gene"] == "b"


def test_failed_rows_sort_last_in_both_modes():
    good = _ko("good", 5.0, -1.0)
    bad = {**_ko("bad", float("nan"), float("nan")), "evaluation_status": "failed"}
    for mode in ("effect", "remaining"):
        rows = sorted([bad, good], key=lambda r: _ko_sort_key(r, mode))
        assert rows[0]["gene"] == "good"


# ── item 8: objective terms vs biomass reactions ─────────────────────────────────

from cmig.io.model_import import objective_structure_warning  # noqa: E402


def test_multi_term_objective_is_called_out():
    """A-B9: iAF987's 283-term objective read as '283 biomass reactions'."""
    warning = objective_structure_warning(283)
    assert warning is not None
    assert "283 terms" in warning
    assert "not a single biomass reaction" in warning
    assert "objective value" in warning


def test_single_term_objective_is_silent():
    assert objective_structure_warning(1) is None


def test_absent_objective_is_called_out():
    assert "no objective reaction" in (objective_structure_warning(0) or "")


# ── item 9: scalarisation bias and the Pareto alternative ────────────────────────

from cmig.core.search_advanced import pareto_frontier_nd  # noqa: E402
from cmig.core.search_product import (  # noqa: E402
    MULTI_METRIC_UNITS,
    PARETO_EPSILON_GRID,
    SCALARISATION_WARNING,
)


def test_pareto_is_an_available_metric_with_its_own_unit():
    assert "pareto" in MULTI_METRIC_UNITS
    assert "not totally ordered" in MULTI_METRIC_UNITS["pareto"]


def test_scalarisation_warning_names_the_vertex_bias():
    assert "vertex" in SCALARISATION_WARNING
    assert "single-metabolite specialist" in SCALARISATION_WARNING
    assert "--multi-metric pareto" in SCALARISATION_WARNING


def test_epsilon_grid_starts_at_zero_and_increases():
    """0.0 reproduces the plain scalarised vertex; the rest force mixed solutions."""
    assert PARETO_EPSILON_GRID[0] == 0.0
    assert list(PARETO_EPSILON_GRID) == sorted(PARETO_EPSILON_GRID)
    assert len(PARETO_EPSILON_GRID) >= 3


def test_nd_front_keeps_genuine_tradeoffs_and_drops_dominated_points():
    """Six targets: the 2-target helper cannot express this, which is why the flag was always
    False for the SCFA preset."""
    specialist_a = (10.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    specialist_b = (0.0, 10.0, 0.0, 0.0, 0.0, 0.0)
    balanced = (5.0, 5.0, 0.0, 0.0, 0.0, 0.0)
    dominated = (1.0, 1.0, 0.0, 0.0, 0.0, 0.0)
    keep = pareto_frontier_nd([specialist_a, specialist_b, balanced, dominated])
    assert set(keep) == {0, 1, 2}
    assert 3 not in keep


def test_nd_front_reduces_to_the_single_best_when_one_point_dominates():
    keep = pareto_frontier_nd([(1.0, 1.0), (2.0, 2.0), (0.5, 0.5)])
    assert keep == [1]


def test_nd_front_handles_a_single_point():
    assert pareto_frontier_nd([(1.0, 2.0, 3.0)]) == [0]


def test_nd_front_is_empty_for_no_points():
    assert pareto_frontier_nd([]) == []


# ── item 5: multi-target artifact contract ───────────────────────────────────────

from cmig.cli.main import GUI_CLI_WORKFLOWS  # noqa: E402


def test_workflow_map_still_advertises_the_artifacts_the_multi_path_now_writes():
    """D9: the map promised pool_diagnostics.csv and figures; the multi path produced neither.

    The fix is to produce them, so the advertised contract must still list them.
    """
    search = next(w for w in GUI_CLI_WORKFLOWS if w["cli_command"] == "cmig search")
    assert "pool_diagnostics.csv" in search["key_outputs"]
    assert any(name.endswith(".svg") for name in search["key_outputs"])


def test_manifest_records_the_cross_feeding_attribution_method(tmp_path):
    """A-B15: the allocation method appeared in no artifact, only in source."""
    from cmig.core.interactions import CROSS_FEEDING_ALLOCATION_METHOD as method
    from cmig.io.solve_output import build_run_components, write_solve_output

    bundle = build_tidy(_crossfeed_result())
    components = build_run_components(
        _crossfeed_result(), model_checksum="m", medium_checksum="d",
        tradeoff_f=0.5, micom_version="0.39.0",
    )
    write_solve_output(bundle, components, tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["edge_attribution"]["cross_feeding_allocation_method"] == method
    assert manifest["edge_attribution"]["cross_feeding_identifiable"] is False
