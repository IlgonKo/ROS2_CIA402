# TD-021 Windows 실행 스크립트의 PYTHONPATH 중복 및 진단 출력 정리

## 배경 및 현재 구조

Windows 실행 스크립트는 시작할 때 다음 방식으로 project root를 기존 `PYTHONPATH` 앞에 추가하고
전체 값을 진단 로그로 출력한다.

```powershell
$env:PYTHONPATH = "$ProjectRoot;$env:PYTHONPATH"
Write-Host "PYTHONPATH=$env:PYTHONPATH"
```

같은 PowerShell process에서 script를 반복 실행하면 동일한 project root가 계속 누적된다.

## 관련 위치

- `scripts/windows/motion_server.ps1`
- `scripts/windows/axis_panel.ps1`
- `scripts/windows/io_panel.ps1`

## 문제와 위험

- 반복 실행할 때마다 환경변수와 로그가 불필요하게 길어진다.
- 실제 project root 확인보다 중복된 검색 경로가 더 많이 노출된다.
- 외부에서 전달된 유효한 `PYTHONPATH` 항목을 보존하면서 중복만 제거해야 한다.

## 목표 구조 및 구현 범위

- `PYTHONPATH`를 path separator로 분리하고 빈 항목을 제거한다.
- Windows path 비교 규칙에 맞게 project root 중복을 대소문자 구분 없이 제거한다.
- project root를 정확히 한 번만 첫 번째 항목으로 추가한다.
- 정상 로그에는 `Project root: <resolved path>`만 출력하고 전체 `PYTHONPATH`는 출력하지 않는다.
- 세 실행 스크립트가 동일한 처리 규칙을 사용한다.

## 범위 제외

- Docker의 `/workspace` `PYTHONPATH` 설정은 변경하지 않는다.
- 프로젝트 및 설치 경로 자체의 변경은 [TD-019](TD-019-project-path-migration.md)에서 처리한다.

## 검증 계획

- 빈 값, project root 없음, 한 번 포함, 여러 번 포함과 대소문자 차이 입력을 검증한다.
- 외부 경로가 있는 경우 값과 상대적 순서가 보존되는지 확인한다.
- 같은 PowerShell process에서 각 script를 반복 실행해 항목 수가 증가하지 않는지 확인한다.
- PowerShell parser 검사와 대표 launcher smoke test를 수행한다.

## 완료 증거

완료 시 변경된 공통 처리 방식, 반복 실행 결과와 PowerShell 검증 결과를 기록한다.
