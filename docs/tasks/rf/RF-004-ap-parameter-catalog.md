# RF-004 AP Parameter Catalog

## 현재 상태

AP parameter read/write는 구현되어 있지만 catalog 조회와 write 전 metadata validation은 제공하지 않는다.

## 차단 사유 및 재개 조건

CPX EtherCAT ESI의 `0x27F0`은 AP parameter access mailbox 형식만 설명한다. AP 하위 module별 catalog에는
APDD가 필요하므로 APDD의 안정적인 확보 방식, version 식별과 cache 정책이 확정된 후 재개한다.

## 구현 범위

- APDD에서 parameter id, type, length, access, range와 label을 해석한다.
- module identity/version과 맞는 catalog를 선택한다.
- catalog 조회 API와 parameter write 사전 validation을 제공한다.

## 기술 제약

ESI EtherCAT object dictionary를 AP parameter catalog로 사용하지 않는다. APDD 없는 module의 fallback을
추측으로 생성하지 않는다.

## 검증 계획

- 여러 APDD version fixture와 malformed/missing catalog를 테스트한다.
- 대표 AP module의 catalog 결과 및 parameter read/write를 실장치에서 비교한다.

## 완료 증거

완료 시 APDD source/version 정책, 지원 module 목록과 시험 결과를 기록한다.
