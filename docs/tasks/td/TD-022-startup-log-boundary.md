# TD-022 Motion Server 초기화 로그의 책임 및 조건부 출력 정리

## 배경 및 현재 구조

Motion Server 초기화 완료 로그가 server/runtime 설정과 축별 device 상태를 한 줄에 함께 출력한다.
또한 실제 적용 여부와 관계없이 command-line/environment에서 읽은 DC/CSP parameter 원본값을 출력한다.

현재 혼재된 정보의 예:

- server/runtime: backend, axis count, cycle time, spin wait time
- 조건부 기능: DC phase lock/absolute shift/tuning, CSP profile/interpolation/velocity offset
- device 상태: statusword, software position limits, actual position(`AP`)

## 문제와 위험

- `PYSOEM_DC_ENABLED=0`이어도 DC tuning 값이 표시되어 실제 활성 상태로 오인할 수 있다.
- phase lock이 꺼져 실제로 무효인 absolute shift의 원본 설정값이 `True`로 표시될 수 있다.
- 축 수에 따라 device 배열이 길어져 핵심 server startup 정보가 묻힌다.
- server lifecycle log와 device feedback/diagnostics의 책임 경계가 불명확하다.

## 관련 위치

- `motion_server/server.py`
- `motion_server/config.py`
- `motion_server/app/state.py`
- `motion_server/app/cycle_diagnostics.py`
- device feedback/status API handler

## 목표 출력 정책

- 초기화 INFO 로그는 `Motion Server initialized`와 backend, axis count, cycle time 등
  server/runtime 요약만 한 줄로 출력한다.
- `dc_enabled`는 실제 적용 상태를 출력한다.
- DC가 비활성화되면 phase lock, absolute shift와 phase tuning parameter를 출력하지 않는다.
- DC가 활성화되고 phase lock도 활성화된 경우에만 phase tuning parameter를 출력한다.
- CSP 관련 parameter는 실제 startup motion mode 또는 활성 capability 기준으로 필요한 경우에만 출력한다.
- statusword, software position limits와 actual position은 초기화 요약에서 제거한다.

## Device 정보 제공 경계

- 정상 축 상태와 위치는 feedback/status API에서 제공한다.
- startup validation 실패와 안전상 중요한 불일치는 warning/error 로그로 남긴다.
- 상세 startup readback이 필요하면 server INFO 요약과 분리된 명시적 diagnostics/debug 경로를 사용한다.

## 검증 계획

- mock/pysoem backend와 DC off/on 조합의 출력 필드를 테스트한다.
- phase lock off/on 및 absolute shift 조합에서 실제 적용값만 출력되는지 확인한다.
- PP/PV/CSP startup mode별 CSP field 포함 여부를 확인한다.
- 1축/6축 구성에서 초기화 요약에 device 배열과 `AP`가 포함되지 않는지 검증한다.
- 초기화 실패 warning/error가 필요한 원인 정보를 계속 제공하는지 확인한다.

## 완료 증거

완료 시 startup log field contract, 조합별 자동 테스트와 대표 출력 예제를 기록한다.
