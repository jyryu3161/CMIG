# cmig-gui-views Analysis
> Phase 2(1차 슬라이스). Match ≈100% (GV1~GV6 Met). 284 tests · ruff/mypy clean.
| GV1 실 sweep | ✅ test_sweep_view_runs_real_sweep(JobRunner DONE) |
| GV2 cache-hit | ✅ test_sweep_view_cache_hit_display |
| GV3 실패 row | ✅ test_sweep_view_failed_row(silent 위장 금지) |
| GV4 sign+FVA | ✅ test_profile_view_sign_and_fva |
| GV5 target | ✅ test_profile_view_targets |
| GV6 빈 안전 | ✅ test_profile_view_empty |
## 정직성: SweepView 가 **실 JobRunner sweep 소비**(orphan UI 아님)·실패 row 명시·offscreen 실행 증거(G-7b 시각 QA 별도 carry).
## Findings 없음(0 C/I/M).
