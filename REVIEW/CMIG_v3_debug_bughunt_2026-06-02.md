# CMIG v3.0 — 전체 코드베이스 디버깅 버그 수색 (검증 통과본)

- 작성일: 2026-06-02
- 기준 명세(권위): `CMIG_명세서_v3.0.md`
- 직전 리뷰: `REVIEW/CMIG_v3_codereview_gaps_2026-06-01.md` (F-1~F-11 + Extension 버그)
- 방법: 전체 `cmig/` 패키지를 **10개 모듈 클러스터 + 4개 횡단 차원**(수치 정확성·동시성/자원·에러처리·결정성)으로 14개 finder 병렬 수색 → 각 발견을 **적대적 검증자**가 인용 `file:line`을 직접 읽어 반증 시도(기본값 "refuted", 코드로 확인될 때만 "real") → 검증 통과분만 수록.
- 목적: 직전 리뷰가 *명세 갭·계약·정직성*에 집중한 것과 달리, 본 문서는 **테스트로는 드러나지 않는 실제 결함**(수치/과학적 정확성, 상태 변형, 동시성/자원, 엣지케이스, 재현성)에 집중한다.

## 0. 그라운드 트루스 (직접 확인, 2026-06-02)

| 게이트 | 결과 |
|---|---|
| `uv run pytest` | **green (exit 0)** (실 MICOM·OSQP·dFBA·host·stats·R·GUI offscreen 포함) |
| `uv run ruff check .` | All checks passed |
| `uv run mypy cmig` | Success: no issues found in 55 source files (strict) |
| 코드 규모 | `cmig/` 약 7,773 LOC / 52 모듈, 48 테스트 파일 |

**모든 정적/동적 게이트가 통과한다.** 따라서 아래 발견은 전부 "녹색 테스트를 통과한 채 살아있는" 결함이다 — 입력이 비정상/경계이거나, 과학적으로만 틀리거나, 검사 경로가 없는 부류.

## 1. 요약

- **검증 통과(real): 31 raw → 28 distinct** (중복 병합: engine inf-growth ×2, GA 결정성 ×2, sandbox apply/restore, `_load_bounds_json` 2건).
- 적대적 검증에서 **기각(false positive): 5건** (§5).
- uncertain: 1건 (§4).

| 심각도 | 건수(distinct) | 신규 | 기존 리뷰 연관 |
|---|---|---|---|
| 🔴 High | 2 | 1 (D-1) | 1 (D-2 = F-1) |
| 🟠 Med | 13 | 11 | 2 (D-11 host mutation, D-12 dfba) |
| 🟡 Low | 12 | 8 | 4 (D-18, D-25 F-10, D-27 F-11, + D-17 F-8 인접) |
| ⚪ Uncertain | 1 | 1 | — |

> **검증자가 심각도를 하향 조정한 항목 다수**: 원래 High로 제기됐으나 (a) 현재 프로덕션 배선이 트리거하지 않음(latent), (b) 영향 반경이 주장보다 좁음, (c) 트리거가 solver 런타임 의존이라 정적으로 보장 안 됨 — 이런 경우 Med/Low로 내렸다. 각 항목에 근거 명시.

---

## 2. 🔴 High

### D-1. `model_checksum`가 실제 GEM 모델 파일이 아니라 taxonomy CSV를 해싱 — 재현성/캐시 정합성 위반 (신규)
- 위치: `cmig/cli/main.py:105` (`_cmd_solve`), `:854` (`_cmd_sweep`)
- 증상: `model_checksum=file_checksum(tax_path)` — taxonomy CSV(`{id, file}` 두 컬럼만 보유)의 SHA-256을 계산한다. 실제 GEM 내용은 이후 `micom.Community(taxonomy)`가 `file` 컬럼의 경로에서 로드한다(`core/engine.py:115`). 즉 run_hash 구성요소 #1(모델 내용 바인딩)이 **모델 바이트가 아니라 CSV 텍스트에만** 묶인다.
- 영향: 참조된 GEM 파일을 **같은 경로에서 내용만 교체/편집**하면 CSV는 바이트 동일 → 동일 `model_checksum` → 동일 `run_hash`. `run_hash`는 캐시 키(`service/store.py:79` `cache_lookup_by_run_hash`)이자 [HASH-SINGLE] 재현성 기준이므로, 과학적으로 다른 solve가 **stale 캐시 hit / 거짓 집계 동일성**으로 처리된다. 명세 §2(line 68: `MemberModel.source.checksum`)·`docs/01-plan/schema.md:222`(구성요소 #1 = 멤버 모델 파일 체크섬의 집합)와 정면 충돌. 기존 F-2(구성요소 #5 `bounds={}`)와는 별개 축(구성요소 #1).
- 트리거 조건: 새 경로로 모델을 추가하면 CSV도 바뀌어 가려지지만, **in-place 편집/교체**에서는 조용히 stale 결과. 조건부지만 silent + 명세 위반이라 High.
- 수정안: `model_checksum`을 taxonomy `file` 컬럼이 가리키는 모델 파일들의 바이트에 대한 결정적 해시(정렬된 `(member_id, file_checksum(path))` 쌍의 sha256)로 계산. CLI 양쪽(`:105`, `:854`) I/O 경계에서 처리.

### D-2. OSQP flux를 `full`로 오기재 — 명세가 폐기한 `osqp_growth_highs_flux` hybrid를 그대로 구현 (기존 F-1, 신규 증거)
- 위치: `cmig/core/engine.py:171-177`
- 증상: `cmig_solver=="osqp"`일 때 `growth_solver, flux_solver, flux_report = "osqp", "highs", "full"`. 명세 §4.2(line 11·59·163·189)는 "OSQP는 LP flux 재계산 부재로 **qp_only_approximate**로만 보고, `osqp_growth_highs_flux` hybrid는 폐기, full-flux로 표기 금지"를 반복 명시. 코드는 정확히 그 폐기된 hybrid(growth=osqp QP + flux=highs LP)를 수행하고 `full`로 찍는다. 올바른 라벨 `qp_only_approximate`는 타입(`engine.py:24`)에 존재하나 미사용.
- 영향(F-1 대비 신규 증거): ① **provenance 오염** — `io/solve_output.py:55`가 run_hash 구성요소 #7 `solver_setting={growth_solver:osqp, flux_solver:highs}`로 폐기 hybrid를 기록. ② **golden 오염** — osqp golden fixture가 `full`로 캡처/비교되어 갖지 못한 full-flux 충실도를 주장. 모든 OSQP run(2개 solver 중 하나)의 과학적 full-flux provenance가 거짓이며, 하위 sign/cross-feeding/profile 테이블이 QP-only flux를 정확한 pFBA로 신뢰.
- 수정안: osqp 분기를 `growth_solver, flux_solver, flux_report = "osqp", None, "qp_only_approximate"`로 (growth QP는 진짜이므로 osqp 유지). docstring `engine.py:12,29`도 갱신.

---

## 3. 🟠 Med

### D-3. `analyze_pair`가 solve status를 버려 infeasible 결과를 확신에 찬 상호작용(neutralism 등)으로 오분류 (신규)
- 위치: `cmig/core/pair.py:60-68`
- 증상: co/mono 성장률의 status·diagnostic을 전혀 읽지 않는다. `co.member_growth.get(m,0.0) or 0.0`에서 `NaN or 0.0 == NaN`(NaN은 truthy), infeasible 단일배양은 `solve_single_model(...).objective`로 비유한/garbage 값. 이 값이 `interaction_type`로 흘러가 `_sign(NaN)==0`(`NaN>eps`·`NaN<-eps` 모두 False) → co-culture 전체 infeasible이면 **neutralism**, 한쪽 mono infeasible이면 **amensalism** 등으로 분류. `PairResult`에 status/diagnostic 필드 없음.
- 영향: infeasible pair(나쁜 medium·gate mismatch·exchange 누락)가 진단 없이 "진짜 생물학적 무상호작용"처럼 보고됨. `delta.py`의 TC-6("infeasible을 변화없음으로 위장 금지")가 막는 안티패턴을 `pair.py`만 방어하지 않음. (헤드라인 "항상 neutralism"은 과장 — 어느 solve가 실패하느냐에 따라 라벨이 달라짐.) feasible 행복경로만 테스트되어 녹색.
- 수정안: 각 solve의 `status=="optimal"`/`math.isfinite` 가드, `PairResult`에 status/diagnostic 추가, 실패 시 `interaction_type` 대신 실패 전파(`delta._solve_diag` 미러링).

### D-4. community solve가 비유한(inf) 성장률을 `status=optimal`로 보고 — `unbounded`는 죽은 코드 (신규, engine inf-growth ×2 병합)
- 위치: `cmig/core/engine.py:180-184`
- 증상: `objective=float(sol.growth_rate)` 후 가드가 `if math.isnan(objective)`만 검사. `±inf`(경계 오설정·uptake 무한 개방 등 실제 FBA 결과)는 `isnan`을 통과해 `status="optimal"`, `objective=inf`로 반환. line 179 주석은 "비유한(infeasible) 가드"라 하지만 NaN만 처리. `SolveResult.status` Literal의 `"unbounded"`(`:63,181`)는 프로덕션 어디서도 할당되지 않는 죽은 코드. 형제 소비자 `delta.py:61`은 `if not math.isfinite(...)`로 방어하는데 생산자 engine은 비방어 — 비대칭.
- 영향: 무경계/수치적 퇴화 solve가 진단 없이 정상 optimal로 기록. `golden_fixture.py:102`가 `growth_expected.tsv`에 리터럴 `"inf"`를, `sweep.py:207`이 잘못된 `optimal` status를 전파. (검증 정정: `objective`는 `manifest.json`/run_hash 11구성요소에 포함되지 않으므로 hash는 오염 안 됨 — 영향 반경이 주장보다 좁아 High→Med.)
- 트리거: `cooperative_tradeoff`는 보통 유계라 misconfigured 모델 필요 + MICOM이 inf를 반환할지 raise/NaN할지는 solver 의존(정적 미보장).
- 수정안: `if not math.isfinite(objective): status = "unbounded" if math.isinf(objective) else "infeasible"` + 대응 `DiagnosticCode` 추가(이미 선언된 `unbounded` Literal 배선).

### D-5. `tables_close`가 골든 허용오차 비교에서 NaN/inf 불일치를 조용히 통과 (신규)
- 위치: `cmig/core/golden.py:96-105`
- 증상: line 102 `if abs(av - ev) > atol + rtol*abs(ev): raise`. IEEE-754상 `NaN > x`는 항상 False이므로 actual이 NaN이고 expected가 유한이면 불일치를 못 잡고 행을 통과시킨다. `inf-vs-inf`도 `abs(inf-inf)=NaN`으로 마스킹. None 가드(98-101)는 NaN(float)을 못 잡음. (정정: 일반 `inf-vs-유한`은 `inf>thresh=True`로 잡힘 — NaN-actual-vs-유한, inf-vs-inf만 마스킹.)
- 영향: OSQP/반복 solver 경로에서 flux가 NaN으로 퇴화하는 회귀(심각한 수치 실패)가 골든 검증을 조용히 통과. `tests/test_engine_golden.py:55,61`(SC-6 OSQP 허용오차 게이트)의 안전망 약화. (테스트 전용 함수라 사용자 산출 직접 오염은 아님 → Med.) gurobi 경로는 hash-exact + `_round`가 NaN→"NaN"이라 잡힘. 기존 `golden.py:21`(D-18) hash 경로와는 별개.
- 수정안: line 102 앞에서 `if math.isnan(av) or math.isnan(ev): raise`(infs는 정확 일치 요구) — 비유한이 `>` 비교에 도달하지 못하게.

### D-6. `apply_bounds`/`restore_bounds`의 lower-우선 순차 대입 — 유효한 입력에서 ValueError + 롤백 없는 부분 변형 (신규, apply+restore 병합)
- 위치: `cmig/core/sandbox.py:146` (`apply_bounds`), `:155` (`restore_bounds`)
- 증상: `rxn.lower_bound, rxn.upper_bound = b.lower, b.upper`는 lower를 먼저 대입. cobra의 `lower_bound` setter는 **현재(낡은) upper**와 비교하므로, 요청 쌍 `(8,20)` 자체는 유효해도 현재 bounds가 `(-10,5)`면 `ValueError: lower must be <= upper (8 <= 5)`. 원자적 `rxn.bounds=(8,20)`이면 성공. `apply_bounds`는 예외 시 `original` undo dict를 반환 못 해 루프 앞부분에서 이미 변형된 reaction이 복구 불능. `restore_bounds`도 대칭으로, 미리보기가 창을 아래로 좁혔다가 취소할 때 raise되어 모델이 제약 상태에 고착.
- 영향: reaction flux 창을 위로 이동시키는 유효한 sandbox 편집이 오해 소지 있는 에러로 루프 중간 크래시 + caller community에 부분 변형 잔존. cancel/undo(§10/A11, SC-8 preview 비오염)가 실패. (정정: 프로덕션 solve 경로는 community를 호출마다 새로 빌드하고 예외 시 폐기하므로 "장기 community 오염"은 완화 → High→Med. 실현 피해는 유효 입력 크래시 + undo 계약 위반.)
- 수정안: 양쪽을 원자적 `rxn.bounds = (b.lower, b.upper)` / `rxn.bounds = (lo, hi)`로. 추가로 루프를 예외 시 부분 변형 되돌리도록 감싸기.

### D-7. GA `best_members`/`top_k`가 프로세스 간 비결정적(PYTHONHASHSEED 의존) — 명시된 seed 재현성 계약 위반 (신규, search_ga ×2 병합)
- 위치: `cmig/core/search_ga.py:118-122`
- 증상: `final = sorted(set(pop) | set(cache), key=fit, reverse=True)`. `set(...)`의 원소는 `tuple[str,...]`(Genome)이라 반복 순서가 PYTHONHASHSEED에 따라 무작위. `sorted`는 안정 정렬이므로 **fitness 동점** 게놈들의 상대 순서가 set 비결정 순서를 물려받음 → `best=final[0]`, `top_k=final[:k]`가 프로세스마다 달라짐. 동점은 흔함(`search.py:108`이 비최적 solve에 `float("-inf")` 반환, 동일 size/flux 다수). 모듈 docstring(line 6-7,72)·`test_search_ga.py:34` SC-GA3가 "동일 seed → 동일 결과"를 약속.
- 영향: 실증 — 동일 `seed=7`로 PYTHONHASHSEED=1/2/3/42에서 `best_members`가 매번 다름(전부 `best_fitness=4.0`). `cli/main.py:417-439`가 `ga.best_members`/`ga.top_k`를 `search_advanced_summary.json`에 직접 기록 → 동일 명령 재실행 시 다른 "최적 consortium" 보고. PYTHONHASHSEED 미고정(pyproject/conftest)이라 단일 프로세스 테스트가 못 잡음. (`best_fitness` 수치는 항상 정확 → Med.)
- 수정안: line 118에 결정적 2차 키, 예: `sorted(set(pop)|set(cache), key=lambda g: (-fit(g), g))` (또는 `key=lambda g:(fit(g), g), reverse=True`).

### D-8. `make_sweep_job`이 취소된 sweep을 잘린 부분결과와 함께 `DONE`으로 보고 (신규)
- 위치: `cmig/service/jobrunner.py:181-185`
- 증상: `_job`이 `run_sweep(..., should_cancel=lambda: ctx.cancelled)`를 무조건 반환. `run_sweep`은 협조적 취소 시 condition 경계에서 `break`하고 누적 행을 정상 반환(`core/sweep.py:142-144`) — 예외를 던지지 않음. 어댑터는 호출 후 `ctx.cancelled` 재확인도, `JobCancelled` raise도 안 해 `_run()`이 성공 경로로 떨어져 status=**DONE**(`:135-138`). 형제 `gui/app.py:321-326`은 `ctx.raise_if_cancelled()`로 올바르게 처리.
- 영향: 긴 sweep을 취소한 사용자가 status상 완전 완료와 구별 불가능한 DONE job(조용히 잘린 condition 부분집합)을 받음. 하위 `sweep.parquet`/matrix 소비자가 부분 출력을 완전한 것으로 처리. (정정: live 트리거는 JobRunner+`cancel()` 경로(SweepView)뿐 — CLI sweep은 `should_cancel` 미전달이라 트리거 안 됨, GUI 미조립(F-3) → Med. F-11과 별개.)
- 수정안: `_job`에서 `run_sweep` 결과 캡처 후 `if ctx.cancelled: raise JobCancelled()` (`run_fixture` 미러링).

### D-9. `solve_host`가 maintenance reaction 부재 시 ATP-maintenance 제약을 조용히 생략 → 거짓 viable=True (신규)
- 위치: `cmig/core/host.py:244-251`
- 증상: maintenance 제약이 `if maintenance_reaction in ex_ids:`(line 245) 안에서만 적용. 호스트 모델에 `"ATPM"`(기본값)이라는 reaction이 없으면 블록 전체가 **경고/진단 없이** 생략되고, `viable = status=="optimal"`(line 251)이 순수 LP feasibility로만 결정. `HostSolveResult(True,...)` 반환에 "maintenance가 강제됐는지"를 구별하는 필드 없음. docstring(line 51,223) 계약 "viable = ATP maintenance 충족 + feasible" 및 명세 §12(line 120-121) 위반.
- 영향: maintenance reaction id가 `ATPM`이 아닌 비-toy 호스트(`ATPM_c`, `NGAM` 등)는 maintenance 미강제로 viable=True 거짓 보고. (정정: 현재 실 GEM은 별도 `solve_generic_host` 경로로 라우팅, CLI는 reaction 이름 override 미노출 → latent, High→Med. toy fixture가 `ATPM` 정의(`synthetic_host.py:57`)라 테스트 가려짐.)
- 수정안: line 245에 `else` 분기 — 진단(`DiagnosticCode.HOST_MAINTENANCE_ABSENT` 신설) 발행 + `viable=False` 또는 최소한 결과에 diagnostic 첨부.

### D-10. `solve_host`가 maintenance lower bound를 덮어써 모델의 더 엄격한 maintenance를 완화 가능 (신규)
- 위치: `cmig/core/host.py:247`
- 증상: `mr.bounds = (maintenance_flux, max(mr.upper_bound, maintenance_flux))` — lower를 호출자 `maintenance_flux`(기본 1.0)로 하드 대입, 기존 `lower_bound` 무시. `max(...)` 보호가 upper에만 적용되고 lower엔 누락. 모델이 더 높은 NGAM(예 ATPM bounds `(5.0,1000)`)을 인코딩해도 기본 `maintenance_flux=1.0`이면 `(1.0,1000)`이 되어 생물학적 maintenance 5.0이 폐기.
- 영향: 낮은 기질에서 실제 NGAM을 못 채워 non-viable이어야 할 호스트가 maintenance 완화로 viable 보고. 명세 §12의 "lower-bound constraint"(조여야 함)를 푸는 셈. toy fixture가 `HOST_MAINTENANCE=1.0==기본값`이라 가려짐. (D-9의 lifetime 이슈와 별개 — line 247은 `with host:` 안이라 변형은 롤백됨; 여기 결함은 잘못 대입된 *값*.)
- 수정안: lower를 `max(mr.lower_bound, maintenance_flux)`로 — 제약이 완화가 아니라 강화되도록.

### D-11. `solve_generic_host`/`benchmark_generic_host`가 caller의 `model.solver`를 영구 변형 (기존 host mutation, 별개 함수)
- 위치: `cmig/core/host.py:157`
- 증상: `set_model_solver(host, solver)`(`single_model.py:60`에서 `model.solver = solver`)를 `with host:` 컨텍스트 없이 호출. cobra는 `with model:` 블록 안에서만 solver 대입을 되돌리므로(@resettable), 컨텍스트 밖 변형은 영구. `solve_host`(line 230)는 올바르게 `with`로 감쌌지만 generic 경로는 누락. osqp일 땐 `lp_method` config도 같이 변형(`single_model.py:57`).
- 영향: 사용자 Recon3D/Human-GEM 모델을 benchmark한 뒤 같은 객체로 후속 solve 시 사용자가 설정한 것과 다른 solver/config를 조용히 사용 → 수치/재현성 변화. `benchmark_generic_host`는 "비침습 inspection"으로 문서화됐는데 caller 모델을 다른 solver로 바꿔놓음. `test_host.py:121`은 solver 보존 미검사라 녹색. (호출 자체의 반환값은 정확 + 많은 caller가 fresh 모델 로드 → Med.)
- 수정안: `with host:`로 감싸기(`solve_host` 미러링) 또는 `try/finally`로 `host.solver` snapshot·복원.

### D-12. dFBA emergency clamp가 소비량이 가용 기질을 초과하게 허용 — 질량보존 위반 (기존 dfba)
- 위치: `cmig/core/dfba.py:113-121`
- 증상: 적응적 halving이 `min_dt`에 도달해도 농도가 음수가 될 때 `else` 분기가 `new_conc=max(...,0.0)`로 clamp하면서 `biomass += mu*biomass*min_dt`로 **전체 성장률 mu**를 그대로 credit. MM 캡은 uptake *rate*만 제한(line 94)하지 유한 step의 적분 소비를 `≤가용`으로 제한 못 함. 음수 overshoot(가용 초과 소비)는 clamp로 버려지고 그 기질로 만든 성장은 유지 → 유령 기질로 성장. 명세 §13(line 134) "non-negativity(소비≤가용·S clip)·질량보존" 위반.
- 영향: 고갈 근처에서 biomass가 overshoot, 최종 biomass·고갈 궤적 왜곡. (정정: 위반은 고갈 단일 step에 국한, 크기 `≤mu*biomass*min_dt`(min_dt 기본 1e-4), 다음 step은 s=0→uptake=0으로 자기제한 → Med 하단. `test_dfba.py`는 비음성·bound 복원만 검사, 기질-성장 균형 미검사.)
- 수정안: else 분기에서 제한 분율 `f=min(conc[ex]/(|flux|*biomass*min_dt))`를 `[0,1]`로 clamp 후 농도 업데이트와 biomass 증분 **양쪽**을 `f`로 스케일.

### D-13. `Diagnostic.from_exception`이 메시지 부분문자열로 INFEASIBLE 분류 — 래핑된 IO/프로그래밍 에러 오분류 (신규)
- 위치: `cmig/core/diagnostics.py:42-50`
- 증상: `code = INFEASIBLE if "infeasible" in str(exc).lower() else SOLVER_ERROR` — 예외 타입 무시, 자유 텍스트 부분문자열만. 이게 sweep 실패 경로(`sweep.py:157`)·JobRunner(`jobrunner.py:133`)의 유일한 예외→코드 분류기. 결정적 실패모드 (a): `fva.py:85-130`·`medium.py:124`이 **어떤** 근본원인이든 `FVAInfeasibleError(f"FVA infeasible (...): {e}")`로 래핑 — 'infeasible' 토큰이 메시지에 하드코딩되므로 AttributeError 등 IO/프로그래밍 에러가 INFEASIBLE로 코딩됨.
- 영향: sweep 실패원인 통계·batch 요약·GUI 진단 필터가 code별 mis-bucket: 실제 solver-infeasible이 SOLVER_ERROR로, 'infeasible' 포함 무관 에러가 INFEASIBLE로. 수치 결과는 안 바뀌나 모듈이 약속한 기계가독 진단 계약(docstring·§4.4/G4) 위반. (수치 무영향 → Med.)
- 수정안: 예외 타입 우선 분기 — `FVAInfeasibleError`/`MILPInfeasibleError`→INFEASIBLE, capability 부재→별도 코드, true solver infeasibility는 cobra/optlang 예외 클래스/status enum으로 판정, 그 외 SOLVER_ERROR.

### D-14. infeasible search consortium(score=null/-inf)이 GUI에 Score 0.0으로 표시 (신규)
- 위치: `cmig/gui/builder.py:240-260, 273-276`
- 증상: `score = _float_value(item.get("score", 0.0))`. CLI(`main.py:477`)가 `_finite_or_none()`로 비유한 score를 JSON `null`로 직렬화하므로 infeasible consortium(true score `-inf`, `search.py:108`)은 `"score": null`. `dict.get("score", 0.0)`은 **키가 없을 때만** 0.0 — 키가 있고 값이 None이면 None 반환. `_float_value(None)`이 0.0 반환 → 테이블에 Score "0".
- 영향: solve 실패(infeasible) consortium이 0.0-score feasible 결과처럼 표시. (정정: 요약이 score로 정렬돼 infeasible은 맨 아래 위치하고 Status 컬럼은 "infeasible" 표시 → 행 순위 오염 아닌 Score 컬럼 표시 결함, High→Med. F-3로 GUI 미조립이라 현재 latent.)
- 수정안: None을 명시 처리 — `raw=item.get("score"); score = float("nan") if raw is None else _float_value(raw)`, NaN/None을 "—"/"failed"로 렌더.

### D-15. GUI search-fixture job이 temp 디렉토리 누수(`mkdtemp` 미삭제) (신규)
- 위치: `cmig/gui/app.py:357`
- 증상: `out_dir = Path(tempfile.mkdtemp(prefix="cmig-search-"))` 후 성공/실패 어느 경로에서도 삭제 안 함. 코드베이스의 다른 모든 temp 사용(`render/client.py:78`, `composer.py:117`, `synthetic_pair.py:103`)은 `TemporaryDirectory()` 컨텍스트로 자동정리하는데 이 raw mkdtemp만 예외. `cmig/gui/`에 rmtree/closeEvent/atexit 전무.
- 영향: Search 탭 실행마다 `cmig-search-XXXX` 디렉토리+내용이 시스템 temp에 영구 누적 → 장기 GUI 세션/CI offscreen 루프에서 inode/disk 고갈, `/tmp` 오염. (데이터 정합성 무영향, JobRunner 발견과 별개 → Med.)
- 수정안: 본문을 `with tempfile.TemporaryDirectory(prefix="cmig-search-") as td:`로 감싸 블록 종료 전 summary 읽기, 또는 read 후 `finally`에서 `shutil.rmtree(out_dir, ignore_errors=True)`.

---

## 4. 🟡 Low

### D-16. `_load_bounds_json`: JSON null은 미포착 TypeError 크래시, JSON bool은 숫자 bound로 조용히 수용 (신규, 2건 병합)
- 위치: `cmig/cli/main.py:683-685`
- 증상: `lo, hi = float(pair[0]), float(pair[1])`에 원소 타입 검사 없음. ① `{"R1":[null,5]}` → `float(None)`은 **TypeError**(ValueError 아님), caller의 `except ValueError/GateBlockedError/OSError`에 안 잡혀 top-level 트레이스백. ② `bool`은 `int` 서브클래스라 `{"R1":[false,true]}`가 `[0.0,1.0]`으로 통과 — 오탈자가 reaction을 `[0,1]`로 조용히 제약하고 run_hash bounds 구성요소(F-2)에 반영.
- 영향: 잘못된 bounds JSON이 graceful rc=2("bounds 값 오류") 대신 트레이스백(null) 또는 silent 데이터 수용(bool). fail-explicit 계약 위반. (손수 만든 비정상 입력 필요, 과학 산출 무오염 → Low.)
- 수정안: `float()`를 `try/except (TypeError, ValueError) → raise ValueError("bounds 값 오류...")`로 감싸고, 677-682 가드에 `isinstance(pair[i], bool)` 거부 추가.

### D-17. minimal medium U-base fallback `abs(lower_bound) or 1000.0`가 모델 lb==0인 exchange에 1000 uptake 날조 (신규, F-8 인접)
- 위치: `cmig/core/medium.py:84`
- 증상: `out[ex] = abs(float(rxn.lower_bound)) or 1000.0`. `_is_blocked`는 `(0,0)`만 blocked로 보므로 `(0,1000)`(uptake 금지·secretion 허용) exchange는 통과하고, `abs(0.0)==0.0`이 falsy라 `or 1000.0`이 모델이 불허한 uptake 1000.0을 부여. (실 cobra로 재현 확인.)
- 영향: 해당 U-base nutrient의 `uptake_bounds`가 1000.0으로 과대보고. (정정: 표준 BiGG U-base는 lb=-1000이라 기본 경로에선 안 터짐 — 비표준 u_base/커스텀 GEM 필요. `uptake_bounds`는 현재 프로덕션 소비자 없음(grep) → 보고 전용, latent, Med→Low. F-8의 tie-break/cardinality와는 다른 *magnitude 날조* 하위결함.)
- 수정안: `or 1000.0` 제거(`abs(float(rxn.lower_bound))`는 uptake-닫힌 nutrient에 0을 올바르게 산출), 또는 lb==0이면 주입 skip. falsy-zero `or` 관용구 회피.

### D-18. 골든 hash가 ±inf를 비표준 `Infinity` 토큰으로 — manifest와 비대칭 (기존 golden inf)
- 위치: `cmig/core/golden.py:21-27, 42-47`
- 증상: `_round`는 NaN→`"NaN"` 센티넬이나 inf는 `round(inf,6)=inf`로 그대로. `normalized_table_hash`(44-46)가 `allow_nan=False` 없이 `json.dumps` → inf 셀이 비표준 JSON 토큰 `Infinity`/`-Infinity`로 직렬화. `manifest._round_floats`(69-72)는 inf→센티넬 문자열 + `canonical_json`은 `allow_nan=False`(105). golden이 `allow_nan=False`를 빠뜨린 유일한 직렬화기.
- 영향: 동일 inf 값이 golden(토큰 `Infinity`)과 run_hash(센티넬 `"Infinity"`)에서 다르게 정규화 → provenance/정규화 불일치 + 비유한을 "normalized" hash에 silent 수용(fail-loud여야). (대부분 solve가 ±1000 clamp라 inf 도달은 엣지 → Low.)
- 수정안: `golden._round`에 `if math.isinf(v): return "Infinity" if v>0 else "-Infinity"` 추가 AND/OR `normalized_table_hash`의 `json.dumps`에 `allow_nan=False`.

### D-19. `golden_fixture`가 osqp의 growth/sign TSV를 6자리로 캡처(문서화된 ~6.3e-6 jitter에도) (신규)
- 위치: `cmig/golden_fixture.py:98-109`
- 증상: `capture()`가 `growth_expected.tsv`·`sign_expected.tsv`를 모든 variant에 `DEFAULT_DECIMALS=6`으로 기록. 그러나 docstring(30-33)·`VARIANT_DECIMALS`(34-37)는 osqp가 반복적이라 cross-process growth jitter ~6.3e-6라 parquet 골든은 osqp에 4자리를 쓴다고 명시. TSV 두 산출물만 `VARIANT_DECIMALS`를 무시.
- 영향: 커밋된 `osqp/growth_expected.tsv`(0.436962/0.436960/...)가 `gurobi`(0.436964/0.436959/...)와 정확히 6번째 자리에서 갈림 — jitter 밴드 내. 다른 머신에서 fresh capture와 diff하면 osqp가 6번째 자리에서 거짓 불일치. (현재 TSV 내용 비교 소비자 없음(`test_engine_golden.py:104`는 존재만 검사) → latent, Low.)
- 수정안: TSV 포맷에 `DEFAULT_DECIMALS` 대신 `VARIANT_DECIMALS[solver]`(이미 line 112에 `dec` 존재 — 98 위로 hoist) 사용.

### D-20. `FileSystemStore.record_run`이 항상 `micom_version=NULL` 영속 (SolveResult에 해당 필드 없음) (신규)
- 위치: `cmig/service/store.py:74`
- 증상: `getattr(result, "micom_version", None)`인데 `SolveResult`(`engine.py:51-68`)는 `micom_version` 속성이 없는 frozen dataclass → 항상 None 반환. 스키마(`store.py:32`)가 예약한 `micom_version TEXT` 컬럼이 모든 행에서 영구 빈값. 값은 `MicomEngine.micom_version`(`engine.py:108`)으로 가용하나 `RunStore.record_run(run_hash, result)` 시그니처가 버전을 안 받아 영속 시점에 유실.
- 영향: durable store를 MICOM 버전으로 직접 filter/report 불가. (정정: dedup은 무영향 — `micom_version`이 run_hash 11구성요소에 포함(`golden_fixture.py:65,80`)되어 버전 bump가 이미 다른 hash·다른 행 생성. 손실은 "쿼리 가능한 provenance 컬럼이 빈값"으로 좁음 → Low.)
- 수정안: `RunStore.record_run`(및 `FileSystemStore`)이 엔진/버전을 명시 인자로 받게 확장(SolveResult는 frozen이라 못 실음).

### D-21. namespace gate `warned_low`가 status 아닌 confidence로 필터 — 이미 해결된 LOW 매핑에 허위 경고 (신규)
- 위치: `cmig/core/namespace.py:88`
- 증상: `warned_low = [d for d in decisions if d.confidence is Confidence.LOW]` — status 무시하고 모든 LOW를 선택. LOW+RESOLVED 결정이 coverage(resolved, line 89)와 warned_low에 **동시 집계**. docstring(81)은 warned_low를 "low-confidence이며 진행(자동병합 금지)" = WARNED 케이스로 정의, `DecisionStatus.WARNED`(line 31) enum도 존재.
- 영향: 사용자가 이미 해결한 매핑에 경고 표면(§7 coverage%+unresolved 바로가기 혼란), warned-low 카운트 부풀림. (block/solve 정확성 무영향, 수동 편집 후에만 발생 — auto-producer는 LOW+RESOLVED 미생성 → Low.) `model_import.py:159`는 올바르게 status로 'warned' 계산 — gate만 confidence-only.
- 수정안: `warned_low = [d for d in decisions if d.status is DecisionStatus.WARNED]`.

### D-22. `build_tidy`가 `NOISE_FLOOR` import 대신 `eps=1e-6` 하드코딩 (sign noise-floor drift 위험) (신규)
- 위치: `cmig/core/interactions.py:31`
- 증상: `def build_tidy(result, eps=1e-6)` — `sign.NOISE_FLOOR` import 안 함. 이 eps가 `convert()`/`cross_feeding_weight()`/inline 비교(65,90,99-104)로 secretion/uptake/no-flow 분류에 쓰임. `sign.py:21`은 "NOISE_FLOOR는 단일 기준값 — 모든 소비자 공유(독립 하드코딩 금지·drift 제거)" 명문. `metrics.py:18`은 올바르게 import.
- 영향: 현재 출력 무오류(1e-6==1e-6). 그러나 NOISE_FLOOR 재튜닝 시 tidy 분류만 추적 못 해 metrics/sign과 불일치 → latent 골든 회귀·cross-feeding edge 발산. (contract-violation, 현재 무오류 → Low.)
- 수정안: `from cmig.core.sign import NOISE_FLOOR` + `def build_tidy(result, eps: float = NOISE_FLOOR)`.

### D-23. `enumerate_conditions`가 동일-kind 축을 조용히 붕괴 — 축 손실 + 중복 run_hash/parquet 행 (신규, latent)
- 위치: `cmig/core/sweep.py:99-107`
- 증상: `dict(zip(kinds, combo, strict=True))`. `SweepAxis`는 kind∈AXIS_KINDS만 검증(62-64), 축 간 kind 유일성 미검증. 같은 kind 두 축이면 cartesian product는 확장되나 dict는 마지막 값만 유지 → 첫 축 소거 + 여러 condition_id가 동일 axis_values로 붕괴. (`strict=True`는 길이만 검사, 키 유일성 아님.)
- 영향: 반복 kind로 축을 프로그램적으로 만든 caller가 조용히 틀린 sweep(차원 소실, parquet 모호 중복행, run_hash 캐시 교차오염). (정정: 모든 현 CLI caller가 distinct kind 하드코딩(`main.py:752,813`), SweepAxis 다른 생성처 없음 → 도달 불가 latent → Low.)
- 수정안: `enumerate_conditions`에서 `if len(kinds) != len(set(kinds)): raise ValueError`.

### D-24. `run_host_microbe`가 community solve status 무시 — infeasible community가 "굶주린 호스트"로 위장 (신규)
- 위치: `cmig/core/host.py:286-289`
- 증상: `result = eng.cooperative_tradeoff(...)` 후 `result.status`/`result.diagnostic`을 안 읽고 바로 `secretion = {m:v for m,v in result.external_exchange.items() if v>1e-6}` → `solve_host`. community가 infeasible여도 그 status/diagnostic이 `HostSolveResult`로 전파 안 됨.
- 영향: 실패한 microbial community가 "valid한데 굶은 호스트"로 오보고, 진짜 근본원인 유실. 코드베이스의 'silent 위장 금지' 원칙을 이 seam에서 우회. (정정: finder의 NaN 메커니즘은 과장 — `external_exchange`는 medium-row gated(`engine.py:151`), MICOM의 infeasible flux 거동은 런타임 의존. status/diagnostic 폐기 자체는 정적 확실. Extension 계층·facade 미노출·단일 행복경로 테스트 → Low.)
- 수정안: 호출 후 `if result.status != "optimal":` 가드 + `result.status`/`result.diagnostic`을 `HostSolveResult.diagnostic`/`HostImpact`로 전파.

### D-25. profile 렌더가 `--rlib` 미전달 → `figure.R`가 프로젝트 로컬 `.Rlib` 패키지 못 찾음 (기존 F-10)
- 위치: `cmig/render/client.py:81-86` (+ `cmig/render_r/figure.R`)
- 증상: `RenderClient.render`의 `figure.R` cmd에 `--rlib` 없음 + `figure.R`엔 `--rlib`/`.libPaths()` 처리 자체가 없음. Composer 패널(network/heatmap/chord)은 `--rlib` 전달 + `.libPaths(c(rlib, .libPaths()))` 호출. profile 경로만 예외.
- 영향: 렌더 패키지가 프로젝트 `.Rlib`에만 설치된 시스템에서 `figure.R`의 `requireNamespace("svglite"/"ragg")`가 FALSE → base `grDevices::svg`/`sans` 폰트로 조용히 degrade(패널은 정상 — 비일관). (정정: base fallback이 동작해 표준 svg/tiff는 크래시 아님, category는 resource-leak 아닌 config 일관성 → Low. F-10 중복.)
- 수정안: `client.py:81-86` cmd에 `"--rlib", str(_RLIB)` 추가 + `figure.R`에 `--rlib` 읽어 `.libPaths()` prelude(패널 스크립트 미러링).

### D-26. matplotlib `_fallback`이 `savefig` 예외 시 Figure 누수 (try/finally 없음) (신규)
- 위치: `cmig/render/client.py:107-113`
- 증상: `fig,ax = plt.subplots(...)` → `fig.savefig(out, format=spec.format)` → `plt.close(fig)`. try/finally 없음. `savefig`가 가장 실패하기 쉬운데(예: `tiff`는 Pillow 필요, I/O 에러) 예외 시 `plt.close` 건너뛰어 pyplot 전역 Figure 매니저에 등록 잔존. `SUPPORTED_FORMATS`가 tiff 허용(validate 통과)이라 도달 가능. `plt.close`는 코드베이스 유일, `plt.close('all')` 안전망 없음.
- 영향: 실패한 fallback 렌더마다 pyplot 관리 Figure 1개 누수(메모리 + "More than 20 figures opened" 경고). (에러 경로·env 의존·현 프로덕션 렌더 루프 미배선(F-3) → latent, Low.)
- 수정안: `savefig`를 `try/finally`(`finally: plt.close(fig)`)로, 또는 pyplot 대신 `Figure`+`FigureCanvasAgg` 직접 사용해 전역 레지스트리 의존 제거.

### D-27. `JobRunner.retry`/`result`가 lock 없이 공유 dict 읽기 + bare KeyError (기존 F-11 확장)
- 위치: `cmig/service/jobrunner.py:157-160` (`retry`), `:152-155` (`result`)
- 증상: `submit()`은 `_specs`/`_futures`를 `self._lock` 하에 채우는데(91-101), `retry()`는 `self._specs[job_id]`를(159), `result()`는 `self._futures[job_id]`를(154) **lock 없이** 읽음. `poll()`/`cancel()`(142-150)은 올바르게 lock 획득 — 비일관. unknown job_id는 bare `KeyError`.
- 영향: (정정: CPython GIL상 단일 `dict[key]` 조회는 원자적이라 torn read/크래시는 없음 — 실질 결함은 ① poll/cancel 대비 형식적 비일관 lock, ② unknown id에 비구조화 KeyError. 수치/누수/데드락 없음 → Low. F-11(144-156)의 재기술/확장.)
- 수정안: `retry()`/`result()`의 dict 읽기를 `with self._lock:`로 감싸고 부재 id에 구조화 에러(도메인 KeyError) raise.

---

## 5. ⚪ Uncertain (1)

### D-28. `write_solve_output`의 parquet+manifest 비원자적 기록 — 크래시 시 manifest 없는 출력 디렉토리 (crash-consistency 하드닝)
- 위치: `cmig/io/solve_output.py:84-135`
- 증상(사실): `bundle.write(out)`(parquet 3-4개 순차) → `target_summary.json` → `manifest.json`을 전부 **최종 경로에 직접 기록**, temp+rename 없음. 코드베이스에 `os.replace`/원자적 publish 전무. manifest가 마지막이자 유일한 run_hash 운반자.
- 검증 판정(uncertain, conf 0.6): 비원자 기록은 사실이나 **주장된 영향은 과장**. 유일한 manifest reader(`service/outcome.py:48`)는 부재 시 `FileNotFoundError`/`JSONDecodeError`/`KeyError`로 **hard-fail**하지 정상 처리하지 않음. "valid한 run dir로 오인"하는 스캐너 없음. `artifacts[]`는 parquet 기록 성공 후 계산(87-95)되어 존재하지 않는 파일을 나열할 수 없음. 명세에 atomicity 요구 없음. → 정상 동작/일반 예외에선 무해, `kill -9`/disk-full/정전 같은 비정상 중단 시의 crash-consistency 갭(하드닝).
- 수정안(원하면): 각 파일을 temp 경로에 쓰고 `os.replace`로 publish, `manifest.json`을 마지막 commit marker로 — run dir은 manifest 존재 시에만 valid.

---

## 6. 적대적 검증에서 기각된 주장 (false positive 기록)

> 분석 단계에서 제기됐으나 **코드/실증으로 반박**됨. 보고서 본문 제외. 정직성 차원에서 기록.

| 기각 주장 | 반박 근거 |
|---|---|
| `solve_output.py:43-47` abundance 이중 라운딩(6→variant)으로 run_hash 비멱등 | 산술 전제는 맞으나, **프로덕션 run_hash/캐시 키는 항상 decimals=6**(`manifest.py:131,135,40`) — 6→6은 멱등(200만 샘플 0 불일치). 영향 전제 반박. |
| `metrics.py:101-117` infeasible 단일배양 성장률을 'no change'로 오분류 | `_sign(NaN)=0`은 맞으나 "infeasible mono가 NaN/0 objective"가 **거짓**. 실 cobra(gurobi) infeasible 모델로 `solve_single_model`이 `status=infeasible`이되 `objective=1000.0`(solver incumbent의 유한 garbage), fluxes 비-NaN 반환 → `_sign`은 ±1. |
| `fva.py:75-76,124-125` FVA가 caller `.solver`를 영구 변형 | 변형 자체는 사실이나 모듈 전반(knockout/solve_single/host/dfba)에 균일·의도적이며 어떤 프로덕션 caller도 변형된 모델을 재사용 안 함 — *잘못된 거동을 낳는 결함*으로는 반박. |
| `store.py:49-52` 호출마다 sqlite 연결 열고 안 닫음 → 누수 | `with sqlite3.connect()`가 블록 후 연결을 열어두는 건 사실이나, **실증: 2000회 호출에 fd 평탄(delta=1, WAL 파일)**, gc 비활성에도 CPython refcount가 `with` 종료 즉시 100개 연결 모두 finalize — 누적/fd 누수 없음. |
| `jobrunner.py:152-155` `result()`가 FAILED job에 None 반환해 에러 은폐 | 메커니즘은 맞으나 **설계 §4.4 명문 계약** — `result()`는 "완료 시 산출 회수"(재-raise 약속 없음), 실패는 `poll()`의 `state=failed`+`diagnostic`으로 표면화(NFR Reliability: job 실패가 GUI를 죽이지 않음). 의도된 동작. |

---

## 7. 권장 수정 우선순위 (디버깅 관점)

> 효율 표기 S/M/L. 모든 수정은 작은 변경·기존 테스트 green 유지 가능. git 활성화됨(되돌리기 가능).

1. **D-2 (F-1) OSQP `qp_only_approximate` 정직화** — 과학적 provenance 신뢰, 1줄 변경·큰 효과. (S) 단 osqp 골든 재캡처 필요.
2. **D-1 model_checksum** — 재현성/캐시 정합성 핵심, 명세 §2 구성요소 #1 준수. (M) 골든 run_hash 영향 → 재캡처 동반.
3. **수치/과학 정확성 군**: D-4(inf→optimal 가드) · D-5(tables_close NaN 통과) · D-12(dfba 질량보존) · D-9/D-10(host maintenance) — 작은 가드 추가로 거짓 성공/유령 성장 차단. (S–M)
4. **에러 정직성 군**: D-3(pair status) · D-13(diagnostic 분류) · D-8(sweep cancel→DONE) · D-14(GUI score 0.0) — 실패를 실패로 보고. (S–M)
5. **상태/자원 안전성**: D-6(sandbox bounds 원자화) · D-11(host solver 컨텍스트) · D-15/D-26(temp/figure 누수) · D-27(jobrunner lock). (S)
6. **결정성/재현성**: D-7(GA tie-break) · D-19(osqp TSV 자리수) · D-23(sweep 중복 kind) · D-18(golden inf). (S)
7. **입력/계약 위생**: D-16(bounds JSON) · D-17(U-base 1000) · D-20(micom_version) · D-21(warned_low) · D-22(NOISE_FLOOR) · D-24(host status) · D-25(--rlib). (S)
8. **D-28** crash-consistency 하드닝은 선택(정상 경로 무해).

> ⚠️ **골든 영향 주의**: D-1·D-2(+D-18/D-19)는 run_hash 또는 골든 fixture 산출에 영향 → 수정 시 `cmig golden`/`golden_fixture` 재캡처 + `git diff`로 의도된 변화만 커밋해야 함. 나머지는 골든 무영향(가드/누수/계약).

---

## 8. 반영 상태 (2026-06-02)

이번 수정에서 반영:
- D-1 model checksum: taxonomy CSV가 아니라 `file` 컬럼의 사용자 제공 GEM 파일 checksum 집합으로 계산.
- D-2 OSQP provenance: 루트 명세 기준 `flux_solver=null`, `flux_report_status=qp_only_approximate`.
- D-3 pair 실패 전파, D-4 비유한 growth 가드, D-5 golden NaN/inf 비교 가드.
- D-6 sandbox bounds 원자화, D-7 GA tie-break 결정성, D-8 sweep cancel 상태 전파.
- D-9/D-10 host maintenance 부재/완화 방지, D-11 generic host solver context 복원.
- D-12 dFBA 고갈 step 질량보존 스케일링.
- D-13 exception diagnostic 타입 우선 분류, D-14 GUI null score 표시, D-15 temp dir 자동정리.
- D-16 bounds JSON null/bool 거부, D-17 U-base lb=0 uptake 날조 제거.
- D-18 golden inf canonicalization, D-19 OSQP TSV variant decimals.
- D-21 namespace warned_low status 기준, D-22 NOISE_FLOOR 단일 기준 사용.
- D-23 duplicate sweep axis kind 거부, D-24 host-microbe community failure 전파.
- D-25 profile R renderer `--rlib`, D-26 matplotlib fallback figure close, D-27 JobRunner lock read.

이번 수정에서 제외:
- D-20 `FileSystemStore.record_run`의 `micom_version` 컬럼 보강은 store API 변경이 필요해 별도 패치로 분리.
- D-28 atomic output publish는 crash-consistency hardening 성격이라 별도 패치로 분리.
