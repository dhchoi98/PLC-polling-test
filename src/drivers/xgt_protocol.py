"""
LS산전 XGT Cnet 시리얼 프로토콜 드라이버

Cnet 시리얼 프레임 구조 (ASCII 기반):
  요청: [ENQ] [Station(2)] [Cmd(1)] [CmdType(2)] [Data...] [EOT] [BCC(2)]
  응답(정상): [ACK] [Station(2)] [Cmd(1)] [CmdType(2)] [Data...] [ETX] [BCC(2)]
  응답(에러): [NAK] [Station(2)] [Cmd(1)] [CmdType(2)] [ErrCode(4)] [ETX] [BCC(2)]

BCC: 프레임 전체 바이트 합의 하위 1바이트를 2자리 ASCII hex로 변환하여 전송
     예) 합계 = 0x03A4 → 하위 바이트 = 0xA4 → "A4" (0x41 0x34) = 2바이트
"""

import struct
import logging
from typing import List, Optional

from src.drivers.base import PLCDriver, PLCProtocolError, PLCNAKError
from src.transport.base import Transport

logger = logging.getLogger("plc_test")

# --- 프레임 제어 문자 ---
ENQ = 0x05  # 요청 시작
EOT = 0x04  # 요청 끝
ACK = 0x06  # 정상 응답
NAK = 0x15  # 에러 응답
ETX = 0x03  # 응답 끝

# --- 유효한 디바이스 타입 ---
VALID_DEVICES = {"P", "M", "K", "F", "T", "C", "L", "D", "S", "Z"}

# --- 유효한 데이터 타입 ---
VALID_DATA_TYPES = {"X", "B", "W", "D", "L"}  # Bit, Byte, Word, DWord, LWord

# --- NAK 에러 코드 ---
NAK_ERROR_CODES = {
    0x0003: "요청 블록 수 초과 (개별 읽기/쓰기 시 16블록 초과)",
    0x0004: "변수 길이 초과 (변수명 최대 16자 초과)",
    0x0007: "디바이스 변수 타입 에러",
    0x0011: "데이터 에러 (%로 시작하지 않거나 존재하지 않는 영역/크기)",
    0x1132: "잘못된 디바이스 메모리",
    0x1232: "데이터 길이 초과",
    0x1234: "여유 프레임 에러 (EOT 뒤 불필요한 문자 존재)",
    0x1332: "데이터 타입 불일치 (모든 블록이 동일 타입이어야 함)",
}

# NAK 에러별 조치 가이드
NAK_TROUBLESHOOT = {
    0x0003: "→ 블록 수를 줄이세요 (SS 최대 16블록)",
    0x0004: "→ 변수명이 16자를 초과합니다. 주소 포맷 확인",
    0x0007: "→ 디바이스 타입이 잘못됐습니다. D/M/T/C 등 유효한 타입 사용",
    0x0011: "→ 변수명 포맷 확인 (%로 시작해야 함). 존재하지 않는 영역이거나 주소 범위 초과",
    0x1132: "→ 해당 디바이스 주소가 이 PLC 모델에 존재하지 않습니다\n"
            "   DR32H 기준: D0~D10239, M0~M1023 범위 확인",
    0x1232: "→ 읽기 개수가 너무 많습니다. SB Word 최대 60개",
    0x1234: "→ BCC 계산 오류 가능성. 프레임 포맷을 확인하세요",
    0x1332: "→ 요청 내 모든 블록의 데이터 타입이 동일해야 합니다",
}


class XGTProtocolError(PLCProtocolError):
    """XGT 프로토콜 에러"""
    pass


class XGTNAKError(PLCNAKError, XGTProtocolError):
    """PLC가 NAK(에러) 응답을 반환"""
    def __init__(self, error_code: int):
        self.error_code = error_code
        desc = get_nak_description(error_code)
        tip = NAK_TROUBLESHOOT.get(error_code, "→ 공식 매뉴얼 부록3 '에러코드 및 대책' 참조")
        super().__init__(f"NAK 에러 0x{error_code:04X}: {desc}\n  {tip}")


class XGTBCCError(PLCProtocolError):
    """BCC 검증 실패"""
    pass


def get_nak_description(error_code: int) -> str:
    """NAK 에러 코드에 대한 설명 반환"""
    return NAK_ERROR_CODES.get(error_code, f"알 수 없는 에러 (0x{error_code:04X})")


def format_device_address(device: str, address: int, data_type: str = "W") -> str:
    """
    디바이스 주소를 XGT 포맷 문자열로 변환

    Examples:
        ("D", 0, "W")   -> "%DW00000"
        ("D", 100, "W") -> "%DW00100"
        ("M", 50, "W")  -> "%MW00050"
        ("M", 0, "X")   -> "%MX00000"
    """
    device = device.upper()
    data_type = data_type.upper()

    if device not in VALID_DEVICES:
        raise ValueError(f"잘못된 디바이스 타입: {device} (허용: {VALID_DEVICES})")
    if data_type not in VALID_DATA_TYPES:
        raise ValueError(f"잘못된 데이터 타입: {data_type} (허용: {VALID_DATA_TYPES})")
    if address < 0:
        raise ValueError(f"주소는 0 이상이어야 합니다: {address}")

    return f"%{device}{data_type}{address:05d}"


def calculate_bcc(frame_bytes: bytes) -> bytes:
    """
    BCC(Block Check Character) 계산

    프레임의 모든 바이트를 합산한 뒤 하위 1바이트(mod 256)를 취하여
    2자리 ASCII hex 문자열로 변환하여 반환한다.

    공식 매뉴얼: "하위 한 Byte만 ASCII로 변환하여 BCC에 첨가합니다"
    예) 합계 = 0x03A4 → 하위 바이트 = 0xA4 → "A4" = bytes([0x41, 0x34])

    Args:
        frame_bytes: BCC를 제외한 프레임 전체 바이트

    Returns:
        2바이트 ASCII hex (예: checksum이 0xA4이면 b"A4")
    """
    checksum = sum(frame_bytes) % 256
    return f"{checksum:02X}".encode("ascii")


def build_read_request(
    device: str,
    address: int,
    count: int,
    station: int = 0,
    data_type: str = "W",
) -> bytes:
    """
    연속 읽기(rSB) 요청 프레임 조립

    프레임 구조:
      ENQ + Station(2) + 'r' + "SB" + NameLen(2) + Name(가변) + Count(2) + EOT + BCC(2)

    Args:
        device: 디바이스 타입 ("D", "M" 등)
        address: 시작 주소
        count: 읽을 개수 (Word 기준 최대 60개)
        station: PLC 국번 (0~31, RS-232C는 보통 0)
        data_type: 데이터 타입 ("W"=Word, "B"=Byte 등, "X"=Bit는 SB 미지원)

    Returns:
        전송할 바이트 시퀀스
    """
    if not 0 <= station <= 31:
        raise ValueError(f"국번은 0~31 범위여야 합니다: {station}")
    if count < 1:
        raise ValueError(f"읽기 개수는 1 이상이어야 합니다: {count}")
    if count > 60:
        raise ValueError(f"SB 연속 읽기는 최대 60개(120바이트)입니다: {count}")
    if data_type.upper() == "X":
        raise ValueError("Bit(X) 연속 읽기(SB)는 지원되지 않습니다. 개별 읽기(SS)를 사용하세요.")

    var_name = format_device_address(device, address, data_type)
    var_name_bytes = var_name.encode("ascii")

    frame = bytearray()
    frame.append(ENQ)
    frame.extend(f"{station:02X}".encode("ascii"))     # Station: hex "00"~"1F"
    frame.append(ord("r"))                              # Command: 소문자 r = BCC 포함
    frame.extend(b"SB")                                 # Command Type: 연속 읽기
    frame.extend(f"{len(var_name_bytes):02X}".encode("ascii"))  # 변수명 길이 (hex)
    frame.extend(var_name_bytes)                        # 변수명: "%DW00000"
    frame.extend(f"{count:02X}".encode("ascii"))        # 읽기 개수 (hex)
    frame.append(EOT)

    bcc = calculate_bcc(bytes(frame))
    frame.extend(bcc)

    return bytes(frame)


def build_bit_read_request(
    device: str,
    address: int,
    station: int = 0,
) -> bytes:
    """
    개별 읽기(rSS) 요청 프레임 조립 — 비트 1개 읽기용

    프레임 구조:
      ENQ + Station(2) + 'r' + "SS" + BlockCount(2) + NameLen(2) + Name(가변) + EOT + BCC(2)

    SB(연속읽기)는 Bit를 지원하지 않으므로 SS(개별읽기)를 사용한다.
    """
    if not 0 <= station <= 31:
        raise ValueError(f"국번은 0~31 범위여야 합니다: {station}")

    var_name = format_device_address(device, address, "X")
    var_name_bytes = var_name.encode("ascii")

    frame = bytearray()
    frame.append(ENQ)
    frame.extend(f"{station:02X}".encode("ascii"))
    frame.append(ord("r"))
    frame.extend(b"SS")                                     # 개별 읽기
    frame.extend(b"01")                                     # 블록 수: 1개
    frame.extend(f"{len(var_name_bytes):02X}".encode("ascii"))
    frame.extend(var_name_bytes)
    frame.append(EOT)

    bcc = calculate_bcc(bytes(frame))
    frame.extend(bcc)

    return bytes(frame)


def parse_read_response(
    data: bytes,
    expected_station: Optional[int] = None,
) -> List[int]:
    """
    연속 읽기(rSB) ACK 응답 프레임 파싱

    응답 구조:
      ACK + Station(2) + 'r' + "SB" + BlockCount(2) + DataSize(2) + DataHex(가변) + ETX + BCC(2)

    NAK 응답:
      NAK + Station(2) + 'r' + "SB" + ErrorCode(4) + ETX + BCC(2)

    Args:
        data: 수신한 전체 응답 바이트
        expected_station: 검증할 국번 (None이면 검증 안 함)

    Returns:
        읽은 워드 값 리스트

    Raises:
        XGTNAKError: PLC가 에러 응답을 반환한 경우
        XGTBCCError: BCC 검증 실패
        XGTProtocolError: 기타 프레임 에러
    """
    hex_str = " ".join(f"{b:02X}" for b in data)

    if len(data) < 8:
        raise XGTProtocolError(
            f"응답이 너무 짧습니다: {len(data)} bytes\n"
            f"  수신 데이터: {hex_str}\n"
            f"  → 최소 8바이트 이상이어야 합니다"
        )

    header = data[0]

    # BCC 검증: 마지막 2바이트가 BCC (ASCII hex)
    body = data[:-2]
    received_bcc = data[-2:]
    expected_bcc = calculate_bcc(body)
    if received_bcc != expected_bcc:
        raise XGTBCCError(
            f"BCC 불일치\n"
            f"  수신 BCC: {received_bcc!r} (0x{received_bcc.hex()})\n"
            f"  기대 BCC: {expected_bcc!r} (0x{expected_bcc.hex()})\n"
            f"  전체 프레임: {hex_str}\n"
            f"  가능한 원인:\n"
            f"  1) 전송 중 데이터 깨짐 → 케이블 접촉 불량\n"
            f"  2) 보레이트/패리티 불일치로 일부 바이트가 변형됨\n"
            f"  3) 변수명 포맷이 PLC가 기대하는 것과 다름 (5자리 vs 3자리)"
        )

    # 국번 검증
    try:
        station_str = data[1:3].decode("ascii")
    except UnicodeDecodeError:
        raise XGTProtocolError(
            f"국번 바이트를 ASCII로 해석할 수 없습니다: {data[1:3]!r}\n"
            f"  전체 프레임: {hex_str}\n"
            f"  → 보레이트 불일치 가능성"
        )

    if expected_station is not None:
        expected_str = f"{expected_station:02X}"
        if station_str != expected_str:
            raise XGTProtocolError(
                f"국번 불일치: 수신='{station_str}', 기대='{expected_str}'\n"
                f"  → config.yaml이나 코드의 station 설정을 확인하세요\n"
                f"  → PLC XG5000에서 Cnet 국번 확인"
            )

    # NAK 응답 처리
    if header == NAK:
        try:
            error_code_str = data[6:10].decode("ascii")
            error_code = int(error_code_str, 16)
        except (UnicodeDecodeError, ValueError):
            raise XGTProtocolError(
                f"NAK 응답의 에러 코드를 파싱할 수 없습니다\n"
                f"  에러 코드 바이트: {data[6:10]!r}\n"
                f"  전체 프레임: {hex_str}"
            )
        raise XGTNAKError(error_code)

    # ACK 응답 처리
    if header != ACK:
        raise XGTProtocolError(
            f"알 수 없는 응답 헤더: 0x{header:02X}\n"
            f"  (ACK=0x06 또는 NAK=0x15를 기대)\n"
            f"  전체 프레임: {hex_str}\n"
            f"  → 보레이트 불일치 가능성이 높습니다"
        )

    # data[3] = command ('r'), data[4:6] = command type ("SB")
    # data[6:8] = block count
    # data[8:10] = data size (바이트 수, hex)
    # data[10:-3] = 데이터 (ASCII hex) — 마지막 3바이트는 ETX + BCC(2)
    try:
        block_count = int(data[6:8].decode("ascii"), 16)
        data_size = int(data[8:10].decode("ascii"), 16)
        data_hex_str = data[10:-3].decode("ascii")  # ETX 앞까지
    except (ValueError, UnicodeDecodeError) as e:
        raise XGTProtocolError(
            f"응답 데이터 파싱 실패: {e}\n"
            f"  블록수 바이트: {data[6:8]!r}\n"
            f"  데이터크기 바이트: {data[8:10]!r}\n"
            f"  전체 프레임: {hex_str}\n"
            f"  → 응답 프레임 구조가 예상과 다릅니다"
        )

    # ASCII hex → 바이트 → 워드 값 변환
    if len(data_hex_str) != data_size * 2:
        raise XGTProtocolError(
            f"데이터 길이 불일치\n"
            f"  응답 DataSize: {data_size} 바이트 → hex 문자열 {data_size * 2}자 기대\n"
            f"  실제 수신: {len(data_hex_str)}자\n"
            f"  데이터 내용: '{data_hex_str}'\n"
            f"  전체 프레임: {hex_str}"
        )

    raw_bytes = bytes.fromhex(data_hex_str)

    # Cnet ASCII 프로토콜은 hex 값을 MSB부터 전송 → 빅엔디안
    # 예) M000=H1234 → "1234" → bytes [0x12, 0x34] → unpack(">H") = 0x1234
    if len(raw_bytes) >= 2 and len(raw_bytes) % 2 == 0:
        # 워드 단위 (2바이트 정렬)
        word_count = len(raw_bytes) // 2
        values = list(struct.unpack(f">{word_count}H", raw_bytes))
    else:
        # 바이트 단위 (비트 읽기 등 — 1바이트씩 반환)
        values = list(raw_bytes)

    return values


class XGTProtocolDriver(PLCDriver):
    """LS산전 XGT Cnet 시리얼 프로토콜 드라이버"""

    def __init__(self, transport: Transport, station: int = 0):
        self._transport = transport
        self._station = station
        self._connected = False

    def connect(self) -> None:
        self._transport.open()
        self._connected = True
        logger.info(f"PLC 연결 성공 (국번: {self._station})")

    def disconnect(self) -> None:
        self._transport.close()
        self._connected = False
        logger.info("PLC 연결 해제")

    def read_words(self, device: str, address: int, count: int) -> List[int]:
        """워드 디바이스 읽기"""
        if not self._connected:
            raise XGTProtocolError("PLC에 연결되지 않았습니다 → connect()를 먼저 호출하세요")

        request = build_read_request(
            device, address, count,
            station=self._station,
            data_type="W",
        )
        var_name = format_device_address(device, address, "W")
        logger.debug(f"TX [{var_name} x{count}]: {request.hex(' ')}")

        try:
            self._transport.send(request)
        except Exception as e:
            raise XGTProtocolError(
                f"{device}{address}~{device}{address+count-1} 읽기 요청 전송 실패: {e}"
            ) from e

        try:
            response = self._transport.receive()
        except TimeoutError as e:
            raise TimeoutError(
                f"{device}{address}~{device}{address+count-1} ({count}워드) 읽기 응답 없음\n"
                f"  요청 프레임: {request.hex(' ')}\n"
                f"  {e}"
            ) from e

        logger.debug(f"RX [{var_name} x{count}]: {response.hex(' ')}")
        return parse_read_response(response, expected_station=self._station)

    def read_bits(self, device: str, address: int, count: int) -> List[bool]:
        """비트 디바이스 읽기 (개별 읽기 SS 사용 — SB는 Bit 미지원)"""
        if not self._connected:
            raise XGTProtocolError("PLC에 연결되지 않았습니다 → connect()를 먼저 호출하세요")

        # 공식 매뉴얼: "Bit 디바이스 연속 읽기(SB)는 지원되지 않습니다"
        # 개별 읽기(rSS)로 각 비트를 하나씩 읽는다
        logger.debug(f"비트 읽기: {device}{address}~{device}{address+count-1} ({count}비트, SS 개별)")
        values = []
        for i in range(count):
            bit_addr = address + i
            request = build_bit_read_request(
                device, bit_addr,
                station=self._station,
            )
            logger.debug(f"TX [%{device}X{bit_addr:05d}]: {request.hex(' ')}")

            try:
                self._transport.send(request)
                response = self._transport.receive()
            except TimeoutError as e:
                raise TimeoutError(
                    f"{device}{bit_addr} 비트 읽기 응답 없음 ({i+1}/{count}번째)\n"
                    f"  {e}"
                ) from e

            logger.debug(f"RX [%{device}X{bit_addr:05d}]: {response.hex(' ')}")

            bit_values = parse_read_response(response, expected_station=self._station)
            values.append(bool(bit_values[0]))

        return values

    @property
    def is_connected(self) -> bool:
        return self._connected
