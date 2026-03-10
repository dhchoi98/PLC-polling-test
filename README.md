# PLC Polling Communication Test

다양한 PLC에 대해 **폴링 방식 데이터 읽기**의 통신 가능 여부와 응답 속도를 검증하는 범용 테스트 프로그램.

## 지원 범위

| 구분 | 현재 구현 | 확장 예정 |
|------|-----------|-----------|
| **프로토콜** | LS XGT Cnet | MC Protocol (미쓰비시/키엔스), MEWTOCOL (파나소닉) |
| **전송 방식** | RS-232C, TCP/IP | RS-485, 이더넷 (통신모듈 경유) |
| **연결 대상** | CPU 내장 시리얼 포트 | Cnet/FEnet 통신모듈, 시리얼-이더넷 변환기 |

## 아키텍처

```
scripts (테스트 실행)
    ↓
src/drivers/        (프로토콜 변환: 요청 조립 ↔ 응답 파싱)
  ├── xgt_protocol  — LS산전
  ├── mc_protocol   — 미쓰비시/키엔스 (예정)
  └── mewtocol      — 파나소닉 (예정)
    ↓
src/transport/      (바이트 송수신)
  ├── serial        — RS-232C / RS-485
  └── tcp           — 이더넷 / 변환기
    ↓
PLC
```

드라이버(프로토콜)와 전송 계층을 추상 인터페이스(`base.py`)로 분리하여, 새로운 PLC 프로토콜이나 전송 방식을 추가해도 테스트 스크립트는 수정 없이 사용 가능.

## 프로젝트 구조

```
├── config.yaml                 # PLC 연결 설정 + 읽을 디바이스 목록
│
├── src/
│   ├── drivers/
│   │   ├── base.py             # PLCDriver 추상 인터페이스
│   │   └── xgt_protocol.py     # LS XGT Cnet Protocol 드라이버
│   ├── transport/
│   │   ├── base.py             # Transport 추상 인터페이스
│   │   ├── serial_transport.py # RS-232C / RS-485 시리얼 전송
│   │   └── tcp_transport.py    # TCP 전송 (이더넷/변환기용)
│   └── utils.py                # 로깅, 바이트 변환 유틸리티
│
├── tests/
│   └── test_xgt_frame.py       # XGT 프레임 조립/파싱 단위 테스트
│
├── scripts/
│   ├── scan_serial_ports.py    # 시리얼 포트 스캔
│   ├── single_read.py          # 1회 읽기 테스트
│   ├── polling_test.py         # 반복 폴링 + 소요 시간 측정
│   ├── multi_device_timing.py  # 순차 읽기 시간 측정 (N대 추정)
│   └── memory_scan.py          # 메모리 영역 스캔 (사용 중인 주소 탐색)
│
└── docs/
    ├── LEARNING_GUIDE.md       # 프로젝트 학습 가이드
    └── REFERENCE_MANUALS.md    # 참고 매뉴얼 목록
```

## 설치

```bash
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 사용법

### 1. 시리얼 포트 확인

USB-RS232C 케이블을 연결한 뒤:

```bash
python scripts/scan_serial_ports.py
```

확인된 포트 번호를 `config.yaml`의 `port`에 설정.

### 2. config.yaml 수정

```yaml
plc:
  protocol: "xgt"          # 프로토콜 선택
  connection: "serial"     # serial 또는 ethernet

  serial:
    port: "COM3"           # ← 실제 포트 번호
    baudrate: 9600         # ← PLC 설정과 일치해야 함

  ethernet:
    host: "192.168.1.100"  # ← PLC 또는 변환기 IP
    port: 2004
```

### 3. 1회 읽기 테스트

```bash
python scripts/single_read.py
```

```
[OK] PLC 연결 성공: COM3 @ 9600bps
[READ] D0=1234, D1=5678, D2=0, ...
[OK] 소요 시간: 47.3ms
```

### 4. 반복 폴링 테스트

```bash
python scripts/polling_test.py
```

1초 간격으로 반복 읽기. `Ctrl+C`로 종료 시 통계 출력.

### 5. 순차 읽기 시간 측정

```bash
python scripts/multi_device_timing.py
```

N회 연속 읽기로 다수 PLC 순차 폴링 시간을 추정.

## 성공 기준

| 항목 | 기준 |
|------|------|
| 기본 통신 | PLC 디바이스 값이 정상적으로 읽힘 |
| 데이터 정합성 | 읽은 값이 PLC 모니터링 소프트웨어 값과 일치 |
| 안정성 | 60초 이상 연속 폴링 시 통신 에러 없음 |
| 1회 읽기 속도 | 200ms 이내 (9600bps 기준) |

## 주의사항

- **읽기(Read) 전용** — 쓰기(Write) 명령은 절대 사용하지 않음
- 가동 중인 PLC에 영향을 주지 않도록 주의
- 시리얼 포트에 다른 장비(HMI 등)가 연결되어 있으면 분리 후 테스트

## 참고 자료

- [pyserial 문서](https://pyserial.readthedocs.io/)
- 매뉴얼 상세 목록: [docs/REFERENCE_MANUALS.md](docs/REFERENCE_MANUALS.md)
- 프로젝트 학습 가이드: [docs/LEARNING_GUIDE.md](docs/LEARNING_GUIDE.md)
