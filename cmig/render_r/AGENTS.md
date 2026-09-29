# cmig/render_r

## 범위

출판 그림용 R 스크립트와 R 환경 고정. `figure.R`(단일 profile, ggplot2), `network.R`(ggraph + graphlayouts + igraph), `heatmap.R`(ComplexHeatmap + circlize colorRamp2), `chord.R`(circlize), `renv.lock`(R 4.3.2, Bioconductor 3.18, 네 스크립트의 전체 의존성 closure). SVG는 svglite, TIFF는 ragg.

범위 아님: 그림 호출·staging·provenance(`cmig/render`의 Python 코드), 그림 데이터 생성.

## 경계

- 스크립트는 파일(tidy Parquet/CSV, figure spec JSON)로 입력을 받고 파일로 출력한다. CMIG Python 객체나 프로세스 상태에 접근하지 않는다.
- `--rlib` 인자로 받은 경로를 `.libPaths()` 앞에 넣는다. 전역 라이브러리에 설치하지 않는다.
- OS 시스템 라이브러리(글꼴, PNG, TIFF, 컴파일러)는 설치하지 않는다.

## 불변식

- 새 R 패키지를 쓰면 `renv.lock`을 갱신한다. lock 갱신은 의도된 릴리스 변경이며, 갱신 후 렌더 테스트를 모두 다시 돌린다.
- 레이아웃은 기본적으로 결정적(stress 레이아웃, spec의 seed)이다. 같은 입력·spec·lock이면 같은 그림이 나와야 한다.
- R 오류는 0이 아닌 종료 코드로 끝내 Python 쪽이 `RenderError`로 알 수 있게 한다. 빈 그림을 성공으로 쓰지 않는다.

## 구현 패턴

- 복원: `Rscript -e 'renv::restore(lockfile="cmig/render_r/renv.lock", library=".Rlib", prompt=FALSE)'`.
- 비대화형으로 실행되어야 한다(프롬프트를 띄우면 Python 쪽 시간 제한에 걸린다).

## 테스트

- R이 설치된 환경에서 네 스크립트 각각을 실제로 렌더하고 provenance의 스크립트·lock checksum을 확인한다. R이 없는 CI에서는 이 검증이 skip되며 이를 통과로 세지 않는다.
