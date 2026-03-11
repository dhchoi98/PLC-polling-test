# PLC 폴링 통신 테스트 — 실행 계획

## 현재 상태: Phase 3 진행 중 (FEnet 이더넷 통신 성공)

---

## Phase 1: 프레임 레벨 ✅ 완료
- [x] PLCDriver, Transport 추상 인터페이스
- [x] XGT Cnet 프레임 조립/파싱 (시리얼 ASCII)
- [x] XGT FEnet 프레임 조립/파싱 (이더넷 바이너리)
- [x] BCC 계산 (Cnet + FEnet)
- [x] 디바이스 주소 변환
- [x] 단위 테스트 (test_xgt_frame.py)

## Phase 2: 전송 레벨 ✅ 완료
- [x] SerialTransport (RS-232C pyserial)
- [x] TCPTransport (시리얼-이더넷 변환기용)
- [x] FEnetTransport (XBL-EMTA 바이너리 TCP)
- [x] config.yaml 로더 + 검증
- [x] scan_serial_ports.py

## Phase 3: 통합 테스트 🔧 진행 중
- [x] FEnet 이더넷 연결 + 핑 테스트 성공
- [x] FEnet D 레지스터 읽기 성공 (D5000~D5006 = 100~700, 6ms)
- [x] FEnet 프로토콜 버그 수정 (BCC 체크섬, 바이트 주소, CPU Info)
- [x] single_read.py — FEnet 이더넷으로 1회 읽기 성공
- [ ] Cnet 시리얼 통합 테스트 (현장에서 RS-232C 연결 필요)
- [ ] polling_test.py — 반복 폴링 + 시간 측정
- [ ] multi_device_timing.py — 20대 PLC 순차 읽기 시간 측정

## Phase 4: 인터랙티브 스캐너 🆕 (다음 단계)
사용자 요구사항: config.yaml을 건드리지 않고, 실행 시점에 대화형으로 모든 설정 선택

- [ ] **interactive_scan.py** — 런타임 대화형 PLC 스캐너
  - 실행 시 제조사 선택 (LS / Mitsubishi / Keyence / Panasonic)
  - 프로토콜 선택 (Cnet / FEnet / MC Protocol / MEWTOCOL 등)
  - 연결 방식 + 파라미터 입력 (시리얼 or 이더넷)
  - D 레지스터 전체 스캔 → non-zero 값만 출력
  - 터미널 출력 + 로그 파일 저장
- [ ] 드라이버 런타임 팩토리 (yaml 의존 없이 파라미터로 직접 생성)
- [ ] 미구현 프로토콜 선택 시 안내 메시지 (확장 대비 구조만 준비)

## Phase 5: 추가 프로토콜 드라이버 (본 프로젝트 대비)
- [ ] MC Protocol 드라이버 (미쓰비시)
- [ ] Keyence Upper Link 드라이버
- [ ] MEWTOCOL 드라이버 (파나소닉, RS-485)

---

## 이번 세션 주요 성과
1. XBL-EMTA FEnet 이더넷 통신 최초 성공
2. FEnet 드라이버 3개 버그 수정:
   - CPU Info: 0xA0 → 0xB0 (XGB MK)
   - BCC 체크섬 계산 추가 (헤더 바이트 합)
   - 연속 읽기 주소: %DW → %DB (바이트 주소 변환)
3. 이더넷 1회 읽기 소요 시간: **6ms** (시리얼 대비 압도적)

## 참고: FEnet 프로토콜 정정 사항 (매뉴얼 대조 결과)
- Company ID: 10바이트 ("LSIS-XGT" + NULL NULL)
- 헤더 마지막 바이트: Reserved가 아니라 BCC (Application Header Byte Sum)
- 연속 읽기(h1400): 반드시 바이트 타입 주소 (%DB, %MB)만 허용
- 주소 포맷: 패딩 불필요 (%DW0, %DB10000 등 숫자 그대로)
- Data Type: 개별=0x0000(비트)/0x0002(워드), 연속=0x0014
