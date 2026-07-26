"""Round 6 track B — THE generic boundary-isolation invariant, on real genome-scale models.

One property, asserted across five models through the **production** code paths:

    after isolation, no boundary reaction may supply mass except the explicitly declared ones,
    at their declared bounds.

Not per-site spot checks. Each test below is a different way of *reaching*
:func:`cmig.core.boundary.boundary_isolation_violations`; the assertion itself is the same
sentence every time, and none of these tests re-implements the isolation logic they check.

The probe is a spy on ``model.optimize``, because every isolation site does its work inside a
``with model:`` context that restores the bounds on exit — so the only place the invariant can be
observed is with the LP's own bounds in force. That is exactly the probe the round-6 verification
built by hand to find instances 3–5; having it here means it runs on every commit.

Coverage floor: the three bundled microbial GEMs are tracked, so those parametrisations can never
skip. Recon3D and RECON1 are gitignored large binaries and skip when absent — Recon3D is the one
model in the set where the defect has a measured consequence (95 of its 1655 mass-supplying
boundary reactions are sinks or demands and are invisible to ``model.exchanges``), so its skip is
reported by name rather than folded into a count.
"""

from __future__ import annotations

from typing import Any

import pytest
from _gem_fixtures import bundled_model_path, human_gem_path, human_gem_skip_reason

from cmig.core.boundary import (
    boundary_isolation_violations,
    mass_supplying_boundary,
    realised_boundary_suppliers,
)

cobra = pytest.importorskip("cobra")
pytest.importorskip("gurobipy")

#: The declared availability the round-6 verification used, so the numbers are comparable.
#: Every one of these four exchanges exists on all five models (measured).
DECLARED_AVAILABILITY: dict[str, float] = {
    "ac": 2.5, "etoh": 1.75, "fe2": 9.8, "glc__D": 5.0,
}
DECLARED_EXCHANGES: dict[str, float] = {
    f"EX_{metabolite}_e": limit for metabolite, limit in DECLARED_AVAILABILITY.items()
}

#: (label, loader) for every model the invariant is asserted on. Human GEMs resolve to None and
#: skip; bundled microbial GEMs never do.
HUMAN_GEMS = ("Recon3D.xml", "RECON1.xml")
MICROBIAL_GEMS = ("iML1515.xml", "iYO844.xml", "iHN637.xml")
ALL_GEMS = (*HUMAN_GEMS, *MICROBIAL_GEMS)


@pytest.fixture(scope="module")
def gem_cache() -> dict[str, Any]:
    """Load each GEM at most once — Recon3D is 27 MB and takes ~7 s to parse."""
    return {}


def _load(gem_cache: dict[str, Any], name: str) -> Any:
    if name not in gem_cache:
        if name in HUMAN_GEMS:
            path = human_gem_path(name)
            if path is None:
                pytest.skip(human_gem_skip_reason(name))
        else:
            path = bundled_model_path(name)
        gem_cache[name] = cobra.io.read_sbml_model(str(path))
    return gem_cache[name]


def _interface_map(model: Any) -> dict[str, str]:
    """A reviewed interface map for the declared metabolites.

    Supplied explicitly so this test measures *isolation* and not id resolution — the id-case
    mapping divergence has its own regression test. The map is production input, not logic.
    """
    ids = {str(reaction.id) for reaction in model.reactions}
    return {
        metabolite: f"EX_{metabolite}_e"
        for metabolite in DECLARED_AVAILABILITY
        if f"EX_{metabolite}_e" in ids
    }


class _IsolationProbe:
    """Records the invariant at the moment the LP is solved, from inside the isolation context."""

    def __init__(self, model: Any, declared: dict[str, float]) -> None:
        self.model = model
        self.declared = declared
        self.violations: dict[str, float] | None = None
        self.realised: dict[str, float] | None = None
        self.open_suppliers: set[str] | None = None
        self._real = model.optimize

    def __enter__(self) -> _IsolationProbe:
        def spy(*args: Any, **kwargs: Any) -> Any:
            # Self-uninstalling: cobra's FVA ships the model to a ProcessPool, and a closure
            # attached to the instance is unpicklable. Recording once is all the invariant needs —
            # it is a statement about the bounds, and the bounds do not change after this point.
            self.__exit__()
            solution = self._real(*args, **kwargs)
            self.violations = boundary_isolation_violations(self.model, self.declared)
            self.open_suppliers = set(mass_supplying_boundary(self.model))
            self.realised = realised_boundary_suppliers(
                self.model, {str(rid): float(value) for rid, value in solution.fluxes.items()}
            )
            return solution

        self.model.optimize = spy      # instance attribute shadows the bound method
        return self

    def __exit__(self, *exc: Any) -> None:
        try:
            del self.model.optimize
        except AttributeError:          # pragma: no cover - defensive
            pass


# ── the invariant, through the host-coupling isolation path (instance 2) ────────────────────────


@pytest.mark.parametrize("gem", ALL_GEMS)
def test_solve_bigg_host_isolates_the_whole_boundary(gem: str, gem_cache: dict[str, Any]) -> None:
    """``solve_bigg_host(close_unlisted_uptake=True)``: nothing else may feed the host.

    Pre-fix this closed ``host.exchanges`` only. On Recon3D that left 95 sinks/demands at
    ``lower_bound = -1000``, and the published host objective (368.01) was measured to be
    identical with microbial availability zeroed — a number the microbes provably did not affect.
    """
    from cmig.core.host_coupling import solve_bigg_host

    host = _load(gem_cache, gem)
    declared = {
        exchange: limit
        for exchange, limit in DECLARED_EXCHANGES.items()
        if exchange in {str(r.id) for r in host.reactions}
    }
    with _IsolationProbe(host, declared) as probe:
        solve_bigg_host(
            host,
            dict(DECLARED_AVAILABILITY),
            interface_map=_interface_map(host),
            close_unlisted_uptake=True,
            solver="gurobi",
        )

    assert probe.violations == {}, (
        f"{gem}: {len(probe.violations or {})} boundary reactions can still supply mass after "
        f"isolation, e.g. {sorted((probe.violations or {}).items())[:5]}"
    )
    assert probe.open_suppliers == set(declared)
    # Nothing outside the declared set actually fed the LP either.
    assert set(probe.realised or {}) <= set(declared), sorted(
        set(probe.realised or {}) - set(declared)
    )


@pytest.mark.parametrize("gem", ALL_GEMS)
def test_exact_medium_isolates_the_whole_boundary(gem: str, gem_cache: dict[str, Any]) -> None:
    """``apply_medium_translated(exact=True)`` must be genuinely exact (instance 3).

    It delegated to cobra's ``Model.medium`` setter, which does ``frozenset(self.exchanges)`` and
    therefore never closes a sink or a demand. Measured before the fix: declared uptake 1.0,
    achieved growth 1000.0, the sink still at -1000.
    """
    from cmig.core.medium_spec import MediumSpec, apply_medium_translated

    model = _load(gem_cache, gem)
    spec = MediumSpec(uptake=dict(DECLARED_EXCHANGES))
    with model:
        translation = apply_medium_translated(model, spec, strict=False, exact=True)
        declared = dict(translation.spec.uptake)
        assert declared, f"{gem}: no declared exchange matched, the assertion would be vacuous"
        assert boundary_isolation_violations(model, declared) == {}
        assert set(mass_supplying_boundary(model)) == set(declared)


@pytest.mark.parametrize("gem", ALL_GEMS)
def test_boundary_is_never_smaller_than_the_view_the_old_code_used(
    gem: str, gem_cache: dict[str, Any]
) -> None:
    """The measurement that makes the four tests above non-vacuous, model by model."""
    model = _load(gem_cache, gem)
    boundary = {str(r.id) for r in model.boundary}
    exchanges = {str(r.id) for r in model.exchanges}
    medium = set(dict(model.medium))

    assert medium <= exchanges <= boundary
    if gem == "Recon3D.xml":
        # The one model in the set where the difference has a measured scientific consequence.
        assert len(boundary) == 1806
        assert len(exchanges) == 1560
        suppliers = mass_supplying_boundary(model)
        assert len(suppliers) == 1655
        non_exchange = [s for s in suppliers.values() if not s.is_exchange]
        assert len(non_exchange) == 95
        assert {s.capacity for s in non_exchange} == {1000.0}


# ── the opt-out must keep working, and must say what it left open ───────────────────────────────


def test_keep_host_uptake_leaves_the_boundary_open_and_reports_the_count(
    gem_cache: dict[str, Any],
) -> None:
    """``--keep-host-uptake`` is opt-in-to-close, so it must NOT isolate — but must disclose.

    Leaving 1655 mass sources open is a legitimate diagnostic mode. Doing it silently is not.
    """
    from cmig.core.host_coupling import solve_bigg_host

    host = _load(gem_cache, "Recon3D.xml")
    with _IsolationProbe(host, DECLARED_EXCHANGES) as probe:
        result = solve_bigg_host(
            host,
            dict(DECLARED_AVAILABILITY),
            interface_map=_interface_map(host),
            close_unlisted_uptake=False,
            solver="gurobi",
        )

    assert len(probe.open_suppliers or ()) == 1655
    assert result.boundary_isolation is not None
    assert result.boundary_isolation["isolated"] is False
    assert result.boundary_isolation["n_open_suppliers"] == 1655
    assert result.boundary_isolation["n_open_non_exchange_suppliers"] == 95


def test_forced_supply_bounds_are_reported_rather_than_mangled() -> None:
    """iAF987 forces uptake in its SBML, so its background cannot be fully closed.

    ``EX_ac_e [-8.88, -6.84]`` and ``EX_fe3_e [-67.37, -49.21]``: cobra's ``model.medium`` setter
    raises on these. Isolation reports them as irreducible instead, so a caller can see that the
    background is not closed rather than receive a number that pretends it is.
    """
    from cmig.core.boundary import close_boundary_supply

    model = cobra.io.read_sbml_model(str(bundled_model_path("iAF987.xml")))
    with model:
        closure = close_boundary_supply(model)

    assert set(closure.forced_supply) == {"EX_ac_e", "EX_fe3_e"}
    assert closure.forced_supply["EX_ac_e"] == pytest.approx(6.84)
    assert closure.forced_supply["EX_fe3_e"] == pytest.approx(49.21)
    assert closure.complete is False
