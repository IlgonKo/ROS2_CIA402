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
- Motion Server의 trajectory/safety limit와 device에 저장된 OD parameter의 책임이 혼재한다.

## 관련 위치

- `device/cmmt/required_od.py`
- `device/virtual_servo_drive/od_model.py`
- `device/virtual_servo_drive/servo_model.py`
- `motion_server/app/startup.py`
- `motion_server/config.py`

## 목표 구조 및 구현 범위

- Virtual Servo의 초기 OD parameter는 profile의 required OD default에서 생성한다.
- mock runtime 생성 단계에서 device OD motion parameter를 자동으로 덮어쓰지 않는다.
- `MOTION_SERVER_MAX_VELOCITY`, `MOTION_SERVER_ACCELERATION`, `MOTION_SERVER_DECELERATION`은 MotionController의 서버 측 command/trajectory 제한으로 사용한다.
- device OD parameter 변경은 실축과 동일하게 명시적인 axis setting 명령을 통해 수행한다.
- startup readback은 mock과 실축 모두 기존 device parameter를 읽어 runtime 상태를 구성한다.

## 검증 계획

- Virtual Servo 생성 직후와 전체 startup 이후 required OD default가 유지되는지 검증한다.
- 서버 motion limit 설정값이 MotionController에는 적용되지만 device OD를 변경하지 않는지 검증한다.
- axis setting 명령을 실행하면 mock과 실축의 동일한 profile API 경로로 OD parameter가 변경되는지 검증한다.
- 서로 다른 required OD default와 서버 limit 조합을 사용해 양쪽 값이 독립적으로 유지되는지 검증한다.

## 완료 증거

완료 시 제거된 startup write 경로, mock/real parameter 정책 비교와 자동 테스트 결과를 기록한다.
