# CMIG v3.0 구현 리뷰

- 작성일: 2026-05-31
- 기준 명세: `CMIG_명세서_v3.0.md`
- 확인 범위: `cmig/`, `tests/`, `fixtures/community_3_member/expected/`, `README.md`, `pyproject.toml`
- 검증 명령: `uv run pytest`
- 결과: `95 passed, 4 warnings`
- 후속 업데이트: `REVIEW/CMIG_v3_update_review_2026-06-01.md`에 2026-06-01 코드 재검토와 분석 시나리오 제안을 추가했다.

## 요약

현재 코드는 명세서 v3.0의 Baseline 중 **MVP-1a headless core**와 일부 **MVP-2 순수 로직**을 상당 부분 반영했다. 특히 sign 정규화, namespace hard gate, tidy contract, run_hash 11개 구성요소, golden fixture, delta, sandbox preview/commit, sweep cache/diagnostic, R render subprocess/fallback 경계가 코드와 테스트로 존재한다.

다만 제품 관점의 MVP-0~2 완료로 보기는 어렵다. CLI의 실제 solve 명령은 아직 안내 메시지만 반환하고, GUI shell/service/job runner/medium editor/FBA/pFBA/FVA/knockout 등 명세의 데스크톱 워크플로는 대부분 미구현이다. 또한 **OSQP growth 후 HiGHS LP pFBA 재계산**은 명세상 핵심 요구인데, 현재 구현은 결과 메타데이터와 golden 이름만 `highs/full`로 표시하고 실제 LP 재계산 코드가 보이지 않는다.

## 반영 상태 매트릭스

| 명세 항목 | 상태 | 근거 | 비고 |
|---|---:|---|---|
| MICOM exact pin | 반영 | `pyproject.toml` `micom==0.39.0` | README는 아직 2a/2b 설명이 혼재 |
| MICOM public API wrapper | 부분 반영 | `cmig/core/engine.py` | `cooperative_tradeoff(... fluxes=True, pfba=True)` 사용 |
| OSQP growth → LP pFBA 재계산 | 미흡 | `cmig/core/engine.py:117-119`, `157-159` | 실제 HiGHS LP 재계산 경로 불명확 |
| sign convention 단일 진입점 | 반영 | `cmig/core/sign.py`, `tests/test_sign.py` | canonical/실데이터 테스트 있음 |
| cross-feeding 추출 | 반영 | `cmig/core/interactions.py`, `tests/test_validation.py` | weight=min 규칙 테스트 있음 |
| namespace hard gate | 반영 | `cmig/core/namespace.py`, `tests/test_namespace_gate.py` | high-confidence unresolved 차단 구현 |
| tidy nodes/edges/profile | 반영 | `cmig/core/tidy.py`, `tests/test_tidy.py` | matrix optional, timecourse 범위 외 처리 |
| run_hash 11 구성요소 | 반영 | `cmig/core/manifest.py`, `tests/test_run_hash.py` | float rounding 포함 |
| golden fixture solver별 분리 | 부분 반영 | `fixtures/community_3_member/expected/*` | `highs` 단독 golden은 없음, `osqp`가 추가됨 |
| sandbox bound constraint + preview/commit | 부분 반영 | `cmig/core/sandbox.py`, `tests/test_sandbox.py` | core 로직만, debounce/FVA/GUI 없음 |
| sweep cache + failed diagnostic | 반영 | `cmig/core/sweep.py`, `tests/test_sweep.py` | diagnostic은 자유 문자열, 구조화 JSON은 아님 |
| R render subprocess/fallback | 부분 반영 | `cmig/render/client.py`, `tests/test_render.py` | profile bar 중심, 저널 preset/폰트/다양한 도표는 제한 |
| GUI graph viewer | 부분 반영 | `cmig/gui/graph_data.py`, `cmig/gui/graph_view.py` | Cytoscape payload/위젯 골격 |
| CLI 실제 community solve | 미구현 | `cmig/cli/main.py:31-37` | 현재는 2b 설치 안내 후 exit 2 |
| MVP-0 desktop shell/sidecar/job runner | 미구현 | 코드 구조상 부재 | PySide shell, FastAPI/sidecar facade 없음 |
| AN-SINGLE FBA/pFBA/FVA/knockout | 미구현 | 코드 구조상 부재 | solver capability만 있음 |
| Medium editor/comparison | 부분 반영 | `cmig/core/medium.py` | minimal medium core만 있음 |
| Extension G2/G3/G5 | 범위 외 | 명세상 PART II | 현재 구현하지 않는 것이 맞음 |

## 주요 발견

### R1. `osqp_growth_highs_flux`가 실제 LP 재계산을 수행한다는 증거가 없다

- 위치: `cmig/core/engine.py:117-119`, `cmig/core/engine.py:157-159`, `cmig/golden_fixture.py:50-56`
- 명세: §4.2, §16은 OSQP로 growth 확보 후 growth/community constraint를 고정하고 LP solver, 특히 HiGHS로 pFBA/normalization을 재수행해야 한다.
- 현재 코드: `community.cooperative_tradeoff(... pfba=True)` 한 번 호출 후, `cmig_solver == "osqp_growth_highs_flux"`이면 `growth_solver="osqp"`, `flux_solver="highs"`, `flux_report_status="full"`만 설정한다.
- 추가 증거: `fixtures/community_3_member/expected/osqp/config.json`와 `osqp_growth_highs_flux/config.json`의 `tidy_hashes`가 동일하다. 이는 hybrid fixture가 순수 OSQP 결과와 같은 flux를 저장하고 있음을 시사한다.
- 영향: 사용자는 `full (LP pFBA)` 결과라고 믿지만 실제로는 QP-only flux일 수 있다. 재현성, solver 비교, golden SC-6의 의미가 약해진다.
- 권장 조치: hybrid 경로에서 실제로 HiGHS/LP pFBA를 실행하는 별도 함수 또는 MICOM 지원 API를 연결하고, 테스트는 단순 메타데이터 확인이 아니라 `osqp`와 `osqp_growth_highs_flux`가 의도한 계산 경로를 다르게 탔는지 검증해야 한다.

### R2. 명세의 solver별 golden 목록과 구현 목록이 다르다

- 위치: `CMIG_명세서_v3.0.md` §16, `cmig/golden_fixture.py:25`
- 명세: solver별 golden은 `gurobi`, `highs`, `osqp_growth_highs_flux`.
- 구현: `SOLVER_VARIANTS = ("gurobi", "osqp", "osqp_growth_highs_flux")`.
- 비고: 문서 아카이브에는 pure-HiGHS QP 불가로 `osqp`로 조정했다는 설명이 있으나, 권위 명세는 아직 `highs`를 요구한다.
- 영향: 명세 기반 검토/CI 기준과 실제 회귀 기준이 어긋난다.
- 권장 조치: 둘 중 하나를 확정해야 한다. pure-HiGHS를 baseline에서 제외한다면 v3.0 명세 또는 REVIEW 결정 로그에 공식 변경으로 남겨야 한다.

### R3. CLI는 MVP-1a 완료 조건의 "CLI 3개+ 미생물·배지에서 산출"을 충족하지 못한다

- 위치: `README.md:11-17`, `cmig/cli/main.py:31-37`
- 명세: §16 MVP-1a 완료 조건은 CLI로 3개+ 미생물·배지 산출과 golden 통과를 요구한다.
- 현재 코드: `cmig solve`는 실제 solve를 수행하지 않고 "2b 엔진 stack 설치 후 사용 가능" 안내 후 종료한다.
- 영향: 라이브러리 함수와 테스트 fixture로는 solve가 되지만, 사용자 또는 자동화가 호출할 headless CLI 산출 경로가 없다.
- 권장 조치: 최소 CLI를 추가해야 한다. 예: `cmig solve-fixture --solver gurobi --out out/` 또는 taxonomy/medium 입력 기반 `cmig solve`가 `nodes.parquet`, `edges.parquet`, `profile.parquet`, manifest를 쓰도록 연결.

### R4. sandbox의 FVA/no-change 진단은 축약 구현이다

- 위치: `cmig/core/sandbox.py:1-9`, `cmig/core/sandbox.py:68-100`
- 명세: 변화 미미 시 FVA 범위와 "no significant change" 진단을 표시해야 한다.
- 현재 코드: delta threshold만으로 `no_significant_change`를 계산하고 FVA 계산/표시는 없다.
- 영향: bound constraint 변경 후 우회 보상 때문에 external profile 변화가 작을 때, 사용자가 실제 대체 flux 경로 또는 허용 범위를 판단할 근거가 부족하다.
- 권장 조치: FVA 결과를 `SandboxResult` 또는 profile `fva_lo/fva_hi`에 채우는 경로를 추가하고, 테스트에 "변화 없음 + FVA range 존재" 케이스를 넣는다.

### R5. sweep diagnostic 형식이 구조화되어 있지 않다

- 위치: `cmig/core/sweep.py:132-135`
- 명세/설계 문서: 실패 run은 diagnostic을 저장해야 하며, 계획 문서에서는 구조화 JSON 문자열 `{code, message, detail?}` 방향이 제시되어 있다.
- 현재 코드: `RuntimeError: infeasible` 같은 자유 문자열이다.
- 영향: GUI/통계/리포트에서 실패 원인별 필터링과 집계가 어렵다.
- 권장 조치: `Diagnostic` dataclass 또는 helper를 만들고 `code` enum(`infeasible`, `solver_error`, `capability_missing`, `gate_blocked` 등)을 저장한다.

### R6. README와 실제 상태가 맞지 않는다

- 위치: `README.md:11-39`
- 현재 README는 "현재 상태: MVP-1a — 2a", "SC-1·SC-5·SC-6·SC-7은 2b에서"라고 되어 있으나, 현재 테스트에는 MICOM golden/SC-5/SC-6/SC-7이 포함되어 통과한다.
- 영향: 신규 개발자가 현재 완료 범위를 오해할 수 있다.
- 권장 조치: README를 "2a + 일부 2b 통합 테스트/golden 존재, CLI solve 미구현, hybrid LP 재계산 검증 필요"처럼 갱신한다.

## 잘 반영된 점

- `cmig/core/sign.py`는 §4.3의 `+ = secretion`, `- = uptake` 규칙을 단일 진입점으로 구현하고 테스트가 있다.
- `cmig/core/namespace.py`는 high-confidence unresolved mapping 차단과 low-confidence warning을 명확히 분리한다.
- `cmig/core/manifest.py`는 v3.0에서 확장된 run_hash 11개 구성요소를 반영한다.
- `cmig/core/tidy.py`와 `cmig/core/interactions.py`는 nodes/edges/profile parquet 계약과 cross-feeding edge 산출을 안정적으로 구현한다.
- `cmig/core/sandbox.py`는 flux 직접 변경이 아니라 bound 변경/복구 API를 제공하고 preview가 store를 오염시키지 않는 테스트를 가진다.
- `cmig/core/sweep.py`는 cache hit, failed run 기록, `sweep.parquet` 저장을 테스트로 보장한다.
- `pyproject.toml`의 `pickle`/`cPickle` banned API 설정은 명세의 pickle 금지 정책과 맞다.

## 다음 업데이트 우선순위

1. `osqp_growth_highs_flux`의 실제 HiGHS LP pFBA 재계산 구현 여부를 확정하고, 현재 메타데이터-only 상태를 수정한다.
2. 명세 v3.0의 golden solver 목록(`highs`)과 구현 목록(`osqp`)의 불일치를 공식 결정으로 정리한다.
3. 실제 `cmig solve` CLI 산출 경로를 만들어 MVP-1a 완료 조건을 사용자가 실행 가능한 형태로 맞춘다.
4. sandbox에 FVA range 산출을 붙이고 `no_significant_change` 진단을 더 과학적으로 만든다.
5. sweep diagnostic을 구조화 JSON으로 바꿔 GUI/리포트/통계 후속 작업의 기반을 만든다.
6. README 상태 섹션을 현재 구현 상태와 테스트 결과에 맞게 갱신한다.

## 검증 로그

```text
$ uv run pytest
........................................................................ [ 75%]
.......................                                                  [100%]
95 passed, 4 warnings in 7.54s
```

경고는 OSQP의 `PendingDeprecationWarning` 4건이며 테스트 실패는 아니다.
