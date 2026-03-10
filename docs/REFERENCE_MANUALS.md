# 참고 매뉴얼 및 다운로드 센터

PLC 통신 프로토콜 개발 시 참고할 매뉴얼 목록과 각 제조사 다운로드 센터 링크.
PDF 파일은 용량 문제로 GitHub에 포함하지 않음.

---

## LS ELECTRIC (LS산전)

### 보유 매뉴얼

| 파일명 | 내용 | 용량 |
|--------|------|------|
| `XGB_Series_KO_202407.pdf` | XGB 시리즈 종합 카탈로그 (CPU, I/O, 통신모듈 사양 등) | 31MB |
| `XGL-C22B_T6_Manual_V3.2_202111_KR.pdf` | XGL-C22B Cnet 통신 모듈 사용설명서 (RS-232C/RS-485 설정, 접속 방법) | 11MB |
| `사용설명서_XGB Cnet_국문_V2.3_20251124.pdf` | **XGT Cnet 프로토콜 상세 스펙** — 프레임 구조, 명령어, BCC 계산, 에러코드 등 | 10MB |
| `사용설명서_XGB FEnet_국문_V2.1_20260209.pdf` | XGB FEnet (이더넷) 통신 프로토콜 스펙. TCP/UDP 기반 XGT 통신용 | 12MB |

### 다운로드 센터

- https://www.ls-electric.com → 고객지원 → 다운로드 센터
- 검색 키워드: "XGB Cnet", "XGB FEnet", "XGT 프로토콜"

### 주로 참고한 부분

- **Cnet 매뉴얼**: XGT 시리얼 프로토콜 프레임 구조 (ENQ/ACK/NAK, BCC 계산, 명령어 포맷)
- **XGL-C22B 매뉴얼**: RS-232C 핀 배치, 통신 파라미터 설정 방법
- **FEnet 매뉴얼**: TCP 기반 XGT 프로토콜 (이더넷 연결 시 참고)

---

## Mitsubishi Electric (미쓰비시)

### 다운로드 센터

- https://www.mitsubishielectric.co.jp/fa/download/search.do → 매뉴얼 검색
- https://www.mitsubishielectric.com/fa/products/cnt/plcnet/pmerit/index.html → CC-Link / MELSEC 통신

### 필요 매뉴얼 (MC Protocol)

| 검색 키워드 | 내용 |
|-------------|------|
| MELSEC Communication Protocol | MC Protocol 프레임 구조 (3E/4E 프레임) |
| QJ71C24N | 시리얼 통신 모듈 사용설명서 |
| GX Works2/3 | 프로그래밍 소프트웨어 (디바이스 모니터 확인용) |

---

## KEYENCE (키엔스)

### 다운로드 센터

- https://www.keyence.co.jp/downloads/ → KV 시리즈 매뉴얼
- 계정 로그인 필요

### 필요 매뉴얼 (MC Protocol 호환)

| 검색 키워드 | 내용 |
|-------------|------|
| KV-8000/7000 시리즈 통신 | 상위 링크 통신 매뉴얼 |
| KV STUDIO | 프로그래밍 소프트웨어 |

> 키엔스 PLC는 미쓰비시 MC Protocol 호환 모드를 지원하므로, MC Protocol 드라이버로 통신 가능.

---

## Panasonic (파나소닉)

### 다운로드 센터

- https://industrial.panasonic.com/ac/e/dl/ → PLC 매뉴얼
- https://www3.panasonic.biz/ac/j/fasys/plc/ → FP 시리즈

### 필요 매뉴얼 (MEWTOCOL)

| 검색 키워드 | 내용 |
|-------------|------|
| MEWTOCOL-COM | MEWTOCOL 통신 프로토콜 상세 스펙 |
| FP-X / FP7 시리즈 통신 | 시리얼(RS-485) 통신 설정 |
| FPWIN GR/Pro | 프로그래밍 소프트웨어 |

> 파나소닉 PLC 일부 모델은 이더넷 포트가 없어 RS-485 시리얼 통신만 가능.

---

## 공통 참고

| 자료 | 링크 |
|------|------|
| pyserial 문서 | https://pyserial.readthedocs.io/ |
| RS-232C 핀 배치 | https://en.wikipedia.org/wiki/RS-232 |
| RS-485 규격 | https://en.wikipedia.org/wiki/RS-485 |
