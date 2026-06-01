# CMIG v3.0 업데이트 구현 리뷰 및 분석 시나리오 제안

- 작성일: 2026-06-01
- 기준 명세: `CMIG_명세서_v3.0.md`
- 이전 리뷰: `REVIEW/CMIG_v3_implementation_review.md`
- 확인 범위: `cmig/`, `tests/`, `fixtures/community_3_member/expected/`, `README.md`, `pyproject.toml`
- 검증 명령: `uv run pytest`
- 결과: `129 passed, 4 warnings`
- 비고: 현재 디렉터리는 Git repository가 아니므로 변경 diff가 아니라 파일 내용 기준으로 재검토했다.

## 1. 업데이트 요약

이전 리뷰 이후 headless core의 검증이 크게 보강되었다. 특히 `delta`/`sandbox` 실패 전파, FVA 모듈, sweep schema 전개, render CSV 안정화, E2E pipeline, 4-member robustness 테스트가 추가되었다. 테스트 수는 `95 passed`에서 `129 passed`로 증가했다.

그러나 가장 중요한 기존 R1, 즉 **`osqp_growth_highs_flux`가 실제 HiGHS LP pFBA 재계산을 수행하는지**는 아직 해결되지 않았다. 현재도 `cmig/core/engine.py`는 `community.cooperative_tradeoff(... fluxes=True, pfba=True)`를 1회 호출한 뒤 메타데이터만 `flux_solver="highs"`, `flux_report_status="full"`로 바꾼다. `osqp`와 `osqp_growth_highs_flux` golden의 tidy hash가 동일한 점도 그대로다.

## 2. 이전 리뷰 항목별 상태

| 이전 항목 | 현재 상태 | 판단 |
|---|---:|---|
| R1 `osqp_growth_highs_flux` 실제 LP 재계산 부재 | 미해결 | 여전히 메타데이터-only 가능성이 높음 |
| R2 golden solver 목록 불일치 | 미해결 | 명세는 `gurobi/highs/osqp_growth_highs_flux`, 구현은 `gurobi/osqp/osqp_growth_highs_flux` |
| R3 CLI 실제 solve 미구현 | 미해결 | `cmig solve`는 여전히 안내 메시지만 출력 |
| R4 sandbox FVA/no-change 축약 | 부분 해결 | FVA 모듈은 추가됐지만 sandbox/community profile과 통합은 아직 아님 |
| R5 sweep diagnostic 자유 문자열 | 부분 해결 | axis schema는 개선됐지만 diagnostic은 여전히 자유 문자열 |
| R6 README 상태 불일치 | 미해결 | README는 아직 2a/2b 설명이 현재 테스트 상태와 어긋남 |

## 3. 새로 잘 반영된 점

- `cmig/core/delta.py`: 입력 solve가 `infeasible`이거나 objective가 `NaN`이면 `DeltaResult.status="failed"`와 diagnostic을 전파한다. 실패를 정상 delta로 위장하지 않는 방향이라 좋다.
- `cmig/core/sandbox.py`: constrained solve 실패 시 `no_significant_change=False`, `status="failed"`로 전파한다. 이전의 "실패가 변화 없음으로 보일 위험"은 상당히 줄었다.
- `cmig/core/fva.py`: cobra FVA를 위임하고, `FVAUnavailableError`와 `FVAInfeasibleError`를 분리했다. `attach_fva_to_profile`도 생겼다.
- `cmig/core/sweep.py`: `axes` 단일 JSON 컬럼 대신 `axis_medium_variant`, `axis_abundance`, `axis_member_set`, `axis_bounds`, `axis_tradeoff_f`, `axis_solver` 컬럼으로 전개되었다.
- `cmig/render/client.py`: CSV 출력에서 `NaN/inf`를 빈 문자열로 처리하고 float를 고정 자릿수로 직렬화한다.
- 테스트: `tests/test_e2e_pipeline.py`와 `tests/test_robustness.py`가 추가되어 3-member fixture 밖의 4-member community와 GUI/render hop 일부까지 확인한다.

## 4. 남은 주요 리스크

### U1. Hybrid solver 경로는 아직 과학적으로 위험하다

- 위치: `cmig/core/engine.py:117-119`, `cmig/core/engine.py:157-159`
- 문제: `osqp_growth_highs_flux`는 실제 재계산이 아니라 결과 라벨만 `highs/full`로 보인다.
- 근거: `fixtures/community_3_member/expected/osqp/config.json`와 `osqp_growth_highs_flux/config.json`의 `tidy_hashes`가 동일하다.
- 영향: QP-only flux를 LP pFBA 재계산 결과로 오인할 수 있다. 논문용/재현성 분석에서 가장 큰 신뢰도 리스크다.
- 의견: 실제 LP pFBA 구현 전까지 `osqp_growth_highs_flux`는 `experimental` 또는 `not_implemented`로 강등하고, `flux_report_status="qp_only_approximate"` 또는 별도 `"metadata_only_hybrid"` 진단을 넣는 편이 안전하다.

### U2. CLI solve가 없어 플랫폼 사용 경로가 테스트 fixture에 갇혀 있다

- 위치: `cmig/cli/main.py:31-37`
- 문제: 라이브러리 함수와 테스트는 커졌지만 사용자가 `cmig solve`로 community 결과를 만들 수 없다.
- 의견: 가장 작은 실용 slice는 `cmig solve-fixture --solver gurobi --out out/`다. 그 다음 `taxonomy.csv + medium.csv/yaml + solver + tradeoff_f` 입력을 받는 `cmig solve`로 확장하면 된다.

### U3. Host-microbe 목적과 현재 구현 사이의 간극이 크다

- 현재 강점: microbe-only community modeling, cross-feeding, external profile, delta, sweep.
- 현재 약점: HostModel, lumen/blood 2-interface, epithelial/colonocyte viability constraint, host objective readout, host-specific sign convention이 없다.
- 의견: host-microbe를 플랫폼의 중심 가치로 둘 계획이면 `HostModel`을 늦게 붙이는 부가 기능으로 두기보다, 지금부터 tidy/profile schema에 `interface={lumen,blood}`와 `organism_type={microbe,host}` 확장 여지를 둬야 한다.

### U4. FVA 모듈은 생겼지만 sandbox/community 결과와 아직 연결되지 않았다

- 위치: `cmig/core/fva.py`, `cmig/core/sandbox.py`
- 문제: `attach_fva_to_profile`은 helper이고, sandbox의 no-change 진단 결과에 FVA range가 자동으로 붙지는 않는다.
- 의견: `evaluate_sandbox(..., fva_ranges=None)`나 별도 `SandboxDiagnostics`를 만들어 no-change일 때 FVA 범위, constrained reaction, affected exchanges를 함께 반환하는 것이 좋다.

### U5. diagnostic은 아직 기계 판독성이 낮다

- 위치: `cmig/core/sweep.py:140-146`
- 문제: `RuntimeError: infeasible` 같은 자유 문자열이다.
- 의견: `Diagnostic(code, message, detail)` JSON 문자열로 통일하면 GUI 필터, batch summary, 실패 원인 통계가 쉬워진다.

### U6. README가 현재 상태를 설명하지 못한다

- 위치: `README.md:11-39`
- 문제: README는 아직 "2a, 2b는 이후"라고 쓰지만 현재는 MICOM golden/e2e/robustness 테스트가 있다.
- 의견: "headless core + partial 2b integration complete, CLI solve and host-microbe not yet implemented, hybrid solver caveat"로 갱신해야 한다.

## 5. 대표 분석 시나리오 제안 및 구현 가능성

아래 시나리오는 과도한 신기능보다는 문헌에서 반복적으로 쓰이는 community/host-microbe modeling 질문으로 제한했다.

### S1. 식이 perturbation: Western diet vs high-fiber/protein/fermented diet

- 문헌 근거: MICOM은 diet와 microbiome composition이 community function에 미치는 영향을 개인별로 예측하는 도구로 제안되었다. MICOMWeb도 high-fibre, high-fat/protein, fermented foods 조건에서 export flux와 taxon growth를 비교한다.
- 분석 질문: 식이 medium을 바꾸면 community growth, taxon growth, SCFA export, competition/cross-feeding edge가 어떻게 변하는가?
- 현재 구현 가능성: **부분 가능**.
- 가능한 현재 기능: medium variant를 sweep axis로 두고 `external_profile`, `member_growth`, `cross_feeding` 비교 가능. `run_hash`와 `sweep.parquet` 기반 반복 분석도 가능.
- 부족한 점: 사용자 입력 medium editor/CLI solve, diet preset, cohort-level 통계/시각화가 부족하다.
- 반영 의견: `medium_presets/`에 Western/high-fiber/protein/fermented diet YAML을 두고 `cmig sweep --axis medium_variant` CLI를 먼저 구현한다.

### S2. 개인별 SCFA 생산 및 prebiotic/probiotic response

- 문헌 근거: personalized microbial community-scale metabolic models는 diet/prebiotic/probiotic input에 따른 SCFA production profile 예측에 사용된다.
- 분석 질문: 동일 prebiotic 또는 probiotic 추가가 개인별 abundance 차이에 따라 acetate/propionate/butyrate 생산을 어떻게 바꾸는가?
- 현재 구현 가능성: **부분 가능, microbe-only 중심**.
- 가능한 현재 기능: abundance/member_set/tradeoff_f sweep, add-member delta, external profile delta.
- 부족한 점: SCFA target dashboard, target metabolite preset, probiotic engraftment/abundance plausibility, cohort statistics가 없다.
- 반영 의견: `TargetMetaboliteSet`을 추가해 acetate/propionate/butyrate를 기본 타깃으로 묶고, `delta` 결과에서 target-only summary를 자동 생성한다.

### S3. Acetate-to-butyrate cross-feeding: Bifidobacterium adolescentis - Faecalibacterium prausnitzii

- 문헌 근거: host-microbe metabolic modeling review는 B. adolescentis가 acetate를 만들고 F. prausnitzii가 이를 이용해 butyrate를 생산하는 예를 대표 community FBA 사례로 설명한다.
- 분석 질문: primary fermenter가 만든 acetate가 butyrate producer 성장과 butyrate secretion에 얼마나 기여하는가?
- 현재 구현 가능성: **microbe-only pair/community는 가능**.
- 가능한 현재 기능: pair/community solve, cross-feeding edge `weight=min(secretor,consumer)`, external profile, member add/remove delta.
- 부족한 점: 실제 AGORA/VMH 모델 import와 namespace mapping workflow가 필요하다. Butyrate/acetate exchange ID 매핑 품질이 관건이다.
- 반영 의견: 이 시나리오를 `fixtures/pair_acetate_butyrate/` golden 후보로 추가하면 sign/cross-feeding 검증에 과학적 의미가 생긴다.

### S4. Keystone taxa add/remove: community resilience와 metabolic shift

- 문헌 근거: FBA 기반 community 모델은 member addition/removal, probiotic addition, microbial composition perturbation 분석에 반복적으로 사용된다.
- 분석 질문: Akkermansia, Faecalibacterium, Ruminococcus 같은 특정 taxon을 제거/추가하면 SCFA, mucin/carbohydrate utilization, interaction network가 어떻게 바뀌는가?
- 현재 구현 가능성: **부분 가능**.
- 가능한 현재 기능: `compute_delta`, member_set sweep, graph payload, profile delta.
- 부족한 점: taxa/model library, abundance normalization UI, biological preset이 없다. "keystone"을 판정하는 metric도 아직 명확하지 않다.
- 반영 의견: `keystone_score = |target_flux_delta| + |growth_delta| + network_edge_delta` 같은 단순 MVP metric부터 시작한다. 과학적 명칭은 "candidate keystone effect" 정도로 보수적으로 둔다.

### S5. Host epithelial maintenance: microbiota가 host viability/maintenance에 미치는 영향

- 문헌 근거: 최근 host-microbiota multi-objective modeling 연구는 enterocyte와 gut microbe GEM을 lumen compartment로 연결하고, diet 조건에 따른 competition/mutualism/neutralism 및 choline cross-feeding을 분석했다. 같은 연구는 minimal microbiota가 epithelial cell maintenance를 도울 수 있음을 보였다.
- 분석 질문: 특정 microbe 또는 minimal community가 enterocyte/colonocyte maintenance lower-bound를 만족시키는 데 어떤 대사체를 공급/소비하는가?
- 현재 구현 가능성: **현재는 불가, Extension MVP-3 필요**.
- 필요한 구현:
  - `HostModel` entity
  - lumen/blood 2-interface exchange schema
  - host viability/maintenance lower-bound constraint
  - host objective를 community objective에 섞지 않는 기본 정책
  - host-specific profile/sign table
- 반영 의견: 명세 §12의 spike를 우선 구현해야 한다. 작은 1 host + 1 microbe LGG 또는 E. coli toy model로 시작하고, 바로 Human-GEM 전체를 붙이지 않는 것이 안전하다.

### S6. Drug/xenobiotic metabolism by gut microbiome

- 문헌 근거: AGORA2는 7,302 strains와 98 drugs의 strain-resolved drug degradation/biotransformation capability를 포함하며, personalized gut microbial drug metabolism 예측에 쓰였다.
- 분석 질문: 특정 drug/metabolite가 어떤 taxa에 의해 소비/변환되고, community composition에 따라 잔류/생성 flux가 어떻게 달라지는가?
- 현재 구현 가능성: **부분 가능하지만 데이터 의존성이 큼**.
- 가능한 현재 기능: drug을 medium/external metabolite로 표현할 수 있으면 uptake/secretion profile과 taxon exchange 비교는 가능하다.
- 부족한 점: drug biotransformation reaction curation, metabolite namespace, host absorption/blood interface, toxicity objective가 없다.
- 반영 의견: MVP에서는 "drug metabolism"이라고 넓게 선언하지 말고 `xenobiotic exchange screening`으로 제한한다. AGORA2/VMH 호환 모델을 입력으로 받을 때만 활성화하는 것이 안전하다.

## 6. 시나리오별 구현 우선순위 제안

| 우선순위 | 시나리오 | 이유 |
|---:|---|---|
| 1 | S3 acetate-to-butyrate cross-feeding | 현재 core 강점과 가장 잘 맞고 fixture/golden으로 만들기 좋음 |
| 2 | S1 diet perturbation | medium sweep, external profile, graph viewer를 제품 가치로 보여주기 좋음 |
| 3 | S2 SCFA/prebiotic/probiotic response | S1/S3 위에 target summary와 add-member delta를 얹으면 가능 |
| 4 | S4 keystone add/remove | delta와 graph를 활용하되 metric 정의는 보수적으로 시작 |
| 5 | S5 host epithelial maintenance | 플랫폼 정체성상 중요하지만 설계/스키마 확장이 필요 |
| 6 | S6 drug/xenobiotic metabolism | AGORA2/VMH 데이터 의존성이 커서 입력 호환성 확보 후 진행 |

## 7. 구현 로드맵에 반영할 의견

1. **먼저 microbe-only science fixture를 강화한다.** `pair_acetate_butyrate` fixture를 만들고 acetate uptake/secretion, butyrate secretion, cross-feeding edge를 golden으로 고정한다.
2. **CLI 산출 경로를 만든다.** GUI보다 먼저 `cmig solve-fixture`, `cmig solve`, `cmig sweep`이 parquet과 manifest를 쓰게 해야 플랫폼 분석 흐름이 생긴다.
3. **Hybrid solver를 정직하게 표시한다.** 실제 LP 재계산 전까지 `osqp_growth_highs_flux`의 `full` 표기를 피한다.
4. **Host-microbe schema seed를 지금 심는다.** tidy/profile에 `organism_type`, `interface`, `compartment`를 확장 가능한 방식으로 설계한다. 기존 microbe-only rows에서는 null 또는 `"lumen"` default를 허용한다.
5. **SCFA target preset을 추가한다.** acetate/propionate/butyrate/lactate/succinate 정도를 기본 target set으로 두면 S1-S4 분석이 명확해진다.
6. **diagnostic을 구조화한다.** sweep/solve/sandbox 모두 `{code,message,detail}`로 맞추면 GUI와 batch report가 쉬워진다.

## 8. 참고 문헌 및 근거 링크

- MICOM: Metagenome-Scale Modeling To Infer Metabolic Interactions in the Gut Microbiota. mSystems, 2020. https://journals.asm.org/doi/10.1128/msystems.00606-19
- MICOM paper PMC mirror/search record: https://pmc.ncbi.nlm.nih.gov/articles/PMC6977071/
- MICOMWeb: microbial community metabolic modeling of the human gut, 2025. https://pmc.ncbi.nlm.nih.gov/articles/PMC12674444/
- AGORA2 / Genome-scale metabolic reconstruction of 7,302 human microorganisms for personalized medicine. Nature Biotechnology, 2023. https://www.nature.com/articles/s41587-022-01628-0
- Microbial community-scale metabolic modelling predicts personalized short-chain fatty acid production profiles in the human gut. https://pmc.ncbi.nlm.nih.gov/articles/PMC11841136/
- Understanding the host-microbe interactions using metabolic modeling. Microbiome, 2021. https://link.springer.com/article/10.1186/s40168-020-00955-1
- Community metabolic modeling of host-microbiota interactions through multi-objective optimization. iScience, 2024. https://pubmed.ncbi.nlm.nih.gov/38952683/
- Genome-scale metabolic modelling of human gut microbes to inform rational community design. Gut Microbes, 2025. https://pmc.ncbi.nlm.nih.gov/articles/PMC12283000/
