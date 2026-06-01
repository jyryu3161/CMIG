# CMIG — Community Metabolic Interaction GUI

네이티브 데스크톱 커뮤니티 대사 상호작용 분석 도구. community FBA를 **MICOM**(정확 pin·public API only)에
위임하고, CMIG가 **namespace gate · sign 정규화 · tidy 계약 · delta · sandbox · sweep · R 출판 그림**의
부가가치 계층을 소유한다.

- 명세(권위): `CMIG_명세서_v3.0.md` (§1–§11, §16)
- PDCA 문서: `docs/00-pm` · `docs/01-plan` · `docs/02-design`
- 아키텍처: Option C — layered headless `core/` + EngineService facade + 4 SC-driven seams

## 현재 상태 (2026-06)

**headless core + EngineService facade + 기본 GUI shell + fixture/demo CLI 산출 경로.**
`uv run pytest` 기준 전 테스트 green(실 MICOM·R·MILP·FVA·GUI offscreen 포함). `mypy` gate는
프로덕션 소스(`cmig/`) strict 기준이며, `tests/`는 pytest/ruff 대상으로 관리한다.

구현됨:
- `core/sign·namespace(gate)·tidy·manifest(run_hash 11)·solver` — 순수 로직 + 계약.
- `core/engine`(실 MICOM cooperative_tradeoff) · `core/interactions·delta·sandbox·sweep·medium_spec·targets·metrics·fva` · `core/diagnostics`(구조화 {code,message,detail} — **engine/delta/sandbox/sweep 전면 적용**).
- `core/single_model·pair·matrix·dfba·host·host_impact·search·search_advanced·search_ga·stats·stats_embed` — v3.0 extension의 구현 가능분. host는 synthetic toy coupling + generic human GEM(Recon3D/Human-GEM style) smoke solve를 분리.
- `io/solve_output` + **`cmig solve-fixture --solver --out`** 및 **`cmig solve --taxonomy [--medium] --solver --tradeoff-f --out`** → nodes/edges/profile.parquet + manifest.json(run_hash). medium 입력은 `medium_presets/`(csv) 또는 사용자 csv/json.
- `targets`(SCFA target readout) · `render/`(R ggplot2 SVG/TIFF, composer; 논문용 font/palette/line style) · `gui/`(app shell·Cytoscape graph·tables, offscreen 실행 검증).

**Solver (F1: full-flux metadata)**:
- `gurobi` = canonical full-flux(QP+LP 모두 Gurobi → `flux_report_status='full'`).
- `osqp` = optlang hybrid 경로(QP는 OSQP, LP pFBA flux는 HiGHS →
  `flux_report_status='full'`, `flux_solver='highs'`).
- 별도 `osqp_growth_highs_flux` solver 이름은 폐기됨 — `osqp` alias 자체가 optlang hybrid다.

범위:
- 현재 제품 범위는 사용자가 직접 제공하는 SBML/JSON/MAT 모델과 MICOM 호환 taxonomy csv를 입력받는 방식이다. 외부 모델 카탈로그를 자동으로 가져오거나 큐레이션하지 않는다.

아직 미구현(후속):
- **실 Human-GEM/Recon host 정량 coupling 검증** — 현재 host-microbe coupling은 synthetic toy + 실 MICOM 분비 wiring 검증, generic human GEM은 사용자가 제공한 모델의 smoke solve로 검증.
- **사람 시각 QA(G-7b)** — GUI는 offscreen 실행 증거까지 자동화.

## 개발 (uv)

```bash
uv sync --extra engine --extra render --extra gui   # 전체 stack
uv run pytest                                       # 전 테스트 (실 MICOM·R·FVA·GUI offscreen)
uv run ruff check . && uv run mypy cmig
uv run cmig solvers                                 # solver capability matrix
uv run cmig solve-fixture --solver gurobi --out out/  # 고정 fixture solve → parquet + manifest
uv run cmig solve --taxonomy tax.csv --medium medium_presets/western_diet.csv --out out/  # 사용자 입력
uv run cmig host-fixture --out out/                 # synthetic host-microbe smoke
uv run cmig model-review --model /path/to/model.xml --out out/  # user-provided GEM review
uv run cmig host-generic --model /path/to/Recon3D.xml --out out/  # generic human GEM smoke
uv run cmig dfba-fixture --out out/                 # e_coli_core dFBA timecourse
uv run cmig search-fixture --out out/               # 3-member target-max search
uv run cmig stats-demo --out out/                   # stats/FDR demo
uv run cmig golden verify                           # MICOM-version golden gate (SC-5)
```

`Recon3D.xml` 같은 대용량 외부 GEM은 git에 포함하지 않는다. 로컬 검증은 사용자가 직접 경로를
지정해 수행한다. 테스트 편의를 위해 `CMIG_RECON3D_PATH=/path/to/Recon3D.xml`를 설정할 수 있으며,
파일이 없으면 Recon3D smoke tests는 skip된다.

## Success Criteria
SC-1~9(golden·MICOM regression·OSQP→LP tolerance·sign·gate·tidy·재현)은 `tests/`로 검증되며,
hardening cycle에서 SC-H1~6(GUI 실행·E2E·적대리뷰·FVA 등)이 추가로 통과한다. 상세는
`docs/archive/`의 각 사이클 report 참조.
