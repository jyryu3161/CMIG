# cmig-gui-views Planning Document
> Roadmap Phase 2 (§11) — Sweep View + External Profile Viewer (인터랙티브 뷰 1차 슬라이스).
## Executive Summary
| Problem | sweep 결과·external profile 인터랙티브 뷰 부재 |
| Solution | gui/views.py — SweepView(JobRunner+make_sweep_job 실 sweep·cache-hit) + ExternalProfileView(net flux·sign 색·FVA·target) |
| Function UX Effect | 축 정의→비차단 sweep→결과 매트릭스, profile 표(diverging 색·FVA 범위·target 요약) |
| Core Value | 실 backend 소비(JobRunner sweep·sign/FVA/target)·테이블 기반 offscreen 클린 검증·G-7b carry |
## Success Criteria
GV1 실 sweep · GV2 cache-hit · GV3 실패 row · GV4 sign+FVA · GV5 target · GV6 빈 안전.
## Carry-over: Community Builder+Sandbox(drag·debounce)·Scenario Compare(delta network)·QWebEngine 차트.
