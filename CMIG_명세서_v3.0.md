# CMIG 명세서 v3.0 — Implementation Baseline + Extension Roadmap
### 상태: Implementation Baseline 승인본 (MVP-0~2 착수 기준)

**가칭:** CMIG (Community Metabolic Interaction GUI)
**핵심:** CNApy 스타일 네이티브 GUI + Python sidecar 백엔드. **커뮤니티 엔진 = MICOM, CMIG = 부가가치 계층 소유.** 출판 그림은 R 별도 프로세스. Docker/원격은 선택.
**플랫폼:** macOS Apple Silicon (Must), Windows 10/11 x64 (Must), macOS Intel · Linux (Should)

## 0. 변경 요약 & 문서 구조

### v2.9 → v3.0 (Implementation Baseline 승인본)
- **#1 MVP-1a fixture hash 구체화:** expected_nodes/edges/profile.parquet 분리, **float 컬럼 rounding/tolerance 후 hash**, **solver별 golden 분리**(gurobi · osqp) — §10·§16. `osqp_growth_highs_flux` hybrid는 full-flux를 오인시킬 수 있어 폐기하고, OSQP는 `qp_only_approximate`로 명시한다.
- **#2 run hash 정의 확장:** model/medium checksum·member set·abundance·bounds·tradeoff f·solver setting + **micom_version·cmig_core_version·namespace mapping decisions·flux normalization method** — §10·§7.
- **#3 sandbox preview/commit 분리:** sandbox run은 기본 **preview(임시)**, Apply/Save 시에만 Scenario/Run artifact 승격(sweep/cache/store 오염 방지) — §10·§11·§8.
- **#4 통계 5a 우선 유지:** 5a(분포·effect size·검정·BH-FDR)까지 명시 우선, 5b/5c 수요 확인 후 — §15.

### v2.8 → v2.9
- **Baseline / Extension 분리(가장 중요):** v2.8이 baseline으로 비대해져, MVP-0~2만 **PART I Implementation Baseline**으로 고정하고 host-microbe·다중타깃·통계는 **PART II Extension Roadmap**으로 분리.
- **G1** 문구 정밀화(flux 직접 변경 아님 → bound constraint 변경 후 재최적화) — §10·§11.
- **G2** host 기본 정책 확정(objective 미포함 + viability constraint) + objective 선택지 + lumen/blood sign 표 + spike 유지 — §12.
- **G3** Pareto 2타깃 기본/3 optional/4+ 비권장, weighted **단위 정규화 필수**, direction **semantic preset** — §14.
- **G4** **run hash 캐시 + 실패 run diagnostic** — §10.
- **G5** **MVP-5a/5b/5c** 분할(초기 5a) — §15.

### 문서 구조
- **공통 Foundation (§1–§9):** 양쪽에 적용 — 제품정의·의존성·아키텍처·커뮤니티 엔진·데이터·검증·재현성·NFR·출판그림.
- **PART I — Implementation Baseline (§10–§11, MVP-0~2):** 지금 구현·검증 고정 범위. MICOM wrapper·namespace gate·sign/tidy·delta·medium·R export·**G1 sandbox**·**G4 sweep(캐시)**.
- **PART II — Extension Roadmap (§12–§15):** 설계 확정·baseline 분리. **G2 host-microbe(+spike)**·dFBA·**G3 다중타깃 search**·**G5 통계**.
- **로드맵·리스크·결정문 (§16–§18) + 부록.**

---

# 공통 Foundation (§1–§9)

## 1. 제품 정의 및 범위
다수 미생물 GEM·사람세포 모델·배지·외부 대사체 환경을 통합 분석하는 **커뮤니티 대사 상호작용 분석 도구**.
**차별점:** ① 멤버 추가 시 상호작용 변화(delta) ② external 프로파일 ③ 미생물–미생물/–host interaction ④ 특정 물질 생산 조합.
**Baseline vs Extension 경계:** Baseline = 다종 미생물 community 분석·delta·sandbox·sweep. Extension = host-microbe·다중타깃 search·통계.
**비목표:** 공간/agent 시뮬·strain engineering·모델 자동 재구성·SaaS·Escher(optional post-MVP §11).

## 2. 의존성 정책 (Build vs Buy)
- **Own(부가가치 계층):** namespace 정합, sign 정규화, tidy contract, cross-feeding/interaction 추출, delta, CMIG-MIP/MRO, dFBA, consortium search, sandbox, sweep, 통계, validator, GUI·그림.
- **Depend:** **MICOM(Apache-2.0)** 커뮤니티 엔진 · COBRApy+optlang(cobrapy LGPL 옵션) · **Gurobi(권장)**/HiGHS/OSQP/CPLEX · NetworkX · SciPy/statsmodels/scikit-learn(통계) · R 시각화(별도 프로세스).
- **Solver capability matrix:** LP=Gurobi/HiGHS/CPLEX · QP=Gurobi/OSQP/CPLEX(+HiGHS exp) · MILP=Gurobi/HiGHS/CPLEX. OSQP=QP 전용(flux는 LP 재계산), HiGHS-QP=experimental, **GLPK 비번들(GPL)**. capability 부재 시 해당 분석만 비활성화.
- **제외/연기:** Escher(optional post-MVP) · BacArena/COMETS(공간) · SMETANA(코어 미사용·optional 대조) · PyCoMo/MIMEco/FLYCOP.
- **라이선스(배포 전 재검증):** MICOM/optlang/OSQP/SMETANA=Apache · cobrapy=**LGPL 옵션** · HiGHS/Escher=MIT · SciPy류=BSD · **GLPK=GPL→미번들** · Gurobi/CPLEX=상용 학술·미번들 · R=별도 프로세스 격리.

## 3. 아키텍처
```
CMIG Desktop App (PySide6/Qt) ─ GUI/Service ─ Engine Interface
   ├ [기본] Python sidecar (cobrapy + MICOM + CMIG 부가가치 계층)   계산
   ├ [선택] R Render Service (별도 프로세스, 데이터 I/O)            출판 그림
   ├ [선택] Docker Compose                                         재현·격리
   └ [선택] Remote backend (서버/HPC, 토큰)
```
Backend: FastAPI(원격) · job runner(+sweep 배치) · COBRApy(LGPL)+optlang+**MICOM(정확 pin)** · 통계=SciPy/statsmodels/sklearn · 결과 Parquet/Arrow · 메타 YAML+SQLite.

## 4. 커뮤니티 엔진 코어 (MICOM 위임 + 부가가치 계층)
- **4.1 책임/정책:** MICOM=community 구성·cooperative tradeoff·abundance·medium·knockout. CMIG=namespace 정합+gate·sign 정규화·tidy·추출·delta·지표·sandbox·sweep·통계·search·GUI. **MICOM public API + documented flux-return 옵션만**(`cooperative_tradeoff(fluxes=True, pfba=...)`), internal 금지, 미노출 시 upstream PR. **정확 버전 pin**(`micom==X.Y.Z`), 업그레이드는 golden 통과 후 승격.
- **4.2 Cooperative tradeoff + flux 보고:** ① μ_c\*=max Σ a_m μ_m; ② μ_c≥f·μ_c\* 하 member growth L2(QP). **Gurobi는 full-flux(QP+LP pFBA) canonical 경로**, OSQP는 LP flux 재계산 부재로 **`QP-only approximate`** 로만 보고한다. `osqp_growth_highs_flux` hybrid는 폐기하며, 향후 LP 재계산 경로를 실제 구현·검증하기 전까지 full-flux로 표기하지 않는다. (growth/flux solver 분리 기록.)
- **4.3 Sign convention(강제):** `+`=환경으로 분비, `−`=환경에서 흡수. net=환경 exchange, 멤버 기여=멤버↔pool. cross-feeding m→m′: m 분비(+)∧m′ 흡수(−), weight=min. 변환은 부기 계층 단일 진입점.
- **4.4 수치:** pFBA 정규화·QP-only 상태표기·loopless 옵션·infeasible diagnostic.
- **4.5 CMIG-MIP/MRO + minimal medium(cardinality MILP):** U 기본{H₂O,H⁺,Pi}, O₂ 호기/혐기 옵션, blocked 제외, tie-break 결정적. MRO=영양 중복, MIP=cross-feeding 절감. CMIG-defined(+ optional SMETANA-compatible).
- **4.6 Tidy 데이터 계약:** `nodes / edges / profile / matrix / timecourse`(parquet). sweep store는 §5.
- **4.7 Sign 테스트 계약(의무):** MICOM flux→(ui_flux,label) 단위테스트 + canonical case CI(환경 −10→uptake10/+8→secretion8; 멤버↔pool −5→uptake5/+3→분비3).
- **4.8 Namespace hard gate(필수):** exchange 대사체 정합·confidence. **unresolved high-confidence exchange mapping → community solve 차단·해소 요구.** low-confidence 경고 후 진행·자동병합 금지·audit trail.

## 5. 데이터 모델
**MemberModel:** id/name/strain; taxonomy{ncbi_taxid,lineage}; source{file_path, file_format SBML|JSON|MAT, origin, namespace_convention, checksum}; stats; biomass/exchange compartment; abundance(+bounds). **pickle 금지.**
HostModel/Medium/Scenario 유지. AggregationStore `sweep.parquet`(condition_id, axis 값, metric, value, **run_hash, status{ok|failed}, diagnostic**). run_hash 구성요소 = model/medium checksum·member set·abundance·bounds·tradeoff f·solver setting·**micom_version·cmig_core_version·namespace_mapping_decisions·flux_normalization_method**. (G3 targets[]·G5 StatsConfig는 PART II.)

## 6. 모델 품질 검증
빠른 자체 검증기(import 내장, blocker 아님) + 선택 memote deep QC. namespace gate(§4.8)는 solve 직전 적용.

## 7. 재현성
재현 = objective + 정규화 flux(pFBA+tie-break) + solver 버전 일치. **RunManifest:** inputs(checksum·env lock·namespace 결정), engine(micom exact pin·tradeoff_f), solver(growth_solver QP·flux_solver LP·tolerance·flux_report_status), algorithms(metric_mode·minimal_medium·seed·normalization), **sweep(axes·n_runs·run_hash)**, software 버전(cmig_core_version 포함), figure_specs, platform. **run_hash = model/medium checksum + member set + abundance + bounds + tradeoff f + solver setting + micom_version + cmig_core_version + namespace mapping decisions + flux normalization method.**

## 8. 비기능 요구사항
성능(계산 GUI 밖·job·Parquet·lazy graph)·보안(127.0.0.1·토큰·docker socket 미마운트·pickle 금지)·안정성(GUI 생존·cancel/retry·infeasible diagnostic·fallback·capability 강등·public API만·QP-only 표기·**namespace gate 차단**·**sandbox debounce/취소·preview run은 store/cache에 비기록(Apply/Save 시에만 승격)**)·라이선스(cobrapy LGPL 재검증·GLPK 미번들·Gurobi WLS·R 격리)·재현성(figure_spec·MICOM golden 승격·**sweep/stats 방법·seed 기록**·**run_hash에 micom/cmig 버전·namespace 결정·normalization 포함**).

## 9. 출판용 그림 (R 별도 프로세스)
ggplot2 1차 렌더러, opt-in, figure_spec 재현, Python(plotnine/matplotlib) fallback. network=ggraph(+graphlayouts), chord=circlize, heatmap=ComplexHeatmap, 통계=ggplot2/ComplexHeatmap. Export=SVG(svglite)/TIFF(ragg 600dpi LZW)/PDF/EPS, 저널 프리셋·팔레트·폰트 임베딩. Export 워크플로: 분석 상태 자동 승계 + 결정적 레이아웃(stress) 기본 + [화면 배치 보존] override + 미리보기 + seed 저장.

---

# PART I — Implementation Baseline (MVP-0~2)

> **Baseline 범위 고정:** 아래 §10–§11과 §16 Baseline 블록이 MVP-0~2의 구현·검증 범위다. host-microbe·다중타깃·통계는 PART II로 분리하여 baseline 일정·검증 초점을 흐리지 않는다.

## 10. Baseline 분석 기능
> 출력은 §4.6 tidy 계약. solve는 §4.8 gate 통과 후 MICOM 호출.

- **AN-SINGLE:** FBA/pFBA/FVA, knockout, exchange 요약, growth feasibility, bound 편집.
- **AN-PAIR:** monoculture vs co-culture, interaction typing, CMIG-MRO, cross-feeding, 교환 대사체, 배지별 matrix.
- **AN-COMMUNITY:** MICOM solve → community/member 성장, exchange decomposition, cross-feeding edge, external profile, abundance/medium sensitivity, FVA.
- **AN-DELTA(핵심):** baseline 복제 → 멤버 추가 → 동일 조건 재solve → 차이 산출.
- **AN-SANDBOX (G1):** **reaction flux를 직접 바꾸는 기능이 아니라, reaction bound constraint를 변경하고 community problem을 재최적화하는 기능이다.** 멤버 reaction bound를 인터랙티브 제약(드래그) → **debounced 재solve(§4.2)** → baseline vs constrained **external-profile delta**. 우회 보상으로 변화 미미 시 **FVA 범위·"no significant change" 진단** 표시. 취소·되돌리기.
  - **preview vs commit(필수):** **sandbox run은 기본적으로 preview 상태(임시)이며, 사용자가 Apply/Save를 선택한 경우에만 Scenario/Run artifact로 승격한다.** preview solve는 sweep/cache/store에 기록하지 않아(또는 ephemeral 표시) sandbox 실험이 영구 store·재현 자산을 오염시키지 않는다.
- **AN-SWEEP (G4):** parameter sweep — 축{medium variant·abundance·member set·bounds·tradeoff f·solver} × 값 → **N-run 배치(job)** → long-format 집계 store `sweep.parquet`. **캐시·run hash(필수): 아래 정의의 run hash로 캐시(재계산 회피·재현성). 실패 run도 condition_id별 diagnostic으로 저장(누락 금지).** sensitivity의 일반화.
  - **Run hash 정의:** `model checksum, medium checksum, member set, abundance, bounds, tradeoff f, solver setting, MICOM exact version, CMIG core version, namespace mapping decisions, flux normalization method` 를 포함한다.

## 11. Baseline GUI
**원칙:** progressive disclosure · non-blocking(진행률·취소) · linked selection · undo/redo · 검색·필터 · tooltip=provenance · 부호 범례 상시 · command palette · 상태바 · autosave · 테마(고대비) · 한/영 토글.

- **Project Explorer / Model Manager / Medium Editor:** 트리·import(SBML/JSON/MAT)·summary·reaction/metabolite/gene 테이블(필터·정렬·다중선택)·exchange/biomass 탐지·namespace 상태(coverage%·unresolved 바로가기)·validation·medium 편집(CSV paste·preset·Check Growth·minimal medium·before/after profile).
- **Community Builder:** 멤버 추가/삭제(drag)·abundance(절대/상대·normalize)·objective·tradeoff(f) 슬라이더·추가 영향 라이브 preview·실행 전 **namespace hard gate(§4.8)**, **(G1) constraint sandbox: 멤버 reaction bound 슬라이더(drag, = bound 제약·재최적화) → 놓으면 debounced 재solve → external-profile delta 오버레이; 우회 보상 시 'no significant change'·FVA 표시; 취소·되돌리기. 드래그 중 solve는 preview(임시)이며 [Apply/Save] 시에만 Scenario/Run으로 승격.**
- **Interaction Graph Viewer(Cytoscape):** 노드/엣지 인코딩·레이아웃·필터·linked highlight·[Export Figure](§9).
- **External Profile Viewer:** net diverging bar·per-member stacked bar·heatmap·scenario diff·target dashboard·FVA error bar·**(G1) baseline vs constrained delta 오버레이**·export.
- **Scenario Compare / Delta:** A/B(또는 N)·delta 뷰·delta network·delta heatmap·동일 조건 고정 토글.
- **Sweep View(G4):** 축·값 정의·배치 실행·진행률·결과 매트릭스(condition × metric)·캐시 hit 표시·집계 export.
- **(Optional post-MVP) Metabolic Map(Escher):** map JSON/BiGG-map 보유 시에만 활성화. baseline 아님.
- **Runtime & Jobs:** runtime·solver(capability)·라이선스 상태·자원 경고·job 리스트(sweep 포함).

---

# PART II — Extension Roadmap (post-baseline)

> 설계는 확정하되 **baseline 구현·검증 범위에 포함하지 않는다.** 각 모듈은 독립 후속(MVP-3~5)으로 진행.

## 12. Host-Microbe (G2 · 선행 spike 필수)
- **Host objective 선택지:** {growth, ATP maintenance, biomass maintenance, target secretion, **viability lower-bound**}.
- **기본 정책(권장·잠정):** **host를 community objective에 포함하지 않는다.** host는 **viability/maintenance lower-bound constraint**로 두고, 미생물 community는 **MICOM cooperative tradeoff**로 푼다. host impact는 **constraint + flux readout**으로 평가(host objective를 community 최적화에 섞지 않음).
- **Compartment topology:** **apical/lumen(미생물 공유 pool)** / **basolateral/blood(host 전용·비공유)** 2-interface.
- **Sign convention (host 2-interface):**

| interface | `+` (양수) | `−` (음수) |
|---|---|---|
| lumen (apical, 미생물 공유) | host→lumen **분비** (미생물 흡수 가능) | host가 lumen에서 **흡수** (미생물 산물 소비) |
| blood (basolateral, host 전용) | host→blood **분비** (전신 배출/공급) | host가 blood에서 **흡수** (전신 공급: O₂·glucose 등) |

- **구성 옵션:** (A) MICOM 근사(host lumen-only single interface·pseudo constraint) / (B) CMIG-owned 2-compartment(MICOM 외부/후처리).
- **선행 spike(필수):** Human-GEM 1 + 미생물 2로 ① MICOM의 maintenance-objective host·비대칭 compartment 수용성 ② 솔브 시간·메모리(10k+ reactions) 측정 → (A)/(B) 결정. **spike 통과 전 본착수 금지.** 구성·결정 manifest 기록.

## 13. Dynamic FBA (AN-DFBA · Extension)
well-mixed SOA — 매 step FBA→μ·exchange; Michaelis–Menten uptake; **non-negativity**(소비≤가용·S clip); adaptive Δt; event(고갈·infeasibility); 수치 acceptance(비음수·질량보존·Δt 수렴·참조 케이스). 공간 grid는 비목표.

## 14. Consortium Search 단일·다중 타깃 (G3 · Extension)
- **목적함수:** `max(target exchange) s.t. community growth ≥ f·μ_c*, member min growth, (host viability)` — community 기본 growth와 분리.
- **다중 타깃:** `targets[]`{metabolite, direction, weight, constraint}.
  - **direction semantic preset:** `maximize_secretion`(↑분비) · `minimize_toxic_secretion`(↓독성분비) · `maximize_uptake_reduction`(잔류↓=흡수↑) · `maximize_uptake`.
  - **weighted score:** per-target flux를 **단위 정규화 후** 가중합 (정규화 필수 — 단위·스케일 상이).
  - **Pareto:** **2 타깃 기본**, 3 타깃 optional, **4+ 비권장**.
- **전략(조합 탐색):** 2–20 exhaustive / 20–100 CMIG-MRO·MIP pre-screening+greedy / 100+ feature+GA·Bayesian / abundance continuous.
- **출력:** rank별 members, per-target flux/yield, growth, abundance, key_crossfeeding, required_medium, limiting/toxic, host_impact, robustness, **pareto_rank·trade-off 곡선**, 자연어 설명.
- **GUI:** 다중 target row(방향 preset·가중치·임계)·top-k 테이블·Pareto 산점도(2D)·trade-off 곡선.

## 15. 통계 분석 (G5 · Extension · 단계 분할)
입력 = AN-SWEEP 집계 store. **통계 오용(샘플 독립성·다중검정) 경고·방법·seed manifest 기록.** StatsConfig{groups, methods, fdr_method, seed, dimred, clustering}.
- **MVP-5a (경량·우선):** 분포 요약, **effect size**, **2그룹/다그룹 검정**, **BH-FDR**(statsmodels `multipletests`: BH/BY).
- **MVP-5b:** **PCA · 클러스터링**.
- **MVP-5c:** UMAP · volcano · advanced cohort analysis.
- 통계 그림은 §9 R 렌더러(boxplot/volcano/PCA/clustering heatmap)로 출판 export.
- *잠정: 초기에는 5a까지. 5b/5c는 수요 확인 후.*

---

## 16. MVP 로드맵

### PART I — Implementation Baseline
- **MVP-0 Foundation:** PySide6 shell · Python sidecar · Engine Interface · SBML import · medium editor(기본) · FBA/pFBA · run manifest · solver capability matrix(GLPK 비번들).
- **MVP-1a Headless 커뮤니티 코어(1순위):** MICOM 통합(정확 pin·public API+documented flux) · namespace gate(§4.8) · §4.7 sign 테스트 · tidy contract · community/member growth · exchange decomposition · cross-feeding 추출 · §4.2 OSQP 후 LP pFBA. *완료: CLI 3개+ 미생물·배지에서 산출 + sign 테스트 + gate 동작 + **golden fixture 통과**.*
  - **Golden fixture 구조:** `fixtures/community_3_member/` = models(3)·medium.yaml·config.yaml(tradeoff_f·seed·micom 버전) + `expected/`: **`expected_nodes.parquet`·`expected_edges.parquet`·`expected_profile.parquet`** + `growth_expected.tsv`·`sign_expected.tsv`.
  - **Hash 규칙:** **float 컬럼은 hash 전 rounding/tolerance 적용**(예: 6 decimal·abs/rel tol) 후 정규화 hash 비교(부동소수·alternate optima 잡음 흡수).
  - **Solver별 golden 분리:** `gurobi`(full-flux)와 `osqp`(`qp_only_approximate`) expected set 보관·CI 매트릭스. `highs` 단독 및 `osqp_growth_highs_flux` hybrid는 baseline golden에서 제외한다.
- **MVP-1b GUI graph:** Cytoscape·필터·linked selection·Inspector·gate UI.
- **MVP-1c 검증:** MICOM 튜토리얼 재현 + cross-feeding sanity + sign 테스트 + **MICOM 버전 golden regression**(승격 게이트).
- **MVP-2 Delta·배지·R export·(G1) sandbox·(G4) sweep:** add-member delta · scenario compare · medium comparison·minimal medium·limiting nutrient·sensitivity · CMIG-MIP/MRO·interaction typing · R Render(SVG/TIFF·Figure Composer) · **G1 constraint sandbox** · **G4 sweep(run hash 캐시·실패 diagnostic)**.

### PART II — Extension Roadmap
- **[Spike] Host-Microbe 적합성 (G2):** Human-GEM 1+미생물 2 → MICOM 수용성·scale 측정 → 구성 (A)/(B) 결정. *baseline 병행 착수 가능.*
- **MVP-3 Host-Microbe(§12) + dFBA(§13):** spike 통과 후 host 구성(기본=objective 미포함·viability constraint) · 2-interface · mapping wizard · microbe↔host flux · host impact dashboard · well-mixed dFBA.
- **MVP-4 Consortium Search(§14):** 단일·다중 타깃(targets[]·ε-constraint/weighted·Pareto 2타깃) · pre-screening · top-k · robustness · trade-off 곡선.
- **MVP-5 통계(§15):** **5a**(분포·effect size·검정·BH-FDR) → 5b(PCA·클러스터링) → 5c(UMAP·volcano·advanced).

### 결정 필요(잠정)
ⓐ G5 범위(5a까지 vs 5b/5c 포함) · ⓑ G2 구성 (A)/(B)(spike 후) · ⓒ G3 weighted 정규화 방식·Pareto 타깃수.

---

## 17. 주요 리스크와 대응
**Baseline:** namespace mismatch→§4.8 hard gate · sign 혼동→§4.7 테스트 · alternate optima/loop→pFBA·loopless · MICOM API/버전→정확 pin·public API·golden 승격 · OSQP LP flux 부재→QP-only 표기 · **G1 sandbox 보상 우회→FVA·no-change 진단** · **G4 sweep 비용/재현→run hash 캐시·실패 diagnostic** · GLPK(GPL)→미번들 · cobrapy 라이선스→LGPL·재검증 · R GPL→프로세스 격리 · 과범위→Baseline/Extension 분리.
**Extension:** **G2 host objective/compartment 불일치·scale→선행 spike·objective 미포함 기본·2-interface** · G3 다중목적 비용/단위→정규화·ε-constraint 기본·Pareto≤2 · G5 통계 오용→BH-FDR·가정 경고·5a 우선.

## 18. 최종 결정문
CMIG는 네이티브 데스크톱 앱으로 **커뮤니티 FBA를 MICOM(정확 pin)에 위임**하고 CMIG가 namespace 정합·sign 정규화·tidy·추출·delta·sandbox·sweep·search·통계·시각화의 **부가가치 계층을 소유**한다. 문서는 **PART I Implementation Baseline(MVP-0~2: 커뮤니티 코어·delta·medium·R export·G1 sandbox·G4 sweep)** 과 **PART II Extension Roadmap(host-microbe+spike·dFBA·다중타깃 search·통계)** 로 분리하여, baseline 일정·검증 초점을 고정한다. host는 기본적으로 **community objective에 포함하지 않고 viability/maintenance constraint로 평가**하며 구성은 선행 spike로 확정한다. cooperative tradeoff는 QP growth → LP pFBA flux 재계산, solve 전 namespace hard gate. 라이선스는 cobrapy LGPL(재검증)+GLPK 미번들+R 격리.

```
Baseline(MVP-0~2): MICOM wrapper · namespace gate · sign/tidy · delta · medium · R export · G1 sandbox · G4 sweep(캐시)
Extension(MVP-3~5): [spike]→host-microbe(objective 미포함·viability constraint·2-interface) · dFBA · 다중타깃 search(ε-constraint+weighted·Pareto≤2) · 통계(5a→5b→5c)
엔진: MICOM(Apache·정확 pin·public API만) | solver: capability matrix · GLPK 미번들 · full-flux=Gurobi · OSQP=QP-only approximate
시각화: 기본 graph/profile/heatmap/delta | 출판 R→SVG·TIFF | Escher optional post-MVP
라이선스: cobrapy=LGPL(재검증)·GLPK 제외·MICOM/SMETANA/OSQP=Apache·HiGHS/Escher=MIT·R 격리·Gurobi 학술
```

---

## 부록 A. 설계 결정 요약 (크로스 검증용)
A1 MICOM 채택(public API+documented flux만·정확 pin·golden 승격) · A2 네이티브 우선 · A3 R 시각화 전용·프로세스 격리 · A4 Export 레이아웃(상태 승계+결정적+override) · A5 재현성(growth QP/flux LP 분리) · A6 solver capability matrix(OSQP QP 전용·HiGHS-QP exp·GLPK 제외) · A7 라이선스(cobrapy LGPL 재검증·GLPK 미번들·R 격리) · A8 Escher optional post-MVP · A9 CMIG-MIP/MRO(+ SMETANA-compatible) · A10 namespace hard gate(MVP-1a blocker) · **A11 (G1) sandbox = bound constraint 변경+재최적화(flux 직접 변경 아님)·우회 보상 시 FVA/no-change·preview 기본·Apply/Save 시에만 artifact 승격** · **A12 (G2) host = community objective 미포함·viability constraint 기본·2-interface(lumen/blood) sign·구성 A/B는 spike 후** · **A13 (G3) target 최대화는 growth와 분리·weighted 단위 정규화 필수·Pareto≤2 기본** · **A14 (G4) sweep run hash 캐시(model/medium/member/abundance/bounds/tradeoff/solver+micom·cmig 버전·namespace 결정·normalization)·실패 diagnostic** · **A15 (G5) 통계 5a(검정+BH-FDR) 우선·5b/5c 후속·오용 경고** · **A16 Baseline/Extension 분리로 baseline 스코프 고정** · **A17 MVP-1a golden: parquet 분리·float rounding/tolerance 후 hash·solver별(gurobi/osqp) 분리.**
