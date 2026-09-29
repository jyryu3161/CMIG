# 0001. 커뮤니티 FBA는 MICOM에 위임하고 정확한 버전으로 고정한다

- 상태: 수락
- 날짜: 2026-06 (명세 v3.0 부록 A1, MVP-1a)

## 맥락

커뮤니티 구성과 cooperative tradeoff(커뮤니티 성장 최대화 후 멤버 성장 L2 QP)를 직접 구현하면 검증 부담이 크고, 기존 도구와 결과를 비교하기 어렵다. 반면 외부 엔진에 맡기면 엔진 버전이 바뀔 때마다 숫자가 조용히 바뀔 수 있고, 모든 run 기록이 엔진 버전에 묶인다.

## 결정

커뮤니티 구성·cooperative tradeoff·abundance·배지 적용은 MICOM에 맡긴다. 호출은 `cmig/core/engine.py` 한 곳을 거치고, public API와 문서화된 flux 반환 옵션(`cooperative_tradeoff(fraction=f, fluxes=True, pfba=True)`)만 쓴다. `micom==0.39.0`을 정확히 고정하고 MICOM 버전은 solve `run_hash`의 구성요소로 넣는다. CMIG는 namespace 정합, 부호 정규화, tidy, 상호작용 추출, 탐색, 숙주 결합, 동역학, 재현성 기록을 소유한다.

## 대안

- 자체 커뮤니티 LP/QP 구현: 검증된 공개 구현과의 비교 기준을 잃고 유지 부담이 커서 제외.
- MICOM 범위 버전 허용(`>=`): 업그레이드마다 golden 숫자가 경고 없이 바뀌어 재현성 기록이 무의미해지므로 제외.
- 다른 커뮤니티 도구(SMETANA, PyCoMo 등)를 코어로: SMETANA는 코어 대신 선택적 비교 대상으로만 남김.

## 결과

- MICOM 업그레이드는 gurobi·osqp golden을 모두 통과해야 승격된다. 승격하면 golden hash가 바뀐다.
- MICOM 0.39가 제공하지 않는 것은 CMIG가 바깥에서 해결해야 한다: 숙주 결합(→ 구성 B), 비단위 계수 exchange 보존 불가(→ 커뮤니티 입력 거부).
- pool/member 식별자 해석은 MICOM 0.39의 비공개 구조에 기대고 있다. 버전 확인을 붙였지만 공개 API가 아니므로 MICOM 버전을 바꿀 때 가장 먼저 깨질 곳이다.
