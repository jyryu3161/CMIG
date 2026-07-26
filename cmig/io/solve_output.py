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
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from cmig import CMIG_CORE_VERSION
from cmig.core.golden import DEFAULT_DECIMALS
from cmig.core.interactions import CROSS_FEEDING_ALLOCATION_METHOD
from cmig.core.manifest import RunHashComponents, RunManifest, canonical_json

KNOWN_SOLVE_ARTIFACTS = frozenset({
    "nodes.parquet",
    "edges.parquet",
    "profile.parquet",
    "matrix.parquet",
    "target_summary.json",
})


def prune_stale_artifacts(
    out_dir: str | Path, known: Iterable[str], written: Iterable[str]
) -> list[str]:
    """Remove artifacts a previous run left in ``out_dir`` that this run did not produce.

    An artifact emitted only under some condition (``search_unevaluated.csv`` when candidates
    could not be evaluated, ``matrix.parquet`` when a matrix exists) survives into the next run
    that reuses the same ``--out`` unless somebody deletes it. The result is a directory whose
    manifest describes run 2 while an orphan file from run 1 sits beside it contradicting it —
    R5-P3 CC-3 observed a `search_unevaluated.csv` asserting that the current run's rank-1 member
    was unevaluable.

    ``known`` is the complete set of names the writer may emit; ``written`` is what it actually
    emitted this time. Returns the sorted names removed, so callers can report them.
    """
    out = Path(out_dir)
    removed: list[str] = []
    for name in sorted(set(known) - set(written)):
        stale = out / name
        if stale.exists():
            stale.unlink()
            removed.append(name)
    return removed


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
    decimals: int = DEFAULT_DECIMALS,
) -> RunHashComponents:
    """임의 taxonomy+medium solve → run_hash 11구성요소 (cmig solve 용, 단일 canonical).

    golden_fixture._run_hash_components 와 동일 계약 — fixture 고정값 대신 인자로 받는다.

    ``decimals`` **must equal the precision these components will be hashed at.** abundance 는
    solve 산출값이므로 여기서 잡음을 흡수하지만, hash 가 쓰는 자릿수와 다르게 반올림하면 그
    값이 hash 자릿수 기준 고정점이 아니게 되어 published hash 가 움직인다
    (golden_fixture._run_hash_components 의 osqp 회귀 참조).
    """
    abundance = {
        k: round(v, decimals)
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
            },
            "provenance": provenance or {},
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
        prune_stale_artifacts(out, KNOWN_SOLVE_ARTIFACTS, artifacts)
        for artifact in artifacts:
            os.replace(tmp / artifact, out / artifact)
        os.replace(tmp / "manifest.json", manifest_path)
    return manifest_path
