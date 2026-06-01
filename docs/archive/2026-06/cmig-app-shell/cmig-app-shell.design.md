# cmig-app-shell Design (Option C)
| gui/app.py | 신규 | CmigMainWindow·ProjectExplorer·RuntimeJobsPanel·JobsBridge·I18N·build_main_window |
| tests/test_app_shell.py | 신규 | 6 (offscreen) |
## 설계
- QMainWindow + QSplitter 3-pane(explorer|중앙 QStackedWidget|jobs). JobsBridge QTimer 폴링 → RuntimeJobsPanel.refresh(runner.poll). submit_job→runner.submit+track. i18n dict(ko/en). offscreen 검증(QT_QPA_PLATFORM=offscreen).
