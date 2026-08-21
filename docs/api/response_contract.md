# API Success/Fail 응답 계약

## 적용 범위

이 문서는 client 요청에 대해 Motion Server가 한 번 반환하는 공통 response envelope의 목표 계약을
정의한다. 주기적인 feedback과 서버가 자발적으로 보내는 notification에는 이 envelope를 적용하지 않는다.
현재 구현에는 `ok`, `accepted`, `reason`, 최상위 `error`와 `command_rejected` type이 혼재하므로
TD-005에서 이 계약으로 migration한다.

## Success response

```json
{
  "type": "system/axis/param_read",
  "result": "success",
  "request_id": "optional-client-request-id",
  "data": {
    "axis": 0,
    "index": 24676,
    "subindex": 0,
    "value": 1000
  }
}
```

## Fail response

```json
{
  "type": "system/axis/param_read",
  "result": "fail",
  "request_id": "optional-client-request-id",
  "failure": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Axis 10 does not exist.",
    "details": {
      "axis": 10
    }
  }
}
```

## 공통 규칙

- `type`은 요청의 command type을 그대로 사용한다. 실패 시 `command_rejected` 같은 공통 type으로 바꾸지 않는다.
- `result`는 소문자 `success` 또는 `fail`만 사용한다.
- 요청에 `request_id`가 있으면 같은 값을 응답에 포함하고, 없으면 응답에서도 생략한다.
- Success에는 `data`만, Fail에는 `failure`만 포함하며 두 필드를 동시에 포함하지 않는다.
- 반환할 결과 데이터가 없는 Success도 `data`를 빈 object로 제공한다.
- notification에는 `result`, `data`와 `failure`를 공통 response envelope 용도로 추가하지 않는다.

## Failure 필드

- `code`: client가 분기와 복구 판단에 사용하는 안정적인 failure code
- `message`: 사용자가 읽을 수 있는 실패 설명
- `details`: 구조화된 선택 부가정보이며 없으면 생략

failure code와 내부 정보 비노출 규칙은 [Failure Code](failure_codes.md)를 따른다.
구체적인 내부 Exception 계층과 mapper는 다음 설계 단계에서 확정한다.

## 비동기 명령의 Success

비동기 명령의 Success는 요청이 승인되어 작업을 시작했다는 의미이며 작업 완료를 의미하지 않는다.
진행, 완료, 중단과 Diagnostic 발생은 후속 status 또는 notification으로 전달한다.

## Migration 대상

목표 계약에서는 다음 기존 표현을 제거한다.

- `ok`
- `accepted`
- `reason`
- 최상위 `error`
- 실패 응답의 `type: command_rejected`

호환 기간에 기존 필드와 새 envelope를 함께 보낼지는 TD-005 구현 계획에서 별도로 결정한다.
