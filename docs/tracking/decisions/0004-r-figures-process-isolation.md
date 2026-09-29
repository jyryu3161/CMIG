# 0004. 출판 그림은 별도 R 프로세스와 고정된 renv lock으로 만든다

- 상태: 수락
- 날짜: 2026-06-01

## 맥락

출판 품질의 network(ggraph), heatmap(ComplexHeatmap), chord(circlize) 그림은 R 생태계가 가장 낫다. 그러나 R과 여러 패키지는 GPL이고, 전역 R 라이브러리 버전은 사용자마다 달라 그림 재현이 어렵다.

## 결정

R은 subprocess로만 실행한다(CMIG 프로세스에 GPL 코드를 싣지 않음). 패키지는 `cmig/render_r/renv.lock`(R 4.3.2, Bioconductor 3.18)으로 고정하고, gitignore된 프로젝트 로컬 `.Rlib`에 복원한다. 성공한 렌더마다 실제 R·패키지 버전과 입력·스크립트·lock·출력 checksum을 `<figure>.render_provenance.json`에 남긴다. 단일 profile 그림은 R이 없으면 matplotlib로 대체하고, 다중 패널 그림은 R 전용이며 R이 없으면 명시적 오류로 끝낸다.

## 대안

- Python 전용(matplotlib/plotnine): 다중 패널 출판 그림 품질이 부족해 기본 경로로 채택하지 않음.
- 전역 R 라이브러리 사용: 재현 불가, 사용자 환경 오염으로 제외.
- 다중 패널도 matplotlib로 몰래 대체: 사용자가 R 그림을 받았다고 오해하므로 제외.

## 결과

- lock 갱신은 의도된 릴리스 변경이며, 갱신 후 렌더 테스트를 모두 다시 돌린다.
- 글꼴·PNG·TIFF·컴파일용 OS 라이브러리는 CMIG가 설치하지 않는다.
