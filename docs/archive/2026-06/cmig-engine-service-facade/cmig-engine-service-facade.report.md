<!--
  PDCA Completion Report — cmig-engine-service-facade (Roadmap Phase 0.1)
  Chain: Plan → Design(Option C) → Do → Check(98.5%, iterate 1) → Report
-->

# cmig-engine-service-facade — Completion Report (v1.0)

## Executive Summary

| 관점 | Value Delivered (실측) |
|------|------------------------|
| **Problem** | Option C의 EngineService facade·Store seam이 명시 클래스로 부재 → solve/sandbox/sweep/io 오케스트레이션 산재, GUI·JobRunner·PART II 착수 불가. |
| **Solution** | `cmig/service/` 신규 패키지: 명시 `EngineService`(순수 위임) + `FileSystemStore`(sqlite meta, seam #3) + `SolveOutcome` 값객체. RunStore Protocol을 `core/run_store.py`로 정식화(레이어 정상). CLI를 facade 소비로 리팩터(인라인 ~50줄 → ~15줄). |
| **Function UX Effect** | CLI·GUI·JobRunner 공통 facade 진입점. 동일 run_hash 영속 dedup(FileSystemStore). 실 MICOM gurobi E2E(parquet+manifest+target_summary) 동작. solve_single은 정직한 capability_missing. |
| **Core Value** | 재현성(run_hash **비트 일치** facade==CLI==library) + 정직성(가짜 success 0·unwired 0) + 후속 16 feature 공통 토대. **204 tests·잔여 결함 0**. |

## 1. Success Criteria 최종 상태 (6/6 Met)

| SC | 상태 | 증거 |
|----|------|------|
| SC-S1 facade 비트일치 | ✅ Met | `test_solve_fixture_run_hash_matches_library` + `test_facade_bit_identical_to_cli` + `test_facade_solve_community_matches_cli`(A3 추가) — run_hash `29844e29…` facade==CLI==library |
| SC-S2 Store cache | ✅ Met | record_run/cache_lookup hit·miss·idempotent·NaN→NULL (7 store tests) |
| SC-S3 CLI 무변 | ✅ Met | CLI facade 소비(main.py:42,88), 기존 CLI 테스트 green, 산출 비트 일치 |
| SC-S4 RunStore Protocol 승격 | ✅ Met | `isinstance(FileSystemStore, RunStore)` + sandbox COMMIT 영속 + service→core 방향 |
| SC-S5 honest stub | ✅ Met | solve_single → status=capability_missing·run_hash None·가짜 success 0 |
| SC-S6 품질 게이트 | ✅ Met | **204 passed** · mypy strict clean · ruff clean · 0 placeholder · Qt-isolation(subprocess) |

## 2. 산출물

**신규 7**: `core/run_store.py`(Protocol) · `service/{__init__,outcome,engine_service,store}.py` · `tests/test_service_facade.py`(6) · `tests/test_filesystem_store.py`(7)
**수정 2**: `cli/main.py`(facade 소비 리팩터) · `core/sandbox.py`(RunStore re-export)

## 3. Key Decisions & Outcomes

| 결정 | 출처 | 따랐나 | 결과 |
|------|------|--------|------|
| Option C(명시 facade + FileSystemStore + SolveOutcome) | Plan/Checkpoint 3 | ✅ | 경계 clean·risk Low·maintainability High |
| solve_single 무조건 CAPABILITY_MISSING(MILP 게이트 제거) | Design §2.4(적대 검증) | ✅ | osqp-only 오라벨 방지·정직 |
| RunStore Protocol **core 유지**(service로 이동 X) | Design §4.1(적대 검증) | ✅ | core→service 역전 제거, 레이어 정상 |
| run_hash 단일 canonical 위임(재구현 0) | Plan [HASH-SINGLE] | ✅ | facade==CLI==library 비트 일치 |
| env_lock 기본 None·CLI 미전달 | Design §2.3 | ✅ | manifest bytes 불변 |
| sqlite3 meta index·`cmig/service/` 패키지 | Checkpoint 2 | ✅ | 명세 §3(YAML+SQLite) 정합·Qt 비의존 |

## 4. 정직성 — 검증·잔여 위험·경계

- **"테스트 green ≠ 기능 연결" probe 통과**: facade가 실제 CLI 산출 경로에 wire됨(orphan helper 아님), sandbox commit이 FileSystemStore.record_run로 영속. 14-agent 적대 검증이 명시 확인.
- **하드 불변 6종 전량 충족**: HASH-SINGLE·BIT-IDENTICAL·QT-INDEPENDENT·HONEST-STUB·STORE↔CACHE 비중첩·LAYER-NORMAL.
- **적대 검증 9 raw → 3 Minor confirmed → 전량 수정**(iterate 1): A1 CLI OSError→rc2 · A2 assert→명시 status guard(-O 안전) · A3 solve_community 비트일치 테스트.
- **경계(정직 표기)**: FileSystemStore.cache_lookup은 **meta/provenance probe**지 값 replay 아님(값 replay는 sweep RunHashCache). default CLI 경로는 persistence 미연결(opt-in, 후속 `--store`). solve_single은 Phase 1.1까지 stub.
- **osqp run_hash 비트일치 미검증(설계 의도)**: osqp 1차 jitter로 cross-process 6-decimal 불일치 가능 → gurobi(결정적)만 비트일치 검증. 기존 정책 일관.

## 5. Quality Metrics
- 테스트: **204 passed**(191 baseline + 13 신규: facade 6 + store 7), 0 fail.
- 정적: ruff clean · mypy strict clean(35 files) · 0 placeholder.
- Match Rate: 98.5%(struct 98·func 96·contract 99·runtime 100) → 3 Minor 수정 후 유효 ≈100%.
- 적대 검증: 14 agents, 9 raw → 6 rejected(non-issue) → 3 Minor confirmed → 3 fixed.

## 6. 결론
Roadmap Phase 0.1 완료. Option C facade·Store seam·RunStore Protocol 정식화로 **GUI(0.3)·JobRunner(0.2)·AN-SINGLE(1.1)·PART II의 공통 토대** 확보. run_hash 단일 canonical·비트 일치·Qt 비의존을 회귀 게이트로 보호. 다음: **Phase 0.2 `cmig-jobrunner`**(facade 소비 비차단 실행) 또는 병행 `host-microbe-spike`(3.0).

## Version History
| 버전 | 일자 | 내용 |
|------|------|------|
| v1.0 | 2026-06-01 | 완료 보고. SC 6/6 Met, 204 passed, Match 98.5%(3 Minor 수정 후 ≈100%), 잔여 결함 0. |
