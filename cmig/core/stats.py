"""통계 5a — 그룹 비교(effect size·검정·BH-FDR) (Roadmap Phase 3.7, §15).

Design Ref: §15 G5 / cmig-stats.design. Plan SC: SC-ST1~ST6.

scipy/statsmodels 위임. **robust 기본**(Cliff's δ·Mann-Whitney/Kruskal) — flux 분포는 비정규가
흔하므로 정규성 가정 검정(Welch/ANOVA)은 opt-in. 오용 경고(stats_warnings) — 과학적 주장 회피.

[sweep replicate 의미론] 결정적 sweep 조건은 독립 반복이 아니다. replicate ID가 별도 column으로
제공되고 사용자가 독립성을 명시적으로 확인한 경우에만 p-value를 계산한다. 같은 replicate의 여러
조건은 먼저 한 관측치로 집계해 pseudo-replication을 방지한다.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def groups_from_sweep_rows(
    rows: Sequence[Mapping[str, object]], *, metric: str, group_axis: str,
    replicate_column: str | None = None,
    replicate_aggregate: str = "mean",
) -> dict[str, list[float]]:
    """sweep long-format 행 → 그룹별 값. status==ok & metric 일치만 사용.

    replicate_column이 없으면 동일 run_hash replay를 제거한 결정적 조건값(기술통계 전용)을
    반환한다. replicate_column이 있으면 group×replicate 내 여러 조건을 먼저 mean/median으로
    집계해 각 독립 replicate가 정확히 한 관측치만 기여하게 한다.
    """
    if replicate_aggregate not in {"mean", "median"}:
        raise ValueError("replicate_aggregate must be 'mean' or 'median'")
    col = f"axis_{group_axis}"
    buckets: dict[tuple[str, str], list[float]] = {}
    seen_runs: set[tuple[str, str]] = set()
    for row_index, r in enumerate(rows):
        if r.get("status") != "ok" or r.get("metric") != metric:
            continue
        if col not in r:
            raise ValueError(f"group axis column missing from sweep: {col}")
        v = r.get("value")
        if v is None:
            continue
        value = float(v)  # type: ignore[arg-type]
        if not math.isfinite(value):
            raise ValueError("sweep statistics require finite values")
        group = str(r.get(col))
        if replicate_column is None:
            run_id = str(r.get("run_hash") or r.get("condition_id") or f"row-{row_index:08d}")
            if (group, run_id) in seen_runs:
                continue
            seen_runs.add((group, run_id))
            replicate = run_id
        else:
            if replicate_column not in r or r.get(replicate_column) in {None, ""}:
                raise ValueError(
                    f"independent replicate column missing/empty: {replicate_column}"
                )
            replicate = str(r[replicate_column])
        buckets.setdefault((group, replicate), []).append(value)

    groups: dict[str, list[float]] = {}
    for (group, _replicate), values in sorted(buckets.items()):
        aggregate = (
            statistics.fmean(values)
            if replicate_aggregate == "mean"
            else float(statistics.median(values))
        )
        groups.setdefault(group, []).append(float(aggregate))
    return groups


@dataclass(frozen=True)
class GroupSummary:
    group: str
    n: int
    median: float
    iqr: float
    mean: float
    sd: float


def distribution_summary(groups: Mapping[str, Sequence[float]]) -> list[GroupSummary]:
    """그룹별 분포 요약(median/IQR/mean/sd/n). 결정적 순서(그룹명 정렬)."""
    import numpy as np

    out: list[GroupSummary] = []
    for g in sorted(groups):
        vals = [float(v) for v in groups[g]]
        n = len(vals)
        if n == 0:
            out.append(GroupSummary(g, 0, float("nan"), float("nan"), float("nan"), float("nan")))
            continue
        if n > 1:
            q1, q3 = float(np.percentile(vals, 25)), float(np.percentile(vals, 75))
        else:
            q1 = q3 = vals[0]
        out.append(GroupSummary(
            group=g, n=n, median=float(statistics.median(vals)), iqr=q3 - q1,
            mean=float(statistics.fmean(vals)),
            sd=float(statistics.stdev(vals)) if n > 1 else float("nan"),
        ))
    return out


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    """Cliff's δ ∈ [-1,1] — robust effect size(비모수). δ = (#a>b − #a<b)/(na·nb)."""
    na, nb = len(a), len(b)
    if na == 0 or nb == 0:
        return 0.0
    gt = sum(1 for x in a for y in b if x > y)
    lt = sum(1 for x in a for y in b if x < y)
    return (gt - lt) / (na * nb)


def cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    """Cohen's d — 정규·등분산 가정 effect size(pooled sd)."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    va, vb = statistics.variance(a), statistics.variance(b)
    pooled = (((na - 1) * va + (nb - 1) * vb) / (na + nb - 2)) ** 0.5
    return 0.0 if pooled == 0 else (ma - mb) / pooled


@dataclass(frozen=True)
class TestResult:
    test: str
    statistic: float
    pvalue: float
    effect_size: float
    effect_name: str


def two_group_test(
    a: Sequence[float], b: Sequence[float], *, parametric: bool = False,
) -> TestResult:
    """2그룹 검정 — 기본 Mann-Whitney U + Cliff's δ(robust); parametric → Welch t + Cohen's d."""
    from scipy import stats
    if parametric:
        res = stats.ttest_ind(a, b, equal_var=False)
        return TestResult("welch_t", float(res.statistic), float(res.pvalue),
                          cohens_d(a, b), "cohens_d")
    res = stats.mannwhitneyu(a, b, alternative="two-sided")
    return TestResult("mann_whitney_u", float(res.statistic), float(res.pvalue),
                      cliffs_delta(a, b), "cliffs_delta")


def multi_group_test(
    groups: Mapping[str, Sequence[float]], *, parametric: bool = False,
) -> TestResult:
    """다그룹 검정 — 기본 Kruskal-Wallis(robust); parametric → one-way ANOVA. effect size nan."""
    from scipy import stats
    samples = [list(groups[g]) for g in sorted(groups)]
    if parametric:
        res = stats.f_oneway(*samples)
        return TestResult("one_way_anova", float(res.statistic), float(res.pvalue),
                          float("nan"), "none")
    res = stats.kruskal(*samples)
    return TestResult("kruskal_wallis", float(res.statistic), float(res.pvalue),
                      float("nan"), "none")


def fdr_correct(pvalues: Sequence[float], *, method: str = "fdr_bh") -> list[float]:
    """BH(fdr_bh)/BY(fdr_by) FDR 보정 — statsmodels multipletests. 보정 p-value 반환."""
    from statsmodels.stats.multitest import multipletests
    if not pvalues:
        return []
    _, q, _, _ = multipletests(list(pvalues), method=method)
    return [float(x) for x in q]


def normality_pvalue(x: Sequence[float]) -> float:
    """Shapiro-Wilk 정규성 검정 p-value(작을수록 비정규). n<3 → nan."""
    from scipy import stats
    if len(x) < 3:
        return float("nan")
    return float(stats.shapiro(x).pvalue)


def stats_warnings(
    groups: Mapping[str, Sequence[float]], *,
    min_n: int = 3,
    independent_replicates: bool = False,
) -> list[str]:
    """오용 경고 — 독립 반복 부재 시 추론통계 차단 사실을 명시한다."""
    warns: list[str] = []
    for g in sorted(groups):
        n = len(groups[g])
        if n < min_n:
            warns.append(f"소표본 그룹 '{g}' (n={n}<{min_n}) — 검정력 부족, 해석 주의")
    if not independent_replicates:
        warns.append(
            "결정적 sweep 조건은 독립 반복이 아니므로 추론통계(p-value/FDR)를 차단함 — "
            "기술통계와 조건별 효과만 보고"
        )
    for g in sorted(groups):
        p = normality_pvalue(groups[g])
        if p == p and p < 0.05:                       # 비정규 → robust 권고
            warns.append(f"그룹 '{g}' 비정규(Shapiro p={p:.3g}) — robust(Cliff's δ/MWU) 권고")
    return warns
