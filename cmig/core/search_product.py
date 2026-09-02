"""Product-facing model-pool search.

This layer connects the target-max search core to user-provided model pools.
It supports exhaustive small-pool ranking, deterministic random sampling, and
GA approximation for larger candidate spaces.
"""

from __future__ import annotations

import itertools
import math
import random
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from typing import Any, Literal, cast

from cmig.core.search import Direction, TargetSpec, score_target_result, target_max_solve
from cmig.core.search_ga import GAConfig

SearchStrategy = Literal["auto", "exhaustive", "random", "ga"]


@dataclass(frozen=True)
class SearchConfig:
    target: str
    direction: Direction = Direction.MAX_SECRETION
    min_size: int = 2
    max_size: int = 2
    strategy: SearchStrategy = "auto"
    n_samples: int = 100
    seed: int = 0
    top_k: int = 10
    growth_fraction: float = 0.5
    solver: str = "gurobi"
    robustness_fva: bool = False
    exhaustive_max: int = 100
    ga_config: GAConfig | None = None


@dataclass(frozen=True)
class PoolRank:
    rank: int
    members: tuple[str, ...]
    score: float
    target_flux: float
    community_growth: float
    status: str
    diagnostic: str | None = None
    robustness_fva_lo: float | None = None
    robustness_fva_hi: float | None = None
    robustness_status: str | None = None

    @property
    def robustness_width(self) -> float | None:
        if self.robustness_fva_lo is None or self.robustness_fva_hi is None:
            return None
        return self.robustness_fva_hi - self.robustness_fva_lo


@dataclass(frozen=True)
class PoolSearchResult:
    target: str
    target_exchange: str
    direction: str
    strategy: str
    n_pool_members: int
    n_candidates_total: int
    n_candidates_evaluated: int
    ranks: list[PoolRank]
    warnings: list[str]
    # P0-B: 평가 불가 후보는 rank 를 갖지 않고 여기에만 들어간다. --top-k 는 `ranks` 만 자르므로
    # 이 목록은 절단과 무관하게 항상 완전하다.
    unevaluated: list[PoolRank] = field(default_factory=list)
    ga_metadata: dict[str, Any] | None = None

    @property
    def n_candidates_ranked(self) -> int:
        return len(self.ranks)

    @property
    def n_candidates_failed(self) -> int:
        return len(self.unevaluated)

    @property
    def n_robustness_failed(self) -> int:
        """Number of ranked rows whose requested robustness analysis was unavailable."""
        return sum(
            row.robustness_status not in (None, "ok")
            for row in self.ranks
        )


# B4: 동점/전부-0 랭킹 경고. rank 1 이 "최고"로 읽히므로, 실제로는 아무 후보도 target 을 만들지
# 못했거나 상위가 동점일 때 그 사실을 반드시 알려야 한다(현재는 알파벳 순 1등이 최고로 보고된다).
TIE_TOLERANCE = 1e-9


def is_evaluable(status: str, score: float) -> bool:
    """랭킹에 들어갈 자격 — optimal LP 이고 점수가 유한한 행만."""
    return status == "optimal" and math.isfinite(score)


def unevaluable_warnings(
    unevaluated: list[tuple[tuple[str, ...], str, str | None]], n_total: int
) -> list[str]:
    """P0-B/P0-C: 평가 불가 후보를 반드시 최상위 warnings 로 노출한다.

    평가되지 않은 후보는 --top-k 절단으로 사라질 수 있으므로(red-team F1: top-k 10 에서는 보이고
    top-k 2 에서는 사라진다), 개수와 이름을 절단과 무관한 최상위 warnings 에 남긴다.
    """
    if not unevaluated:
        return []
    names = ", ".join("+".join(members) for members, _status, _diag in unevaluated)
    warnings = [
        f"{len(unevaluated)} of {n_total} candidates could not be evaluated and are excluded "
        f"from the ranking (see unevaluated): {names}"
    ]
    if len(unevaluated) == n_total:
        warnings.append(
            "no candidate was evaluable; there is no ranking and no best producer"
        )
    return warnings


# F9 (round 5): with the sign-domain constraint, MINIMISING a target exchange yields exactly 0
# whenever 0 is feasible — essentially always. The LP answer is right, but the generic all-zero
# message ("no candidate achieved a non-zero target flux") then states something false about the
# science: the same pool secretes 12.11 mmol gDW^-1 h^-1 of acetate when asked in the max_*
# direction. Minimisation directions need their own wording.
MINIMISATION_DIRECTIONS = frozenset({"min_secretion", "min_uptake"})


def _is_minimisation(direction: str | None) -> bool:
    return str(direction) in MINIMISATION_DIRECTIONS


def _ranking_degeneracy_warnings(
    scored: list[tuple[tuple[str, ...], float, str]],
    *,
    tolerance: float = TIE_TOLERANCE,
    score_is_flux: bool = True,
    direction: str | None = None,
) -> list[str]:
    """(members, score, status) 목록 → 전부-0 / 상위 동점 경고. 순수 함수(solver 불요).

    ``score_is_flux=False`` 는 점수가 정규화된 무차원 값일 때 쓴다 — 이때 0 점은 flux 가 0 이라는
    뜻이 아니라 정규화 폭이 0 이라는 뜻일 수 있으므로(codex B3), 관측된 flux 를 부정하지 않는다.
    """
    warnings: list[str] = []
    evaluable = [row for row in scored if row[2] == "optimal" and math.isfinite(row[1])]
    if not evaluable:
        return warnings
    if all(abs(score) <= tolerance for _, score, _ in evaluable):
        warnings.append(
            "every evaluable candidate scored 0, which is the EXPECTED optimum for a "
            f"{direction} search (0 target flux is essentially always attainable). This does "
            "NOT mean the target cannot be produced — re-run with the matching max_* direction "
            "to measure capability. The ranking order is arbitrary"
            if _is_minimisation(direction) else
            "no candidate achieved a non-zero target flux; the ranking order is arbitrary "
            "and rank 1 must not be reported as the best producer"
            if score_is_flux else
            "every evaluable candidate scored 0; with a normalized metric this can mean the "
            "candidate set has zero score range (a single candidate, or all candidates equal) "
            "rather than zero target flux — read the per-target flux columns, and prefer "
            "--multi-metric carbon_equivalent for an absolute score"
        )
        return warnings
    best = max(score for _, score, _ in evaluable)
    tied = [members for members, score, _ in evaluable if abs(score - best) <= tolerance]
    if len(tied) > 1:
        warnings.append(
            f"top-{len(tied)} candidates tied at score {best:.6g} "
            f"({', '.join('+'.join(m) for m in sorted(tied))}); rank 1 is the first tie in "
            "member order, not a unique optimum"
        )
    return warnings


def _validate_config(config: SearchConfig) -> None:
    if config.min_size <= 0:
        raise ValueError("--min-size must be > 0")
    if config.max_size < config.min_size:
        raise ValueError("--max-size must be >= --min-size")
    if config.strategy == "random" and config.n_samples <= 0:
        raise ValueError("--n-samples must be > 0")
    if config.top_k <= 0:
        raise ValueError("--top-k must be > 0")
    if config.exhaustive_max < 0:
        raise ValueError("--exhaustive-max must be >= 0")
    if not (0.0 < config.growth_fraction <= 1.0):
        raise ValueError("--growth-fraction must satisfy 0<f<=1")


def count_candidate_combinations(ids: list[str], min_size: int, max_size: int) -> int:
    """Count allowed member sets without constructing them."""
    n_ids = len(ids)
    upper = min(max_size, n_ids)
    if min_size > upper:
        return 0
    return sum(math.comb(n_ids, size) for size in range(min_size, upper + 1))


def _iter_candidate_combinations(
    ids: list[str], min_size: int, max_size: int
) -> Iterator[tuple[str, ...]]:
    """Yield sorted member combinations lazily in size/lexicographic order."""
    ordered = sorted(ids)
    upper = min(max_size, len(ordered))
    for size in range(min_size, upper + 1):
        yield from itertools.combinations(ordered, size)


def candidate_combinations(ids: list[str], min_size: int, max_size: int) -> list[tuple[str, ...]]:
    """Enumerate sorted member combinations deterministically.

    Kept as the materialized compatibility API. Large single-target searches use
    :func:`count_candidate_combinations` and the lazy/sampled helpers instead.
    """
    return list(_iter_candidate_combinations(ids, min_size, max_size))


def choose_strategy(
    n_candidates: int, requested: SearchStrategy, *, exhaustive_max: int = 100
) -> str:
    """Resolve auto/random/GA strategy for product search."""
    if requested != "auto":
        return requested
    return "exhaustive" if n_candidates <= exhaustive_max else "ga"


def _sample_integer_ranks(total: int, sample_size: int, rng: random.Random) -> list[int]:
    """Uniformly sample unique integers from ``range(total)`` for arbitrary-size totals.

    Floyd's algorithm avoids both a candidate list and ``range(total)``'s platform-sized
    length limitation. The returned order is deterministic and independent of set iteration.
    """
    selected: set[int] = set()
    for upper in range(total - sample_size, total):
        picked = rng.randrange(upper + 1)
        selected.add(upper if picked in selected else picked)
    return sorted(selected)


def _unrank_combination(ids: list[str], size: int, rank: int) -> tuple[str, ...]:
    """Return the zero-based lexicographic ``rank`` among ``size``-member combinations."""
    n_ids = len(ids)
    n_combinations = math.comb(n_ids, size)
    if rank < 0 or rank >= n_combinations:
        raise ValueError("combination rank out of range")
    members: list[str] = []
    start = 0
    for position in range(size):
        remaining = size - position - 1
        for index in range(start, n_ids):
            suffixes = math.comb(n_ids - index - 1, remaining)
            if rank < suffixes:
                members.append(ids[index])
                start = index + 1
                break
            rank -= suffixes
    return tuple(members)


def _candidate_from_global_rank(
    ids: list[str], min_size: int, max_size: int, rank: int
) -> tuple[str, ...]:
    """Map a rank in the mixed-size candidate space to its member tuple."""
    upper = min(max_size, len(ids))
    for size in range(min_size, upper + 1):
        block_size = math.comb(len(ids), size)
        if rank < block_size:
            return _unrank_combination(ids, size, rank)
        rank -= block_size
    raise ValueError("candidate rank out of range")


def sample_candidate_combinations(
    ids: list[str],
    min_size: int,
    max_size: int,
    *,
    n_samples: int,
    seed: int,
) -> list[tuple[str, ...]]:
    """Sample uniformly from every allowed combination without enumerating the space."""
    if n_samples <= 0:
        raise ValueError("--n-samples must be > 0")
    ordered = sorted(ids)
    total = count_candidate_combinations(ordered, min_size, max_size)
    sample_size = min(n_samples, total)
    ranks = _sample_integer_ranks(total, sample_size, random.Random(seed))
    return [
        _candidate_from_global_rank(ordered, min_size, max_size, rank)
        for rank in ranks
    ]


# Round 5 (codex F3, part 2): every search evaluator called `apply_medium_checked` and threw the
# returned "could not be applied" list on the floor. Under `--allow-unknown-medium` that made a
# search silently run on a *different* medium from the requested one and still report `optimal`
# with no warning anywhere. The medium is an input to the science, so a partially-honoured medium
# has to reach both the per-candidate diagnostic and the run-level warnings.
UNAPPLIED_MEDIUM_PREFIX = "requested medium exchanges not applied (no counterpart in the model)"

# Round 6 (track B, instance 1): a merged medium is an overlay on MICOM's permissive default, not a
# defined medium. Measured on iML1515+iYO844+iHN637 with the shipped `western_diet.csv`: `EX_o2_m`
# stayed at 999999 and community growth came out 1.2677557 against 0.6990206751 with oxygen closed —
# an 81 % overestimate from one absent row. The count is stated so a search cannot report a
# "medium" result whose background nobody looked at.
MERGED_MEDIUM_PREFIX = "medium was MERGED onto the model's default, not applied exactly"


def _apply_search_medium(
    community: Any,
    medium_spec: Any | None,
    *,
    strict_medium: bool,
    notes: set[str] | None = None,
) -> str | None:
    """Apply the requested medium to one consortium. Returns a diagnostic when it was not whole."""
    if medium_spec is None:
        return None
    from cmig.core.medium_spec import MEDIUM_APPLICATION_MERGE, medium_application_report

    translation = medium_application_report(community, medium_spec, strict=strict_medium)
    parts: list[str] = []
    if translation.unmatched:
        parts.append(f"{UNAPPLIED_MEDIUM_PREFIX}: {sorted(translation.unmatched)}")
    if (
        translation.application_mode == MEDIUM_APPLICATION_MERGE
        and translation.undeclared_suppliers
    ):
        parts.append(
            f"{MERGED_MEDIUM_PREFIX}: {len(translation.undeclared_suppliers)} boundary reactions "
            "outside the requested medium can still supply mass, e.g. "
            f"{list(translation.undeclared_suppliers[:6])}"
        )
    if not parts:
        return None
    note = "; ".join(parts)
    if notes is not None:
        notes.add(note)
    return note


def _with_medium_note(diagnostic: str | None, note: str | None) -> str | None:
    if note is None:
        return diagnostic
    return note if not diagnostic else f"{note}; {diagnostic}"


def _evaluate_members(
    engine: Any,
    taxonomy: Any,
    members: tuple[str, ...],
    spec: TargetSpec,
    *,
    growth_fraction: float,
    solver: str,
    medium_spec: Any | None = None,
    strict_medium: bool = True,
    robustness_fva: bool = False,
    medium_notes: set[str] | None = None,
) -> PoolRank:
    sub = taxonomy[taxonomy["id"].astype(str).isin(members)].copy()
    medium_note: str | None = None
    try:
        community = engine.build_community(sub, cmig_solver=solver)
        medium_note = _apply_search_medium(
            community, medium_spec, strict_medium=strict_medium, notes=medium_notes
        )
        result = target_max_solve(
            community,
            spec,
            growth_fraction=growth_fraction,
            solver=solver,
        )
        fva_lo = fva_hi = None
        fva_status = None
        if robustness_fva:
            from cmig.core.search_advanced import robustness_fva as run_robustness_fva

            fva = run_robustness_fva(
                community,
                spec,
                growth_fraction=growth_fraction,
                solver=solver,
            )
            fva_status = fva.status
            if fva.status == "ok":
                fva_lo = fva.fva_lo
                fva_hi = fva.fva_hi
        return PoolRank(
            rank=0,
            members=members,
            score=score_target_result(result, spec),
            target_flux=result.target_flux,
            community_growth=result.community_growth,
            status=result.status,
            diagnostic=_with_medium_note(result.diagnostic, medium_note),
            robustness_fva_lo=fva_lo,
            robustness_fva_hi=fva_hi,
            robustness_status=fva_status,
        )
    except Exception as error:  # noqa: BLE001 - isolate one failed consortium
        return PoolRank(
            rank=0,
            members=members,
            score=float("-inf"),
            target_flux=0.0,
            community_growth=0.0,
            status="failed",
            diagnostic=_with_medium_note(str(error), medium_note),
        )


def _add_robustness_fva(
    engine: Any,
    taxonomy: Any,
    row: PoolRank,
    spec: TargetSpec,
    *,
    growth_fraction: float,
    solver: str,
    medium_spec: Any | None,
    strict_medium: bool,
    medium_notes: set[str] | None = None,
) -> PoolRank:
    """Attach FVA to one final ranked row without repeating the target-max solve."""
    sub = taxonomy[taxonomy["id"].astype(str).isin(row.members)].copy()
    try:
        community = engine.build_community(sub, cmig_solver=solver)
        _apply_search_medium(
            community,
            medium_spec,
            strict_medium=strict_medium,
            notes=medium_notes,
        )
        from cmig.core.search_advanced import robustness_fva as run_robustness_fva

        fva = run_robustness_fva(
            community,
            spec,
            growth_fraction=growth_fraction,
            solver=solver,
        )
        robustness_note = None
        if fva.status != "ok":
            reason = fva.diagnostic or "no diagnostic was returned"
            robustness_note = f"robustness FVA {fva.status}: {reason}"
        return replace(
            row,
            robustness_fva_lo=fva.fva_lo if fva.status == "ok" else None,
            robustness_fva_hi=fva.fva_hi if fva.status == "ok" else None,
            robustness_status=fva.status,
            diagnostic=_with_medium_note(row.diagnostic, robustness_note),
        )
    except Exception as error:  # noqa: BLE001 - robustness must not erase a valid ranking
        return replace(
            row,
            diagnostic=_with_medium_note(
                row.diagnostic,
                f"robustness FVA failed: {error}",
            ),
            robustness_status="failed",
        )


def _json_safe(value: Any) -> Any:
    """Replace non-finite numbers recursively so metadata is strict-JSON serializable."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _ga_metadata(config: GAConfig, result: Any) -> dict[str, Any]:
    """Build JSON-ready provenance for an approximate search."""
    history: list[Any] = []
    for item in getattr(result, "history", []):
        history.append(asdict(cast(Any, item)) if is_dataclass(item) else item)
    metadata = {
        "config": asdict(config),
        "generations_run": result.generations_run,
        "evaluations": result.evaluations,
        "stop_reason": getattr(result, "stop_reason", "generations"),
        "history": history,
        "warning": result.warning,
    }
    return cast(dict[str, Any], _json_safe(metadata))


def search_model_pool(
    engine: Any,
    taxonomy: Any,
    config: SearchConfig,
    *,
    medium_spec: Any | None = None,
    strict_medium: bool = True,
) -> PoolSearchResult:
    """Rank model-pool combinations for a target metabolite."""
    _validate_config(config)
    ids = [str(x) for x in taxonomy["id"]]
    if len(set(ids)) != len(ids):
        raise ValueError("taxonomy id values must be unique")
    n_candidates_total = count_candidate_combinations(
        ids, config.min_size, config.max_size
    )
    if n_candidates_total == 0:
        raise ValueError("no candidate combinations generated")
    strategy = choose_strategy(
        n_candidates_total,
        config.strategy,
        exhaustive_max=config.exhaustive_max,
    )
    spec = TargetSpec(config.target, config.direction)
    warnings: list[str] = []
    medium_notes: set[str] = set()
    cache: dict[tuple[str, ...], PoolRank] = {}
    ga_metadata: dict[str, Any] | None = None

    def evaluate(members: tuple[str, ...]) -> PoolRank:
        if members not in cache:
            cache[members] = _evaluate_members(
                engine,
                taxonomy,
                members,
                spec,
                growth_fraction=config.growth_fraction,
                solver=config.solver,
                medium_spec=medium_spec,
                strict_medium=strict_medium,
                # FVA is deliberately deferred until the final top-k is known.
                robustness_fva=False,
                medium_notes=medium_notes,
            )
        return cache[members]

    if strategy == "exhaustive":
        for members in _iter_candidate_combinations(
            ids, config.min_size, config.max_size
        ):
            evaluate(members)
    elif strategy == "random":
        selected = sample_candidate_combinations(
            ids,
            config.min_size,
            config.max_size,
            n_samples=config.n_samples,
            seed=config.seed,
        )
        for members in selected:
            evaluate(members)
        if len(selected) < n_candidates_total:
            warnings.append("random sampling evaluated a subset; global optimum is not guaranteed")
    elif strategy == "ga":
        from cmig.core.search_ga import genetic_search

        warnings.append("GA approximate search; global optimum is not guaranteed")
        # SearchConfig.seed is the run-level reproducibility contract shared with random search;
        # a nested GAConfig may tune the algorithm but cannot silently select a different run.
        normalized_ga_config = replace(
            config.ga_config if config.ga_config is not None else GAConfig(),
            min_size=config.min_size,
            max_size=config.max_size,
            seed=config.seed,
        )
        ga = genetic_search(
            ids,
            lambda genome: evaluate(tuple(genome)).score,
            normalized_ga_config,
            top_k=config.top_k,
        )
        warnings.append(ga.warning)
        ga_metadata = _ga_metadata(normalized_ga_config, ga)
    else:
        raise ValueError(f"unsupported search strategy: {strategy}")

    # The GA may evaluate many candidates that never reach its final population/top-k. Its
    # fitness callback populates this product cache, so use the cache itself as the audit trail.
    evaluated = list(cache.values())
    # P0-B: 평가 가능한 후보만 랭킹에 들어간다. 실패 후보를 score=-inf 로 정렬 바닥에 두고
    # --top-k 로 자르면 실패가 산출물에서 완전히 사라진다(red-team F1).
    solved = sorted(
        (row for row in evaluated if is_evaluable(row.status, row.score)),
        key=lambda row: (-row.score, row.members),
    )
    failed = sorted(
        (row for row in evaluated if not is_evaluable(row.status, row.score)),
        key=lambda row: row.members,
    )
    # B4: 동점/전부-0 은 평가된 후보 전체를 기준으로 판정한다(top_k 절단 전).
    warnings.extend(_ranking_degeneracy_warnings(
        [(row.members, row.score, row.status) for row in solved],
        direction=config.direction.value,
    ))
    warnings.extend(unevaluable_warnings(
        [(row.members, row.status, row.diagnostic) for row in failed], len(evaluated)
    ))

    def _renumber(row: PoolRank, rank: int) -> PoolRank:
        return replace(row, rank=rank)

    ranked = [_renumber(row, i + 1) for i, row in enumerate(solved[: config.top_k])]
    if config.robustness_fva:
        ranked = [
            _add_robustness_fva(
                engine,
                taxonomy,
                row,
                spec,
                growth_fraction=config.growth_fraction,
                solver=config.solver,
                medium_spec=medium_spec,
                strict_medium=strict_medium,
                medium_notes=medium_notes,
            )
            for row in ranked
        ]
        robustness_failed = [
            row for row in ranked if row.robustness_status not in (None, "ok")
        ]
        if robustness_failed:
            details = ", ".join(
                f"{'+'.join(row.members)} ({row.robustness_status})"
                for row in robustness_failed
            )
            warnings.append(
                f"robustness FVA was unavailable for {len(robustness_failed)} reported "
                f"candidate(s); target-max rankings were retained: {details}"
            )
    warnings.extend(sorted(medium_notes))
    # 평가 불가 후보는 rank 0 (= "순위 없음")으로 남고, top_k 와 무관하게 전부 보고된다.
    unevaluated = [_renumber(row, 0) for row in failed]
    return PoolSearchResult(
        target=config.target,
        target_exchange=spec.exchange_id(),
        direction=config.direction.value,
        strategy=strategy,
        n_pool_members=len(ids),
        n_candidates_total=n_candidates_total,
        n_candidates_evaluated=len(cache),
        ranks=ranked,
        warnings=warnings,
        unevaluated=unevaluated,
        ga_metadata=ga_metadata,
    )


# ── Multi-target search (§14 다중 타깃) ─────────────────────────────────────────
# Users can rank model-pool combinations against several targets at once, combined
# by a weighted sum of per-target scores normalized into [0,1] over the observed
# range, plus an N-dimensional Pareto non-dominated flag.


MultiTargetMetric = Literal[
    "normalized_weighted", "carbon_equivalent", "raw_sum", "pareto"
]

# Epsilon floors, as a fraction of each target's own achievable maximum for that consortium.
# 0.0 reproduces the plain scalarised vertex; the rest force progressively more mixed solutions.
PARETO_EPSILON_GRID: tuple[float, ...] = (0.0, 0.05, 0.15, 0.3, 0.5)

# 점수의 단위 — 무차원 정규화 점수와 실제 flux 합을 같은 칸에 담지 않기 위해 결과에 기록한다.
MULTI_METRIC_UNITS: dict[str, str] = {
    "normalized_weighted": "dimensionless (weighted min-max over the candidate set)",
    "carbon_equivalent": "mmol C gDW^-1 h^-1",
    "raw_sum": "mmol gDW^-1 h^-1",
    # F6 (round 5): the pareto path never resolves carbon numbers — `carbon_numbers` is empty and
    # the score is sum(user weight x flux), with weights defaulting to 1.0. Labelling that
    # "mmol C" claimed a carbon-equivalent score that was never computed, i.e. it asserted that C2
    # acetate and C4 succinate had been made commensurate when they had simply been added up.
    "pareto": (
        "sum(weight x flux); mmol gDW^-1 h^-1 unless --target-weights are carbon numbers "
        "(front members are not totally ordered — the score does not rank the front)"
    ),
}

# S1's deepest limit. Maximising a weighted sum over a polytope lands on a vertex, so a carbon-
# weighted objective concentrates on whichever acid has the best carbon-per-substrate yield and
# reports every other target as exactly 0. That is a property of weighted-sum LP, not degeneracy:
# no weight vector avoids it, because every weight vector still selects a vertex.
SCALARISATION_WARNING = (
    "a weighted-sum objective is optimised at a vertex of the feasible set, so this ranking "
    "systematically favours a single-metabolite specialist over a balanced producer — the "
    "winner's 'total' can be one metabolite and zero of the others. Use --multi-metric pareto "
    "for the non-dominated trade-off set instead of one scalarised winner"
)

# flux 열의 출처 표시 (B3): 하나의 joint LP 해인지, 표적별 독립 해(동시 달성 불가)인지.
FLUX_BASIS_JOINT = "joint_weighted_lp"
FLUX_BASIS_CAPABILITY = "per_target_capability_not_simultaneous"
FLUX_BASIS_NONE = "unevaluated"


@dataclass(frozen=True)
class MultiTargetConfig:
    targets: list[str]
    directions: dict[str, Direction]
    weights: dict[str, float]
    min_size: int = 2
    max_size: int = 2
    growth_fraction: float = 0.5
    solver: str = "gurobi"
    top_k: int = 10
    exhaustive_max: int = 100
    metric: MultiTargetMetric = "normalized_weighted"


@dataclass(frozen=True)
class MultiTargetRank:
    rank: int
    members: tuple[str, ...]
    weighted_score: float               # metric 에 따라 무차원 or 실제 flux 합; -inf = 평가 불가
    target_fluxes: dict[str, float]     # metabolite → raw exchange flux
    target_scores: dict[str, float]     # metabolite → per-target contribution
    community_growth: float
    status: str
    pareto: bool = False
    diagnostic: str | None = None
    # B3: 이 consortium 에 exchange 자체가 없어 0 으로 기여한 target 들.
    missing_targets: tuple[str, ...] = ()
    # B3: flux 열이 한 해에서 온 것인지(joint) 표적별 독립 해인지(동시 달성 불가) 표시.
    flux_basis: str = FLUX_BASIS_JOINT


@dataclass(frozen=True)
class MultiTargetSearchResult:
    targets: list[str]
    target_exchanges: dict[str, str]
    directions: dict[str, str]
    weights: dict[str, float]
    strategy: str
    normalizer: str
    solution_semantics: str
    n_pool_members: int
    n_candidates_total: int
    n_candidates_evaluated: int
    ranks: list[MultiTargetRank]
    warnings: list[str]
    metric: str = "normalized_weighted"
    score_unit: str = MULTI_METRIC_UNITS["normalized_weighted"]
    # P0-C: 평가 불가 후보 — rank 를 갖지 않고 top_ranked 에 들어가지 않는다.
    unevaluated: list[MultiTargetRank] = field(default_factory=list)


@dataclass(frozen=True)
class _ComboEval:
    members: tuple[str, ...]
    status: str
    community_growth: float
    fluxes: dict[str, float]
    signed: dict[str, float]            # direction-adjusted raw (larger = better), no weight
    diagnostic: str | None = None
    missing_targets: tuple[str, ...] = ()
    flux_basis: str = FLUX_BASIS_CAPABILITY


def _signed_raw(result: Any, spec: TargetSpec) -> float:
    """Direction-adjusted raw target value (larger = better), without the weight."""
    if result.status != "optimal":
        return float("-inf")
    match spec.direction:
        case Direction.MAX_SECRETION | Direction.MIN_UPTAKE:
            return float(result.target_flux)
        case _:  # MIN_SECRETION, MAX_UPTAKE
            return -float(result.target_flux)


def rank_multi_target(
    evals: list[_ComboEval], specs: list[TargetSpec], *,
    normalization_ranges: dict[str, tuple[float, float]] | None = None,
    metric: MultiTargetMetric = "normalized_weighted",
) -> tuple[list[MultiTargetRank], str]:
    """Pure ranking. Returns (ranked_rows, normalizer_name). Testable without a solver.

    ``normalized_weighted`` min-max normalizes each target over the candidate set (dimensionless,
    not comparable across runs). ``carbon_equivalent``/``raw_sum`` keep real flux units and simply
    weight-and-add, so the score is comparable across runs — the weights carry the chemistry
    (carbon number) instead of the candidate set carrying it.
    """
    from cmig.core.search_advanced import (
        normalize_score,
        pareto_frontier_nd,
        weighted_multi_target,
    )

    mets = [s.metabolite for s in specs]
    weight_of = {s.metabolite: s.weight for s in specs}
    ok = [e for e in evals if e.status == "optimal"]
    ranges: dict[str, tuple[float, float]] = {}
    for m in mets:
        if normalization_ranges is not None and m in normalization_ranges:
            ranges[m] = normalization_ranges[m]
        else:
            vals = [e.signed[m] for e in ok if m in e.signed]
            ranges[m] = (min(vals), max(vals)) if vals else (0.0, 1.0)

    rows: list[MultiTargetRank] = []
    if metric == "normalized_weighted":
        normalizer = (
            "capability_range_joint_lp" if normalization_ranges is not None else "observed_range"
        )
    else:
        normalizer = f"none_{metric}_absolute_units"
    for e in evals:
        if e.status != "optimal":
            rows.append(MultiTargetRank(
                0, e.members, float("-inf"), e.fluxes, {}, e.community_growth,
                e.status, False, e.diagnostic, e.missing_targets, e.flux_basis))
            continue
        contributions: dict[str, float] = {}
        if metric == "normalized_weighted":
            for m in mets:
                lo, hi = ranges[m]
                contributions[m] = normalize_score(
                    e.signed.get(m, 0.0), observed_min=lo, observed_max=hi).value
            score = weighted_multi_target(contributions, specs)
        else:
            # 실제 단위 유지: 기여도 = weight(=carbon number 등) × direction 보정 flux.
            for m in mets:
                contributions[m] = weight_of[m] * e.signed.get(m, 0.0)
            score = sum(contributions.values())
        rows.append(MultiTargetRank(
            0, e.members, score, e.fluxes, contributions, e.community_growth, "optimal",
            False, None, e.missing_targets, e.flux_basis))

    ok_idx = [i for i, row in enumerate(rows) if row.status == "optimal"]
    points = [tuple(evals[i].signed[metabolite] for metabolite in mets) for i in ok_idx]
    keep = {ok_idx[k] for k in pareto_frontier_nd(points)}
    rows = [replace(row, pareto=(i in keep)) for i, row in enumerate(rows)]

    # P0-C: 평가 불가 행은 rank 를 받지 않는다 — rank 2/3 을 부여받고 top_ranked 에 들어가면
    # "평가되었지만 낮은 점수"와 구별할 수 없다. rank 0 = 순위 없음.
    solved = sorted(
        (r for r in rows if is_evaluable(r.status, r.weighted_score)),
        key=lambda r: (-r.weighted_score, r.members),
    )
    failed = sorted(
        (r for r in rows if not is_evaluable(r.status, r.weighted_score)),
        key=lambda r: r.members,
    )
    ranked = [replace(r, rank=i + 1) for i, r in enumerate(solved)]
    unevaluated = [replace(r, rank=0) for r in failed]
    return ranked + unevaluated, normalizer


def _evaluate_members_multi(
    engine: Any, taxonomy: Any, members: tuple[str, ...], specs: list[TargetSpec], *,
    growth_fraction: float, solver: str, medium_spec: Any | None, strict_medium: bool,
    medium_notes: set[str] | None = None,
) -> _ComboEval:
    """Per-target capability pass. Fluxes come from independent solves — NOT simultaneous.

    B3: a target whose exchange is absent from this consortium contributes flux 0 (it simply
    cannot make that metabolite) and is listed in ``missing_targets``. Only a genuinely
    non-optimal LP (infeasible / baseline failure / solver error) disqualifies the consortium.
    """
    sub = taxonomy[taxonomy["id"].astype(str).isin(members)].copy()
    try:
        community = engine.build_community(sub, cmig_solver=solver)
        medium_note = _apply_search_medium(
            community, medium_spec, strict_medium=strict_medium, notes=medium_notes
        )
        fluxes: dict[str, float] = {}
        signed: dict[str, float] = {}
        status = "optimal"
        growth = 0.0
        diag: str | None = None
        missing: list[str] = []
        for spec in specs:
            res = target_max_solve(
                community, spec, growth_fraction=growth_fraction, solver=solver)
            if res.status == "missing":
                # exchange 부재 = 이 대사체를 만들 수 없음 → 0 기여, consortium 은 계속 평가된다.
                missing.append(spec.metabolite)
                fluxes[spec.metabolite] = 0.0
                signed[spec.metabolite] = 0.0
                continue
            fluxes[spec.metabolite] = float(res.target_flux)
            signed[spec.metabolite] = _signed_raw(res, spec)
            growth = float(res.community_growth)
            if res.status != "optimal":       # 진짜 non-optimal LP → 랭킹 불가
                status = res.status
                diag = res.diagnostic
        if len(missing) == len(specs):        # 평가할 target 이 하나도 없다
            status = "missing"
            diag = f"no target exchange present in this consortium: {sorted(missing)}"
        return _ComboEval(
            members, status, growth, fluxes, signed, _with_medium_note(diag, medium_note),
            tuple(sorted(missing)), FLUX_BASIS_CAPABILITY,
        )
    except Exception as e:  # noqa: BLE001 - per-combo isolation
        return _ComboEval(members, "failed", 0.0, {}, {}, str(e), (), FLUX_BASIS_NONE)


def _capability_ranges(
    evals: list[_ComboEval], specs: list[TargetSpec]
) -> dict[str, tuple[float, float]]:
    """Observed per-target capability ranges used only to scale the joint LP objective."""
    ok = [row for row in evals if row.status == "optimal"]
    ranges: dict[str, tuple[float, float]] = {}
    for spec in specs:
        values = [row.signed[spec.metabolite] for row in ok if spec.metabolite in row.signed]
        ranges[spec.metabolite] = (min(values), max(values)) if values else (0.0, 1.0)
    return ranges


def _joint_lp_scales(
    metric: MultiTargetMetric, ranges: dict[str, tuple[float, float]]
) -> dict[str, float]:
    """joint LP 목적식의 target 별 나눗값.

    ``normalized_weighted`` 는 표적 간 크기 차이를 candidate set 의 capability 폭으로 흡수한다
    (무차원). ``carbon_equivalent``/``raw_sum`` 은 실제 단위를 유지해야 하므로 1.0 — 가중치가
    화학(탄소 수)을 담고, candidate set 이 점수 척도를 바꾸지 않는다.
    """
    if metric != "normalized_weighted":
        return dict.fromkeys(ranges, 1.0)
    return {
        metabolite: (high - low if high - low > 1e-12 else 1.0)
        for metabolite, (low, high) in ranges.items()
    }


def _evaluate_members_multi_joint(
    engine: Any, taxonomy: Any, members: tuple[str, ...], specs: list[TargetSpec], *,
    normalization_ranges: dict[str, tuple[float, float]], growth_fraction: float,
    solver: str, medium_spec: Any | None, strict_medium: bool,
    metric: MultiTargetMetric = "normalized_weighted",
    medium_notes: set[str] | None = None,
) -> _ComboEval:
    """Evaluate one consortium with a single jointly feasible weighted LP solution."""
    from cmig.core.search import joint_target_solve

    sub = taxonomy[taxonomy["id"].astype(str).isin(members)].copy()
    try:
        community = engine.build_community(sub, cmig_solver=solver)
        medium_note = _apply_search_medium(
            community, medium_spec, strict_medium=strict_medium, notes=medium_notes
        )
        scales = _joint_lp_scales(metric, normalization_ranges)
        result = joint_target_solve(
            community,
            specs,
            normalization_scales=scales,
            growth_fraction=growth_fraction,
            solver=solver,
        )
        return _ComboEval(
            members,
            result.status,
            result.community_growth,
            result.target_fluxes,
            result.signed_values,
            _with_medium_note(result.diagnostic, medium_note),
            result.missing_targets,
            FLUX_BASIS_JOINT if result.status == "optimal" else FLUX_BASIS_NONE,
        )
    except Exception as e:  # noqa: BLE001 - per-combo isolation
        return _ComboEval(members, "failed", 0.0, {}, {}, str(e), (), FLUX_BASIS_NONE)


def _pareto_points_for_members(
    engine: Any, taxonomy: Any, members: tuple[str, ...], specs: list[TargetSpec], *,
    capability: dict[str, float], growth_fraction: float, solver: str,
    medium_spec: Any | None, strict_medium: bool,
    epsilon_grid: tuple[float, ...] = PARETO_EPSILON_GRID,
    medium_notes: set[str] | None = None,
) -> list[_ComboEval]:
    """Trace one consortium's trade-off surface with an epsilon-constraint sweep.

    Each epsilon level forces every target to at least that fraction of its own achievable
    maximum, which removes the single-metabolite vertices from the feasible set and makes the
    optimiser return a genuinely mixed flux vector. Infeasible levels are simply dropped — an
    epsilon that cannot be met is information about the trade-off, not an error.
    """
    from cmig.core.search import epsilon_constrained_solve

    sub_taxonomy = taxonomy[taxonomy["id"].astype(str).isin(members)].copy()
    points: list[_ComboEval] = []
    try:
        community = engine.build_community(sub_taxonomy, cmig_solver=solver)
        medium_note = _apply_search_medium(
            community, medium_spec, strict_medium=strict_medium, notes=medium_notes
        )
        for epsilon in epsilon_grid:
            floors = {
                spec.metabolite: epsilon * max(0.0, capability.get(spec.metabolite, 0.0))
                for spec in specs
            }
            result = epsilon_constrained_solve(
                community, specs, floors,
                normalization_scales=dict.fromkeys(
                    (spec.metabolite for spec in specs), 1.0
                ),
                growth_fraction=growth_fraction, solver=solver,
            )
            if result.status != "optimal":
                continue
            points.append(_ComboEval(
                members, "optimal", result.community_growth,
                dict(result.target_fluxes), dict(result.signed_values),
                _with_medium_note(f"epsilon={epsilon:g}", medium_note),
                result.missing_targets, FLUX_BASIS_JOINT,
            ))
    except Exception as error:  # noqa: BLE001 - per-combo isolation, same as the other passes
        return [_ComboEval(members, "failed", 0.0, {}, {}, str(error), (), FLUX_BASIS_NONE)]
    if not points:
        # Every epsilon level came back non-optimal without raising. Returning [] made the
        # consortium vanish from both the ranking and `unevaluated` while
        # n_candidates_evaluated still counted it; it is an unevaluable candidate.
        return [_ComboEval(
            members, "failed", 0.0, {}, {},
            _with_medium_note("no epsilon level solved to optimality", medium_note),
            (), FLUX_BASIS_NONE,
        )]
    return points


def search_model_pool_multi(
    engine: Any, taxonomy: Any, config: MultiTargetConfig, *,
    medium_spec: Any | None = None, strict_medium: bool = True,
) -> MultiTargetSearchResult:
    """Rank model-pool combinations against multiple targets (weighted-normalized + Pareto)."""
    if len(config.targets) < 2:
        raise ValueError("multi-target search needs >= 2 targets; use single --target otherwise")
    if config.min_size <= 0 or config.max_size < config.min_size:
        raise ValueError("require 0 < --min-size <= --max-size")
    if config.top_k <= 0:
        raise ValueError("--top-k must be > 0")
    if not (0.0 < config.growth_fraction <= 1.0):
        raise ValueError("--growth-fraction must satisfy 0<f<=1")
    if set(config.directions) != set(config.targets):
        raise ValueError("directions keys must match targets exactly")
    if set(config.weights) != set(config.targets):
        raise ValueError("weights keys must match targets exactly")
    if any(not math.isfinite(config.weights[t]) or config.weights[t] < 0.0 for t in config.targets):
        raise ValueError("target weights must be finite and non-negative")
    if not any(config.weights[t] > 0.0 for t in config.targets):
        raise ValueError("at least one target weight must be positive")

    ids = [str(x) for x in taxonomy["id"]]
    if len(set(ids)) != len(ids):
        raise ValueError("taxonomy id values must be unique")
    specs = [
        TargetSpec(t, config.directions[t], config.weights[t]) for t in config.targets
    ]
    n_candidates_total = count_candidate_combinations(
        ids, config.min_size, config.max_size
    )
    if n_candidates_total == 0:
        raise ValueError("no candidate combinations generated")
    if n_candidates_total > config.exhaustive_max:
        raise ValueError(
            f"{n_candidates_total} candidates > exhaustive_max={config.exhaustive_max}; "
            "narrow --min-size/--max-size (multi-target search is exhaustive-only, no silent "
            "truncation)")
    # Multi-target search is exhaustive-only, but the guard above guarantees this
    # compatibility list is small before it is materialized.
    candidates = candidate_combinations(ids, config.min_size, config.max_size)

    medium_notes: set[str] = set()
    capability_evals = [
        _evaluate_members_multi(
            engine, taxonomy, members, specs,
            growth_fraction=config.growth_fraction, solver=config.solver,
            medium_spec=medium_spec, strict_medium=strict_medium,
            medium_notes=medium_notes)
        for members in candidates
    ]
    ranges = _capability_ranges(capability_evals, specs)
    if config.metric == "pareto":
        return _pareto_search(
            engine, taxonomy, candidates, capability_evals, specs, config,
            medium_spec=medium_spec, strict_medium=strict_medium, ids=ids,
            medium_notes=medium_notes,
        )
    evals: list[_ComboEval] = []
    for members, capability in zip(candidates, capability_evals, strict=True):
        if capability.status != "optimal":
            evals.append(capability)
            continue
        evals.append(
            _evaluate_members_multi_joint(
                engine,
                taxonomy,
                members,
                specs,
                normalization_ranges=ranges,
                growth_fraction=config.growth_fraction,
                solver=config.solver,
                medium_spec=medium_spec,
                strict_medium=strict_medium,
                metric=config.metric,
                medium_notes=medium_notes,
            )
        )
    all_rows, normalizer = rank_multi_target(
        evals, specs, normalization_ranges=ranges, metric=config.metric
    )
    # P0-C: rank 0 = 순위 없음 = 평가 불가. 별도 블록으로 나눠 top_ranked 를 오염시키지 않는다.
    ranked = [row for row in all_rows if row.rank > 0]
    unevaluated = [row for row in all_rows if row.rank == 0]
    warnings: list[str] = list(_multi_target_warnings(ranked, unevaluated, config))
    warnings.extend(sorted(medium_notes))
    return MultiTargetSearchResult(
        targets=list(config.targets),
        target_exchanges={s.metabolite: s.exchange_id() for s in specs},
        directions={t: config.directions[t].value for t in config.targets},
        weights=dict(config.weights),
        strategy="exhaustive",
        normalizer=normalizer,
        solution_semantics="joint_weighted_lp_single_flux_vector",
        n_pool_members=len(ids),
        n_candidates_total=n_candidates_total,
        n_candidates_evaluated=len(evals),
        ranks=ranked[: config.top_k],
        warnings=warnings,
        metric=config.metric,
        score_unit=MULTI_METRIC_UNITS[config.metric],
        unevaluated=unevaluated,
    )


def _pareto_search(
    engine: Any, taxonomy: Any, candidates: list[tuple[str, ...]],
    capability_evals: list[_ComboEval], specs: list[TargetSpec], config: MultiTargetConfig,
    *, medium_spec: Any, strict_medium: bool, ids: list[str],
    medium_notes: set[str] | None = None,
) -> MultiTargetSearchResult:
    """Report the non-dominated trade-off set instead of one scalarised winner (item 9).

    Every (consortium, epsilon level) pair that solves contributes one achieved flux vector; the
    front is the non-dominated subset across all of them, using the user's weights only to order
    the *report*, never to collapse the objectives. Points on the front are NOT totally ordered —
    that is the whole point, and the summary says so.
    """
    from cmig.core.search_advanced import pareto_frontier_nd

    metabolites = [spec.metabolite for spec in specs]
    weight_of = {spec.metabolite: spec.weight for spec in specs}
    points: list[_ComboEval] = []
    unevaluated: list[_ComboEval] = []
    for members, capability in zip(candidates, capability_evals, strict=True):
        if capability.status != "optimal":
            unevaluated.append(capability)
            continue
        found = _pareto_points_for_members(
            engine, taxonomy, members, specs,
            capability={m: capability.signed.get(m, 0.0) for m in metabolites},
            growth_fraction=config.growth_fraction, solver=config.solver,
            medium_spec=medium_spec, strict_medium=strict_medium,
            medium_notes=medium_notes,
        )
        if found and all(point.status != "optimal" for point in found):
            unevaluated.extend(found)
            continue
        points.extend(point for point in found if point.status == "optimal")

    vectors = [tuple(point.signed.get(m, 0.0) for m in metabolites) for point in points]
    keep = set(pareto_frontier_nd(vectors)) if vectors else set()
    rows: list[MultiTargetRank] = []
    for index, point in enumerate(points):
        if index not in keep:
            continue
        contributions = {m: weight_of[m] * point.signed.get(m, 0.0) for m in metabolites}
        rows.append(MultiTargetRank(
            0, point.members, sum(contributions.values()), point.fluxes, contributions,
            point.community_growth, "optimal", True, point.diagnostic,
            point.missing_targets, point.flux_basis,
        ))
    # Deduplicate identical achieved vectors from different epsilon levels of the same consortium.
    seen: set[tuple[Any, ...]] = set()
    unique: list[MultiTargetRank] = []
    for row in sorted(rows, key=lambda r: (-r.weighted_score, r.members)):
        key = (row.members, tuple(round(row.target_fluxes.get(m, 0.0), 6) for m in metabolites))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    ranked = [replace(row, rank=i + 1) for i, row in enumerate(unique)]

    warnings = list(unevaluable_warnings(
        [(r.members, r.status, r.diagnostic) for r in unevaluated],
        len(candidates),
    ))
    n_specialists = sum(
        1 for row in ranked
        if sum(1 for m in metabolites if abs(row.target_scores.get(m, 0.0)) > TIE_TOLERANCE) <= 1
    )
    warnings.append(
        f"pareto mode: {len(ranked)} non-dominated points across {len(candidates)} consortia and "
        f"{len(PARETO_EPSILON_GRID)} epsilon levels. Front members are NOT totally ordered — "
        "rank here is a reporting order (weighted sum), not a claim that rank 1 is best. "
        f"{n_specialists} of {len(ranked)} front points are single-metabolite specialists"
    )
    warnings.extend(sorted(medium_notes or ()))
    return MultiTargetSearchResult(
        targets=list(config.targets),
        target_exchanges={s.metabolite: s.exchange_id() for s in specs},
        directions={t: config.directions[t].value for t in config.targets},
        weights=dict(config.weights),
        strategy="exhaustive_epsilon_constraint",
        normalizer="none_pareto_front_absolute_units",
        solution_semantics="epsilon_constrained_lp_non_dominated_set",
        n_pool_members=len(ids),
        n_candidates_total=len(candidates),
        n_candidates_evaluated=len(candidates),
        ranks=ranked[: config.top_k] if config.top_k else ranked,
        warnings=warnings,
        metric="pareto",
        score_unit=MULTI_METRIC_UNITS["pareto"],
        unevaluated=unevaluated_ranks(unevaluated, metabolites),
    )


def unevaluated_ranks(
    evals: list[_ComboEval], metabolites: list[str]
) -> list[MultiTargetRank]:
    """Unevaluable combos as rank-0 rows (P0-C), shared by the pareto path."""
    return [
        MultiTargetRank(
            0, e.members, float("-inf"), e.fluxes, {}, e.community_growth,
            e.status, False, e.diagnostic, e.missing_targets, e.flux_basis,
        )
        for e in evals
    ]


def _multi_target_warnings(
    ranked: list[MultiTargetRank],
    unevaluated: list[MultiTargetRank],
    config: MultiTargetConfig,
) -> list[str]:
    """B3/B4: 부재 target·평가 불가·전부-0·동점을 요약 warnings 로 노출한다."""
    warnings: list[str] = list(unevaluable_warnings(
        [(r.members, r.status, r.diagnostic) for r in unevaluated],
        len(ranked) + len(unevaluated),
    ))
    # P0-F(D7): 선형 joint 목적식은 정점 해를 고르므로, 일부 target 이 정확히 0 인 것은
    # "만들 수 없다"가 아니라 "이 정점에서 선택되지 않았다"일 수 있다.
    collapsed = [
        r for r in ranked
        if r.status == "optimal"
        and any(abs(v) <= TIE_TOLERANCE for v in r.target_scores.values())
        and any(abs(v) > TIE_TOLERANCE for v in r.target_scores.values())
    ]
    if collapsed:
        warnings.append(
            "the joint objective is linear, so its optimum is a vertex: targets reported as "
            "exactly 0 alongside positive ones may be a vertex-selection artifact rather than an "
            "inability to produce them ("
            + ", ".join(
                f"{'+'.join(r.members)}:"
                + ",".join(
                    sorted(m for m, v in r.target_scores.items() if abs(v) <= TIE_TOLERANCE)
                )
                for r in collapsed[:5]
            )
            + ")"
        )
    partial = [r for r in ranked if r.status == "optimal" and r.missing_targets]
    if partial:
        warnings.append(
            "some combinations lack an exchange for part of the target set; those targets "
            "contribute flux 0 rather than disqualifying the combination: "
            + ", ".join(f"{'+'.join(r.members)}({','.join(r.missing_targets)})" for r in partial)
        )
    if config.metric == "normalized_weighted":
        warnings.append(
            "normalized_weighted scores are min-max normalized over this candidate set; they "
            "are dimensionless and NOT comparable across runs — use --multi-metric "
            "carbon_equivalent for an absolute, run-comparable total"
        )
    # Item 9: every scalarised metric inherits the vertex-selection bias, so say it on all of them.
    if config.metric != "pareto":
        warnings.append(SCALARISATION_WARNING)
    warnings.extend(_ranking_degeneracy_warnings(
        [(r.members, r.weighted_score, r.status) for r in ranked],
        score_is_flux=config.metric != "normalized_weighted",
    ))
    return warnings
