"""Workflow-level reproducibility envelope — manifest.json + run_hash for every science command.

Design Ref: §4.3 [HASH-11 · HASH-SINGLE]. Closes the round-2 reproducibility gap (R2-C F6): only
`solve`/`solve-fixture` emitted a manifest, so a published `search`, `host-*`, `gene-ko-search`,
`strain-growth`, `abundance-impact`, `sweep`, `dfba` or `model-quality` result could not be
re-derived — the parameters that *determine* the answer (growth_fraction, solver, medium,
tradeoff_f, seed, strategy, target/direction, KO spec, host model + interface map + biomass basis,
versions) were recorded nowhere.

**This is an envelope, not an extension.** `manifest.RUN_HASH_COMPONENTS` is a frozen 11-component
contract that `golden verify` (SC-5) and the sweep run-hash cache depend on; it is not touched.
Where a community solve happens inside a workflow, its existing 11-component run_hash is embedded
here as the single ``solve_run_hash`` component — never recomputed ([HASH-SINGLE]).

Two properties the per-kind tuples below are designed to enforce:

1. **Declared order is part of the hash.** Components serialize as an ordered list of
   ``[name, value]`` pairs, not as a dict, so reordering a tuple changes every hash of that kind.
   Combined with the per-kind assertions, editing a component set is necessarily a deliberate act.
2. **Nothing determining the answer is optional.** A kind's tuple is the complete list of inputs
   that change its result; a caller that omits one gets a KeyError, not a silently weaker hash.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cmig import CMIG_CORE_VERSION
from cmig.core.manifest import DEFAULT_FLOAT_DECIMALS, canonicalize_floats
from cmig.core.medium_spec import MEDIUM_POLICY

WORKFLOW_MANIFEST_SCHEMA_VERSION = "1.0"

# ── component vocabulary ───────────────────────────────────────────────────────
# Every name a per-kind tuple may use. Declared once so a typo in a kind tuple fails at import
# rather than silently dropping a determining parameter out of the hash.
WORKFLOW_COMPONENT_VOCABULARY: frozenset[str] = frozenset({
    "workflow_kind",              # which analysis produced this
    "cmig_core_version",
    "dependency_versions",        # micom / cobra / optlang / gurobipy / osqp / pandas / pyarrow
    "solver_setting",             # solver name + solver-level knobs
    "model_checksum",             # taxonomy model bytes + per-member taxonomy metadata
    "medium",                     # medium checksum + namespace-bridge decisions
    "abundances",
    "tradeoff_f",
    "growth_fraction",
    "target_spec",                # target(s) / preset / direction / multi-metric / weights
    "search_spec",                # min/max size, strategy, seed, top_k, n_samples, robustness
    "knockout_spec",              # ko level, member, gene/reaction list, selection, seed, cap
    "host_spec",                  # host model + interface map + objective + exchange handling
    "biomass_basis",              # kind + source + gDW bases
    "flux_normalization_method",  # the normalization ACTUALLY used, not the one intended
    "solve_run_hash",             # embedded 11-component solve hash ([HASH-SINGLE])
    "sweep_spec",
    "dfba_spec",
    "quality_spec",
})

# Shared prefix. Spelled out here once; each kind still declares its full tuple below and asserts
# its own length, so adding or dropping a component is never accidental.
_BASE: tuple[str, ...] = (
    "workflow_kind",
    "cmig_core_version",
    "dependency_versions",
    "solver_setting",
    "model_checksum",
    "medium",
)

# ── per-kind ordered component tuples ──────────────────────────────────────────
WORKFLOW_HASH_COMPONENTS: dict[str, tuple[str, ...]] = {
    "model_pool_search": _BASE + ("target_spec", "search_spec", "growth_fraction"),
    "multi_target_model_pool_search": _BASE + ("target_spec", "search_spec", "growth_fraction"),
    "strain_growth": _BASE + (
        "abundances", "tradeoff_f", "flux_normalization_method", "solve_run_hash",
    ),
    "abundance_impact": _BASE + (
        "abundances", "tradeoff_f", "target_spec", "sweep_spec", "flux_normalization_method",
    ),
    "gene_ko_search": _BASE + (
        "target_spec", "search_spec", "growth_fraction", "knockout_spec",
    ),
    "host_microbe_bigg": _BASE + (
        "abundances", "tradeoff_f", "host_spec", "biomass_basis",
        "flux_normalization_method", "solve_run_hash",
    ),
    "host_search_bigg": _BASE + (
        "tradeoff_f", "target_spec", "search_spec", "host_spec", "biomass_basis",
    ),
    "host_ko_impact": _BASE + (
        "abundances", "tradeoff_f", "target_spec", "knockout_spec", "host_spec", "biomass_basis",
    ),
    "sweep": _BASE + ("tradeoff_f", "sweep_spec"),
    "dfba": _BASE + ("dfba_spec",),
    "model_quality": _BASE + ("quality_spec",),
}

# Per-kind arity assertions. Each number is the deliberate size of that kind's contract; changing a
# tuple without changing its number fails at import, which is the point.
_EXPECTED_ARITY: dict[str, int] = {
    "model_pool_search": 9,
    "multi_target_model_pool_search": 9,
    "strain_growth": 10,
    "abundance_impact": 11,
    "gene_ko_search": 10,
    "host_microbe_bigg": 12,
    "host_search_bigg": 11,
    "host_ko_impact": 12,
    "sweep": 8,
    "dfba": 7,
    "model_quality": 7,
}

assert set(_EXPECTED_ARITY) == set(WORKFLOW_HASH_COMPONENTS), (
    "every workflow kind must declare its expected arity"
)
for _kind, _components in WORKFLOW_HASH_COMPONENTS.items():
    assert len(_components) == _EXPECTED_ARITY[_kind], (
        f"workflow kind {_kind!r} declares {len(_components)} components, "
        f"expected {_EXPECTED_ARITY[_kind]} — editing a component set must be deliberate"
    )
    assert len(set(_components)) == len(_components), f"{_kind!r} repeats a component"
    assert set(_components) <= WORKFLOW_COMPONENT_VOCABULARY, (
        f"{_kind!r} uses components outside the declared vocabulary: "
        f"{sorted(set(_components) - WORKFLOW_COMPONENT_VOCABULARY)}"
    )
    assert _components[0] == "workflow_kind", (
        f"{_kind!r} must lead with workflow_kind so two kinds can never collide on one hash"
    )
del _kind, _components


class WorkflowManifestError(ValueError):
    """A workflow manifest could not be built from the supplied components."""


def workflow_components_for(kind: str) -> tuple[str, ...]:
    """Ordered component names for ``kind``. Unknown kind is an error, not a silent empty hash."""
    try:
        return WORKFLOW_HASH_COMPONENTS[kind]
    except KeyError:
        raise WorkflowManifestError(
            f"unknown workflow kind: {kind!r} (declared: {sorted(WORKFLOW_HASH_COMPONENTS)})"
        ) from None


def canonical_workflow_payload(
    kind: str, components: dict[str, Any], *, decimals: int = DEFAULT_FLOAT_DECIMALS
) -> list[list[Any]]:
    """(kind, components) → ordered ``[[name, value], ...]`` with floats normalized.

    An ordered pair-list rather than a dict, so the declared order in
    :data:`WORKFLOW_HASH_COMPONENTS` is itself part of the hash.
    """
    names = workflow_components_for(kind)
    supplied = dict(components)
    supplied.setdefault("workflow_kind", kind)
    if supplied.get("workflow_kind") != kind:
        raise WorkflowManifestError(
            f"workflow_kind component {supplied.get('workflow_kind')!r} != manifest kind {kind!r}"
        )
    missing = [name for name in names if name not in supplied]
    if missing:
        raise WorkflowManifestError(
            f"workflow kind {kind!r} is missing determining components: {missing}"
        )
    extra = sorted(set(supplied) - set(names))
    if extra:
        raise WorkflowManifestError(
            f"workflow kind {kind!r} received components outside its contract: {extra}"
        )
    return [[name, canonicalize_floats(supplied[name], decimals)] for name in names]


def canonical_workflow_json(
    kind: str, components: dict[str, Any], *, decimals: int = DEFAULT_FLOAT_DECIMALS
) -> str:
    """Canonical serialization: sorted keys inside each value, fixed separators, no NaN."""
    return json.dumps(
        canonical_workflow_payload(kind, components, decimals=decimals),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def compute_workflow_hash(
    kind: str, components: dict[str, Any], *, decimals: int = DEFAULT_FLOAT_DECIMALS
) -> str:
    """workflow run_hash = SHA-256(canonical_workflow_json). Identical inputs → identical hash."""
    return hashlib.sha256(
        canonical_workflow_json(kind, components, decimals=decimals).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class WorkflowManifest:
    """Workflow manifest. ``env_lock`` is recorded but excluded from the hash [HASH-ENVLOCK]."""

    kind: str
    components: dict[str, Any]
    status: str = "ok"
    artifacts: list[str] = field(default_factory=list)
    diagnostic: str | None = None
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    env_lock: str | None = None
    platform: dict[str, str] = field(default_factory=dict)
    float_decimals: int = DEFAULT_FLOAT_DECIMALS

    @property
    def run_hash(self) -> str:
        return compute_workflow_hash(self.kind, self.components, decimals=self.float_decimals)

    def to_payload(self) -> dict[str, Any]:
        return {
            "manifest_schema_version": WORKFLOW_MANIFEST_SCHEMA_VERSION,
            "manifest_scope": "workflow",
            "workflow_kind": self.kind,
            "run_hash": self.run_hash,
            "float_decimals": self.float_decimals,
            "hash_components": list(workflow_components_for(self.kind)),
            "components": canonical_workflow_payload(
                self.kind, self.components, decimals=self.float_decimals
            ),
            # NOT a hash component, deliberately (round 5, blocker 5). The CC-11 fix changed what
            # a `--medium` run computes without moving `run_hash` (measured: solve growth
            # 0.881561 -> 1.125065 under an identical hash), and the discontinuity cannot be
            # recorded in a component because `cmig_core_version` is frozen. This marker lets a
            # consumer tell the two eras apart mechanically. `hash_components` above is the
            # authority on what is hashed, so adding a payload key here cannot move a run_hash.
            "medium_policy": MEDIUM_POLICY,
            "status": self.status,
            "diagnostic": self.diagnostic,
            "warnings": list(self.warnings),
            "summary": self.summary,
            "env_lock": self.env_lock,
            "platform": self.platform,
            "artifacts": sorted(self.artifacts),
        }


def _env_lock(dependency_versions: dict[str, str]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(dependency_versions, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_workflow_manifest(
    kind: str,
    components: dict[str, Any],
    *,
    status: str = "ok",
    artifacts: list[str] | None = None,
    diagnostic: str | None = None,
    warnings: list[str] | None = None,
    summary: dict[str, Any] | None = None,
) -> WorkflowManifest:
    """Assemble a manifest, deriving env_lock and platform from the running interpreter."""
    import platform as platform_lib

    dependencies = components.get("dependency_versions") or {}
    return WorkflowManifest(
        kind=kind,
        components=components,
        status=status,
        artifacts=list(artifacts or []),
        diagnostic=diagnostic,
        warnings=list(warnings or []),
        summary=summary or {},
        env_lock=_env_lock(dependencies if isinstance(dependencies, dict) else {}),
        platform={
            "os": platform_lib.system().lower(),
            "arch": platform_lib.machine(),
            "python": platform_lib.python_version(),
        },
    )


def write_workflow_manifest(
    out_dir: str | Path,
    kind: str,
    components: dict[str, Any],
    *,
    status: str = "ok",
    artifacts: list[str] | None = None,
    diagnostic: str | None = None,
    warnings: list[str] | None = None,
    summary: dict[str, Any] | None = None,
) -> str:
    """Write ``manifest.json`` for a workflow run and return its run_hash."""
    manifest = build_workflow_manifest(
        kind, components,
        status=status, artifacts=artifacts, diagnostic=diagnostic,
        warnings=warnings, summary=summary,
    )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(
        json.dumps(
            manifest.to_payload(), indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False
        )
        + "\n"
    )
    return manifest.run_hash


# ── component builders ─────────────────────────────────────────────────────────
# Shared so every command records the same things the same way; a per-command dict literal would
# drift and re-open exactly the gap this module closes.


def base_components(
    kind: str,
    *,
    solver_setting: dict[str, Any],
    model_checksum: str,
    medium: dict[str, Any],
    dependency_versions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The six components every workflow kind records."""
    from cmig.io.solve_output import runtime_versions

    return {
        "workflow_kind": kind,
        "cmig_core_version": CMIG_CORE_VERSION,
        "dependency_versions": dependency_versions or runtime_versions(),
        "solver_setting": solver_setting,
        "model_checksum": model_checksum,
        "medium": medium,
    }


def medium_component(
    medium_path: str | None,
    medium_checksum: str,
    *,
    namespace_bridge: dict[str, Any] | None = None,
    allow_unknown: bool = False,
) -> dict[str, Any]:
    """Medium identity + the namespace-bridge decisions that changed what was actually applied.

    Phase 3 made `strain-growth` translate media across the `_m`/`_e` exchange namespaces; which
    metabolites were bridged, and which a member could not be offered at all, changes the numbers,
    so it belongs in the hash rather than only in the summary.
    """
    return {
        "source": str(medium_path) if medium_path else None,
        "checksum": medium_checksum,
        "allow_unknown_medium": bool(allow_unknown),
        "namespace_bridge": namespace_bridge or {},
    }


def pool_model_checksum(taxonomy: Any) -> str:
    """Model-bytes + taxonomy-metadata fingerprint for a model pool."""
    from cmig.io.solve_output import taxonomy_model_checksum

    return taxonomy_model_checksum(taxonomy)


def optional_file_checksum(path: str | Path | None) -> str | None:
    """sha256 of a file that may not be supplied (interface map, host medium, ...)."""
    if not path:
        return None
    from cmig.io.solve_output import file_checksum

    candidate = Path(path)
    return file_checksum(candidate) if candidate.exists() else f"missing:{candidate}"


def mapping_checksum(mapping: dict[str, Any] | None) -> str | None:
    """Deterministic checksum of an in-memory mapping (a loaded interface map)."""
    if mapping is None:
        return None
    payload = json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
