# TD-023 Virtual Servo OD 초기값의 Startup 덮어쓰기

## 배경 및 현재 구조

Virtual Servo의 OD Model은 선택된 profile의 required OD default를 적용해 가상 장비의 초기 parameter를 구성한다.
그러나 mock runtime 생성 과정에서 `servo.set_motion_limits()`를 호출하여 다음 OD를 서버 설정값으로 즉시 다시 기록한다.

- `0x607F` Max profile velocity
- `0x2183:0C` Negative velocity limit
- `0x60C5` Max acceleration
- `0x60C6` Max deceleration
- `0x6083` Profile acceleration
- `0x6084` Profile deceleration

실축 startup은 해당 parameter를 덮어쓰지 않고 장비의 기존 값을 SDO로 읽어 runtime 상태를 구성한다.

## 문제와 위험

- required OD에 정의한 Virtual Servo 초기값이 실제 mock 구동 상태에 반영되지 않는다.
- mock과 실축의 startup parameter 정책이 달라 시험 결과가 실제 장비 동작을 대표하지 못할 수 있다.
- MotionController가 정상 startup에서는 device OD readback을 사용하지만 readback 실패 시
  `MOTION_SERVER_MAX_VELOCITY`, `MOTION_SERVER_ACCELERATION`, `MOTION_SERVER_DECELERATION`으로
  대체하여 제한값의 기준이 일관되지 않다.
- 위 설정은 device 제한과 최솟값을 계산하지 않으므로 독립적인 server safety limit로 볼 수 없다.

## 관련 위치

- `device/cmmt/required_od.py`
- `device/virtual_servo_drive/od_model.py`
- `device/virtual_servo_drive/servo_model.py`
- `motion_server/app/startup.py`
- `motion_server/config.py`

## 목표 구조 및 구현 범위

- Virtual Servo의 초기 OD parameter는 profile의 required OD default에서 생성한다.
- mock runtime 생성 단계에서 device OD motion parameter를 자동으로 덮어쓰지 않는다.
- `MOTION_SERVER_MAX_VELOCITY`, `MOTION_SERVER_ACCELERATION`, `MOTION_SERVER_DECELERATION`과
  대응 command-line option 및 이에 기반한 motion limit fallback을 제거한다.
- MotionController의 velocity, acceleration과 deceleration 제한은 mock과 실축 모두
  device OD readback을 기준으로 구성한다.
- 필수 motion limit OD readback에 실패하면 임의의 server 기본값으로 계속하지 않고
  initialization error로 처리한다.
- device OD parameter 변경은 실축과 동일하게 명시적인 axis setting 명령을 통해 수행한다.
- startup readback은 mock과 실축 모두 기존 device parameter를 읽어 runtime 상태를 구성한다.
- 독립적인 server safety limit가 필요하면 별도 요구사항과 명시적인 설정으로 추가하고,
  적용값을 device limit와 server safety limit 중 더 제한적인 값으로 계산한다.

## 검증 계획

- Virtual Servo 생성 직후와 전체 startup 이후 required OD default가 유지되는지 검증한다.
- MotionController 제한이 device OD readback과 일치하는지 검증한다.
- 필수 motion limit OD readback 실패가 initialization error가 되는지 검증한다.
- 제거 대상 `MOTION_SERVER_*` 설정과 command-line option이 startup 제한값에 관여하지 않는지 검증한다.
- axis setting 명령을 실행하면 mock과 실축의 동일한 profile API 경로로 OD parameter가 변경되는지 검증한다.
- 서로 다른 required OD default를 가진 virtual axis별로 readback과 MotionController 제한이 독립적으로 구성되는지 검증한다.

## 완료 증거

완료 시 제거된 startup write 경로, mock/real parameter 정책 비교와 자동 테스트 결과를 기록한다.
