"""Regression pins for round-9 measured cross-run artifact comparability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("cobra")
pytest.importorskip("micom")

from cmig.cli.main import main  # noqa: E402
from cmig.core.engine import SolveResult  # noqa: E402
from cmig.core.interactions import build_tidy  # noqa: E402
from cmig.core.workflow_manifest import DETERMINISTIC_ARTIFACT_KINDS  # noqa: E402
from cmig.synthetic_pair import build_pair_taxonomy  # noqa: E402

PROMOTED_KINDS = ("pair", "delta", "single", "minimal_medium")


def _solve_result(
    members: list[str], external: dict[str, float], growth: float
) -> SolveResult:
    abundance = 1.0 / len(members)
    return SolveResult(
        objective=growth,
        member_growth={member: growth for member in members},
        abundances={member: abundance for member in members},
        external_exchange=external,
        member_exchange={member: {} for member in members},
        status="optimal",
        flux_report_status="full",
        growth_solver="gurobi",
        flux_solver="gurobi",
        members=members,
    )


@pytest.fixture(scope="module")
def repeated_runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[dict[str, Any]]]:
    root = tmp_path_factory.mktemp("deterministic_artifacts")
    taxonomy = build_pair_taxonomy(root / "models")
    taxonomy_path = root / "pair.csv"
    taxonomy.to_csv(taxonomy_path, index=False)
    medium = root / "glucose.csv"
    medium.write_text(
        "exchange_id,uptake_limit\nEX_glc__D_e,10\nEX_ac_e,0\n"
    )
    producer = Path(
        str(taxonomy.loc[taxonomy["id"] == "producer", "file"].iloc[0])
    )
    baseline, variant = root / "baseline", root / "variant"
    build_tidy(_solve_result(["A"], {"ac": 2.0}, 0.4)).write(baseline)
    build_tidy(
        _solve_result(["A", "B"], {"ac": 5.0, "but": 1.0}, 0.6)
    ).write(variant)

    commands = {
        "pair": [
            "pair", "--taxonomy", str(taxonomy_path), "--medium", str(medium),
            "--exact-medium", "--assume-bigg-namespace",
        ],
        "delta": [
            "delta", "--baseline", str(baseline), "--variant", str(variant),
        ],
        "single": [
            "single", "--model", str(producer), "--method", "both", "--fva",
            "--reaction-ko", "GLC2AC", "--medium", str(medium), "--exact-medium",
            "--assume-bigg-namespace",
        ],
        "minimal_medium": [
            "minimal-medium", "--model", str(producer), "--min-growth", "1",
            "--medium", str(medium), "--exact-medium", "--assume-bigg-namespace",
        ],
    }
    measured: dict[str, list[dict[str, Any]]] = {}
    for kind, argv in commands.items():
        records: list[dict[str, Any]] = []
        for index in (1, 2):
            out = root / f"{kind}_{index}"
            assert main([*argv, "--out", str(out)]) == 0
            manifest = json.loads((out / "manifest.json").read_text())
            records.append({
                "run_hash": manifest["run_hash"],
                "result_digest": manifest["result_digest"]["digest"],
                "artifact_digests": manifest["result_digest"]["artifacts"],
                "cross_run_comparable": manifest["result_digest"][
                    "cross_run_comparable"
                ],
            })
        measured[kind] = records
    return measured


@pytest.mark.parametrize("kind", PROMOTED_KINDS)
def test_promoted_kind_remains_byte_identical_across_repeated_runs(
    kind: str, repeated_runs: dict[str, list[dict[str, Any]]]
) -> None:
    first, second = repeated_runs[kind]

    assert kind in DETERMINISTIC_ARTIFACT_KINDS
    assert first["run_hash"] == second["run_hash"]
    assert first["artifact_digests"] == second["artifact_digests"]
    assert first["result_digest"] == second["result_digest"]
    assert first["cross_run_comparable"] is True
    assert second["cross_run_comparable"] is True
