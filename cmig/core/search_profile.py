"""Context-local phase timings; telemetry never participates in ranking or RNG state."""

from __future__ import annotations

import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import replace
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

P = ParamSpec("P")
T = TypeVar("T")
_TIMINGS: ContextVar[dict[str, float] | None] = ContextVar("cmig_search_timings", default=None)


def timed(phase: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def decorate(function: Callable[P, T]) -> Callable[P, T]:
        @wraps(function)
        def run(*args: P.args, **kwargs: P.kwargs) -> T:
            start = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                timings = _TIMINGS.get()
                if timings is not None:
                    timings[phase + "_seconds"] = (
                        timings.get(phase + "_seconds", 0.0) + time.perf_counter() - start
                    )
                    timings[phase + "_calls"] = timings.get(phase + "_calls", 0.0) + 1

        return run

    return decorate


def profile_evaluation(function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def run(*args: P.args, **kwargs: P.kwargs) -> T:
        timings: dict[str, float] = {}
        token = _TIMINGS.set(timings)
        start = time.perf_counter()
        try:
            value: Any = function(*args, **kwargs)
            timings["evaluation_seconds"] = time.perf_counter() - start
            if isinstance(value, list):
                # A Pareto solve creates many points. Charge the solve only once.
                if value:
                    value = [replace(value[0], timings=timings), *value[1:]]
            else:
                combined = dict(getattr(value, "timings", {}))
                for key, amount in timings.items():
                    combined[key] = combined.get(key, 0.0) + amount
                value = replace(value, timings=combined)
            return cast(T, value)
        finally:
            _TIMINGS.reset(token)

    return run
