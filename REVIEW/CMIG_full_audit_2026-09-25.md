# CMIG 전체 감사 진입 보고서 — 2026-09-25

검토자: GPT-6 Astra. 제품 기준 commit: `c45c836f0c12da04404a712f61f53bec0b346675` (`0.3.0`). 이번 통합 작업은 이 보고서만 작성했으며 제품 코드·테스트를 수정하거나 commit/push하지 않았다.

CMIG는 **배지·abundance·성장 제약 아래에서 목표 flux가 좋은 균주 집합을 찾는 계산 도구**로 상당한 실행·검증 기반을 갖췄다. 그러나 지원 입력의 일부 경로에서 물질 공급, 숙주 전달, 그림의 점수가 잘못 표현되고 GUI 설정과 실행 조건이 달라질 수 있다. 아래 P1 결함을 먼저 고친 뒤 기능 확장과 배포 UX를 진행하는 것이 적절하다.

상세 재현·소스 부록은 [과학 코어 감사](scientific_audit_2026-09-25.md)(SC-01~08)와 [UI·워크플로 감사](ui_workflow_audit_2026-09-25.md)(F1~12)에 있다. 이 문서는 두 보고서를 통합하고 영향이 큰 주장 및 관련 현재 소스를 다시 대조한 진입점이다. 이번 통합 단계는 새 solver 실험을 추가하지 않았으며, 수치·화면 증거는 두 상세 감사에서 이번 날짜에 수행한 재현이다. 과거 리뷰의 결론을 현재 결함의 증거로 대신하지 않았다.

## 현재 구현이 잘하는 것과 실제 최적화 문제

- 후보 조합 전체를 MICOM community LP로 평가한다. 단독 균주 점수나 pairwise MIP를 더해 조합 성능을 대신하지 않으므로, 방문한 조합의 3종 이상 대사적 상보성을 반영할 수 있다.
- 외부 탐색은 exhaustive·budgeted GA·random으로 균주 집합을 선택한다. 내부 LP는 대략 `max Σ w_t·(u_t(v_t)−b_t)/s_t`, `Sv=0`, 배지/bounds, `μcommunity ≥ max(f·μ*, absolute_floor)`, 선택적 member-growth floor를 적용한다. `b_t`, `s_t`는 선택한 점수 정책의 기준점과 척도이며 `μ*`는 해당 조합·배지·성장 정책에서 다시 계산된다.
- 분비 방향은 `v≥0`, 흡수 방향은 `v≤0` domain 안에서 max/min을 utility로 변환한다. `min_secretion`은 분비 억제이며 흡수에 의한 해독 목적과 같지 않다. 가능한 최솟값이 0이면 0이 정상 해다.
- 최신 product 경로는 finite/positive abundance 및 요청한 taxa와 실제 MICOM taxa의 불일치를 검사한다. 정확히 k종을 선택해도 k종 모두 양의 성장·안정 공존을 보장하지는 않는다.
- GA genome은 member set이다. 입력 abundance를 선택 집합 안에서 재정규화하며 abundance를 동시에 연속 최적화하지 않는다. normalized GA/random은 고정 reference를 요구하고, exhaustive의 observed-range 점수는 비교 pool에 의존한다.
- 다중 타깃 LP의 목적식과 보고 점수는 같은 affine 척도를 사용한다. Pareto는 공동으로 feasible한 vector의 extremes/slices를 수집하고 top-k와 별도로 archive를 유지한다. 독립적으로 얻은 각 타깃 최댓값을 한 공동 해로 제시하지 않는다.
- SearchService·CLI·GUI의 주 검색은 typed config, 명시적 medium policy, checkpoint identity, 평가 예산, worker 제출 순서를 공유한다. Search 출력에는 staging/lock/rollback이 구현되어 있다. 최근 수정된 구성원 검증·방향 domain·재개·원자적 Search 게시를 미해결 결함으로 재등록하지 않았다.

작은 실제 MICOM 재현에서 4개 모델의 2종 조합 6개는 workers=1/2 결과가 같았고, 평가 3개 뒤 취소·재개는 연속 실행의 순서·점수·history와 일치했다. top-1 사후 검증의 11개 추가 scenario는 탐색 예산과 분리되어 기록되었다. `2a+b≤20` fixture의 Pareto archive에는 `(10,0)`, `(0,20)`을 포함한 7개 vector가 남았으며 불가능한 `(10,20)`은 없었다([과학 감사의 검색 재현·부록 B](scientific_audit_2026-09-25.md)).

이 증거는 GA의 전역 최적성이나 일반적 우월성을 뜻하지 않는다. 12개 pool·3종 선택, oracle 220개·평가 예산 25·5 seeds의 합성 지형에서 additive 최적해 적중은 random 0/5, GA 2/5였지만 hidden-synergy에서는 random 1/5, GA 0/5였다. 이는 GEM 처리량 benchmark가 아닌 oracle 재생 실험이다.

큰 flux는 강한 단독 producer만으로도 나올 수 있다. 별도 synergy/null-model 목적식은 없으며, leave-one-out·monoculture·abundance perturbation은 조건 변화에 대한 민감도다. FVA는 feasible 범위이지 통계적 신뢰구간이 아니고, shared-pool flux 배분도 실제 donor→recipient의 인과적 전달을 입증하지 않는다. 탄소 등가 flux는 수율·titer 또는 생물학적 효능이 아니다.

## 먼저 고칠 확정 결함 — P1

P1은 잘못된 과학적 수치/실행 조건을 정상 결과처럼 전달하거나 선택 출력 경계 밖 파일을 덮어쓰는 문제다. 각 항목의 상세 보고서에는 입력, 실행 명령, 수정 방향, 누락 회귀가 보존되어 있다.

**P1-1 · 미식별 숙주 전달을 0으로 바꿔 KO 효과·검색 점수를 만든다 — SC-01.**
위치: [host_ko_impact.py:155](../cmig/core/host_ko_impact.py#L155), [:109](../cmig/core/host_ko_impact.py#L109), [CLI main.py:2288](../cmig/cli/main.py#L2288). upstream `host_impact`가 point를 생략하고 interval을 남겼는데 소비자가 `.get(target, 0.0)`으로 채운다.
재현: 같은 host objective=5에서 baseline acetate FVA `[0,5]`, butyrate 제거 후 `[5,5]`; 실제 core 변환은 baseline=0, KO=5, delta=+5, `comparable=true`다. 기대는 미식별 point/delta의 null 및 interval 보존이다.
증거: [SC-01·부록 C](scientific_audit_2026-09-25.md), `/tmp/cmig_host_ambiguity_probe_20260925.log`. 실제 LP/FVA와 core 소비 경계를 재현했으며 host-search CLI 전체 실행은 미실행이다. **core와 CLI의 같은 ambiguity 손실을 한 결함으로 묶었다.**
수정·회귀: point/interval/identifiable을 끝까지 보존하고 objective 비교와 target 비교를 분리한다. `[0,5]↔[5,5]`, 양쪽 ambiguous, 실제 `[0,0]`을 KO JSON/CSV와 host-search metric까지 구분해야 한다.

**P1-2 · community dFBA가 내부 sink 공급을 놓치고 해석 가능으로 승인한다 — SC-02.**
위치: [dfba_community.py:431](../cmig/core/dfba_community.py#L431), [:535](../cmig/core/dfba_community.py#L535), [:227](../cmig/core/dfba_community.py#L227). 외부 `community.exchanges`만 닫고 진단한다.
재현: `SK_glc__D_c=(-10,1000)`, tracked glucose=0, biomass=0.1, `dt=t_end=0.1`, `close_untracked_uptake=True`; 실제 biomass는 0.2가 되지만 경고·untracked 공급은 비어 있고 `interpretable=true`다. sink 없는 대조는 stalled다.
증거: [SC-02·부록 A의 `community_hidden_sink`](scientific_audit_2026-09-25.md); 실제 MICOM/pFBA 대조다. 기대는 미선언 공급 폐쇄 또는 추적 불가 진단이다.
수정·회귀: member sink/demand까지 공통 boundary 정책을 적용한다. positive/negative 공급, forced supply, formula-X 예외와 close on/off에서 물질 공급량·acceptance를 확인해야 한다.

**P1-3 · 역방향 exchange에서 dFBA 농도와 host 흡수량의 부호가 틀린다 — SC-03.**
위치: [dfba.py:318](../cmig/core/dfba.py#L318), [:342](../cmig/core/dfba.py#L342), [host_types.py:602](../cmig/core/host_types.py#L602), [host_coupling.py:428](../cmig/core/host_coupling.py#L428).
재현: `--> glc__D_e`처럼 양의 flux가 흡수인 exchange. 실제 dFBA는 biomass 0.1→0.2와 함께 glucose를 **1→1.1**로 늘린다. host는 실제 uptake=5, objective=5인데 secretion/uptake 없음/FVA `[0,0]`으로 읽는다.
증거: [SC-03·부록 A의 `single_dfba_reverse`, `host_reverse`](scientific_audit_2026-09-25.md). 정방향 대조와 실제 optimal solve를 사용했다. 기대는 방향을 바꿔도 물리적 소비·전달량이 같아야 한다는 것이다.
수정·회귀: 반응의 방향과 stoichiometric coefficient로 물리량을 변환하는 adapter를 통일한다. uptake cap·농도 고갈·FVA 양 endpoint·non-unit coefficient의 방향 불변성을 검사한다.

**P1-4 · AGORA catalogue ID로 출력 폴더 밖 파일을 덮어쓸 수 있다 — F1.**
위치: [agora2.py:264](../cmig/io/agora2.py#L264), [:552](../cmig/io/agora2.py#L552), [:556](../cmig/io/agora2.py#L556). ID 검증 없이 `out_dir / f"{entry.id}.xml"`에 기록한다.
재현: `CatalogueEntry(id="../escaped", file="safe.xml", ...)`, VMH/SBML, offline fetcher. 선택한 `out/` 밖 임시 sibling 파일이 기존 내용에서 `<sbml/>`로 실제 바뀌었다.
증거: [F1의 독립 TemporaryDirectory 재현](ui_workflow_audit_2026-09-25.md), [agora_path_probe.json](../.run/audit-20260925/agora_path_probe.json). 기대는 선택한 출력 경계 안에서만 게시하는 것이다.
수정·회귀: ID/file basename 검증과 resolved containment를 모두 적용한다. `../`, 절대 경로, Windows separator, symlink 및 변환 staging에서 외부 바이트가 보존되는 offline 회귀가 필요하다.

**P1-5 · 다중 타깃 그림이 음수 기여도를 지워 JSON과 다른 점수를 보인다 — F2.**
위치: [main.py:7978](../cmig/cli/main.py#L7978)의 `max(0.0, target_score)`.
재현: `glc__D,ac`, 방향 `min_uptake,max_secretion`, `raw_sum`, size=1 exhaustive. 실제 기여 −10과 +13.358851988, 총점 3.358851988인데 그림에는 +13.36만 남는다.
증거: [실제 search_summary.json](../.run/audit-20260925/mixed/search_summary.json), [그림](../.run/audit-20260925/mixed-figure-preview.png), [F2의 CLI 명령](ui_workflow_audit_2026-09-25.md). solver 점수 오류가 아니라 저장 SVG/TIFF와 GUI의 표현 오류다.
수정·회귀: 양/음 누적을 분리한 signed plot과 총점을 표시한다. 실제 mixed-direction 산출물의 contribution 부호·합과 bar geometry가 일치해야 한다.

**P1-6 · Search 탭 설정이 옆 분석 버튼의 실제 실행 조건에 반영되지 않는다 — F3.**
위치: [app.py:1922](../cmig/gui/app.py#L1922), [:1973](../cmig/gui/app.py#L1973), [:2020](../cmig/gui/app.py#L2020), [builder.py:641](../cmig/gui/builder.py#L641).
재현: medium 경로, `min_uptake`, growth fraction=0.75를 선택한 뒤 Gene KO/Strain Growth/Ratio Impact 실행. 세 요청 모두 medium을 누락하고 KO/Ratio는 방향·성장분율도 누락한다. 화면은 적용 범위를 설명하지 않는다.
증거: [ui_functional.json의 `adjacent_workflow_argv`](../.run/audit-20260925/ui_functional.json), [F3](ui_workflow_audit_2026-09-25.md). 실제 GUI/JobRunner의 CLI 인수를 recorder로 검증한 것이며 세 solver 결과의 수치 비교는 아니다.
수정·회귀: workflow별 설정 범위를 명시하거나 typed request를 공유한다. 비기본 조건 전달·실행 조건 표시·실행 중 설정 변경 감지까지 확인해야 한다.

## 그 밖의 확정 결함 — P2

P2는 제한된 경로의 정확성, 진단, 읽기·배포·사용 가능성을 해치는 문제다. 다음은 상세 보고서 ID를 유지한 수정 backlog이며 단순 probe 준비 실수는 포함하지 않았다.

| ID · 위치 | 유발 조건과 기대/실제 | 증거 · 수정/누락 회귀의 핵심 |
| --- | --- | --- |
| SC-04 · [engine.py:286](../cmig/core/engine.py#L286), [medium_spec.py:255](../cmig/core/medium_spec.py#L255) | 동일 `glc__D_e`의 exchange 이름만 바꾸면 member/tidy가 가짜 carbon으로 집계되거나 사라지고 medium도 counterpart를 못 찾음 | 과학 부록 A `exchange_name`, `medium_name`; 실제 metabolite mapping을 권위로 삼고 이름 변경 전후 질량수지 불변성 검사 |
| SC-05 · [search_product.py:1244](../cmig/core/search_product.py#L1244) | Pareto 16시도 중 1 optimal/15 time_limit인데 성공 1행만 남고 timeout 경고 없음 | 과학 부록 B `pareto_partial_timeout`; 후속 status는 mock 주입. infeasible/timeout/error별 attempt ledger와 resume 진단 보존 |
| SC-06 · [search.py:513](../cmig/core/search.py#L513) | legacy `rank_consortia`, abundance `[1,1e-8]`에서 실제 1종 해를 2종 optimal로 순위화 | 과학 부록 B `legacy_rank_filtered`; 새 product와 gate를 공유하거나 deprecated 처리. 최신 SearchService 수정 실패로 오해하지 말 것 |
| SC-07 · [stats.py:307](../cmig/core/stats.py#L307), [:329](../cmig/core/stats.py#L329) | `[1,1,1]` vs `[10,10,10]`의 pooled SD=0인데 Cohen's d=0으로 보고 | 과학 부록 A `constant_distinct_groups`; unavailable/null로 구분하고 JSON·volcano 소비까지 검사 |
| SC-08 · [solver.py:74](../cmig/core/solver.py#L74), [single_model.py:38](../cmig/core/single_model.py#L38) | highspy 설치만으로 HiGHS LP/MILP 사용 가능 표시, 실제 COBRA adapter 없음으로 `SolverNotFound` | 과학 부록 D 및 `/tmp/cmig_solver_probe_20260925.log`; 설치와 interface capability를 분리하고 표시된 solver 최소 solve 검사 |
| F4 · [host_view.py:80](../cmig/gui/host_view.py#L80), [builder.py:790](../cmig/gui/builder.py#L790) | 기본 창 폭 2045, 긴 Pareto 경고 후 2771로 강제 확대되어 목표 화면에 들어가지 않음 | 아래 screenshots/geometry; 숨은 tab 최소 폭·긴 한 줄을 줄이고 전체 main window 회귀 |
| F5 · [app.py:1707](../cmig/gui/app.py#L1707), [:2653](../cmig/gui/app.py#L2653) | 실제 all-baseline-failed rc=3의 manifest·원인·임시 경로를 GUI가 잃고 generic error만 표시 | `ui_additional.json/scientific_failure`; 실패 run도 진단과 artifact 경로로 열 수 있어야 함 |
| F6 · [app.py:1402](../cmig/gui/app.py#L1402), [:1552](../cmig/gui/app.py#L1552) | dFBA artifact 변경을 CLI inspect는 mismatch/failed로 판정하지만 GUI 읽기는 integrity 상태 누락 | `ui_additional.json/dfba_tampered`; 공통 inspector로 valid/mismatch/missing/not_recorded 구분. manifest 없는 spatial tamper는 이 결함 증거가 아님 |
| F7 · [builder.py:738](../cmig/gui/builder.py#L738), [:746](../cmig/gui/builder.py#L746) | multi-target에서 없는 Scatter를 고르면 이전 Ranking 그림이 그대로 남음 | `ui_functional.json/pareto_scatter`; artifact 기반 선택지 및 preview clear 회귀 |
| F8 · [builder.py:789](../cmig/gui/builder.py#L789) | 4개 Pareto 경고 중 첫 항목만 표시, sampled approximation/report-order 설명 접근 불가 | 실제 Pareto summary와 matched PNG; 모든 run warning·단위·실패 수를 펼쳐 볼 수 있어야 함 |
| F9 · [builder.py:574](../cmig/gui/builder.py#L574), [:749](../cmig/gui/builder.py#L749) | 2.33:1 SVG가 7.13:1 preview로 늘어남; 긴 저장 그림 단위도 경계 밖으로 나감 | `final_evidence.log`, 아래 PNG; aspect ratio 유지와 저장 SVG text 경계 검사 |
| F10 · [app.py:1439](../cmig/gui/app.py#L1439) | valid tidy bundle의 manifest를 `{broken`으로 만들면 `JSONDecodeError`가 load 경계를 빠져나옴 | `ui_functional.json/invalid_manifest`; guarded parse/검증 후 UI 게시. 전체 프로세스 종료는 입증하지 않음 |
| F11 · [agora2.py:186](../cmig/io/agora2.py#L186) | raw URL prefix 검사에 `../../../../etc/passwd`가 통과해 허용 publisher path 밖 요청까지 도달 | `agora_path_probe.json`; HTTP 경로이며 로컬 파일 읽기가 아님. 정규화·basename·redirect 계약과 offline 회귀 필요 |
| F12 · [pyproject.toml:83](../pyproject.toml#L83), [editors.py:71](../cmig/gui/editors.py#L71) | 소스 밖 wheel 실행에서 medium preset 없음, sdist README의 로컬 tutorial 링크 단절 | `distribution_probe.json`; package resource 배포 및 clean install 기능/로컬 링크 검사 |

표의 과학 probe 원문은 [과학 감사 부록 A~D](scientific_audit_2026-09-25.md), UI 증거 목록·명령은 [UI 감사](ui_workflow_audit_2026-09-25.md), JSON은 [ui_additional](../.run/audit-20260925/ui_additional.json)·[ui_functional](../.run/audit-20260925/ui_functional.json)·[distribution_probe](../.run/audit-20260925/distribution_probe.json)에 있다. `.run` 산출물은 ignored 로컬 증거이므로 공유 시 별도 보존이 필요하다.

## 미구현·문서화된 한계·개선 과제

아래 항목은 현재 계획과 제공 범위를 구분한 것이다. 미제공 기능 자체를 위의 확정 수치 결함과 같은 것으로 세지 않는다.

| 영역 | 현재 범위와 필요한 다음 단계 |
| --- | --- |
| 타깃별 편집 | library/CLI는 방향·weight를 제공하지만 GUI는 공통 direction 하나뿐이다. GUI per-target 행 편집이 필요하다. 사용자 per-target threshold는 `MultiTargetConfig`·CLI·UI 모두 미구현이며 내부 epsilon slice를 이 기능으로 간주할 수 없다. |
| Pareto UX | archive는 계산하지만 GUI는 stacked bar와 frontier 수 중심이다. 2D trade-off plot·vector별 조건/진단 inspector는 확장 범위다. 기존 Scatter의 stale preview는 별도 F7 결함이다. |
| 탐색 정책 | abundance 동시 최적화, 명시적 synergy/null-model fitness, 제조비용·size penalty, 주 검색과 host viability의 결합 최적화는 제공되지 않는다. size 범위 제약은 비용 penalty가 아니다. |
| prescreen/알고리즘 | 자동 MIP/MRO prescreen·greedy/Bayesian 주 탐색은 미구현이다. 수동 singleton prescreen은 상보적 donor를 놓칠 수 있다는 한계가 문서화되어 있다. helper/enum 존재만으로 기능을 제공한다고 판단하지 않는다. |
| UI/CLI 동등성 | GUI는 taxonomy·recursive pool·일부 preset/sample-N·GA 세부 연산/예산·solver thread·Pareto resolution을 충분히 노출하지 않는다. GUI 기본 metric/top-k는 CLI와 다르며 비교 시 실행 조건 확인이 필요하다. |
| 파일·재개 | model folder browse는 있으나 medium/checkpoint는 수동 경로 중심이고 출력은 임시 디렉터리다. 일반 Open Run은 Search viewer를 제공하지 않는다. 저장 project·출력 위치·경로 복사·기존 search readback의 일관된 흐름이 필요하다. |
| 취소·상태 | 취소는 후보/배치 경계 협조 취소이며 실행 중 solver 즉시 중단을 뜻하지 않는다. 전용 Search Cancel은 toolbar와 달리 pending 취소 상태 표시가 늦는 P3 일관성 문제가 있다. |
| 한국어·표·모델 안내 | 일부 shell/editor만 번역되어 Search/Host/Dynamics에는 영어가 남는다. 길고 잘린 ID, 제한된 필터·진단 접근, model-quality 경고 미노출과 일반 objective의 `Biomass` 라벨은 개선 대상이다. |
| scientific scope | spatial은 diffusion preview이며 full spatial dFBA가 아니다. host coupling/FVA와 사후 민감도는 실험적 효능·인과적 synergy·장기 공존을 입증하지 않는다. |

문서 계약도 정리해야 한다. [USER_GUIDE](../docs/USER_GUIDE.md)는 community-dFBA CLI 사용법과 후반부의 “CLI 미제공” 범위 설명이 충돌하고, [USAGE](../docs/USAGE.md)의 GUI/CLI 상호 재열기 동등성 설명은 Search viewer가 없는 현재 GUI에 그대로 적용할 수 없다. [명세 §14](../CMIG_명세서_v3.0.md)의 확장 요구를 현재 기능 목록과 분리해야 한다.

원자성·provenance 보장은 workflow별로 다르다. Search directory transaction은 이미 구현되었지만 [render/publication.py:53](../cmig/render/publication.py#L53)의 figure/spec/provenance는 파일별 교체이며 전체 set transaction으로 입증되지 않았다. legacy solve/spatial에는 모든 artifact digest가 기록된다는 일반 설명을 적용할 수 없다. 이는 보장 범위/문서 문제이며 이번에 render 중단으로 실제 손상을 재현했다는 뜻은 아니다.

## 실제 시각 검증

PySide6를 Qt offscreen으로 실제 렌더하고 아래 주요 PNG를 이미지 도구로 확인했다. 단순 widget 생성/기능 테스트를 시각 QA로 대체하지 않았다. 사용자 desktop은 조작하지 않았다.

| 화면·요청 크기 | 실제 관찰과 screenshot |
| --- | --- |
| Search 1500×950 | 실제 **2045×950**. [빈 Search](../.run/audit-20260925/en-search-empty-1500x950.png) |
| Search 1280×800 / 자연 최소 | 실제 **2045×823**. [1280 요청](../.run/audit-20260925/en-search-empty-1280x800.png), [1×1 요청으로 측정한 실제 최소](../.run/audit-20260925/en-search-empty-1x1.png) |
| 한국어 1280×800 | 실제 **2045×820**, 한글 glyph는 보이나 번역 범위는 부분적. [한국어 Search](../.run/audit-20260925/ko-search-empty-1280x800.png) |
| Pareto 1500×950 / 1280×800 | 실제 **2771×950 / 2771×823**. 입력과 실제 run을 맞춘 [1500 요청](../.run/audit-20260925/pareto-matched-request1500x950-actual2771x950.png), [1280 요청](../.run/audit-20260925/pareto-matched-request1280x800-actual2771x823.png) |
| 점수·실패 설명 | [음수 기여도 손실](../.run/audit-20260925/mixed-figure-preview.png), [실패 run GUI](../.run/audit-20260925/en-failed-search.png) |

치수는 [ui_geometry.json](../.run/audit-20260925/ui_geometry.json)과 기능 probe에 보존했다. Host·Dynamics·Medium·Sweep·실제 profile 화면도 상세 UI 보고서에 연결했다. 강제로 고정 크기를 준 보조 캡처와 초기 probe의 form/summary 주입 불일치는 제품 결함 증거로 사용하지 않았다. WebEngine graph의 offscreen GPU/초기 viewport 관찰은 native 재현 전까지 환경 제약으로 남긴다.

## 검증 결과·범위·미검증 영역

- 코디네이터 전체 baseline: **1,537 passed / 1 failed / 18 skipped, 1,556 collected**. [보존 pytest 로그](../.run/audit-20260925/baseline-pytest.log). 이 통합 작업에서 전체 pytest를 중복 실행하지 않았다.
- 실패: `tests/test_agora2.py::test_fetch_model_refuses_a_url_outside_the_publisher`. URL을 먼저 거부하지 않고 publisher 응답을 SBML로 읽다가 예상과 다른 오류가 발생한다. baseline의 상위 경로 3회 입력 자체는 정규화 후 AGORA2 prefix 안에 남으므로 그것만으로 prefix 이탈을 주장하지 않는다. F11은 **4회 입력의 별도 offline interception**으로 이탈을 확인했다. 단순 외부 서버 불안정으로만 분류할 수 없다.
- 상세 감사 추가 테스트: 과학 정책 선택 **9 passed**, Search/cancel/rollback 관련 UI·service 선택 **7 passed**. 각 보고서의 `-k`가 선택한 검사만 센 값이며 해당 파일 전체 통과를 뜻하지 않는다.
- Ruff, strict mypy, version/envelope, lock, build/distribution gate는 코디네이터 결과에서 통과했다. golden 검사는 version/hash 확인이며 모든 golden fixture의 새로운 solver 수치 재계산을 뜻하지 않는다. F12처럼 파일 allowlist 통과만으로 설치 UX가 검증되지는 않는다.
- 환경: macOS 15.6 arm64, Python 3.12.11, COBRA 0.31.1, MICOM 0.39.0, Gurobi 12.0.3, OSQP 1.1.1. HiGHS도 설치되었으며 SC-08은 패키지 부재가 아닌 adapter/capability 불일치다.

| 모듈/흐름 | 검토·동적 증거와 범위 참조 |
| --- | --- |
| search/product/GA/execution/validation/FVA | 현재 소스·정책 pytest·작은 실제 MICOM·worker/resume·oracle benchmark. [과학 감사의 모듈별 범위 표](scientific_audit_2026-09-25.md) |
| engine/pool/solver/boundary/medium/namespace | 소스와 모델 이름·방향·hidden supply·adapter 대조. import 전 형식 동작은 기존 baseline에 의존 |
| dFBA/community/spatial/host/map | 실제 작은 동역학·host LP/FVA 및 정적 interface 검토. 대형 host-map의 생화학 identity 정답 검증은 아님 |
| interactions/pair/matrix/stats/delta/sandbox/sweep | 주요 단위·보존·상태·rollback 계약 검토, tidy/zero-variance probe. 모든 조합을 동적 재실행하지 않음 |
| GUI/service/CLI/io/render/export | 실제 검색·readback·Qt 요청/취소·화면·AGORA offline·wheel probe. [UI 감사의 범위 표와 증거 목록](ui_workflow_audit_2026-09-25.md) |
| manifest/store/golden/docs/package/CI | 현재 계약·정적 경로·tamper 읽기·배포물 검사 및 코디네이터 baseline. 모든 publication/CI 분기 실증은 아님 |

명시적 미검증: 대규모 실제 AGORA2/Recon/HumanGEM 탐색·coupling, 장시간 dt-convergence·메모리·강제 process kill·실제 solver timeout, 고차원 Pareto 품질/처리량, R 전용 그림, native macOS/Windows·HiDPI·접근성·키보드·다중 모니터. 18 skipped를 통과로 세지 않았으며 독립 생물학적 cohort나 실험 효능은 검증하지 않았다.

배포 검증 공백: 기존 CI의 GUI suite는 Gurobi secret이 필요한 Ubuntu job에 편중되어 외부 fork에서 건너뛰며 OS matrix 녹색이 native GUI 검증을 뜻하지 않는다. source 밖 wheel 기능·preset·sdist 링크, USER_GUIDE 명령과 release tag 검증을 별도로 연결할 필요가 있다([UI 감사의 CI/문서 절](ui_workflow_audit_2026-09-25.md)).

## Sol 구현 순서와 실행 가능한 인수 기준

각 단계는 실패를 드러내는 회귀부터 추가하고 Astra가 수치·표현 계약을 검토한다. 아래 명령은 관련 기존 suite의 시작점이며 새 회귀 추가 없이 이 문제들이 검증된 것으로 인정하지 않는다. 전체 baseline 재실행은 변경 통합 시 코디네이터와 한 번 조율한다.

1. **출력 경계와 과학 정보 손실부터 차단:** F1/F11, SC-01~03을 우선 수정한다. AGORA offline 경로 탈출 거부, ambiguous point null 유지, 방향 불변 농도·host 전달, hidden sink 공급 폐쇄/진단을 정확한 수치 assertion으로 고정한다.

   `uv run --no-sync pytest tests/test_agora2.py tests/test_host_ko_impact.py tests/test_host_medium_strictness.py tests/test_round8_community_dfba.py tests/test_boundary_isolation_dynamics.py -q`

2. **같은 입력·물리량을 모든 계층에 보존:** SC-04~08과 F3을 수정한다. exchange 이름 변경 전후 identity/질량수지, legacy/product membership gate, partial Pareto attempt ledger, undefined effect, solver adapter, 비기본 GUI 요청을 회귀화한다.

   `uv run --no-sync pytest tests/test_search_policy_v2.py tests/test_search_execution.py tests/test_search_service.py tests/test_engine_golden.py tests/test_stats.py tests/test_single_model.py tests/test_solver_and_cli.py -q`

3. **결과·실패·읽기를 신뢰 가능하게 표시:** F2/F5~10. signed contribution 총합=보고 점수, failed run의 출력 경로·진단 접근, digest 상태, 손상 manifest의 처리, 전체 경고 접근, 없는 그림의 clear를 확인한다. Search transaction의 rollback은 유지한다.

   `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_run_transaction.py tests/test_app_shell.py tests/test_gui_editors_builder.py tests/test_gui_render.py -q`

4. **실제 화면과 설치 제품을 인수:** F4/F9/F12. main window 전체를 1500×950·1280×800·실제 최소 크기와 한국어/긴 경로/Pareto 경고로 렌더하고 새 PNG를 육안 비교한다. source 밖 clean wheel에서 medium preset이 열리고 sdist 로컬 링크가 해소되어야 한다.

   `uv run --no-sync pytest tests/test_distribution_audit.py tests/test_docs_commands.py -q` 이후, 새 wheel smoke·USER_GUIDE 계약·GUI 무라이선스 CI 회귀를 추가한다. 위 테스트만으로 시각·설치 인수를 대신하지 않는다.

5. **그 다음 사용자 기능 확장:** per-target direction/weight/threshold의 공통 schema와 실행 예시를 먼저 합의된 설계로 만들고 CLI/library/GUI에 동일하게 연결한다. Pareto 2D·vector inspector, Search readback·출력 경로, 고급 GA 설정, 한국어·표 탐색을 순서대로 보완한다. abundance/synergy/host-coupled 목적은 별도 과학 설계와 비교 benchmark가 필요한 확장이다.

[하네스 사용 문서](../docs/HARNESS.md)와 [Astra 하네스 설계](harness_design_2026-09-25.md)는 별도 작업으로 존재한다. 이 제품 감사는 하네스 구현·복구·모델 routing을 최종 인수한 보고서가 아니며, 진행 중인 하네스 변경을 위 baseline 검증에 포함시키지 않는다.
