# Client Response 해석 계약

배포 이력이 없으므로 TD-005-S11부터 client는 현재 Success/Fail envelope만 해석한다. 기존 응답에 대한
backward compatibility는 제공하지 않는다.

## 정규화 결과

- 신규 Success의 `data`는 client 내부에서 top-level view로 펼치고 `ok: true`로 해석한다.
- 신규 Fail은 `ok: false`, 안전한 `message/error`, `failure_code`와 소문자 `reason` view로 해석한다.
- `failure.details`의 승인된 target/authority field만 기존 client view에 전달한다.
- JSON object가 아니거나 envelope 구조가 잘못된 응답은 `MALFORMED_RESPONSE`로 변환하여 connection
  read loop를 중단시키지 않는다.

이 view는 client 내부 표시 계층이다. Motion Server의 공개 계약에 `ok`, top-level
`error` 또는 `reason`을 다시 추가하는 것이 아니다.

`result`가 없는 request response, `command_rejected`, top-level `ok/error` 응답은
`MALFORMED_RESPONSE`로 거부한다. `system/feedback`과 승인된 notification은 envelope 밖 메시지로 읽는다.

## Axis 장치 원시 Diagnostic 명칭

- 신규 정식 field는 `device_diagnostics`다.
- Motion Server 공통 Alarm/Fault snapshot은 별도 `diagnostic_status` field를 사용한다.
- `diagnostics`는 삭제된 field이며 client가 변환하거나 fallback하지 않는다.

## Client 적용 범위

- Axis Control Panel
- I/O Control Panel
- ROS Bridge의 수신 경계

ROS Bridge의 과거 command namespace, trajectory와 전체 status/feedback 이관은 이 해석 작업과
구분하며 [RF-008](../tasks/rf/RF-008-ros-bridge-migration.md)에서 계속 추적한다.
