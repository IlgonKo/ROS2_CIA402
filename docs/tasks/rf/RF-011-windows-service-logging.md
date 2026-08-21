# RF-011 Windows Service 실행 및 파일 로그 옵션

## 사용자 가치

Windows EtherCAT host에서 사용자 로그인이나 열린 terminal 없이 Motion Server를 자동 실행하고,
startup·runtime·fault 기록을 파일로 보존해 운영 및 장애 분석에 사용할 수 있게 한다.

## 실행 모드

- 기존 foreground/console 실행은 개발, 설정 확인과 수동 진단 용도로 유지한다.
- Windows Service 실행은 설치 시 사용자가 선택할 수 있는 운영 옵션으로 제공한다.
- 두 실행 모드는 동일한 executable, configuration schema와 device catalog를 사용한다.

## Service 구현 범위

- service install/uninstall과 start/stop/restart/status 명령을 제공한다.
- Windows boot 시 자동 시작 여부와 service recovery 정책을 설정할 수 있게 한다.
- stop/shutdown 요청에서 EtherCAT output과 runtime resource를 안전하게 정리한다.
- service account, working directory, configuration/catalog 경로와 권한 요구사항을 문서화한다.
- 이미 실행 중인 foreground instance 또는 동일 TCP port와 충돌할 때 명확한 오류를 제공한다.

## 파일 로그 범위

- console과 file output의 활성 여부 및 log level을 설정할 수 있게 한다.
- 기본 log directory와 파일명에 Motion Server instance 및 날짜를 식별할 수 있는 규칙을 사용한다.
- size 또는 time 기반 rotation과 retention 개수/기간을 설정할 수 있게 한다.
- initialization error, connection, authority, command rejection, EtherCAT fault와 recovery를 보존한다.
- log directory 생성/쓰기 실패 시 service startup 정책과 Windows Event Log 또는 대체 진단 경로를 정의한다.
- password, token 또는 불필요한 전체 environment 값은 기록하지 않는다.

## Packaging 및 Migration

- Windows standalone package에 service 관리 도구와 필요한 runtime dependency를 포함한다.
- 설치 경로 변경은 [TD-019](../td/TD-019-project-path-migration.md), legacy service 식별자 migration은
  [TD-020](../td/TD-020-legacy-runtime-identifiers.md)과 조율한다.
- 설치 및 사용자 문서 반영은 [RF-006](RF-006-deployment-validation.md)과
  [RF-010](RF-010-user-documentation.md)의 검증 범위에 포함한다.

## 검증 계획

- clean Windows PC에서 install/start/status/restart/stop/uninstall lifecycle을 검증한다.
- Windows 재부팅 후 자동 시작과 Motion Server TCP 연결을 확인한다.
- 정상 종료, initialization failure, process crash와 configured recovery 동작을 검증한다.
- log rotation/retention, 동시 write, disk/write failure와 restart 후 로그 연속성을 검증한다.
- foreground와 service mode가 동일 설정에서 같은 axis/I/O 구성을 생성하는지 비교한다.

## 완료 증거

완료 시 service lifecycle 기록, configuration 표, packaging manifest, 대표 log와 clean-system 시험 결과를 추가한다.
