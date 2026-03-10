"""XGT FEnet 바이너리 프레임 조립/파싱 단위 테스트

PLC 없이 실행 가능. 프레임 바이트 시퀀스가 XGT FEnet 스펙에 맞는지 검증한다.
"""

import struct
import pytest

from src.drivers.xgt_fenet import (
    COMPANY_ID,
    HEADER_SIZE,
    CPU_XGB,
    SOURCE_PC,
    SOURCE_PLC,
    CMD_READ_REQ,
    CMD_READ_RES,
    DTYPE_CONTINUOUS,
    DTYPE_INDIVIDUAL,
    build_fenet_header,
    build_read_request,
    build_bit_read_request,
    parse_fenet_header,
    parse_read_response,
    format_device_address,
    FEnetProtocolError,
    FEnetNAKError,
)


# ============================================================
# 디바이스 주소 변환 테스트
# ============================================================

class TestFormatDeviceAddress:
    def test_d_word_zero(self):
        assert format_device_address("D", 0, "W") == "%DW00000"

    def test_d_word_100(self):
        assert format_device_address("D", 100, "W") == "%DW00100"

    def test_m_word_50(self):
        assert format_device_address("M", 50, "W") == "%MW00050"

    def test_m_bit_zero(self):
        assert format_device_address("M", 0, "X") == "%MX00000"

    def test_m_bit_15(self):
        assert format_device_address("M", 15, "X") == "%MX00015"

    def test_invalid_device(self):
        with pytest.raises(ValueError):
            format_device_address("Q", 0, "W")

    def test_negative_address(self):
        with pytest.raises(ValueError):
            format_device_address("D", -1, "W")


# ============================================================
# FEnet 헤더 테스트
# ============================================================

class TestBuildFEnetHeader:
    def test_header_size(self):
        header = build_fenet_header(data_length=10)
        assert len(header) == HEADER_SIZE

    def test_company_id(self):
        header = build_fenet_header(data_length=10)
        assert header[:8] == COMPANY_ID

    def test_cpu_info_xgb(self):
        header = build_fenet_header(data_length=10)
        assert header[12] == CPU_XGB

    def test_source_pc(self):
        header = build_fenet_header(data_length=10)
        assert header[13] == SOURCE_PC

    def test_invoke_id(self):
        header = build_fenet_header(data_length=10, invoke_id=0x1234)
        invoke_id = struct.unpack_from("<H", header, 14)[0]
        assert invoke_id == 0x1234

    def test_data_length(self):
        header = build_fenet_header(data_length=42)
        length = struct.unpack_from("<H", header, 16)[0]
        assert length == 42

    def test_slot_number(self):
        header = build_fenet_header(data_length=10, slot=3)
        assert header[18] == 3


# ============================================================
# 연속 읽기(SB) 요청 프레임 테스트
# ============================================================

class TestBuildReadRequest:
    def test_total_length(self):
        """헤더(20) + 데이터 영역 크기가 맞는지"""
        frame = build_read_request("D", 0, 10)
        # 데이터 = Command(2)+DataType(2)+Reserved(2)+BlockCount(2)
        #        + NameLen(2)+Name(8, "%DW00000")+DataCount(2) = 20
        assert len(frame) == HEADER_SIZE + 20

    def test_header_company_id(self):
        frame = build_read_request("D", 0, 10)
        assert frame[:8] == COMPANY_ID

    def test_command_read(self):
        frame = build_read_request("D", 0, 10)
        command = struct.unpack_from("<H", frame, HEADER_SIZE)[0]
        assert command == CMD_READ_REQ

    def test_data_type_continuous(self):
        frame = build_read_request("D", 0, 10)
        data_type = struct.unpack_from("<H", frame, HEADER_SIZE + 2)[0]
        assert data_type == DTYPE_CONTINUOUS

    def test_block_count_one(self):
        frame = build_read_request("D", 0, 10)
        block_count = struct.unpack_from("<H", frame, HEADER_SIZE + 6)[0]
        assert block_count == 1

    def test_variable_name(self):
        frame = build_read_request("D", 100, 5)
        # offset: header(20) + cmd(2)+dtype(2)+res(2)+bc(2)+namelen(2) = 30
        name_len = struct.unpack_from("<H", frame, HEADER_SIZE + 8)[0]
        name = frame[HEADER_SIZE + 10:HEADER_SIZE + 10 + name_len]
        assert name == b"%DW00100"

    def test_data_count_bytes(self):
        """count * 2 바이트 (워드 = 2바이트)"""
        frame = build_read_request("D", 0, 10)
        # 변수명 "%DW00000" = 8바이트
        # offset: header(20) + cmd(2)+dtype(2)+res(2)+bc(2)+namelen(2)+name(8) = 38
        data_count = struct.unpack_from("<H", frame, HEADER_SIZE + 18)[0]
        assert data_count == 20  # 10워드 * 2바이트

    def test_header_length_matches_data(self):
        frame = build_read_request("D", 0, 10)
        header_length = struct.unpack_from("<H", frame, 16)[0]
        actual_data = len(frame) - HEADER_SIZE
        assert header_length == actual_data

    def test_invoke_id_in_header(self):
        frame = build_read_request("D", 0, 10, invoke_id=42)
        invoke_id = struct.unpack_from("<H", frame, 14)[0]
        assert invoke_id == 42

    def test_slot_in_header(self):
        frame = build_read_request("D", 0, 10, slot=3)
        assert frame[18] == 3

    def test_count_zero_raises(self):
        with pytest.raises(ValueError):
            build_read_request("D", 0, 0)

    def test_bit_type_raises(self):
        with pytest.raises(ValueError):
            build_read_request("D", 0, 10, data_type="X")


# ============================================================
# 비트 개별 읽기(SS) 요청 프레임 테스트
# ============================================================

class TestBuildBitReadRequest:
    def test_command_read(self):
        frame = build_bit_read_request("M", [0, 1, 2])
        command = struct.unpack_from("<H", frame, HEADER_SIZE)[0]
        assert command == CMD_READ_REQ

    def test_data_type_individual(self):
        frame = build_bit_read_request("M", [0, 1, 2])
        data_type = struct.unpack_from("<H", frame, HEADER_SIZE + 2)[0]
        assert data_type == DTYPE_INDIVIDUAL

    def test_block_count_matches(self):
        frame = build_bit_read_request("M", [0, 1, 2])
        block_count = struct.unpack_from("<H", frame, HEADER_SIZE + 6)[0]
        assert block_count == 3

    def test_single_bit_variable_name(self):
        frame = build_bit_read_request("M", [5])
        # offset: header(20) + cmd(2)+dtype(2)+res(2)+bc(2) + namelen(2) = 30
        name_len = struct.unpack_from("<H", frame, HEADER_SIZE + 8)[0]
        name = frame[HEADER_SIZE + 10:HEADER_SIZE + 10 + name_len]
        assert name == b"%MX00005"

    def test_max_16_blocks(self):
        frame = build_bit_read_request("M", list(range(16)))
        block_count = struct.unpack_from("<H", frame, HEADER_SIZE + 6)[0]
        assert block_count == 16

    def test_over_16_raises(self):
        with pytest.raises(ValueError):
            build_bit_read_request("M", list(range(17)))

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            build_bit_read_request("M", [])

    def test_header_length_matches_data(self):
        frame = build_bit_read_request("M", [0, 1, 2])
        header_length = struct.unpack_from("<H", frame, 16)[0]
        actual_data = len(frame) - HEADER_SIZE
        assert header_length == actual_data


# ============================================================
# FEnet 헤더 파싱 테스트
# ============================================================

class TestParseFEnetHeader:
    def test_valid_header(self):
        header = build_fenet_header(data_length=10, invoke_id=7, slot=3)
        result = parse_fenet_header(header)
        assert result["invoke_id"] == 7
        assert result["slot"] == 3
        assert result["data_length"] == 10

    def test_too_short_raises(self):
        with pytest.raises(FEnetProtocolError):
            parse_fenet_header(b"\x00" * 10)

    def test_wrong_company_id_raises(self):
        bad_header = b"WRONG-ID" + b"\x00" * 12
        with pytest.raises(FEnetProtocolError, match="CompanyID"):
            parse_fenet_header(bad_header)


# ============================================================
# 응답 프레임 생성 헬퍼
# ============================================================

def _build_response(
    values: list,
    invoke_id: int = 0,
    error_info: int = 0x0000,
    data_type: int = DTYPE_CONTINUOUS,
    slot: int = 0,
) -> bytes:
    """테스트용 정상 응답 프레임 생성"""
    if data_type == DTYPE_CONTINUOUS:
        # 워드 값을 리틀엔디안 바이너리로
        block_data = struct.pack(f"<{len(values)}H", *values)
    else:
        # 비트 값 (각 1바이트)
        block_data = bytes(values)

    block_count = 1
    # 데이터 영역: Command(2) + DataType(2) + Reserved(2) + ErrorInfo(2) + BlockCount(2)
    #            + DataSize(2) + Data(가변)
    data_area = struct.pack(
        "<H H H H H",
        CMD_READ_RES,
        data_type,
        0x0000,
        error_info,
        block_count,
    )
    data_area += struct.pack("<H", len(block_data))
    data_area += block_data

    header = struct.pack(
        "<8s H H B B H H B B",
        COMPANY_ID,
        0x0000,
        0x0000,
        CPU_XGB,
        SOURCE_PLC,
        invoke_id,
        len(data_area),
        slot,
        0x00,
    )
    return header + data_area


def _build_bit_response(
    values: list,
    invoke_id: int = 0,
    error_info: int = 0x0000,
) -> bytes:
    """테스트용 비트 응답 프레임 (개별 읽기 — 블록 여러 개)"""
    block_count = len(values)

    data_area = struct.pack(
        "<H H H H H",
        CMD_READ_RES,
        DTYPE_INDIVIDUAL,
        0x0000,
        error_info,
        block_count,
    )
    for v in values:
        data_area += struct.pack("<H", 1)  # DataSize = 1바이트
        data_area += bytes([v])

    header = struct.pack(
        "<8s H H B B H H B B",
        COMPANY_ID,
        0x0000,
        0x0000,
        CPU_XGB,
        SOURCE_PLC,
        invoke_id,
        len(data_area),
        0,
        0x00,
    )
    return header + data_area


# ============================================================
# 연속 읽기(SB) 응답 파싱 테스트
# ============================================================

class TestParseReadResponse:
    def test_single_word(self):
        response = _build_response([1234])
        values = parse_read_response(response)
        assert values == [1234]

    def test_multiple_words(self):
        response = _build_response([100, 200, 300, 400, 500])
        values = parse_read_response(response)
        assert values == [100, 200, 300, 400, 500]

    def test_zero_values(self):
        response = _build_response([0, 0, 0])
        values = parse_read_response(response)
        assert values == [0, 0, 0]

    def test_max_word_value(self):
        response = _build_response([0xFFFF])
        values = parse_read_response(response)
        assert values == [65535]

    def test_ten_words(self):
        expected = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        response = _build_response(expected)
        values = parse_read_response(response)
        assert values == expected

    def test_invoke_id_match(self):
        response = _build_response([42], invoke_id=7)
        values = parse_read_response(response, expected_invoke_id=7)
        assert values == [42]

    def test_invoke_id_mismatch_raises(self):
        response = _build_response([42], invoke_id=7)
        with pytest.raises(FEnetProtocolError, match="Invoke ID"):
            parse_read_response(response, expected_invoke_id=99)

    def test_error_response_raises(self):
        response = _build_response([0], error_info=0x1132)
        with pytest.raises(FEnetNAKError) as exc_info:
            parse_read_response(response)
        assert exc_info.value.error_code == 0x1132

    def test_too_short_raises(self):
        with pytest.raises(FEnetProtocolError):
            parse_read_response(b"\x00" * 10)


# ============================================================
# 비트 개별 읽기(SS) 응답 파싱 테스트
# ============================================================

class TestParseBitResponse:
    def test_single_bit_off(self):
        response = _build_bit_response([0])
        values = parse_read_response(response)
        assert values == [0]

    def test_single_bit_on(self):
        response = _build_bit_response([1])
        values = parse_read_response(response)
        assert values == [1]

    def test_multiple_bits(self):
        response = _build_bit_response([1, 0, 1, 1, 0])
        values = parse_read_response(response)
        assert values == [1, 0, 1, 1, 0]

    def test_16_bits(self):
        bits = [i % 2 for i in range(16)]
        response = _build_bit_response(bits)
        values = parse_read_response(response)
        assert values == bits


# ============================================================
# 에러 응답 테스트
# ============================================================

class TestFEnetErrors:
    def test_error_code_preserved(self):
        response = _build_response([0], error_info=0x0003)
        with pytest.raises(FEnetNAKError) as exc_info:
            parse_read_response(response)
        assert exc_info.value.error_code == 0x0003

    def test_unknown_error_code(self):
        response = _build_response([0], error_info=0x9999)
        with pytest.raises(FEnetNAKError) as exc_info:
            parse_read_response(response)
        assert "알 수 없는 에러" in str(exc_info.value)

    def test_wrong_command_raises(self):
        """응답 커맨드가 Read Response가 아닌 경우"""
        response = _build_response([42])
        # Command 필드를 조작 (offset 20~21)
        bad = bytearray(response)
        struct.pack_into("<H", bad, HEADER_SIZE, 0x0059)  # Write Response
        with pytest.raises(FEnetProtocolError, match="커맨드"):
            parse_read_response(bytes(bad))


# ============================================================
# 라운드트립 테스트: 요청 빌드 → 응답 빌드 → 파싱
# ============================================================

class TestRoundtrip:
    def test_build_request_and_parse_response(self):
        """요청을 빌드하고, 가상 응답을 파싱하여 정합성 확인"""
        invoke_id = 42
        request = build_read_request("D", 0, 5, invoke_id=invoke_id)

        # 요청 헤더의 invoke_id 확인
        req_invoke = struct.unpack_from("<H", request, 14)[0]
        assert req_invoke == invoke_id

        # 가상 응답
        expected = [100, 200, 300, 400, 500]
        response = _build_response(expected, invoke_id=invoke_id)
        values = parse_read_response(response, expected_invoke_id=invoke_id)
        assert values == expected

    def test_various_counts(self):
        for count in [1, 5, 10, 20, 50]:
            expected = list(range(count))
            response = _build_response(expected)
            values = parse_read_response(response)
            assert values == expected

    def test_little_endian_correctness(self):
        """FEnet은 리틀엔디안 — 0x0102는 바이트 [02, 01]"""
        response = _build_response([0x0102])
        # 블록 데이터 부분: DataSize(2) + Data(2)
        # Data 위치: header(20) + Cmd(2)+DT(2)+Res(2)+Err(2)+BC(2)+DS(2) = 32
        assert response[32] == 0x02  # 하위 바이트 먼저
        assert response[33] == 0x01  # 상위 바이트
        values = parse_read_response(response)
        assert values == [0x0102]
