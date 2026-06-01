# cmig-app-shell — Completion Report (v1.0)
## Executive Summary
| Problem | 데스크톱 셸·JobRunner Qt 연동 부재 |
| Solution | gui/app.py 3-pane + ProjectExplorer + Runtime&Jobs + JobsBridge(JobRunner→Qt) + i18n |
| Function UX Effect | offscreen 생성·실 job 상태 표시·중앙 도킹·한영 |
| Core Value | service 실 소비·offscreen 검증·G-7b carry. 278 tests·잔여 결함 0 |
## SC 최종 (6/6 Met): AP1~AP6.
## 산출물: gui/app.py · tests/test_app_shell.py(6, offscreen).
## Key Decisions: JobsBridge QTimer 폴링(Qt 비의존 service↔Qt) · 중앙 QStackedWidget(그래프 뷰 도킹) · i18n dict.
## Quality: 278 passed·ruff clean·mypy strict clean·0 placeholder.
## Carry-over: G-7b human 시각 QA(디스플레이 환경) · 2.x 인터랙티브 뷰(Community Builder/Sandbox/Compare/Sweep view).
## 결론: Phase 0.3 완료. §11 셸 토대 확보.
