# RF-013 Virtual AP Module 및 IO-Link Parameter Device

## 사용자 가치

실제 AP module과 IO-Link Device가 없어도 Motion Server의 기존 AP parameter 및 IO-Link ISDU API를
사용하여 parameter read/write 동작을 개발하고 회귀 시험한다.

## 책임 경계

- RF-001의 Virtual CPX station은 EtherCAT에서 보이는 gateway OD와 request/response 전달을 담당한다.
- AP module parameter와 IO-Link ISDU의 실제 값은 CPX station OD에 펼쳐 넣지 않는다.
- Virtual AP Module은 module별 AP parameter 공간과 장치 반응을 소유한다.
- Virtual IO-Link Device는 연결된 module/port별 ISDU parameter 공간과 장치 반응을 소유한다.
- `VirtualCpxApDevice`는 Model_Update 시점에 gateway OD의 요청을 해석하여 대상 virtual device에
  전달하고, 처리 결과를 gateway OD의 data/status에 반영한다.
- Motion Server는 실장치와 동일한 AP parameter 및 IO-Link ISDU command sequence를 사용하며
  mock 전용 API나 우회 경로를 만들지 않는다.

## 구현 범위

- 설정된 AP module마다 `module / parameter_id / instance`로 식별되는 runtime parameter 공간을
  생성한다.
- 설정된 IO-Link module/port마다 `index / subindex`로 식별되는 ISDU runtime parameter 공간을
  생성한다.
- parameter의 초기값, datatype, 길이와 read/write access를 정의하고 검증한다.
- AP parameter access gateway `0x27F0`의 read/write 요청, status와 data 응답을 virtual AP module에
  연결한다.
- IO-Link module별 ISDU access gateway를 virtual IO-Link Device에 연결한다.
- 존재하지 않는 module/port/parameter, 잘못된 길이·access와 장치 처리 실패를 실장치 API와 같은
  Failure 계약으로 반환한다.
- device reset과 재생성 시 초기값·runtime value의 유지 또는 초기화 정책을 명시하고 구현한다.

## 선행 및 연관 기능

- [RF-001](RF-001-cpx-virtual-io.md)의 Virtual CPX OD Model, process image와 gateway OD 기반이
  선행되어야 한다.
- [RF-004](RF-004-ap-parameter-catalog.md)는 APDD 기반 catalog 조회와 write 전 metadata
  validation을 제공하는 별도 기능이다. RF-013은 gateway 뒤의 virtual runtime parameter 공간과
  장치 반응을 담당한다.
- IO-Link parameter definition은 설정된 IODD와 일치해야 하며, 정의 source와 초기값 정책은
  구현 전에 확정한다.

## 제외 범위

- AP/IO-Link parameter를 CPX EtherCAT station OD의 개별 object로 직접 노출하지 않는다.
- 실제 firmware의 처리 지연, 비결정적 timing과 모든 vendor-specific fault를 완전 모사하지 않는다.
- RF-004의 APDD catalog 조회 API를 이 기능에서 중복 구현하지 않는다.

## 검증 계획

- AP module 및 IO-Link module/port 조합별 독립 parameter 공간과 초기값을 검증한다.
- 같은 module 내 instance, 서로 다른 module/port와 동일 index/subindex 사이의 값 격리를 검증한다.
- 기존 Motion Server AP parameter 및 IO-Link ISDU API로 gateway OD부터 virtual parameter
  device까지 end-to-end read/write를 검증한다.
- unknown target, access 위반, 길이 오류, reset과 재생성 경로를 자동 테스트한다.

## 완료 증거

완료 시 지원 virtual AP module/IO-Link Device 목록, parameter definition source, 초기화·reset 정책,
자동 테스트와 가능한 범위의 실장치 비교 결과를 기록한다.
