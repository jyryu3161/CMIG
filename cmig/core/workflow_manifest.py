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
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cmig import CMIG_CORE_VERSION
from cmig.core.manifest import DEFAULT_FLOAT_DECIMALS, canonicalize_floats
from cmig.core.medium_spec import MEDIUM_POLICY

# 1.1 (R5-P3 CC-4): the float canonicalization changed from "always round to six decimals" to
# "round only when rounding is lossless, otherwise keep the exact value". Under 1.0 a
# growth_fraction of 0.5000001 and one of 0.5000004, a target weight of 1e-7 and one of 4e-7, and
# a solver tolerance of 1.1e-7 and one of 4.4e-7 all produced identical envelope hashes, which
# defeats the manifest's central claim. Envelope hashes computed under 1.0 are therefore NOT
# comparable to hashes computed under 1.1; the version is what makes that visible rather than
# silent. The frozen 11-component solve hash is unaffected — see cmig.core.manifest._round_floats.
WORKFLOW_MANIFEST_SCHEMA_VERSION = "1.1"

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
    "map_spec",                   # host-map matching policy + id-normalization rules
    "bundle_spec",                # the sub-runs a bundling command certifies (kinds + hashes)
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
    # `host-map` does not solve, but it decides the interface map every host run then depends on.
    # What determines that map: the host model bytes, the microbial pool bytes (model_checksum),
    # and the matching/normalization policy (map_spec) — nothing else.
    "host_map": _BASE + ("host_spec", "map_spec"),
    # `publication-benchmark` bundles sub-runs and claims to certify them, so its hash covers both
    # its own arguments and the identity of what it bundled (bundle_spec carries each child's kind
    # and run_hash). A bundle over a different set of runs is a different bundle.
    "publication_benchmark": _BASE + (
        "tradeoff_f", "target_spec", "search_spec", "quality_spec", "dfba_spec",
        "host_spec", "biomass_basis", "bundle_spec",
    ),
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
    "host_map": 8,
    "publication_benchmark": 14,
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


# ── result digest: the answer side of the fingerprint ──────────────────────────
# `run_hash` certifies the *inputs*. That is a claim about what was asked, not about what came
# back, and round-5 verification showed the difference is exploitable: three changes to
# `build_host_map` — capping the reported entries, capping the host index, dropping currency
# metabolites — each rewrote the real interface map (67 entries → 22, → 62) with `run_hash`,
# `map_spec` and the matching-behaviour digest all bit-identical. Certifying an implementation
# from the input side cannot be completed: `map_spec.match_behavior` measures one small synthetic
# instance, so anything keyed on scale or on real BiGG vocabulary is invisible to it, and a fixture
# can only cover decision points somebody has already written.
#
# `result_digest` closes that from the other side by fingerprinting the artifact bytes the run
# actually produced. It is **additive and outside the hash**: no published `run_hash` moves, and
# the envelope golden is untouched. What it buys is that two runs sharing a `run_hash` but
# differing in `result_digest` become *detectable* rather than silently equivalent — which is
# precisely the false negative. `cmig inspect-run` recomputes it from the files on disk and says so
# loudly when they disagree, which also catches an edited or truncated artifact after the fact.
#
# Be precise about what each one certifies:
#   run_hash      — these inputs, under this serialization contract.
#   result_digest — these output bytes.
# Neither implies the other, and that is the point.
RESULT_DIGEST_SCHEMA_VERSION = "1.0"

#: Kinds whose declared artifacts are byte-deterministic for identical inputs, so
#: ``result_digest`` is comparable *across* runs and not merely within one. Verified by running the
#: command twice and diffing (`host_map`: artifacts byte-identical, nothing timestamped). A kind is
#: not listed until that has actually been measured — a kind whose artifacts embed a timestamp, a
#: figure raster or a parquet write id would differ between two identical runs, and claiming
#: comparability for it would manufacture false alarms. Unlisted kinds still get a digest; it
#: certifies *those bytes* and is still checked by `inspect-run`.
DETERMINISTIC_ARTIFACT_KINDS: frozenset[str] = frozenset({"host_map"})


def artifact_result_digest(
    out_dir: str | Path, kind: str, artifacts: list[str] | None
) -> dict[str, Any]:
    """sha256 over the artifact bytes a run produced, plus a per-artifact breakdown.

    A declared artifact that is absent or unreadable is recorded in ``missing_artifacts`` rather
    than skipped: a run that failed to write half its outputs must not digest the same as one that
    wrote them all.
    """
    out = Path(out_dir)
    digests: dict[str, str] = {}
    missing: list[str] = []
    for name in sorted(artifacts or []):
        path = out / name
        try:
            digests[name] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            missing.append(name)
    combined = json.dumps(
        {"artifacts": digests, "missing_artifacts": sorted(missing)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    return {
        "result_digest_schema_version": RESULT_DIGEST_SCHEMA_VERSION,
        "algorithm": "sha256",
        "digest": "sha256:" + hashlib.sha256(combined.encode("utf-8")).hexdigest(),
        "artifacts": digests,
        "missing_artifacts": sorted(missing),
        "cross_run_comparable": kind in DETERMINISTIC_ARTIFACT_KINDS,
    }


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
    #: Outside the hash by construction — see the note above `RESULT_DIGEST_SCHEMA_VERSION`.
    result_digest: dict[str, Any] | None = None

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
            "result_digest": self.result_digest,
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
    result_digest: dict[str, Any] | None = None,
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
        result_digest=result_digest,
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
    """Write ``manifest.json`` for a workflow run and return its run_hash.

    Called after the run's artifacts are on disk, so the result digest fingerprints what this run
    actually produced. `manifest.json` itself is never one of them — it carries the digest.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = build_workflow_manifest(
        kind, components,
        status=status, artifacts=artifacts, diagnostic=diagnostic,
        warnings=warnings, summary=summary,
        result_digest=artifact_result_digest(out, kind, artifacts),
    )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        manifest.to_payload(), indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False
    ) + "\n"
    # R5-P3 (opus F4 / codex F8): `write_text` truncates the destination before it writes, so a
    # failure part-way through replaced the previous run's manifest with unparseable JSON — the
    # run's only reproducibility record, destroyed by a re-run that itself failed. Stage into the
    # same directory (so os.replace stays on one filesystem and is therefore atomic) and swap.
    # This is the pattern io.solve_output already uses for the solve path.
    fd, tmp_name = tempfile.mkstemp(dir=out, prefix=".manifest.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, out / "manifest.json")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
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


def pool_model_checksum(taxonomy: Any, *, base_dir: str | Path | None = None) -> str:
    """Model-bytes + taxonomy-metadata fingerprint for a model pool.

    ``base_dir`` resolves taxonomy ``file`` columns recorded relative to the taxonomy csv, the way
    the commands that load those models already do; without it a relative pool would fingerprint
    as "model file missing" and the manifest would be skipped.
    """
    from cmig.io.solve_output import taxonomy_model_checksum

    return taxonomy_model_checksum(taxonomy, base_dir=base_dir)


def bundle_component(children: list[dict[str, Any]]) -> dict[str, Any]:
    """The sub-runs a bundling command certifies: each child's kind, run_hash and output location.

    **The bundle hash includes the child hashes, deliberately.** A bundle is a claim about a
    specific set of runs, so two bundles assembled from identical arguments but certifying
    different sub-runs are not the same scientific object and must not share a fingerprint.
    Recording only the bundling command's own arguments would let a bundle hash stand for runs it
    never saw. It also gives a reader the inverse direction: from the bundle manifest alone they
    can tell *which* runs were certified and check each child's own ``manifest.json``.

    A child whose manifest could not be written is recorded with ``run_hash: None`` rather than
    dropped — the bundle then hashes differently from one where every child was fingerprinted,
    which is honest: that bundle certifies less.
    """
    normalized = [
        {
            "kind": str(child["kind"]),
            "run_hash": None if child.get("run_hash") is None else str(child["run_hash"]),
            "artifacts_dir": str(child.get("artifacts_dir") or ""),
            "status": str(child.get("status") or "ok"),
        }
        for child in children
    ]
    # Sorted, so the bundle identity is the *set* of certified runs rather than the incidental
    # order the benchmark happened to execute them in.
    normalized.sort(key=lambda item: (item["kind"], item["artifacts_dir"], item["run_hash"] or ""))
    return {
        "bundle_hash_includes_child_hashes": True,
        "n_children": len(normalized),
        "child_kinds": sorted({item["kind"] for item in normalized}),
        "children": normalized,
    }


def optional_file_checksum(path: str | Path | None) -> str | None:
    """sha256 of a file that may not be supplied (interface map, host medium, ...)."""
    if not path:
        return None
    from cmig.io.solve_output import file_checksum

    candidate = Path(path)
    return file_checksum(candidate) if candidate.exists() else f"missing:{candidate}"


def _file_identity(path: str | Path | None) -> str | None:
    """The hashable identity of a supplied file: its name, never the path used to reach it.

    Paired with the checksum recorded beside it — together they say *which file*, without making
    the reader's directory layout part of the scientific fingerprint.
    """
    return Path(path).name if path else None


def host_spec_component(
    *,
    host_model: str | Path | None,
    host_model_checksum: str | None,
    host_objective: str | None = None,
    host_medium: str | Path | None = None,
    host_medium_checksum: str | None = None,
    microbe_medium: str | Path | None = None,
    microbe_medium_checksum: str | None = None,
    interface_map: str | Path | None = None,
    interface_map_checksum: str | None = None,
    exchange_suffix: str | None = None,
    exclude_metabolites: list[str] | None = None,
    include_currency_metabolites: bool = False,
    keep_host_uptake: bool = False,
) -> dict[str, Any]:
    """Everything about the host side that changes the host objective, in one shape.

    One builder rather than a per-command dict literal: `host_spec` is hashed by five kinds now
    (`host_microbe_bigg`, `host_search_bigg`, `host_ko_impact`, `host_map`,
    `publication_benchmark`), and a second literal would eventually disagree with the first about
    which key holds which fact — at which point two runs of the same experiment stop sharing a
    hash for no scientific reason. Keys are fixed and always present; an option a command does not
    expose records as its inert default rather than being dropped.

    **File identity is the bytes, not the location.** Every path recorded here has a checksum
    companion that already pins its content, so the path is provenance. Recording it verbatim made
    the *same file* fingerprint differently depending on where the reader kept it or which
    directory they ran from — round-5 measured `c5a6c402…` from a relative host path and
    `b52137b2…` from the absolute path to the identical bytes, so a faithful reproduction looked
    like a failed one. Only the file name is hashed: enough to keep the manifest readable, stable
    under a move or a change of working directory.
    """
    return {
        "host_model": _file_identity(host_model),
        "host_model_checksum": host_model_checksum,
        "host_objective": host_objective,
        "host_medium": _file_identity(host_medium),
        "host_medium_checksum": host_medium_checksum,
        "microbe_medium": _file_identity(microbe_medium),
        "microbe_medium_checksum": microbe_medium_checksum,
        "interface_map": _file_identity(interface_map),
        "interface_map_checksum": interface_map_checksum,
        "exchange_suffix": exchange_suffix,
        "exclude_metabolites": sorted(exclude_metabolites or []),
        "include_currency_metabolites": bool(include_currency_metabolites),
        "keep_host_uptake": bool(keep_host_uptake),
    }


def mapping_checksum(mapping: dict[str, Any] | None) -> str | None:
    """Deterministic checksum of an in-memory mapping (a loaded interface map)."""
    if mapping is None:
        return None
    payload = json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
