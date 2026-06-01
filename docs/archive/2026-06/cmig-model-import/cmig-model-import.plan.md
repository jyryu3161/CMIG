# cmig-model-import Planning Document
> Roadmap Phase 0.4 (§11 Model Manager) — SBML/JSON/MAT GEM import.
## Executive Summary
| 관점 | 내용 |
|---|---|
| Problem | 외부 GEM(SBML/JSON/MAT) import + 요약 부재 |
| Solution | io/model_import.py — cobra.io 위임, 확장자 자동 감지, exchange/biomass 탐지 + 카운트 → ModelSummary |
| Function UX Effect | e_coli_core: 95 rxns·72 mets·137 genes·20 exchanges·biomass 탐지. Model Manager 표시용 as_dict |
| Core Value | cobra 위임·미지원/손상 명시 에러(정직). §11 Model Manager 토대 |
## Success Criteria
MI1 SBML · MI2 JSON · MI3 as_dict · MI4 미지원/손상 에러 · MI5 파일 부재.
