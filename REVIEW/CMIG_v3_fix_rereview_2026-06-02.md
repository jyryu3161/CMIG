# CMIG v3.0 — 디버깅 수정 재검토 의견 (검증 통과본)

- 작성일: 2026-06-02
- 대상: `REVIEW/CMIG_v3_debug_bughunt_2026-06-02.md`(D-1~D-28)에 대해 외부 AI가 적용한 수정
- 범위(커밋): `b2db458`(baseline) → `bf69fb4 Fix debug bughunt findings` → `d770bb2 Complete store provenance and atomic output fixes` (= HEAD)
- 방법: 전체 코드 diff 정독 + 추가 테스트 검토 + 게이트 재실행 + 골든 재생성 정당성 실증(run_hash 직접 계산).

---

## 0. 종합 판정: ✅ 양호 — 수정 품질 높음, 회귀 없음

| 게이트 (2026-06-02, fixed) | 결과 |
|---|---|
| `uv run pytest` | **green (exit 0)** |
| `uv run ruff check .` | All checks passed |
| `uv run mypy cmig` | Success: no issues found in 55 source files (strict) |

- **회귀 테스트가 vacuous하지 않음**: 추가된 10개 테스트가 실제 버그 시나리오를 가둠
  (D-1 모델 바이트 변경→checksum 변화, D-6 `(-10,5)→(8,20)` 정확한 시나리오,
  D-8 JobRunner 통한 mid-flight 취소→CANCELLED, D-20 `micom_version=="0.39.0"` 단언,
  D-16 null/bool 거부, D-21 LOW+RESOLVED→warned 제외, D-28 publish commit-marker 등).
- **골든 재생성 정당**: `growth/sign_expected.tsv`는 6→4자리(D-19)만 변경, flux 값 자체는
  동일(`0.436962→0.4370`, `5.152535→5.1525`) — D-2가 라벨 전용 변경임을 교차 확인.
- 수정안 대부분이 보고서 fix sketch와 정확히 일치하거나 더 나은 형태.

---

## 1. 항목별 수정 상태 (28건)

| 분류 | 항목 | 상태 |
|---|---|---|
| ✅ 정확 + 전용 회귀 테스트 | D-1, D-2, D-5, D-6, D-8, D-13, D-16, D-20, D-21, D-28 | 수정 + 테스트로 가드됨 |
| ✅ 정확 (전용 테스트 없음) | D-4, D-7, D-9, D-10, D-11, D-12, D-14, D-15, D-17, D-18, D-19, D-22, D-23, D-24, D-26, D-27 | 코드 검토상 정확, 전용 테스트는 없음 |

수정 내용 핵심 확인:
- **D-2** osqp 분기 `("osqp", None, "qp_only_approximate")` + docstring/solver.py/README/schema/glossary/decision 문서 일괄 갱신 — 정직화 정확.
- **D-4** `if not math.isfinite: unbounded/infeasible` 분기 + `DiagnosticCode.UNBOUNDED` 신설(+`_PRIORITY` 배선) — 정확.
- **D-12** dfba: 제한분율 `f=min(conc/required)`로 농도·biomass 둘 다 스케일(`effective_mu=mu*growth_scale`)
  → 한계 기질이 정확히 0으로 소진되고 성장도 동일 비율 → **질량보존 정확**(수식 검증함).
- **D-6** sandbox: 원자적 `rxn.bounds=()` + 예외 시 `restore_bounds` 후 re-raise → undo 계약 보존.
- **D-7** GA: `key=lambda g: (-fit(g), g)` 결정적 2차 키 — 정확.
- **D-9** maintenance reaction 부재 시 `HostSolveResult(False, "infeasible", ...)` + `HOST_MAINTENANCE_ABSENT` 진단.
- **D-10** `max(mr.lower_bound, maintenance_flux)` — 완화 방지.
- **D-11** host generic: 전체 본문 `with host:` 래핑 — solver 영구변형 해소.
- **D-28** parquet/manifest를 `TemporaryDirectory`에 쓰고 `os.replace`로 publish, manifest를 마지막 commit-marker로 — 비원자 기록 해소.

---

## 2. ⚠️ 짚어둘 지점 (수정은 됐으나 보완 권장)

### C-1 (중요) — osqp 골든 run_hash가 테스트로 보호되지 않음
실증 결과:
- `flux_solver=None` → run_hash `a422eb89…` (= 커밋된 osqp 골든, baseline·HEAD 동일)
- `flux_solver="highs"` → run_hash `ce6667b4…` (다름) → **`flux_solver`는 run_hash 구성요소 #7에 실제로 포함됨**

그런데 **baseline 코드는 `"highs"`를 방출**(F-1 버그)했으므로 baseline이 만들어내는 run_hash는 `ce6667b4`여야 하는데, **커밋된 baseline 골든은 `a422eb89`(=None 버전)**였다. 즉 **baseline의 osqp 골든 run_hash는 이미 stale**했고, 원인은 **osqp가 tolerance 비교만 받고 `config.json["run_hash"]`를 검증하는 테스트가 없어서** solver_setting 변경 시 staleness가 안 잡히는 구조적 갭이다. D-2 수정이 코드를 이미-커밋된 골든과 **우연히 일치**시켜 정합성을 복원했지만, 갭 자체는 남아 `flux_solver`를 또 바꾸면 재발한다.

→ **권장**: `test_golden_regression_per_solver`의 osqp 분기에, `_run_hash_components(solve("osqp"))`로 계산한 run_hash가 `config.json["run_hash"]`와 정확히 일치하는지 단언하는 1줄 추가.

### C-2 (경미) — D-13 잔여
`from_exception`이 예외 *타입명* `.endswith("infeasibleerror")`로 판정 → 임의 메시지 false-positive 제거(개선 확실). 다만 `fva.py`/`medium.py`의 `*InfeasibleError` 래퍼가 **임의 근본원인(IO/프로그래밍 에러)까지 그대로 감싸므로** 그 경우 여전히 INFEASIBLE로 분류된다(래퍼 자체 미수정). 현재 이 경로로 cobra의 bare `Infeasible`는 도달하지 않아 실해는 작지만, 완전 해소는 래퍼에서 근본원인 타입을 구분해야 한다.

### C-3 (경미) — D-25 rlib 경로 취약
`render/client.py:86`은 `Path(".Rlib").resolve()`(**cwd 상대**)인데 `composer.py:25`는 `Path(__file__).resolve().parents[2]/".Rlib"`(**모듈 상대, 견고**). repo 루트가 아닌 cwd에서 실행하면 client 경로가 빗나간다.
→ **권장**: client도 composer의 `_RLIB`(또는 동일 모듈상대 계산)을 재사용.

### C-4 (테스트 커버리지) — 과학적 수정 일부가 무방비
정확하지만 전용 회귀 테스트가 없는 항목 중 특히 거동을 바꾸는 두 건은 가드 테스트를 권장:
- **D-12 (dfba 질량보존)**: 고갈 step에서 `소비 ≤ 가용`이고 `Δbiomass`가 limiting fraction으로 스케일되는지.
- **D-3 (pair 실패 전파)**: infeasible co/mono 입력이 `interaction="failed"` + diagnostic을 내는지.

(그 외 D-4·D-7·D-9·D-10·D-11·D-14·D-23·D-24 등은 one-liner/구조 변경이라 코드상 정확하나 테스트 없음.)

### C-5 (정보) — D-20 sqlite 경로
프로덕션 solve는 `record_run`을 쓰지 않고 manifest로 `micom_version`을 이미 기록한다. `FileSystemStore.record_run`은 sandbox-commit 경로에서만 호출되며 거기서 `micom_version`이 정상 전달된다 — 구조적으로 올바름.

---

## 3. 회귀 점검
- osqp `edges` tidy_hash 변경 + `nodes`/`edges`/`profile`.parquet 바이트 변경은 **OSQP 반복해의 cross-process jitter**(4자리 경계)로, flux 값 변화가 아니며(`nodes`/`profile` 정규화 hash 불변) tolerance 비교라 통과 — 수정 회귀 아님. 단 **osqp 골든의 머신 의존성**은 사전부터 존재하는 별개 특성(D-19가 지적한 jitter).
- gurobi 골든(hash-exact) 및 production run_hash 정합성 영향 없음.

---

## 4. 결론 / 후속 권장 우선순위
28건 모두 합당하게 수정됐고 게이트·회귀 테스트 통과로 회귀 없음을 확인했다. 추가 작업 권장 순서:
1. **C-1** — osqp golden run_hash 검증 테스트 추가(staleness 재발 방지, 가장 중요).
2. **C-4** — D-12·D-3 가드 테스트 추가(과학적 거동 회귀 방지).
3. **C-3** — `render/client.py` rlib 경로를 모듈상대로 통일.
4. **C-2** — `fva.py`/`medium.py` 래퍼의 근본원인 타입 구분(진단 정밀화).
