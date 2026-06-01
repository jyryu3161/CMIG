# Host-Microbe Config Decision: B (CMIG 2-compartment) (2026-06-01)

§12 host-microbe spike 결정. **probe로 settled (Human-GEM 불요)**:
- micom 0.39.0 `Community.__init__` 파라미터에 **`host` 없음**(probe 확인) → config A(MICOM-native maintenance-host) public API 불가.
- → **config B 채택**: CMIG가 미생물 community(micom)를 solve → 환경 분비(lumen 가용) → host(cobra)를 lumen uptake 한계 + **viability 제약(ATP maintenance ≥ 임계, host는 군집 성장 목적 미포함)**으로 별도 solve → flux decomposition.

**핵심 정정**: host 구현은 **특정 Human-GEM에 종속되지 않음** — GEM 구조(lumen/blood interface + maintenance)만 맞으면 동일 동작. synthetic toy host(colonocyte-like, butyrate 의존)로 계약·정성 검증 완료. Human-GEM은 (1) 실 스케일(10k+ rxn) 성능/feasibility (2) 생물학적 정량 타당성에만 필요(synthetic_pair "정량 해석 금지, 정성 검증용"과 동일 한계).

검증(end-to-end): synthetic_pair community(butyrate 6.25 분비) → host 흡수 → viable(biomass 30.25). 미생물 없으면 host non-viable(infeasible, colonocyte butyrate 의존 정성 재현).
