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
from dataclasses import dataclass, field

STATS_METHODS = (
    "robust",
    "parametric",
    "distribution_summary",
    "mann_whitney_u",
    "welch_t",
    "kruskal_wallis",
    "one_way_anova",
    "cliffs_delta",
    "cohens_d",
)
FDR_METHODS = ("fdr_bh", "fdr_by")
DIMRED_METHODS = ("none", "pca", "umap")
CLUSTERING_METHODS = ("none", "kmeans")
_MAX_RANDOM_SEED = 2**32 - 1


def _positive_int(value: object, *, field_name: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field_name} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True)
class DimredConfig:
    """Configuration for an optional dimensionality-reduction step."""

    method: str = "none"
    n_components: int = 2
    n_neighbors: int = 15

    def __post_init__(self) -> None:
        if self.method not in DIMRED_METHODS:
            raise ValueError(
                f"dimred.method must be one of {list(DIMRED_METHODS)}; got {self.method!r}"
            )
        _positive_int(self.n_components, field_name="dimred.n_components")
        _positive_int(self.n_neighbors, field_name="dimred.n_neighbors", minimum=2)

    def as_provenance(self) -> dict[str, object]:
        if self.method == "none":
            return {"method": "none"}
        record: dict[str, object] = {
            "method": self.method,
            "n_components": self.n_components,
        }
        if self.method == "umap":
            record["n_neighbors"] = self.n_neighbors
        return record


@dataclass(frozen=True)
class ClusteringConfig:
    """Configuration for an optional clustering step."""

    method: str = "none"
    k: int = 2

    def __post_init__(self) -> None:
        if self.method not in CLUSTERING_METHODS:
            raise ValueError(
                "clustering.method must be one of "
                f"{list(CLUSTERING_METHODS)}; got {self.method!r}"
            )
        _positive_int(self.k, field_name="clustering.k")

    def as_provenance(self) -> dict[str, object]:
        if self.method == "none":
            return {"method": "none"}
        return {"method": "kmeans", "k": self.k}


DimredInput = DimredConfig | Mapping[str, object] | str
ClusteringInput = ClusteringConfig | Mapping[str, object] | str


def _coerce_dimred(value: DimredInput) -> DimredConfig:
    if isinstance(value, DimredConfig):
        return value
    if isinstance(value, str):
        return DimredConfig(method=value)
    allowed = {"method", "n_components", "n_neighbors"}
    unexpected = sorted(set(value) - allowed)
    if unexpected:
        raise ValueError(f"dimred contains unsupported fields: {unexpected}")
    try:
        return DimredConfig(**dict(value))  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError(f"invalid dimred configuration: {error}") from error


def _coerce_clustering(value: ClusteringInput) -> ClusteringConfig:
    if isinstance(value, ClusteringConfig):
        return value
    if isinstance(value, str):
        return ClusteringConfig(method=value)
    allowed = {"method", "k"}
    unexpected = sorted(set(value) - allowed)
    if unexpected:
        raise ValueError(f"clustering contains unsupported fields: {unexpected}")
    try:
        return ClusteringConfig(**dict(value))  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError(f"invalid clustering configuration: {error}") from error


@dataclass(frozen=True)
class StatsConfig:
    """Validated, JSON-ready configuration for a statistics workflow.

    Group and method order is intentionally preserved because it can determine an
    effect-size direction. Mutable input sequences/mappings are normalized during
    construction so a frozen instance cannot drift after its provenance is recorded.
    """

    groups: tuple[str, ...]
    methods: tuple[str, ...] = ("robust",)
    fdr_method: str = "fdr_bh"
    seed: int = 0
    dimred: DimredInput = field(default_factory=DimredConfig)
    clustering: ClusteringInput = field(default_factory=ClusteringConfig)

    def __post_init__(self) -> None:
        if isinstance(self.groups, str):
            raise ValueError("groups must be a sequence of group names, not a string")
        groups = tuple(self.groups)
        if not groups:
            raise ValueError("groups must contain at least one group name")
        if any(not isinstance(group, str) or not group.strip() for group in groups):
            raise ValueError("groups must contain only non-empty strings")
        if any(group != group.strip() for group in groups):
            raise ValueError("group names must not contain leading or trailing whitespace")
        if len(groups) != len(set(groups)):
            raise ValueError("groups must not contain duplicates")

        if isinstance(self.methods, str):
            raise ValueError("methods must be a sequence, not a string")
        methods = tuple(self.methods)
        if not methods:
            raise ValueError("methods must contain at least one method")
        if any(not isinstance(method, str) or not method for method in methods):
            raise ValueError("methods must contain only non-empty strings")
        unsupported_methods = sorted(set(methods) - set(STATS_METHODS))
        if unsupported_methods:
            raise ValueError(
                f"methods contains unsupported values {unsupported_methods}; "
                f"allowed values are {list(STATS_METHODS)}"
            )
        if len(methods) != len(set(methods)):
            raise ValueError("methods must not contain duplicates")
        if self.fdr_method not in FDR_METHODS:
            raise ValueError(
                f"fdr_method must be one of {list(FDR_METHODS)}; got {self.fdr_method!r}"
            )
        if (
            isinstance(self.seed, bool)
            or not isinstance(self.seed, int)
            or not 0 <= self.seed <= _MAX_RANDOM_SEED
        ):
            raise ValueError(f"seed must be an integer between 0 and {_MAX_RANDOM_SEED}")

        object.__setattr__(self, "groups", groups)
        object.__setattr__(self, "methods", methods)
        object.__setattr__(self, "dimred", _coerce_dimred(self.dimred))
        object.__setattr__(self, "clustering", _coerce_clustering(self.clustering))

    def as_provenance(self) -> dict[str, object]:
        """Return the canonical JSON-ready record proposed for workflow hashing."""
        dimred = self.dimred
        clustering = self.clustering
        assert isinstance(dimred, DimredConfig)
        assert isinstance(clustering, ClusteringConfig)
        return {
            "groups": list(self.groups),
            "methods": list(self.methods),
            "fdr_method": self.fdr_method,
            "seed": self.seed,
            "dimred": dimred.as_provenance(),
            "clustering": clustering.as_provenance(),
        }


# Readable aliases for callers that prefer the expanded name.
DimensionalityReductionConfig = DimredConfig
DimRedConfig = DimredConfig
ClusterConfig = ClusteringConfig


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
    if method not in FDR_METHODS:
        raise ValueError(f"FDR method must be one of {list(FDR_METHODS)}; got {method!r}")
    checked: list[float] = []
    for pvalue in pvalues:
        value = float(pvalue)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"p-values must be finite and between 0 and 1; got {pvalue!r}")
        checked.append(value)
    if not checked:
        return []
    _, q, _, _ = multipletests(checked, method=method)
    return [float(x) for x in q]


def prepare_volcano_data(
    results: Mapping[str, TestResult | Mapping[str, object]]
    | Sequence[Mapping[str, object]],
    *,
    fdr_method: str = "fdr_bh",
    feature_column: str = "feature",
) -> list[dict[str, object]]:
    """Build a deterministic effect-size versus adjusted-p-value table.

    ``results`` may be a mapping from feature name to :class:`TestResult` (or a
    mapping with equivalent fields), or tidy input rows containing ``feature``,
    ``effect_size``, and ``pvalue``. The returned rows are sorted by feature so
    mapping insertion order cannot affect serialized output.
    """
    prepared: list[dict[str, object]] = []
    if isinstance(results, Mapping):
        items: Sequence[tuple[object, object]] = list(results.items())
        for feature, result in items:
            if isinstance(result, TestResult):
                prepared.append({
                    feature_column: feature,
                    "test": result.test,
                    "effect_size": result.effect_size,
                    "effect_name": result.effect_name,
                    "pvalue": result.pvalue,
                })
            elif isinstance(result, Mapping):
                prepared.append({feature_column: feature, **dict(result)})
            else:
                raise ValueError(
                    "volcano results mapping values must be TestResult or mappings"
                )
    else:
        prepared = [dict(row) for row in results]

    seen_features: set[str] = set()
    validated: list[dict[str, object]] = []
    for row in prepared:
        if feature_column not in row or not str(row[feature_column]).strip():
            raise ValueError(f"volcano row missing non-empty {feature_column!r}")
        feature = str(row[feature_column])
        if feature in seen_features:
            raise ValueError(f"duplicate volcano feature: {feature!r}")
        seen_features.add(feature)
        try:
            effect_size = float(row["effect_size"])  # type: ignore[arg-type]
            pvalue = float(row["pvalue"])  # type: ignore[arg-type]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"volcano feature {feature!r} requires numeric effect_size and pvalue"
            ) from error
        if not math.isfinite(effect_size):
            raise ValueError(f"volcano effect_size must be finite for feature {feature!r}")
        if not math.isfinite(pvalue) or not 0.0 <= pvalue <= 1.0:
            raise ValueError(
                f"volcano pvalue must be finite and between 0 and 1 for feature {feature!r}"
            )
        clean = dict(row)
        clean[feature_column] = feature
        clean["effect_size"] = effect_size
        clean["pvalue"] = pvalue
        validated.append(clean)

    validated.sort(key=lambda row: str(row[feature_column]))
    adjusted = fdr_correct(
        [float(row["pvalue"]) for row in validated],  # type: ignore[arg-type]
        method=fdr_method,
    )
    output: list[dict[str, object]] = []
    for row, qvalue in zip(validated, adjusted, strict=True):
        out = dict(row)
        out["adjusted_pvalue"] = qvalue
        out["neg_log10_adjusted_pvalue"] = (
            float("inf") if qvalue == 0.0 else -math.log10(qvalue)
        )
        out["fdr_method"] = fdr_method
        output.append(out)
    return output


# Short noun-form alias for figure-preparation callers.
volcano_data = prepare_volcano_data


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
