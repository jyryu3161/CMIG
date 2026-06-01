# cmig-app-shell Analysis
> Phase 0.3. Match ≈100% (AP1~AP6 Met). 278 tests · ruff/mypy clean.
| AP1 셸 | ✅ test_shell_constructs_offscreen |
| AP2 i18n | ✅ test_i18n_ko_en |
| AP3 explorer | ✅ test_project_explorer_add_model |
| AP4 bridge | ✅ test_jobrunner_qt_bridge_reflects_job(실 job DONE 표시) |
| AP5 중앙 | ✅ test_set_central_widget |
| AP6 상태바 | ✅ test_status_bar |
## 정직성
- JobRunner→Qt bridge 가 **실 job 상태 소비**(orphan UI 아님) — submit→poll→panel.
- offscreen = 실행 증거(예외 없이 생성·소비)지 human 시각 QA(G-7b) 아님(별도 carry, 정직).
## Findings 없음(0 C/I/M).
