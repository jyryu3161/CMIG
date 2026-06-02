"""통계 5a — 그룹 비교(effect size·검정·BH-FDR) (Roadmap Phase 3.7, §15).

Design Ref: §15 G5 / cmig-stats.design. Plan SC: SC-ST1~ST6.

scipy/statsmodels 위임. **robust 기본**(Cliff's δ·Mann-Whitney/Kruskal) — flux 분포는 비정규가
흔하므로 정규성 가정 검정(Welch/ANOVA)은 opt-in. 오용 경고(stats_warnings) — 과학적 주장 회피.

[sweep replicate 의미론] 결정적 sweep 에는 그룹 내 반복이 없으므로, **그룹=한 축 값 / 표본=다른
축 값** 으로 해석한다(예: 그룹=medium_variant, 표본=member_set들). pseudo-replication 위험은
경고로 노출(사용자가 무시 가능) — honesty-first.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def groups_from_sweep_rows(
    rows: Sequence[Mapping[str, object]], *, metric: str, group_axis: str,
) -> dict[str, list[float]]:
    """sweep long-format 행 → 그룹별 값 (실 wiring). status==ok & metric 일치만 사용.

    그룹 = axis_<group_axis> 값. group_axis 의 각 값이 한 그룹, 나머지 축이 그룹 내 표본
    (pseudo-replication 경고 대상).
    """
    col = f"axis_{group_axis}"
    groups: dict[str, list[float]] = {}
    for r in rows:
        if r.get("status") != "ok" or r.get("metric") != metric:
            continue
        v = r.get("value")
        if v is None:
            continue
        key = str(r.get(col))
        groups.setdefault(key, []).append(float(v))  # type: ignore[arg-type]
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


def stats_warnings(groups: Mapping[str, Sequence[float]], *, min_n: int = 3) -> list[str]:
    """오용 경고(honesty-first) — 소표본·pseudo-replication·비정규. 차단 아님(노출만)."""
    warns: list[str] = []
    for g in sorted(groups):
        n = len(groups[g])
        if n < min_n:
            warns.append(f"소표본 그룹 '{g}' (n={n}<{min_n}) — 검정력 부족, 해석 주의")
    warns.append(
        "결정적 sweep 그룹 비교는 pseudo-replication 위험(독립 반복 아님) — "
        "효과크기(effect size) 중심 해석 권고, 단정적 통계 주장 회피"
    )
    for g in sorted(groups):
        p = normality_pvalue(groups[g])
        if p == p and p < 0.05:                       # 비정규 → robust 권고
            warns.append(f"그룹 '{g}' 비정규(Shapiro p={p:.3g}) — robust(Cliff's δ/MWU) 권고")
    return warns
