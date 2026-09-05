"""Shared search request, preflight and isolated solver workers for CLI and GUI."""

from __future__ import annotations

import multiprocessing
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Any

from cmig.core.search_constraints import SEARCH_POLICY_VERSION, validate_taxonomy
from cmig.core.search_execution import SearchControl
from cmig.core.search_profile import timed

if TYPE_CHECKING:
    from cmig.core.medium_spec import MediumSpec
    from cmig.core.search_product import MultiTargetConfig, SearchConfig

_CONTROL: ContextVar[SearchControl | None] = ContextVar("cmig_search_control", default=None)


@contextmanager
def search_control(control: SearchControl) -> Iterator[None]:
    token = _CONTROL.set(control)
    try:
        yield
    finally:
        _CONTROL.reset(token)


def current_search_control() -> SearchControl | None:
    return _CONTROL.get()


@dataclass(frozen=True)
class SearchRequest:
    taxonomy: Any
    config: SearchConfig | MultiTargetConfig
    medium: MediumSpec | None = None
    strict_medium: bool = True
    exact_medium: bool | None = None


def search_identity(request: SearchRequest) -> dict[str, Any]:
    from cmig.core.medium_spec import requested_medium_application_mode
    from cmig.core.search_ga import GA_POLICY_VERSION
    from cmig.io.solve_output import runtime_versions, taxonomy_model_checksum

    config = asdict(request.config)
    if "direction" in config:
        config["direction"] = config["direction"].value
    if "directions" in config:
        config["directions"] = {key: value.value for key, value in config["directions"].items()}
    return {
        "policy": SEARCH_POLICY_VERSION,
        "ga_policy": GA_POLICY_VERSION,
        "config": config,
        "models": taxonomy_model_checksum(request.taxonomy),
        "medium": asdict(request.medium) if request.medium is not None else None,
        "medium_mode": requested_medium_application_mode(
            has_custom_medium=request.medium is not None
        ),
        "strict_medium": request.strict_medium,
        "versions": runtime_versions(),
    }


class SearchService:
    def run(
        self, request: SearchRequest, *, engine: Any = None, control: SearchControl | None = None
    ) -> Any:
        from cmig.core.medium_spec import cli_exact_medium

        control = control or current_search_control() or SearchControl()
        medium_context = (
            cli_exact_medium(request.exact_medium)
            if request.exact_medium is not None
            else nullcontext()
        )
        with control.session(), medium_context:
            return self._run(request, engine=engine, control=control)

    def _run(self, request: SearchRequest, *, engine: Any, control: SearchControl | None) -> Any:
        from cmig.core.engine import MicomEngine
        from cmig.core.search_product import (
            MultiTargetConfig,
            search_model_pool,
            search_model_pool_multi,
        )

        validate_taxonomy(request.taxonomy)
        if request.config.validation_top < 0:
            raise ValueError("--validate-top must be >= 0")
        control = control or current_search_control()
        if control is not None:
            context = search_identity(request)
            context["solver_threads"] = control.solver_threads
            context["solve_timeout"] = control.solve_timeout
            control.bind(context)
            self.preflight(request, control=control)
        selected: Any = (
            search_model_pool_multi
            if isinstance(request.config, MultiTargetConfig)
            else search_model_pool
        )
        engine = engine if engine is not None else MicomEngine()
        if isinstance(engine, MicomEngine):
            engine.cache_models = True
        result = selected(
            engine,
            request.taxonomy,
            request.config,
            medium_spec=request.medium,
            strict_medium=request.strict_medium,
            **({"control": control} if control is not None else {}),
        )
        if request.config.validation_top:
            from cmig.core.search_validation import validate_top_candidates

            validation_engine = (
                ConfiguredEngine(engine, control.solver_threads, control.solve_timeout)
                if control
                else engine
            )
            result = replace(
                result,
                validation_report=validate_top_candidates(
                    request, result, validation_engine, control
                ),
            )
        totals: dict[str, float] = {}
        rows = list(result.evaluations)
        if control is not None and isinstance(request.config, MultiTargetConfig):
            rows = []
            for record in control.records.values():
                rows.extend(record.get("points") or [])
                if record.get("capability") is not None:
                    rows.append(record["capability"])
        for row in rows:
            for key, value in (
                row.get("timings", {}) if isinstance(row, dict) else getattr(row, "timings", {})
            ).items():
                totals[key] = totals.get(key, 0.0) + value
        for row in result.ranks:
            for key, value in row.timings.items():
                if key.startswith("fva_"):
                    totals[key] = totals.get(key, 0.0) + value
        return replace(
            result,
            profile={
                "completed_evaluation_totals": totals,
                "workers": control.workers if control else 1,
                "scope": "cumulative completed search evaluations; overlapping phase timers; "
                "excludes preflight, publication, interrupted solves and post-validation",
            },
        )

    @staticmethod
    def preflight(request: SearchRequest, *, control: SearchControl | None = None) -> None:
        """Probe a solver once; individual metabolic infeasibility stays per-candidate."""
        from cmig.core.engine import _require_allowed_solver
        from cmig.core.single_model import SingleModelUnavailableError, _require_lp
        from cmig.io.model_import import ModelImportError, load_cobra_model

        _require_allowed_solver(request.config.solver)
        try:
            _require_lp(request.config.solver)
        except SingleModelUnavailableError as error:
            raise ValueError(f"search solver preflight failed: {error}") from error
        if request.config.solver == "gurobi":
            import gurobipy

            try:
                with gurobipy.Env(empty=True) as env:
                    env.setParam("OutputFlag", 0)
                    env.start()
            except gurobipy.GurobiError as error:
                raise ValueError(f"search solver preflight failed: {error}") from error
        # Missing or malformed source files affect every containing combination.
        # Check them once without discarding non-producers or non-viable monocultures.
        for path in dict.fromkeys(str(path) for path in request.taxonomy["file"]):
            if control is not None:
                control.check()
            try:
                load_cobra_model(path)
            except ModelImportError as error:
                raise ValueError(f"search model preflight failed: {error}") from error


_WORKER_ENGINE: Any = None
_WORKER_REQUEST: SearchRequest | None = None


class ConfiguredEngine:
    def __init__(self, engine: Any, threads: int, timeout: float | None) -> None:
        self.engine, self.threads, self.timeout = engine, threads, timeout

    @timed("build")
    def build_community(self, taxonomy: Any, cmig_solver: str = "gurobi") -> Any:
        community = self.engine.build_community(taxonomy, cmig_solver=cmig_solver)
        if cmig_solver == "gurobi":
            community.solver.problem.Params.Threads = self.threads
            community.solver.problem.Params.Seed = 0
        if self.timeout is not None:
            community.solver.configuration.timeout = self.timeout
        return community


def _start_worker(
    request: SearchRequest, threads: int, timeout: float | None, exact_medium: bool
) -> None:
    global _WORKER_ENGINE, _WORKER_REQUEST
    from cmig.core.engine import MicomEngine
    from cmig.core.medium_spec import _CLI_EXACT_MEDIUM

    _CLI_EXACT_MEDIUM.set(exact_medium)
    _WORKER_REQUEST = request
    engine = MicomEngine()
    engine.cache_models = True
    _WORKER_ENGINE = ConfiguredEngine(engine, threads, timeout)


def _evaluate_worker(job: tuple[Any, ...]) -> Any:
    from cmig.core.search import TargetSpec
    from cmig.core.search_product import (
        MultiTargetConfig,
        _evaluate_members,
        _evaluate_members_multi,
        _evaluate_members_multi_joint,
        _pareto_points_for_members,
    )

    assert _WORKER_REQUEST is not None
    request = _WORKER_REQUEST
    members, phase, ranges, known_capability = job
    if isinstance(request.config, MultiTargetConfig):
        config = request.config
        specs = [
            TargetSpec(target, config.directions[target], config.weights[target])
            for target in config.targets
        ]
        notes: set[str] = set()
        common: dict[str, Any] = dict(
            growth_fraction=config.growth_fraction,
            solver=config.solver,
            medium_spec=request.medium,
            strict_medium=request.strict_medium,
            growth_policy=config.growth_policy,
            medium_notes=notes,
        )
        capability = known_capability
        if phase == "capability" or (config.metric == "pareto" and capability is None):
            capability = _evaluate_members_multi(
                _WORKER_ENGINE, request.taxonomy, members, specs, **common
            )
        points = None
        if phase != "capability":
            if config.metric == "pareto":
                points = (
                    _pareto_points_for_members(
                        _WORKER_ENGINE,
                        request.taxonomy,
                        members,
                        specs,
                        capability=capability.signed,
                        resolution=config.pareto_resolution,
                        **common,
                    )
                    if capability.status == "optimal"
                    else [capability]
                )
            else:
                points = [
                    _evaluate_members_multi_joint(
                        _WORKER_ENGINE,
                        request.taxonomy,
                        members,
                        specs,
                        metric=config.metric,
                        normalization_ranges=ranges,
                        **common,
                    )
                ]
        return members, capability, points, notes
    return _evaluate_members(
        _WORKER_ENGINE,
        request.taxonomy,
        members,
        TargetSpec(request.config.target, request.config.direction),
        growth_fraction=request.config.growth_fraction,
        solver=request.config.solver,
        medium_spec=request.medium,
        strict_medium=request.strict_medium,
        growth_policy=request.config.growth_policy,
    )


@contextmanager
def search_workers(request: SearchRequest, control: SearchControl) -> Iterator[Any]:
    from cmig.core.medium_spec import MEDIUM_APPLICATION_EXACT, requested_medium_application_mode

    exact = requested_medium_application_mode(has_custom_medium=True) == MEDIUM_APPLICATION_EXACT
    with ProcessPoolExecutor(
        max_workers=control.workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=_start_worker,
        initargs=(request, control.solver_threads, control.solve_timeout, exact),
    ) as executor:

        def evaluate(
            members: list[tuple[str, ...]],
            *,
            phase: str = "evaluate",
            ranges: Any = None,
            capabilities: Any = None,
        ) -> Iterator[Any]:
            control.check()
            # No queue beyond the active batch. Gather in submission order so solver
            # completion timing cannot alter the GA's RNG or evaluation ledger.
            jobs = [(genome, phase, ranges, (capabilities or {}).get(genome)) for genome in members]
            try:
                # Yield ordered completions immediately so an eventual worker
                # crash cannot discard earlier completed rows in this batch.
                yield from executor.map(_evaluate_worker, jobs)
            except BrokenProcessPool as error:
                raise ValueError(
                    "search worker terminated unexpectedly; check memory and solver resources"
                ) from error

        yield evaluate
