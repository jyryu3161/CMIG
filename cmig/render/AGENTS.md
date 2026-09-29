# cmig/render

## 범위

출판 그림의 Python 쪽.
- `client.py` — `RenderClient`: tidy profile → R subprocess(`cmig/render_r/figure.R`) → SVG/TIFF/PDF. R이 없으면 matplotlib로 대체. 실패는 `RenderError`.
- `composer.py` — 다중 패널 dispatch: network(ggraph, edges), heatmap(ComplexHeatmap, matrix), chord(circlize, edges). R 전용.
- `publication.py` — staging 경로에서 그림을 만든 뒤 그림·spec·provenance 세트를 게시.
- `provenance.py` — `<figure>.render_provenance.json`(실제 R·패키지 버전, 스크립트·lock·입력·spec·출력 SHA-256).
- `figure_style.py` — 공통 저널 스타일.

범위 아님: R 스크립트 자체와 lock(`cmig/render_r`), 분석 그림 데이터 생성(`cmig/core/interaction_figures.py` 등).

## 경계

- R은 반드시 subprocess로 실행한다. `rpy2` 같은 in-process R 바인딩을 도입하지 않는다(GPL 격리).
- R 패키지 경로는 저장소 루트의 `.Rlib`(`--rlib` 인자로 전달)다. 전역 R 라이브러리에 설치하거나 기대지 않는다.
- matplotlib은 사용 시점에 import한다(`render` extra 선택).

## 불변식

- 단일 profile 그림만 matplotlib로 대체할 수 있다. 다중 패널(network/heatmap/chord)은 R 또는 필요한 패키지가 없으면 `RenderError`로 끝낸다. 대체 그림을 R 그림처럼 내보내지 않는다.
- R 호출에는 시간 제한이 있다. 대화형 프롬프트 등으로 멈추면 `RenderError`가 된다.
- 성공한 렌더마다 provenance sidecar를 남긴다. figure spec(seed 포함)으로 다시 그릴 수 있어야 한다.
- 그림은 staging에서 완성된 뒤 게시한다. 현재 그림·spec·provenance는 파일별 원자적 교체이며, 세트 전체의 원자성은 보장하지 않는다. 세트 원자성을 주장하지 않는다.
- 다중 타깃 기여 그림은 음수 기여를 0 아래로, 양수를 위로 그리고 저장된 총점을 표시한다. 음수를 0으로 잘라내지 않는다. 긴 단위·정규화·Pareto 문구는 캔버스 안에서 줄바꿈한다.

## 구현 패턴

- 새 패널: R 스크립트를 `cmig/render_r/`에 추가 → `renv.lock` 의존성 확인 → `composer.py`에 dispatch 추가 → provenance에 스크립트 checksum 포함.
- 테스트용 가짜 `Rscript` 대역은 `--out`이 없는 호출(예: `uname -p`)을 실제 `subprocess.run`으로 넘긴다.

## 테스트

- R 부재: 단일 그림 fallback, 다중 패널 `RenderError`(`tests/test_render.py`, `tests/test_figure_composer.py`).
- staging·게시, provenance checksum(`tests/test_round9_render_pipeline.py`, `tests/test_figure_publication_export.py`).
- signed 기여 부호·합과 막대 geometry 일치, SVG 텍스트가 경계 안(`tests/test_remediation_figures.py`).
