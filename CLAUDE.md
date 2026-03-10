# PLC 폴링 통신 테스트 프로젝트

## 테스트 목적

1. **PLC에서 폴링 방식으로 데이터를 제대로 가져올 수 있는가?**
   - 래더 프로그램 수정 없이, PC에서 PLC 디바이스 메모리(D, M 등)를 읽어올 수 있는지 검증
   - 통신 모듈 없이 PLC CPU 내장 포트만으로 통신 가능한지 검증

2. **시리얼 방식으로 순차 폴링 시 시간이 얼마나 걸리는가?**
   - 1대 읽는 데 걸리는 시간 측정 (ms)
   - N대를 순차적으로 읽을 때 총 소요 시간 추정 (실제 프로젝트는 20대)
   - 1~5초 주기 폴링이 현실적인지 판단할 근거 확보

## 테스트 환경

- **PLC**: LS산전 XGB DR32H (CPU 모듈)
- **연결**: RS-232C (PLC CPU 내장 시리얼 포트) — USB-RS232C 컨버터로 노트북 연결
- **PC**: Windows 노트북
- **언어**: Python 3.11+
- **프로토콜**: LS XGT Protocol (시리얼)
- **위치**: 아버지 공장 (가동 중인 실제 PLC)

## ⚠️ 절대 주의

- **래더 프로그램 수정 금지** — 읽기(Read)만 수행
- **쓰기(Write) 명령 사용 금지** — 코드에 write 함수가 있더라도 테스트에서 절대 호출하지 않을 것
- 시리얼 포트에 다른 장비(HMI 등)가 연결되어 있으면 잠깐 분리 후 테스트, 끝나면 원복
- 가동 중인 설비에 영향을 주지 않도록 주의

## 배경 — 왜 이 테스트를 하는가

이후 본 프로젝트에서 20대 PLC(키엔스/미쓰비시/파나소닉)의 생산 데이터를 수집하는 POP System을 개발할 예정이다. 그 중 파나소닉 6대는 이더넷 포트가 없어서 시리얼(RS-485)로 통신해야 한다. 이번 테스트로 시리얼 폴링의 가능 여부와 속도를 검증하여, 본 프로젝트의 기술적 실현 가능성을 사전 확인한다.

LS XGT Protocol은 본 프로젝트에서 쓰는 MC Protocol/MEWTOCOL과 다르지만, "상위 PC에서 PLC 디바이스 메모리를 폴링으로 읽어온다"는 구조는 동일하다. 여기서 성공하면 프로토콜만 바꿔서 같은 패턴을 적용할 수 있다.

## 기술 스택

- Python 3.11+
- pyserial — 시리얼 통신
- struct — 바이트 패킹/언패킹
- time — 소요 시간 측정
- yaml — 설정 파일
- pytest — 단위 테스트

## 프로젝트 구조

```
plc-comm-test/
├── CLAUDE.md                   # 이 파일
├── README.md
├── requirements.txt
├── config.yaml                 # PLC 연결 설정 + 읽을 디바이스 목록
│
├── src/
│   ├── __init__.py
│   ├── drivers/
│   │   ├── __init__.py
│   │   ├── base.py             # PLCDriver 추상 인터페이스
│   │   └── xgt_protocol.py     # LS XGT Protocol 드라이버
│   ├── transport/
│   │   ├── __init__.py
│   │   ├── base.py             # Transport 추상 인터페이스
│   │   └── serial_transport.py # RS-232C 시리얼 전송 계층
│   └── utils.py                # 로깅, 바이트 변환 유틸리티
│
├── tests/
│   ├── __init__.py
│   ├── test_xgt_frame.py       # XGT 프레임 조립/파싱 단위 테스트 (PLC 없이 가능)
│   └── test_live_plc.py        # 실제 PLC 연결 통합 테스트
│
└── scripts/
    ├── scan_serial_ports.py    # 사용 가능한 시리얼 포트 스캔
    ├── single_read.py          # 1회 읽기 테스트
    ├── polling_test.py         # 반복 폴링 + 소요 시간 측정
    └── multi_device_timing.py  # 여러 디바이스 순차 읽기 시간 측정
```

## 구현 상세

### 1. PLCDriver 추상 인터페이스 (src/drivers/base.py)

모든 PLC 프로토콜 드라이버의 공통 인터페이스. 향후 MC Protocol, MEWTOCOL 드라이버도 이 인터페이스를 구현한다.

```python
from abc import ABC, abstractmethod
from typing import List

class PLCDriver(ABC):
    @abstractmethod
    def connect(self) -> None:
        """PLC 연결"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """PLC 연결 해제"""
        pass

    @abstractmethod
    def read_words(self, device: str, address: int, count: int) -> List[int]:
        """
        워드 디바이스 읽기 (16비트 레지스터)
        - device: 디바이스 타입 ("D", "T" 등)
        - address: 시작 주소
        - count: 읽을 워드 수
        - return: 값 리스트
        """
        pass

    @abstractmethod
    def read_bits(self, device: str, address: int, count: int) -> List[bool]:
        """
        비트 디바이스 읽기 (M, P, X, Y 등)
        """
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        pass
```

### 2. Transport 추상 인터페이스 (src/transport/base.py)

프로토콜 드라이버와 물리적 통신 방식을 분리.

```python
from abc import ABC, abstractmethod

class Transport(ABC):
    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def send(self, data: bytes) -> None: ...

    @abstractmethod
    def receive(self, size: int, timeout: float = 1.0) -> bytes: ...

    @property
    @abstractmethod
    def is_open(self) -> bool: ...
```

### 3. SerialTransport (src/transport/serial_transport.py)

pyserial을 래핑한 시리얼 전송 계층.

시리얼 파라미터 (config.yaml에서 읽음):
```yaml
serial:
  port: "COM3"        # 실제 포트 번호 — 현장에서 확인 후 변경
  baudrate: 9600       # PLC 설정에 따라 다름 (9600/19200/38400/115200)
  bytesize: 8
  parity: "none"       # LS산전 기본
  stopbits: 1
  timeout: 1.0         # 초
```

⚠️ 보레이트는 PLC 설정과 반드시 일치해야 함. XG5000에서 확인하거나 아버지에게 문의.

### 4. XGT Protocol 드라이버 (src/drivers/xgt_protocol.py)

LS산전 XGT Protocol 스펙 기반 구현.

#### XGT 시리얼 프레임 구조

```
[Header(2)] [Station No(2)] [PLC Info(2)] [CPU Info(1)] [Source(1)] [Invoke ID(2)] [Length(2)] [Command(2)] [Command Type(2)] [Data...]  [Tail(2)] [BCC(1)]
```

핵심:
- Header: 0x05, 0x00 (ENQ, 고정)
- Tail: 0x04, 0x00 (EOT, 고정)
- BCC: 체크섬 (데이터 영역 XOR)
- Command:
  - 0x0054: Read request (읽기 요청)
  - 0x0055: Read response (읽기 응답)
- Data Type:
  - 0x00: Byte
  - 0x01: Word
  - 0x02: DWord
  - 0x03: LWord
  - 0x04: Bit (연속)
- 바이트 오더: 리틀엔디안 (Little Endian)
- 디바이스 주소 포맷: "%DW00100" = D영역 Word 100번지, "%MW00050" = M영역 Word 50번지

#### 구현할 함수

1. `build_read_request(device, address, count)` → bytes
   - 읽기 요청 프레임 조립
   - 디바이스 주소를 XGT 포맷 문자열로 변환 ("%DW00100" 등)
   - BCC 계산

2. `parse_read_response(data)` → List[int]
   - 응답 프레임 파싱
   - 에러 코드 확인 (0x0000이면 정상)
   - 데이터 영역에서 워드 값 추출

3. `read_words(device, address, count)` → List[int]
   - build_read_request → transport.send → transport.receive → parse_read_response

### 5. 설정 파일 (config.yaml)

```yaml
plc:
  name: "LS-XGB-TEST"
  protocol: "xgt"

  serial:
    port: "COM3"         # ← 현장에서 확인 후 변경
    baudrate: 9600       # ← PLC 설정에 맞춰야 함
    bytesize: 8
    parity: "none"
    stopbits: 1
    timeout: 1.0

  # 읽을 디바이스 목록
  devices:
    - name: "counter_test"
      device: "D"
      address: 0
      count: 10
      type: "word"
      description: "D0~D9 워드 읽기 테스트"

    - name: "bit_status"
      device: "M"
      address: 0
      count: 16
      type: "bit"
      description: "M0~M15 비트 상태 테스트"

# 폴링 테스트 설정
polling:
  interval_sec: 1.0    # 폴링 주기 (초)
  duration_sec: 60     # 테스트 지속 시간 (초)
  log_file: "polling_results.csv"
```

### 6. 테스트 스크립트

#### scripts/scan_serial_ports.py
- 노트북에 연결된 시리얼 포트(COM 포트) 목록 출력
- USB-RS232C 컨버터가 몇 번 포트로 잡혔는지 확인용

#### scripts/single_read.py
- PLC에 1회 연결 → 디바이스 값 읽기 → 출력 → 종료
- 가장 먼저 실행할 스크립트 (통신 되는지 기본 확인)
- 성공 시 출력 예시:
  ```
  [OK] PLC 연결 성공: COM3 @ 9600bps
  [READ] D0=1234, D1=5678, D2=0, D3=0, D4=42, D5=0, D6=0, D7=0, D8=0, D9=100
  [OK] 소요 시간: 47.3ms
  ```

#### scripts/polling_test.py (핵심 테스트 #1)
- 설정된 주기(1초)로 반복 폴링
- 매 사이클마다:
  - 읽기 요청 시작 시간 기록
  - config의 모든 디바이스 읽기
  - 완료 시간 기록
  - 소요 시간(ms) 계산
- 결과를 CSV로 저장:
  ```csv
  cycle,timestamp,device,address,value,elapsed_ms
  1,2025-03-05 14:30:01.123,D,0,1234,45.2
  1,2025-03-05 14:30:01.168,D,10,5678,42.8
  2,2025-03-05 14:30:02.125,D,0,1235,44.9
  ```
- Ctrl+C로 종료 시 통계 출력:
  ```
  === 폴링 테스트 결과 ===
  총 사이클: 60
  1회 읽기 평균: 45.3ms
  1회 읽기 최소: 38.1ms
  1회 읽기 최대: 62.7ms
  전체 사이클 평균: 92.1ms
  통신 에러: 0회
  ```

#### scripts/multi_device_timing.py (핵심 테스트 #2)
- 동일 PLC에 연속 읽기를 20번 반복 수행
- 마치 20대 PLC를 순차 폴링하는 것과 유사한 시간 측정
- 출력 예시:
  ```
  === 순차 읽기 시간 측정 (20회 반복) ===
  1회차: 46.2ms
  2회차: 44.8ms
  ...
  20회차: 45.1ms
  ---
  합계: 903.4ms
  평균: 45.2ms/회
  ---
  20대 PLC 순차 폴링 추정 시간: 약 903ms (1초 이내)
  → 1초 폴링 주기 가능 여부: ✅ 가능
  ```

### 7. 단위 테스트 (tests/test_xgt_frame.py)

PLC 없이 실행 가능한 테스트:

1. **프레임 조립 테스트**
   - `build_read_request("D", 0, 10)`이 올바른 바이트 시퀀스를 생성하는지
   - 디바이스 주소 변환이 정확한지 ("%DW00000")
   - BCC 계산이 맞는지

2. **프레임 파싱 테스트**
   - 정상 응답 바이트를 넣으면 올바른 값 리스트가 나오는지
   - 에러 응답을 넣으면 예외가 발생하는지

3. **디바이스 주소 변환 테스트**
   - ("D", 0) → "%DW00000"
   - ("D", 100) → "%DW00100"
   - ("M", 50) → "%MW00050"

## 구현 우선순위

### Phase 1: 프레임 레벨 (PLC 없이 — 집에서 가능)
1. PLCDriver, Transport 추상 인터페이스 정의
2. XGT 프레임 조립 함수 (read request)
3. XGT 프레임 파싱 함수 (read response)
4. BCC 계산 함수
5. 디바이스 주소 변환 함수
6. 단위 테스트 (test_xgt_frame.py)

### Phase 2: 전송 레벨 (PLC 없이 — 집에서 가능)
7. SerialTransport 구현
8. config.yaml 로더
9. scan_serial_ports.py 스크립트

### Phase 3: 통합 테스트 (PLC 연결 필요 — 아버지 공장)
10. XGTProtocolDriver 전체 조립
11. single_read.py로 1회 읽기 성공 확인
12. polling_test.py로 반복 폴링 + 시간 측정
13. multi_device_timing.py로 순차 읽기 시간 측정
14. 결과 CSV + 통계 → 본 프로젝트 근거 자료로 보관

## 현장에서 확인할 것 (아버지에게 물어볼 것)

- [ ] PLC 시리얼 포트 보레이트 설정값 (9600? 19200? 115200?)
- [ ] 시리얼 포트에 현재 연결된 장비가 있는지 (있으면 잠깐 분리 가능한지)
- [ ] 래더에서 값이 변하는 D레지스터 주소 하나 (카운터 등 — 값이 올라가는 걸 눈으로 확인하기 위해)
- [ ] USB-RS232C 케이블 준비 (없으면 구매 필요)

## 성공 기준

1. ✅ single_read.py로 PLC 디바이스 값이 정상적으로 읽힘
2. ✅ 읽어온 값이 XG5000 디바이스 모니터에서 보이는 값과 일치
3. ✅ 폴링 테스트에서 통신 에러 없이 60초 이상 연속 동작
4. ✅ 1회 읽기 소요 시간이 200ms 이내 (시리얼 9600bps 기준)
5. ✅ 20대 환산 추정 시간이 5초 이내 (실시간 폴링 가능 판단)

## 참고 자료

- LS산전 XGT Protocol 매뉴얼: LS산전 홈페이지 다운로드 센터에서 "XGT FEnet, Cnet 통신 프로토콜" 검색
- XG5000: LS산전 PLC 프로그래밍 소프트웨어 (디바이스 모니터 + 통신 파라미터 확인용)
- pyserial 문서: https://pyserial.readthedocs.io/