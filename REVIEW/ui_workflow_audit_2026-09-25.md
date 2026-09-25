# UI·애플리케이션 워크플로 감사 — 2026-09-25

검토자: GPT-6 Astra UI/workflow review owner. 기준 소스: `c45c836f0c12da04404a712f61f53bec0b346675`. 감사 종료 무렵 다른 worker가 하네스용 AGENTS/CLAUDE·README·CI 등을 추가했고, 새 루트 규칙을 읽어 소유 범위를 유지했다. 아래 애플리케이션 판정은 변경되지 않은 제품 코드와 하네스 추가 전 package/README snapshot을 기준으로 한다. 애플리케이션·테스트·설정·하네스는 수정하지 않았고 commit/push도 수행하지 않았다. 본 보고서와 무시되는 `.run/audit-20260925/`의 검증 산출물만 남겼다. 별도 harness 설계/최종 검토는 이 보고서의 판정 대상이 아니다.

## 판정

**수정이 필요한 확정 결함이 있다.** 우선순위가 높은 것은 AGORA 카탈로그의 출력 경로 이탈, 음수 목적 기여도를 제거하는 다중 타깃 그림, Search 탭의 보이는 배지 설정을 무시하는 인접 분석이다. GUI가 검색 서비스를 실제 호출하고 최신 checkpoint/원자적 게시 기능을 이용하는 것은 확인했지만, 이것이 전체 GUI의 설정·결과 설명·재열기 동등성을 보장하지는 않는다.

P1은 파일 손상 또는 분석 조건/수치의 오해를 유발하는 문제, P2는 주요 사용 흐름·진단·읽기·배포의 결함, P3은 개선 수준으로 사용했다. 실제 생물학적 효능이나 특정 균주의 우월성을 평가하지 않았다. 수치 재현에는 MICOM에 번들된 작은 E. coli core 모델을 사용했으며, 동일 모델의 두 별도 member ID는 UI 검증용이다.

## 근거와 실행 범위

먼저 `docs/USER_GUIDE.md`, `docs/USAGE.md`, `CMIG_명세서_v3.0.md` §11/14 및 baseline/extension 경계, `CHANGELOG.md`, `REVIEW/CMIG_search_implementation_2026-09-05.md`를 읽었다. 과거 보고서는 수정 항목과 범위 확인에만 썼고 결함의 증거는 현 소스/현 실행에서 얻었다.

환경은 macOS arm64, 프로젝트 `.venv`의 Python 3.12.11, PySide6, MICOM 0.39.0이다. 실제 실행에는 Gurobi를 사용했다. HiGHS/OSQP 부재를 가정하지 않았으며 전체 solver 재검증은 coordinator가 담당했다. GUI는 `QT_QPA_PLATFORM=offscreen`, QtWebEngine은 `--disable-gpu --no-sandbox`로 실행했다. 사용자 데스크톱은 조작하지 않았다.

| 범위 | 이번 감사의 직접 근거 | 한계 |
|---|---|---|
| `cmig/gui/app.py`, `__main__.py` | 실제 main window 생성, 모든 기본/고급 탭 캡처, 검색 job/실패/취소, run 열기, 크기 측정 | OS별 native 메뉴·키보드·멀티모니터 수동 QA는 아님 |
| `cmig/gui/builder.py` | Search 실제 summary/그림, 인접 workflow argv, 결과 무효화 코드, UI geometry | 대규모 100행 이상 테이블 성능은 미측정 |
| `cmig/gui/views.py` | 실제 fixture Profile, dFBA load, spatial preview, Sweep 화면 | 실제 전축 sweep 재실행은 하지 않음 |
| `cmig/gui/editors.py` | Medium/Models 구조·preset 로더·import 연결 정적 검토, wheel preset probe | 대형 human GEM import 시간은 미측정 |
| `cmig/gui/host_view.py` | 실제 빈 Host 화면/최소 크기, request와 export 연결 정적 검토 | 새 host 생물학 계산은 실행하지 않음 |
| `cmig/gui/graph_view.py`, `graph_data.py`, assets | 실제 3-member tidy bundle 표시, JS geometry, PNG 확인 | WebEngine 재fit probe가 응답하지 않아 native 그래프 결함으로 확정하지 않음 |
| `cmig/service/search_service.py` | 실제 SearchRequest/Service 경유 single/multi 실행, medium/control/config 전달 검토 | 수천 후보 탐색 throughput 재측정 없음 |
| `cmig/service/jobrunner.py`, `outcome.py` | 실제 failed/cancelled 상태, targeted cancel tests, payload/error 계약 검토 | 장시간 메모리 누수 부하 시험 없음 |
| `cmig/service/engine_service.py`, `store.py` | 실제 `solve_fixture` 산출/읽기, namespace·medium·provenance 연결 및 SQLite 계약 검토 | 모든 facade 분기와 SQLite 장애를 재주입하지 않음 |
| `cmig/service/publication_benchmark.py`, `cmig/cli/publication.py` | 출판 bundle/manifest/error 경계 정적 검토 | 통합 publication benchmark는 coordinator baseline에 의존 |
| `cmig/cli/main.py` | single/multi/mixed-direction search, dfba, spatial, inspect-run 실제 실행; parser와 GUI adapter 비교 | 모든 34 workflow 수치 결과를 독립 재실행한 것은 아님 |
| `cmig/io` 전체 모듈 | AGORA URL/파일 경로 offline probe, model format/cache/path 검토, solve/dfba/quality writer와 transaction/atomic 코드 검토 | 모든 filesystem/OS failure 조합을 재현하지 않음 |
| `cmig/render`, CLI search exporters | 실제 SVG/TIFF 생성·Qt 렌더·음수 기여도 재현, publication sidecar/atomic 경계 검토 | R 전용 모든 패널의 시각 QA는 아님 |
| 문서·패키지·CI | 새 wheel/sdist build, 압축 내용/README 링크 검사, 소스 밖 wheel import/preset 실행, CI YAML 검토 | 원격 CI 실행·release 게시 없음 |

Coordinator의 기존 baseline 기록은 `.run/audit-20260925/baseline-pytest.log`이다. coordinator가 집계한 결과는 **1,537 passed / 1 failed / 18 skipped**이며, 실패는 `tests/test_agora2.py::test_fetch_model_refuses_a_url_outside_the_publisher`이다. 이 실패를 단순 외부 서버 불안정으로 제외하지 않고 아래 F11에서 offline으로 재확인했다. 기존 baseline 전체를 중복 실행하지 않았다.

이번 targeted 실행은 다음 **7개 선택 테스트 통과**이며 `.run/audit-20260925/targeted_tests.log`에 있다. 이 결과를 전체 테스트 통과로 확대하지 않는다.

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q \
  tests/test_run_transaction.py tests/test_jobrunner.py tests/test_gui_editors_builder.py \
  -k 'search or cancel or rollback'
```

## 확정 결함

### F1 · P1 · AGORA 카탈로그 ID가 선택한 출력 폴더 밖의 파일을 덮어쓴다

- **위치:** `cmig/io/agora2.py:263` `read_catalogue`, `:552` 목적 경로 구성, `:556` 직접 write; 일반 변환도 `:569`에서 같은 target을 사용한다.
- **입력/트리거:** `CatalogueEntry(id="../escaped", file="safe.xml", ...)`, `namespace="vmh"`, `file_format="sbml"`; 카탈로그 JSON의 ID도 동일하게 검증 없이 들어온다.
- **기대:** member ID와 파일명을 검증하고 모든 결과를 `out_dir` 내부에만 기록한다.
- **실제:** `selected-models/`에 쓰도록 요청했지만 부모의 `escaped.xml`이 `original user data`에서 `<sbml/>`로 바뀌었다. 반환 provenance에는 단순 `file="escaped.xml"`만 남는다. 정상 네트워크 응답 없이도 재현된다.
- **증거:** `.run/audit-20260925/agora_path_probe.json`; `/tmp/cmig_ui_finalize_evidence.py`의 offline fetcher probe. 다음은 핵심 재현이며 전부 임시 디렉터리 안에서만 실행할 수 있다.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from cmig.io.agora2 import CatalogueEntry, fetch_model
with TemporaryDirectory() as tmp:
    root = Path(tmp)
    victim = root / "escaped.xml"
    victim.write_text("original user data")
    fetch_model(CatalogueEntry("../escaped", "safe.xml", "1M", ""), root / "out",
                namespace="vmh", file_format="sbml", fetcher=lambda _: b"<sbml/>")
    print(victim.read_text())  # <sbml/>
```

- **수정 방향:** 카탈로그 로드/선택 및 fetch 경계에서 ID·파일의 separator, 절대 경로, dot segment를 거부하고, 최종 resolved 경로의 output containment도 검사한다. symlink와 변환용 staging 경로까지 같은 계약을 적용한다.
- **빠진 회귀:** 악의적 cached catalogue의 `../`, 절대 경로, Windows separator, symlink destination에 대해 출력 경계 밖 바이트가 변하지 않는 offline 테스트.

### F2 · P1 · 다중 타깃 그림이 음수 기여도를 0으로 잘라 실제 점수와 달라진다

- **위치:** `cmig/cli/main.py:7978` `_write_multi_target_figure`의 `max(0.0, target_scores[...])`.
- **입력:** 두 core-model singleton, `--targets glc__D,ac --target-directions min_uptake,max_secretion --multi-metric raw_sum --min-size 1 --max-size 1 --strategy exhaustive`.
- **기대/실제:** 실제 LP/JSON은 glucose 기여도 **−10**, acetate **13.358851988**, 총점 **3.358851988**이다. 저장 SVG/TIFF와 GUI는 glucose 막대를 제거하고 acetate **13.36**만 표시한다. 최대화/최소화를 혼합한 목적의 불리한 기여가 사라지므로 비교 그림이 점수를 충실히 표현하지 못한다.
- **증거:** `.run/audit-20260925/mixed/search_summary.json`, `mixed/search_plot.svg`, `mixed_search.log`, `mixed-figure-preview.png`. 실제 MICOM/Gurobi 계산이며 합성 summary를 임의로 주입한 수치가 아니다.
- **재현:** `/tmp/cmig_ui_seed_runs.py`로 `ui_pool.csv`를 만든 후 다음 실행. 그림은 Qt SVG로 직접 열어 확인했다.

```sh
.venv/bin/python -c 'from cmig.cli.main import main; raise SystemExit(main())' search \
  --taxonomy .run/audit-20260925/ui_pool.csv --min-size 1 --max-size 1 \
  --targets glc__D,ac --target-directions min_uptake,max_secretion \
  --multi-metric raw_sum --strategy exhaustive --out /tmp/cmig-mixed-repro
```

- **수정 방향:** 양/음 기여를 별도로 누적하는 diverging plot 또는 signed scatter를 사용하고 총점·단위를 유지한다. 입력 점수 자체를 변경할 필요는 없다.
- **빠진 회귀:** 실제 mixed-direction 결과의 `target_scores` 부호/합과 그림의 bar geometry가 일치하는 검증. 파일 존재 검사만으로는 잡히지 않는다.

### F3 · P1 · Search 탭의 배지/방향 설정을 KO·성장·비율 분석이 조용히 무시한다

- **위치:** `cmig/gui/builder.py:641` `REQUEST_FIELDS`; `cmig/gui/app.py:1922` KO argv, `:1973` strain-growth argv, `:2020` abundance-impact argv.
- **입력:** 같은 Search 탭에서 Medium에 defined medium 경로, Direction=`min_uptake`, Growth fraction=`0.75`를 넣고 `Rank Gene KOs`, `Strain Growth`, `Ratio Impact` 실행.
- **기대:** 적용 대상 설정을 공유하거나 해당 분석에는 적용되지 않는다고 실행 전에 명확히 표시한다. 사용자가 배지 실험으로 이해한 결과가 기본 배지 계산으로 바뀌어서는 안 된다.
- **실제:** 세 CLI argv 모두 `--medium`이 없다. KO/Ratio에는 방향·성장분율도 없다. `REQUEST_FIELDS`에서도 제외되어, 실행 중 medium을 변경해도 해당 결과의 superseded 설명에 잡히지 않는다. 화면에는 같은 입력과 결과표를 공유하며 적용 범위를 알려 주는 표시가 없다.
- **증거:** `ui_functional.json`의 `adjacent_workflow_argv`; `/tmp/cmig_ui_functional_audit.py`가 실제 GUI 메서드와 JobRunner를 실행하고 CLI 경계만 가벼운 recorder로 교체했다. 이 검증은 **요청 전달 증거**이며 세 분석의 새 solver 수치 비교는 아니다.
- **수정 방향:** workflow별 form을 분리하거나, 공유되는 scientific settings를 명시적으로 같은 typed request에 전달한다. 실행된 조건을 결과 헤더에 표시한다.
- **빠진 회귀:** 각 버튼의 비기본 medium·direction·growth fraction 요청 전달 및 실행 중 해당 필드 변경 시 request mismatch 표시.

### F4 · P2 · 기본 창이 1500/1280 화면에 들어가지 않으며 경고가 최소 폭을 더 늘린다

- **위치:** `cmig/gui/host_view.py:80`/`:118`의 긴 단일 run row, `cmig/gui/app.py:916` QTabWidget 구성 및 `:928` splitter, `cmig/gui/builder.py:564` 단일행 status, `:790` 경고 결합.
- **입력:** 표준 `build_main_window()`를 1500×950 또는 1280×800으로 resize/show. 이어 실제 Pareto summary 로드.
- **기대/실제:** 기본 창은 각각 **2045×950**, **2045×823**으로 확대된다. 독립 Search 최소 hint는 **941×718**이나 Host는 **1575×443**이고, 숨겨진 Host의 최소 폭이 탭/좌우 pane을 통해 전체 창에 전파된다. Pareto 첫 경고 문자열이 들어오면 전체 최소 폭이 **2771**로 늘었다. 한국어 shell은 기본 최소 **2045×820**이었다.
- **증거:** `ui_geometry.json`, `ui_functional.json`의 `tab_min_hints`; 아래 시각 QA 목록. `__main__.py:25`의 배포 기본 크기 1500×950이 실제 만족되지 않는다.
- **수정 방향:** form 행을 나누고 긴 설정을 접을 수 있게 하며 tab의 최소 hint가 모든 화면 폭을 고정하지 않도록 스크롤/size policy를 구성한다. 경고는 word-wrap되는 제한 높이 영역/상세 패널로 분리한다.
- **빠진 회귀:** 독립 Search 위젯만이 아니라 모든 탭이 포함된 main window를 두 목표 크기로 표시하고 actual size, 필수 제어의 가시성/입력 폭을 검사한다. 긴 경고·경로·한국어도 포함한다.

### F5 · P2 · 실패 실행의 산출물과 원인 진단이 GUI에서 접근 불가능해진다

- **위치:** `cmig/gui/app.py:1707` 비영 exit를 generic RuntimeError로 축약, `:2653` failed/cancelled completion 분기; `:780` Jobs 표에는 error column/tooltip 없음.
- **입력:** 실제 작은 pool, size=1, target=ac, member growth floor=100. 모든 후보가 baseline_failed가 되는 실행.
- **기대:** 실패 상태를 유지하면서 생성된 manifest, unevaluated 행, 구체적 진단과 출력 경로를 사용자가 열 수 있어야 한다.
- **실제:** CLI는 `search_unevaluated.csv`, `search_evaluations.json`, `manifest.json`과 구체적인 infeasible diagnostic을 남겼다. GUI는 `solver_error: RuntimeError: search failed with rc=3`만 표시하고 표 0행, Explorer run 0개이다. `_search_jobs`에서도 제거하며 화면에는 임시 출력 경로가 없다. 잘못된 입력의 rc=2도 같은 방식으로 원인 문구를 잃는다.
- **증거:** `ui_additional.json`의 `scientific_failure`, `en-failed-search.png`; `/tmp/cmig_ui_additional_audit.py`. 실패 산출물의 원래 임시 경로와 전체 파일 목록/summary를 JSON에 보존했다.
- **수정 방향:** CLI exit와 과학적 status/diagnostic/artifact path를 구조화한 outcome으로 전달하고, 실패 run도 Explorer에 등록한다. 실패 후보를 성공 순위표에 섞지 않는 현재 정책은 유지한다.
- **빠진 회귀:** 실제 rc=3 run이 실패 badge와 artifact path·후보 원인으로 열리는 GUI 테스트; input validation 실패의 actionable message도 확인한다.

### F6 · P2 · GUI Open Run이 저장된 artifact digest 불일치를 알리지 않는다

- **위치:** `cmig/gui/app.py:1402` dFBA 직접 routing, `:1552` `load_dfba_dir` summary-only read; host/spatial/tidy loader에도 공통 integrity preflight가 없다.
- **입력:** 실제 `dfba`를 생성한 뒤 `dfba_summary.json`에 필드를 추가해 기록된 digest를 깨고 CLI/GUI로 각각 읽는다.
- **기대:** GUI도 manifest digest 불일치를 명시하고 검증되지 않은 결과임을 표시한다.
- **실제:** `inspect-run`은 **exit 3, artifact_integrity=mismatch, status=failed**. GUI는 `Loaded dFBA run`, `dFBA loaded ... · 1 warning(s)`로 정상적인 읽기 화면을 제공하며 integrity 경고가 없다. 기존 과학적 warning은 보이지만 파일 변조와는 다른 경고다. GUI가 과학적 성공을 새로 계산했다고 주장하는 결함은 아니고, **읽은 바이트의 검증 상태가 사라지는 결함**이다.
- **증거:** `ui_additional.json`의 `dfba_tampered`, `ui_additional.log`; `dfba/manifest.json`. spatial-preview는 현재 manifest가 없으므로 처음 시행한 spatial tamper probe는 `not_recorded`였고 이 결함의 증거로 쓰지 않았다.
- **수정 방향:** `inspect-run`과 같은 공통 run inspector를 GUI loader 앞에 두고 `mismatch`/`not_recorded`/검증됨을 구분한다.
- **빠진 회귀:** 지원 viewer에 대해 valid digest, 변경 artifact, missing artifact, legacy not-recorded를 각각 열어 UI 표시를 검증한다.

### F7 · P2 · Scatter 선택이 존재하지 않는 그림을 가리켜도 이전 Ranking 그림이 남는다

- **위치:** `cmig/gui/builder.py:738` 고정 mapping, `:746` 없는 artifact이면 그대로 return.
- **입력:** 실제 multi-target/Pareto run을 로드하고 Figure를 Ranking→Scatter로 변경한다.
- **기대:** 지원되는 그림만 선택 가능하거나 빈 화면과 미지원 설명을 표시한다.
- **실제:** `search_scatter.svg`는 이 모드에서 생성되지 않지만 combo는 Scatter, preview는 이전 막대 그림 그대로이다. 이미지 비교도 변경 전후 동일했다. Export는 그때서야 artifact not found를 표시한다.
- **증거:** `ui_functional.json`의 `pareto_scatter`: `artifact_exists=false`, `same_preview=true`. `docs/USER_GUIDE.md:543` 부근은 multi-target에서 scatter 파일이 없음을 정확히 설명한다.
- **수정 방향:** 실제 run의 artifact/metric에 맞게 선택지를 구성하고 없는 artifact 선택 시 preview를 반드시 clear한다.
- **빠진 회귀:** multi-target에서 Scatter 비활성/설명과 missing-file 전환 시 stale preview가 남지 않는 검사. Pareto 2D 구현은 별도 미구현 범위이다.

### F8 · P2 · Search가 첫 경고만 노출하여 Pareto 해석에 필요한 나머지 설명을 숨긴다

- **위치:** `cmig/gui/builder.py:789` `warning_list[0]`만 연결; `:797` 이후 결과 table 구성, `:860`은 frontier 수만 표시.
- **입력:** 실제 `ac,but` Pareto 결과는 4개 warnings를 가진다.
- **기대:** 전체 warnings와 solution semantics/단위/평가·실패 수에 접근할 수 있어야 한다. frontier의 report order를 최고 순위로 오해하지 않도록 설명해야 한다.
- **실제:** 첫 vertex warning만 보이고 나머지 missing exchange, tie, **sampled approximation / rank is reporting order** 경고는 UI에 없다. tooltip도 빈 문자열이다. per-row diagnostic tooltip은 있으나 run-level 경고 전체를 대체하지 않는다. 긴 첫 경고는 F4의 폭 증가도 일으킨다.
- **증거:** `ui_functional.json`의 `pareto.warning_count=4`, `warning_tooltip=""`; `pareto/search_summary.json`; 설정을 맞춘 최종 Pareto PNG.
- **수정 방향:** 요약 badge와 펼칠 수 있는 전체 경고·실행 조건/단위·unevaluated 상세 패널을 제공한다. raw JSON 열기 또는 경로 복사도 최소한 필요하다.
- **빠진 회귀:** 두 번째 이후 warning 및 Pareto ranking caveat가 접근 가능한 텍스트로 남는지 검사한다.

### F9 · P2 · SVG preview가 원래 종횡비를 무시해 축·글자를 늘인다

- **위치:** `cmig/gui/builder.py:574` 기본 `QSvgWidget`; `:749` 바로 load. WebEngine fallback은 `object-fit:contain`이지만 실제 QtSvg 경로에는 대응 설정이 없다.
- **입력:** 실제 Pareto/mixed search SVG를 main window에서 표시한다.
- **기대/실제:** viewBox는 **604.8×259.2 (2.33:1)**인데 실제 preview는 **2283×320 (7.13:1)**로 늘어나고 renderer는 **IgnoreAspectRatio**이다. 표와 달리 제목·축 글씨가 가로로 찌그러진다. Pareto의 긴 score-unit 설명은 저장 그림 자체에서도 x축 양끝 밖으로 나가며, `main.py:7264`의 tight_layout만으로 가로 긴 한 줄이 맞춰지지 않는다.
- **증거:** `final_evidence.log`의 renderer/viewBox/size, `mixed-figure-preview.png`, 최종 Pareto PNG. 이는 widget 실행 여부 검증만으로 발견할 수 없는 시각 결함이다.
- **수정 방향:** QtSvg에서도 aspect ratio를 유지하고 letterbox 영역을 허용한다. 축에는 짧은 단위를 쓰고 Pareto caveat는 별도 caption으로 옮겨 실제 SVG/TIFF의 text bounding box도 검사한다.
- **빠진 회귀:** wide/tall 화면에 동일 SVG를 렌더해 종횡비를 확인하고, 긴 Pareto 단위의 저장 그림 경계 포함 여부를 검사한다.

### F10 · P2 · valid tidy bundle의 손상 manifest를 열면 예외가 GUI 경계를 빠져나간다

- **위치:** `cmig/gui/app.py:1439`의 `json.loads`가 위의 load try/except 밖에 있다.
- **입력:** 정상 `solve_fixture` parquet들이 있는 디렉터리에서 `manifest.json`만 `{broken`으로 바꾸고 `load_run_dir` 실행.
- **기대:** 읽기 실패를 상태에 표시하고 일관되게 이전/빈 화면으로 전환한다.
- **실제:** `JSONDecodeError`가 호출 경계를 빠져나온다. Python 메서드 직접 호출에서 확인했으며, 이것만으로 프로세스 전체가 반드시 종료된다고 단정하지 않는다. native Qt slot에서는 처리되지 않은 예외와 갱신 중단 문제가 된다.
- **증거:** `ui_functional.json`의 `invalid_manifest`; `/tmp/cmig_ui_functional_audit.py`.
- **수정 방향:** manifest parse/schema 검사와 bundle 검증을 하나의 guarded load 단계로 묶고 성공 후에만 UI 상태를 publish한다.
- **빠진 회귀:** malformed JSON, JSON list/null, 필수 필드 누락을 가진 run을 이전 valid run 이후에 여는 GUI 테스트.

### F11 · P2 · AGORA URL allowlist가 dot segment를 허용하고 실제 네트워크에 의존하는 회귀가 있다

- **위치:** `cmig/io/agora2.py:186` `_open_url` raw `startswith`, `:130` `CatalogueEntry.url`, `tests/test_agora2.py:344`.
- **입력:** `.../individual_reconstructions/../../../../etc/passwd`(상위 경로 네 번).
- **기대:** 파일 basename/정규화된 URL path를 검증한 뒤 허용한 publisher resource 경로만 요청한다.
- **실제:** 위 문자열은 검증을 통과하여 `urllib.request.urlopen`까지 전달된다. 정규화된 path는 `/files/reconstructions/etc/passwd`로 허용 prefix `/files/reconstructions/AGORA2/` 밖이다. offline interception에서 직접 확인했다. 여기서 `/etc/passwd`는 **HTTP URL의 경로 문자열**이며 로컬 시스템 파일 읽기가 발생했다는 뜻은 아니다. 같은 fetcher는 redirect의 최종 URL도 검사하지 않는다(이 부분은 정적 검토).
- **증거:** `agora_path_probe.json`의 `escaped_prefix_urlopen`, `normalized_path_inside_allowlist=false`. baseline의 상위 경로 **세 번** 예제는 정규화해도 AGORA2 prefix 내부이며, 그 예제만으로 prefix 이탈을 주장하면 안 된다. 다만 모델 파일명 검증이 없고 실제 외부 서버에 접속한 뒤 HTML을 모델로 파싱하다 테스트가 실패했다. 본 감사는 상위 경로 네 번의 별도 offline 입력으로 실제 prefix 이탈을 검증했다.
- **수정 방향:** scheme/host/path를 파싱·정규화하고 허용 경로/파일명과 redirect 대상에 계약을 적용한다. malformed catalogue는 네트워크 전에 거절한다.
- **빠진 회귀:** urlopen을 반드시 offline으로 가로채어 dot segment, encoded separator, redirect가 네트워크 전에/대상 전환 전에 거절되는지 검증한다. publisher 응답 문구에 의존하지 않는다.

### F12 · P2 · 배포 패키지에 GUI 배지 preset이 없고 sdist README 링크가 끊긴다

- **위치:** `pyproject.toml:83` wheel package 범위와 `:86` sdist include, `cmig/gui/editors.py:71` repo-relative `medium_presets`, `scripts/audit_distribution.py:49` docs allowlist, `README.md:84` tutorial 링크.
- **입력:** 새로 만든 wheel을 `/tmp/cmig-ui-dist-20260925/wheel`에 풀고 소스 밖 cwd/PYTHONPATH에서 `MediumEditor()` 생성.
- **기대:** 배포판의 preset 기능이 필요한 자료를 찾거나 명확한 추가 설치 안내를 제공한다. 포함된 README의 로컬 링크도 유효해야 한다.
- **실제:** preset directory는 존재하지 않고 combo count=1(선택 안내 placeholder뿐)이다. wheel/sdist에 `medium_presets/`가 없다. sdist의 `docs/cmig_hands_on_tutorial.html` 링크도 대상 파일이 없다. 현 distribution audit는 allowlist 검사이므로 이 상태를 통과시킨다.
- **증거:** `distribution_probe.json`, `build.log`; `uv build --out-dir /tmp/cmig-ui-dist-20260925`; 소스 밖 `QT_QPA_PLATFORM=offscreen PYTHONPATH=/tmp/cmig-ui-dist-20260925/wheel .../.venv/bin/python` 실행. graph.html/figure.R는 wheel에 포함됨을 함께 확인했다.
- **수정 방향:** 배포 가능한 preset 자료를 package resource로 포함하고 importlib.resources 등으로 접근하거나, 배포판 지원 범위를 명시한다. tutorial을 포함하거나 source URL로 링크한다.
- **빠진 회귀:** 새 wheel 설치/압축 해제 환경에서 실제 preset 목록을 검사하고 새 sdist 내부 README 링크를 검사한다. checkout에서만 링크 존재를 확인하는 현재 테스트로는 부족하다.

## 기능 동등성과 미구현 범위 — 위의 확정 결함과 별도

| 항목 | 현재 사실 / 분류 | 근거와 후속 기준 |
|---|---|---|
| 타깃별 direction/weight | **UI 미구현, CLI/library 구현**. UI에는 하나의 direction combo만 있어 `ac↑ + 독성분비↓`를 동시에 설정할 수 없다. weight 입력도 없음 | `builder.py:494`, `app.py:1677`; CLI `main.py:10585`/`:10591`. §14의 다중 target row를 실제 UI로 구현하고 target ID와 direction/weight를 함께 저장하는 회귀 필요 |
| 타깃별 threshold | **계획 범위 미구현**. `MultiTargetConfig`에는 사용자 per-target constraint map이 없고 CLI/UI 옵션도 없다. epsilon slice 내부 bounds를 임의 threshold 편집 기능으로 간주하면 안 됨 | `core/search_product.py:833`, 명세 §14 `targets[]{...,constraint}`. 입력 계약부터 설계해야 함 |
| Pareto scatter/trade-off 탐색 | **계획 UI 미구현**. archive는 JSON으로 존재하나 화면은 순위형 stacked bar와 frontier 개수뿐 | `builder.py:860`, `main.py:7961`; 2D actual feasible vector plot, 선택한 점→members/성장 연결, 3+ target projection 의미 표시 필요 |
| Search 설정 parity | medium(exact), seed, GA budget, workers, 성장 하한, timeout, multi metric/scales, validation, checkpoint/resume는 실제 연결됨. `--taxonomy`, recursive scan, target preset/weights/directions, n-samples, GA population/generations/operators/patience, solver threads, Pareto resolution 등은 UI 미노출 | `REQUEST_FIELDS`, `run_search_fixture`, parser 대조. GUI 기본 multi metric=carbon_equivalent, CLI 기본=normalized_weighted; GUI top-k=3, CLI=10, GUI GA cap=500도 다름. 차이를 숨긴 “동일 명령” 재현을 피하고 effective request 내보내기 필요 |
| Search 재열기 | **현재 미지원 및 문서 동등성 주장과 불일치**. live completion에서는 보이는 search를 Open Run/Explorer double click으로 다시 열 수 없음 | `app.py:1412`가 no-viewer를 명시적으로 반환. probe 결과 0행/None. `manifest.kind` 대신 `workflow_kind`를 읽어야 하므로 안내문에도 현재 `unknown` 표시. `docs/USAGE.md:71`의 “and vice versa”를 제한하거나 summary loader 재사용 필요 |
| 파일/path onboarding | Search에 pool Browse만 있고 medium/checkpoint/out 선택은 없음. search output은 OS temp의 무작위 경로이며 save project/run 관리가 없음. Imported model을 search taxonomy로 연결하는 흐름도 없음 | `builder.py:425`, `app.py:1715`, `_search_temp_root`. 현재 제한/개선 항목. model import parse+review가 GUI thread에서 동기 실행되는 것도 대형 GEM 실측이 필요한 성능 개선 후보 |
| 모델 review UI | CLI/library의 model review와 UI는 동등하지 않음. UI는 counts/exchange/“Biomass:” 문자열만 보여 주고 `current_model_review`의 warnings/next_actions는 화면에 출력하지 않음 | `app.py:1369`, `editors.py:738`. §11의 reaction/metabolite/gene 필터 테이블, namespace 상세 해소 UI는 별도 미구현. objective term을 무조건 biomass로 표시하는 문구도 개선 필요 |
| 한국어 | shell/탭/일부 editor는 번역됨. Search, Host, Dynamics의 본문/버튼/실행 설명은 대부분 영어; 런타임 한/영 toggle은 없고 시작 인자만 있음 | `app.py:898`이 strings 없이 `SearchView()` 생성, `builder.py:424` 등 literal. `ko-search-empty-*`로 실제 확인. 부분 localization으로 문서에 명시하거나 catalog 적용 확대 |
| job cancel | 취소 요청 후 최종 cancelled 전이는 실제 확인됨. 다만 Search의 Cancel은 `bridge.cancelling`에 추가하지 않아 기다리는 동안 Jobs 행은 running; toolbar Cancel Selected Job은 cancelling로 바꿈 | `app.py:1625` 대 `:1068`; `ui_additional.json` `cancel_pending`. **P3 일관성 개선**, 동일 경로로 묶는 회귀 필요 |
| 표 설명/탐색 | per-target flux가 하나의 text cell에 합쳐지고 columns는 균등 stretch; 긴 member ID/상태가 잘릴 수 있음. 일반 cell의 전체값 tooltip, row detail, 정렬/필터, 단위 헤더 등이 부족 | `builder.py:567`, `:802`. run/evaluation/validation 원본 JSON에는 더 많은 근거가 있으므로 상세 패널 연결이 우선 |

## 시각 QA: 요청 크기와 실제 크기를 구분한 결과

**실제 PySide6 화면을 렌더하고 PNG를 image 도구로 열어 확인했다.** 단순 offscreen 테스트 통과를 시각 QA로 대신하지 않았다. 모든 경로의 prefix는 `.run/audit-20260925/`이다.

| 캡처 | 요청 / 실제 픽셀 | 직접 확인한 내용 |
|---|---|---|
| `en-search-empty-1500x950.png` | 1500×950 / **2045×950** | 최초 전체 shell, control density, 양쪽 pane |
| `en-search-empty-1280x800.png`, `en-search-empty-1x1.png` | 1280×800 또는 최소 요청 / **2045×823** | 표 viewport 높이 71px, 실제 최소 크기 |
| `ko-search-empty-1280x800.png` | 1280×800 / **2045×820** | 한글 글리프는 보임; shell만 번역된 영역 차이 |
| `pareto-matched-request1500x950-actual2771x950.png` | 1500×950 / **2771×950** | size=1, metric=pareto 등 입력을 결과에 맞춘 최종 화면; 경고 확장·막대 그림·변형된 글자 |
| `pareto-matched-request1280x800-actual2771x823.png` | 1280×800 / **2771×823** | 같은 실제 결과의 최소 높이 화면 |
| `en-pareto-forced-1500x950.png`, `en-pareto-forced-1280x800.png` | **강제 fixed-size** 1500×950 / 1280×800 | 좁은 viewport에서 label·입력·축 잘림. 앱이 자연스럽게 이 크기를 허용했다는 증거는 아님 |
| `mixed-figure-preview.png`, `en-mixed-result.png` | 실제 SVG widget/main window | 음수 기여도 삭제 및 종횡비 무시 |
| `en-profile-loaded.png` | 요청 1500×950 / 2045×950 | 실제 3-member bundle의 signed bars, table, member contribution; 부호 범례 표시 |
| `en-host_view-1500x950.png` | 요청 1500×950 / 2045×950 | 긴 Host controls가 최소 폭 원인; provenance source 입력이 매우 작게 보임 |
| `en-dynamics_view-1280x800.png` | 요청 1280×800 / 2045×823 | 시간·초기값·spatial 설정과 표/preview 배치 |
| `en-medium_editor-1500x950.png`, `en-sweep_view-1500x950.png` | 요청 1500×950 / 2045×950 | 배지/namespace/정확 적용 제어 및 sweep 설정 배치 |
| `en-graph-loaded.png`, `graph-before-refit.png` | 요청 1500×950 / 2045×950 | 실제 graph/table/legend; 그래프가 좌상단에 작고 일부 잘린 offscreen 관찰 |
| `en-failed-search.png` | 실제 failed job 화면 | generic rc=3만 보이고 실패 artifact 경로/후보 원인 부재 |

Models/Community/Sandbox/Compare 등의 빈 화면도 `ui_render` probe로 캡처했으나, 위 표에 없는 모든 PNG를 상세 시각 심사했다고 주장하지 않는다. `ui_geometry.json`이 각 캡처의 실제 크기를 기록한다. 초기 `en-pareto-normal`/강제 viewport 사진은 `load_summary`에 fixture 결과를 직접 넣은 상태라 일부 form 값이 결과와 달랐다. **이 차이는 probe setup이며 애플리케이션의 request mismatch 결함으로 보고하지 않았다.** 최종 `pareto-matched-*`에는 해당 설정을 맞췄다.

그래프는 JS에서 canvas 1575×582, zoom=1, pan=(0,0), 일부 negative rendered bounds를 확인했지만 재fit 호출 뒤 callback이 돌아오지 않았다. QtWebEngine은 `GPUInfo not initialized` 등 offscreen 경고도 냈다. 따라서 그래프 배치를 확인된 native 버그로 올리지 않고 **환경을 바꾼 추가 재현 필요**로 남긴다. screenshot이 예쁘게 나오지 않았다는 이유만으로 core graph payload가 틀렸다고 판단하지 않았다.

## 문서·원자적 게시·release 경계

- `docs/USER_GUIDE.md:877`에는 실제 `dfba-community` CLI 설명이 있지만 `:1168`에는 “library-level prototype … no CLI surface yet”라고 남아 있다. `cmig/cli/main.py:10428` parser와 `:5385` 실행 경로가 존재하므로 **확정 문서 모순**이다. `:1140`의 single-model-only 문구도 정리해야 한다.
- 같은 문서 `:346`은 search staging/rollback을 정확히 설명하지만 `:1163` 이후 atomicity 설명은 per-file 한계만 일반화한다. **Search run transaction은 이미 구현된 수정**이다. `cmig/io/run_transaction.py`의 staging/lock/rollback 및 관련 선택 테스트를 확인했고 “Search가 여전히 옛 산출물과 섞인다”는 과거 F8을 재등록하지 않았다. 반면 `cmig/render/publication.py:53`은 figure/spec/provenance 세 파일을 차례로 교체하므로 독립 render artifact set 전체를 단일 directory transaction이라고 부를 수 없다. workflow별 보장 범위를 문서화해야 한다.
- GUI Search/Host의 Export Figure는 `app.py:1272`/`:1248`에서 SVG 단일 `shutil.copyfile`만 수행한다. CLI가 만든 run manifest나 figure sidecar를 함께 내보내지 않고 export 실패를 UI boundary에서 잡지도 않는다. **개선 항목:** 원자적 copy, source=destination 처리, sidecar/출처 선택 export를 제공한다. 이번에는 실제 디스크-full 손상을 주입하지 않았으므로 별도 확정 손상 사례로 세지 않았다.
- `README.md:33`의 모든 analysis가 artifact digest를 남긴다는 일반화는 `USER_GUIDE.md:99`의 legacy solve 예외, 현재 spatial-preview의 no-manifest 결과와 맞지 않는다. 실제 spatial probe에서 `inspect-run artifact_integrity=not_recorded, result_digest_absent_reason=no_manifest`였다. 이를 과학적 성공 판정 오류로 확대하지 않고 문서 계약을 좁힐 필요가 있다.
- `.github/workflows/ci.yml:55`의 license-free 테스트 목록에는 GUI가 없고 quality 설치에도 gui extra가 없다. 실제 GUI suite는 Gurobi secret이 필요한 Ubuntu solver job에만 연결되고 외부 fork PR에서는 이 job을 건너뛴다. macOS/Windows matrix의 녹색이 native GUI QA를 뜻하지 않는다. **P2 release 검증 공백:** solver와 무관한 shell/layout/request tests를 gui extra를 가진 독립 matrix로 분리할 가치가 있다.
- CI package job은 distribution allowlist만 검사하며 설치된 wheel 동작·preset·sdist 로컬 링크는 검사하지 않는다(F12). `tests/test_docs_commands.py:25`는 README/USAGE만 대상으로 하고 USER_GUIDE는 제외한다. 명세의 계획과 현재 가이드의 제공 범위를 검사하는 문서 계약 테스트를 보강해야 한다.
- CI trigger는 main push/PR/workflow_dispatch이며 tag push/release가 없다. tag에서 version/changelog를 검사하는 스크립트가 존재하더라도 자동 tag gate가 현재 workflow에 연결되었다고 말할 수 없다. 실제 게시 방식이 수동인지 확인해 release checklist와 맞출 개선 항목이다.
- 새 wheel에서 AGORA list를 한 차례 실행했을 때 서버 응답에 `.xml` entry가 없어 명확한 오류와 rc=2를 반환했다(`distribution_probe.json`). 이것은 **현재 외부 응답/환경 관찰**이지 wheel에 카탈로그를 반드시 번들해야 한다는 증거가 아니다. 카탈로그는 원래 on-demand cache이다. 후속 path/URL 재현은 전부 offline으로 수행했다.

## 재현 산출물과 남은 검증

주요 기계 판독 근거: `ui_geometry.json`, `ui_functional.json`, `ui_additional.json`, `agora_path_probe.json`, `distribution_probe.json`, `final_evidence.log`. 실제 run은 `single/`, `pareto/`, `mixed/`, `solve/`, `dfba/`, `spatial/`에 있다. dfba/spatial/invalid_manifest는 readback 검증을 위해 의도적으로 변형한 산출물이므로 정상 연구 결과로 재사용하면 안 된다.

세션의 probe 소스는 `/tmp/cmig_ui_render_audit.py`, `/tmp/cmig_ui_seed_runs.py`, `/tmp/cmig_ui_functional_audit.py`, `/tmp/cmig_ui_additional_audit.py`, `/tmp/cmig_ui_distribution_probe.py`, `/tmp/cmig_ui_finalize_evidence.py`이다. root cwd에서 `PYTHONPATH=. .venv/bin/python <script>`로 실행했다. 세부 로그에 probe의 최초 실패(지원되지 않는 `.gz` 이름으로 fixture를 복사했던 경우) 후 수정 실행이 있을 수 있으므로, 판정은 최종 JSON과 현재 source lines를 기준으로 했다. 처음 실패한 probe를 애플리케이션 결함으로 계산하지 않았다.

남은 검증은 native macOS/Windows/HiDPI·키보드·접근성, 대형 GEM import 응답성, R 전용 publication 패널, 장시간 job 메모리와 process 종료, 확장 Pareto archive의 interactive 탐색이다. 이 항목들은 미검증/개선 범위이며 이번 감사가 생물학적 결과나 모든 UI 동작의 완전성을 보증하지 않는다.
