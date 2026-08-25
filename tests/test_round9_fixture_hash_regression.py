"""Round-9 V6 defect 2 regression: a fresh fixture solve must emit its frozen hash.

`EngineService.solve_fixture` hashed every solver at the default 6 decimals while
the frozen OSQP variant is defined at 4 (`VARIANT_DECIMALS`), so a fresh
`cmig solve-fixture --solver osqp` published a run_hash that could never match the
committed golden. `cmig golden verify` did not catch it because it recomputes each
stored config from its own stored components; only a fresh CLI run exposed the
drift (REVIEW/round9/report_V6.md, defect 2).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("micom")

FROZEN = Path("fixtures/community_3_member/expected")


def _frozen_hash(solver: str) -> str:
    config = json.loads((FROZEN / solver / "config.json").read_text())
    return str(config["run_hash"])


@pytest.mark.parametrize("solver", ["gurobi", "osqp"])
def test_fresh_fixture_solve_emits_the_frozen_variant_hash(solver, tmp_path):
    from cmig.service import EngineService

    outcome = EngineService().solve_fixture(solver=solver, out_dir=tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())

    assert manifest["run_hash"] == _frozen_hash(solver), (
        "a fresh fixture solve must reproduce its published golden hash; a mismatch "
        "means components/hash decimals diverged from VARIANT_DECIMALS"
    )
    assert outcome.run_hash == manifest["run_hash"]
    # The decimals the manifest hashed at must be the frozen variant's decimals.
    frozen_decimals = json.loads((FROZEN / solver / "config.json").read_text())[
        "golden_decimals"
    ]
    assert manifest["float_decimals"] == frozen_decimals
