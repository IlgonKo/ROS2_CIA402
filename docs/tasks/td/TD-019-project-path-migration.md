# TD-019 프로젝트·저장소 및 설치 경로 변경

## 배경 및 현재 구조

공식 프로젝트명은 Motion Server지만 repository와 설치 경로에는 과거 실험 프로젝트명이 남아 있다.

- GitHub repository: `ROS2_CIA402`
- Windows workspace: `ROS2_CIA402\virtual_ethercat`
- Linux workspace: `/home/festo/Documents/ROS_CIA402/virtual_ethercat`
- sync script가 `virtual_ethercat` project root와 기존 remote root를 전제로 한다.

## 문제와 위험

- 사용자에게 보이는 프로젝트명과 checkout/install 경로가 일치하지 않는다.
- 경로를 즉시 변경하면 기존 shortcut, service working directory와 문서가 중단될 수 있다.
- Git repository 자체 이름 변경과 로컬 directory 이동을 동시에 수행하면 rollback과 원인 분석이 어렵다.

## 확정 결정

- GitHub repository는 `IlgonKo/ROS2_CIA402`에서 `IlgonKo/motion-server`로 변경한다.
- Windows repository root는 `C:\Users\Festo\Documents\motion-server`를 사용한다.
- Linux repository root는 `/home/festo/Documents/motion-server`를 사용한다.
- 이전 경로 alias나 fallback은 두지 않고 직접 전환한다. 아직 외부 배포되지 않았으므로
  이전 checkout은 rollback을 위한 임시 보관본으로만 취급한다.
- 적용 순서는 script·문서의 고정 경로 제거, GitHub repository rename, remote URL 변경,
  로컬 directory 이동 순서로 한다.
- Windows-to-Linux archive sync는 대상 Git checkout과 `.env`를 삭제할 수 있으므로 제거한다.
  Linux source update는 GitHub clone과 `git pull --ff-only`로 통일하고 `.env`는 host에 유지한다.
- Docker/systemd 실행 식별자는 TD-020, ROS 전용 식별자는 RF-008에서 별도로 변경한다.

## 구현 범위

- GitHub repository와 clone URL 변경 절차를 정의한다.
- Windows/Linux local path를 새 기본 경로로 변경한다.
- destructive Windows-to-Linux sync script와 관련 안내를 제거한다.
- 문서, 설정 예제와 service working directory를 새 경로에 맞춘다.
- 기존 checkout을 이동하고 remote URL을 갱신하는 migration 및 rollback 절차를 제공한다.

## Migration

1. 작업 트리가 clean이고 현재 branch가 원격에 push되었는지 확인한다.
2. GitHub repository를 `IlgonKo/motion-server`로 rename한다.
3. `origin`을 `https://github.com/IlgonKo/motion-server.git`로 변경한다.
4. Windows repository를 `C:\Users\Festo\Documents\motion-server`로 이동한다.
5. Linux checkout을 `/home/festo/Documents/motion-server`에 clone하고 기존 `.env`를 보존한다.
6. 새 경로에서 test, Windows launcher, Linux Basic mode startup을 검증한다.

## Rollback

1. 실행 중인 Motion Server를 중지한다.
2. 로컬 directory를 이전 경로로 되돌린다.
3. `origin`을 이전 repository URL로 되돌린다.
4. 필요할 때 GitHub repository 이름을 `ROS2_CIA402`로 되돌린다.
5. 이전 경로에서 기본 검사와 startup을 다시 수행한다.

Rollback은 이전 이름을 코드에서 동시에 지원하는 호환 계층이 아니라 migration 자체를
취소하는 절차다.

## 범위 제외

- Docker image/container, systemd unit와 환경변수 이름은 [TD-020](TD-020-legacy-runtime-identifiers.md)에서 처리한다.
- ROS package와 robot identifier 변경은 [RF-008](../rf/RF-008-ros-bridge-migration.md)에서 처리한다.
- 사용자 노출 `Axis Server` 문구 변경은 [TD-003](TD-003-axis-server-naming.md)에서 처리한다.

## 검증 계획

- 새 GitHub URL에서 clean clone하고 repository 내부 link와 script를 검사한다.
- Linux에서 새 GitHub URL을 clone하고 `git pull --ff-only`로 갱신한다.
- 새 Linux 경로에서 Docker Basic mode startup과 service working directory를 확인한다.
- 기존 경로에서 migration과 rollback 절차를 각각 한 번 재현한다.

## 완료 증거

### 완료

- 2026-08-26: GitHub repository를 `IlgonKo/motion-server`로 rename하고 default branch가
  `main`인지 확인했다.
- 2026-08-26: `origin`을 `https://github.com/IlgonKo/motion-server.git`로 변경하고
  `main`과 `td/019-project-path-migration` branch 조회를 확인했다.
- 2026-08-26: `C:\Users\Festo\Documents\motion-server`에 새 URL로 clean clone했다.
- clean clone에서 optional `.env`가 없는 조건을 반영하고 전체 unittest 265개,
  legacy naming 검사, PowerShell parser 및 `git diff --check`를 통과했다.
- 기존 checkout은 Codex desktop process가 directory를 사용 중이라 이동할 수 없으므로
  현재 작업 종료 후 제거 가능한 rollback 사본으로 보존했다.

- 2026-08-26: Linux host에서 새 GitHub repository의 최신 코드를 받아
  `/home/festo/Documents/motion-server` 경로의 Motion Server 구동에 성공했다.
- destructive sync script를 제거하고 Linux 갱신 계약을 Git clone/pull로 단일화했다.
