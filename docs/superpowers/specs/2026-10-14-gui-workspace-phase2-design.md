# GUI 작업 공간 개편 2단계 설계 — 분석 화면 분리·모델 브라우저·전역 검색·결과 표시

작성 2026-10-14. 대상: `cmig/gui/`, `cmig/io/project.py`, 새 `cmig/io/model_index.py`. 선행: 1단계(`docs/superpowers/specs/2026-10-13-gui-workspace-phase1-design.md`, main `d6a1d31`).

참고 자료:
- Apple HIG "Designing for macOS": 사이드바, 툴바 검색 칸, 펼침 단추, 상태 표시, 키보드 조작
- CNApy 1.2.8: REA로 실제 창을 캡처하고 조작해 확인(2026-10-13)
  - 가져올 점: 목록+상세 모델 보기, 입력 즉시 걸러지는 검색, 입력값과 계산값의 색 구분, 마지막 결과를 알려 주는 상태 표시줄, 짧은 분석 창
  - 피할 점: 비표준 메뉴, 글자 없는 아이콘 툴바, 화면을 차지하는 빈 지도와 콘솔, 계산 중 멈춤, 프로젝트당 모델 하나

## 1. 목적

연구자가 분석마다 필요한 입력만 보고 실행하고, 가져온 모델의 내용과 성장 여부를 바로 확인하며, 프로젝트 안의 무엇이든 찾아 열 수 있게 한다.

현재 문제(2026-10-13 REA로 캡처한 실제 창, 1500×950, BiGG 모델 3개 프로젝트):
- Combination Search 화면 한 스크롤에 Search·Gene KO·Strain Growth·Ratio Impact 입력이 섞여 있다. 사이드바의 Gene Knockout과 Strain Growth & Ratio는 같은 화면의 다른 위치로 스크롤만 한다.
- Community Solve 화면에 멤버 입력이 두 곳이다. 선택기는 "Members: 3 selected"인데, 그 아래 Member/Abundance 표는 비어 있고 "Add member"로 id를 직접 입력하게 한다.
- Host–Microbe 화면은 실행 전부터 빈 결과 표 3개가 화면 절반을 차지하고, 열 머리글이 잘린다.
- 모델 표의 Check 열은 세 모델 모두 "warning"이라고만 쓴다. 실제 이유는 namespace를 아직 검토하지 않았다는 것이다.
- 상세 패널의 "BiGG namespace coverage 0.0%"는 검토를 마친 매핑의 비율이다. 그래서 BiGG 모델도 검토 전에는 0%로 나와, BiGG가 아닌 것처럼 읽힌다.
- iAF987의 목적함수(283개 항)를 "Biomass:" 아래 전부 늘어놓는다. 그 때문에 경고와 파일 정보가 화면 밖으로 밀린다. A-B9에서 다중 항 목적함수를 biomass로 부르지 않기로 한 규칙과도 어긋난다.
- 가져온 모델의 반응·대사체·유전자를 볼 방법이 없다. 상세 패널에는 exchange 목록만 있다.
- 모델이 자라는지 확인하려면 Medium Editor에서 커뮤니티 solve를 돌려야 한다.
- 프로젝트 전체를 찾는 기능이 없다.
- 모든 표 왼쪽에 행 번호가 보인다. 아무것도 고르지 않았을 때 상세 패널은 "Nothing selected"와 꺼진 버튼만 보이며 화면 폭의 약 1/5을 차지한다.
- 다중 모델 선택기는 키보드로 조작할 수 없다(1단계에서 남은 문제).

성공 기준:
- 모든 분석 화면은 필수 입력 2–5개와 Run이 첫 화면에 보이고, 나머지 설정은 펼침 단추 아래에 있다.
- 같은 입력이면 화면을 나누기 전과 똑같은 CLI 인자가 나온다.
- 모델을 고르면 반응·대사체·유전자·exchange를 찾아 볼 수 있다. Check Growth 한 번으로 성장 여부를 볼 수 있다.
- ⌘F 한 번으로 모델, 반응, 대사체, 배지, 실행 기록을 찾아 연다.
- RUNS에서 지난 실행을 열면 그 분석 화면에 결과와 입력이 함께 돌아온다.
- 1280×800과 1500×950 창, 밝은 모드와 어두운 모드에서 잘리거나 겹치는 화면이 없다.

## 2. 범위

포함:
- 분석 화면 분리와 공통 화면 구조(입력 카드, Advanced, 결과 영역)
- 실행 입력 기록과 RUNS에서 입력 복원
- 모델 표의 점검 이유, 모델 브라우저, 모델 색인
- Check Growth와 모델별 namespace 확인 기록
- 전역 검색(⌘F)
- 결과 표시: 상태 표시줄의 마지막 실행, 계산값 강조, 행 번호 숨김, 빈 결과 상태, 선택 없음일 때의 상세 패널
- 키보드로 조작할 수 있는 선택기
- 1단계 보류 항목 세 가지: 제거한 id로 이름 바꾸기, 실행 기록 hash 계산과 AGORA2 카탈로그 조회의 백그라운드 이동, Host 표 머리글 잘림

제외:
- 3단계로 넘김: 결과 화면 통합, Compare 개편, 그림 개선
- 넣지 않음: 모델 편집(bounds, 반응 추가), 대사 지도, 검색 기록, 한국어 번역(중단 유지)
- 기록만 함: 접근성 '누름'(AXPress)으로 사이드바 항목이 선택되지 않는 문제를 `docs/tracking/findings.md`에 적는다. 마우스와 키보드로는 정상이다.
- CLI 옵션·hash·manifest·tidy 스키마 변경. 기능 때문에 CLI를 바꿔야 하는 일이 생기면 이번에는 하지 않고 findings에 기록한다.

## 3. 화면 목록과 사이드바

분석 하나에 화면 하나를 둔다. 사이드바 ANALYSES와 Analysis 메뉴는 구분선으로 네 묶음을 나눈다. 사이드바는 2단계 깊이를 유지한다.

| 묶음 | 화면(키) | CLI |
|---|---|---|
| Community | Combination Search(`search`) · Gene Knockout(`gene_ko`) · Strain Growth(`strain_growth`) · Ratio Impact(`ratio_impact`) · Community Solve(`community`) | `search` · `gene-ko-search` · `strain-growth` · `abundance-impact` · `solve` |
| Host | Host–Microbe(`host`) · Host Combination Search(`host_search`) | `host-microbe-bigg` · `host-search-bigg` |
| Dynamics | dFBA(`dfba`) · Spatial Preview(`spatial`) | `dfba` · `spatial-preview` |
| Tools | Medium Editor(`medium`) · Sweep(`sweep`) · Constraint Sandbox(`sandbox`) · Compare Runs(`compare`) | 지금과 같음 |

- 툴바의 Run(⌘R)은 지금 화면의 Run 버튼과 같은 동작이다. 그 버튼이 꺼져 있으면 Run도 꺼진다(1단계 규칙 유지).
- 1단계 프로젝트의 `analysis_settings`는 열 때 새 키로 옮긴다:
  - `growth` → `strain_growth`, `ratio_impact`
  - `dynamics` → `dfba`, `spatial`
  - `host` → `host`, `host_search`
  - 옮긴 뒤 저장할 때 옛 키는 쓰지 않는다.

## 4. 분석 화면 구조

모든 분석 화면은 같은 틀을 쓴다.

```
┌ <분석 이름> ── 한 줄 설명 ─────────────────────────────┐
│ [입력 카드] 필수 입력 (화면별 2–5개)        [Cancel][▶ Run] │
│ ▸ Advanced options · 3 changed  (기본 접힘)            │
├─ Results ──────────────────────────────────────────────┤
│ ✓ 10:31 · search-20261014-103100 · 12 models · western │
│ 결과 표 / 그림 / 후보 상세                              │
└────────────────────────────────────────────────────────┘
```

화면별 필수 입력. 이 표에 없는 입력은 모두 Advanced 아래에 둔다.

| 화면 | 필수 입력 | Advanced |
|---|---|---|
| Combination Search | 모델, 배지, 타깃 표(Add·Remove·Fill from preset. 2행 이상이면 Multi-target metric), 크기 범위 | 전략, Top K, FVA, seed, workers, growth fraction, 멤버 성장 하한, 커뮤니티 성장 하한, Validate top, solve timeout, checkpoint·resume, GA 공통 멤버 보존, 배지 모드, unknown 배지 허용 |
| Gene Knockout | 모델, 배지, 고정 조합 멤버, 타깃과 방향, 편집 멤버(선택) | 유전자 id, 멤버당 최대 유전자 수, KO Top K, growth fraction |
| Strain Growth | 모델, 배지 | cooperative tradeoff f |
| Ratio Impact | 모델, 배지, 비율을 바꿀 멤버, 비율 목록, 타깃 | cooperative tradeoff f |
| Community Solve | 멤버 표(선택기에서 고른 멤버가 곧 행. abundance만 고침), namespace 확인 | tradeoff f |
| Host–Microbe | 숙주, 미생물, 숙주 배지, 미생물 배지, biomass 기준(종류·출처·미생물 gDW·숙주 gDW) | 숙주 목적함수, tradeoff f, 숙주 흡수 유지, currency 대사체, unknown 배지 허용 |
| Host Combination Search | 숙주, 미생물, 배지 두 개, 타깃, 지표, 크기 범위, biomass 기준 | Host–Microbe와 같은 항목 |
| dFBA | 모델, 초기값, 종료 시간 | dt, 초기 biomass, 추적하지 않는 흡수 닫기 |
| Spatial Preview | 대사체, 격자 크기, 단계 수 | dt, 확산 계수, source, sink |
| Tools 화면 | 지금 입력을 같은 틀로 정리. 기능은 바꾸지 않는다 | 화면별 |

입력 카드와 Advanced:
- **값과 의미는 지금과 같다.** 기본값은 CLI 기본값이고, 화면에 보이는 위치만 바뀐다.
- **Gene Knockout과 Ratio Impact의 타깃은 각 화면의 입력이다.** 지금은 Search 타깃 표의 한 행을 빌려 쓴다.
- **멤버를 id로 직접 입력하던 칸은 선택기로 바꾼다.** 넘기는 인자 값의 형식(구분자 포함)은 지금과 같다.
  - Gene Knockout 고정 조합(`--members`): 그 화면에서 고른 모델 중에서 여러 개를 고른다.
  - Gene Knockout 편집 멤버(`--member`): 고정 조합 중에서 하나를 고르거나 "All members"(지금의 빈칸)를 고른다.
  - Ratio Impact 멤버: 그 화면에서 고른 모델 중에서 하나를 고른다.
- **Community Solve 멤버 표:**
  - 선택기에서 모델을 고르거나 빼면 표의 행이 따라 바뀐다.
  - 직접 id를 입력하는 행과 "Add member", "Remove selected" 단추는 없앤다.
  - abundance를 고친 멤버를 선택에서 뺐다가 다시 넣으면 abundance는 기본값 1로 돌아간다.
- **Advanced가 접혀 있어도 기본값과 다른 설정의 개수를 보인다.** 예: "Advanced options · 3 changed". 숨은 설정이 결과를 바꾸고 있다는 것을 놓치지 않게 한다.
- **Run을 누르면** Run이 꺼지고 Cancel이 켜진다. 취소 중 표시는 1단계 규칙을 따른다.

결과 영역:
- **결과가 없을 때**는 "No results yet — set the inputs above and press Run." 한 줄만 보인다. 결과 표와 그림은 결과가 생기면 나타난다.
- **결과가 생기면** 상태 줄을 보인다: ✓/⚠/✗/⊘, 끝난 시각, run 이름, 주요 입력 요약.
- **입력을 바꾸면** 지금의 무효화 규칙을 그대로 따른다("Inputs changed — run again").
- **기존 결과 위젯은 그대로 이 영역에 옮긴다**: Search 순위 표·Pareto·후보 상세, Host 표·네트워크, dFBA 표·그림.
- **Community Solve 결과**: 지금 별도 화면인 Profile | Graph가 이 영역으로 들어온다.
- **모든 표의 행 번호(세로 머리글)를 숨긴다.** 분석 화면 밖의 표도 포함한다.
- **창이 작을 때** 화면 전체가 세로로 스크롤된다. 입력 카드 안의 입력칸은 잘리지 않고 여러 줄로 배치된다.

### 실행 입력 기록과 복원

- **실행을 시작할 때** 화면 입력값을 `runs/_inputs/<run>-request.json`에 원자적으로 쓴다.
  - 내용: `schema_version: 1`, `analysis`(화면 키), `values`(입력 이름 → 값), `models`(고른 모델 id), `media`(배지 참조), `created`, `cmig_version`.
  - CLI 산출물에는 손대지 않는다.
  - 쓰기에 실패하면 taxonomy를 쓰지 못했을 때처럼 실행을 거부하고 사유를 보인다.
- **RUNS에서 실행을 열면:**
  - `analysis`의 화면이 열리고, 결과 영역에 그 결과가 나오며, 입력 카드와 Advanced가 그 실행의 값으로 채워진다.
  - 복원한 입력은 결과와 같으므로 결과를 무효로 표시하지 않는다.
  - 화면 위 배너에 "Inputs restored from <run>"을 보인다.
- **기록이 없는 실행:**
  - 1단계 실행이나 Open Run…으로 연 실행이 여기에 해당한다.
  - manifest의 `workflow_kind`로 화면을 고르고 입력은 그대로 둔다. 배너에는 "Inputs for this run cannot be restored"를 보인다.
  - 맞는 화면이 없는 종류는 지금처럼 결과와 상세 패널만 보인다.
- **지금은 고를 수 없는 값:** 기록에는 있지만 이제 고를 수 없는 값(삭제된 모델·배지, checksum이 바뀐 모델)은 빼고 복원하며, 무엇을 뺐는지 배너에 적는다.
- **지금 입력은 덮어쓴다.** 복원하면 그 화면의 현재 입력을 대체하며, 되돌리기는 없다.

## 5. 모델 표·모델 브라우저·색인

모델 표(사이드바 MODELS 머리글 선택):
- Check 열에 짧은 이유를 보인다. 여러 이유가 겹치면 가장 나쁜 것 하나를 보이고, 나머지는 도움말 풍선에 넣는다.

| 표시 | 조건 |
|---|---|
| `✗ Unreadable` | 점검 `failed` |
| `⚠ File changed` / `⚠ File missing` | `integrity`가 `changed` / `missing` |
| `⚠ Namespace not reviewed` | namespace 검토가 막힘이고, 모델별 확인이 없음 |
| `⚠ No objective` | 목적함수 항 없음 |
| `⚠ Objective is not growth` | `objective_structure_warning`이 경고함(다중 항, demand·exchange 단일 항 등) |
| `✓ Ready` | 위에 해당 없음. 모델별 확인이 있으면 `✓ Ready · namespace confirmed` |

- **점검 결과에 구조화된 값을 새로 기록한다**:
  - `namespace_mappings`: `{total, resolved, unresolved_high, warned_low}`
  - `objective_warning`: `objective_structure_warning`의 문구 또는 null
- **1단계 항목에는 이 값이 없다.** 그래서 `build_import_review`가 쓴 경고 문구에서 한 번 읽어 낸다. 다시 점검하지는 않는다.

모델 브라우저(사이드바에서 모델 하나 선택):
```
┌ iAF987 · 1285 reactions · 1109 metabolites · 987 genes   [Medium ▾] [Check Growth] ┐
│ ⚠ Namespace not reviewed — needed before community analyses   [Confirm…]          │
│ Objective: 283 terms — not a single biomass reaction ▸                             │
│ Growth: not checked yet                                                            │
├ [Reactions] [Metabolites] [Genes] [Exchanges]          🔍 filter                   ┤
│ 목록: id · name · (반응) bounds · subsystem                                          │
├────────────────────────────────────────────────────────────────────────────────────┤
│ 상세: 반응 = 이름으로 쓴 식, bounds, GPR, subsystem / 대사체 = formula, charge,      │
│       compartment, 관련 반응 / 유전자 = 관련 반응 / exchange = bounds                │
└────────────────────────────────────────────────────────────────────────────────────┘
```
- **읽기 전용이다.** 모델 사본을 수정하지 않는다.
- **필터**: 입력하는 즉시 id와 이름에서 대소문자 구분 없이 부분 일치로 찾는다. 반응은 식에서도 찾는다.
- **상세 이동**: 상세에서 관련 반응·대사체를 누르면 해당 탭의 그 항목으로 이동한다.
- **목적함수 표시**:
  - 1개 항이고 `objective_structure_warning`이 없을 때: `Objective: <id> (biomass)`
  - 그 밖의 경우: 항 개수와 경고 문구를 보이고, 목록은 펼침 단추 아래에 둔다.
  - "Biomass" 라벨은 첫 번째 경우에만 쓴다.
- **namespace 표시**:
  - "BiGG namespace coverage" 대신 `Namespace mappings: 0 of 95 reviewed`와 상태 문구를 보인다.
  - 상태 문구는 `Not reviewed — needed before community analyses`, `Confirmed by you · 2026-10-14`, `Changed since confirmed` 중 하나다.
- **오른쪽 상세 패널**: 파일 정보(checksum, 원본, 형식, integrity)와 경고 전문만 보인다. exchange 목록은 브라우저의 Exchanges 탭으로 옮긴다.
- **아무것도 고르지 않았을 때 상세 패널**: 프로젝트 요약(모델·배지·실행 수, 마지막 실행의 상태)을 보인다.

모델 색인(`cmig/io/model_index.py`, Qt 없음):
- **위치**: `models/.index/<sha256>.json`. `schema_version: 1`, `sha256`, `model_id`를 둔다.
- **내용**:
  - `reactions[]`: `id`, `name`, `metabolites{id: coef}`, `lower`, `upper`, `gpr`, `subsystem`
  - `metabolites[]`: `id`, `name`, `formula`, `charge`, `compartment`
  - `genes[]`: `id`, `name`, `reactions[]`
  - `exchanges[]`, `objective[]`(`id`, `coef`)
- **만드는 시점**:
  - 모델을 가져올 때 점검과 같은 읽기에서 만든다. 파일을 한 번만 읽는다.
  - 프로젝트를 열었을 때 색인이 없거나, 깨졌거나, schema가 다르거나, sha256이 다르면 백그라운드 작업 하나로 다시 만든다.
  - 작업 창에 "Index models 3/12"처럼 진행이 보이고 취소할 수 있다.
- **쓰기**: 원자적으로 쓴다. 읽을 수 없는 색인은 지우지 않고 덮어 다시 만든다.
- **용도**: 브라우저와 검색에만 쓴다. 분석 입력, taxonomy, CLI 인자에는 쓰지 않는다.
- **모델을 프로젝트에서 제거해도 색인은 남긴다.** 되돌리기를 하면 다시 쓰이기 때문이다.

## 6. Check Growth와 모델별 namespace 확인

Check Growth(모델 브라우저 머리글):
- **입력**:
  - 배지 선택기: 기본값은 "Model default (no medium file)"이다. 배지를 고르면 exact로 적용하고 머리글에 "(exact)"를 붙인다.
  - "Skip medium metabolites this model lacks" 체크 상자: 기본은 꺼짐이다. 켜면 `--allow-unknown-medium`을 넘긴다. 꺼져 있을 때 CLI가 대응 없는 대사체로 거부하면, 머리글에 그 개수와 이 상자를 켜라는 안내를 보인다.
- **실행**:
  - `cmig single --model <사본 절대 경로> --fba --out runs/check-growth-YYYYMMDD-HHMMSS[-N] [--medium <경로> --exact-medium] [--allow-unknown-medium] --assume-bigg-namespace`
  - 기존 작업 실행기로만 실행한다. `--solver`는 넘기지 않는다(CLI 기본값).
  - request.json의 `analysis`는 `check_growth`이고 `models`는 그 모델 하나다.
- **namespace가 확인되지 않은 모델**은 GUI가 실행을 거부한다. 사유와 [Confirm…]을 보이며, CLI가 거부할 때와 같은 판단이다.
- **결과 읽기**: `single_summary.json`과 기존 inspect 판독을 쓴다.

| 조건 | 머리글 |
|---|---|
| FBA `optimal`, `growth_feasible` 참, 목적함수가 성장 | `✓ Growth 0.874 h⁻¹ · Gurobi (full-flux) · western_diet (exact) · 10:31` |
| 위와 같지만 목적함수가 성장이 아님(5절) | `✓ Objective value 12.3 · <경고 문구> · …` |
| FBA `optimal`, `growth_feasible` 거짓 | `✗ No growth (below 1e-06) · …` |
| FBA 상태가 `optimal`이 아님 | `✗ <상태>, 예: Infeasible · …` |
| CLI 실패, 판독 실패, 무결성 불일치 | `✗ Failed: <사유 첫 줄>` |
| 취소 | `⊘ Cancelled` |
| 요약 상태 `degraded` | 앞에 ⚠를 붙이고 경고(뺀 배지 대사체 등)를 펼침 아래에 둔다 |

- **솔버 표기**는 요약의 `solver`를 따른다: `gurobi` → "Gurobi (full-flux)", `osqp` → "OSQP (QP-only approximate)".
- **머리글의 Growth 줄**은 이 모델(같은 sha256)의 가장 최근 Check Growth 실행에서 읽는다. 앱을 다시 켜도 RUNS에서 다시 찾는다. 해당하는 실행이 없으면 "not checked yet"이다.
- **RUNS 표시**는 "Check Growth · iAF987 · 10:31"이다. 열면 그 모델의 브라우저가 열리고 머리글에 그 실행 결과가 보인다. 모델이 프로젝트에서 빠졌으면 결과와 상세 패널만 보인다.

모델별 namespace 확인:
- **확인하기**:
  - 브라우저의 [Confirm…]을 누르면 시트가 열린다. 문구: "I reviewed this model; its exchange ids already use the BiGG namespace."
  - 확인하면 모델 항목에 `namespace_confirmed: {sha256, at}`을 기록한다. Edit > Undo로 되돌릴 수 있다("Undo Confirm Namespace").
  - [Revoke]로 취소할 수 있다.
- **유효 조건**: `sha256`이 지금 파일과 같고 `integrity`가 `ok`일 때만 유효하다. 파일이 바뀌면 "Changed since confirmed"로 보이고 확인되지 않은 것으로 다룬다.
- **Check Growth**에는 확인란이 없다. 그 모델의 확인 기록만 보고 실행 여부를 정한다(위 거부 규칙).
- **확인란이 있는 분석**: Community Solve, Medium Editor(성장 확인·minimal medium).
  - 고른 모델이 모두 확인되어 있으면 "already BiGG" 확인란이 체크된 채 시작한다. 옆에 "All 3 models confirmed in this project"를 적는다.
  - 하나라도 확인되지 않았으면 비운 채 시작하고 "iYO844 not confirmed"처럼 적는다.
  - 사용자가 직접 체크하거나 해제한 상태는 모델 선택이 바뀔 때까지 유지한다. 선택이 바뀌면 다시 계산한다.
- **CLI 인자**는 사용자가 직접 체크했을 때와 똑같은 `--assume-bigg-namespace`다. hash 계약은 바뀌지 않는다.

## 7. 전역 검색(⌘F)

- **위치**: 툴바 오른쪽 검색 칸(자리표시 "Search project")이다. Edit > Find… ⌘F를 누르면 이 칸으로 이동한다.
- **찾는 대상**:
  - 모델 id·파일 이름
  - 색인의 반응·대사체·유전자 id와 이름, exchange id
  - 배지 이름과 배지에 든 exchange id
  - 실행 이름·분석 종류·상태
- **찾는 방식**:
  - 2글자 이상에서 시작한다. 대소문자는 구분하지 않는다.
  - 순서: id 완전 일치 → id 앞부분 일치 → 그 밖의 부분 일치. 같은 순위 안에서는 id 순이다.
- **결과 목록**:
  - 칸 아래 목록이 입력하는 즉시 열린다.
  - Models / Reactions / Metabolites / Genes / Media / Runs로 묶고, 묶음마다 최대 8줄이다. 넘치면 "+37 more — refine the search" 한 줄을 보인다.
  - 같은 항목이 여러 모델에 있으면 모델마다 한 줄이다. 예: `glc__D_e · iAF987`.
  - 색인을 만드는 중인 모델이 있으면 끝에 "2 models still indexing"을 보인다.
- **결과를 고르면**:
  - 모델: 브라우저로 간다.
  - 반응·대사체·유전자: 그 모델 브라우저의 해당 탭에서 그 항목이 선택된다.
  - 배지: 배지 상세로 간다.
  - 실행: 4절의 복원으로 연다.
- **키보드**: 칸에 포커스가 있는 동안 ↑/↓로 결과를 옮기고, Return으로 열고, Esc로 목록을 닫는다. 목록이 닫힌 상태에서 Esc를 누르면 칸을 비운다.
- **메모리**: 검색 표는 `(종류, id)`마다 이름과 그 항목이 있는 모델 id 목록 하나만 둔다. AGORA2처럼 모델이 많아도 같은 대사체를 모델 수만큼 반복해 담지 않는다. 색인을 다 읽어 들이지 않고 이 표만 메모리에 둔다.
- **검색 기록은 두지 않는다.**

## 8. 결과 표시

- **상태 표시줄 왼쪽**: 마지막으로 끝난 실행을 보인다.
  - 예: `✓ Community Solve · community-20261014-103100 · Gurobi (full-flux)`
  - degraded는 ⚠, 실패는 ✗와 사유 첫 줄, 취소는 ⊘로 보인다. 누르면 그 실행을 연다.
  - 숫자 요약은 넣지 않는다. 숫자는 결과 영역과 Check Growth 머리글에서만 보인다.
  - 잠깐 보이는 안내 문구가 나오는 동안에는 가려지고, 안내 문구가 사라지면 다시 보인다.
- **입력값과 계산값의 구분**: 적용 범위는 분석 화면 결과 표, Community 표, Host 표, dFBA 표, Sandbox 표다. Compare는 3단계에서 다룬다.
  - 입력을 되풀이한 열(abundance, 배지 한도, 고정한 제약)은 기본 글자색이다.
  - 계산된 열(flux, growth, score, 전달량)은 시스템 강조색으로 쓰고, 열 머리글 도움말에 "Computed by CMIG"라고 적는다.
  - 밝은 모드와 어두운 모드 모두 시스템 팔레트를 따른다.
- **실패·평가 불가 행**: 회색 글자에 상태 문구를 보인다. 값처럼 강조하지 않으며 순위 규칙도 지금과 같다(순위에 넣지 않음).
- **flux 표 위 범례**: `+ secretion / − uptake (mmol gDW⁻¹ h⁻¹)`.

## 9. 키보드 선택기와 1단계 보류 항목

다중 모델 선택기:
- **필터 칸과 목록 사이**: 필터 칸에서 ↓나 Tab을 누르면 목록으로 간다. 목록 맨 위에서 ↑를 누르면 필터 칸으로 돌아온다.
- **Space**로 체크를 켜고 끄며, 선택기는 열린 채로 있다.
- **Tab**을 누르면 Select All과 Select None으로 차례로 간다.
- **Return이나 Esc**를 누르면 닫히고, 포커스는 선택기 단추로 돌아온다.
- **하나만 고르는 선택기**는 Return으로 지금 항목을 고르고 닫힌다.

1단계 보류 항목:
- **제거한 모델과 같은 id로 다른 모델 이름을 바꿀 때**: 분석별로 기억된 선택이 그 이름으로 옮겨 가지 않게 한다. 제거된 id를 기억 목록에서 먼저 지운다.
- **실행 기록 hash 계산과 AGORA2 카탈로그 조회**를 화면 스레드 밖으로 옮긴다.
- **Host 표 열 머리글**: 잘리지 않게 줄을 바꾸고, 단위는 도움말 풍선에 넣는다.

## 10. 코드 구조

- **`cmig/gui/analysis_page.py`**: 공통 틀이다.
  - `AnalysisPage`(제목·설명, 입력 카드, Run/Cancel, `AdvancedSection`, `ResultsArea`, 복원 배너)
  - 화면별 `snapshot() -> dict`, `restore(values) -> list[str]`(뺀 값의 설명), `changed_advanced() -> int`
- **`cmig/gui/pages/`**: 화면 하나당 모듈 하나다. 기존 `SearchView`, `HostImpactView`, `DfbaSpatialView`, `CommunityBuilderView`의 위젯과 결과 위젯을 화면별로 나눠 옮긴다. Tools 화면은 기존 위젯을 틀로 감싼다.
- **`cmig/gui/model_browser.py`**: 브라우저와 Check Growth 머리글이다.
- **`cmig/gui/find.py`**: 검색 칸과 결과 목록이다. 맞추기 함수는 Qt 없이 테스트할 수 있게 둔다.
- **`cmig/io/model_index.py`(Qt 없음)**: `build_index(path)`, `write_index(project, entry, index)`, `load_index(project, entry)`(유효하지 않으면 None). `cmig.gui`·`cmig.cli`를 import하지 않는다.
- **`cmig/io/project.py`**:
  - `namespace_confirmed` 필드와 확인·해제·유효 판정
  - 점검의 구조화 값
  - `write_run_request` / `read_run_request`
  - 옛 `analysis_settings` 키 옮기기
- **`app.py`**: 조립, 메뉴, 툴바, 실행 연결만 남긴다.
  - 분석별 argv를 만드는 함수는 화면 위젯 대신 `snapshot()` 값에서 인자를 만든다.
  - 분석은 계속 CLI argv → `JobRunner` → `cmig.cli.main.main`으로만 실행한다.

## 11. 오류 처리

- **색인**: 만들다 실패한 모델은 브라우저에 "Model contents unavailable: <사유>"와 [Retry]를 보인다. 분석에서 고르는 데는 영향이 없다.
- **request.json**: 읽을 수 없거나 형식이 다르면 기록이 없을 때처럼 다루고, 배너에 그 사유를 적는다.
- **Check Growth**: 거부, 실패, 취소는 6절 표대로 보이며, 성공처럼 보이지 않는다.
- **namespace 확인 기록의 저장 실패**: 1단계의 되돌리기 규칙대로 변경을 되돌리고 사유를 보인다.
- **검색 중 색인을 읽을 수 없을 때**: 그 모델을 결과에서 빼고 "1 model could not be searched"를 보인다.

## 12. 검증

- **CLI 인자 동일성**:
  - 화면을 나누기 전에 지금 코드로 분석별 대표 입력의 argv를 기록하는 테스트를 먼저 넣는다.
  - 대상: Search(단일·다중 타깃·Advanced 변경), Gene KO, Strain Growth, Ratio Impact, Community, Host, Host Search, dFBA, Spatial, Medium 성장 확인, Sweep, Sandbox.
  - 나눈 뒤에도 그 테스트가 그대로 통과해야 한다.
- **색인(Qt 없음)**: cobra textbook 모델로 만들고 읽는다. 다음을 확인한다:
  - sha256 변경, 깨진 파일, schema 불일치 때 다시 만든다.
  - 원본 사본이 바뀌지 않는다.
  - argv와 taxonomy에 색인 경로가 나오지 않는다.
- **Check Growth**: 다음을 확인한다:
  - argv
  - 6절 표의 각 상태(`single_summary.json` 가짜 산출물)와 OSQP 표기
  - 미확인 모델의 실행 거부
  - unknown 배지 거부 안내
  - 다시 켠 뒤 최근 결과 표시
- **namespace 확인**: 확인·해제·되돌리기와 파일 변경 후 무효를 확인한다. 분석 확인란이 미리 체크되는 규칙도 확인한다(모두 확인 / 일부 미확인 / 사용자 직접 변경 / 선택 변경).
- **실행 열기**: 복원 왕복, 기록 없음 배너, 삭제된 모델 배너, 복원 뒤 결과가 무효로 표시되지 않는지 확인한다.
- **전역 검색**: 순위, 묶음별 최대 줄 수, 여러 모델 항목, 색인 중 표시, 키보드 이동, 고른 뒤 이동한 화면을 확인한다.
- **키보드 선택기**: QTest 키 입력으로 필터 → 목록 → Space → Select All → Esc를 거쳐 본다.
- **결과 표시**: 계산값 열 강조, 실패 행 비강조, 행 번호 숨김, 빈 결과 상태, 상태 표시줄 마지막 실행과 그것을 눌러 여는 동작을 확인한다.
- **1단계 프로젝트 열기**: 옛 `analysis_settings` 키를 옮기는지, 구조화 값이 없는 모델 항목을 읽는지 확인한다.
- **화면 확인**:
  - 모든 화면을 1280×800과 1500×950에서 offscreen으로 캡처한다.
  - REA로 실제 창을 밝은 모드와 어두운 모드에서 캡처한다.
  - 잘림, 겹침, 빈 공간을 눈으로 확인하고 고친다.
- **최종**: `harness_checks.py --tier quality`, 전체 pytest(Gurobi), `cmig golden verify`, `verify-envelope`.
- **문서**: `docs/USER_GUIDE.md` GUI 절, `CHANGELOG.md`, `docs/tracking/status.md`, `docs/tracking/findings.md`(AXPress), `cmig/gui/AGENTS.md`, `cmig/io/AGENTS.md`.
- **사용자 확인**: 실제 macOS 화면에서 주요 흐름을 확인한다.

## 13. 불변식

- GUI는 계산하지 않는다. CLI 옵션, `run_hash`, envelope, manifest, tidy 스키마, golden은 그대로다.
- 원본 GEM과 프로젝트의 모델 사본은 수정하지 않는다. 프로젝트 폴더 밖에는 쓰지 않는다.
- 실패, 취소, 판독 실패, 성장 없음은 성공이나 0의 성장처럼 보이지 않는다. 다중 항 목적함수 값은 "Growth"로 부르지 않는다.
- namespace 확인은 사용자의 명시적 동작으로만 생긴다. 파일이 바뀌면 무효가 되고, 고른 모델이 모두 확인됐을 때만 미리 체크한다.
- Gurobi는 full-flux, OSQP는 QP-only approximate로 표기한다.
- 프로젝트 형식은 버전 1을 유지하고, 새 항목은 모두 선택 항목이다. 1단계 프로젝트는 그대로 열린다.
- 새 UI 문구는 영어로만 쓴다. `I18N` 새 키는 `en`·`ko`에 같은 영어 문구로 넣는다.
- strict mypy(graph_view 제외), Ruff, pickle 금지, 원자적 쓰기.
