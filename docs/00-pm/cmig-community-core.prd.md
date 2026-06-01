# cmig-community-core PRD — PART I Implementation Baseline (MVP-0 ~ MVP-2)

> **요약(One-liner):** 커뮤니티 FBA를 **MICOM(정확 pin·public API)** 에 위임하고, CMIG가 **namespace 정합·sign 정규화·tidy 계약·cross-feeding/delta 추출·constraint sandbox·sweep·출판급 R 그림** 의 부가가치 계층을 소유하는, **재현성(run_hash)** 과 **namespace 무결성** 을 일급으로 다루는 네이티브 데스크톱 커뮤니티 대사 상호작용 분석 도구.
>
> **Project**: CMIG (Community Metabolic Interaction GUI) — native desktop scientific application (NOT SaaS/web)
> **Platform**: macOS Apple Silicon (Must), Windows 10/11 x64 (Must) · macOS Intel/Linux (Should)
> **Stack**: PySide6/Qt GUI + Python sidecar (cobrapy + MICOM + CMIG 부가가치 계층) · optional R Render · optional Docker · optional Remote backend
> **Author**: PM Agent Team (pm-lead)
> **Date**: 2026-05-31
> **Status**: Draft — Pre-Plan PM Discovery
> **Authoritative ground truth**: `CMIG_명세서_v3.0.md` (§1–§11, §16). 본 PRD는 명세를 권위 자료로 두고 **시장/사용자/가치/포지셔닝 framing + 우선순위화된 baseline 요구사항 집합** 을 추가한다. **명세와 모순되지 않는다.**

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 미생물 community의 대사 상호작용(cross-feeding·external profile·멤버 추가 영향) 분석은 현재 MICOM/SMETANA 같은 **스크립트 전용 라이브러리/CLI**에 갇혀 있다. 인터랙티브한 가설 형성(멤버 add/remove, 제약 perturbation)과 **재현 가능·출판급** 결과 산출이 단절되어, 연구자가 bespoke MICOM 스크립트를 작성·유지보수해야 한다. |
| **Solution** | 커뮤니티 FBA 엔진은 **MICOM에 위임**(정확 pin·public API + documented flux only)하고, CMIG가 **namespace hard gate, sign 정규화, tidy 데이터 계약, cross-feeding/delta 추출, G1 constraint sandbox, G4 sweep, R 출판 그림** 을 소유하는 PySide6 네이티브 GUI. 모든 결과는 **run_hash 재현성** 과 **golden fixture 검증** 으로 뒷받침된다. |
| **Function/UX Effect** | (1) Headless 커뮤니티 코어가 CLI/GUI 공통으로 동작, (2) Cytoscape 스타일 interaction graph + linked selection + inspector, (3) **add-member delta** 와 **constraint sandbox(bound 제약 변경+재최적화, preview→Apply/Save 승격)** 로 가설을 즉시 시각 확인, (4) sweep 배치(캐시·실패 diagnostic), (5) SVG/TIFF 출판 그림. |
| **Core Value** | community-FBA를 **스크립트 전문가 워크플로 → 인터랙티브·재현 가능·출판 준비 데스크톱 도구** 로 전환. 고유 wedge = **유일한 네이티브 GUI** 가 MICOM에 community FBA를 위임하면서 interaction/delta/sandbox/sweep + 출판급 R 그림을 소유하고, **run_hash 재현성 + namespace 무결성** 을 일급으로 둔다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | community 대사 상호작용 분석이 스크립트 전용에 갇혀, 인터랙티브 가설형성·재현성·출판품질이 단절됨 |
| **WHO** | 전산/시스템 생물학자, microbiome·gut-microbiota 연구자, 미생물 community 대사공학자 (2차: bioinformatics core facility, constraint-based modeling 대학원생) |
| **RISK** | (1) namespace mismatch로 잘못된 cross-feeding 결론, (2) sign 혼동, (3) MICOM API/버전 drift, (4) OSQP LP 정확도, (5) sandbox 보상 우회로 인한 오해석 — 모두 명세의 hard gate/test/golden/FVA로 방어 |
| **SUCCESS** | golden fixture 통과(solver별), sign-test CI green, namespace gate 차단동작, run_hash 캐시 정확성, MICOM-version golden regression 통과(승격 게이트) |
| **SCOPE** | MVP-0 Foundation → MVP-1a Headless core(1순위) → MVP-1b GUI graph → MVP-1c validation → MVP-2 delta/medium/R export/G1 sandbox/G4 sweep. **PART II(host-microbe/G2·dFBA·다중타깃/G3·통계/G5)는 범위 외.** |

---

## 1. Discovery — 기회 분석 (Opportunity Solution Tree)

> Teresa Torres OST. **Outcome → Opportunities → Solutions → Experiments.** 명세 §1, §10–§11 근거.

**Desired Outcome:** 연구자가 bespoke MICOM 스크립트 없이, community 대사 상호작용 가설을 **인터랙티브하게 형성하고 재현·출판 품질로 소통** 한다.

### 1.1 Opportunity 1 — "스크립트 작성/유지보수 부담"
연구자는 community 구성·solve·결과 추출을 매번 Python 스크립트로 작성해야 하고, MICOM API/solver 변경 시 깨진다.
- **Solution S1.1:** Headless 커뮤니티 코어(MVP-1a)가 CLI에서 모델/배지만으로 산출 — 스크립트 불필요.
- **Solution S1.2:** MICOM 정확 pin + public API only + golden 승격으로 버전 drift 방어.
- **Experiment:** MICOM 튜토리얼을 GUI/CLI로 재현(MVP-1c) → "스크립트 0줄로 동일 결과" 입증.

### 1.2 Opportunity 2 — "cross-feeding/external profile를 신뢰할 수 없음"
namespace mismatch·sign 혼동이 잘못된 상호작용 결론으로 이어진다(silent failure).
- **Solution S2.1:** **Namespace hard gate(§4.8)** — unresolved high-confidence exchange mapping이면 solve 차단.
- **Solution S2.2:** **Sign 테스트 계약(§4.7)** — canonical case CI로 부호 규약 강제.
- **Solution S2.3:** Cross-feeding 추출(분비+ ∧ 흡수−, weight=min) 단일 진입점.
- **Experiment:** cross-feeding sanity + sign tests(MVP-1c) — 의도적 mismatch fixture로 gate 차단 확인.

### 1.3 Opportunity 3 — "정적 분석은 가설 탐색에 느림"
멤버를 더하거나 제약을 바꾼 영향을 보려면 매번 재스크립트·재실행.
- **Solution S3.1:** **AN-DELTA** — baseline 복제→멤버 추가→동일 조건 재solve→차이.
- **Solution S3.2:** **G1 constraint sandbox** — reaction **bound 제약 변경 후 재최적화**(flux 직접 편집 아님), debounced re-solve, preview→Apply/Save 승격, 보상 우회 시 FVA/no-change 진단.
- **Experiment:** add-member delta + sandbox preview overlay(MVP-2) — drag 후 external-profile delta 즉시 표시.

### 1.4 Opportunity 4 — "결과를 재현/출판하기 어려움"
solver·버전·정규화 차이로 재현 실패. 그림은 별도 도구로 다시 그림.
- **Solution S4.1:** **run_hash**(model/medium checksum·member set·abundance·bounds·tradeoff f·solver·micom_version·cmig_core_version·namespace 결정·flux normalization) + **golden fixture**.
- **Solution S4.2:** **G4 sweep** run-hash 캐시(재계산 회피) + 실패 run diagnostic 저장.
- **Solution S4.3:** **R Render**(SVG/TIFF 600dpi, Figure Composer) 출판 그림.
- **Experiment:** golden regression CI(solver 매트릭스) + run_hash 캐시 hit 검증(MVP-1a/MVP-2).

### 1.5 Top Assumptions (Impact × Risk 우선순위)
| # | Assumption | Impact | Risk | 검증 방법 |
|---|-----------|:---:|:---:|---|
| A1 | MICOM public API + documented flux(`cooperative_tradeoff(fluxes=True, pfba=...)`)만으로 충분 | High | High | MVP-1a 통합 + 미노출 시 upstream PR |
| A2 | OSQP growth→LP pFBA flux 재계산이 alternate-optima 잡음 안에서 안정적 | High | High | solver별 golden(osqp_growth_highs_flux) + float tolerance hash |
| A3 | namespace hard gate가 false-block 없이 실제 mismatch만 차단 | High | Med | confidence 임계 + audit trail + sanity fixture |
| A4 | bound-constraint sandbox 재최적화가 debounce 내 인터랙티브 속도 | Med | Med | sandbox spike(재solve latency) |
| A5 | 연구자가 "스크립트 대체" 가치를 GUI 전환 비용보다 높게 평가 | High | Med | MVP-1c 튜토리얼 재현 + 베타 사용자 인터뷰 |

---

## 2. Strategy — Value Proposition & Positioning

### 2.1 JTBD (6-Part)
- **When** 미생물 community의 대사 상호작용을 연구할 때,
- **I want to** 멤버를 인터랙티브하게 add/remove하고 제약을 perturb하여 cross-feeding·external profile 변화를 즉시 보고,
- **so I can** bespoke MICOM 스크립트를 작성·유지보수하지 않고 가설을 형성·소통한다.
- **Functional:** community/member growth, exchange decomposition, cross-feeding, delta, sandbox, sweep.
- **Emotional:** "내 분석이 맞다"는 확신(gate·sign·golden) + "재현/공유 가능"하다는 안심(run_hash·R 그림).
- **Social:** 출판급 그림·재현 manifest로 동료·리뷰어에게 신뢰성 있게 제시.

### 2.2 Value Proposition Canvas (요약)
| Customer Jobs | Pains | Pain Relievers (CMIG) | Gains | Gain Creators (CMIG) |
|---|---|---|---|---|
| community solve·상호작용 추출 | MICOM 스크립트 작성/유지 | Headless core + GUI, 스크립트 0줄 | 빠른 가설 탐색 | add-member delta · constraint sandbox |
| 결과 신뢰 | namespace/sign silent error | hard gate + sign 테스트 CI | 정확한 cross-feeding | 단일 진입점 sign 정규화 |
| 재현·출판 | solver/버전 drift, 그림 재작업 | run_hash + golden + R export | 리뷰어 통과 | golden regression · figure_spec |

### 2.3 Positioning Statement
**전산/시스템 생물학자** 를 위한 CMIG는, **MICOM 라이브러리·SMETANA CLI·CNApy(단일종 GUI)** 와 달리, **community FBA를 MICOM에 위임하면서 interaction/delta/sandbox/sweep + 출판급 R 그림** 을 소유하는 **유일한 네이티브 GUI** 이며, **run_hash 재현성과 namespace 무결성** 을 일급으로 둔다.

### 2.4 SWOT (요약)
- **S:** MICOM 위임으로 엔진 정확성 차용 + 고유 부가가치(delta/sandbox/sweep) + 재현성/무결성 일급.
- **W:** 데스크톱 배포 복잡도(3 OS·solver matrix·R 격리), MICOM 버전 결합.
- **O:** GUI 부재 시장 공백(MICOM=라이브러리, SMETANA=CLI), 출판급 그림 수요.
- **T:** MICOM API 변경, Gurobi 상용 의존, 데스크톱 대비 노트북/클라우드 트렌드.
- **SO 전략:** MICOM 위임 + GUI wedge로 "MICOM의 GUI 프론트엔드" 포지션 선점.
- **WT 전략:** 정확 pin + golden 승격 게이트로 버전 drift 위험 봉쇄; GLPK 미번들·R 프로세스 격리로 라이선스 위험 차단.

---

## 3. Research — 시장·사용자·경쟁

### 3.1 Personas (3)
**P1 — 미생물 community 시스템 생물학자 (Primary / Beachhead)**
- 역할: gut-microbiota·환경 microbiome의 cross-feeding을 cobrapy/MICOM으로 모델링.
- JTBD: 멤버 조합·배지에 따른 상호작용 변화를 빠르게 탐색·출판.
- Pain: MICOM 스크립트 반복 작성, 결과 재현·그림 재작업.
- CMIG 가치: add-member delta + sandbox + R export.

**P2 — Microbiome 연구자(실험 중심, 모델링 보조)**
- 역할: wet-lab 가설을 in silico로 사전 점검.
- JTBD: "이 멤버를 넣으면 butyrate 분비가 늘까?"를 코드 없이 확인.
- Pain: constraint-based modeling 코딩 장벽.
- CMIG 가치: GUI Community Builder + Check Growth + external profile viewer.

**P3 — 미생물 대사공학자 / consortium 설계자**
- 역할: 특정 물질 생산 community 후보 탐색(기초).
- JTBD: 배지·abundance·bounds sweep로 민감도 파악.
- Pain: sweep 배치·캐시·실패 추적을 수동 관리.
- CMIG 가치: G4 sweep(run-hash 캐시·실패 diagnostic). *(다중타깃 자동 search는 PART II.)*

*2차: bioinformatics core facility(파이프라인 표준화·재현성), constraint-based modeling 대학원생(학습·재현).*

### 3.2 경쟁 환경 (real tools)
| Tool | 형태 | community FBA | GUI | 상호작용/delta | sandbox | sweep | 출판 그림 | 재현성 |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **MICOM** | Python 라이브러리 | ✅(엔진) | ❌ | 부분(코드) | ❌ | ❌ | ❌ | 코드 의존 |
| **SMETANA** | CLI | △(상호작용 점수) | ❌ | △ | ❌ | ❌ | ❌ | △ |
| **COMETS/BacArena** | 공간/agent 시뮬 | △(다른 목표) | △ | ❌ | ❌ | ❌ | ❌ | △ |
| **CNApy** | 단일종 GUI(최근접 GUI 유사물) | ❌(단일종) | ✅ | ❌ | △(편집) | ❌ | △ | △ |
| **Escher** | map viz | ❌ | ✅ | ❌ | ❌ | ❌ | △ | ❌ |
| **memote** | QC | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅(QC) |
| **CMIG** | **네이티브 GUI + 부가가치 계층** | ✅(MICOM 위임) | ✅ | ✅(delta·typing) | ✅(G1) | ✅(G4) | ✅(R) | ✅(run_hash·golden) |

**Wedge 요약:** MICOM=엔진(GUI 없음), SMETANA/COMETS=다른 형태/목표, CNApy=단일종 GUI. **community FBA를 MICOM에 위임하면서 interaction/delta/sandbox/sweep + 출판급 R 그림을 소유하는 유일한 네이티브 GUI** 가 CMIG의 빈틈.

### 3.3 시장 규모 (정성 — 학술 도구 framing, SaaS 아님)
- **TAM:** constraint-based metabolic modeling 연구자 전반(단일종 포함) — 전 세계 수만 명(cobrapy/COBRA Toolbox 사용자 기반).
- **SAM:** **community/microbiome 대사 모델링** 수행 연구자 — MICOM/SMETANA 사용·인용 community(수천 명 규모 추정).
- **SOM(beachhead 초기):** MICOM을 이미 쓰는데 **GUI·재현성·출판 그림** 이 필요한 lab — 초기 채택자 수십~수백 lab.
- *주의: 본 도구는 오픈/학술 데스크톱 도구이므로 매출 TAM이 아니라 **채택(adoption)·인용·lab 수** 로 측정한다.*

### 3.4 Customer Journey (P1, primary)
Awareness(MICOM 논문/튜토리얼·학회) → Consideration(GUI·재현성 필요 인지) → Onboarding(SBML import·namespace 상태·Check Growth) → **Aha(community solve→interaction graph + add-member delta)** → Habit(sandbox·sweep로 가설 반복) → Advocacy(R 그림으로 출판·재현 manifest 공유).

---

## 4. ICP · Beachhead · GTM

### 4.1 ICP (Ideal Customer Profile)
**이미 MICOM으로 community FBA를 수행하지만 GUI·재현성·출판 그림이 없어 스크립트에 묶여 있는** 전산/시스템 생물학 lab. macOS/Windows 데스크톱, Gurobi 학술 라이선스 또는 HiGHS 사용, SBML 모델 보유, 출판 압박 있음.

### 4.2 Beachhead Segment (Geoffrey Moore — 4-criteria scoring)
**선정: "MICOM 숙련 microbiome 시스템 생물학 lab"**

| 기준 | 평가 | 점수(1-5) |
|---|---|:--:|
| Target customer 명확성 | MICOM 인용/사용 lab — 식별 가능 | 5 |
| Compelling reason to buy | 스크립트 제거 + 재현성 + 출판 그림 | 5 |
| Whole product 충족 가능 | MVP-1a~MVP-2가 핵심 job 충족 | 4 |
| 경쟁 부재 | community GUI 직접 경쟁 없음 | 5 |

→ **합계 19/20.** Beachhead = MICOM 숙련 community modeling lab. 여기서 "스크립트 대체 + 재현 + 출판" whole product를 완성한 뒤 microbiome 실험 중심 연구자(P2)·core facility로 확장.

### 4.3 GTM (학술 도구 채널·지표)
- **채널:** MICOM 생태계(튜토리얼 재현·호환성으로 신뢰), 학회/워크숍 데모, GitHub release + 재현 manifest, 논문 methods 인용.
- **온보딩 wedge:** "MICOM 튜토리얼을 스크립트 0줄로 GUI에서 재현"(MVP-1c) → 즉시 add-member delta 체험.
- **채택 지표:** golden 통과 release 수, 재현 manifest 공유 건수, GUI로 산출된 figure가 들어간 논문/preprint 수, sandbox/delta 사용 세션 비율.
- **Battlecard(vs MICOM):** "MICOM은 엔진, CMIG는 그 위의 GUI — 같은 엔진, 같은 결과(golden), 스크립트 없이 인터랙티브·재현·출판."
- **Battlecard(vs CNApy):** "CNApy는 단일종 GUI. CMIG는 community(다종)·cross-feeding·delta·sandbox에 특화."

### 4.4 Growth Loop
재현 manifest·R 그림이 들어간 논문 → 다른 lab이 동일 분석 재현 시도 → CMIG로 import → golden 통과 신뢰 → 자신의 community 분석 → 또 출판. (재현성이 성장 루프의 엔진.)

---

## 5. 제품 요구사항 (Baseline 우선순위 집합)

> 모든 solve는 §4.8 namespace gate 통과 후 MICOM 호출. 출력은 §4.6 tidy 계약(`nodes/edges/profile/matrix/timecourse` parquet).

### 5.1 MVP-0 Foundation (P0)
| ID | 요구사항 | 근거 |
|---|---|---|
| FR-0.1 | PySide6 Qt shell — Project Explorer/Model Manager/Medium Editor 골격 | §11 |
| FR-0.2 | Python sidecar + Engine Interface(계산은 GUI 밖 job) | §3, §8 |
| FR-0.3 | SBML import(+JSON/MAT), summary, reaction/metabolite/gene 테이블 | §10, §11 |
| FR-0.4 | 기본 medium editor(CSV paste·preset·Check Growth) | §11 |
| FR-0.5 | FBA/pFBA(단일종 AN-SINGLE: knockout·exchange 요약·bound 편집·growth feasibility) | §10 |
| FR-0.6 | RunManifest 기록 + **solver capability matrix**(LP/QP/MILP, **GLPK 비번들=GPL**, capability 부재 시 해당 분석 비활성화) | §2, §7 |

### 5.2 MVP-1a Headless 커뮤니티 코어 (P0 — 1순위)
| ID | 요구사항 | 근거 |
|---|---|---|
| FR-1a.1 | **MICOM 통합** — 정확 pin(`micom==X.Y.Z`), **public API + documented flux only**(`cooperative_tradeoff(fluxes=True, pfba=...)`), internal 금지 | §4.1 |
| FR-1a.2 | **Namespace hard gate(§4.8)** — unresolved high-confidence exchange mapping → **solve 차단·해소 요구**; low-confidence는 경고 후 진행·자동병합 금지·audit trail | §4.8 |
| FR-1a.3 | **Sign 테스트 계약(§4.7)** — MICOM flux→(ui_flux,label) 단위테스트 + canonical case CI(환경 −10→uptake10/+8→secretion8; 멤버↔pool −5→uptake5/+3→분비3) | §4.7 |
| FR-1a.4 | **Tidy 데이터 계약** 출력(nodes/edges/profile parquet) | §4.6 |
| FR-1a.5 | Community/member growth · **exchange decomposition** · **cross-feeding 추출**(분비+ ∧ 흡수−, weight=min) · external profile | §4.3, §10 |
| FR-1a.6 | **OSQP growth → LP pFBA flux 재계산(§4.2)** — growth 확보 후 community constraint 고정→LP(Gurobi/HiGHS/CPLEX)로 pFBA/정규화 재수행; LP 부재 시 "QP-only approximate" 표기; growth/flux solver 분리 기록 | §4.2 |
| FR-1a.7 | **Golden fixture 통과** — `fixtures/community_3_member/` (models×3·medium.yaml·config.yaml) + expected_nodes/edges/profile.parquet + growth/sign_expected.tsv; **float 컬럼 rounding/tolerance 후 hash**; **solver별 golden 분리**(gurobi·highs·**osqp_growth_highs_flux**) CI 매트릭스 | §10, §16 |

**MVP-1a 완료 정의:** CLI 3개+ 미생물·배지에서 산출 + sign 테스트 통과 + gate 동작 + **golden fixture 통과(solver별).**

### 5.3 MVP-1b GUI Graph (P1)
| ID | 요구사항 | 근거 |
|---|---|---|
| FR-1b.1 | **Interaction Graph Viewer(Cytoscape 스타일)** — 노드/엣지 인코딩·레이아웃 | §11 |
| FR-1b.2 | 필터 · linked selection/highlight · Inspector | §11 |
| FR-1b.3 | **Gate UI** — namespace coverage%·unresolved 바로가기·차단 상태 표시 | §4.8, §11 |

### 5.4 MVP-1c 검증 (P1 — 승격 게이트)
| ID | 요구사항 | 근거 |
|---|---|---|
| FR-1c.1 | **MICOM 튜토리얼 재현**(GUI/CLI, 스크립트 0줄) | §16 |
| FR-1c.2 | cross-feeding sanity + sign 테스트 통과 | §4.7, §16 |
| FR-1c.3 | **MICOM-version golden regression**(버전 업그레이드는 golden 통과 후에만 승격) | §4.1, §16, §17 |

### 5.5 MVP-2 Delta · Medium · R export · G1 sandbox · G4 sweep (P1)
| ID | 요구사항 | 근거 |
|---|---|---|
| FR-2.1 | **AN-DELTA(add-member delta)** — baseline 복제→멤버 추가→동일 조건 재solve→차이(delta 뷰·delta network·delta heatmap) | §10 |
| FR-2.2 | **Scenario Compare** — A/B(또는 N)·동일 조건 고정 토글 | §10, §11 |
| FR-2.3 | Medium comparison · minimal medium(cardinality MILP) · limiting nutrient · sensitivity | §4.5, §10 |
| FR-2.4 | **CMIG-MIP/MRO + interaction typing**(영양 중복=MRO, cross-feeding 절감=MIP) | §4.5, §10 |
| FR-2.5 | **R Render Service**(별도 프로세스) — SVG(svglite)/TIFF(ragg 600dpi LZW), Figure Composer, figure_spec 재현, Python fallback | §9 |
| FR-2.6 | **G1 Constraint Sandbox** — reaction **bound constraint 변경 후 재최적화**(flux 직접 편집 아님); 멤버 bound 슬라이더 drag→**debounced 재solve(§4.2)**→baseline vs constrained **external-profile delta 오버레이**; 보상 우회로 변화 미미 시 **FVA 범위·"no significant change" 진단**; 취소·되돌리기. **preview 기본(임시) — sweep/cache/store 비기록; Apply/Save 시에만 Scenario/Run artifact 승격** | §4.2, §8, §10, §11 |
| FR-2.7 | **G4 Sweep** — 축{medium variant·abundance·member set·bounds·tradeoff f·solver}×값→N-run 배치(job)→long-format `sweep.parquet`; **run_hash 캐시(재계산 회피·재현)**; **실패 run도 condition_id별 diagnostic 저장(누락 금지)**; 캐시 hit 표시 | §5, §10 |
| FR-2.8 | **run_hash 정의 준수** = model/medium checksum·member set·abundance·bounds·tradeoff f·solver setting·**micom_version·cmig_core_version·namespace_mapping_decisions·flux_normalization_method** | §5, §7, §10 |

### 5.6 비기능 요구사항 (NFR — §8)
| ID | NFR | 근거 |
|---|---|---|
| NFR-1 | 성능: 계산은 GUI 밖(job)·Parquet·lazy graph·non-blocking(진행률·취소) | §8, §11 |
| NFR-2 | 보안: 127.0.0.1 바인딩·토큰·docker socket 미마운트·**pickle 금지** | §8 |
| NFR-3 | 안정성: GUI 생존·cancel/retry·infeasible diagnostic·capability 강등·QP-only 표기·**gate 차단**·**sandbox debounce/취소·preview 비기록** | §8 |
| NFR-4 | 라이선스: cobrapy LGPL(재검증)·**GLPK 미번들(GPL)**·Gurobi WLS 학술·**R 프로세스 격리** | §2, §8 |
| NFR-5 | 재현성: figure_spec·**MICOM golden 승격**·sweep/seed 기록·**run_hash에 micom/cmig 버전·namespace 결정·normalization 포함** | §7, §8 |
| NFR-6 | i18n/접근성: 한/영 토글·고대비 테마·**부호 범례 상시** | §11 |
| NFR-7 | 플랫폼: macOS Apple Silicon(Must)·Windows 10/11 x64(Must)·macOS Intel/Linux(Should) | header |

---

## 6. Success Criteria (구체적·테스트 가능 — 명세 acceptance gate 앵커)

| # | Success Criteria | 측정/Evidence | 명세 앵커 |
|---|---|---|---|
| SC-1 | **Golden fixture 통과(solver별)** — gurobi·highs·osqp_growth_highs_flux 각각 expected_nodes/edges/profile.parquet과 float rounding/tolerance 후 hash 일치 | CI 매트릭스 green | §10, §16, A17 |
| SC-2 | **Sign-test CI green** — canonical case(환경 −10→uptake10/+8→secretion8; 멤버↔pool −5→uptake5/+3→분비3) 단위테스트 통과 | sign_expected.tsv 일치 | §4.7, A10 |
| SC-3 | **Namespace gate 차단 동작** — unresolved high-confidence exchange mapping fixture에서 community solve가 **차단** + 해소 요구 메시지; low-confidence는 경고 후 진행·자동병합 없음·audit trail 기록 | gate blocking test | §4.8, A10 |
| SC-4 | **run_hash 캐시 정확성** — 동일 입력(11개 구성요소 동일)→캐시 hit·재계산 회피; 구성요소 1개라도 변경→miss·재계산; 실패 run은 diagnostic으로 저장(누락 0) | sweep 캐시 hit/miss 테스트 | §5, §10, A14 |
| SC-5 | **MICOM-version golden regression(승격 게이트)** — MICOM 버전 업그레이드는 golden 통과 시에만 승격; 미통과 시 차단 | regression CI | §4.1, §16, §17, A1 |
| SC-6 | **OSQP→LP 재계산 정확성** — osqp_growth_highs_flux golden이 gurobi golden과 tolerance 내 일치; LP 부재 시 "QP-only approximate" 표기 | solver별 golden 비교 | §4.2, A5/A6 |
| SC-7 | **MICOM 튜토리얼 재현** — 스크립트 0줄로 GUI/CLI에서 MICOM 튜토리얼 결과 재현 + cross-feeding sanity 통과 | MVP-1c 재현 로그 | §16 |
| SC-8 | **Sandbox preview 비오염** — preview solve가 sweep/cache/store에 기록되지 않음; Apply/Save 시에만 Scenario/Run으로 승격; 보상 우회 시 FVA/no-change 진단 표시 | preview/commit 분리 테스트 | §4.2, §8, §10, A11 |
| SC-9 | **tidy 계약 준수** — 모든 산출이 nodes/edges/profile parquet 스키마 일치 | schema 검증 | §4.6 |

---

## 7. Pre-mortem — Top 3 Risks & Mitigation

| # | 실패 시나리오 | 영향 | 완화 (명세 근거) |
|---|---|---|---|
| R1 | MICOM API/버전 drift로 산출 변화 또는 깨짐 | 코어 기능 정지·재현 실패 | 정확 pin + public API only + **golden 승격 게이트**(SC-5); 미노출 기능은 upstream PR (§4.1, §17) |
| R2 | namespace mismatch/sign 혼동이 silent하게 잘못된 cross-feeding 결론 생성 | 과학적 신뢰 붕괴 | **hard gate 차단(SC-3)** + **sign 테스트 CI(SC-2)** + 단일 진입점 변환 (§4.7, §4.8) |
| R3 | OSQP LP 정확도/alternate-optima 잡음으로 golden 불안정 | CI flakiness·재현 실패 | **OSQP growth→LP pFBA 재계산** + **float rounding/tolerance 후 hash** + solver별 golden 분리(SC-1, SC-6) (§4.2, §16) |

*추가 경계: 과범위(scope creep) → Baseline/Extension 엄격 분리(§16, A16); GLPK(GPL)/R(GPL) 라이선스 → 미번들·프로세스 격리(NFR-4).*

---

## 8. User Stories (대표 — INVEST)

- **US-1 (P1):** "연구자로서 3개 미생물 모델과 배지를 import하면, 스크립트 없이 community를 solve하고 cross-feeding graph를 본다." → FR-1a, FR-1b. **AC:** namespace gate 통과 시 solve, 미통과 시 차단 메시지; graph에 cross-feeding edge 표시.
- **US-2 (P1):** "연구자로서 community에 멤버 1개를 추가하면, 동일 조건에서 external-profile delta를 즉시 본다." → FR-2.1. **AC:** baseline 복제→재solve→delta network/heatmap 표시.
- **US-3 (P1):** "연구자로서 멤버 reaction bound를 drag로 조이면, preview로 constrained external-profile delta가 오버레이되고, Apply 전까지 store는 오염되지 않는다." → FR-2.6. **AC:** preview는 ephemeral; 보상 우회 시 FVA/no-change; Apply/Save 시 artifact 승격.
- **US-4 (P3):** "연구자로서 배지·abundance sweep을 돌리면, 동일 조건은 캐시 hit로 재계산을 피하고 실패 run은 diagnostic으로 남는다." → FR-2.7. **AC:** run_hash 캐시 hit 표시; 실패 condition_id별 diagnostic 저장.
- **US-5 (P1):** "연구자로서 분석 상태에서 출판 그림을 export하면, SVG/TIFF(600dpi)로 figure_spec과 함께 재현 가능하게 저장된다." → FR-2.5. **AC:** R 격리 프로세스; seed/figure_spec 저장.

---

## 9. Test Scenarios (Success Criteria 파생)

1. **Golden 매트릭스:** 3-member fixture를 gurobi/highs/osqp_growth_highs_flux로 solve → float tolerance 후 hash가 각 expected set과 일치 (SC-1).
2. **Sign canonical:** 환경 −10/+8, 멤버↔pool −5/+3 입력 → ui_flux·label이 sign_expected.tsv와 일치 (SC-2).
3. **Gate blocking:** unresolved high-confidence exchange fixture → solve 차단 + 해소 요구; low-confidence fixture → 경고 후 진행·자동병합 없음·audit 기록 (SC-3).
4. **Cache hit/miss:** 동일 11-구성요소 → hit; bounds 1개 변경 → miss·재계산; infeasible run → diagnostic 저장(누락 0) (SC-4).
5. **MICOM regression:** MICOM 버전 상향 fixture → golden 통과 시 승격, 미통과 시 차단 (SC-5).
6. **Sandbox preview:** drag preview N회 → sweep/cache/store 레코드 0; Apply 1회 → Scenario/Run artifact 1개 승격; 보상 우회 fixture → FVA/no-change 표시 (SC-8).
7. **튜토리얼 재현:** MICOM 튜토리얼 입력 → GUI/CLI 산출이 튜토리얼 결과와 cross-feeding sanity 일치 (SC-7).

---

## 10. Out of Scope — PART II Extension Roadmap (미래)

> 아래는 **본 baseline PRD 범위 외**. 설계는 명세에서 확정되었으나 MVP-0~2 구현·검증 초점을 흐리지 않도록 분리하며, 향후 로드맵으로만 언급한다.

- **G2 Host-Microbe (MVP-3, 선행 spike 필수):** Human-GEM + 미생물 community, host=community objective 미포함·viability/maintenance constraint 기본, 2-interface(lumen/blood) sign 규약, 구성 (A)/(B)는 spike 후 결정. (§12)
- **dFBA (MVP-3):** well-mixed dynamic FBA, Michaelis–Menten uptake, non-negativity, adaptive Δt. (§13)
- **G3 Consortium Search 단일·다중 타깃 (MVP-4):** targets[]·direction semantic preset·weighted(단위 정규화 필수)·**Pareto≤2 기본**·pre-screening·top-k·robustness. (§14)
- **G5 통계 (MVP-5):** 5a(분포·effect size·검정·BH-FDR) → 5b(PCA·클러스터링) → 5c(UMAP·volcano·advanced); 오용 경고·seed manifest. (§15)
- **Escher Metabolic Map:** optional post-MVP, map JSON 보유 시에만. (§11)

---

## 부록 — Attribution

PM Agent Team은 [pm-skills](https://github.com/phuryn/pm-skills)(Pawel Huryn, MIT License)의 프레임워크를 통합한다: Opportunity Solution Tree(Teresa Torres), JTBD 6-Part, Value Proposition Canvas, Beachhead(Geoffrey Moore), Pre-mortem.
도메인 ground truth: `CMIG_명세서_v3.0.md` v3.0 Implementation Baseline 승인본.

**다음 단계:** `/pdca plan cmig-community-core` (본 PRD가 Plan 문서에 자동 참조됩니다)
