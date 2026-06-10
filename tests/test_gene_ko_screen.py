"""gene-ko-search 고도화(Feature #1) 단위·통합 테스트.

순수 단위(solver 비의존): target 선택·병렬 매핑·NaN-safe 정렬·figure 실패 안전성.
통합(micom gated): reaction-level KO, --jobs 병렬 결과 동등성, summary 신규 필드.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from cmig.cli.main import (
    _ko_sort_key,
    _map_ko_evaluations,
    _select_ko_targets,
)


class _FakeGene:
    def __init__(self, gid: str) -> None:
        self.id = gid


class _FakeReaction:
    def __init__(self, rid: str, objective_coefficient: float = 0.0) -> None:
        self.id = rid
        self.objective_coefficient = objective_coefficient


class _FakeModel:
    def __init__(self, genes: list[str], reactions: list[Any]) -> None:
        self.genes = [_FakeGene(g) for g in genes]
        self.reactions = [
            _FakeReaction(*r) if isinstance(r, tuple) else _FakeReaction(r)
            for r in reactions
        ]


# ── _select_ko_targets ────────────────────────────────────────────────────────

def test_select_ko_targets_explicit_used_verbatim():
    model = _FakeModel(["b3", "b1", "b2"], [])
    selected, total, method = _select_ko_targets(
        model, ko_level="gene", explicit=["b2", "b1"], max_n=20, selection="id", seed=0
    )
    assert selected == ["b2", "b1"]
    assert total == 2
    assert method == "explicit"


def test_select_ko_targets_id_truncates_and_reports_total():
    model = _FakeModel(["b3", "b1", "b2", "b4"], [])
    selected, total, method = _select_ko_targets(
        model, ko_level="gene", explicit=None, max_n=2, selection="id", seed=0
    )
    # sorted by id, first 2; full count disclosed so the caller can warn about truncation.
    assert selected == ["b1", "b2"]
    assert total == 4
    assert method == "id"


def test_select_ko_targets_max_zero_means_all():
    model = _FakeModel(["b1", "b2", "b3"], [])
    selected, total, _ = _select_ko_targets(
        model, ko_level="gene", explicit=None, max_n=0, selection="id", seed=0
    )
    assert selected == ["b1", "b2", "b3"]
    assert total == 3


def test_select_ko_targets_random_is_deterministic_per_seed():
    model = _FakeModel([f"b{i:02d}" for i in range(12)], [])
    first = _select_ko_targets(
        model, ko_level="gene", explicit=None, max_n=4, selection="random", seed=7
    )
    second = _select_ko_targets(
        model, ko_level="gene", explicit=None, max_n=4, selection="random", seed=7
    )
    assert first == second
    selected, total, method = first
    assert total == 12
    assert method == "random(seed=7)"
    assert len(selected) == 4
    assert selected == sorted(selected)


def test_select_ko_targets_reaction_excludes_boundary_and_objective():
    model = _FakeModel(
        [],
        ["EX_glc__D_e", "DM_atp_c", "SK_h_c", "PGI", "ENO", "EX_ac_e", ("BIOMASS", 1.0)],
    )
    selected, total, method = _select_ko_targets(
        model, ko_level="reaction", explicit=None, max_n=0, selection="id", seed=0
    )
    # EX_/DM_/SK_ boundary pseudo-reactions and the objective/biomass reaction are skipped.
    assert selected == ["ENO", "PGI"]
    assert total == 2
    assert method == "id"


# ── _map_ko_evaluations ───────────────────────────────────────────────────────

def test_map_ko_evaluations_preserves_order_for_any_jobs():
    items = list(range(9))

    def evaluate(i: int) -> dict[str, object]:
        return {"member": "m", "gene": str(i), "evaluation_status": "ok", "score_delta": float(i)}

    serial = _map_ko_evaluations(items, evaluate, jobs=1)
    parallel = _map_ko_evaluations(items, evaluate, jobs=4)
    assert serial == parallel
    assert [row["gene"] for row in serial] == [str(i) for i in range(9)]


# ── _ko_sort_key (BUG-2: NaN-safe deterministic ranking) ──────────────────────

def test_ko_sort_key_orders_ok_finite_then_nan_then_failed():
    rows = [
        {"member": "m", "gene": "a", "evaluation_status": "ok", "score_delta": 1.0},
        {"member": "m", "gene": "b", "evaluation_status": "ok", "score_delta": float("nan")},
        {"member": "m", "gene": "c", "evaluation_status": "failed", "score_delta": float("nan")},
        {"member": "m", "gene": "d", "evaluation_status": "ok", "score_delta": 2.0},
    ]
    rows.sort(key=_ko_sort_key)
    assert [row["gene"] for row in rows] == ["d", "a", "b", "c"]


def test_ko_sort_key_is_stable_when_all_deltas_nan():
    # baseline-infeasible: every score_delta is NaN -> order must still be deterministic.
    rows = [
        {"member": "m", "gene": g, "evaluation_status": "ok", "score_delta": float("nan")}
        for g in ("g3", "g1", "g2")
    ]
    rows.sort(key=_ko_sort_key)
    assert [row["gene"] for row in rows] == ["g1", "g2", "g3"]


# ── direction-aware figure coloring (C1: must track objective, not raw flux sign) ────────

def test_ko_effect_category_is_direction_aware():
    from cmig.cli.main import _ko_effect_category

    # Color must follow the OBJECTIVE (score_delta, already normalized so larger=better for every
    # --direction), NOT the raw target_flux_delta sign — else min_secretion/max_uptake invert.
    # max_secretion: a KO raising secretion improves the goal (delta>0, score_delta>0).
    assert _ko_effect_category("ok", 2.0, 1.5) == "improve"
    # min_secretion / max_uptake: best KO LOWERS the flux (delta<0) yet score_delta>0 -> improve.
    assert _ko_effect_category("ok", -2.0, 1.5) == "improve"
    # a KO that worsens the objective, regardless of the flux-delta sign.
    assert _ko_effect_category("ok", 2.0, -1.5) == "worsen"
    assert _ko_effect_category("ok", -0.4, -0.4) == "worsen"
    # a KO that makes the consortium infeasible (score_delta -inf) worsens the objective.
    assert _ko_effect_category("ok", -1.0, float("-inf")) == "worsen"
    # no measurable / unknown effect, and failure handling.
    assert _ko_effect_category("ok", 0.0, 0.0) == "neutral"
    assert _ko_effect_category("ok", 1.0, float("nan")) == "neutral"
    assert _ko_effect_category("failed", 0.0, 0.0) == "failed"
    assert _ko_effect_category("ok", float("nan"), 1.0) == "failed"


# ── figure (US-005): failure/NaN safe ─────────────────────────────────────────

def test_write_gene_ko_figures_handles_failed_and_nan_rows(tmp_path):
    pytest.importorskip("matplotlib")
    from cmig.cli.main import _write_gene_ko_figures

    class _Baseline:
        target_flux = 1.5

    rows = [
        {"member": "p", "gene": "g1", "evaluation_status": "ok", "target_flux_delta": -0.4},
        {"member": "p", "gene": "g2", "evaluation_status": "failed",
         "target_flux_delta": float("nan")},
        {"member": "q", "gene": "g3", "evaluation_status": "ok", "target_flux_delta": 0.2},
    ]
    _write_gene_ko_figures(
        rows, tmp_path, target="but", ko_level="gene", direction="max_secretion",
        baseline=_Baseline(), n_evaluated=3, n_total=10, selection="id",
    )
    assert (tmp_path / "gene_ko_plot.svg").exists()
    assert (tmp_path / "gene_ko_plot.tiff").exists()


def test_write_gene_ko_figures_empty_rows_still_render(tmp_path):
    pytest.importorskip("matplotlib")
    from cmig.cli.main import _write_gene_ko_figures

    class _Baseline:
        target_flux = float("nan")

    _write_gene_ko_figures(
        [], tmp_path, target="ac", ko_level="reaction", direction="max_uptake",
        baseline=_Baseline(), n_evaluated=0, n_total=0, selection="random(seed=1)",
    )
    assert (tmp_path / "gene_ko_plot.svg").exists()
    assert (tmp_path / "gene_ko_plot.tiff").exists()


# ── integration (micom gated) ─────────────────────────────────────────────────

def _write_pair(tmp_path):
    import cobra
    import pandas as pd

    from cmig.synthetic_pair import build_pair_models

    producer, consumer = build_pair_models()
    producer.reactions.get_by_id("GLC2AC").gene_reaction_rule = "g_prod"
    consumer.reactions.get_by_id("AC2BUT").gene_reaction_rule = "g_cons"
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    producer_path = model_dir / "producer.xml"
    consumer_path = model_dir / "consumer.xml"
    cobra.io.write_sbml_model(producer, str(producer_path))
    cobra.io.write_sbml_model(consumer, str(consumer_path))
    taxonomy = pd.DataFrame({
        "id": ["producer", "consumer"],
        "file": [str(producer_path), str(consumer_path)],
        "abundance": [0.5, 0.5],
    })
    taxonomy_path = tmp_path / "taxonomy.csv"
    taxonomy.to_csv(taxonomy_path, index=False)
    return taxonomy_path


def test_gene_ko_reaction_level_cli(tmp_path):
    pytest.importorskip("micom")
    from cmig.cli.main import main

    taxonomy_path = _write_pair(tmp_path)
    out = tmp_path / "ko_reaction"
    rc = main([
        "gene-ko-search",
        "--taxonomy", str(taxonomy_path),
        "--members", "producer,consumer",
        "--member", "producer",
        "--target", "but",
        "--ko-level", "reaction",
        "--reactions", "GLC2AC",
        "--out", str(out),
    ])
    assert rc == 0
    payload = json.loads((out / "gene_ko_summary.json").read_text())
    assert payload["ko_level"] == "reaction"
    assert payload["gene_selection"] == "id"
    assert isinstance(payload["warnings"], list)
    assert payload["n_genes_total"] >= payload["n_genes_evaluated"]
    assert payload["top_ranked"][0]["gene"] == "GLC2AC"
    assert payload["top_ranked"][0]["target_flux_delta"] < 0.0


def test_gene_ko_jobs_parallel_matches_serial(tmp_path):
    pytest.importorskip("micom")
    from cmig.cli.main import main

    taxonomy_path = _write_pair(tmp_path)

    def _run(out_name: str, jobs: int) -> list[tuple[str, str]]:
        out = tmp_path / out_name
        rc = main([
            "gene-ko-search",
            "--taxonomy", str(taxonomy_path),
            "--members", "producer,consumer",
            "--target", "but",
            "--max-genes", "0",
            "--jobs", str(jobs),
            "--out", str(out),
        ])
        assert rc == 0
        payload = json.loads((out / "gene_ko_summary.json").read_text())
        return [(row["member"], row["gene"]) for row in payload["top_ranked"]]

    assert _run("serial", 1) == _run("parallel", 2)


def test_gene_ko_random_selection_warns(tmp_path):
    pytest.importorskip("micom")
    from cmig.cli.main import main

    taxonomy_path = _write_pair(tmp_path)
    out = tmp_path / "ko_random"
    rc = main([
        "gene-ko-search",
        "--taxonomy", str(taxonomy_path),
        "--members", "producer,consumer",
        "--member", "producer",
        "--target", "but",
        "--gene-selection", "random",
        "--seed", "3",
        "--out", str(out),
    ])
    assert rc == 0
    payload = json.loads((out / "gene_ko_summary.json").read_text())
    assert payload["gene_selection"] == "random"
    assert payload["seed"] == 3
    # random selection is disclosed as a warning (honesty: never a silent arbitrary subset).
    assert any("sampled" in w for w in payload["warnings"])
