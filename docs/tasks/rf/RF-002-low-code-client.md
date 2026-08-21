# RF-002 Low-code Reference Client

## 사용자 가치

Node-RED 같은 low-code 환경과 최소 Python 코드에서 Control Panel 없이 Motion Server를 사용할 수 있게 한다.

## 구현 범위

- TCP JSON-lines 연결, 연결 해제와 재연결을 처리한다.
- request/response correlation과 비동기 feedback 분리를 예제로 제공한다.
- authority acquire/release, feedback, axis motion, I/O output과 parameter access를 포함한다.
- Basic mode 기준 Node-RED flow와 최소 Python reference client를 제공한다.

## 범위 제외

생산용 범용 SDK와 특정 PLC/SCADA 제품별 connector는 별도 기능으로 다룬다.

## 검증 계획

- server restart와 network disconnect 후 재연결을 검증한다.
- Node-RED와 Python에서 동일한 축/I/O scenario를 수행한다.
- clean environment에서 import/install 절차와 예제 payload를 검증한다.

## 완료 증거

완료 시 flow/client artifact, 실행 절차와 smoke-test 결과를 기록한다.
