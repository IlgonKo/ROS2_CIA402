# RF-010 사용자 문서 최신화

## 목표

사용자 및 설치 매뉴얼을 최신 Motion Server, Control Panel, device profile과 Remote I/O 동작에 맞춘다.

## 구현 범위

- User Manual에 최신 API namespace, authority, axis/I/O feedback, parameter access와 Basic mode를 반영한다.
- Installation Manual에 Windows package와 Linux Docker 설치 및 설정 절차를 반영한다.
- `config.txt`/`.env`, ESI/IODD 배치, startup, log와 기본 troubleshooting을 설명한다.
- 문서 파일명, 내부 링크, version과 packaging 포함 규칙을 정리한다.

## 범위 제외

개발자용 상세 내부 구조는 architecture 문서에서 유지하고 사용자 매뉴얼에 중복하지 않는다.

## 검증 계획

- 최신 API/configuration과 문서 항목을 대조한다.
- Windows/Linux에서 문서만 사용해 Basic mode 설치와 smoke test를 수행한다.
- 최종 DOCX/PDF는 rendering 후 페이지 잘림, 표, 이미지와 링크를 확인한다.

## 완료 증거

완료 시 문서 version, review checklist, rendering 결과와 신규 환경 재현 기록을 추가한다.
