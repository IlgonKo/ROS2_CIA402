# TD-034 Linear/Rotary Velocity Command 허용 범위 정리

- 등록일: 2026-09-04
- 상태: `open`
- 우선순위: 보통
- 후속 작업: RF-018

## 배경

RF-018은 DualSense 같은 gamepad의 stick 입력으로 X/Y/Z/Rotation을 동시에 수동 velocity 제어하는
reference client다. 이 client는 신규 gamepad API 대신 기존 `system/axes/move_vel`을 사용한다.

현재 Motion Server의 `move_vel` 경로에는 linear axis에서 PV/velocity command가 제한되는 부분이
남아 있을 가능성이 있다. command authority, enabled/fault 상태, motion/software limit와 timeout
safety는 이미 기존 계약으로 유지하되, linear/rotary axis 모두 velocity command를 사용할 수 있도록
허용 범위를 정리해야 한다.

## 범위

- `system/axis/move_vel`과 `system/axes/move_vel`의 현재 제한 조건 조사
- linear axis에서 velocity command가 막히는 지점과 의도 확인
- linear/rotary 모두 velocity command 허용
- linear mm/s, rotary deg/s 기준 unit conversion 확인
- axis별 max velocity/motion limit와 software limit 유지 확인
- 다축 `move_vel`을 RF-018의 X/Y/Z/Rotation 수동 velocity command에 사용할 수 있는지 검증

## 유지할 기존 안전 계약

- command authority 필요
- axis enabled 필요
- fault 없음
- motion limit 유지
- software limit 유지
- axis별 max velocity 이하 제한
- command timeout 또는 feedback timeout 시 stop

## 제외 범위

- 신규 gamepad 전용 API
- 신규 다축 jog API
- force/torque control
- trajectory generation
- safety guard 우회
- RF-018 gamepad client 구현

## 완료 조건

- linear axis와 rotary axis 모두 `system/axis/move_vel` 및 `system/axes/move_vel`에서 허용된다.
- 기존 safety validation과 runtime/fault/authority gating이 유지된다.
- mm/s와 deg/s 단위 변환이 axis role별로 회귀 테스트된다.
- 다축 velocity command가 일부 축 실패 시 기존 Fail/PartialFailure 계약과 일치한다.
- neutral/zero velocity 또는 stop 경계가 RF-018에서 안전하게 사용할 수 있도록 명확히 문서화된다.
