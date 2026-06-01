---
template: glossary
version: 1.0
feature: cmig-community-core
project: CMIG (Community Metabolic Interaction GUI)
scope: PART I — Implementation Baseline (MVP-0~2)
authoritative_spec: CMIG_명세서_v3.0.md (§1–§11, §16, 부록 A)
date: 2026-05-31
status: Draft
---

# CMIG 도메인 용어집 (Domain Glossary) — PART I Baseline

> **목적 (Purpose)**: CMIG PART I Baseline(MVP-0~2)의 도메인 용어(domain term)·약속(contract)·규약(convention)을 **단일 권위 정의(single authoritative definition)** 로 고정한다. 모든 entity·invariant·코드·UI·문서가 이 용어집의 정의와 표현을 참조한다. 본 문서는 community FBA를 **MICOM(정확 pin·public API only)** 에 위임하고 CMIG가 **부가가치 계층(value-added layer)** 을 소유한다는 전제 위에서 작성된다.

> **명세 권위 노트 (Spec Authority Note)**: 권위 자료(authoritative source)는 **`CMIG_명세서_v3.0.md`** (§1–§11, §16, 부록 A) 이다. 본 용어집은 명세와 **모순되지 않으며**, 모든 정의는 spec 섹션 앵커(예: §4.3, §4.8, §5, §7, §10, A11)를 단다. **spec에 명시되지 않은 값**은 `(Design에서 확정)` 으로 표기한다. 일반 직렬화(serialization)는 **Parquet/Arrow/JSON/YAML/SQLite만** 허용하며 **pickle 금지**(§5·§8). **TSV는 golden fixture(growth_expected/sign_expected) 전용**(§16; 일반 직렬화 목록 외). host-microbe(G2)·dFBA·다중타깃(G3)·통계(G5)는 **PART II (범위 외, Out of Scope)** 로만 표기한다(§12–§15).

---

## 목차 (Table of Contents)

1. [핵심 규약 5선 (Core Contracts at a Glance)](#1-핵심-규약-5선-core-contracts-at-a-glance)
   - [A. 부호 규약 표 (Sign Convention) — §4.3](#a-부호-규약-표-sign-convention--43)
   - [B. Namespace gate 의미 — §4.8](#b-namespace-gate-의미--48)
   - [C. preview vs Apply/commit — A11](#c-preview-vs-applycommit--a11)
   - [D. QP-only approximate 의미 — §4.2](#d-qp-only-approximate-의미--42)
   - [E. tidy contract 5테이블 한 줄 요약 — §4.6](#e-tidy-contract-5테이블-한-줄-요약--46)
2. [용어집 (Glossary, 알파벳·주제별)](#2-용어집-glossary-알파벳주제별)
   - [2.1 도메인 엔티티 (Core Domain Entities) — §5](#21-도메인-엔티티-core-domain-entities--5)
   - [2.2 분석 모드 (Analysis Modes) — §10](#22-분석-모드-analysis-modes--10)
   - [2.3 알고리즘·수치 (Algorithms & Numerics) — §4.2·§4.4·§4.5](#23-알고리즘수치-algorithms--numerics--4244 45)
   - [2.4 지표 (Metrics) — §4.5](#24-지표-metrics--45)
   - [2.5 규약·계약 (Conventions & Contracts) — §4.3·§4.6·§4.7](#25-규약계약-conventions--contracts--434647)
   - [2.6 재현성 (Reproducibility) — §7·§10·§16](#26-재현성-reproducibility--71016)
   - [2.7 solver·라이선스 (Solvers & Licensing) — §2](#27-solver라이선스-solvers--licensing--2)
   - [2.8 GUI 패턴 (GUI Patterns) — §10·§11](#28-gui-패턴-gui-patterns--1011)
3. [run_hash 11 구성요소 레퍼런스 — §5·§7·§10·A14](#3-run_hash-11-구성요소-레퍼런스--571014)
4. [범위 외 용어 (Out of Scope — PART II) — §12–§15](#4-범위-외-용어-out-of-scope--part-ii--1215)
5. [미결정 사항 (Open Decisions)](#5-미결정-사항-open-decisions)
6. [Spec 앵커 색인 (Spec Anchor Index)](#6-spec-앵커-색인-spec-anchor-index)

---

## 1. 핵심 규약 5선 (Core Contracts at a Glance)

> 명세가 강제(enforce)하는 5가지 핵심 규약. 모든 baseline 산출·UI·테스트의 기반이다.

### A. 부호 규약 표 (Sign Convention) — §4.3

flux 부호는 **강제(mandatory)** 규약이다: `+`=환경으로 **분비(secretion)**, `−`=환경에서 **흡수(uptake)**. net 값은 **환경 exchange**, 멤버 기여(member contribution)는 **멤버↔공유 pool(member↔pool)** 로 분해된다. 모든 부호 변환은 **부기 계층(sign layer)의 단일 진입점(single entry point)** 을 경유하며(§4.3·§4.7), §4.7 sign-test contract로 CI 검증한다.

| 맥락 (scope) | `+` (양수) 의미 | `−` (음수) 의미 | net / 분해 기준 | spec 앵커 |
|---|---|---|---|---|
| **환경 exchange (environment exchange)** | 환경으로 **분비** (secretion) | 환경에서 **흡수** (uptake) | net = 환경 exchange | §4.3 |
| **멤버 ↔ pool (member↔pool)** | 멤버 → pool **분비** (secretion) | 멤버 ← pool **흡수** (uptake) | 멤버 기여 = 멤버↔pool | §4.3 |
| **cross-feeding (m→m′)** | 멤버 m이 **분비**(raw>0) | 멤버 m′이 **흡수**(raw<0) | edge weight = `min(\|m 분비\|, \|m′ 흡수\|)` [mmol/gDW/h] | §4.3 |

**canonical case (§4.7, CI 강제)** — `raw_flux → (ui_flux, label)` 변환의 의무 단위테스트 기준값:

| 맥락 | raw_flux | ui_flux (magnitude, ≥0) | label |
|---|---:|---:|---|
| 환경 exchange | −10 | 10 | uptake |
| 환경 exchange | +8 | 8 | secretion |
| 멤버↔pool | −5 | 5 | uptake |
| 멤버↔pool | +3 | 3 | 분비 (secretion) |

> 주의: spec §4.7은 멤버↔pool에 한국어 **'분비'** 를 직접 사용한다. 환경 `secretion`과의 enum 통일 여부는 `(Design에서 확정)`. `ui_flux`는 부호 정규화된 **크기(magnitude)** 이므로 항상 ≥0이다.

### B. Namespace gate 의미 — §4.8

solve **직전(just before solve)** 에 적용되는 **차단형 하드 게이트(hard gate)**. exchange 대사체(metabolite)의 namespace 정합·confidence(`high`|`low`)를 검사한다.

| confidence | 상태 (status) | gate 거동 (behavior) | 결과 |
|---|---|---|---|
| **high** + **unresolved** (미해소) | `unresolved` | **차단 (block)** | community solve(MICOM 호출) **수행 안 함**, 해소(resolution) 요구 |
| **low** | `warned` | **경고 (warn) 후 진행** | solve 진행하되 **자동병합(auto-merge) 금지** · audit trail 기록 |
| (any) **resolved** (해소) | `resolved` | 통과 (pass) | 정상 진행 |

- **핵심 불변(invariant)**: unresolved high-confidence mapping이 1건이라도 존재하면 **MICOM solve를 호출하지 않는다**(§4.8·§10). low-confidence는 절대 자동병합하지 않고 경고 후 진행하며 audit trail에 기록한다(§4.8).
- gate 통과는 RunManifest/run_hash 정상 산출의 **선행조건(precondition)** 이다. high/low **임계 기준(threshold)** 은 `(Design에서 확정)`(§4.8).
- GUI: Model Manager에 namespace 상태(coverage%·unresolved 바로가기)를 상시 노출(§11). coverage% 산출식(분모 정의)은 `(Design에서 확정)`.

### C. preview vs Apply/commit — A11

G1 sandbox run의 상태 이원화(state dichotomy). **sandbox 실험이 영구 store·재현 자산을 오염시키지 않도록** 분리하는 규약(§10 AN-SANDBOX·§8·A11).

| 상태 (state) | 의미 | store/cache/sweep 기록 | run_hash·manifest |
|---|---|---|---|
| **preview** (기본 default) | 임시(ephemeral) solve | **비기록** (또는 ephemeral 표시) | null 또는 ephemeral |
| **commit** | Apply/Save로 승격 | **기록** (Scenario/Run artifact) | 영구 산출·기록 |

- preview→commit **승격(promotion)** 은 오직 사용자의 **Apply/Save** 액션으로만 발생한다(§10·A11).
- preview solve는 sweep/cache/store에 기록하지 않는다(AggregationStore 비오염 불변, §8·A11·SC-8).

### D. QP-only approximate 의미 — §4.2

cooperative tradeoff는 2단계 solve다: ① **OSQP(QP)** 로 member growth L2 확보 → growth/community constraint 고정 → ② **LP solver(Gurobi/HiGHS/CPLEX)** 로 pFBA/normalization **재계산(recompute)**. OSQP는 **QP 전용**이므로 flux는 반드시 LP로 재계산한다(§4.2).

- **`QP-only approximate`**: LP flux_solver가 **부재(absent)** 하여 LP pFBA 재계산을 수행할 수 없을 때, **QP 결과만으로 근사한 flux임을 명시적으로 표기**하는 상태(flux_report_status). 정확도 한계를 사용자에게 투명하게 알린다(§4.2·§4.4·§8·A6).
- 대비 상태값(예: `full`)의 명칭은 `(Design에서 확정)` — spec은 `QP-only approximate`만 명시.
- growth_solver(QP)·flux_solver(LP)는 RunManifest에 **분리 기록**한다(§7·§4.2).

### E. tidy contract 5테이블 한 줄 요약 — §4.6

모든 분석 산출의 **단일 출력 계약(single output contract)** = `nodes / edges / profile / matrix / timecourse` (parquet). 전 소비자(graph viewer·profile·delta·sweep·R export)가 **단일 reader** 경유. 스키마 버전 필드 + 계약 테스트 필수(plan §6.2·§6.3 파생). **sweep store는 별개**(§5, AggregationStore). 단, **`timecourse`는 Baseline 비대상** — dFBA(§13) PART II placeholder로 명명만 포함(MVP-0~2 미산출).

| 테이블 | 한 줄 요약 (one-liner) | spec 앵커 |
|---|---|---|
| **nodes** | 그래프 노드(멤버/대사체 등) 정의 — graph viewer 노드 인코딩 입력 | §4.6 |
| **edges** | 방향성 상호작용(cross-feeding 등) edge — `min` weight·sign 규약 적용 | §4.6·§4.3 |
| **profile** | community ↔ 환경 net exchange 프로파일 — External Profile Viewer 입력 | §4.6 |
| **matrix** | 조건×대사체/멤버 행렬형 산출(배지별 matrix 등) | §4.6 |
| **timecourse** | 시계열형 산출(시간축 결과) — **Baseline 비대상**: 시간축 산출(dFBA, AN-DFBA)은 **PART II §13** 범위. MVP-0~2에서는 명명만 포함된 **placeholder** | §4.6·§13 (PART II) |

> golden fixture(§16 MVP-1a)는 이 중 **nodes/edges/profile 3종**만 회귀 비교 대상으로 보관한다(§16·A17). 각 테이블 **컬럼 표준명**(node_id/edge type/flux/label 등)은 `(Design/Schema에서 확정)`(plan §8.2). sweep.parquet은 §4.6 5종이 아니라 §5 스토어 규약의 지배를 받는다.

---

## 2. 용어집 (Glossary, 알파벳·주제별)

> 표기 규약: 각 용어는 **한국어 + 영어 기술용어(English technical term)** 병기. 정의는 측정/검증 가능한 형태로 기술하고 spec 앵커를 단다. 수치 용어는 단위·부호를 명시한다.

### 2.1 도메인 엔티티 (Core Domain Entities) — §5

직렬화는 Parquet/Arrow/JSON/YAML/SQLite만, **pickle 금지**(§5·§8).

CommunityModel (커뮤니티 모델)
: MICOM community 조립체(assembly) = member set + abundance + medium. MICOM `cooperative_tradeoff` solve의 입력 객체. community solve는 **MICOM에 위임**(public API only), CMIG는 namespace 정합·sign 정규화 부가가치 계층을 소유한다(§4.1). HostModel 결합은 **PART II (범위 외)**. — **§4.1·§4.5·§5**

HostModel (호스트 모델)
: 사람세포/host GEM 엔티티. spec §5에서 `HostModel/Medium/Scenario 유지`로만 호명되는 **stub**. 본격 구성(2-interface lumen/blood·viability constraint·objective)은 **PART II (범위 외)** (§12 G2 host-microbe). Baseline 엔티티 계약에는 stub만 포함. — **§5(유지·stub)·§12 (PART II)**

Medium (배지)
: 외부 대사체 환경의 exchange 가용성(availability) 정의. composition·preset·minimal medium 입력 포함. solve 전 §4.8 namespace gate 대상이며 `checksum`은 run_hash 구성요소(§7). uptake 허용은 음수 lower_bound로 표현(흡수=`−`, §4.3). minimal medium 산출은 MILP capability를 요구한다. — **§4.5·§5·§10**

MemberModel (멤버 모델)
: 커뮤니티의 단일 미생물 **GEM(genome-scale metabolic model)** 멤버를 표현하는 도메인 엔티티. `id/name/strain`, `taxonomy{ncbi_taxid, lineage}`, `source{file_path, file_format(SBML|JSON|MAT), origin, namespace_convention, checksum}`, `stats`, `biomass/exchange compartment`, `abundance(+bounds)`로 구성. community 조립의 기본 단위이자 namespace gate·sign 정규화의 대상. `id`는 member set 내 유일(unique). **불변식**: `source.file_format ∈ {SBML, JSON, MAT}` 폐쇄 enum·**pickle 금지**(schema [FILE-FORMAT]/[NO-PICKLE], §5·§8). — **§5**

Scenario (시나리오)
: 재현 가능한 분석 실행 단위(reproducible run unit) = medium + constraints + member set + config(`tradeoff_f`, `seed`, `solver`, `flux_normalization_method`). **preview(임시)** 또는 **commit(artifact 승격)** 상태를 가진다(§10 AN-SANDBOX·A11 → [1.C](#c-preview-vs-applycommit--a11)). commit 시 run_hash 산출. — **§5·§10·§11·A11**

abundance (존재비)
: 멤버의 community 내 상대(relative)/절대(absolute) 존재비. normalize 가능. CommunityModel solve 입력이자 run_hash 구성요소(해소·정규화 후 값). 우선순위 = `Scenario.abundance_overrides` > `MemberModel.abundance`(선언). normalize 적용 시 합=1.0. 단위(절대 vs 상대)는 `(Design에서 확정)`. — **§5·§7·§11**

AggregationStore (집계 스토어)
: AN-SWEEP(G4)가 N-run 배치 결과를 누적하는 **long-format(좁은 형태)** Parquet 스토어 `sweep.parquet`. 한 행 = `(condition_id, axis 값, metric, value, run_hash, status{ok|failed}, diagnostic)`. **성공·실패 run을 모두 보관**(실패 누락 금지). §4.6 tidy 5종이 아니라 **§5 스토어 규약**을 따르며 pickle 금지(Parquet/Arrow). 물리 경로/분할 정책은 `(Design에서 확정)`. — **§5·§10·§4.6(sweep 카브아웃)**

condition_id (조건 식별자)
: sweep 그리드 내 한 조건(축 값 조합)의 식별자. 동일 condition_id의 모든 행은 동일 축 값 집합·동일 run_hash를 공유한다. 실패 run도 condition_id별 diagnostic으로 반드시 보관(누락 금지). 생성 규칙(순차 인덱스 vs 결정적 슬러그)은 `(Design에서 확정)`. — **§5·§10**

status {ok | failed}
: run 결과 상태 enum. `ok`=정상 solve(metric/value 채워짐), `failed`=infeasible/solver 오류 등(value 결측·diagnostic 필수). 실패 run도 store에 기록(§10). — **§5·§10**

diagnostic (진단)
: 실패(또는 QP-only 등 주의) run의 진단 메시지/구조. infeasible 원인·capability 강등·QP-only 표기 등을 담는다(§4.4). `status=failed`인 condition_id에는 **필수(≠null)**. 구조(자유 텍스트 vs 구조화)는 `(Design에서 확정)`. — **§5·§10·§4.4**

checksum (체크섬)
: 모델/배지 입력 파일의 결정적(deterministic) 해시. `source` 메타이자 run_hash 구성요소(model/medium checksum). pickle 금지 직렬화 정책 하에서 입력 무결성·재현성 보장. 해시 알고리즘은 `(Design에서 확정)`. — **§5·§7·§10**

### 2.2 분석 모드 (Analysis Modes) — §10

> baseline 분석 모드는 정확히 **6종**. 모든 solve는 §4.8 gate 통과 후 MICOM 호출, 출력은 §4.6 tidy 계약을 따른다.

AN-SINGLE (단일종 분석)
: 단일 GEM에 대한 baseline 분석 모드 — FBA/pFBA/FVA, knockout, exchange 요약, growth feasibility, reaction bound 편집. community solve 이전 단일 모델 검토용. — **§10·§16 MVP-0**

AN-PAIR (페어 분석)
: 두 멤버에 대한 monoculture vs co-culture 비교 — interaction typing, CMIG-MRO, cross-feeding, 교환 대사체, 배지별 matrix 산출. — **§10**

AN-COMMUNITY (커뮤니티 분석)
: §4.8 namespace gate 통과 후 MICOM solve를 수행하는 **핵심 community 분석** — community/member growth, exchange decomposition, cross-feeding edge, external profile, abundance/medium sensitivity, FVA. — **§10·§4.8**

AN-DELTA (델타 분석, 핵심)
: baseline community를 복제 → 멤버 추가 → 동일 조건 재solve → 두 결과의 차이(delta) 산출. CMIG 차별점 ①(멤버 추가 시 상호작용 변화)의 직접 구현. delta 뷰·delta network·delta heatmap 제공. — **§1·§10·§11**

AN-SANDBOX (G1 샌드박스)
: **reaction flux를 직접 바꾸는 기능이 아니라**, 멤버 reaction의 **bound constraint를 변경하고 community problem을 재최적화(re-optimize)** 하는 기능(불변, A11). 인터랙티브 드래그 → debounced 재solve(§4.2) → baseline vs constrained external-profile delta. 보상 우회로 변화 미미 시 FVA 범위·`no significant change` 진단. 취소·되돌리기 지원. preview 기본(→ [1.C](#c-preview-vs-applycommit--a11)). **PART I Baseline (MVP-2)**. — **§10·§11·§16·A11**

AN-SWEEP (G4 스윕)
: parameter sweep — 축 `{medium variant·abundance·member set·bounds·tradeoff f·solver}` × 값 조합을 **N-run 배치(batch job)** 로 실행해 long-format `sweep.parquet`에 모으는 sensitivity의 일반화. run_hash(11구성요소)로 캐시(재계산 회피·재현성), 실패 run도 condition_id별 diagnostic으로 저장(누락 금지). **PART I Baseline (MVP-2)**. — **§10·§5·§11·§16·A14**

### 2.3 알고리즘·수치 (Algorithms & Numerics) — §4.2·§4.4·§4.5

cooperative tradeoff (협력 트레이드오프)
: MICOM의 2단계 community 최적화: ① `μ_c* = max Σ_m a_m·μ_m` 로 최대 community growth를 구하고, ② `μ_c ≥ f·μ_c*` (0≤f≤1) 제약 하에서 member growth를 **L2-최소화(QP)** 하여 균형 잡힌 멤버 성장 분포를 얻는다. `f=1`이면 `μ_c=μ_c*`. **MICOM 위임**. — **§4.1·§4.2**

tradeoff f (트레이드오프 f)
: cooperative tradeoff 파라미터. `μ_c ≥ f·μ_c*` 제약의 `f` (`0 < f ≤ 1`, dimensionless). Scenario config 요소이자 run_hash 구성요소이며 CommunityModel로 전달. — **§4.2·§5·§7**

pFBA (parsimonious FBA / 절약 FBA)
: objective 최적값을 유지하면서 총 flux 합(`Σ|v|`)을 최소화하여 alternate optima를 줄이고 정규화된 flux를 얻는 방법. 재현성(§7)·golden fixture 정규화의 기반. OSQP growth 확보 후 LP solver로 재수행. — **§4.2·§4.4·§7·§16·A17**

FVA (Flux Variability Analysis / 플럭스 변동 분석)
: objective 제약 하에서 각 reaction flux의 최소/최대 가능 범위를 계산하는 분석. AN-SINGLE/AN-COMMUNITY 산출이며, G1 sandbox에서 보상 우회로 변화가 미미할 때 `no significant change` 진단과 함께 FVA 범위를 표시한다. — **§10·§11**

loopless (무루프 / thermodynamic loop 제거)
: 열역학적으로 불가능한 internal cycle(loop)을 배제하는 옵션. alternate optima/loop로 인한 비물리적 flux를 방지하며 pFBA와 함께 수치 안정성을 확보한다. — **§4.4·§17**

minimal medium (최소 배지 / cardinality MILP)
: 성장을 지원하는 최소 cardinality(=정수 개수, MILP minimize)의 exchange 집합 산출. 비포함 기본 `U = {H₂O, H⁺, Pi}`, O₂는 호기(aerobic)/혐기(anaerobic) 옵션, blocked reaction 제외, tie-break은 **결정적(deterministic)**. **MILP capability(Gurobi/HiGHS/CPLEX)** 필요 — 미지원 시 해당 분석만 비활성화(§2). — **§4.5·§2·§16 MVP-2**

QP-only approximate (QP 전용 근사)
: → [1.D](#d-qp-only-approximate-의미--42) 참조. LP solver 부재로 LP pFBA 재계산 불가 시 QP 결과만으로 근사한 flux임을 명시 표기하는 상태. — **§4.2·§4.4·§8·A6**

infeasible diagnostic (실행불가 진단)
: solve가 infeasible일 때 원인을 진단·표기하는 수치 거동(§4.4). sweep 실패 run의 diagnostic 컬럼과 연계. — **§4.4·§5·§10**

### 2.4 지표 (Metrics) — §4.5

CMIG-MIP (Metabolic Interaction Potential / cross-feeding 절감 지표)
: 멤버 간 cross-feeding을 통한 영양 의존(상호 공급) 정도를 정량화하는 **CMIG-정의(CMIG-defined)** 지표 — community가 cross-feeding으로 절감하는 영양 요구를 나타낸다. CMIG-defined 기본(+ optional SMETANA-compatible). 정확 산식(formula)은 `(Design에서 확정)`. — **§4.5·§10 AN-PAIR·A9**

CMIG-MRO (Metabolic Resource Overlap / 영양 중복 지표)
: 멤버들이 동일 영양원을 두고 경쟁하는 정도(영양 자원 중복)를 정량화하는 **CMIG-정의** 지표. interaction typing의 입력. CMIG-defined 기본(+ optional SMETANA-compatible). 정확 산식은 `(Design에서 확정)`. — **§4.5·§10 AN-PAIR·A9**

### 2.5 규약·계약 (Conventions & Contracts) — §4.3·§4.6·§4.7

sign convention (부호 규약) — §4.3
: → [1.A](#a-부호-규약-표-sign-convention--43) 참조. `+`=환경으로 분비(secretion), `−`=환경에서 흡수(uptake). net=환경 exchange, 멤버 기여=멤버↔pool. 변환은 부기 계층 **단일 진입점**에서만 수행. — **§4.3·§4.7·§11(부호 범례 상시)·§8.2**

sign-test contract (부호 테스트 계약) — §4.7
: MICOM flux→(ui_flux,label) 변환을 검증하는 **의무 단위테스트 + canonical CI case 계약**. canonical 값은 [1.A](#a-부호-규약-표-sign-convention--43) 표 참조. §4.3 sign convention의 강제를 CI로 보장. golden fixture의 `sign_expected.tsv`를 정의. — **§4.7·§4.3·§8.2·§16 MVP-1a**

cross-feeding (교차 영양 / 상호 대사물 공급)
: 한 멤버 m이 분비(+)한 대사물을 다른 멤버 m′이 흡수(−)하는 멤버 간 대사 교환. edge `m→m′` 성립 조건 = `m flux>0(분비) ∧ m′ flux<0(흡수)`, edge weight = `min(|m 분비|, |m′ 흡수|)` [mmol/gDW/h]. CMIG가 추출·typing하는 핵심 상호작용. — **§4.3·§10**

exchange decomposition (교환 분해)
: community의 전체 exchange flux를 (a) 환경과의 **net exchange** 와 (b) 각 **멤버↔공유 pool 기여** 로 분해하는 것. external profile과 cross-feeding edge 추출의 기반. — **§4.3·§10 AN-COMMUNITY**

external profile (외부 프로파일 / external metabolite profile)
: community가 환경(외부 medium pool)과 주고받는 **net exchange flux** 의 프로파일. 분비(+)/흡수(−)를 대사물별로 나타내며 External Profile Viewer의 net diverging bar·heatmap·scenario diff 입력. baseline vs constrained delta의 비교 대상. — **§1·§4.3·§10·§11**

tidy contract (tidy 데이터 계약) — §4.6
: → [1.E](#e-tidy-contract-5테이블-한-줄-요약--46) 참조. 모든 분석 산출의 단일 출력 계약 = `nodes / edges / profile / matrix / timecourse` (parquet). 전 소비자가 단일 reader 경유. 스키마 버전 필드 + 계약 테스트 필수. sweep store는 별도(§5). — **§4.6·§10·§16 MVP-1a**

NamespaceDecision (네임스페이스 매핑 결정)
: exchange 대사체 매핑 결정 1건의 audit 레코드 — confidence(`high`|`low`)·decision(`resolved`|`unresolved`|`warned`)·rationale·audit_ts. 이 레코드 집합이 곧 run_hash 구성요소 `namespace_mapping_decisions`이며 gate 입력이자 audit trail 단위. **자동병합 금지**. — **§4.8·§5·§7·§10**

namespace gate (네임스페이스 하드 게이트) — §4.8
: → [1.B](#b-namespace-gate-의미--48) 참조. solve 직전 exchange 대사물의 namespace 정합·confidence 검사 필수 게이트. unresolved high-confidence → solve 차단·해소 요구. low-confidence → 경고 후 진행·자동병합 금지·audit trail. — **§4.8·§6·§10·§16 MVP-1a·A10**

### 2.6 재현성 (Reproducibility) — §7·§10·§16

> 재현(reproduction) = **objective + 정규화 flux(pFBA+tie-break) + solver 버전 일치**(§7).

run_hash (재현성 해시) — §10
: 단일 community solve(또는 sweep run) 입력의 결정적 동일성을 식별하는 정규화 hash. **정확히 11개 구성요소**(→ [3장](#3-run_hash-11-구성요소-레퍼런스--571014))로 구성. AN-SWEEP 캐시 키(재계산 회피)이자 재현성 자산. 동일 11구성요소 → 캐시 hit, 1개라도 변경 → miss·재계산. `env_lock`은 run_hash에 **포함되지 않는다**(manifest inputs에만, §7). — **§5·§7·§10·A14**

RunManifest (런 매니페스트)
: 단일 run의 완전한 재현 메타데이터 레코드. `inputs`(checksum·env lock·namespace 결정), `engine`(micom exact pin·tradeoff_f), `solver`(growth_solver QP·flux_solver LP·tolerance·flux_report_status), `algorithms`(metric_mode·minimal_medium·seed·normalization), `sweep`(axes·n_runs·run_hash), `software`(cmig_core_version 포함), `figure_specs`, `platform`. — **§7·§2**

env lock (환경 잠금)
: RunManifest inputs의 의존성 환경 잠금 기록(conda/uv lock 등). solver·MICOM·cobrapy 바이너리 의존을 결정적으로 재현하기 위한 환경 명세. **run_hash 11구성요소에는 미포함**, manifest inputs에만 기록. lock 포맷은 `(Design에서 확정)`. — **§7·§10**

flux normalization method (flux_normalization_method)
: flux 정규화 방법(pFBA 기반·tie-break 포함). run_hash 11구성요소 중 하나이며 RunManifest `algorithms.normalization`에 기록. 재현성이 정규화 flux 일치를 요구하므로 run_hash·manifest 양쪽 필수. enum 값셋은 `(Design에서 확정)`. — **§7·§10·§4.4**

cmig_core_version (CMIG core 버전)
: CMIG core(부가가치 계층) 버전. run_hash 11구성요소 중 하나이며 software 버전 기록. §5 엔티티 필드로 미명시 — manifest/Scenario commit 시 주입 가정, 보유 위치는 `(Design에서 확정)`. — **§7·§8·§10**

micom_version (MICOM exact version)
: 정확 pin된 MICOM 버전(`micom==X.Y.Z`). run_hash 구성요소이자 golden 승격 게이트 대상 — 버전 업그레이드는 solver별 golden 통과 후에만 승격(미통과 시 차단). 구체 버전은 `(Design에서 확정)`. — **§4.1·§7·§16·§17**

float rounding/tolerance hash (부동소수 라운딩/허용오차 해시)
: golden 비교·run_hash 직렬화 시 float 컬럼에 hash 전 rounding/tolerance(예: **6 decimal**·abs/rel tol) 적용 후 정규화 hash. 부동소수·alternate optima 잡음을 흡수하여 결정적 비교 보장. rounding vs tolerance 택일/병행·구체값은 `(Design에서 확정)`. — **§16·§10·A17**

golden fixture / promotion gate (골든 픽스처 / 승격 게이트)
: `fixtures/community_3_member/` = models · `expected/`(nodes/edges/profile.parquet + config.json) + growth/sign expected. float rounding/tolerance 후 정규화 hash 비교. **solver별 분리**(`gurobi`·`osqp`) CI 매트릭스. MICOM 버전 업그레이드는 golden 통과 시에만 승격되는 게이트. — **§4.1·§10·§16 MVP-1a·§17·A1·A17**

osqp_growth_highs_flux (solver golden 변형 — **폐기**)
: (구) growth=OSQP(QP)→flux=HiGHS(LP) 조합 변형. **폐기됨**(cmig-analysis-completion F1): HiGHS는 실 LP 재계산을 하지 않아 osqp와 동일했고, HiGHS 의존을 제거해 full-flux를 gurobi 전용으로 단순화. 무라이선스 경로는 `osqp`(qp_only_approximate). — `docs/decisions/2026-06-01-golden-solver-list.md`

flux_report_status (flux 보고 상태)
: flux 산출의 신뢰 상태 플래그. LP flux_solver 부재 시 `QP-only approximate`로 표기(→ [1.D](#d-qp-only-approximate-의미--42)). 대비 상태값(`full` 등) 명칭은 `(Design에서 확정)`. — **§7·§4.2·§4.4**

### 2.7 solver·라이선스 (Solvers & Licensing) — §2

solver capability matrix (솔버 능력 매트릭스)
: 분석 유형(LP/QP/MILP)별 사용 가능 solver 표. **LP**=Gurobi/HiGHS/CPLEX · **QP**=Gurobi/OSQP/CPLEX(+HiGHS experimental) · **MILP**=Gurobi/HiGHS/CPLEX. OSQP=QP 전용(flux는 LP 재계산), HiGHS-QP=experimental, GLPK=GPL→**비번들(unbundled)**. capability 부재 시 **해당 분석만 비활성화**(앱 전체 강등 아님). — **§2·§16 MVP-0·A6·A7**

| problem class | 사용 가능 solver | 비고 |
|---|---|---|
| **LP** | Gurobi · HiGHS · CPLEX | pFBA/FVA/flux 정규화·minimal medium의 LP |
| **QP** | Gurobi · OSQP · CPLEX (+ HiGHS *experimental*) | member growth L2 |
| **MILP** | Gurobi · HiGHS · CPLEX | cardinality minimal medium |

growth_solver / flux_solver 분리 (solver role separation)
: cooperative tradeoff 2단계 solve를 위한 solver 역할 분리. `growth_solver`(QP)로 member growth L2 확보 → growth/community constraint 고정 → `flux_solver`(LP)로 pFBA/normalization 재수행. OSQP로 QP growth 후 LP solver(Gurobi/HiGHS/CPLEX)로 flux 재계산. LP 부재 시 `QP-only approximate` 표기. manifest에 분리 기록. — **§4.2·§7·A5**

default solver (기본 solver)
: 기본 solver = **Gurobi**(Plan §7.2 결정·권장; spec §2='Gurobi(권장)'). CI=Gurobi WLS; 무라이선스 경로는 highs·osqp golden으로 보존. 무라이선스 환경 자동 fallback 규칙은 `(Design에서 확정)`. — **§2·Plan §7.2**

GLPK (GPL solver)
: GPL 라이선스 solver → **번들/배포 제외(미번들)**. capability matrix에 존재하되 `is_bundled=false`. capability가 아닌 **라이선스 정책** 사안(§2·A7). — **§2·A6·A7**

GEM (genome-scale metabolic model / 게놈 규모 대사 모델)
: 한 생물의 전체 대사 reaction·metabolite·gene을 stoichiometric 행렬로 표현한 제약기반 모델. CMIG community 멤버(MemberModel)의 기본 입력 단위, **`{SBML, JSON, MAT}` 폐쇄 enum**으로만 import·**pickle 금지**(§5·§8). (HostModel은 **PART II** G2 범위.) — **§1·§5·§11**

community FBA (커뮤니티 FBA / community flux balance analysis)
: 다수 미생물 GEM을 하나의 community 모델로 구성해 community/member growth·exchange flux를 제약기반 최적화로 푸는 분석. CMIG는 이 solve를 **MICOM(정확 pin·public API only)에 위임**하고(`is_cmig_owned=false`), namespace 정합·sign 정규화·tidy·추출·delta·sandbox·sweep의 부가가치 계층만 소유한다. — **§1·§2·§4.1·§4.2·§10·§18**

### 2.8 GUI 패턴 (GUI Patterns) — §10·§11

preview vs Apply/commit (프리뷰 대 적용/커밋) — A11
: → [1.C](#c-preview-vs-applycommit--a11) 참조. sandbox run은 기본 preview(임시)이며 sweep/cache/store에 비기록. Apply/Save 시에만 Scenario/Run artifact로 승격. — **§10·§11·§8·A11**

debounced re-solve (디바운스 재solve)
: sandbox에서 bound 드래그 중 매 입력마다 solve하지 않고, 드래그를 놓는 등 안정화 시점에만 재최적화(§4.2 cooperative tradeoff)를 트리거하는 패턴. 인터랙티브 latency·UI 프리즈 방지, 취소 가능. debounce 지연(ms)·취소 정책은 `(Design에서 확정)`. — **§10·§11·§8·§4.2**

linked selection / highlight (연동 선택·하이라이트)
: 그래프·프로파일·테이블 간 선택을 연동하는 GUI 원칙(§11). Interaction Graph Viewer·Inspector와 결합. — **§11**

coverage% (네임스페이스 커버리지)
: 전체 exchange 대사체 중 매핑이 resolved된 비율(%). Model Manager에 namespace 상태(coverage%·unresolved 바로가기)로 상시 노출(§11). 산출식(분모=전체 exchange metabolite 정의)은 spec 미명시 → `(Design에서 확정)`. — **§11**

부호 범례 상시 (sign legend always-on)
: GUI에 부호 규약(`+`=분비/`−`=흡수) 범례를 상시 표시하는 i18n/접근성 요구(NFR). sign 혼동 silent error 방지. — **§11·NFR**

---

## 3. run_hash 11 구성요소 레퍼런스 — §5·§7·§10·A14

> `run_hash`는 **정확히 11개** 구성요소로 구성된다(가감 금지). 1개라도 변경 시 캐시 miss·재계산. AggregationStore·RunManifest·reproducibility의 run_hash는 동일 11구성요소·동일 직렬화·동일 해시로 **비트 단위 일치**해야 한다. `env_lock`은 run_hash에 **포함되지 않는다**(manifest inputs에만).

| # | 구성요소 (component) | 설명 | 매핑 |
|---:|---|---|---|
| 1 | **model checksum** | 멤버 GEM 모델 파일 checksum | `MemberModel.source.checksum` (§5) |
| 2 | **medium checksum** | 배지(Medium) 정의 checksum | `Medium.checksum` (§5) |
| 3 | **member set** | 커뮤니티 멤버 id 집합(결정적 정렬) | `Scenario.member_set` (§5) |
| 4 | **abundance** | 멤버별 abundance(해소·정규화 후) | `CommunityModel.members.abundance` (§5·§11) |
| 5 | **bounds** | reaction bound 제약(편집·sandbox commit 반영) | `Scenario.constraints` (§5) |
| 6 | **tradeoff f** | cooperative tradeoff `f` (0<f≤1) | `config.tradeoff_f` (§4.2) |
| 7 | **solver setting** | growth(QP)·flux(LP) solver·tolerance·옵션 (단, tolerance/옵션의 run_hash 직렬화 포함 여부는 `Design에서 확정`, schema OD-13) | `RunManifest.solver` (§4.2·§7) |
| 8 | **micom_version** | MICOM exact pin 버전 | `RunManifest.engine.micom_version` (§4.1) |
| 9 | **cmig_core_version** | CMIG core 버전 | `RunManifest.software.cmig_core_version` (§7) |
| 10 | **namespace_mapping_decisions** | namespace gate(§4.8) 매핑 결정(audit) | `RunManifest.inputs.namespace_decisions` (§4.8) |
| 11 | **flux_normalization_method** | flux 정규화 방법(pFBA+tie-break) | `RunManifest.algorithms.normalization` (§4.4) |

> 참고: spec §5/§7의 `model/medium checksum` 압축 표기는 **#1 model checksum + #2 medium checksum 2개**를 합친 것으로, 분리하면 11개다. run_hash 해시 알고리즘·canonical 직렬화(순서·구분자·인코딩)는 `(Design에서 확정)`(plan §8.2). 구성요소 정의 변경 시 sweep 캐시 무효화·`manifest_schema_version` bump·마이그레이션 정책 적용(plan §6.2·§6.3).

---

## 4. 범위 외 용어 (Out of Scope — PART II) — §12–§15

> 아래는 **PART II Extension Roadmap (범위 외)** 이며 본 Baseline 용어집의 정의 대상이 아니다. 식별·경계용으로만 표기한다.

| 용어 (term) | PART II 모듈 | spec 앵커 |
|---|---|---|
| host-microbe (G2), HostModel 본격 구성, lumen/blood 2-interface, viability constraint | G2 Host-Microbe (선행 spike 필수) | §12·A12 (PART II) |
| dFBA (AN-DFBA), well-mixed dynamic FBA, Michaelis–Menten uptake | dFBA | §13 (PART II) |
| consortium search, targets[], direction semantic preset, weighted score, Pareto | G3 다중타깃 search | §14·A13 (PART II) |
| StatsConfig, effect size, BH-FDR, PCA·클러스터링, UMAP·volcano | G5 통계 | §15·A15 (PART II) |
| Escher Metabolic Map | optional post-MVP | §11 (범위 외) |

---

## 5. 미결정 사항 (Open Decisions)

> spec에 명시되지 않아 Design에서 확정해야 하는 항목. 본 용어집 정의에 `(Design에서 확정)`으로 표기된 지점의 집약.

- **run_hash 직렬화**: 해시 알고리즘(예: SHA-256)·11구성요소 canonical 직렬화 순서·구분자·인코딩 (§10·plan §8.2).
- **float rounding/tolerance**: decimal 자릿수(예: 6)·abs tol·rel tol 값·컬럼별 적용 정책·rounding vs tolerance 택일/병행 (§16·A17).
- **MICOM exact pin 버전** `micom==X.Y.Z` 확정 (§4.1·§16).
- **namespace confidence**: high/low 임계 기준·산정 방식 (§4.8).
- **coverage% 분모 정의**: 전체 exchange metabolite 기준(멤버별 합집합 vs pool 기준) (§11).
- **sign label enum 통일**: 멤버↔pool '분비'를 환경 secretion과 동일 enum으로 통일할지 (§4.7).
- **flux_report_status 대비값**: `QP-only approximate`의 대비 상태(`full` 등) 명칭 (§4.2·§4.4·§7).
- **CMIG-MIP/MRO 산식**: 정확 formula 및 optional SMETANA-compatible 매핑 (§4.5·A9).
- **flux_normalization_method enum 값셋**·metric_mode enum 값셋 (§4.4·§4.5·§7).
- **tidy 컬럼 표준명**: node_id/edge type/flux/label 등 + 스키마 버전 필드 (§4.6·plan §6.3).
- **AggregationStore**: condition_id 생성 규칙·물리 경로/분할·metric 허용 도메인 enum·value 단위·diagnostic 구조 (§5·§10).
- **abundance 단위**: 절대(cell/biomass) vs 상대(dimensionless)·normalize 모드·override 우선순위 정밀 규칙 (§5·§11).
- **checksum 알고리즘**·**env_lock 직렬화 포맷**(conda/uv lock) (§5·§7).
- **debounced re-solve**: debounce 지연(ms)·취소 정책·`no significant change` 판정 임계(FVA 대비 변화량) (§10·§17).
- **minimal medium tie-break** 결정적 규칙 구체화 (§4.5).
- **HiGHS-QP(experimental)** baseline 활성/비활성 여부·default solver 무라이선스 fallback 규칙 (§2·A6).
- **cmig_core_version 보유 엔티티/주입 시점** (§7·§8).

---

## 6. Spec 앵커 색인 (Spec Anchor Index)

| 앵커 | 제목 | 본 용어집 관련 |
|---|---|---|
| §1 | 제품 정의 및 범위 | GEM·external profile·차별점(delta) |
| §2 | 의존성 정책(Build vs Buy·solver capability matrix·라이선스) | [2.7](#27-solver라이선스-solvers--licensing--2) |
| §3 | 아키텍처 | 직렬화 정책(pickle 금지) |
| §4.1 | 책임/정책(MICOM 위임·public API) | community FBA·micom_version |
| §4.2 | Cooperative tradeoff + flux 재계산(QP→LP pFBA) | [1.D](#d-qp-only-approximate-의미--42)·[2.3](#23-알고리즘수치-algorithms--numerics--4244 45) |
| §4.3 | Sign convention(강제) | [1.A](#a-부호-규약-표-sign-convention--43)·[2.5](#25-규약계약-conventions--contracts--434647) |
| §4.4 | 수치(pFBA·QP-only·loopless·infeasible) | [2.3](#23-알고리즘수치-algorithms--numerics--4244 45) |
| §4.5 | CMIG-MIP/MRO + minimal medium(cardinality MILP) | [2.4](#24-지표-metrics--45)·minimal medium |
| §4.6 | Tidy 데이터 계약 | [1.E](#e-tidy-contract-5테이블-한-줄-요약--46) |
| §4.7 | Sign 테스트 계약(의무·canonical) | [1.A](#a-부호-규약-표-sign-convention--43)·sign-test contract |
| §4.8 | Namespace hard gate(필수) | [1.B](#b-namespace-gate-의미--48)·NamespaceDecision |
| §5 | 데이터 모델 (MemberModel·AggregationStore·run_hash 11) | [2.1](#21-도메인-엔티티-core-domain-entities--5)·[3](#3-run_hash-11-구성요소-레퍼런스--571014) |
| §6 | 모델 품질 검증 | namespace gate(solve 직전) |
| §7 | 재현성(RunManifest·run_hash 11) | [2.6](#26-재현성-reproducibility--71016)·[3](#3-run_hash-11-구성요소-레퍼런스--571014) |
| §8 | 비기능 요구사항(pickle 금지·preview 비기록) | [1.C](#c-preview-vs-applycommit--a11)·직렬화 정책 |
| §9 | 출판용 그림(R 별도 프로세스) | tidy 소비자(R export) |
| §10 | Baseline 분석 기능(AN-* 6종·run hash 정의) | [2.2](#22-분석-모드-analysis-modes--10)·[3](#3-run_hash-11-구성요소-레퍼런스--571014) |
| §11 | Baseline GUI | [2.8](#28-gui-패턴-gui-patterns--1011) |
| §16 | MVP 로드맵(MVP-0~2·golden fixture 구조·solver별 분리) | [2.6](#26-재현성-reproducibility--71016)·golden fixture |
| §12–§15 | PART II (host-microbe·dFBA·다중타깃·통계) | [4](#4-범위-외-용어-out-of-scope--part-ii--1215) (범위 외) |
| 부록 A | 설계 결정 요약(A1·A6·A7·A9·A10·A11·A12·A14·A17 등) | 각 항목 교차 검증 |

---

> **문서 종료.** 본 용어집은 PART I Baseline 권위 용어 정의이며, 다른 클러스터(엔티티·재현성·집계 스토어·namespace/sign/golden)의 entity·invariant가 참조하는 단일 근거다. 정의 충돌 시 본 문서와 `CMIG_명세서_v3.0.md`를 우선한다.