"""B1 regression — MICOM 위임 예외가 traceback 대신 구조화 결과로 나오는지.

관측된 실제 실패(gurobipy GurobiError "Unable to retrieve attribute 'X'"): MICOM 은
`CommunitySolution` 생성 시 solver status 확인 없이 primal 을 읽으므로, pFBA stage 가
non-optimal 로 끝나면 status 대신 예외가 올라온다. engine 은 (1) pfba=False 로 1회 재시도하고
(2) 그래도 실패하면 status="solver_failed" 를 돌려주어야 한다. micom/gurobi 불요 — 위임 대상은
`cooperative_tradeoff` 시그니처만 흉내내는 double 이다.
"""

from __future__ import annotations

import json

import pytest

from cmig.core.engine import PFBA_FALLBACK_WARNING, MicomEngine


class _FakeSolution:
    """MICOM CommunitySolution 의 판독 표면(members/fluxes/growth_rate)만 흉내낸다."""

    def __init__(self, growth: float = 0.6) -> None:
        pd = pytest.importorskip("pandas")
        self.growth_rate = growth
        self.members = pd.DataFrame(
            {"growth_rate": [0.5, 0.7], "abundance": [0.5, 0.5]}, index=["A", "B"]
        )
        self.fluxes = pd.DataFrame(
            {"EX_ac_m": [3.0, 0.0, 0.0], "EX_ac_e": [0.0, 8.0, -5.0]},
            index=["medium", "A", "B"],
        )


class _StubCommunity:
    """pfba 인자에 따라 예외/해를 돌려주는 위임 double. 호출 이력을 기록한다."""

    def __init__(self, *, pfba_raises: bool, non_pfba_raises: bool) -> None:
        self.pfba_raises = pfba_raises
        self.non_pfba_raises = non_pfba_raises
        self.calls: list[bool] = []

    def cooperative_tradeoff(self, *, fraction: float, fluxes: bool, pfba: bool):
        self.calls.append(pfba)
        if pfba and self.pfba_raises:
            raise RuntimeError("Unable to retrieve attribute 'X'")
        if not pfba and self.non_pfba_raises:
            raise RuntimeError("retry also died")
        return _FakeSolution()


def test_pfba_success_keeps_pfba_provenance_and_no_warning():
    community = _StubCommunity(pfba_raises=False, non_pfba_raises=False)
    result = MicomEngine().cooperative_tradeoff(community, 0.5)
    assert community.calls == [True]                    # 재시도 없음
    assert result.status == "optimal"
    assert result.flux_normalization_method == "pfba"
    assert result.warnings == []
    assert result.diagnostic is None


def test_pfba_failure_retries_without_pfba_and_warns():
    community = _StubCommunity(pfba_raises=True, non_pfba_raises=False)
    result = MicomEngine().cooperative_tradeoff(community, 0.5)
    assert community.calls == [True, False]             # pFBA → non-pFBA 재시도
    assert result.status == "optimal"                   # 실제 해는 사용 가능
    assert result.objective == pytest.approx(0.6)
    # 조용한 강등 금지: warning + manifest 용 정규화 방식 + 원인 진단이 모두 남는다.
    assert PFBA_FALLBACK_WARNING in result.warnings
    assert result.flux_normalization_method == "fba"
    assert result.diagnostic is not None
    parsed = json.loads(result.diagnostic)
    assert parsed["code"] == "solver_error"
    assert "pFBA flux stage failed" in parsed["message"]


def test_both_stages_failing_yields_structured_solver_failed():
    community = _StubCommunity(pfba_raises=True, non_pfba_raises=True)
    result = MicomEngine().cooperative_tradeoff(community, 0.5)
    assert community.calls == [True, False]
    # 예외가 CLI 까지 올라가지 않고 status 로 표현된다 — 호출자의 status 분기가 동작한다.
    assert result.status == "solver_failed"
    assert result.objective == 0.0
    assert result.member_exchange == {}
    assert result.flux_normalization_method == "none"
    parsed = json.loads(result.diagnostic)
    causes = [c["message"] for c in parsed["detail"]["causes"]]
    assert any("pFBA flux stage failed" in m for m in causes)
    assert any("non-parsimonious retry failed" in m for m in causes)


def test_solution_readout_failure_is_also_structured():
    """해는 돌아왔지만 판독이 깨지는 경우에도 traceback 대신 solver_failed."""

    class _BadSolution:
        growth_rate = 0.5

        @property
        def members(self):
            raise RuntimeError("summary unavailable")

    class _BadCommunity:
        def cooperative_tradeoff(self, **_kwargs):
            return _BadSolution()

    result = MicomEngine().cooperative_tradeoff(_BadCommunity(), 0.5)
    assert result.status == "solver_failed"
    assert "solution readout failed" in result.diagnostic


def test_tradeoff_range_still_fails_fast():
    """인자 오류는 구조화 대상이 아니다 — 여전히 ValueError (§4.2)."""
    community = _StubCommunity(pfba_raises=False, non_pfba_raises=False)
    with pytest.raises(ValueError, match="tradeoff_f"):
        MicomEngine().cooperative_tradeoff(community, 0.0)
    assert community.calls == []
