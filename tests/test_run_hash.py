"""SC-4 run_hash 결정성·캐시 키 — schema §4.2. Plan SC: SC-4."""

import dataclasses
from types import SimpleNamespace

from cmig.core.manifest import (
    RUN_HASH_COMPONENTS,
    RunHashComponents,
    canonical_payload,
    compute_run_hash,
)
from cmig.io.solve_output import build_run_components


def _components(**over):
    base = dict(
        model_checksum="m-abc",
        medium_checksum="med-123",
        member_set=["B", "A", "C"],
        abundance={"A": 0.5, "B": 0.3, "C": 0.2},
        bounds={"EX_glc": [-10.0, 1000.0]},
        tradeoff_f=0.5,
        solver_setting={"growth_solver": "osqp", "flux_solver": "gurobi", "tolerance": 1e-6},
        micom_version="0.33.0",
        cmig_core_version="0.1.0",
        namespace_mapping_decisions=["glc->bigg:glc", "ac->bigg:ac"],
        flux_normalization_method="pfba",
    )
    base.update(over)
    return RunHashComponents(**base)


def test_exactly_eleven_components():
    assert len(RUN_HASH_COMPONENTS) == 11
    assert set(RUN_HASH_COMPONENTS) == {f.name for f in dataclasses.fields(RunHashComponents)}


def test_same_components_same_hash():
    assert compute_run_hash(_components()) == compute_run_hash(_components())


def test_member_set_order_invariant():
    # member_set 정렬 → 순서만 다르면 동일 hash
    h1 = compute_run_hash(_components(member_set=["A", "B", "C"]))
    h2 = compute_run_hash(_components(member_set=["C", "B", "A"]))
    assert h1 == h2


def test_any_component_change_changes_hash():
    base = compute_run_hash(_components())
    assert compute_run_hash(_components(tradeoff_f=0.6)) != base
    assert compute_run_hash(_components(micom_version="0.34.0")) != base
    assert compute_run_hash(_components(bounds={"EX_glc": [-9.0, 1000.0]})) != base
    assert compute_run_hash(_components(flux_normalization_method="fba")) != base


def test_build_run_components_threads_bounds_into_hash():
    result = SimpleNamespace(
        abundances={"A": 1.0},
        members=["A"],
        growth_solver="gurobi",
        flux_solver="gurobi",
    )
    a = build_run_components(
        result,
        model_checksum="m",
        medium_checksum="med",
        tradeoff_f=0.5,
        micom_version="0.39.0",
        bounds={"EX_x": [-1.0, 1000.0]},
    )
    b = build_run_components(
        result,
        model_checksum="m",
        medium_checksum="med",
        tradeoff_f=0.5,
        micom_version="0.39.0",
        bounds={"EX_x": [-2.0, 1000.0]},
    )
    assert compute_run_hash(a) != compute_run_hash(b)


def test_build_run_components_threads_analysis_and_dependency_provenance_into_hash():
    result = SimpleNamespace(
        abundances={"A": 1.0}, members=["A"], growth_solver="gurobi", flux_solver="gurobi"
    )
    common = {
        "model_checksum": "m",
        "medium_checksum": "med",
        "tradeoff_f": 0.5,
        "micom_version": "0.39.0",
    }
    base = build_run_components(
        result,
        **common,
        analysis_settings={"fva": False},
        dependency_versions={"gurobipy": "12.0.0"},
    )
    fva = build_run_components(
        result,
        **common,
        analysis_settings={"fva": True},
        dependency_versions={"gurobipy": "12.0.0"},
    )
    solver_upgrade = build_run_components(
        result,
        **common,
        analysis_settings={"fva": False},
        dependency_versions={"gurobipy": "12.1.0"},
    )
    assert compute_run_hash(base) != compute_run_hash(fva)
    assert compute_run_hash(base) != compute_run_hash(solver_upgrade)


def test_a_determining_input_below_six_decimals_still_changes_the_hash():
    """Contract change, R5-P3 CC-4 (was: "float rounding absorbs noise").

    ``tradeoff_f`` is a user-supplied parameter that determines the answer, not a number that came
    out of a solve, so two different values are two different runs. The old rule mapped *every*
    input below 5e-7 onto 0.0, which meant a solver tolerance of 1e-7 and one of 4e-7 — measurably
    different objectives — shared a run_hash. Alternate-optima noise is still absorbed, but where
    it enters: the callers that build components from a solve result (io.solve_output
    .build_run_components, golden_fixture._run_hash_components, and the CLI's workflow component
    builders) round the solve-derived values before hashing them.
    """
    h1 = compute_run_hash(_components(tradeoff_f=0.5))
    h2 = compute_run_hash(_components(tradeoff_f=0.5 + 1e-9))
    assert h1 != h2
    assert compute_run_hash(_components(tradeoff_f=0.5)) == h1   # still deterministic


def _solve_result(abundances):
    """A minimal stand-in for engine.SolveResult, as build_run_components consumes it."""
    return SimpleNamespace(
        abundances=abundances,
        members=sorted(abundances),
        growth_solver="gurobi",
        flux_solver="gurobi",
        flux_normalization_method="pfba",
    )


def test_solve_derived_values_are_rounded_by_their_builder_not_by_the_hash():
    """The other half of the contract above: noise absorption moved, it did not disappear.

    This must exercise the *builder*. An earlier version of this test rounded both inputs itself
    and never called one, so it would have passed even if every builder's rounding were deleted —
    and the thing it was supposed to guard (a solve-derived value reaching the hash unrounded) is
    exactly the failure mode that later moved the osqp golden hash.
    """
    kwargs = dict(
        model_checksum="m-abc",
        medium_checksum="med-123",
        tradeoff_f=0.5,
        micom_version="0.33.0",
        dependency_versions={"micom": "0.33.0"},
    )
    noisy = build_run_components(_solve_result({"a": 1.0 / 3.0 + 1e-12, "b": 2.0 / 3.0}), **kwargs)
    clean = build_run_components(_solve_result({"a": 1.0 / 3.0, "b": 2.0 / 3.0}), **kwargs)

    # The builder is what absorbs the noise: it hands the hash a six-decimal value.
    assert noisy.abundance == clean.abundance
    assert noisy.abundance["a"] == round(1.0 / 3.0, 6)
    assert compute_run_hash(noisy) == compute_run_hash(clean)

    # And the guard that makes the above meaningful: had the builder NOT rounded, the hash would
    # have separated them — so this test fails if the rounding is removed.
    unrounded_noisy = _components(abundance={"a": 1.0 / 3.0 + 1e-12, "b": 2.0 / 3.0})
    unrounded_clean = _components(abundance={"a": 1.0 / 3.0, "b": 2.0 / 3.0})
    assert compute_run_hash(unrounded_noisy) != compute_run_hash(unrounded_clean)


def test_builder_rounds_at_the_decimals_it_is_asked_to_hash_at():
    """The osqp regression, in unit form.

    A builder that pre-rounds at a *different* precision than the hash uses produces a value that
    is not a fixed point at the hash's decimals, so it takes the lossless branch and moves the
    published hash. The builder must therefore round at the decimals it will be hashed at.
    """
    result = _solve_result({"a": 1.0 / 3.0, "b": 2.0 / 3.0})
    for decimals in (2, 4, 6):
        components = build_run_components(
            result,
            model_checksum="m",
            medium_checksum="d",
            tradeoff_f=0.5,
            micom_version="0.33.0",
            dependency_versions={},
            decimals=decimals,
        )
        for member, value in components.abundance.items():
            assert round(value, decimals) == value, (
                f"abundance[{member}]={value!r} is not a fixed point at decimals={decimals}"
            )


def test_env_lock_not_in_payload():
    payload = canonical_payload(_components())
    assert "env_lock" not in payload
    assert set(payload.keys()) == set(RUN_HASH_COMPONENTS)


def test_non_finite_floats_deterministic():
    """I-6: bounds 의 ±inf/NaN 가 결정적 sentinel 로 직렬화(NaN≠NaN·Infinity 비결정성 제거)."""
    import math

    def inf_b():
        return _components(bounds={"EX_x": [-math.inf, math.inf]})

    def nan_b():
        return _components(bounds={"EX_x": [math.nan, 1.0]})

    # 예외 없이 결정적 hash 산출 + 동일 입력 동일 hash
    assert compute_run_hash(inf_b()) == compute_run_hash(inf_b())
    assert compute_run_hash(nan_b()) == compute_run_hash(nan_b())
    # inf != finite
    assert compute_run_hash(inf_b()) != compute_run_hash(_components(bounds={"EX_x": [-1.0, 1.0]}))


def test_round_floats_normalizes_negative_zero():
    """C4: round(-1e-9, 6) == -0.0 must normalize to +0.0 so a near-zero flux cannot diverge a
    run_hash depending on the sign of its rounded zero."""
    import math

    from cmig.core.manifest import _round_floats

    # R5-P3 CC-4 narrowed this: the guarantee is about *signed zero*, which is what could make one
    # value serialize two ways. -1e-9 is no longer collapsed onto zero at all (it is a distinct
    # value, and collapsing it is exactly the collision CC-4 removed), so the probe is -0.0 itself.
    nz = _round_floats(-0.0, 6)
    assert nz == 0.0
    assert math.copysign(1.0, nz) == 1.0  # +0.0, not -0.0
    # normal values are untouched by the `+ 0.0` normalization
    assert _round_floats(1.234567, 6) == 1.234567
    assert _round_floats(-2.5, 6) == -2.5
    # a structure containing -0.0 hashes identically to one containing +0.0
    a = _components(bounds={"EX_x": [-0.0, 1.0]})
    b = _components(bounds={"EX_x": [0.0, 1.0]})
    assert compute_run_hash(a) == compute_run_hash(b)
    # and a genuinely different near-zero bound is now distinguishable
    assert compute_run_hash(_components(bounds={"EX_x": [-1e-9, 1.0]})) != compute_run_hash(b)


def test_golden_round_normalizes_negative_zero():
    """C4: golden._round mirrors manifest — signed-zero noise must not diverge the golden hash."""
    import math

    from cmig.core.golden import _round

    nz = _round(-1e-9, 6)
    assert nz == 0.0
    assert math.copysign(1.0, nz) == 1.0
    assert _round(1.234567, 6) == 1.234567
