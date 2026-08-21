# Diagnostic Status 조회 계약

Motion Server의 기존 status 응답은 `diagnostic_status` snapshot을 포함한다. 이 객체는 장치 원시
diagnostic readback과 구분되는 Motion Server 공통 Diagnostic 상태다.

## Snapshot 구조

```json
{
  "diagnostic_status": {
    "level": "normal | alarm | fault",
    "statuses": []
  }
}
```

- `level`은 해당 status 응답 범위에 존재하는 활성 Diagnostic 중 가장 높은 level이다.
- 활성 Diagnostic이 없으면 `normal`과 빈 `statuses`를 반환한다. NORMAL Diagnostic 객체는 만들지 않는다.
- `statuses`는 Fault, Alarm 순서이고 같은 level에서는 source type/index, code와 ID 순서로 정렬한다.

## Status별 조회 범위

| Status | 포함 범위 |
| --- | --- |
| `system/server/status` | 모든 source의 활성 Diagnostic |
| `system/bus/status` | `BUS:0` |
| `system/axis/status` | 요청한 `AXIS:<index>` |
| `system/axes/status` | 모든 `AXIS` source |
| `system/io/status` | 모든 `IO` source |

Axis status의 기존 `diagnostics` field는 CMMT 원시 SDO readback이며 `diagnostic_status`와 다른 계약이다.
기존 client 호환을 위해 이 field의 이름과 payload는 TD-005-S08D에서 변경하지 않는다.

## 활성 Status 구조

```json
{
  "diagnostic_id": "opaque-id",
  "definition": {
    "code": "AXIS_DRIVE_FAULT",
    "level": "fault",
    "title": "Axis drive fault",
    "description": "The CiA 402 drive reports an active fault.",
    "latching": true
  },
  "source": {
    "type": "axis",
    "index": 0
  },
  "history": {
    "occurred_at": "2026-08-21T01:02:03Z",
    "acknowledged_at": null,
    "resolved_at": null
  }
}
```

- 시간은 ISO 8601 문자열이며 timezone이 있는 값은 UTC `Z`로 직렬화한다.
- `diagnostic_id`는 client가 구조를 해석하지 않는 opaque 문자열이다.
- `detail`과 `context`는 내부 모델의 예약 field다. 공개 범위와 안전한 schema가 확정되지 않았으므로
  status 응답에는 포함하지 않는다.
- 조회는 상태를 변경하지 않는다. acknowledge 명령, notification과 영속 이력 조회는 이 계약의 범위가 아니다.
