# Client Response 호환 계약

TD-005-S09에서는 서버의 Success/Fail 최종 전환 전에 배포 client가 기존 응답과 신규 envelope를 모두
읽도록 공통 decoder를 사용한다.

## 정규화 결과

- 기존 성공 응답은 현재 top-level data와 `ok: true` 의미를 유지한다.
- 신규 Success의 `data`는 client 내부에서 top-level view로 펼치고 `ok: true`로 해석한다.
- 기존 `command_rejected`와 `ok: false`는 실패로 해석한다.
- 신규 Fail은 `ok: false`, 안전한 `message/error`, `failure_code`와 소문자 `reason` view로 해석한다.
- `failure.details`의 승인된 target/authority field만 기존 client view에 전달한다.
- JSON object가 아니거나 envelope 구조가 잘못된 응답은 `MALFORMED_RESPONSE`로 변환하여 connection
  read loop를 중단시키지 않는다.

이 정규화 view는 client 내부 호환 계층이다. Motion Server의 공개 신규 계약에 `ok`, top-level
`error` 또는 `reason`을 다시 추가하는 것이 아니다.

## Axis 장치 원시 Diagnostic 명칭

- 신규 정식 field는 `device_diagnostics`다.
- 기존 응답의 `diagnostics`는 decoder가 `device_diagnostics`로 읽는다.
- S09 기간의 서버 legacy status adapter는 구버전 client를 위해 `diagnostics` 별칭을 함께 보낸다.
- Motion Server 공통 Alarm/Fault snapshot은 별도 `diagnostic_status` field를 사용한다.
- S10에서 신규 envelope 송신으로 전환하면 정식 data에는 `device_diagnostics`만 포함한다.
- S11에서 legacy 송신 별칭과 client fallback의 제거 여부를 최종 검증한다.

## Client 적용 범위

- Axis Control Panel
- I/O Control Panel
- ROS Bridge의 수신 경계

ROS Bridge의 과거 command namespace, trajectory와 전체 status/feedback 이관은 이 decoder 작업과
구분하며 [RF-008](../tasks/rf/RF-008-ros-bridge-migration.md)에서 계속 추적한다.
