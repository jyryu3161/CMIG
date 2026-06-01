"""C7 — solve 산출 경로: TidyBundle + run_hash → parquet + manifest.json.

Design Ref(foundations): §3 (C7 CLI 산출). Plan SC: SC-F2.

사용자/자동화가 community solve 결과를 소비할 수 있는 산출 경로. **단일 경로 불변**:
run_hash 는 manifest.compute_run_hash(components) 단일 canonical 경유([HASH-SINGLE]) —
자체 hash 재구현 금지. 따라서 산출 manifest 의 run_hash == 라이브러리 경로 run_hash.
"""

from __future__ import annotations

import hashlib
import json
import platform as platform_lib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cmig import CMIG_CORE_VERSION
from cmig.core.golden import DEFAULT_DECIMALS
from cmig.core.manifest import RunHashComponents, RunManifest, canonical_json


def file_checksum(path: str | Path) -> str:
    """파일 바이트의 결정적 체크섬 (model_checksum 등)."""
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()[:24]


def build_run_components(
    result: Any,
    *,
    model_checksum: str,
    medium_checksum: str,
    tradeoff_f: float,
    micom_version: str,
    bounds: dict[str, list[float]] | None = None,
    namespace_decisions: Sequence[str] = (),
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
        solver_setting={"growth_solver": result.growth_solver, "flux_solver": result.flux_solver},
        micom_version=micom_version,
        cmig_core_version=CMIG_CORE_VERSION,
        namespace_mapping_decisions=list(namespace_decisions),
        flux_normalization_method="pfba",
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
) -> Path:
    """tidy bundle(parquet) + manifest.json 산출. manifest 경로 반환.

    parquet: nodes/edges/profile(+matrix). manifest: run_hash(canonical) + components + meta.
    target_summary 제공 시 target_summary.json 산출 + artifacts 반영 (F3).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # parquet — TidyBundle.write (pickle 금지, schema §8.6)
    bundle.write(out)  # type: ignore[attr-defined]

    # AF-1: artifacts 를 실제 산출 파일에서 파생(하드코딩 X) — matrix 등 누락 방지.
    artifacts = ["nodes.parquet", "edges.parquet", "profile.parquet"]
    if getattr(bundle, "matrix", None) is not None:
        artifacts.append("matrix.parquet")
    # F3: target readout 산출(SCFA 등) — manifest artifacts 에 반영.
    if target_summary is not None:
        (out / "target_summary.json").write_text(
            json.dumps(target_summary, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        )
        artifacts.append("target_summary.json")

    platform_info = platform or {
        "os": platform_lib.system().lower(),
        "arch": platform_lib.machine(),
        "python": platform_lib.python_version(),
    }
    manifest = RunManifest(components=components, env_lock=env_lock, platform=platform_info)
    payload = {
        "manifest_schema_version": "1.0",
        "run_hash": manifest.run_hash,                       # compute_run_hash (단일 canonical)
        "float_decimals": manifest.float_decimals,
        # canonical_json 은 비유한 float sentinel·정렬·allow_nan=False (결정적·재현)
        "components": json.loads(canonical_json(components, manifest.float_decimals)),
        "diagnostic": diagnostic,
        "env_lock": env_lock,                                # manifest 만 (run_hash 미포함, §7)
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
        },
        "sweep": sweep,
        "figure_specs": figure_specs or [],
        "platform": manifest.platform,
        "artifacts": artifacts,
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
    )
    return manifest_path
