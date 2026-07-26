"""C7 — solve 산출 경로: TidyBundle + run_hash → parquet + manifest.json.

Design Ref(foundations): §3 (C7 CLI 산출). Plan SC: SC-F2.

사용자/자동화가 community solve 결과를 소비할 수 있는 산출 경로. **단일 경로 불변**:
run_hash 는 manifest.compute_run_hash(components) 단일 canonical 경유([HASH-SINGLE]) —
자체 hash 재구현 금지. 따라서 산출 manifest 의 run_hash == 라이브러리 경로 run_hash.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import platform as platform_lib
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cmig import CMIG_CORE_VERSION
from cmig.core.golden import DEFAULT_DECIMALS
from cmig.core.interactions import CROSS_FEEDING_ALLOCATION_METHOD
from cmig.core.manifest import RunHashComponents, RunManifest, canonical_json
from cmig.core.medium_spec import MEDIUM_POLICY

KNOWN_SOLVE_ARTIFACTS = frozenset({
    "nodes.parquet",
    "edges.parquet",
    "profile.parquet",
    "matrix.parquet",
    "target_summary.json",
})


def file_checksum(path: str | Path) -> str:
    """파일 바이트의 결정적 체크섬 (model_checksum 등)."""
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def taxonomy_model_checksum(taxonomy: Any, *, base_dir: str | Path | None = None) -> str:
    """Fingerprint model bytes and solve-relevant taxonomy metadata."""
    root = None if base_dir is None else Path(base_dir)
    rows: list[dict[str, Any]] = []
    for record in taxonomy.to_dict("records"):
        raw_path = Path(str(record["file"]))
        model_path = raw_path
        if not model_path.exists() and not model_path.is_absolute() and root is not None:
            model_path = root / raw_path
        if not model_path.exists():
            raise ValueError(f"taxonomy model 파일 없음: {raw_path}")
        metadata: dict[str, Any] = {}
        for key, raw in sorted(record.items()):
            if key == "file":
                continue
            value = raw.item() if hasattr(raw, "item") else raw
            if isinstance(value, float) and math.isnan(value):
                value = None
            if not isinstance(value, (str, int, float, bool, type(None))):
                value = str(value)
            metadata[str(key)] = value
        rows.append({
            "id": str(record["id"]),
            "file_checksum": file_checksum(model_path),
            "taxonomy_metadata": metadata,
        })
    payload = json.dumps(
        sorted(rows, key=lambda row: row["id"]),
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def runtime_versions() -> dict[str, str]:
    """재현성에 필요한 런타임 패키지 버전을 설치 metadata에서 수집한다."""
    versions: dict[str, str] = {}
    for distribution in (
        "cmig", "cobra", "micom", "optlang", "gurobipy", "osqp", "pandas", "pyarrow"
    ):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "not-installed"
    return versions


def build_run_components(
    result: Any,
    *,
    model_checksum: str,
    medium_checksum: str,
    tradeoff_f: float,
    micom_version: str,
    bounds: dict[str, list[float]] | None = None,
    namespace_decisions: Sequence[str] = (),
    analysis_settings: dict[str, Any] | None = None,
    dependency_versions: dict[str, str] | None = None,
) -> RunHashComponents:
    """임의 taxonomy+medium solve → run_hash 11구성요소 (cmig solve 용, 단일 canonical).

    golden_fixture._run_hash_components 와 동일 계약 — fixture 고정값 대신 인자로 받는다.
    """
    abundance = {
        k: round(v, DEFAULT_DECIMALS)
        for k, v in sorted(result.abundances.items())
        if v is not None
    }
    return RunHashComponents(
        model_checksum=model_checksum,
        medium_checksum=medium_checksum,
        member_set=sorted(result.members),
        abundance=abundance,
        bounds=bounds or {},
        tradeoff_f=tradeoff_f,
        solver_setting={
            "growth_solver": result.growth_solver,
            "flux_solver": result.flux_solver,
            "dependency_versions": dependency_versions or runtime_versions(),
            "analysis_settings": analysis_settings or {},
        },
        micom_version=micom_version,
        cmig_core_version=CMIG_CORE_VERSION,
        namespace_mapping_decisions=list(namespace_decisions),
        # B1: pFBA stage 가 실패해 non-parsimonious 로 강등된 solve 를 manifest 가 "pfba" 라고
        # 주장하지 않도록 결과가 들고 온 실제 정규화 방식을 기록한다(run_hash 도 이에 따라 달라짐).
        flux_normalization_method=getattr(result, "flux_normalization_method", "pfba"),
    )


def write_solve_output(
    bundle: object,
    components: RunHashComponents,
    out_dir: str | Path,
    *,
    diagnostic: str | None = None,
    env_lock: str | None = None,
    platform: dict[str, str] | None = None,
    target_summary: list[dict[str, Any]] | None = None,
    sweep: dict[str, Any] | None = None,
    figure_specs: list[dict[str, Any]] | None = None,
    flux_report_status: str | None = None,
    provenance: dict[str, Any] | None = None,
) -> Path:
    """tidy bundle(parquet) + manifest.json 산출. manifest 경로 반환.

    parquet: nodes/edges/profile(+matrix). manifest: run_hash(canonical) + components + meta.
    target_summary 제공 시 target_summary.json 산출 + artifacts 반영 (F3).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tmp_parent = out.parent
    tmp_parent.mkdir(parents=True, exist_ok=True)
    tmp_prefix = f".{out.name}.tmp-"
    manifest_path = out / "manifest.json"

    with tempfile.TemporaryDirectory(prefix=tmp_prefix, dir=tmp_parent) as td:
        tmp = Path(td)
        # parquet — TidyBundle.write (pickle 금지, schema §8.6)
        bundle.write(tmp)  # type: ignore[attr-defined]

        # AF-1: artifacts 를 실제 산출 파일에서 파생(하드코딩 X) — matrix 등 누락 방지.
        artifacts = ["nodes.parquet", "edges.parquet", "profile.parquet"]
        if getattr(bundle, "matrix", None) is not None:
            artifacts.append("matrix.parquet")
        # F3: target readout 산출(SCFA 등) — manifest artifacts 에 반영.
        if target_summary is not None:
            (tmp / "target_summary.json").write_text(
                json.dumps(
                    target_summary, indent=2, sort_keys=True, ensure_ascii=True,
                    allow_nan=False,
                )
            )
            artifacts.append("target_summary.json")

        platform_info = platform or {
            "os": platform_lib.system().lower(),
            "arch": platform_lib.machine(),
            "python": platform_lib.python_version(),
        }
        dependencies = runtime_versions()
        resolved_env_lock = env_lock or (
            "sha256:"
            + hashlib.sha256(
                json.dumps(dependencies, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
        )
        manifest = RunManifest(
            components=components, env_lock=resolved_env_lock, platform=platform_info
        )
        payload = {
            "manifest_schema_version": "2.0",
            "run_hash": manifest.run_hash,                       # compute_run_hash
            "float_decimals": manifest.float_decimals,
            # canonical_json 은 비유한 float sentinel·정렬·allow_nan=False (결정적·재현)
            "components": json.loads(canonical_json(components, manifest.float_decimals)),
            "diagnostic": diagnostic,
            "env_lock": resolved_env_lock,                       # manifest 만 (§7)
            "inputs": {
                "model_checksum": components.model_checksum,
                "medium_checksum": components.medium_checksum,
                "member_set": components.member_set,
                "abundance": components.abundance,
                "bounds": components.bounds,
                "namespace_mapping_decisions": components.namespace_mapping_decisions,
            },
            "solver": {
                **components.solver_setting,
                "flux_report_status": flux_report_status,
            },
            "software": {
                "cmig_core_version": components.cmig_core_version,
                "micom_version": components.micom_version,
                "dependency_versions": dependencies,
            },
            # A-B15 / B-D6: the cross-feeding attribution method was documented only in source.
            # A published edge weight must carry how it was derived.
            "edge_attribution": {
                "cross_feeding_allocation_method": CROSS_FEEDING_ALLOCATION_METHOD,
                "cross_feeding_identifiable": False,
                "note": (
                    "a steady-state shared pool does not identify pairwise donor->recipient "
                    "transfer; cross_feeding weights are a mass-conserving proportional "
                    "allocation, not a measurement"
                ),
                # Round-5 opus F3 / codex F2: `edges.weight` is the raw micom member exchange,
                # which is a PER-TAXON rate, while `profile.net_flux` in the same run directory is
                # a COMMUNITY-level rate. Two units lived in one run with nothing distinguishing
                # them, so a rare member's edge looks larger than an abundant member's (measured:
                # 84.57 at abundance 0.1 vs 12.29 at abundance 0.9 for the same CO2 edge). The
                # value is not changed here — that requires re-blessing the frozen golden
                # edges.parquet — but the basis is now stated so it cannot be misread.
                #
                # The identity below is stated in full because a shorter phrasing was read two
                # different ways by two reviewers. `weight` is a MAGNITUDE (>= 0): its direction
                # lives in `edge_type` and in the source/target ordering, so a naive
                # sum(abundance * weight) does NOT reconstruct the net exchange (measured on a
                # 0.25/0.75 pair: naive 1.25 vs true 0.75). Restoring the sign from `edge_type`
                # and excluding the allocated cross_feeding rows does (0.75 == 0.75).
                "weight_unit": "mmol gDW_taxon^-1 h^-1 (PER-TAXON; multiply by the member's "
                               "abundance for a community-basis rate)",
                "weight_basis": "per_taxon_unweighted",
                "weight_is_magnitude": True,
                "weight_basis_note": (
                    "edges.weight is NOT comparable to profile.net_flux, which is community-basis "
                    "(mmol gDW_community^-1 h^-1). Reconstruction, per metabolite: take only "
                    "edge_type in {secretion, uptake} (cross_feeding rows are an allocation, not "
                    "a measured exchange, and must be excluded); give each row the sign of its "
                    "direction (+ for secretion, - for uptake); multiply each by the abundance of "
                    "the member endpoint; the sum equals that metabolite's profile.net_flux. "
                    "Summing the unsigned weights, or including cross_feeding, does NOT."
                ),
            },
            # NOT hashed (round 5, blocker 5): marks which medium semantics produced this run.
            # Stamped by the writer, not the caller, so no solve path can omit it.
            "provenance": {"medium_policy": MEDIUM_POLICY, **(provenance or {})},
            "sweep": sweep,
            "figure_specs": figure_specs or [],
            "platform": manifest.platform,
            "artifacts": artifacts,
        }
        (tmp / "manifest.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        )

        # manifest.json is the commit marker. Remove any stale marker before publishing artifacts.
        if manifest_path.exists():
            manifest_path.unlink()
        for stale in KNOWN_SOLVE_ARTIFACTS - set(artifacts):
            stale_path = out / stale
            if stale_path.exists():
                stale_path.unlink()
        for artifact in artifacts:
            os.replace(tmp / artifact, out / artifact)
        os.replace(tmp / "manifest.json", manifest_path)
    return manifest_path
