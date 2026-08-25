"""Phase 3.7-3.9 — 통계(5a 검정/FDR + 5b PCA/cluster + 5c UMAP). Plan SC: SC-ST1~ST9.

순수 수치 입력 — 결정적·빠름(micom 불요). scipy/statsmodels/sklearn/umap 위임 검증.
"""

from __future__ import annotations

import json
import math

import pytest

from cmig.core.stats import (
    TestResult as StatsTestResult,
)
from cmig.core.stats import (
    cliffs_delta,
    cohens_d,
    distribution_summary,
    fdr_correct,
    groups_from_sweep_rows,
    multi_group_test,
    normality_pvalue,
    prepare_volcano_data,
    stats_warnings,
    two_group_test,
)

pytest.importorskip("scipy")
pytest.importorskip("statsmodels")

_LOW = [1.0, 1.1, 0.9, 1.05, 0.95]
_HIGH = [3.0, 3.2, 2.8, 3.1, 2.9]


def test_distribution_summary():
    """SC-ST1: median/IQR/mean/sd/n."""
    s = distribution_summary({"low": _LOW, "high": _HIGH})
    by = {g.group: g for g in s}
    assert by["low"].n == 5 and abs(by["low"].median - 1.0) < 1e-9
    assert by["high"].mean > by["low"].mean
    singleton = distribution_summary({"one": [1.0]})[0]
    assert math.isnan(singleton.sd)


def test_effect_sizes():
    """SC-ST2: Cliff's δ(완전 분리=1) + Cohen's d(큰 효과)."""
    assert cliffs_delta(_HIGH, _LOW) == 1.0       # 모든 high>low → δ=1
    assert cliffs_delta(_LOW, _HIGH) == -1.0
    assert cohens_d(_HIGH, _LOW) > 2.0            # 매우 큰 효과


def test_two_group_test_robust_and_parametric():
    """SC-ST3: MWU(robust 기본)+Cliff's δ / Welch t(parametric)+Cohen's d."""
    r = two_group_test(_LOW, _HIGH)
    assert r.test == "mann_whitney_u" and r.pvalue < 0.05 and r.effect_name == "cliffs_delta"
    rp = two_group_test(_LOW, _HIGH, parametric=True)
    assert rp.test == "welch_t" and rp.pvalue < 0.05 and rp.effect_name == "cohens_d"


def test_multi_group_test():
    """SC-ST4: Kruskal-Wallis(기본)/ANOVA(parametric) — 3그룹 차이 검출."""
    groups = {"a": _LOW, "b": _HIGH, "c": [5.0, 5.1, 4.9, 5.2, 4.8]}
    assert multi_group_test(groups).pvalue < 0.05
    assert multi_group_test(groups, parametric=True).test == "one_way_anova"


def test_fdr_correction():
    """SC-ST5: BH-FDR — 보정 p ≥ 원 p, 단조."""
    raw = [0.001, 0.01, 0.04, 0.5]
    q = fdr_correct(raw, method="fdr_bh")
    assert len(q) == 4
    assert all(qi >= ri - 1e-12 for qi, ri in zip(q, raw, strict=True))
    assert fdr_correct([]) == []


def test_stats_warnings_honesty():
    """SC-ST6: 독립 반복 없는 deterministic sweep는 추론통계를 차단한다."""
    warns = stats_warnings({"tiny": [1.0, 2.0]}, min_n=3)
    assert any("소표본" in w for w in warns)
    assert any("p-value" in w and "차단" in w for w in warns)


def test_groups_from_sweep_rows_wiring():
    """SC-ST6: sweep long-format → 그룹(실 wiring). status==ok·metric 필터·axis 그룹."""
    rows = [
        {"status": "ok", "metric": "growth", "axis_solver": "gurobi", "value": 1.0},
        {"status": "ok", "metric": "growth", "axis_solver": "gurobi", "value": 1.2},
        {"status": "ok", "metric": "growth", "axis_solver": "osqp", "value": 0.8},
        {"status": "failed", "metric": "growth", "axis_solver": "osqp", "value": None},
        {"status": "ok", "metric": "other", "axis_solver": "gurobi", "value": 9.0},
    ]
    g = groups_from_sweep_rows(rows, metric="growth", group_axis="solver")
    assert set(g) == {"gurobi", "osqp"}
    assert g["gurobi"] == [1.0, 1.2] and g["osqp"] == [0.8]


def test_groups_from_sweep_rows_aggregates_each_replicate_once():
    rows = [
        {
            "status": "ok", "metric": "growth", "axis_solver": "gurobi",
            "replicate_id": "r1", "value": 1.0,
        },
        {
            "status": "ok", "metric": "growth", "axis_solver": "gurobi",
            "replicate_id": "r1", "value": 3.0,
        },
        {
            "status": "ok", "metric": "growth", "axis_solver": "gurobi",
            "replicate_id": "r2", "value": 4.0,
        },
    ]
    groups = groups_from_sweep_rows(
        rows, metric="growth", group_axis="solver", replicate_column="replicate_id"
    )
    assert groups == {"gurobi": [2.0, 4.0]}


def test_stats_sweep_cli_reads_sweep_store(tmp_path):
    from cmig.cli.main import main
    from cmig.core.sweep import SweepRow, write_sweep_parquet

    sweep = tmp_path / "sweep.parquet"
    write_sweep_parquet(
        [
            SweepRow("c0", {"solver": "gurobi"}, "growth", 1.0, "h0", "ok", None, False),
            SweepRow("c1", {"solver": "gurobi"}, "growth", 1.2, "h1", "ok", None, False),
            SweepRow("c2", {"solver": "osqp"}, "growth", 0.8, "h2", "ok", None, False),
            SweepRow("c3", {"solver": "osqp"}, "growth", 0.9, "h3", "ok", None, False),
        ],
        sweep,
    )
    out = tmp_path / "stats"
    rc = main(["stats-sweep", "--sweep", str(sweep), "--out", str(out)])
    assert rc == 0
    payload = json.loads((out / "stats_sweep_summary.json").read_text())
    assert payload["group_axis"] == "solver"
    assert payload["groups"] == {"gurobi": 2, "osqp": 2}
    assert payload["test"] is None
    assert payload["inference"]["status"] == "not_run_no_independent_replicates"


def test_stats_sweep_cli_runs_inference_only_with_confirmed_replicates(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from cmig.cli.main import main

    rows = []
    for group, base in (("gurobi", 1.0), ("osqp", 3.0)):
        for replicate, delta in (("r1", 0.0), ("r2", 0.1), ("r3", -0.1)):
            rows.append({
                "status": "ok", "metric": "growth", "axis_solver": group,
                "replicate_id": replicate, "value": base + delta,
            })
    sweep = tmp_path / "replicates.parquet"
    pq.write_table(pa.Table.from_pylist(rows), sweep)
    out = tmp_path / "stats"
    rc = main([
        "stats-sweep", "--sweep", str(sweep), "--replicate-column", "replicate_id",
        "--confirm-independent-replicates", "--out", str(out),
    ])
    assert rc == 0
    payload = json.loads((out / "stats_sweep_summary.json").read_text())
    assert payload["inference"]["status"] == "completed"
    assert payload["test"]["test"] == "mann_whitney_u"


def test_normality_pvalue():
    """비정규 데이터 → 낮은 Shapiro p (robust 권고 트리거)."""
    skewed = [0.0, 0.0, 0.0, 0.0, 0.1, 10.0]
    p = normality_pvalue(skewed)
    assert p == p and 0.0 <= p <= 1.0
    assert normality_pvalue([1.0, 2.0]) != normality_pvalue([1.0, 2.0])  # n<3 → nan


def test_pca_and_kmeans():
    """SC-ST7 (5b): PCA(2D)+explained_variance, KMeans 라벨."""
    pytest.importorskip("sklearn")
    import numpy as np

    from cmig.core.stats_embed import kmeans_cluster, pca_embed
    rng = np.random.RandomState(0)
    mat = np.vstack([rng.randn(10, 5), rng.randn(10, 5) + 8])
    emb = pca_embed(mat, n_components=2)
    assert emb.coords.shape == (20, 2) and len(emb.explained_variance) == 2
    labels = kmeans_cluster(mat, k=2)
    assert len(labels) == 20 and len(set(labels)) == 2


def test_embed_rejects_invalid_small_shapes():
    pytest.importorskip("sklearn")
    import numpy as np

    from cmig.core.stats_embed import kmeans_cluster, pca_embed
    with pytest.raises(ValueError, match="n_components"):
        pca_embed(np.ones((1, 5)), n_components=2)
    with pytest.raises(ValueError, match="KMeans k"):
        kmeans_cluster(np.ones((2, 3)), k=3)


def test_umap_embed():
    """SC-ST8 (5c): UMAP 임베딩 shape."""
    pytest.importorskip("umap")
    import numpy as np

    from cmig.core.stats_embed import umap_embed
    rng = np.random.RandomState(0)
    mat = np.vstack([rng.randn(15, 6), rng.randn(15, 6) + 6])
    emb = umap_embed(mat, n_components=2)
    assert emb.coords.shape == (30, 2)


def test_umap_rejects_too_few_samples():
    pytest.importorskip("umap")
    import numpy as np

    from cmig.core.stats_embed import umap_embed
    with pytest.raises(ValueError, match="at least 3 samples"):
        umap_embed(np.ones((2, 4)), n_components=2)


def test_seeded_low_level_embedding_helpers_record_the_seed():
    pytest.importorskip("sklearn")
    import numpy as np

    from cmig.core.stats_embed import kmeans_cluster, pca_embed

    matrix = np.array([
        [0.0, 0.2, 0.4],
        [0.1, 0.4, 0.2],
        [4.0, 4.2, 4.1],
        [4.3, 4.0, 4.2],
    ])
    embedding = pca_embed(matrix, n_components=2, seed=23)
    assert embedding.seed == 23
    assert kmeans_cluster(matrix, k=2, seed=23) == kmeans_cluster(matrix, k=2, seed=23)


def test_umap_rejects_neighbor_count_instead_of_silently_clamping():
    pytest.importorskip("umap")
    import numpy as np

    from cmig.core.stats_embed import umap_embed

    with pytest.raises(ValueError, match="less than n_samples"):
        umap_embed(np.ones((5, 3)), n_components=2, n_neighbors=5, seed=4)


def test_prepare_volcano_data_adjusts_and_sorts_per_feature_results():
    rows = prepare_volcano_data({
        "z_flux": StatsTestResult("mann_whitney_u", 3.0, 0.04, -0.5, "cliffs_delta"),
        "a_flux": StatsTestResult("mann_whitney_u", 8.0, 0.01, 0.8, "cliffs_delta"),
    })
    assert [row["feature"] for row in rows] == ["a_flux", "z_flux"]
    assert [row["adjusted_pvalue"] for row in rows] == pytest.approx([0.02, 0.04])
    assert rows[0]["effect_size"] == 0.8
    assert rows[0]["fdr_method"] == "fdr_bh"


def test_prepare_volcano_data_rejects_unplottable_values():
    with pytest.raises(ValueError, match="effect_size must be finite"):
        prepare_volcano_data([
            {"feature": "growth", "effect_size": float("nan"), "pvalue": 0.2}
        ])
