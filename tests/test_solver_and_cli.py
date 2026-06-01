"""SolverBackend capability seam + CLI smoke. Design Ref: §4.2·§5."""

from cmig.cli.main import main
from cmig.core.engine import EngineUnavailableError, MicomEngine
from cmig.core.solver import (
    GurobiBackend,
    OsqpBackend,
    SolverBackend,
    capability_matrix,
    get_backend,
)


def test_backends_satisfy_protocol():
    for name in ("gurobi", "highs", "osqp"):
        assert isinstance(get_backend(name), SolverBackend)


def test_gurobi_reports_lp_qp_milp():
    cap = GurobiBackend().capability()
    assert (cap.lp, cap.qp, cap.milp) == (True, True, True)


def test_osqp_reports_hybrid_lp_qp_capability():
    cap = OsqpBackend().capability()
    assert cap.qp is True
    assert cap.lp is True and cap.milp is False
    # cobra/optlang solver="osqp"는 hybrid alias라 LP는 HiGHS로 처리한다.
    assert cap.supports("LP") is True


def test_capability_matrix_has_all_backends():
    m = capability_matrix()
    assert set(m) == {"gurobi", "highs", "osqp"}


def test_glpk_not_in_registry():
    # GLPK=GPL 미번들 (§2) — registry 에 없어야 함
    assert "glpk" not in capability_matrix()


def test_micom_engine_unavailable_in_2a():
    # 2a: micom 미설치 → 가용성 검사 시 명시적 에러 (capability 강등)
    try:
        import micom  # noqa: F401
        installed = True
    except ImportError:
        installed = False
    if not installed:
        import pytest
        with pytest.raises(EngineUnavailableError):
            _ = MicomEngine().micom_version


def test_cli_version_and_solvers(capsys):
    assert main(["version"]) == 0
    assert main(["solvers"]) == 0
    out = capsys.readouterr().out
    assert "cmig" in out
    assert "gurobi" in out


def test_tradeoff_f_range_guard():
    """I-4: tradeoff_f ∉ (0,1] → ValueError (MICOM 위임 전 fail-fast, micom 불요)."""
    import pytest

    from cmig.core.engine import MicomEngine
    eng = MicomEngine()
    for bad in (0.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            eng.cooperative_tradeoff(object(), bad)   # 가드가 community 접근 전에 발동
