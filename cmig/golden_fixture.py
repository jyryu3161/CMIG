"""Golden fixture 빌더/캡처 — community_3_member.

Design Ref: §16 / schema §7.4 / Plan SC: SC-1·SC-5·SC-6.

MICOM 번들 test 모델에서 3-member community 를 구성해 solver별 golden 을 캡처/검증한다.
solver 변형 2종: gurobi(기본·full)·osqp(qp_only_approximate).
float 컬럼은 hash 전 rounding (golden.DEFAULT_DECIMALS).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from cmig import CMIG_CORE_VERSION
from cmig.core.engine import MicomEngine, SolveResult
from cmig.core.golden import DEFAULT_DECIMALS, bundle_hashes
from cmig.core.interactions import build_tidy
from cmig.core.manifest import RunHashComponents, compute_run_hash
from cmig.core.tidy import TidyBundle
from cmig.io.atomic import atomic_write_parquet

SOLVER_VARIANTS = ("gurobi", "osqp")
TRADEOFF_F = 0.5
N_MEMBERS = 3
FIXTURE_DIR = Path("fixtures/community_3_member")

# OD-12·OD-50 (Resolved in Do/2b): per-variant golden float tolerance.
# Gurobi 는 cross-process 결정적(jitter 0) → 6 decimal.
# OSQP 계열은 1차(iterative) → cross-process growth jitter ~6.3e-6, edge ~3.4e-6
# 측정값. 5e-5 half-step 으로 안전 흡수하도록 4 decimal.
VARIANT_DECIMALS: dict[str, int] = {
    "gurobi": 6,
    "osqp": 4,
}
# 무라이선스/cross-solver(SC-6) 비교는 공통 coarse tolerance 사용.
CROSS_SOLVER_DECIMALS = 4


def build_taxonomy() -> object:
    """MICOM 번들 test_taxonomy 의 앞 3 멤버 (결정적)."""
    from micom.data import test_taxonomy

    return test_taxonomy().iloc[:N_MEMBERS].copy()


def solve_with_community(cmig_solver: str) -> tuple[SolveResult, TidyBundle, object]:
    """3-member solve → (result, tidy, community). community FVA(F2) 에 community 필요."""
    engine = MicomEngine()
    taxonomy = build_taxonomy()
    community = engine.build_community(taxonomy, cmig_solver=cmig_solver)
    result = engine.cooperative_tradeoff(community, TRADEOFF_F, cmig_solver=cmig_solver)
    return result, build_tidy(result), community


def solve(cmig_solver: str) -> tuple[SolveResult, TidyBundle]:
    """3-member community 를 cmig_solver 로 solve → (result, tidy)."""
    result, bundle, _ = solve_with_community(cmig_solver)
    return result, bundle


def _run_hash_components(
    result: SolveResult, decimals: int = DEFAULT_DECIMALS
) -> RunHashComponents:
    """fixture run_hash 11구성요소 (SC-4·SC-5 — micom_version 포함).

    ``decimals`` **must be the same precision the resulting components will be hashed at**
    (`compute_run_hash(comps, decimals)`). abundance 는 solve 에서 나온 값이라 여기서 잡음을
    흡수하는데, hash 가 쓰는 자릿수와 다른 자릿수로 반올림하면 그 값은 hash 자릿수 기준
    고정점이 아니게 되어 lossless 분기로 빠지고 published hash 가 움직인다 — osqp golden
    (VARIANT_DECIMALS=4) 이 정확히 그렇게 깨졌다. 두 자릿수는 한 쌍으로 움직여야 한다.
    """
    engine = MicomEngine()
    abundance = {
        k: round(v, decimals)
        for k, v in sorted(result.abundances.items())
        if v is not None
    }
    return RunHashComponents(
        model_checksum="micom_test_taxonomy_3",        # 번들 모델 식별자 (결정적)
        medium_checksum="micom_default_medium",
        member_set=sorted(result.members),
        abundance=abundance,
        bounds={},
        tradeoff_f=TRADEOFF_F,
        solver_setting={"growth_solver": result.growth_solver, "flux_solver": result.flux_solver},
        micom_version=engine.micom_version,
        cmig_core_version=CMIG_CORE_VERSION,
        namespace_mapping_decisions=[],
        flux_normalization_method="pfba",
    )


def capture(base_dir: Path = FIXTURE_DIR) -> dict[str, dict[str, str]]:
    """solver별 golden 캡처 → expected/{solver}/{nodes,edges,profile}.parquet + manifest."""
    hashes: dict[str, dict[str, str]] = {}
    for solver in SOLVER_VARIANTS:
        result, bundle = solve(solver)
        dec = VARIANT_DECIMALS[solver]
        out = base_dir / "expected" / solver
        out.mkdir(parents=True, exist_ok=True)
        atomic_write_parquet(out / "nodes.parquet", bundle.nodes)
        atomic_write_parquet(out / "edges.parquet", bundle.edges)
        atomic_write_parquet(out / "profile.parquet", bundle.profile)
        # growth_expected.tsv (멤버 + community). None(누락) → 'nan'.
        lines = ["member\tgrowth_rate"]
        for m in sorted(result.member_growth):
            g = result.member_growth[m]
            lines.append(f"{m}\t{g:.{dec}f}" if g is not None else f"{m}\tnan")
        lines.append(f"__community__\t{result.objective:.{dec}f}")
        (out / "growth_expected.tsv").write_text("\n".join(lines) + "\n")
        # sign_expected.tsv (external profile 의 (metabolite, ui_flux, label))
        prof = bundle.profile.to_pylist()
        slines = ["metabolite\tui_flux\tlabel"]
        slines += [f"{r['metabolite']}\t{r['ui_flux']:.{dec}f}\t{r['label']}"
                   for r in sorted(prof, key=lambda x: x["metabolite"])]
        (out / "sign_expected.tsv").write_text("\n".join(slines) + "\n")
        # run_hash — 단일 canonical 구현 경유 ([HASH-SINGLE], I-5).
        # 반올림 자릿수는 builder 와 hash 가 반드시 같은 값을 써야 한다(위 docstring 참조).
        comps = _run_hash_components(result, dec)
        run_hash = compute_run_hash(comps, dec)
        (out / "config.json").write_text(
            json.dumps(
                {"components": asdict(comps), "run_hash": run_hash,
                 "golden_decimals": dec, "tidy_hashes": bundle_hashes(bundle, dec)},
                indent=2, sort_keys=True,
            ) + "\n"
        )
        hashes[solver] = bundle_hashes(bundle, dec)
    return hashes


class GoldenVersionMismatch(RuntimeError):
    """golden 캡처 시 MICOM 버전 ≠ 설치 버전 → 승격 차단 (§4.1·§16·§17, SC-5)."""


def _installed_micom_version() -> str:
    return MicomEngine().micom_version


def verify_golden_versions(base_dir: Path = FIXTURE_DIR) -> dict[str, dict[str, object]]:
    """MICOM-version golden regression gate (SC-5).

    각 solver 변형 golden 의 config.json 에 기록된 micom_version 이 현재 설치 버전과
    일치하는지 검사한다. 불일치 = golden 재검증 필요(승격 차단).
    반환: {solver: {recorded, installed, version_ok, published_run_hash, recomputed_run_hash,
    hash_ok, ok}}.

    R5-P3: this compared *only* micom_version, so a change to the hash serialization could move a
    published golden run_hash while the gate stayed green — which is exactly what happened to the
    osqp golden (a422eb89… → 6a30a02a…) and went unnoticed. The gate now also recomputes each
    golden's run_hash from its own recorded components at its own recorded decimals and compares
    it with the published value. That needs no solver and no re-solve, so it stays cheap while
    actually gating the thing the fixture exists to protect.
    """
    installed = _installed_micom_version()
    report: dict[str, dict[str, object]] = {}
    for solver in SOLVER_VARIANTS:
        cfg_path = base_dir / "expected" / solver / "config.json"
        recorded = None
        published_hash: str | None = None
        recomputed_hash: str | None = None
        hash_ok = True
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text())
            recorded = cfg.get("components", {}).get("micom_version")
            published_hash = cfg.get("run_hash")
            components = cfg.get("components")
            decimals = cfg.get("golden_decimals", DEFAULT_DECIMALS)
            if published_hash and isinstance(components, dict):
                try:
                    recomputed_hash = compute_run_hash(
                        RunHashComponents(**components), decimals
                    )
                except TypeError as error:       # component set drifted from the dataclass
                    recomputed_hash = f"uncomputable: {error}"
                hash_ok = recomputed_hash == published_hash
        report[solver] = {
            "recorded": recorded,
            "installed": installed,
            "version_ok": recorded == installed,
            "published_run_hash": published_hash,
            "recomputed_run_hash": recomputed_hash,
            "hash_ok": hash_ok,
            "ok": recorded == installed and hash_ok,
        }
    return report


def assert_golden_versions(base_dir: Path = FIXTURE_DIR) -> None:
    """gate: 버전 불일치 **또는** published run_hash 이동이면 GoldenVersionMismatch (승격 차단)."""
    report = verify_golden_versions(base_dir)
    details: list[str] = []
    for solver, r in report.items():
        if not r["version_ok"]:
            details.append(f"{solver}: micom golden={r['recorded']} != installed={r['installed']}")
        if not r["hash_ok"]:
            details.append(
                f"{solver}: run_hash published={r['published_run_hash']} != "
                f"recomputed={r['recomputed_run_hash']} — the hash serialization moved a "
                f"published golden"
            )
    if details:
        raise GoldenVersionMismatch(
            "MICOM-version golden regression 차단 (SC-5): " + "; ".join(details) + ". "
            "golden 재캡처·재검증 후 승격하세요 (`python -m cmig.golden_fixture`)."
        )


if __name__ == "__main__":
    h = capture()
    for solver, hh in h.items():
        print(solver, hh)
