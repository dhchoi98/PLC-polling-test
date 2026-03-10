"""
LS산전 XGT FEnet 이더넷 프로토콜 드라이버

XBL-EMTA 등 FEnet 이더넷 모듈을 통한 바이너리 TCP 통신.
Cnet(ASCII 시리얼)과 달리 바이너리 프레임을 사용한다.

FEnet 프레임 구조:
  [Header 20바이트] [Data 영역]

  Header (고정 20바이트, 리틀엔디안):
    CompanyID(8)  : "LSIS-XGT"
    Reserved(2)   : 0x0000
    PLC Info(2)   : 0x0000
    CPU Info(1)   : 0xA0 (XGB)
    Source(1)      : 0x33 (외부장치→PLC), 0x11 (PLC→외부장치)
    Invoke ID(2)  : 요청/응답 매칭용 시퀀스
    Length(2)      : 데이터 영역 길이
    FEnet Pos(1)  : 이더넷 모듈 슬롯 번호
    Reserved(1)   : 0x00

  Data 영역 (읽기 요청):
    Command(2)    : 0x0054 (Read)
    Data Type(2)  : 0x0014 (연속 SB) 또는 0x0000 (개별 SS)
    Reserved(2)   : 0x0000
    Block Count(2): 블록 수
    [블록 데이터...]

  Data 영역 (읽기 응답):
    Command(2)    : 0x0055 (Read Response)
    Data Type(2)  : 요청과 동일
    Reserved(2)   : 0x0000
    Error Info(2) : 0x0000 = 정상
    Block Count(2): 블록 수
    [블록 데이터...]
"""

import struct
import logging
from typing import List, Optional

from src.drivers.base import PLCDriver, PLCProtocolError, PLCNAKError
from src.transport.base import Transport

logger = logging.getLogger("plc_test")

# --- FEnet 헤더 상수 ---
COMPANY_ID = b"LSIS-XGT"
HEADER_SIZE = 20

# CPU Info
CPU_XGB = 0xA0
CPU_XGK = 0xA0
CPU_XGI = 0xA4
CPU_XGR = 0xA8

# Source
SOURCE_PC = 0x33     # 외부 장치 → PLC
SOURCE_PLC = 0x11    # PLC → 외부 장치

# Commands
CMD_READ_REQ = 0x0054
CMD_READ_RES = 0x0055
CMD_WRITE_REQ = 0x0058  # 참고용 — 이 프로젝트에서 사용 금지!
CMD_WRITE_RES = 0x0059  # 참고용

# Data Types
DTYPE_INDIVIDUAL = 0x0000   # 개별 읽기 (SS) — 비트 읽기용
DTYPE_CONTINUOUS = 0x0014   # 연속 읽기 (SB) — 워드 연속 읽기용

# --- 유효한 디바이스 타입 ---
VALID_DEVICES = {"P", "M", "K", "F", "T", "C", "L", "D", "S", "Z"}
VALID_DATA_TYPES = {"X", "B", "W", "D", "L"}

# --- FEnet 에러 코드 ---
FENET_ERROR_CODES = {
    0x0000: "정상",
    0x0003: "존재하지 않는 디바이스",
    0x0004: "잘못된 데이터 주소",
    0x0007: "데이터 타입 에러",
    0x0011: "데이터 에러 (존재하지 않는 영역/크기)",
    0x1132: "잘못된 디바이스 메모리",
    0x1232: "데이터 길이 초과",
}


class FEnetProtocolError(PLCProtocolError):
    """FEnet 프로토콜 에러"""
    pass


class FEnetNAKError(PLCNAKError, FEnetProtocolError):
    """PLC가 FEnet 에러 응답을 반환"""
    def __init__(self, error_code: int):
        self.error_code = error_code
        desc = FENET_ERROR_CODES.get(error_code, f"알 수 없는 에러 (0x{error_code:04X})")
        super().__init__(
            f"FEnet 에러 0x{error_code:04X}: {desc}\n"
            f"  → XG5000 디바이스 모니터에서 해당 주소가 유효한지 확인\n"
            f"  → 공식 매뉴얼 부록 '에러코드 및 대책' 참조"
        )


def format_device_address(device: str, address: int, data_type: str = "W") -> str:
    """
    디바이스 주소를 XGT 포맷 문자열로 변환

    Cnet과 동일한 포맷:
        ("D", 0, "W")   -> "%DW00000"
        ("D", 100, "W") -> "%DW00100"
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


def build_fenet_header(
    data_length: int,
    invoke_id: int = 0,
    slot: int = 0,
    cpu_info: int = CPU_XGB,
) -> bytes:
    """
    FEnet 헤더 20바이트 조립

    Args:
        data_length: 데이터 영역 길이
        invoke_id: 요청/응답 매칭용 ID (0~65535)
        slot: FEnet 모듈 슬롯 번호 (보통 0)
        cpu_info: CPU 타입 (0xA0 = XGB)
    """
    return struct.pack(
        "<8s H H B B H H B B",
        COMPANY_ID,         # CompanyID (8)
        0x0000,             # Reserved (2)
        0x0000,             # PLC Info (2)
        cpu_info,           # CPU Info (1)
        SOURCE_PC,          # Source (1): PC → PLC
        invoke_id,          # Invoke ID (2)
        data_length,        # Length (2)
        slot,               # FEnet Position (1)
        0x00,               # Reserved (1)
    )


def build_read_request(
    device: str,
    address: int,
    count: int,
    invoke_id: int = 0,
    slot: int = 0,
    data_type: str = "W",
) -> bytes:
    """
    FEnet 연속 읽기(SB) 요청 프레임 조립

    Args:
        device: 디바이스 타입 ("D", "M" 등)
        address: 시작 주소
        count: 읽을 워드 수
        invoke_id: 요청/응답 매칭 ID
        slot: FEnet 모듈 슬롯 번호
        data_type: "W"=Word, "D"=DWord 등 ("X" 비트는 build_bit_read_request 사용)
    """
    if count < 1:
        raise ValueError(f"읽기 개수는 1 이상이어야 합니다: {count}")
    if data_type.upper() == "X":
        raise ValueError("Bit(X) 연속 읽기는 지원되지 않습니다. build_bit_read_request를 사용하세요.")

    var_name = format_device_address(device, address, data_type)
    var_name_bytes = var_name.encode("ascii")

    # 데이터 영역 조립
    data = struct.pack(
        "<H H H H",
        CMD_READ_REQ,       # Command (2)
        DTYPE_CONTINUOUS,    # Data Type (2): 연속 읽기
        0x0000,              # Reserved (2)
        0x0001,              # Block Count (2): 1블록
    )
    # 블록 데이터: 변수명 길이(2) + 변수명 + 읽기 개수(2)
    data += struct.pack("<H", len(var_name_bytes))
    data += var_name_bytes
    data += struct.pack("<H", count * 2)  # 바이트 수 (워드 = 2바이트)

    header = build_fenet_header(len(data), invoke_id, slot)
    return header + data


def build_bit_read_request(
    device: str,
    addresses: List[int],
    invoke_id: int = 0,
    slot: int = 0,
) -> bytes:
    """
    FEnet 개별 읽기(SS) 요청 프레임 조립 — 비트 읽기용

    FEnet 개별 읽기는 한 프레임에 여러 블록을 넣을 수 있다.
    Cnet SS처럼 비트 하나씩 요청할 필요 없이 최대 16블록까지 한번에 요청 가능.

    Args:
        device: 디바이스 타입 ("M", "P" 등)
        addresses: 읽을 비트 주소 리스트
        invoke_id: 요청/응답 매칭 ID
        slot: FEnet 모듈 슬롯 번호
    """
    if len(addresses) < 1:
        raise ValueError("주소 리스트가 비어있습니다")
    if len(addresses) > 16:
        raise ValueError(f"개별 읽기(SS)는 최대 16블록입니다: {len(addresses)}")

    block_count = len(addresses)

    # 데이터 영역 헤더
    data = struct.pack(
        "<H H H H",
        CMD_READ_REQ,        # Command
        DTYPE_INDIVIDUAL,    # Data Type: 개별 읽기
        0x0000,              # Reserved
        block_count,         # Block Count
    )

    # 각 블록: 변수명 길이(2) + 변수명
    for addr in addresses:
        var_name = format_device_address(device, addr, "X")
        var_name_bytes = var_name.encode("ascii")
        data += struct.pack("<H", len(var_name_bytes))
        data += var_name_bytes

    header = build_fenet_header(len(data), invoke_id, slot)
    return header + data


def parse_fenet_header(data: bytes) -> dict:
    """
    FEnet 응답 헤더 파싱

    Returns:
        dict with: company_id, plc_info, cpu_info, source, invoke_id,
                   data_length, slot
    """
    if len(data) < HEADER_SIZE:
        raise FEnetProtocolError(
            f"FEnet 응답이 너무 짧습니다: {len(data)} bytes (최소 {HEADER_SIZE})\n"
            f"  → 네트워크 상태 확인"
        )

    company_id, reserved, plc_info, cpu_info, source, invoke_id, \
        data_length, slot, reserved2 = struct.unpack_from(
            "<8s H H B B H H B B", data, 0
        )

    if company_id != COMPANY_ID:
        hex_str = " ".join(f"{b:02X}" for b in data[:20])
        raise FEnetProtocolError(
            f"FEnet 헤더 불일치: CompanyID = {company_id!r} (기대: {COMPANY_ID!r})\n"
            f"  헤더: {hex_str}\n"
            f"  → IP/포트가 XBL-EMTA가 맞는지 확인"
        )

    return {
        "company_id": company_id,
        "plc_info": plc_info,
        "cpu_info": cpu_info,
        "source": source,
        "invoke_id": invoke_id,
        "data_length": data_length,
        "slot": slot,
    }


def parse_read_response(
    data: bytes,
    expected_invoke_id: Optional[int] = None,
) -> List[int]:
    """
    FEnet 연속 읽기(SB) 응답 파싱

    응답 데이터 영역:
      Command(2) + DataType(2) + Reserved(2) + ErrorInfo(2) + BlockCount(2)
      + [DataSize(2) + Data(가변)] per block

    Args:
        data: 전체 응답 프레임 (헤더 + 데이터)
        expected_invoke_id: 검증할 Invoke ID (None이면 검증 안 함)

    Returns:
        읽은 워드 값 리스트

    Raises:
        FEnetNAKError: PLC가 에러 응답을 반환한 경우
        FEnetProtocolError: 프레임 파싱 에러
    """
    header = parse_fenet_header(data)

    if expected_invoke_id is not None and header["invoke_id"] != expected_invoke_id:
        raise FEnetProtocolError(
            f"Invoke ID 불일치: 수신={header['invoke_id']}, 기대={expected_invoke_id}\n"
            f"  → 다른 요청의 응답이 섞여 들어온 가능성"
        )

    # 데이터 영역 파싱 (offset 20부터)
    if len(data) < HEADER_SIZE + 10:
        hex_str = " ".join(f"{b:02X}" for b in data)
        raise FEnetProtocolError(
            f"응답 데이터가 너무 짧습니다: {len(data)} bytes\n"
            f"  전체: {hex_str}"
        )

    offset = HEADER_SIZE
    command, data_type, reserved, error_info, block_count = struct.unpack_from(
        "<H H H H H", data, offset
    )

    # 커맨드 확인
    if command != CMD_READ_RES:
        raise FEnetProtocolError(
            f"예상치 못한 응답 커맨드: 0x{command:04X} (기대: 0x{CMD_READ_RES:04X})\n"
            f"  → 요청/응답 불일치"
        )

    # 에러 확인
    if error_info != 0x0000:
        raise FEnetNAKError(error_info)

    # 블록 데이터 파싱
    offset += 10  # Command(2) + DataType(2) + Reserved(2) + ErrorInfo(2) + BlockCount(2)

    values = []
    for block_idx in range(block_count):
        if offset + 2 > len(data):
            raise FEnetProtocolError(
                f"블록 {block_idx+1}/{block_count} 데이터 부족\n"
                f"  현재 offset: {offset}, 전체 길이: {len(data)}"
            )

        data_size = struct.unpack_from("<H", data, offset)[0]
        offset += 2

        if offset + data_size > len(data):
            raise FEnetProtocolError(
                f"블록 {block_idx+1} 데이터 부족: {data_size}바이트 필요, "
                f"{len(data) - offset}바이트 남음"
            )

        block_bytes = data[offset:offset + data_size]
        offset += data_size

        if data_type == DTYPE_CONTINUOUS:
            # 연속 읽기: 바이너리 데이터를 리틀엔디안 워드로 변환
            if data_size >= 2 and data_size % 2 == 0:
                word_count = data_size // 2
                block_values = list(struct.unpack(f"<{word_count}H", block_bytes))
            else:
                block_values = list(block_bytes)
            values.extend(block_values)
        else:
            # 개별 읽기 (비트): 각 블록이 1바이트 (0x00 또는 0x01)
            values.extend(list(block_bytes))

    return values


class XGTFEnetDriver(PLCDriver):
    """LS산전 XGT FEnet 이더넷 프로토콜 드라이버"""

    def __init__(self, transport: Transport, slot: int = 0):
        self._transport = transport
        self._slot = slot
        self._connected = False
        self._invoke_id = 0

    def _next_invoke_id(self) -> int:
        """Invoke ID 순환 (0~65535)"""
        current = self._invoke_id
        self._invoke_id = (self._invoke_id + 1) % 65536
        return current

    def connect(self) -> None:
        self._transport.open()
        self._connected = True
        logger.info(f"FEnet PLC 연결 성공 (슬롯: {self._slot})")

    def disconnect(self) -> None:
        self._transport.close()
        self._connected = False
        logger.info("FEnet PLC 연결 해제")

    def read_words(self, device: str, address: int, count: int) -> List[int]:
        """워드 디바이스 연속 읽기"""
        if not self._connected:
            raise FEnetProtocolError("PLC에 연결되지 않았습니다 → connect()를 먼저 호출하세요")

        invoke_id = self._next_invoke_id()
        request = build_read_request(
            device, address, count,
            invoke_id=invoke_id,
            slot=self._slot,
        )

        var_name = format_device_address(device, address, "W")
        logger.debug(f"FEnet TX [{var_name} x{count}]: {request.hex(' ')}")

        try:
            self._transport.send(request)
        except Exception as e:
            raise FEnetProtocolError(
                f"{device}{address}~{device}{address+count-1} 읽기 요청 전송 실패: {e}"
            ) from e

        try:
            response = self._transport.receive()
        except TimeoutError as e:
            raise TimeoutError(
                f"{device}{address}~{device}{address+count-1} ({count}워드) FEnet 읽기 응답 없음\n"
                f"  {e}"
            ) from e

        logger.debug(f"FEnet RX [{var_name} x{count}]: {response.hex(' ')}")
        return parse_read_response(response, expected_invoke_id=invoke_id)

    def read_bits(self, device: str, address: int, count: int) -> List[bool]:
        """
        비트 디바이스 읽기 (개별 읽기 SS)

        FEnet은 한 프레임에 최대 16블록까지 넣을 수 있으므로,
        Cnet처럼 비트 하나마다 별도 요청할 필요 없이 한번에 최대 16비트 읽기 가능.
        16비트 초과 시 여러 프레임으로 나눈다.
        """
        if not self._connected:
            raise FEnetProtocolError("PLC에 연결되지 않았습니다 → connect()를 먼저 호출하세요")

        all_values = []
        remaining = list(range(address, address + count))

        while remaining:
            batch = remaining[:16]  # 최대 16블록
            remaining = remaining[16:]

            invoke_id = self._next_invoke_id()
            request = build_bit_read_request(
                device, batch,
                invoke_id=invoke_id,
                slot=self._slot,
            )

            logger.debug(
                f"FEnet TX [비트 {device}{batch[0]}~{device}{batch[-1]}]: "
                f"{request.hex(' ')}"
            )

            try:
                self._transport.send(request)
                response = self._transport.receive()
            except TimeoutError as e:
                raise TimeoutError(
                    f"{device}{batch[0]}~{device}{batch[-1]} 비트 FEnet 읽기 응답 없음\n"
                    f"  {e}"
                ) from e

            logger.debug(
                f"FEnet RX [비트 {device}{batch[0]}~{device}{batch[-1]}]: "
                f"{response.hex(' ')}"
            )

            values = parse_read_response(response, expected_invoke_id=invoke_id)
            all_values.extend(bool(v) for v in values)

        return all_values

    @property
    def is_connected(self) -> bool:
        return self._connected
