"""C5/S3 — synthetic acetate→butyrate cross-feeding fixture. Plan SC: SC-F7.

문헌의 대표 cross-feeding 관계(primary fermenter 가 acetate 분비 → butyrate producer 가 acetate
흡수→butyrate 분비)를 **정성 검증**하기 위한 synthetic toy GEM 쌍이다.
**실제 외부 GEM이 아니며 종명을 부여하지 않는다** — 정량 해석 금지
(정성 cross-feeding/sign 검증용).

- synthetic_acetate_producer: glucose 흡수 → acetate 분비 (+biomass)
- synthetic_butyrate_consumer: acetate 흡수 → butyrate 분비 (+biomass)

cobra 로 모델을 코드 생성 → SBML(임시) → micom Community → CMIG 경로(build_tidy).
cobra/micom 은 lazy import (엔진 stack 없는 환경에서 import 안전).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from cmig.core.engine import MicomEngine
from cmig.core.interactions import build_tidy

FIXTURE_DIR = Path("fixtures/pair_acetate_butyrate")
TRADEOFF_F = 0.5


def _met(mid: str) -> Any:
    from cobra import Metabolite

    return Metabolite(mid, compartment="e" if mid.endswith("_e") else "c")


def _rxn(rid: str, stoich: dict[str, float], bounds: tuple[float, float]) -> Any:
    """reaction id·{met_id: coef}·(lb,ub) → cobra Reaction (met 코드 생성)."""
    from cobra import Reaction

    r = Reaction(rid)
    r.add_metabolites({_met(mid): coef for mid, coef in stoich.items()})
    r.bounds = bounds
    return r


def _producer() -> Any:
    """glucose → acetate 분비 synthetic GEM (종명 없음)."""
    from cobra import Model

    m = Model("synthetic_acetate_producer")
    m.add_reactions([
        _rxn("EX_glc__D_e", {"glc__D_e": -1}, (-10, 1000)),       # glucose 흡수
        _rxn("EX_ac_e", {"ac_e": -1}, (0, 1000)),                 # acetate 분비
        _rxn("GLCt", {"glc__D_e": -1, "glc__D_c": 1}, (-1000, 1000)),
        _rxn("ACt", {"ac_c": -1, "ac_e": 1}, (-1000, 1000)),
        _rxn("GLC2AC", {"glc__D_c": -1, "ac_c": 2, "biomass_c": 1}, (0, 1000)),
        _rxn("BIOMASS", {"biomass_c": -1}, (0, 1000)),
    ])
    m.objective = "BIOMASS"
    return m


def _consumer() -> Any:
    """acetate → butyrate 분비 synthetic GEM (종명 없음)."""
    from cobra import Model

    m = Model("synthetic_butyrate_consumer")
    m.add_reactions([
        _rxn("EX_ac_e", {"ac_e": -1}, (-10, 1000)),               # acetate 흡수
        _rxn("EX_but_e", {"but_e": -1}, (0, 1000)),               # butyrate 분비
        _rxn("ACt", {"ac_e": -1, "ac_c": 1}, (-1000, 1000)),
        _rxn("BUTt", {"but_c": -1, "but_e": 1}, (-1000, 1000)),
        _rxn("AC2BUT", {"ac_c": -2, "but_c": 1, "biomass_c": 1}, (0, 1000)),
        _rxn("BIOMASS", {"biomass_c": -1}, (0, 1000)),
    ])
    m.objective = "BIOMASS"
    return m


def build_pair_models() -> tuple[Any, Any]:
    """(producer, consumer) synthetic cobra 모델."""
    return _producer(), _consumer()


def build_pair_taxonomy(out_dir: str | Path) -> Any:
    """synthetic 모델을 SBML 로 쓰고 micom taxonomy DataFrame 반환."""
    import cobra
    import pandas as pd

    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    producer, consumer = build_pair_models()
    pp, cp = d / "producer.xml", d / "consumer.xml"
    cobra.io.write_sbml_model(producer, str(pp))
    cobra.io.write_sbml_model(consumer, str(cp))
    return pd.DataFrame({
        "id": ["producer", "consumer"],
        "file": [str(pp), str(cp)],
        "abundance": [0.5, 0.5],
    })


def solve_pair(cmig_solver: str = "gurobi") -> tuple[Any, Any]:
    """synthetic pair community solve → (SolveResult, TidyBundle). 정성 cross-feeding 검증용."""
    with tempfile.TemporaryDirectory() as td:
        taxonomy = build_pair_taxonomy(td)
        eng = MicomEngine()
        community = eng.build_community(taxonomy, cmig_solver=cmig_solver)
        result = eng.cooperative_tradeoff(community, TRADEOFF_F, cmig_solver=cmig_solver)
    return result, build_tidy(result)
