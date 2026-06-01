# cmig-app-shell Planning Document
> Roadmap Phase 0.3 (§11) — PySide6 3-pane 데스크톱 셸 + JobRunner→Qt bridge.
## Executive Summary
| Problem | 데스크톱 앱 셸(ProjectExplorer·Runtime&Jobs·중앙)·JobRunner Qt 연동 부재 |
| Solution | gui/app.py — QMainWindow 3-pane + ProjectExplorer + RuntimeJobsPanel + JobsBridge(JobRunner→Qt) + i18n(한/영) + 상태바 |
| Function UX Effect | 모델/시나리오/실행 트리·실 job 상태 표·중앙 위젯 도킹 |
| Core Value | service(Qt 비의존) 실 소비·offscreen 검증(G-7b 별도 carry). §11 셸 토대 |
## Success Criteria
AP1 3-pane 생성 · AP2 i18n · AP3 explorer · AP4 JobRunner bridge 실 상태 · AP5 중앙 교체 · AP6 상태바.
