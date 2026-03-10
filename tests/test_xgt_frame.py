"""
XGT Cnet 프레임 조립/파싱 단위 테스트

PLC 없이 실행 가능 — 프로토콜 로직의 정확성을 검증한다.
"""

import struct
import pytest

from src.drivers.xgt_protocol import (
    format_device_address,
    calculate_bcc,
    build_read_request,
    build_bit_read_request,
    parse_read_response,
    get_nak_description,
    XGTNAKError,
    XGTBCCError,
    XGTProtocolError,
    ENQ, EOT, ACK, NAK, ETX,
)


# ============================================================
# 디바이스 주소 변환 테스트
# ============================================================
class TestDeviceAddressFormat:
    def test_d_word_zero(self):
        assert format_device_address("D", 0, "W") == "%DW00000"

    def test_d_word_100(self):
        assert format_device_address("D", 100, "W") == "%DW00100"

    def test_m_word_50(self):
        assert format_device_address("M", 50, "W") == "%MW00050"

    def test_m_bit_0(self):
        assert format_device_address("M", 0, "X") == "%MX00000"

    def test_d_dword(self):
        assert format_device_address("D", 200, "D") == "%DD00200"

    def test_t_word(self):
        assert format_device_address("T", 10, "W") == "%TW00010"

    def test_large_address(self):
        assert format_device_address("D", 99999, "W") == "%DW99999"

    def test_all_valid_devices(self):
        """모든 유효 디바이스 타입이 정상 변환되는지"""
        for dev in ["P", "M", "K", "F", "T", "C", "L", "D", "S", "Z"]:
            addr = format_device_address(dev, 0, "W")
            assert addr == f"%{dev}W00000"
            assert len(addr) == 8

    def test_invalid_device_raises(self):
        with pytest.raises(ValueError, match="잘못된 디바이스"):
            format_device_address("X", 0, "W")

    def test_invalid_data_type_raises(self):
        with pytest.raises(ValueError, match="잘못된 데이터"):
            format_device_address("D", 0, "Q")

    def test_negative_address_raises(self):
        with pytest.raises(ValueError):
            format_device_address("D", -1, "W")

    def test_lowercase_device_accepted(self):
        assert format_device_address("d", 0, "w") == "%DW00000"


# ============================================================
# BCC 계산 테스트
# ============================================================
class TestBCCCalculation:
    def test_returns_two_bytes(self):
        bcc = calculate_bcc(b"\x00\x01\x02")
        assert len(bcc) == 2

    def test_is_ascii_hex(self):
        bcc = calculate_bcc(b"\xff\xff")
        # 0xFF + 0xFF = 510, 510 % 256 = 254 = 0xFE → "FE"
        assert bcc == b"FE"

    def test_wraps_at_256(self):
        bcc = calculate_bcc(bytes([0x80, 0x80]))
        # 128 + 128 = 256, 256 % 256 = 0 → "00"
        assert bcc == b"00"

    def test_single_byte(self):
        bcc = calculate_bcc(bytes([0x41]))  # 65 = 0x41 → "41"
        assert bcc == b"41"

    def test_zero_bytes(self):
        bcc = calculate_bcc(bytes([0x00, 0x00]))
        assert bcc == b"00"

    def test_known_frame_from_manual(self):
        """공식 매뉴얼 98페이지 예제 검증:
        H05+H32+H30+H72+H53+H53+H30+H31+H30+H36+H25+H4D+H57+H31+H30+H30+H04 = H03A4
        → 하위 바이트 = A4 → BCC = "A4"
        """
        frame = bytes([
            0x05,                           # ENQ
            0x32, 0x30,                     # "20" (station)
            0x72,                           # 'r'
            0x53, 0x53,                     # "SS"
            0x30, 0x31,                     # "01" (block count)
            0x30, 0x36,                     # "06" (var name length)
            0x25, 0x4D, 0x57, 0x31, 0x30, 0x30,  # "%MW100"
            0x04,                           # EOT
        ])
        bcc = calculate_bcc(frame)
        expected = sum(frame) % 256
        assert bcc == f"{expected:02X}".encode("ascii")

    def test_manual_bcc_value(self):
        """매뉴얼 예제의 실제 BCC 값 = A4"""
        frame = bytes([
            0x05, 0x32, 0x30, 0x72, 0x53, 0x53,
            0x30, 0x31, 0x30, 0x36,
            0x25, 0x4D, 0x57, 0x31, 0x30, 0x30,
            0x04,
        ])
        total = sum(frame)
        assert total == 0x03A4
        bcc = calculate_bcc(frame)
        assert bcc == b"A4"


# ============================================================
# 프레임 조립 테스트
# ============================================================
class TestBuildReadRequest:
    def test_frame_starts_with_enq(self):
        frame = build_read_request("D", 0, 10)
        assert frame[0] == ENQ

    def test_frame_ends_with_bcc(self):
        frame = build_read_request("D", 0, 10)
        # EOT는 BCC 2바이트 전
        assert frame[-3] == EOT
        assert len(frame[-2:]) == 2

    def test_station_number_default_zero(self):
        frame = build_read_request("D", 0, 1)
        assert frame[1:3] == b"00"

    def test_station_number_5(self):
        frame = build_read_request("D", 0, 1, station=5)
        assert frame[1:3] == b"05"

    def test_station_number_hex_format(self):
        """국번 10 이상은 hex 포맷 (10 → "0A")"""
        frame = build_read_request("D", 0, 1, station=10)
        assert frame[1:3] == b"0A"

    def test_station_number_31(self):
        """국번 31 = 0x1F → "1F" """
        frame = build_read_request("D", 0, 1, station=31)
        assert frame[1:3] == b"1F"

    def test_command_is_lowercase_r(self):
        """소문자 r = BCC 포함 모드"""
        frame = build_read_request("D", 0, 1)
        assert frame[3] == ord("r")

    def test_command_type_is_sb(self):
        """SB = 연속 읽기"""
        frame = build_read_request("D", 0, 10)
        assert frame[4:6] == b"SB"

    def test_contains_variable_name(self):
        frame = build_read_request("D", 100, 10)
        assert b"%DW00100" in frame

    def test_variable_name_length(self):
        frame = build_read_request("D", 0, 10)
        # "%DW00000" = 8자 → "08"
        assert b"08" in frame

    def test_read_count_hex(self):
        frame = build_read_request("D", 0, 16)
        # 16 = 0x10 → "10"
        assert b"10" in frame

    def test_bcc_matches(self):
        frame = build_read_request("D", 0, 10)
        body = frame[:-2]  # BCC는 마지막 2바이트
        expected_bcc = calculate_bcc(body)
        assert frame[-2:] == expected_bcc

    def test_bit_device_raises(self):
        """SB는 Bit(X) 미지원 — 공식 매뉴얼 확인"""
        with pytest.raises(ValueError, match="Bit.*지원되지 않습니다"):
            build_read_request("M", 0, 16, data_type="X")

    def test_max_count_60_ok(self):
        """최대 60워드까지 허용"""
        frame = build_read_request("D", 0, 60)
        assert frame[0] == ENQ

    def test_count_61_raises(self):
        """61워드 이상 요청 시 에러"""
        with pytest.raises(ValueError, match="최대 60개"):
            build_read_request("D", 0, 61)

    def test_no_write_command(self):
        """안전: 읽기 요청에 쓰기 명령이 포함되면 안 됨"""
        frame = build_read_request("D", 0, 10)
        assert frame[3] != ord("w")
        assert frame[3] != ord("W")

    def test_invalid_station_raises(self):
        with pytest.raises(ValueError):
            build_read_request("D", 0, 1, station=32)
        with pytest.raises(ValueError):
            build_read_request("D", 0, 1, station=-1)

    def test_invalid_count_raises(self):
        with pytest.raises(ValueError):
            build_read_request("D", 0, 0)

    def test_frame_length_reasonable(self):
        """10워드 읽기 요청은 30바이트 미만"""
        frame = build_read_request("D", 0, 10)
        assert len(frame) < 30


# ============================================================
# 비트 개별 읽기(SS) 프레임 테스트
# ============================================================
class TestBuildBitReadRequest:
    def test_frame_starts_with_enq(self):
        frame = build_bit_read_request("M", 0)
        assert frame[0] == ENQ

    def test_command_type_is_ss(self):
        """SS = 개별 읽기"""
        frame = build_bit_read_request("M", 0)
        assert frame[4:6] == b"SS"

    def test_contains_bit_variable(self):
        frame = build_bit_read_request("M", 100)
        assert b"%MX00100" in frame

    def test_block_count_is_01(self):
        frame = build_bit_read_request("M", 0)
        assert frame[6:8] == b"01"

    def test_bcc_matches(self):
        frame = build_bit_read_request("M", 0)
        body = frame[:-2]
        expected_bcc = calculate_bcc(body)
        assert frame[-2:] == expected_bcc

    def test_station_hex_format(self):
        frame = build_bit_read_request("M", 0, station=15)
        assert frame[1:3] == b"0F"


# ============================================================
# 테스트 헬퍼 — 실제 PLC 응답 형식과 동일하게 생성
# ============================================================
def _build_ack_response(station: int, values: list[int]) -> bytes:
    """
    테스트용 가짜 ACK 응답 프레임 생성 (SB 연속 읽기 응답)

    실제 PLC와 동일하게 빅엔디안 hex 문자열로 데이터를 인코딩.
    예) M000=H1234 → 데이터 "1234" (MSB 먼저)
    """
    body = bytearray()
    body.append(ACK)
    body.extend(f"{station:02X}".encode("ascii"))
    body.append(ord("r"))
    body.extend(b"SB")

    # Block count = 01
    body.extend(b"01")

    # 워드 값을 빅엔디안 바이트로 변환 (PLC와 동일)
    raw_bytes = bytearray()
    for v in values:
        raw_bytes.extend(struct.pack(">H", v))

    # Data size (바이트 수, hex)
    body.extend(f"{len(raw_bytes):02X}".encode("ascii"))

    # Data (ASCII hex)
    for b in raw_bytes:
        body.extend(f"{b:02X}".encode("ascii"))

    body.append(ETX)

    bcc = calculate_bcc(bytes(body))
    body.extend(bcc)

    return bytes(body)


def _build_ack_response_ss_bit(station: int, bit_value: int) -> bytes:
    """
    테스트용 SS 비트 읽기 ACK 응답 프레임 생성

    비트 값: 0 또는 1 (1바이트)
    """
    body = bytearray()
    body.append(ACK)
    body.extend(f"{station:02X}".encode("ascii"))
    body.append(ord("r"))
    body.extend(b"SS")

    # Block count = 01
    body.extend(b"01")

    # Data size = 01 (1바이트 — 비트)
    body.extend(b"01")

    # Data (0x00 또는 0x01)
    body.extend(f"{bit_value:02X}".encode("ascii"))

    body.append(ETX)

    bcc = calculate_bcc(bytes(body))
    body.extend(bcc)

    return bytes(body)


def _build_nak_response(station: int, error_code: int) -> bytes:
    """테스트용 NAK 응답 프레임 생성"""
    body = bytearray()
    body.append(NAK)
    body.extend(f"{station:02X}".encode("ascii"))
    body.append(ord("r"))
    body.extend(b"SB")
    body.extend(f"{error_code:04X}".encode("ascii"))
    body.append(ETX)

    bcc = calculate_bcc(bytes(body))
    body.extend(bcc)

    return bytes(body)


# ============================================================
# 응답 파싱 테스트 — 워드 읽기 (SB)
# ============================================================
class TestParseReadResponse:
    def test_parse_single_word(self):
        response = _build_ack_response(0, [1234])
        values = parse_read_response(response)
        assert values == [1234]

    def test_parse_multiple_words(self):
        response = _build_ack_response(0, [100, 200, 300])
        values = parse_read_response(response)
        assert values == [100, 200, 300]

    def test_parse_zero_values(self):
        response = _build_ack_response(0, [0, 0, 0])
        values = parse_read_response(response)
        assert values == [0, 0, 0]

    def test_parse_max_word_value(self):
        response = _build_ack_response(0, [65535])
        values = parse_read_response(response)
        assert values == [65535]

    def test_parse_ten_words(self):
        """D0~D9 (10워드) 읽기 시나리오"""
        test_values = [1234, 5678, 0, 0, 42, 0, 0, 0, 0, 100]
        response = _build_ack_response(0, test_values)
        values = parse_read_response(response)
        assert values == test_values

    def test_station_validation(self):
        response = _build_ack_response(5, [42])
        values = parse_read_response(response, expected_station=5)
        assert values == [42]

    def test_station_mismatch_raises(self):
        response = _build_ack_response(5, [42])
        with pytest.raises(XGTProtocolError, match="국번 불일치"):
            parse_read_response(response, expected_station=0)

    def test_station_hex_validation(self):
        """국번 10 이상도 hex 포맷으로 검증"""
        response = _build_ack_response(15, [42])
        values = parse_read_response(response, expected_station=15)
        assert values == [42]

    def test_invalid_bcc_raises(self):
        response = _build_ack_response(0, [100])
        corrupted = response[:-2] + b"XX"
        with pytest.raises(XGTBCCError):
            parse_read_response(corrupted)

    def test_too_short_raises(self):
        with pytest.raises(XGTProtocolError, match="너무 짧"):
            parse_read_response(b"\x06\x30\x30\x72\x53")


# ============================================================
# 공식 매뉴얼 예제 검증 — 바이트 단위 대조
# ============================================================
class TestManualExamples:
    def test_manual_page103_sb_response(self):
        """
        매뉴얼 103페이지 SB 읽기 응답 예제:
        국번 10(=0x0A), M000=H1234, M001=H5678, 2워드 읽기

        ACK응답: ACK + "0A" + 'r' + "SB" + "01" + "04" + "12345678" + ETX + BCC
        """
        response = _build_ack_response(station=10, values=[0x1234, 0x5678])
        values = parse_read_response(response, expected_station=10)
        assert values == [0x1234, 0x5678]

    def test_endianness_correctness(self):
        """
        빅엔디안 검증: 값 0x04D2(=1234)가 "04D2"로 전송되어야 한다.
        리틀엔디안이면 "D204"로 전송되므로 결과가 0xD204(=53764)가 된다.
        """
        response = _build_ack_response(0, [0x04D2])
        values = parse_read_response(response)
        assert values == [0x04D2]  # = 1234
        assert values != [0xD204]  # = 53764 (리틀엔디안이었다면 이 값)

    def test_manual_page100_rss_values(self):
        """
        매뉴얼 100페이지 RSS 예제 값:
        M020 = H1234, P001 = H5678
        (SB 응답으로 시뮬레이션 — 파싱 로직 검증 목적)
        """
        response = _build_ack_response(1, [0x1234, 0x5678])
        values = parse_read_response(response, expected_station=1)
        assert values == [0x1234, 0x5678]


# ============================================================
# 비트 응답 파싱 테스트 (SS)
# ============================================================
class TestParseBitResponse:
    def test_bit_value_0(self):
        """비트 OFF (0x00)"""
        response = _build_ack_response_ss_bit(0, 0)
        values = parse_read_response(response)
        assert values == [0]

    def test_bit_value_1(self):
        """비트 ON (0x01)"""
        response = _build_ack_response_ss_bit(0, 1)
        values = parse_read_response(response)
        assert values == [1]

    def test_bit_station_check(self):
        response = _build_ack_response_ss_bit(5, 1)
        values = parse_read_response(response, expected_station=5)
        assert values == [1]


# ============================================================
# NAK 응답 테스트
# ============================================================
class TestNAKResponse:
    def test_nak_raises_error(self):
        response = _build_nak_response(0, 0x1132)
        with pytest.raises(XGTNAKError) as exc_info:
            parse_read_response(response)
        assert exc_info.value.error_code == 0x1132
        assert "1132" in str(exc_info.value)

    def test_nak_description(self):
        assert "디바이스 메모리" in get_nak_description(0x1132)

    def test_unknown_nak_code(self):
        desc = get_nak_description(0xFFFF)
        assert "알 수 없는" in desc

    def test_all_known_codes_have_descriptions(self):
        known_codes = [0x0003, 0x0004, 0x0007, 0x0011, 0x1132, 0x1232, 0x1234, 0x1332]
        for code in known_codes:
            desc = get_nak_description(code)
            assert "알 수 없는" not in desc


# ============================================================
# 왕복(Roundtrip) 테스트
# ============================================================
class TestRoundtrip:
    def test_build_and_verify_bcc(self):
        """요청 프레임을 만들고 BCC가 정확한지 자체 검증"""
        for device, addr, count in [("D", 0, 10), ("M", 50, 5), ("T", 0, 1)]:
            frame = build_read_request(device, addr, count)
            body = frame[:-2]  # BCC는 마지막 2바이트
            assert frame[-2:] == calculate_bcc(body)

    def test_various_counts(self):
        """다양한 읽기 개수에 대해 프레임 정상 생성"""
        for count in [1, 5, 10, 15, 20, 50, 60]:
            frame = build_read_request("D", 0, count)
            assert frame[0] == ENQ
            assert frame[-3] == EOT
