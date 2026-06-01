<!--
  PDCA Analysis (Check) — cmig-engine-service-facade (Roadmap Phase 0.1)
  Plan: docs/01-plan/features/cmig-engine-service-facade.plan.md
  Design: docs/02-design/features/cmig-engine-service-facade.design.md
  Verified by 14-agent analyze workflow (gap-detector + code-analyzer + 3 adversarial lenses + per-finding re-verify).
-->

# cmig-engine-service-facade Analysis Document

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | Option C facade·Store seam 실체화 → GUI·JobRunner·PART II 토대. |
| **RISK** | facade 재구현 시 run_hash 단일 canonical 위반 → 191 tests·golden 회귀. |
| **SUCCESS** | facade 산출 run_hash·parquet 비트 일치 + 203 green + Store cache + honest stub. |

## Match Rate

| 축 | 점수 | 가중 |
|----|-----:|------|
| Structural | 98 | ×0.15 |
| Functional | 96 | ×0.25 |
| Contract | 99 | ×0.25 |
| Runtime | 100 | ×0.35 |
| **Overall** | **98.5%** | (≥90% 통과) |

- **Structural**: Design §1.1 Module Map 9/9 모듈 존재(facade·SolveOutcome·FileSystemStore·RunStore Protocol·CLI 리팩터·테스트 2).
- **Functional**: 메서드 시그니처 Design §2~4 일치, 0 placeholder.
- **Contract**: facade §2 / SolveOutcome §3 / FileSystemStore §4 / CLI §5 계약 일치.
- **Runtime**: 203 tests green + 실 MICOM E2E(CLI→facade→parquet+manifest+target_summary).

## Strategic Alignment
- **WHY 충족**: facade·Store가 명시 클래스로 실체화 → 16 downstream 소비자 토대 확보.
- **하드 불변 전량 충족**: [HASH-SINGLE] run_hash 재계산 0(manifest read) · [BIT-IDENTICAL] facade==CLI 비트 일치 · [QT-INDEPENDENT] service PySide6 0(subprocess) · [HONEST-STUB] solve_single capability_missing · [COEXIST] FileSystemStore↔sweep RunHashCache 책임 비중첩(hash 1개) · [LAYER-NORMAL] RunStore Protocol core 정의(service→core).
- **"테스트 green ≠ 기능 연결" probe 통과**: facade가 실제 CLI 산출 경로에 wire됨(_cmd_solve/_cmd_solve_fixture가 EngineService 소비), sandbox commit이 FileSystemStore.record_run로 영속 — orphan helper 아님.

## Success Criteria 최종

| SC | 상태 | 증거 |
|----|------|------|
| SC-S1 facade 비트일치 | ✅ Met | `test_solve_fixture_run_hash_matches_library`·`test_facade_bit_identical_to_cli` |
| SC-S2 Store cache | ✅ Met | `test_record_run_then_cache_lookup_hit`·`_miss_returns_none`·`_idempotent`·NaN→NULL |
| SC-S3 CLI 무변 | ✅ Met | CLI facade 소비(main.py:42,88) + 기존 CLI 테스트 green |
| SC-S4 Protocol 승격 | ✅ Met | `isinstance(FileSystemStore, RunStore)` + sandbox COMMIT 영속 + service→core 방향 |
| SC-S5 honest stub | ✅ Met | `test_solve_single_is_honest_stub`(status=capability_missing·run_hash None) |
| SC-S6 품질 게이트 | ✅ Met | 203 passed · mypy strict clean · ruff clean · 0 placeholder · Qt-isolation |

## Findings (14-agent 적대 검증: 9 raw → 3 confirmed Minor, 0 Critical/Important)

| # | 심각도 | 항목 | 조치 | 상태 |
|---|--------|------|------|------|
| A1 | Minor | CLI가 `write_solve_output` OSError 시 raw traceback (ImportError/ValueError만 catch) | `except OSError → rc2` 추가(양 핸들러) | ✅ 수정 |
| A2 | Minor | facade 성공 계약을 `assert`로 narrow → `python -O`에서 strip (Design §3.3은 명시 status guard 처방) | assert → 명시 status 분기(rc1 + diagnostic) | ✅ 수정 |
| A3 | Minor | Design §7이 명시한 `test_facade_solve_community_matches_cli`(user 경로 비트일치) 미작성 | 테스트 추가(run_hash+parquet 일치) | ✅ 수정 |

**Iterate 1회 결과**: 3 Minor 전량 수정 → **204 passed**(+1) · ruff clean · mypy strict clean. Critical/Important/Minor **0 잔여**. 유효 Match ≈ 100%.

**Rejected (6, non-issue 재검증)**: SolveOutcome.from_manifest 미처리 예외(write 직후라 사실상 도달불가)·FVA DRY(의도된 lazy import)·WAL pragma per-connection(정상)·ImportError 중복(faithful)·Store init race(단일 프로세스)·assert가 status 위반(A2로 통합).

## Decision Record 검증
- [Design] solve_single 무조건 CAPABILITY_MISSING(MILP 게이트 제거) → **구현 일치**(engine_service.py:128-131).
- [Design] RunStore Protocol core 유지(레이어 정상) → **구현 일치**(core/run_store.py, sandbox re-export).
- [Design] env_lock 기본 None·CLI 미전달 → **구현 일치**(manifest bytes 불변).

## Checkpoint 5 결정
사용자 선택 = **3건 모두 수정 후 report**. iterate 1회로 A1·A2·A3 수정 완료 → 204 passed·잔여 결함 0.

## Version History
| 버전 | 일자 | 내용 |
|------|------|------|
| v1.0 | 2026-06-01 | Match 98.5%, SC 6/6 Met, 적대 검증 9→3 Minor. Checkpoint 5 대기. |
| v1.1 | 2026-06-01 | Checkpoint 5: 3 Minor 전량 수정(iterate 1회). 204 passed·ruff/mypy clean·잔여 결함 0. 유효 Match ≈100%. |
