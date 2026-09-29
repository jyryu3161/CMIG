# 0005. 결과 의미를 바꾼 정책은 hash 밖 provenance 표식으로 기록한다

- 상태: 수락
- 날짜: 2026-07 ~ 2026-09 (round 6 이후 누적)

## 맥락

배지 적용 방식(이미 열린 uptake에만 적용하던 결함), 경계 격리 범위, 숙주 격리 범위, exchange 물리량 변환, 숙주 전달 식별성, 통계 퇴화 처리, Pareto 표본 기록을 고칠 때마다 같은 입력에서 결과 숫자가 바뀌었다. 이 수정들을 `run_hash`에 넣으면 모든 발표된 hash와 고정 golden이 한꺼번에 움직이고, 넣지 않으면 같은 hash의 두 run이 다른 숫자를 가질 수 있다.

## 결정

`run_hash`는 입력만 인증한다. 결과 의미를 바꾼 정책은 `NON_HASHED_PROVENANCE_MARKERS`(`medium_policy`, `exchange_readout_policy`, `host_transfer_policy`, `statistics_policy`, `pareto_sampling_policy`, `boundary_isolation_policy`, `host_isolation_policy`)의 버전 표식으로 모든 workflow manifest에 찍어 run의 시점을 판정하게 한다. 입력 자체가 바뀌는 변경(새 hash 인자, 직렬화 변경)은 hash 계약 변경으로 처리한다.

## 대안

- 정책 버전을 hash 구성요소로 추가: 고정된 11구성요소 solve hash 계약을 깨고 모든 golden·발표 hash를 이동시키므로 제외.
- 아무 기록 없이 수정: 이전 run이 틀렸는지 판정할 방법이 없어져 제외.

## 결과

- 같은 `run_hash`라도 표식이 다르면 결과를 비교할 수 없다. 소비자는 hash만으로 결과 동일성을 판단하면 안 된다.
- 이전 run의 재실행 필요 여부는 `inspect-run`의 provenance 표식으로 판정한다(예: `medium_policy`가 없거나 `open_uptakes_exact_key_v1`).
- 결과 의미를 바꾸는 새 수정은 표식 값을 올려야 한다.
