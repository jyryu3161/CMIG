"""F2 — community-level FVA (gurobi). Plan SC: SC-C4.

community_fva(EX_*_m) → metabolite 매핑 → profile fva_lo/hi 부착.
핵심 발견: 부착 profile 의 net_flux 는 cooperative_tradeoff(fraction=TRADEOFF_F) 解이므로,
**fraction_of_optimum=TRADEOFF_F 로 FVA 를 돌려야** fva_lo≤net≤fva_hi 가 성립한다(같은 feasible
region). fraction=1.0(max 성장)으로 돌리면 tradeoff 解가 envelope 밖일 수 있음(검증된 사실).
micom 미설치 시 skip.
"""

from __future__ import annotations

import pytest

pytest.importorskip("micom")

from cmig.core.engine import MicomEngine  # noqa: E402
from cmig.core.fva import (  # noqa: E402
    FVARange,
    attach_community_fva_to_profile,
    community_fva,
)
from cmig.core.interactions import build_tidy  # noqa: E402
from cmig.golden_fixture import TRADEOFF_F, build_taxonomy  # noqa: E402


@pytest.fixture(scope="module")
def community_and_bundle():
    eng = MicomEngine()
    com = eng.build_community(build_taxonomy(), cmig_solver="gurobi")
    result = eng.cooperative_tradeoff(com, TRADEOFF_F, cmig_solver="gurobi")
    return com, build_tidy(result)


def test_community_fva_ranges_valid(community_and_bundle):
    """community FVA 가 EX_*_m 에 대해 유효 범위(lo≤hi) 산출."""
    com, _ = community_and_bundle
    fva = community_fva(com, fraction_of_optimum=TRADEOFF_F)
    assert fva and all(isinstance(v, FVARange) and v.lo <= v.hi for v in fva.values())
    assert all(k.startswith("EX_") and k.endswith("_m") for k in fva)   # 환경 exchange만


def test_attach_maps_exchange_to_metabolite(community_and_bundle):
    """EX_*_m reaction id → metabolite(ac 등) 매핑으로 profile fva_lo/hi 부착."""
    com, bundle = community_and_bundle
    fva = community_fva(com, fraction_of_optimum=TRADEOFF_F)
    attached = attach_community_fva_to_profile(bundle.profile.to_pylist(), fva)
    filled = [r for r in attached if r["fva_lo"] is not None]
    assert filled, "어떤 profile 행도 FVA 부착 안 됨(매핑 실패)"
    mets = {r["metabolite"] for r in filled}
    assert "ac" in mets                                                  # EX_ac_m → ac


def test_fva_brackets_tradeoff_net_at_matching_fraction(community_and_bundle):
    """SC-C4: fraction=TRADEOFF_F → 모든 환경 exchange 에 fva_lo ≤ net ≤ fva_hi."""
    com, bundle = community_and_bundle
    fva = community_fva(com, fraction_of_optimum=TRADEOFF_F)
    attached = attach_community_fva_to_profile(bundle.profile.to_pylist(), fva)
    for r in attached:
        if r["fva_lo"] is not None:
            assert r["fva_lo"] - 1e-4 <= r["net_flux"] <= r["fva_hi"] + 1e-4, \
                f"{r['metabolite']} net={r['net_flux']} ∉ [{r['fva_lo']},{r['fva_hi']}]"


def test_fraction_out_of_range_raises(community_and_bundle):
    com, _ = community_and_bundle
    with pytest.raises(ValueError):
        community_fva(com, fraction_of_optimum=0.0)
    with pytest.raises(ValueError):
        community_fva(com, fraction_of_optimum=1.5)


def test_attach_missing_metabolite_is_none():
    """매핑 없는 profile 행 → fva_lo/hi None (강제 0 금지)."""
    rows = [{"metabolite": "unknown_x", "net_flux": 1.0}]
    out = attach_community_fva_to_profile(rows, {"EX_ac_m": FVARange("EX_ac_m", -1.0, 1.0)})
    assert out[0]["fva_lo"] is None and out[0]["fva_hi"] is None


def test_cli_fva_fills_profile_in_output(tmp_path):
    """SC-C4 실채움(실제 산출 경로): cmig solve-fixture --fva → profile fva_lo/hi 채워짐."""
    from cmig.cli.main import main
    from cmig.core.tidy import TidyBundle

    rc = main(["solve-fixture", "--solver", "gurobi", "--fva", "--out", str(tmp_path)])
    assert rc == 0
    bundle = TidyBundle.read(tmp_path)
    rows = bundle.profile.to_pylist()
    filled = [r for r in rows if r["fva_lo"] is not None]
    assert filled, "--fva 인데 profile fva_lo/hi 가 전부 None(실채움 실패)"
    for r in filled:
        assert r["fva_lo"] - 1e-4 <= r["net_flux"] <= r["fva_hi"] + 1e-4   # bracketing(tol)
    # --fva 없으면 채워지지 않음(opt-in)
    out2 = tmp_path / "nofva"
    main(["solve-fixture", "--solver", "gurobi", "--out", str(out2)])
    assert all(r["fva_lo"] is None for r in TidyBundle.read(out2).profile.to_pylist())


def test_community_fva_osqp_rejected_as_capability_not_infeasible(community_and_bundle):
    """AE-1: osqp+community FVA 는 capability 부재(FVAUnavailableError)로 *사전* 거부.

    osqp 는 QP-only approximate(§4.2)라 FVA 반복 재최적화에서 time_limit 으로 퇴화 →
    이전엔 FVAInfeasibleError 로 *오표기*. solver 런타임 실패를 진짜 infeasible 로
    오분류하지 않아야 한다(정직성). 사전 거부이므로 즉시 raise(느린 solve 미진입).
    """
    from cmig.core.fva import FVAInfeasibleError, FVAUnavailableError

    com, _ = community_and_bundle
    with pytest.raises(FVAUnavailableError):
        community_fva(com, fraction_of_optimum=TRADEOFF_F, solver="osqp")
    # 오표기 회귀 가드: infeasible 로 raise 되면 안 됨
    try:
        community_fva(com, fraction_of_optimum=TRADEOFF_F, solver="osqp")
    except FVAInfeasibleError:  # pragma: no cover
        pytest.fail("osqp FVA 가 InfeasibleError 로 오표기됨 (AE-1 회귀)")
    except FVAUnavailableError:
        pass


def test_cli_solve_fixture_osqp_fva_graceful_rc2(tmp_path, capsys):
    """AE-1: `solve-fixture --solver osqp --fva` 는 traceback/rc1 아닌 rc2 + 명시 메시지."""
    from cmig.cli.main import main

    rc = main(["solve-fixture", "--solver", "osqp", "--fva", "--out", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "FVA" in err and "osqp" in err
