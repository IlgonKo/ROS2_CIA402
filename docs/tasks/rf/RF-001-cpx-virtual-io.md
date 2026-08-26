# RF-001 CPX-AP-I-EC Virtual I/O

## 사용자 가치

실제 CPX-AP-I-EC가 없어도 동일한 설정과 Motion Server API로 Remote I/O 기능을 개발하고 회귀 시험한다.

## 구현 범위

- `MOTION_SERVER_IO_<io>_MODULES`와 `MOTION_SERVER_IO_<io>_IOL_PORTS` 설정을 사용한다.
- DI/DO/AI/AO/IO-Link process image와 AP module layout을 모사한다.
- EtherCAT SDO, AP parameter access와 IO-Link ISDU의 가상 동작을 제공한다.
- Motion Server와 IO Control Panel에서 실장치와 가상 장치를 같은 API로 처리한다.

## 기술 제약

실장치 고유 timing과 firmware fault를 완전히 모사한다고 간주하지 않으며 지원 차이를 명시한다.

## 선행 책임 경계

- [TD-028](../td/TD-028-virtual-od-bridge-boundary.md)에서 확정한 공통 Virtual Device 계약을
  사용한다.
- OD Model은 definition과 runtime value, OD Bridge는 Object Access와 PDO 동기화만 담당한다.
- MockSlave는 장치 의미를 해석하지 않고 `virtual_device`에 object-write와 cyclic 처리를 위임한다.
- CPX reset, AP parameter와 IO-Link ISDU의 내부 반응은 `VirtualCpxApDevice`가 담당하며,
  Motion Server의 command sequence를 별도로 복제하지 않는다.

## 검증 계획

- module/port 조합별 process image layout과 codec을 테스트한다.
- feedback, output write, SDO/AP/IOL parameter read/write를 end-to-end 테스트한다.
- 동일 client scenario를 virtual 및 실제 CPX profile에 적용한다.

## 완료 증거

완료 시 지원 범위 표, fixture, 자동 테스트와 실장치 비교 결과를 기록한다.
