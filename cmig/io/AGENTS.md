# cmig/io

## 범위

입력·출력 경계.
- `model_import.py` — SBML(`.xml`, `.sbml`, `.xml.gz`)/JSON/MAT GEM을 cobra로 읽고 요약(exchange·biomass 탐지, 개수). 자체 파서 없음.
- `model_cache.py` — `.sbml`·대문자 확장자 등을 폐기 가능한 정규화 캐시 사본으로 만든다. 사용자 원본은 건드리지 않는다.
- `agora2.py` — AGORA2 카탈로그 조회·다운로드·인코딩 수리·BiGG 식 id 변환. CMIG의 유일한 네트워크 코드.
- `gem_paths.py` — 인간 GEM(Recon3D/RECON1) 파일 탐색 순서: `$CMIG_RECON3D_PATH`/`$CMIG_RECON1_PATH` → `$CMIG_GEM_DIR/<id>.xml` → `data/gems/` → `fixtures/` → `./`.
- `atomic.py` — 단일 파일 원자적 게시(같은 디렉터리 임시 파일 + fsync + `os.replace`, POSIX에서는 부모 디렉터리 sync 시도).
- `run_transaction.py` — 디렉터리 단위 staging·잠금·rollback 게시.
- `solve_output.py`, `dfba_output.py`, `quality_output.py` — 워크플로별 산출 배치와 legacy solve manifest.
- `project.py` — GUI 작업 공간의 프로젝트 폴더(`cmig-project.json` 형식 1, `.cmig-project.lock` 잠금), 모델·배지 사본과 sha256(`add_model_file`, `add_medium_file`, `verify_checksums`, 한 항목만 다시 확인하는 `refresh_integrity`), run 폴더(`new_run_dir`)와 입력 taxonomy(`write_run_taxonomy`), 실패·취소·읽기 거부 표식(`write_run_state`/`read_run_state`/`clear_run_state`), 모델 가져오기 후보(이름만 보는 `model_import_candidates`, 폴더를 뒤지는 `supported_model_paths`). Qt·GUI 코드 없음.

범위 아님: 과학 계산(→ `cmig/core`), 인자 해석(→ `cmig/cli`).

## 경계

- `cmig.gui`, `cmig.cli`, `cmig.service`를 import하지 않는다. PySide6 금지.
- 네트워크 요청은 `agora2.py`에서만 한다. 다른 모듈에 HTTP 코드를 추가하지 않는다.
- 저장소 안(`models/`, `fixtures/`, `data/`)에 다운로드하거나 쓰지 않는다. 출력은 호출자가 준 경로 아래에만. 프로젝트 폴더의 `models/`·`media/`·`runs/`는 사용자가 고른 프로젝트 안이므로 이 금지와 별개다.

## 불변식

- 사용자 원본 모델 파일은 절대 수정하지 않는다.
- AGORA2: 허용 origin은 `https://www.vmh.life`, 허용 경로는 `/files/reconstructions/AGORA2/` 아래. 리다이렉트의 각 다음 요청도 전송 전에 검사한다. 카탈로그 id·파일명은 basename 검증과 resolved 경로 포함 검사를 모두 통과해야 한다(`../`, 절대 경로, `\`, symlink 거부). 위험 파일명은 사용자 정의 fetcher로 넘기기 전에도 거부한다. 원 요청 URL과 실효 URL을 provenance로 남긴다.
- AGORA2 인코딩 수리는 잘못된 바이트만 표적 변환한다. 파일 전체를 latin-1로 다시 해석하지 않는다. id 변환은 구획(`EX_but(e)` → `EX_but_e`)과 이성질체 구분자(`glc_D` → `glc__D`)를 모두 적용한다.
- 원자적 쓰기가 실패하면 이전 파일이 그대로 남아야 한다. 임시 파일은 시스템 temp가 아니라 목적 디렉터리에 만든다(`os.replace`는 같은 파일시스템에서만 원자적).
- legacy solve manifest의 `run_hash`는 `cmig.core.manifest.compute_run_hash`로만 만든다.
- 모르는 확장자·파싱 실패는 명시적 예외(`ModelImportError`)다.
- 프로젝트(`project.py`): `cmig-project.json`의 사본 위치(`file`)는 프로젝트 기준 상대 경로로 두어 폴더를 옮겨도 열린다(절대 경로는 실행 때 계산하며, run 입력 taxonomy만 사본의 절대 경로를 적는다). `source_path`는 원본의 절대 경로(AGORA2는 다운로드 URL)를 출처 기록으로만 남기며 그 경로로 파일을 열지 않는다. 파일이 없거나 손상됐거나 `format_version`이 1이 아니면(미래 형식 포함) 열기를 거부하고 파일에 쓰지 않는다. 모든 I/O 오류는 `ProjectError`로 바꿔 올린다.
- 프로젝트: 저장은 `atomic_write_text`·`atomic_write_binary`로만 한다. 원본 GEM·배지는 읽기만 하고, 사본은 `models/`·`media/`에 쓰며 기존 파일을 덮어쓰지 않는다. 모델 목록에서 빼도 사본은 지우지 않는다(run이 참조할 수 있다). 같은 sha256은 중복으로 거부한다.
- 프로젝트: 열 때(`verify_checksums`)와 run 입력을 만들 때(`write_run_taxonomy`, 단일 경로 입력은 `refresh_integrity`) 사본의 sha256을 다시 계산한다. 다르거나 없는 사본(`integrity` `changed`/`missing`)과 점검에 실패한 모델은 run에 쓰지 않고 오류로 거부한다.
- 프로젝트: run 폴더는 `runs/<kind>-YYYYMMDD-HHMMSS[-N]`이며 기존 폴더를 재사용하지 않는다. run 입력(`<run>-taxonomy.csv`, GUI의 `<run>-state.json`)은 `runs/_inputs/`에 두고 run 폴더 안에는 쓰지 않는다. 표식은 `failed`/`cancelled`/`unreadable`만 기록하고, 읽을 수 없는 표식(손상·너무 깊은 중첩)은 표식 없음으로 본다. `rename_model`은 `analysis_settings`의 `models` 목록 id도 함께 바꾼다.
- 잠금은 PID와 호스트를 담는다. 같은 호스트의 죽은 프로세스가 남긴 형식이 올바른 잠금만 대체하고, 비었거나 깨진 잠금은 조용히 가져가지 않고 보고한다. 네트워크 코드는 없다(AGORA2는 CLI `agora2-fetch` 경유).
- pickle 금지.

## 구현 패턴

- 결과 파일 쓰기는 `atomic_write_text`, `atomic_write_parquet`, `atomic_write_path` 중 하나. 디렉터리 전체가 한 단위여야 하면 `run_transaction`.
- Windows 호환: `os.fchmod` 같은 POSIX 전용 호출은 가드한다. 경로 구분자와 실행 파일 경로는 플랫폼 의미를 따른다.
- 외부 모델의 출처·라이선스·checksum은 추적 파일(`data/gems/GEM_SOURCES.json`, `models/MODEL_SOURCES.json`)에 남긴다.

## 테스트

- AGORA2 테스트는 offline transport로만 한다(실제 VMH 가용성에 기대지 않음). 경로 탈출·리다이렉트·위험 파일명에서 출력 폴더 밖 바이트가 그대로인지 확인(`tests/test_agora2.py`).
- 원자적 쓰기: 중간 실패 시 이전 파일 보존, Windows 이식성(`tests/test_round7_atomic_io.py`, `tests/test_atomic_portability.py`).
- 트랜잭션: 게시 실패 시 이전 run 복원(`tests/test_run_transaction.py`).
- import: 각 형식, 잘못된 확장자, 원본 불변(`tests/test_model_import.py`).
- 프로젝트: 만들기·저장·다시 열기 왕복, 손상·미래 형식 거부(파일 무변경), 잠금 충돌·낡은 잠금, 이름 충돌 접미사, 중복 거부, checksum 변경·누락, taxonomy 내용, run 폴더 비재사용, 원본 불변(`tests/test_project_io.py`).
