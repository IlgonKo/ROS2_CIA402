# RF-006 배포 구성 최종 검증

## 목표

새로운 Windows와 Linux system에서 배포 artifact와 설치 문서만으로 Basic mode를 재현한다.

## 구현 범위

- Windows package의 Motion Server, Axis/IO Control Panel, tools와 manual 포함 내용을 검증한다.
- Linux Docker `.env`와 Windows `config.txt`의 지원 설정을 비교한다.
- CMMT-AS/ST, CPX-AP-I-EC ESI와 IODD의 포함, 검색 및 version 선택 규칙을 확정한다.
- package version, log 위치와 진단 정보 수집 방법을 확인한다.

## 기술 제약

개발 PC의 기존 Python, Docker image, environment와 cached catalog에 의존하지 않는 clean-system 검증이 필요하다.

## 검증 계획

- 새 Windows PC에서 설치, NIC 선택, startup와 Basic mode smoke test를 수행한다.
- 새 Linux PC에서 Docker 설치, EtherCAT NIC 설정, startup와 Basic mode smoke test를 수행한다.
- 누락 catalog, 잘못된 설정과 upgrade scenario를 확인한다.

## 완료 증거

완료 시 artifact manifest, 환경별 checklist와 clean-system 시험 결과를 기록한다.
