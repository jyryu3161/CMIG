# cmig-gui-views Design (Option C)
| gui/views.py | 신규 | SweepView(JobRunner sweep·결과 매트릭스)·ExternalProfileView(profile·sign·FVA·target) |
| tests/test_gui_views.py | 신규 | 6 (offscreen) |
## 설계
- 테이블 기반(QWebEngine 비의존 → offscreen 클린). SweepView.run_sweep=make_sweep_job→runner.submit(실 wiring). load_results(cache_hit·failed 색). ExternalProfileView.load_profile(sign 색 _LABEL_COLOR·FVA [lo,hi])·load_targets.
