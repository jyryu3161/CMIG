---
template: schema
version: 1.0
feature: cmig-community-core
project: CMIG (Community Metabolic Interaction GUI)
phase: Phase 1 — Schema
authoritative_source: CMIG_명세서_v3.0.md (§1–§11, §16, 부록 A)
date: 2026-05-31
status: Draft
scope: PART I Implementation Baseline (MVP-0~2)
---

# CMIG Baseline 데이터 모델 명세 (Data Model Schema)

> **권위 자료 (authoritative source)**: `CMIG_명세서_v3.0.md` (§1–§11, §16, 부록 A).
> 본 문서는 명세(spec)와 **모순되지 않으며**, 모든 필드·규칙·불변식(invariant)에 spec 섹션 앵커(예: §4.6, §5, §7, §4.8)를 단다. spec에 명시되지 않은 값은 `(Design에서 확정)`으로 표기한다.
> **범위 (scope)**: PART I Baseline (MVP-0~2). host-microbe(G2)·dFBA·다중타깃(G3)·통계(G5)는 **PART II (범위 외 / out of scope)** 로만 표기한다.

---

## 1. 개요 (Overview)

### 1.1 목적 (Purpose)
CMIG Baseline의 **데이터 모델(data model)** 을 정식화한다. 검증된 클러스터 fragment의 entities/fields/invariants를 종합하여, 분석 산출의 **단일 출력 계약(single output contract)** 인 tidy 데이터 계약(§4.6), 도메인 엔티티(§5), 재현성(§7), 그리고 sweep 집계 스토어(§5)를 하나의 일관된 스키마로 고정한다.

### 1.2 책임 경계 (Ownership)
- **MICOM 위임 (delegated, is_cmig_owned=false)**: community FBA·cooperative tradeoff (§4.1·§4.2).
- **CMIG 소유 (owned, is_cmig_owned=true)**: namespace 정합·gate·sign 정규화·tidy 계약·cross-feeding/interaction 추출·delta·CMIG-MIP/MRO·sandbox·sweep (§2·§4.1).

### 1.3 스키마 버전·tidy 단일 계약 원칙 (Schema Version & Single Tidy Contract)
- **단일 계약 (single contract, §4.6)**: 모든 분석 산출은 `nodes / edges / profile / matrix / timecourse` (parquet) 5종의 tidy 계약으로만 출력된다. 전 소비자(graph viewer·profile·delta·sweep·R export)는 **단일 reader**를 경유한다 (§4.6·Plan §6.3).
- **스키마 버전 필드 (schema_version)**: tidy 계약과 AggregationStore(`sweep.parquet`)는 `schema_version` 필드를 가지며, 스키마/계약 변경 시 bump한다 (Plan §6.2·§6.3 파생; spec §4.6/§5는 컬럼 표준명을 미상세 → `(Design에서 확정)`).
- **직렬화 정책 (serialization policy, §5·§8)**: 허용 직렬화는 **Parquet/Arrow/JSON/YAML/SQLite** 뿐이다. **pickle 금지 (보안)**. tidy 산출=Parquet, 메타=YAML+SQLite.
- **결정적 재현 (deterministic reproducibility, §7)**: 재현 = objective + 정규화 flux(pFBA+tie-break) + solver 버전 일치. 재현성 키는 `run_hash` (정확히 11개 구성요소, §4·§7·§10).

---

## 2. Tidy 데이터 계약 (Tidy Data Contract, §4.6)

> **계약 정의 (§4.6)**: `nodes / edges / profile / matrix / timecourse` (parquet). sweep store는 §4.6에서 명시적으로 §5로 **카브아웃(carve-out)** 된다 → AggregationStore는 §6 참조.
> **컬럼 표준명 주의**: spec §4.6은 5종의 존재만 정의하고 각 컬럼 표준명은 미상세하다. 아래 컬럼은 verified fragment의 entity 필드(§4.3·§4.6·§16)에서 도출한 권장 스키마이며, 정확한 컬럼 표준명·`edge_type` 전체 집합은 `(Design에서 확정 — Phase 1 Schema 권장)`이다.
> **부호 규약 (§4.3)**: flux/weight 부호는 §4.3 규약을 따르며 — `+`=환경으로 분비(secretion)·`−`=환경에서 흡수(uptake)·net=환경 exchange. 모든 부호 변환은 §4.7 단일 진입점(single entry point)을 경유한다.

### 2.1 `nodes.parquet` — 노드 (커뮤니티 멤버·환경 pool)

| name | type | unit | nullable | desc | anchor |
|------|------|------|----------|------|--------|
| schema_version | string | — | false | tidy 계약 스키마 버전 (단일 reader·계약 테스트 기준). | §4.6·Plan §6.3 |
| node_id | string | — | false | 노드 고유 식별자 (member id 또는 환경 pool 식별자). graph 노드 키. | §4.6·§11 |
| node_type | enum{member, environment_pool} | — | false | 노드 종류 (멤버 또는 공유 exchange pool). `(enum 표준명 Design에서 확정)` | §4.3·§4.6 |
| label | string | — | true | 표시 라벨 (species/organism 등). UI/그래프 노드 라벨. | §5·§4.6 |
| growth | float64 | mmol/gDW/h (또는 1/h) | true | member/community growth (μ). status=ok에서 유효. growth 단위는 `(Design에서 확정)`. | §4.2·§10·§16 |
| abundance | float64 | dimensionless (normalize 시 상대; 절대 모드 표현은 OD-4 `Design에서 확정`) | true | 멤버 abundance. normalize 적용 시 합=1.0. environment_pool에는 미적용(null). | §5·§11 |

### 2.2 `edges.parquet` — 엣지 (cross-feeding 상호작용)

| name | type | unit | nullable | desc | anchor |
|------|------|------|----------|------|--------|
| schema_version | string | — | false | tidy 계약 스키마 버전. | §4.6·Plan §6.3 |
| metabolite | string | — | false | 교환 대사체 식별자 (canonical/pool namespace). source가 분비, target이 흡수. | §4.3·§4.6 |
| source_member | string | — | false | 분비 멤버 m (raw_flux>0/+, label=secretion). edge 방향 출발. | §4.3 |
| target_member | string | — | false | 흡수 멤버 m′ (raw_flux<0/−, label=uptake). edge 방향 도착. | §4.3 |
| weight | float64 | mmol/gDW/h | false | cross-feeding 강도 = min(\|source 분비량\|, \|target 흡수량\|). 항상 ≥0 (ui_flux는 magnitude). | §4.3 |
| edge_type | enum{cross_feeding, ...} | — | true | edge 종류. baseline 추출 대상=cross_feeding. interaction typing/MIP·MRO 등 추가 집합은 `(Design에서 확정)`. | §4.5·§4.6 |

### 2.3 `profile.parquet` — 외부 프로파일 (external metabolite profile)

| name | type | unit | nullable | desc | anchor |
|------|------|------|----------|------|--------|
| schema_version | string | — | false | tidy 계약 스키마 버전. | §4.6·Plan §6.3 |
| metabolite | string | — | false | 환경(외부 medium pool)과 교환되는 대사체 식별자. | §4.3·§4.6 |
| net_flux | float64 | mmol/gDW/h | true | community↔환경 net exchange flux. `+`=환경으로 분비·`−`=환경에서 흡수 (§4.3). status=failed에서 결측. | §4.3·§4.6 |
| label | enum{uptake, secretion} | — | true | net_flux 부호의 의미 라벨 (단일 진입점 산출). | §4.3·§4.7 |
| member_contribution | float64 | mmol/gDW/h | true | 멤버↔pool 기여 (exchange decomposition). 멤버별 분해 행에서 유효. | §4.3 |
| fva_min | float64 | mmol/gDW/h | true | FVA 하한 (보상 우회 변화 미미 시 범위 표시). | §10·§11 |
| fva_max | float64 | mmol/gDW/h | true | FVA 상한. | §10·§11 |

### 2.4 `matrix.parquet` — 매트릭스 (condition × metric 등)

> spec §4.6은 `matrix`의 존재만 명시한다. AN-PAIR의 배지별 matrix·Scenario Compare의 condition×metric 표현에 사용되는 long/wide 산출이며, 정확한 컬럼 표준명은 `(Design에서 확정)`이다.

| name | type | unit | nullable | desc | anchor |
|------|------|------|----------|------|--------|
| schema_version | string | — | false | tidy 계약 스키마 버전. | §4.6·Plan §6.3 |
| row_key | string | — | false | 행 키 (예: condition·member·medium variant). `(표준명 Design에서 확정)` | §4.6·§10 |
| col_key | string | — | false | 열 키 (예: metric·대상 멤버). `(표준명 Design에서 확정)` | §4.6·§10 |
| value | float64 | metric 종속 | true | 셀 값. 단위는 metric 종속 `(Design에서 확정)`. | §4.6 |

### 2.5 `timecourse.parquet` — 타임코스 (PART II placeholder)

> **PART II (범위 외 / out of scope)**: `timecourse`는 §4.6 tidy 계약 5종에 명명되어 있으나, 시간 의존 산출(dFBA, AN-DFBA §13)은 **PART II Extension (§13)** 범위다. Baseline(MVP-0~2)에서는 **컬럼을 채우지 않는 placeholder**로만 둔다. 컬럼 표준명·schema는 PART II에서 확정한다.

| name | type | unit | nullable | desc | anchor |
|------|------|------|----------|------|--------|
| — (placeholder) | — | — | — | **PART II (§13 dFBA) 범위 — Baseline 비대상.** tidy 계약 5종 명명에만 포함. | §4.6·§13 (PART II) |

---

## 3. 도메인 엔티티 (Domain Entities, §5)

> **직렬화 (§5·§8)**: 모든 도메인 엔티티는 Parquet/Arrow/JSON/YAML/SQLite로만 직렬화한다. **pickle 금지**.
> **HostModel**: §5에서 'HostModel/Medium/Scenario 유지'로 호명되나(stub), 본격 구성은 **PART II Extension (§12 G2 host-microbe) 범위 외**다. §3.5 stub 참조.

### 3.1 MemberModel — 단일 미생물 GEM 멤버 (§5)

**목적**: 커뮤니티의 단일 미생물 GEM(genome-scale metabolic model) 멤버를 표현. community 조립의 기본 단위이자 namespace gate·sign 정규화의 대상.

| name | type | unit | nullable | desc | anchor |
|------|------|------|----------|------|--------|
| id | string | — | false | 멤버 고유 식별자 (member set 내 유일). cross-feeding·delta의 멤버 키. | §5 |
| name | string | — | true | 사람이 읽는 표시명 (species/organism). | §5 |
| strain | string | — | true | 균주(strain) 식별. 동일 species 내 변종 구분. | §5 |
| taxonomy.ncbi_taxid | string | — | true | NCBI Taxonomy ID. string 보관 권장(선행 0 안전성); 표현 타입은 `(Design에서 확정)`. | §5 |
| taxonomy.lineage | list&lt;string&gt; | — | true | 분류 계통(lineage) 경로 (상위→하위). | §5 |
| source.file_path | string | — | false | import 원본 모델 파일의 절대 경로. | §5 |
| source.file_format | enum{SBML, JSON, MAT} | — | false | 모델 직렬화 포맷. SBML\|JSON\|MAT만 허용. **pickle 금지**. | §5·§8 |
| source.origin | string | — | true | 모델 출처(provenance) — 예: BiGG·AGORA·user. 허용값 집합은 `(Design에서 확정)`. | §5 |
| source.namespace_convention | string | — | true | exchange/metabolite ID namespace 규약 (예: bigg·kegg·metanetx·seed). gate(§4.8) 입력. 허용값 enum은 `(Design에서 확정)`. | §4.8·§5 |
| source.checksum | string | — | false | 원본 파일의 결정적 해시. run_hash 구성요소 #1 (model checksum). 해시 알고리즘은 `(Design에서 확정)`. | §5·§7·§10 |
| stats | struct{n_reactions:int, n_metabolites:int, n_genes:int, n_exchanges:int} | — | true | 모델 요약 통계. 정확한 필드 집합은 `(Design에서 확정)` — spec은 'stats'로만 명시. | §5 |
| biomass_compartment | string | — | true | biomass(objective) reaction의 compartment 식별자. growth feasibility 기준. | §5·§11 |
| exchange_compartment | string | — | true | exchange reaction의 compartment 식별자. exchange 탐지·sign 정규화·profile 추출 기준. | §5·§11 |
| abundance | float64 | dimensionless(상대) 또는 cell/biomass(절대) | true | 멤버 존재비 선언값. Scenario.abundance_overrides가 우선. normalize 대상. 단위는 `(Design에서 확정)`. | §5·§11 |
| abundance_bounds | struct{lower:float64, upper:float64} | abundance와 동일 | true | abundance 허용 범위 (+bounds). sweep·sensitivity 축의 멤버별 경계. | §5 |

### 3.2 Medium — 배지 (외부 대사체 환경) (§4.5·§5·§10)

**목적**: 외부 대사체 환경(배지) 정의 — exchange 가용성 구성. minimal medium 산출은 cardinality MILP이므로 MILP capability(Gurobi/HiGHS/CPLEX) 필요. solve 전 §4.8 gate 대상.

| name | type | unit | nullable | desc | anchor |
|------|------|------|----------|------|--------|
| id | string | — | false | 배지 식별자. Scenario·sweep medium variant 키. | §5 |
| name | string | — | true | 배지 표시명 (예: M9, minimal, gut-diet). | §5 |
| composition | list&lt;struct{metabolite_id:string, lower_bound:float64, upper_bound:float64}&gt; | mmol/gDW/h (flux; `Design에서 확정`) | false | exchange 대사체별 흐름 경계 — 가용성 정의. uptake 허용=음수 lower_bound (§4.3). | §4.3·§4.5·§5 |
| preset | string | — | true | 사전 정의 배지 preset 식별자 (CSV paste·preset 선택). 카탈로그는 `(Design에서 확정)`. | §5·§11 |
| is_minimal | bool | — | true | minimal medium(cardinality MILP) 산출 여부. true 산출은 MILP capability 요구. | §2·§4.5 |
| minimal_U_default | list&lt;string&gt; | — | true | minimal medium 무조건 포함 기본 집합 U = {H₂O, H⁺, Pi}. invariant로 강제. | §4.5 |
| oxygen_mode | enum{aerobic, anaerobic} | — | true | O₂ 옵션 — 호기(O₂ 포함)/혐기(O₂ 제외). minimal medium·growth 분기. | §4.5 |
| checksum | string | — | false | 배지 정의의 결정적 해시. run_hash 구성요소 #2 (medium checksum). 알고리즘은 `(Design에서 확정)`. | §5·§7·§10 |
| namespace_convention | string | — | true | 배지 metabolite ID namespace 규약. member exchange와의 정합(§4.8)에 사용. | §4.8·§5 |

### 3.3 Scenario — 재현 가능한 분석 실행 단위 (§5·§10·§11·A11)

**목적**: 재현 가능한 분석 실행 단위 = medium + constraints + member set + config(tradeoff f·seed·solver·flux_normalization_method). preview(임시)/commit(artifact 승격) 상태를 가진다.

| name | type | unit | nullable | desc | anchor |
|------|------|------|----------|------|--------|
| id | string | — | false | Scenario 식별자. Scenario Compare(A/B/N)·delta·run_hash 연계 키. | §5·§11 |
| name | string | — | true | Scenario 표시명. | §5 |
| state | enum{preview, commit} | — | false | preview=임시(store/cache/sweep 비기록 또는 ephemeral), commit=Apply/Save로 artifact 승격. **기본=preview**. | §10 AN-SANDBOX·A11 |
| medium_ref | string | — | false | 사용 배지 참조(Medium.id) 또는 임베드. | §5 |
| member_set | list&lt;string&gt; | — | false | 포함 멤버 id 목록(MemberModel.id 참조). run_hash 구성요소 #3. | §5·§7 |
| constraints | list&lt;struct{reaction_id:string, member_id:string, lower_bound:float64, upper_bound:float64, source:enum{user_edit, sandbox}}&gt; | flux (`Design에서 확정`) | true | 추가 bound 제약 (sandbox bound 제약 포함 — flux 직접 변경 아님). source 태그로 sandbox 구분. run_hash 구성요소 #5 (bounds). | §10·§11·A11 |
| config.tradeoff_f | float64 | dimensionless | false | MICOM cooperative tradeoff f (μ_c ≥ f·μ_c*). 범위 0<f≤1. run_hash 구성요소 #6. | §4.2·§5·§7 |
| config.seed | int | — | true | 결정적 재현용 seed (tie-break·sweep). manifest 기록. | §7·§8 |
| config.solver | struct{growth_solver:enum{osqp,gurobi,cplex,highs}, flux_solver:enum{gurobi,highs,cplex}, tolerance:float64} | — | false | growth(QP)·flux(LP) solver 분리 설정. growth 기본=OSQP. flux LP=Gurobi/HiGHS/CPLEX. run_hash 구성요소 #7 (solver setting). | §4.2·§5·§7·A6 |
| config.flux_normalization_method | enum{pfba, ...} | — | true | flux 정규화 방법 (예: pFBA+tie-break). run_hash 구성요소 #11. enum은 `(Design에서 확정)`. | §4.2·§4.4·§7 |
| cmig_core_version | string | — | true | CMIG core 버전. run_hash 구성요소 #9. §5 엔티티 필드 미명시 — commit/manifest 주입 가정, 보유 위치는 `(Design에서 확정)`. | §7·§8 |
| abundance_overrides | list&lt;struct{member_id:string, abundance:float64}&gt; | abundance 단위 | true | Scenario별 abundance 재정의. MemberModel.abundance(선언)보다 우선. run_hash 구성요소 #4. | §5·§7·§11 |
| run_hash | string | — | true | commit 시 산출되는 재현성 키 (11개 구성요소 해시). **preview에서는 null 또는 ephemeral**. | §5·§7·§10 |
| namespace_mapping_decisions | list&lt;struct{exchange_id:string, mapped_id:string, confidence:enum{high,low}, status:enum{resolved,unresolved}}&gt; | — | true | gate가 내린 mapping 결정 (§4.8). audit trail이자 run_hash 구성요소 #10. unresolved high-confidence는 solve 차단. | §4.8·§5·§7 |

### 3.4 CommunityModel — MICOM community 조립체 (§4.1·§4.5·§5)

**목적**: MICOM community 조립체(assembly) = member set + abundance + medium. MICOM `cooperative_tradeoff` solve의 입력 객체. community solve는 MICOM에 위임(public API only); CMIG는 namespace 정합·sign 정규화 부가가치 계층 소유.

| name | type | unit | nullable | desc | anchor |
|------|------|------|----------|------|--------|
| id | string | — | false | CommunityModel 식별자. | §5 |
| members | list&lt;struct{member_id:string, abundance:float64}&gt; | abundance: dimensionless (normalize 후) | false | 조립된 멤버 + 정규화된 abundance. abundance는 (Scenario.abundance_overrides > MemberModel.abundance) 해소 후 normalize. normalize 시 합=1.0. | §4.5·§5·§11 |
| medium_ref | string | — | false | 적용 배지 참조(Medium.id) 또는 임베드. | §5 |
| objective | string | — | true | community objective — MICOM community growth (Σ a_m μ_m). host objective 결합은 **PART II §12 범위 외**. | §4.2·§12 |
| tradeoff_f | float64 | dimensionless | true | cooperative tradeoff f. Scenario.config로부터 전달. 0<f≤1. | §4.2 |
| micom_version | string | — | true | 정확 pin된 MICOM 버전(micom==X.Y.Z). run_hash 구성요소 #8. golden 승격 게이트 대상. | §4.1·§7 |
| namespace_gate_status | enum{passed, blocked, warning} | — | true | solve 직전 namespace hard gate 결과 (§4.8). blocked면 solve 불가. warning은 low-confidence 진행. | §4.8 |
| exchange_compartment_pool | string | — | true | community 공유 exchange pool(환경) compartment — net 환경 exchange·멤버↔pool 분해 기준. | §4.3 |

### 3.5 HostModel — 사람세포/host GEM 엔티티 (§5 stub · PART II 범위 외)

> **PART II (범위 외 / out of scope)**: §5에서 'HostModel/Medium/Scenario 유지'로 호명되나(stub), 본격 구성(2-interface lumen/blood·viability constraint·objective)은 **PART II Extension (§12 G2 host-microbe)** 범위로 선행 spike 후 확정한다. Baseline 엔티티 계약에는 **stub만 포함**하며, 본 Schema의 정의 대상이 아니다.

| name | type | unit | nullable | desc | anchor |
|------|------|------|----------|------|--------|
| — (stub) | — | — | — | **PART II (§12 G2) 범위.** 2-interface(lumen/blood)·viability constraint·host objective는 §12에서 확정. | §5(stub)·§12 (PART II) |

---

## 4. 재현성 (Reproducibility, §7)

> **재현 정의 (§7)**: 재현 = objective + 정규화 flux(pFBA+tie-break) + solver 버전 일치.

### 4.1 RunManifest 구조 (§7·§2)

단일 community/single solve(또는 sweep run)의 완전한 재현 메타데이터를 결정적으로 기록하는 권위 레코드. (메타 직렬화=YAML+SQLite, 산출=Parquet; pickle 금지, §3·§8.)

| 블록 (block) | 구성 (composition) | run_hash 연결 | anchor |
|-------------|-------------------|--------------|--------|
| **inputs** | model_checksum · medium_checksum · **env_lock** · namespace_decisions | model/medium checksum (#1·#2), namespace_mapping_decisions (#10). **env_lock은 run_hash 미포함**. | §7·§4.8·§10 |
| **engine** | micom_version (exact pin) · tradeoff_f | micom_version (#8), tradeoff f (#6) | §7·§4.1·§4.2 |
| **solver** | growth_solver(QP) · flux_solver(LP) · tolerance · flux_report_status | solver setting (#7) | §7·§4.2 |
| **algorithms** | metric_mode · minimal_medium · seed · normalization | flux_normalization_method (#11) | §7·§4.4·§4.5 |
| **sweep** | axes · n_runs · run_hash | sweep 블록 (단일 run에서는 null) | §7·§10 |
| **software** | cmig_core_version | cmig_core_version (#9) | §7 |
| **figure_specs** | list&lt;FigureSpec&gt; (R 렌더러 재현·seed) | — (그림 미생성 시 빈 리스트 `[]`, null 아님) | §7·§9 |
| **platform** | os{macos,windows,linux} · arch{arm64,x64} | — | §7·§1 |
| **run_hash** | 이 manifest 입력으로부터 산출된 정규화 hash (11 구성요소) | manifest↔run_hash 일관성 | §7·§10 |
| **manifest_schema_version** | manifest/계약 스키마 버전 (구성요소 변경 시 bump) | — | Plan §6.2·§6.3 |

**solver 블록 상세**:
- `growth_solver` enum{osqp, gurobi, cplex, highs} — member growth L2(QP). 기본 경로=OSQP. (enum 멤버 순서는 §3.3 config.solver와 통일.) (§4.2·§2).
- `flux_solver` enum{gurobi, highs, cplex}, **nullable** — pFBA/normalization(LP) 재계산. 부재 시 null + `flux_report_status='QP-only approximate'` (§4.2·§4.4).
- `flux_report_status` enum{full, QP-only approximate} — 'full'은 LP 재계산 완료 표현용 명칭으로 **spec 미명시 (명칭 `Design에서 확정`)**. 'QP-only approximate'만 spec 명시 (§4.2·§4.4).
- `tolerance` float64 — solver 수치 tolerance. golden float rounding/tolerance와 정합. 구체 값은 `(Design에서 확정)` (§4.2·§16).

### 4.2 run_hash — 11개 구성요소 (번호 매김) (§5·§7·§10·부록 A14)

> run_hash는 단일 solve/sweep run 입력의 **결정적(deterministic) 동일성 식별자**이자 AN-SWEEP **캐시 키**다. 정확히 **11개 구성요소**를 정규화·직렬화하여 hash한다. **빠짐·추가 금지**.
> **주의**: §5/§7의 'model/medium checksum' 압축 표기는 **model checksum + medium checksum 2개**를 합친 것으로, 분리하면 11개다.

| # | 구성요소 (component) | 출처 엔티티 / 필드 | anchor |
|---|---------------------|-------------------|--------|
| **1** | model checksum | MemberModel.source.checksum (집합) / RunManifest.inputs.model_checksum | §5·§7·§10 |
| **2** | medium checksum | Medium.checksum / RunManifest.inputs.medium_checksum | §5·§7·§10 |
| **3** | member set | Scenario.member_set (멤버 id 결정적 정렬) | §5·§7·§10 |
| **4** | abundance | 해소(Scenario.abundance_overrides > MemberModel.abundance)·정규화 후 값 | §5·§7·§11 |
| **5** | bounds | Scenario.constraints (reaction bound; sandbox commit 반영) | §5·§7·§10 |
| **6** | tradeoff f | Scenario.config.tradeoff_f (0<f≤1) | §4.2·§7·§10 |
| **7** | solver setting | growth_solver(QP) + flux_solver(LP) + tolerance + 옵션 | §4.2·§7·§10 |
| **8** | micom_version | MICOM exact version (micom==X.Y.Z) | §4.1·§7·§10 |
| **9** | cmig_core_version | CMIG core version | §7·§10 |
| **10** | namespace_mapping_decisions | gate(§4.8) 매핑 결정 (결정적 직렬화) | §4.8·§7·§10 |
| **11** | flux_normalization_method | flux 정규화 방법 (pFBA+tie-break 등) | §4.4·§7·§10 |

**`env_lock`은 11개 구성요소에 포함되지 않는다** — RunManifest.inputs에만 기록한다 (§7·§10·Plan §8.3).

### 4.3 float rounding/tolerance·결정적 해시 규칙 (§16·§10·부록 A17)

- **float rounding/tolerance**: float 구성요소(abundance·bounds·tradeoff_f 등) 및 golden 비교 시 float 컬럼은 **hash 전** rounding/tolerance(spec 예: **6 decimal**·abs/rel tol)를 적용한 뒤 정규화 hash한다. 부동소수(floating point)·alternate optima 잡음을 흡수하여 결정적 비교를 보장한다. 정확한 decimal 자릿수·abs tol·rel tol·rounding vs tolerance 택일/병행은 `(Design에서 확정)` (§16·A17).
- **결정성 (determinism)**: 동일 11구성요소 → 동일 hash(캐시 hit); 1개라도 변경 → 다른 hash(miss·재계산) (§10·부록 A14).
- **canonical 직렬화 (canonical serialization)**: 11구성요소의 정규화·직렬화 순서·구분자·인코딩, hash 알고리즘(예: SHA-256)은 `(Design에서 확정)` — spec은 '정규화 hash·결정적'만 명시 (§10·§16·Plan §8.2).
- **단일 정의 (single definition)**: AggregationStore.run_hash · RunManifest.run_hash · Scenario.run_hash는 **동일 11구성요소·동일 직렬화·동일 해시 함수**로 산출되어 비트 단위로 일치해야 한다 (§5·§7·§10).
- **버전 bump**: run_hash 구성요소 정의(11개)가 변경되면 sweep 캐시를 무효화하고 `manifest_schema_version`을 bump하며 캐시 마이그레이션 정책을 적용한다 (Plan §6.2·§6.3).

---

## 5. Solver Capability Matrix (§2·부록 A6·§16)

> 분석 유형(LP/QP/MILP)별 사용 가능 solver와 제약을 명시한다. **capability 부재 시 해당 분석만 비활성화** (앱 전체 강등 아님).

### 5.1 problem_class × solver

| problem_class | 사용 가능 solver (solvers) | 비고 (notes) | anchor |
|---------------|---------------------------|--------------|--------|
| **LP** (pFBA/FVA/flux 정규화·minimal medium LP) | Gurobi · HiGHS · CPLEX · OSQP-hybrid | flux 재계산 경로 | §2·A6 |
| **QP** (member growth L2) | Gurobi · OSQP · CPLEX (+ **HiGHS experimental**) | growth solve | §2·A6 |
| **MILP** (cardinality minimal medium) | Gurobi · HiGHS · CPLEX | minimal medium | §2·§4.5·A6 |

### 5.2 solver별 capability·정책

| solver | LP | QP | MILP | 라이선스 (license) | 번들 (bundled) | 비고 (notes) | anchor |
|--------|:--:|:--:|:----:|-------------------|:--------------:|--------------|--------|
| **Gurobi** | ✅ | ✅ | ✅ | commercial-academic | ❌ (미번들) | **기본 solver (default)** (Plan §7.2; spec §2='권장'). CI=Gurobi WLS. | §2·Plan §7.2 |
| **HiGHS** | ✅ | ⚠️ experimental | ✅ | MIT | ✅ | HiGHS-QP=experimental. 무라이선스 경로. | §2·A6 |
| **OSQP** | ✅ | ✅ | ❌ | Apache+MIT(HiGHS) | ✅ | optlang hybrid alias: QP=OSQP, LP/pFBA=HiGHS. | §2·§4.2·A6 |
| **CPLEX** | ✅ | ✅ | ✅ | commercial-academic | ❌ (미번들) | 상용 학술. | §2·A6 |
| **GLPK** | ✅ | ❌ | ✅ | **GPL** | ❌ (**미번들**) | GPL → 번들/배포 제외. matrix에 존재하되 is_bundled=false. | §2·A6·A7 |

### 5.3 정책 불변식 (policy invariants)
- **OSQP hybrid alias**: cobra/optlang의 `solver="osqp"`는 QP를 OSQP로, LP/pFBA를 HiGHS로 푸는 hybrid interface다. LP/HiGHS 부재 시에만 'QP-only approximate' 표기를 고려한다 (§4.2·A6).
- **disable_analysis_on_missing=true**: capability 부재 시 해당 분석만 비활성화 (§2·§8 NFR Reliability).
- **golden solver 변형 2종**: `gurobi`(full) · `osqp`(full; OSQP-QP + HiGHS-LP) — CI 매트릭스 (§16·A17·Plan §7.2). 별도 `osqp_growth_highs_flux` 이름은 폐기한다.
- **HiGHS-QP(experimental) baseline 노출 여부**는 `(Design에서 확정)` (§2·A6).

---

## 6. AggregationStore — `sweep.parquet` (§5·§10·§4.6 카브아웃·부록 A14)

> **§4.6 카브아웃**: AggregationStore(`sweep.parquet`)는 §4.6 tidy 5종(nodes/edges/profile/matrix/timecourse)에 속하지 **않고**, §4.6이 명시적으로 §5로 위임한 별개의 스토어다. long-format(좁은 형태)으로 단일 reader/스키마 버전 필드를 통해 소비된다.
> **직렬화**: Parquet/Arrow만 사용 (JSON/YAML/SQLite는 manifest/meta용). **pickle 금지** (§5·§8).

### 6.1 컬럼 표 (columns)

| name | type | unit | nullable | desc | anchor |
|------|------|------|----------|------|--------|
| schema_version | string | — | false | AggregationStore 스키마 버전 (단일 reader·계약 테스트 기준). spec §5/§10 미명시 → Plan §6.2/§6.3 파생. 표기 규칙은 `(Design에서 확정)`. | Plan §6.2·§6.3 |
| condition_id | string | — | false | sweep 그리드 내 한 조건(축 값 조합) 식별자. 동일 condition_id 행은 동일 축 값·동일 run_hash 공유. 생성 규칙(인덱스 vs 결정적 슬러그)은 `(Design에서 확정)`. | §5·§10 |
| axis_medium_variant | string | — | true | 축 값 — medium variant 식별자(배지 조합/preset id). | §10 |
| axis_abundance | string | — | true | 축 값 — abundance 설정 식별자/벡터 참조. 표현형(스칼라 vs 참조 vs 해시)은 `(Design에서 확정)`. | §10·§5 |
| axis_member_set | string | — | true | 축 값 — member set 식별자(결정적 정렬 해시/슬러그). | §10·§5 |
| axis_bounds | string | — | true | 축 값 — reaction bound 변주 식별자. 직렬화는 `(Design에서 확정)`. | §10 |
| axis_tradeoff_f | float64 | dimensionless | true | 축 값 — cooperative tradeoff f. run_hash 진입 시 float rounding/tolerance 적용 (A17). 범위(0<f≤1)는 `(Design에서 확정)`. | §10·§4.2 |
| axis_solver | enum{gurobi\|highs\|osqp\|cplex\|...} | — | true | 축 값 — solver setting 식별자 (§2 matrix 기반). `osqp_growth_highs_flux`는 golden 세트 명이지 solver 축 값 아님. 전체 집합은 `(Design에서 확정)`. | §10·§2 |
| metric | string | — | false | 행이 보고하는 측정량 이름 (예: community_growth·member_growth·exchange_flux). 허용 도메인 enum은 `(Design에서 확정)`. | §5·§10 |
| value | float64 | metric 종속 (flux=mmol/gDW/h 류, `Design 확정`) | true | metric의 수치 결과. status=ok에서 유효, failed에서 결측(null). exchange_flux 류는 §4.3 부호 규약 준수. | §5·§4.3·§4.7 |
| run_hash | string | — | false | 이 condition을 생성한 solve의 재현성·캐시 키 (11구성요소 해시). 동일 condition_id 행 전체 공유. 캐시 hit/miss 판정 기준. | §5·§7·§10·A14 |
| status | enum{ok, failed} | — | false | run 결과 상태. ok=정상 solve, failed=infeasible/solver 오류. **실패 run도 기록(누락 금지)**. | §5·§10 |
| diagnostic | string | — | true | 진단 메시지/구조 (infeasible 원인·capability 강등·QP-only). status=failed에는 **필수(≠null)**, ok에서는 null 가능. 구조(JSON 문자열 vs 구조화)는 `(Design에서 확정)`. | §5·§10·§4.4 |

### 6.2 캐시 키 의미 (cache-key semantics) (§10·§11·부록 A14)

- **캐시 hit / miss**: 동일 run_hash가 store에 존재하면 **hit**(재계산 회피·기존 행 재사용); 부재하면 **miss**(MICOM 재solve 후 행 append). Sweep View는 hit 여부를 표시 (§10·§11).
- **결정성**: run_hash 11구성요소가 모두 동일 → hit; 1개라도 변경 → miss·재계산 (§10·부록 A14·SC-4).
- **실패 누락 금지**: status=failed인 run도 condition_id별 diagnostic으로 반드시 보관 (§5·§10·부록 A14).
- **preview 비오염**: G1 sandbox preview solve는 sweep/cache/store에 기록하지 **않는다**. Apply/Save 시에만 Scenario/Run artifact로 승격되어 AggregationStore에 진입 (§10·§11·§8·A11·SC-8).
- **sweep manifest 정합**: `RunManifest.sweep.n_runs = Π(축별 n_values) = len(run_hash 목록)` = 논리 condition 총수 (캐시 hit/miss 무관) (§7·§10).
- **sweep 축 (axes) 폐쇄 enum (6종)**: {medium variant · abundance · member set · bounds · tradeoff f · solver}. 그 외 축은 범위 외 (§10).
- **캐시 무효화**: run_hash 구성요소 정의 변경 시 기존 sweep 캐시 무효화·버전 bump·마이그레이션 정책 적용 (Plan §6.2·§6.3).

---

## 7. NamespaceDecision + Gate 규칙 + Golden fixture 디렉토리 구조 (§4.8·§6·§16·부록 A17)

### 7.1 NamespaceDecision — 매핑 결정 레코드 (§4.8·§5·§7·§10)

exchange 대사체(metabolite) 매핑 결정 1건의 audit 레코드. (1) gate 판정 입력, (2) audit trail 단위, (3) run_hash 구성요소 #10(namespace_mapping_decisions)의 원소.

| name | type | unit | nullable | desc | anchor |
|------|------|------|----------|------|--------|
| metabolite | string | — | false | 매핑 대상 exchange 대사체 식별자 (예: glc__D_e). | §4.8 |
| source_id | string | — | false | 원본(멤버 모델) namespace에서의 식별자 (매핑 출발점). | §4.8·§5 |
| target_id | string | — | true | canonical/pool namespace 매핑 대상 (도착점). resolved일 때 non-null. 'unresolved=target_id null' 표현 여부는 `(Design에서 확정)`. | §4.8 |
| confidence | enum{high, low} | — | false | 매핑 신뢰도. high 미해소→차단, low→경고. 산출 알고리즘·임계값은 `(Design에서 확정)`. | §4.8 |
| decision | enum{resolved, unresolved, warned} | — | false | 처리 결과. resolved=확정, unresolved=미해소(high면 차단), warned=low 경고 후 진행. | §4.8 |
| rationale | string | — | true | 결정 사유 (audit·provenance). 자동병합 금지. | §4.8·§11 |
| audit_ts | string (timestamp; ISO-8601 권장) | — | false | 결정 기록 시각. timezone(UTC)·정밀도·포맷은 `(Design에서 확정)`. | §4.8 |

### 7.2 NamespaceGateResult — gate 평가 결과 (§4.8·§11·§6)

| name | type | unit | nullable | desc | anchor |
|------|------|------|----------|------|--------|
| blocked | bool | — | false | gate 차단 여부. unresolved high-confidence 1건 이상 → true (= solve 차단). true면 MICOM 호출 금지. | §4.8·§10 |
| coverage_pct | float64 | percent (0–100) | false | namespace 커버리지 (%). 산출식(분모=전체 exchange metabolite 정의)은 spec 미규정 → `(Design에서 확정)`. | §11 |
| unresolved_high | list&lt;string&gt; | — | false | 차단 유발 unresolved high-confidence 대사체 목록 (해소 요구·바로가기 대상). | §4.8·§11 |
| warned_low | list&lt;string&gt; | — | false | low-confidence 경고 후 진행된 대사체 목록 (자동병합 없이 진행). | §4.8 |
| decisions | list&lt;NamespaceDecision&gt; | — | false | 본 gate 평가에 사용된 결정 레코드 전체 (audit trail). run_hash #10의 원천. | §4.8·§5·§7 |
| audit_trail_ref | string | — | true | audit trail 위치 참조 (SQLite/로그 핸들). 저장 매체·키는 `(Design에서 확정)`. 메타=YAML+SQLite(§8). | §4.8·§8 |

### 7.3 Gate 규칙 (§4.8·§6·§10)

- **[Gate-차단]** `unresolved AND confidence=high` 결정이 1건이라도 존재 ⇒ `blocked=true` ⇒ community solve(MICOM 호출) **차단**·해소 요구 (§4.8).
- **[Gate-경고]** `confidence=low` 매핑은 차단하지 않고 경고 후 진행하되 `decision=warned` 표기, **자동병합(auto-merge) 절대 금지** (§4.8).
- **[Gate-audit]** 모든 gate 차단/경고 동작은 audit trail에 기록 (누락 금지) (§4.8·§8).
- **[Gate-순서]** gate는 solve **직전**에 적용되며, `blocked=true`이면 어떤 MICOM solve도 실행되지 않는다 (§6·§10).
- **[Gate-선행]** AggregationStore에 기록되는 모든 ok run은 gate 통과 후 MICOM solve 결과여야 한다. 차단된 condition은 정상 run으로 승격되지 않고 sweep.parquet에 `status=failed`·diagnostic으로만 기록된다 (§4.8·§10·SC-3).

### 7.4 Golden fixture 디렉토리 구조 (§10·§16·부록 A17)

`fixtures/community_3_member/` — MVP-1a 완료 정의·MICOM 버전 승격 게이트의 회귀 기준 자산. float rounding/tolerance 후 정규화 hash로 비교. solver별 분리 보관·CI 매트릭스.

```
fixtures/
└── community_3_member/
    ├── models/                          # 미생물 GEM 3개 (SBML|JSON|MAT, §5 file_format)
    │   ├── member_1.xml
    │   ├── member_2.xml
    │   └── member_3.xml
    ├── medium.yaml                       # 공통 배지 정의 (YAML; pickle 금지, §8)
    ├── config.yaml                       # tradeoff_f · seed · micom 버전 등 solve 재현 파라미터
    └── expected/                         # solver별 분리 (CI 매트릭스, §16·A17)
        ├── gurobi/
        │   ├── expected_nodes.parquet    # tidy nodes 기대 산출 (§4.6)
        │   ├── expected_edges.parquet    # tidy edges (cross-feeding 포함, §4.6)
        │   ├── expected_profile.parquet  # tidy profile (external profile, §4.6)
        │   ├── growth_expected.tsv       # community/member growth 기대값
        │   └── sign_expected.tsv         # §4.7 canonical (ui_flux,label) 기대값
        └── osqp/                         # full: OSQP-QP + HiGHS-LP
            ├── expected_nodes.parquet
            ├── expected_edges.parquet
            ├── expected_profile.parquet
            ├── growth_expected.tsv
            └── sign_expected.tsv
        # (별도 highs/osqp_growth_highs_flux solver 이름은 폐기 — decisions/2026-06-01-golden-solver-list.md)
```

> **디렉토리 레이아웃 주의**: 위 트리는 verified fragment 기준 권장 구조다. solver별 `expected/` 중복 vs 공유(예: 입력 모델/medium은 공유, expected만 solver별 분리) 정확 구조는 `(Design에서 확정)` (§16·A17).
>
> **Hash 규칙 (§16)**: float 컬럼은 hash 전 rounding/tolerance(예: 6 decimal·abs/rel tol) 적용 후 정규화 hash 비교 (§4.3 참조). 원시 float 직접 hash 금지.
>
> **승격 게이트 (promotion gate)**: MICOM 버전 상향(micom_version 변경)은 solver별 golden **전부 통과** 시에만 승격되며, 미통과 시 차단 (§4.1·§16·§17).

---

## 8. Invariants 요약 (Invariants Summary)

> 부호(sign)·정규화(normalization)·키 유일성(key uniqueness)·preview 비오염(non-contamination) 등 핵심 불변식.

### 8.1 부호 규약 (Sign convention, §4.3·§4.7)
- **[SIGN-1]** `+`=환경으로 분비(secretion)·`−`=환경에서 흡수(uptake). net=환경 exchange, 멤버 기여=멤버↔pool (§4.3).
- **[SIGN-2]** 모든 `raw_flux → (ui_flux, label)` 변환은 sign 부기 계층의 **단일 진입점(single entry point)** 만 경유한다 (우회 금지) (§4.3·§4.7).
- **[SIGN-3]** ui_flux는 부호 정규화된 **크기(magnitude)** 이며 항상 ≥0 (§4.3·§4.7 canonical −5→5).
- **[SIGN-4 canonical (§4.7)]** 환경 raw −10 ⇒ ui_flux=10·label=uptake; 환경 raw +8 ⇒ ui_flux=8·label=secretion. 멤버↔pool raw −5 ⇒ ui_flux=5·label=uptake; raw +3 ⇒ ui_flux=3·label=분비(secretion). (멤버↔pool '분비' label을 환경 secretion과 동일 enum 통일 여부는 `Design에서 확정`.)
- **[CROSS-FEED]** cross-feeding edge m→m′ 성립 ⟺ (m flux>0 분비) ∧ (m′ flux<0 흡수); weight=min(\|m 분비\|, \|m′ 흡수\|) ≥0 (§4.3).
- **[MEDIUM-SIGN]** Medium.composition의 uptake 허용은 음수 lower_bound로 표현 (§4.3·§4.5).

### 8.2 정규화 (Normalization, §4.5·§5·§11)
- **[ABUND-NORM]** CommunityModel.members의 abundance는 normalize 적용 시 합 = 1.0 (정규화 후 상대 abundance) (§5·§11).
- **[ABUND-PRIORITY]** abundance 우선순위 = Scenario.abundance_overrides > MemberModel.abundance(선언). run_hash #4는 해소·정규화 후 값. 정확 규칙은 `(Design에서 확정)` (§5·§11·§7).
- **[TRADEOFF-RANGE]** tradeoff_f는 0 < f ≤ 1 (μ_c ≥ f·μ_c*). CommunityModel.tradeoff_f는 Scenario.config.tradeoff_f에서 전달되며 동일 제약 (§4.2).
- **[MIN-MEDIUM-U]** minimal medium은 U 기본 집합 {H₂O, H⁺, Pi}를 항상 포함. O₂는 oxygen_mode로 결정. blocked exchange 제외, tie-break 결정적 (§4.5).

### 8.3 키 유일성·참조 무결성 (Key uniqueness & Referential integrity, §5)
- **[ID-UNIQUE]** MemberModel.id는 member set 내에서 **유일** (중복 시 community 조립·cross-feeding 키 충돌) (§5).
- **[REF-INTEGRITY]** Scenario.member_set·CommunityModel.members의 member_id는 모두 존재하는 MemberModel.id를 참조 (§5).
- **[CONDITION-CONSISTENCY]** 동일 condition_id를 가진 모든 행은 동일 축 값 집합·동일 run_hash를 가진다 (§5).

### 8.4 run_hash 완전성·단일 정의 (run_hash completeness, §5·§7·§10·A14)
- **[HASH-11]** run_hash는 정확히 11개 구성요소만 포함 (빠짐·추가 금지). 변경 시 캐시 무효화·schema/버전 bump (§5·§7·§10·FR-2.8·A14).
- **[HASH-ENVLOCK]** env_lock은 RunManifest.inputs에만 기록, run_hash 11구성요소에는 미포함 (§7·§10).
- **[HASH-DETERMINISM]** 동일 11구성요소 → 동일 hash(hit); 1개 변경 → 다른 hash(miss·재계산) (§10·부록 A14·SC-4).
- **[HASH-SINGLE]** AggregationStore.run_hash = RunManifest.run_hash = Scenario.run_hash (동일 직렬화·동일 해시 함수, 비트 단위 일치) (§5·§7·§10).
- **[HASH-FLOAT]** float 구성요소는 hash 전 rounding/tolerance(예: 6 decimal) 적용 후 정규화 hash (§16·A17).
- **[MANIFEST-CONSISTENCY]** RunManifest.algorithms.normalization == run_hash #11; inputs.namespace_decisions == run_hash #10; software.cmig_core_version == run_hash #9; engine.micom_version == run_hash #8 (§7·§10).

### 8.5 preview 비오염·상태 (preview non-contamination & state, §8·§10·A11)
- **[STATE-DEFAULT]** Scenario.state 기본값 = preview (§10 AN-SANDBOX·A11).
- **[PREVIEW-NOWRITE]** preview 상태 solve는 sweep/cache/store에 기록하지 않는다(또는 ephemeral 표시). commit 승격은 오직 Apply/Save 사용자 액션으로만 발생 (§10·§8·A11·SC-8).
- **[RUNHASH-COMMIT]** Scenario.run_hash는 commit 상태에서만 영구 산출·기록. preview에서는 null 또는 ephemeral (§8·A11).

### 8.6 직렬화·solver·gate (Serialization, solver, gate, §2·§4.2·§4.8·§8)
- **[NO-PICKLE]** 어떤 엔티티/산출/fixture도 pickle로 직렬화하지 않는다. 일반 직렬화 허용=Parquet/Arrow/JSON/YAML/SQLite (§5·§8). **TSV는 golden fixture(growth_expected/sign_expected) 전용** — spec §5/§8 일반 직렬화 목록에는 미명시, §16 fixture 형식에서 도출.
- **[FILE-FORMAT]** MemberModel.source.file_format ∈ {SBML, JSON, MAT}만 허용 (§5·§8).
- **[SOLVER-SPLIT]** growth=QP(OSQP 등), flux=LP(Gurobi/HiGHS/CPLEX). `solver="osqp"`는 optlang hybrid alias이므로 growth_solver=osqp, flux_solver=highs로 기록한다. LP 부재 시 'QP-only approximate' 표기 (§4.2·A6).
- **[MILP-CAPABILITY]** Medium.is_minimal=true 산출은 MILP capability(Gurobi/HiGHS/CPLEX) 요구. 미지원 시 minimal medium 분석만 비활성화 (§2·§4.5).
- **[GATE-BLOCK]** unresolved high-confidence exchange mapping 존재 ⇒ CommunityModel.namespace_gate_status=blocked ⇒ MICOM solve 미호출. low-confidence는 warning 진행·자동병합 금지·audit (§4.8).
- **[MICOM-PIN]** MICOM은 정확(exact) pin(micom==X.Y.Z). 버전 업그레이드는 solver별 golden 전부 통과 시에만 승격 (§4.1·§16·SC-5).
- **[STATUS-CLOSED]** AggregationStore.status ∈ {ok, failed}만 허용. failed → diagnostic ≠ null, value 결측 (§5·§10).
- **[CARVE-OUT]** AggregationStore(sweep.parquet)는 §4.6 tidy 5종에 속하지 않고 §5 스토어 규약을 따른다 (§4.6 sweep 카브아웃·§5).
- **[HOST-PARTII]** MemberModel은 미생물 GEM 전용. HostModel(사람세포)은 §5 stub만 포함하며 PART II §12 범위 외 (§5·§12).

---

## 9. Open Decisions — (Design에서 확정)

> 각 fragment의 openDecisions를 취합·중복 제거. 모두 spec에 명시되지 않은 값으로, **Design 단계에서 확정**한다.

### 9.1 도메인 엔티티 (Domain entities, §5)
- **OD-1** MemberModel.taxonomy.ncbi_taxid 표현 타입 (string vs int — 선행 0/비정수 식별자 안전성). (§5)
- **OD-2** MemberModel.stats의 정확한 필드 집합 (spec은 'stats'로만 명시; n_reactions/n_metabolites/n_genes/n_exchanges 후보). (§5)
- **OD-3** MemberModel.source.origin 허용값 집합/enum 여부 (BiGG·AGORA·user·DB명 등). (§5)
- **OD-4** abundance 단위: 절대(cell count/biomass) vs 상대(dimensionless)·normalize 모드 표현·override 우선순위 정밀 규칙. (§5·§11)
- **OD-5** Medium.composition의 bound 단위·표현 (mmol/gDW/h flux 가정 vs 별도). (§5)
- **OD-6** namespace_convention 허용값 enum (bigg·kegg·metanetx·seed·custom). (§4.8)
- **OD-7** Medium preset 카탈로그·minimal medium tie-break 결정 규칙 구체화. (§4.5)
- **OD-8** Scenario.constraints.source 태그(user_edit/sandbox) 표현 방식 (sandbox bound vs 일반 편집 구분, preview 추적용). (§10·A11)
- **OD-9** preview Scenario의 ephemeral 저장 위치/수명 (in-memory only vs temp file). (§8·A11)

### 9.2 재현성·해시 (Reproducibility & hash, §7·§10·§16)
- **OD-10** checksum 해시 알고리즘 (sha256 등) 및 정규화 절차 (입력 무결성). (§5·§16)
- **OD-11** run_hash 해시 함수(예: SHA-256)·11구성요소 canonical 직렬화 순서·구분자·인코딩. (§10·§16·Plan §8.2)
- **OD-12** float rounding/tolerance 정확 파라미터: decimal 자릿수(spec 예=6 decimal)·abs tol·rel tol·컬럼별 적용 정책·rounding vs tolerance 택일/병행. (§16·A17)
- **OD-13** solver_setting struct의 정확한 직렬화 필드 set (어떤 solver 옵션이 run_hash에 포함/제외). (§5·§7·§10)
- **OD-14** RunManifest 직렬화 포맷·파일 레이아웃 (메타=YAML vs SQLite 역할 분담·파일 위치·확장자·schema_version 스킴). (§3·§8·Plan §7.2)
- **OD-15** env_lock 직렬화 방식 (conda lock vs uv lock vs 해시) — run_hash 11구성요소 미포함(불변식 확정). (§7·Plan §8.3)
- **OD-16** flux_normalization_method / algorithms.normalization enum 값셋 (pFBA 외 옵션 존재 여부)·Scenario.config 필드 위치. (§4.4·§7·§10)
- **OD-17** cmig_core_version 보유 엔티티/주입 시점 (run_hash 구성요소이나 §5 엔티티 필드 미명시 — Scenario/manifest commit 주입 가정). (§7·§8)
- **OD-18** metric_mode enum 값셋 (CMIG-MIP/MRO 등 CMIG-defined 지표 모드 명세). (§4.5·§7)
- **OD-19** flux_report_status의 대비 상태값('full' 등) 명칭 — spec은 'QP-only approximate'만 명시. (§4.2·§4.4·§7)
- **OD-20** tolerance(solver 수치)와 golden float rounding/tolerance의 정합 기준·구체 tolerance 값. (§4.2·§16)
- **OD-21** bounds(flux bound)의 단위 — spec 미명시(관례적 mmol/gDW/h 추정). (§5·§7·§10)
- **OD-22** manifest_schema_version 변경 시 sweep 캐시 마이그레이션 정책 (무효화 vs 재해시 vs 보존). (Plan §6.2·§6.3·SC-4)
- **OD-23** RunManifestPlatform 세부 필드 범위 (OS 버전·solver 라이선스 상태·하드웨어). (§7·§11)

### 9.3 solver capability (§2·A6)
- **OD-24** config.solver.growth_solver의 HiGHS-QP(experimental) 허용 여부·기본 solver 정책. (§2·A6)
- **OD-25** default_solver 고정(Gurobi)의 무라이선스 CI 환경 자동 fallback(highs/osqp) 규칙. (§2·Plan §7.2·R4)
- **OD-26** HiGHS-QP(experimental) capability를 baseline에서 활성/비활성·QP 경로 실제 노출 여부. (§2·A6)

### 9.4 AggregationStore·sweep (§5·§10)
- **OD-27** condition_id 생성 규칙 (순차 인덱스 vs 축 값 결정적 슬러그/해시). (§5)
- **OD-28** AggregationStore 물리 경로·파일 분할(append vs 파티셔닝·run당 파일 vs 단일 sweep.parquet)·schema_version 표기. (§5·Plan §6.2·§6.3)
- **OD-29** metric 허용 도메인 enum(community_growth·member_growth·exchange_flux·FVA range 등)·value 단위 체계. (§5·§10)
- **OD-30** 축 값 컬럼 직렬화 표현 (abundance/bounds/member_set를 long-format 단일 컬럼에 스칼라 vs 참조 id vs 결정적 해시로 인코딩). (§10)
- **OD-31** diagnostic 컬럼 구조 (자유 텍스트 vs 구조화 JSON 문자열·코드 enum + 메시지). (§5·§10)
- **OD-32** solver 축 enum 전체 목록 (§2 matrix 기반; osqp_growth_highs_flux는 golden 세트 명이지 solver 축 값 아님). (§2·§10)
- **OD-33** RunManifest.sweep 내 condition_id↔run_hash 매핑 표현 (인라인 list 정렬 정합 vs 별도 매핑 테이블). (§7·§10)
- **OD-34** axis_tradeoff_f 값 도메인 범위(예: 0<f≤1)·경계 처리. (§10)
- **OD-35** status=ok 행의 diagnostic 사용 정책 (QP-only/경고 등 비-실패 진단을 같은 컬럼에 담을지). (§5·§10)

### 9.5 namespace·gate·sign (§4.3·§4.7·§4.8·§11)
- **OD-36** namespace mapping confidence(high/low) 산출 알고리즘·임계값(threshold). (§4.8)
- **OD-37** NamespaceDecision.target_id nullability 표현 ('unresolved=target_id null' vs 별도 상태 필드). (§4.8)
- **OD-38** NamespaceDecision.audit_ts의 timezone(UTC 강제)·정밀도(ms/μs)·포맷 표준. (§4.8)
- **OD-39** namespace_mapping_decisions의 run_hash 직렬화 정규화 규칙(정렬 키·canonical 형태)·11구성요소 직렬화 순서. (§4.8·§5·§7)
- **OD-40** coverage_pct 분모의 정확한 정의 (전체 exchange metabolite 기준 — 멤버별 합집합 vs pool 기준). (§11)
- **OD-41** gate audit_trail 저장 매체(SQLite 테이블 vs ndjson 로그)·키 스키마. (§8)
- **OD-42** gate 차단 시 사용자 해소(resolution) 워크플로(수동 매핑 wizard) 상세 — baseline gate 해소 UI 범위. (mapping wizard는 §16 MVP-3/host 명시) (§4.8·§16)
- **OD-43** 멤버↔pool '분비' label을 환경 secretion과 동일 enum 통일 여부. (§4.7)
- **OD-44** flux 단위 정규화 표기(§4.4 pFBA·QP-only)·ui_flux 단위 문자열 규칙. (§4.4)

### 9.6 tidy 계약·golden (§4.6·§16)
- **OD-45** §4.6 tidy 5종(nodes/edges/profile/matrix/timecourse) 컬럼 표준명·edge_type 전체 집합(cross_feeding 외 interaction typing·MIP·MRO). (§4.6)
- **OD-46** tidy 스키마 버전 필드 경계·도메인 엔티티(MemberModel/Scenario)와의 매핑. (§4.6·Plan §6.3)
- **OD-47** golden normalized_hash 알고리즘(예: 정렬 후 SHA-256)·컬럼 정규화(컬럼 순서·NaN 처리). (§16·A17)
- **OD-48** golden solver_variant 디렉터리 레이아웃 (expected/ 중복 vs 공유) 정확 구조. (§16·A17)
- **OD-49** golden config.yaml 전체 필드 스키마 (tradeoff_f·seed·micom 버전 외 solver setting·tolerance 등 run_hash 정합 필드 포함 여부). (§16)
- **OD-50** osqp_growth_highs_flux golden의 LP 재계산 tolerance가 gurobi golden과 일치하는 허용 오차. (§16·§4.2·A6·SC-6)
- **OD-51** MICOM exact pin 버전 (micom==X.Y.Z) 구체 값. (§4.1·§16)
- **OD-52** CMIG-MIP/MRO 정확 산식 및 optional SMETANA-compatible 정의 매핑. (§4.5·A9)
- **OD-53** 'no significant change' 진단 판정 임계 (FVA 범위 대비 변화량 기준). (§10 AN-SANDBOX·§17)
- **OD-54** debounced re-solve의 debounce 지연(ms)·취소 정책 구체값. (§4.2·§10·§8)

---

## 부록: spec 앵커 인덱스 (Spec Anchor Index)

| 앵커 | 주제 | 본 문서 참조 섹션 |
|------|------|------------------|
| §4.1 | MICOM 위임·정확 pin·public API | §1.2·§3.4·§4.1·§5 |
| §4.2 | Cooperative tradeoff + QP→LP flux 재계산 | §3.3·§4·§5 |
| §4.3 | Sign convention (강제) | §2·§3.4·§8.1 |
| §4.4 | 수치 (pFBA·QP-only·loopless·infeasible) | §4.2·§6 |
| §4.5 | CMIG-MIP/MRO + minimal medium (cardinality MILP) | §3.2·§5·§8.2 |
| §4.6 | Tidy 데이터 계약 (nodes/edges/profile/matrix/timecourse) | §1.3·§2·§6·§7.4 |
| §4.7 | Sign 테스트 계약 (의무·canonical case) | §2·§8.1·§7.4 |
| §4.8 | Namespace hard gate (필수) | §3.3·§3.4·§7 |
| §5 | 데이터 모델 (MemberModel·AggregationStore·run_hash 11구성요소) | §3·§4·§6 |
| §7 | 재현성 (RunManifest·run_hash) | §4·§8.4 |
| §8 | 비기능 (pickle 금지·preview 비기록) | §1.3·§8.5·§8.6 |
| §10 | Baseline 분석 기능·Run hash 정의 | §4·§6·§7 |
| §11 | Baseline GUI (gate coverage%·preview) | §6.2·§7.2 |
| §16 | MVP 로드맵·golden fixture 구조·solver별 분리 | §5·§7.4 |
| 부록 A6 | solver capability matrix | §5 |
| 부록 A11 | (G1) sandbox preview/commit | §3.3·§8.5 |
| 부록 A14 | (G4) sweep run hash 캐시·실패 diagnostic | §4.2·§6 |
| 부록 A17 | MVP-1a golden (parquet 분리·float rounding·solver별) | §4.3·§7.4 |

> **PART II (범위 외 / out of scope) 명시**: §12 host-microbe(G2)·§13 dFBA(+timecourse)·§14 다중타깃(G3)·§15 통계(G5)는 본 Baseline Schema의 정의 대상이 아니며, placeholder/stub으로만 표기한다.
