"""Round-9 V6 defect 1 regression: mass-inconsistent solve artifacts fail closed.

The audit measured a real OSQP community state that reported ``optimal`` and
exited 0 while nearly every metabolite violated the documented edge↔profile
identity (residuals up to ~1.5e3). `cmig solve`/`solve-fixture` now run
`edge_profile_consistency` on the tidy bundle and refuse to report success for
such a state (exit 3; artifacts kept for forensics).
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from cmig.core.interactions import edge_profile_consistency
from cmig.core.tidy import EDGES_SCHEMA, PROFILE_SCHEMA, TIDY_SCHEMA_VERSION


class _Bundle:
    def __init__(self, edges, profile):
        self.edges = edges
        self.profile = profile


def _edges_table(rows):
    base = {
        "source_id": "", "target_id": "", "metabolite": "", "edge_type": "",
        "weight": 0.0, "weight_lo": None, "weight_hi": None,
        "allocation_method": "direct_flux", "identifiable": True,
        "label": "secretion", "schema_version": TIDY_SCHEMA_VERSION,
    }
    filled = [{**base, **row} for row in rows]
    names = [f.name for f in EDGES_SCHEMA]
    return pa.table(
        {name: [row.get(name) for row in filled] for name in names},
        schema=EDGES_SCHEMA,
    )


def _profile_table(rows):
    base = {
        "metabolite": "", "net_flux": 0.0, "ui_flux": 0.0, "direction": "secretion",
        "label": "secretion", "fva_lo": None, "fva_hi": None,
        "schema_version": TIDY_SCHEMA_VERSION,
    }
    filled = [{**base, **row} for row in rows]
    names = [f.name for f in PROFILE_SCHEMA]
    return pa.table(
        {name: [row.get(name) for row in filled] for name in names},
        schema=PROFILE_SCHEMA,
    )


def test_consistent_bundle_passes():
    bundle = _Bundle(
        _edges_table([
            {"source_id": "A", "target_id": "pool", "metabolite": "ac",
             "edge_type": "secretion", "weight": 2.0},
            {"source_id": "pool", "target_id": "B", "metabolite": "ac",
             "edge_type": "uptake", "weight": 0.5, "label": "uptake"},
            # allocated cross-feeding must be excluded from the identity
            {"source_id": "A", "target_id": "B", "metabolite": "ac",
             "edge_type": "cross_feeding", "weight": 99.0,
             "allocation_method": "proportional_shared_pool", "identifiable": False},
        ]),
        _profile_table([{"metabolite": "ac", "net_flux": 1.5}]),
    )
    report = edge_profile_consistency(bundle)
    assert report["consistent"] is True
    assert report["n_failing"] == 0
    assert report["max_residual"] < 1e-12


def test_mass_inconsistent_bundle_fails_with_named_worst_offender():
    bundle = _Bundle(
        _edges_table([
            {"source_id": "A", "target_id": "pool", "metabolite": "ac",
             "edge_type": "secretion", "weight": 0.1},
        ]),
        # the V6 signature: a profile magnitude wildly beyond the edge state
        _profile_table([
            {"metabolite": "ac", "net_flux": 905.0},
            {"metabolite": "ghost", "net_flux": -3.0, "direction": "uptake",
             "label": "uptake"},
        ]),
    )
    report = edge_profile_consistency(bundle)
    assert report["consistent"] is False
    assert report["n_failing"] == 2
    assert report["worst"][0]["metabolite"] == "ac"
    assert report["max_residual"] == pytest.approx(904.9)


def test_solve_command_fails_closed_on_inconsistent_bundle(monkeypatch, tmp_path, capsys):
    """CLI-level: an `optimal` outcome with broken artifacts must exit 3, not 0."""
    pytest.importorskip("micom")
    import pandas as pd

    from cmig.cli import main as cli_main
    from cmig.service import EngineService

    bad_bundle = _Bundle(
        _edges_table([
            {"source_id": "A", "target_id": "pool", "metabolite": "ac",
             "edge_type": "secretion", "weight": 0.1},
        ]),
        _profile_table([{"metabolite": "ac", "net_flux": 905.0}]),
    )

    class _Result:
        status = "optimal"
        objective = 0.0
        warnings: list = []
        diagnostic = None

    class _Outcome:
        status = "ok"
        run_hash = "f" * 64
        manifest_path = tmp_path / "manifest.json"
        result = _Result()
        bundle = bad_bundle

    monkeypatch.setattr(
        EngineService, "solve_community", lambda self, **kwargs: _Outcome()
    )
    tax = tmp_path / "tax.csv"
    model = tmp_path / "m.xml"
    model.write_text("<sbml/>")
    pd.DataFrame(
        {"id": ["A"], "file": [str(model)], "abundance": [1.0]}
    ).to_csv(tax, index=False)

    rc = cli_main.main([
        "solve", "--taxonomy", str(tax), "--assume-bigg-namespace",
        "--solver", "osqp", "--out", str(tmp_path / "out"),
    ])

    assert rc == 3
    err = capsys.readouterr().err
    assert "mass-inconsistent" in err
    assert "NOT a result" in err
    assert "qp_only_approximate" in err
