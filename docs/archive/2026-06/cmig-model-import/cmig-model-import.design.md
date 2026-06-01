# cmig-model-import Design (Option C)
| io/model_import.py | 신규 | ModelSummary·import_model·_detect_format·_load_cobra_model·_biomass_reactions |
| tests/test_model_import.py | 신규 | 6 (e_coli_core SBML+JSON) |
## 설계
- _detect_format: 확장자(.xml/.sbml/.xml.gz·.json·.mat)→fmt. cobra.io read_sbml/load_json/load_matlab 위임.
- biomass = linear_reaction_coefficients(objective). 파싱 실패/미지원/부재 → ModelImportError(명시).
