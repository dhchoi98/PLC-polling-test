# PLC Polling Communication Test

LS산전 XGB PLC에 시리얼(RS-232C)로 연결하여 **폴링 방식 데이터 읽기**의 가능 여부와 속도를 검증하는 테스트 프로젝트.

## 왜 이 테스트를 하는가?

20대 PLC의 생산 데이터를 수집하는 POP System 개발을 앞두고 있다.
그 중 일부 PLC는 이더넷 포트가 없어 **시리얼 통신**이 유일한 방법이다.

이 프로젝트로 검증하려는 것:

1. 래더 프로그램 수정 없이, PC에서 PLC 메모리를 읽어올 수 있는가?
2. 시리얼 폴링으로 20대를 순차 읽기할 때 현실적인 시간 안에 가능한가?

## 테스트 환경

| 항목 | 내용 |
|------|------|
| PLC | LS산전 XGB DR32H (CPU 내장 시리얼 포트) |
| 연결 | RS-232C (USB-RS232C 컨버터 경유) |
| 프로토콜 | LS XGT Cnet Protocol |
| 언어 | Python 3.11+ |

## 프로젝트 구조

```
├── config.yaml                 # PLC 연결 설정 + 읽을 디바이스 목록
│
├── src/
│   ├── drivers/
│   │   ├── base.py             # PLCDriver 추상 인터페이스
│   │   └── xgt_protocol.py     # LS XGT Protocol 드라이버
│   ├── transport/
│   │   ├── base.py             # Transport 추상 인터페이스
│   │   ├── serial_transport.py # RS-232C 시리얼 전송
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
│   ├── multi_device_timing.py  # 순차 읽기 시간 측정 (20대 추정)
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
serial:
  port: "COM3"       # ← 실제 포트 번호
  baudrate: 9600     # ← PLC 설정과 일치해야 함
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

20회 연속 읽기로 20대 PLC 순차 폴링 시간을 추정.

## 성공 기준

| 항목 | 기준 |
|------|------|
| 기본 통신 | PLC 디바이스 값이 정상적으로 읽힘 |
| 데이터 정합성 | 읽은 값이 XG5000 모니터 값과 일치 |
| 안정성 | 60초 이상 연속 폴링 시 통신 에러 없음 |
| 1회 읽기 속도 | 200ms 이내 (9600bps 기준) |
| 20대 환산 | 5초 이내 (실시간 폴링 가능 판단) |

## 아키텍처

```
scripts (테스트 실행)
    ↓
drivers/xgt_protocol.py (프로토콜 변환: 요청 조립 ↔ 응답 파싱)
    ↓
transport/serial_transport.py (바이트 송수신)
    ↓
RS-232C 케이블 → PLC
```

드라이버와 전송 계층을 추상 인터페이스로 분리하여, 향후 다른 PLC 프로토콜(MC Protocol, MEWTOCOL)이나 다른 전송 방식(TCP/IP)으로 확장 가능.

## 주의사항

- **읽기(Read) 전용** — 쓰기(Write) 명령은 절대 사용하지 않음
- 가동 중인 PLC에 영향을 주지 않도록 주의
- 시리얼 포트에 다른 장비(HMI 등)가 연결되어 있으면 분리 후 테스트

## 참고 자료

- [LS ELECTRIC 다운로드 센터](https://www.ls-electric.com) — XGT Cnet/FEnet 프로토콜 매뉴얼
- [pyserial 문서](https://pyserial.readthedocs.io/)
- 매뉴얼 상세 목록: [docs/REFERENCE_MANUALS.md](docs/REFERENCE_MANUALS.md)
- 프로젝트 학습 가이드: [docs/LEARNING_GUIDE.md](docs/LEARNING_GUIDE.md)
