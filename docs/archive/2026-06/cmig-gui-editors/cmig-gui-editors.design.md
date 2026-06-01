# cmig-gui-editors Design (Option C)
| gui/editors.py | 신규 | MediumEditor(load_spec/to_spec·add_row) + ModelManagerPanel(load_summary) |
| tests/test_gui_editors_builder.py | 신규(공유) | ME/MM 케이스 |
## 설계: MediumEditor 표(exchange·uptake_limit)→MediumSpec(validate). ModelManagerPanel=ModelSummary 카운트 label+exchange table+biomass. 검증 실패→ValueError+status(silent 위장 금지). offscreen.
