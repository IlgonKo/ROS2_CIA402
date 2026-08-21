# TD-019 프로젝트·저장소 및 설치 경로 변경

## 배경 및 현재 구조

공식 프로젝트명은 Motion Server지만 repository와 설치 경로에는 과거 실험 프로젝트명이 남아 있다.

- GitHub repository: `ROS2_CIA402`
- Windows workspace: `ROS2_CIA402\virtual_ethercat`
- Linux workspace: `/home/festo/Documents/ROS_CIA402/virtual_ethercat`
- sync script가 `virtual_ethercat` project root와 기존 remote root를 전제로 한다.

## 문제와 위험

- 사용자에게 보이는 프로젝트명과 checkout/install 경로가 일치하지 않는다.
- 경로를 즉시 변경하면 기존 shortcut, sync script, service working directory와 문서가 중단될 수 있다.
- Git repository 자체 이름 변경과 로컬 directory 이동을 동시에 수행하면 rollback과 원인 분석이 어렵다.

## 선행 결정

- GitHub repository 목표 이름
- 로컬 repository root와 상위 workspace의 목표 구조
- Linux 기본 설치 경로
- 경로 migration 적용 순서와 기존 경로 지원 기간

## 구현 범위

- GitHub repository와 clone URL 변경 절차를 정의한다.
- Windows/Linux local path 및 sync destination을 새 기본 경로로 변경한다.
- script가 repository directory 이름을 고정 비교하지 않고 명시적인 project root를 사용하게 한다.
- 문서, 설정 예제와 service working directory를 새 경로에 맞춘다.
- 기존 checkout을 이동하거나 remote URL을 갱신하는 migration 및 rollback 절차를 제공한다.

## 범위 제외

- Docker image/container, systemd unit와 환경변수 이름은 [TD-020](TD-020-legacy-runtime-identifiers.md)에서 처리한다.
- ROS package와 robot identifier 변경은 [RF-008](../rf/RF-008-ros-bridge-migration.md)에서 처리한다.
- 사용자 노출 `Axis Server` 문구 변경은 [TD-003](TD-003-axis-server-naming.md)에서 처리한다.

## 검증 계획

- 새 GitHub URL에서 clean clone하고 repository 내부 link와 script를 검사한다.
- Windows에서 새 경로를 사용해 Linux 새 경로로 one-shot/watch sync를 수행한다.
- 새 Linux 경로에서 Docker Basic mode startup과 service working directory를 확인한다.
- 기존 경로에서 migration과 rollback 절차를 각각 한 번 재현한다.

## 완료 증거

완료 시 경로 mapping, repository rename 기록, migration/rollback 결과와 clean-system 시험 기록을 추가한다.
