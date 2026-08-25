# TD-025 Runtime Parameter Cache 관리 체계 확장

## 배경

TD-023은 CMMT 축 제어에 즉시 필요한 OD readback을 단일
`AxisParameterRuntimeCache`에 보관하고 startup, 설정 변경과 reset lifecycle에서
동기화한다. 범용 parameter refresh와 다른 장치 유형까지 포함하면 TD-023의 Virtual OD
초기화 범위를 벗어나므로 후속 작업으로 분리한다.

## 범위

- cache 항목의 definition, source, validity와 마지막 갱신 시각
- 전체/축별/항목별 명시적 refresh API
- 일반 `param_write` 이후 관련 cache 갱신 또는 invalidation
- Motion Server 외부 commissioning 변경의 refresh 정책
- readback 실패 시 이전 값 유지 또는 invalid 처리 정책
- 다중 항목의 atomic update와 Diagnostic 연동
- RF-005가 통지한 PySOEM Axis restart/recovery 완료 후 해당 축 OD refresh
- restart 후 readback 실패 항목의 invalid 처리와 MotionController 사용 차단
- IO와 향후 device profile별 cache provider 확장 경계

## 제외 범위

- TD-023이 소유하는 CMMT startup, Mock reset 직후 필수 축 parameter 동기화
- 주기 제어 중 SDO polling

## RF-005와의 경계

- RF-005는 실축 restart 완료 감지, EtherCAT 연결 복구와 상태 전이를 책임진다.
- TD-025는 복구 완료 이벤트 이후 OD readback, cache 갱신/invalid 처리와 제어 projection
  재동기화를 책임진다.
