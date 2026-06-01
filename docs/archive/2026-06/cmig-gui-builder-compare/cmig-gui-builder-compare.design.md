# cmig-gui-builder-compare Design (Option C)
| gui/builder.py | 신규 | CommunityBuilderView·DeltaTable·ConstraintSandboxView·ScenarioCompareView |
| render/composer.py | 수정 | JOURNAL_PRESETS·PanelSpec.with_journal |
| tests/test_gui_editors_builder.py | 신규(공유) | CB/CS/SC/JP |
## 설계: CommunityBuilder=멤버 표+abundance+tradeoff 슬라이더(0..100→0..1). DeltaTable=DeltaResult(significant 강조·실패 색). Sandbox=bound 표+preview(비기록·significant 수)/commit(run_hash)·debounce QTimer(OD-54). ScenarioCompare=compute_delta 표시+growth Δ. journal preset(nature/cell/science 규격).
