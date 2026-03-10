# 참고 매뉴얼 목록

이 프로젝트에서 참고한 LS산전 PLC 관련 매뉴얼 목록.
PDF 파일은 용량 문제로 GitHub에 포함하지 않음. LS산전 홈페이지에서 다운로드 가능.

## 매뉴얼 목록

| 파일명 | 내용 | 용량 |
|--------|------|------|
| `XGB_Series_KO_202407.pdf` | XGB 시리즈 종합 카탈로그 (CPU, I/O, 통신모듈 사양 등) | 31MB |
| `XGL-C22B_T6_Manual_V3.2_202111_KR.pdf` | XGL-C22B Cnet 통신 모듈 사용설명서 (RS-232C/RS-485 설정, 접속 방법) | 11MB |
| `사용설명서_XGB Cnet_국문_V2.3_20251124.pdf` | **XGT Cnet 프로토콜 상세 스펙** — 프레임 구조, 명령어, BCC 계산, 에러코드 등. 이 프로젝트의 핵심 참고자료 | 10MB |
| `사용설명서_XGB FEnet_국문_V2.1_20260209.pdf` | XGB FEnet (이더넷) 통신 프로토콜 스펙. TCP/UDP 기반 XGT 통신용 | 12MB |

## 다운로드

LS산전(현 LS ELECTRIC) 홈페이지에서 다운로드:
- https://www.ls-electric.com → 고객지원 → 다운로드 센터
- "XGB Cnet", "XGB FEnet" 등으로 검색

## 이 프로젝트에서 주로 참고한 부분

- **Cnet 매뉴얼**: XGT 시리얼 프로토콜 프레임 구조 (ENQ/ACK/NAK, BCC 계산, 명령어 포맷)
- **XGL-C22B 매뉴얼**: RS-232C 핀 배치, 통신 파라미터 설정 방법
- **FEnet 매뉴얼**: TCP 기반 XGT 프로토콜 (이더넷 연결 시 참고)
