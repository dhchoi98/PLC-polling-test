"""
RS-232C 시리얼 전송 계층

pyserial을 래핑하여 Transport 인터페이스를 구현한다.
응답 수신 시 ETX(0x03) + BCC(2바이트 ASCII hex)를 기준으로 프레임 종료를 감지한다.
"""

import logging
import serial
import serial.tools.list_ports
from typing import Optional

from src.transport.base import Transport

logger = logging.getLogger("plc_test")

# 응답 프레임 종료 감지용
ETX = 0x03
ACK = 0x06
NAK = 0x15

# 수신 버퍼 최대 크기 (무한 루프 방지)
MAX_FRAME_SIZE = 512


class SerialTransport(Transport):
    """RS-232C 시리얼 전송 계층"""

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        bytesize: int = 8,
        parity: str = "none",
        stopbits: int = 1,
        timeout: float = 1.0,
    ):
        self._port = port
        self._baudrate = baudrate
        self._bytesize = bytesize
        self._parity = self._parse_parity(parity)
        self._stopbits = stopbits
        self._timeout = timeout
        self._serial: Optional[serial.Serial] = None

    @staticmethod
    def _parse_parity(parity: str) -> str:
        """패리티 문자열을 pyserial 상수로 변환"""
        mapping = {
            "none": serial.PARITY_NONE,
            "even": serial.PARITY_EVEN,
            "odd": serial.PARITY_ODD,
        }
        return mapping.get(parity.lower(), serial.PARITY_NONE)

    def open(self) -> None:
        if self._serial and self._serial.is_open:
            return

        # 포트 존재 여부 사전 체크
        available = [p.device for p in serial.tools.list_ports.comports()]

        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                bytesize=self._bytesize,
                parity=self._parity,
                stopbits=self._stopbits,
                timeout=self._timeout,
            )
            logger.info(f"시리얼 포트 열림: {self._port} @ {self._baudrate}bps")

        except serial.SerialException as e:
            err_str = str(e).lower()

            # 포트를 찾을 수 없음
            if "could not open" in err_str or "filenotfound" in err_str or "no such file" in err_str:
                if available:
                    ports_str = ", ".join(available)
                    raise IOError(
                        f"시리얼 포트 '{self._port}'를 찾을 수 없습니다\n"
                        f"  현재 사용 가능한 포트: {ports_str}\n"
                        f"  → config.yaml의 serial.port를 위 포트 중 하나로 변경하세요\n"
                        f"  → USB-RS232C 컨버터가 연결되어 있는지 확인하세요"
                    ) from e
                else:
                    raise IOError(
                        f"시리얼 포트 '{self._port}'를 찾을 수 없습니다\n"
                        f"  현재 시스템에 시리얼 포트가 하나도 없습니다!\n"
                        f"  → USB-RS232C 컨버터를 PC에 연결하세요\n"
                        f"  → 드라이버가 설치되어 있는지 확인하세요 (장치관리자 → 포트(COM & LPT))"
                    ) from e

            # 다른 프로세스가 포트를 사용 중
            if "access is denied" in err_str or "permission" in err_str or "busy" in err_str:
                raise IOError(
                    f"시리얼 포트 '{self._port}'에 접근할 수 없습니다 (사용 중이거나 권한 부족)\n"
                    f"  → HMI나 XG5000이 이 포트를 점유 중인지 확인하세요\n"
                    f"  → 다른 터미널에서 이 스크립트를 이미 실행 중인지 확인하세요\n"
                    f"  → 관리자 권한으로 실행해 보세요"
                ) from e

            # 그 외 에러
            if available:
                ports_str = ", ".join(available)
                raise IOError(
                    f"시리얼 포트 열기 실패: {e}\n"
                    f"  사용 가능한 포트: {ports_str}"
                ) from e
            else:
                raise IOError(f"시리얼 포트 열기 실패: {e}") from e

        except PermissionError as e:
            raise IOError(
                f"시리얼 포트 '{self._port}' 권한 거부\n"
                f"  → 관리자 권한으로 실행하거나\n"
                f"  → HMI/XG5000이 포트를 점유 중인지 확인하세요"
            ) from e

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info(f"시리얼 포트 닫힘: {self._port}")
        self._serial = None

    def send(self, data: bytes) -> None:
        if not self._serial or not self._serial.is_open:
            raise IOError("시리얼 포트가 열려있지 않습니다 → connect()를 먼저 호출하세요")

        try:
            self._serial.write(data)
            self._serial.flush()
        except serial.SerialException as e:
            raise IOError(
                f"시리얼 데이터 전송 실패: {e}\n"
                f"  → USB-RS232C 케이블이 빠졌을 수 있습니다\n"
                f"  → 케이블 연결 상태를 확인하세요"
            ) from e

    def receive(self, timeout: float = 0) -> bytes:
        """
        응답 프레임 수신

        ACK/NAK 헤더를 먼저 읽고, ETX를 만날 때까지 읽은 뒤,
        BCC 2바이트를 추가로 읽어서 전체 프레임을 반환한다.
        """
        if not self._serial or not self._serial.is_open:
            raise IOError("시리얼 포트가 열려있지 않습니다 → connect()를 먼저 호출하세요")

        if timeout > 0:
            self._serial.timeout = timeout

        buffer = bytearray()

        try:
            # 1. 첫 바이트(ACK/NAK) 읽기
            header = self._serial.read(1)
            if not header:
                raise TimeoutError(
                    f"PLC 응답 없음 (헤더 수신 타임아웃, {self._timeout}초 대기)\n"
                    f"  가능한 원인:\n"
                    f"  1) 보레이트 불일치 → PLC의 Cnet 설정(XG5000)에서 보레이트 확인\n"
                    f"     config: {self._baudrate}bps, PLC 설정과 일치해야 함\n"
                    f"  2) RS-232C 케이블 불량 또는 미연결 → TX/RX 핀 확인\n"
                    f"  3) PLC가 Cnet 모드가 아님 → XG5000에서 CH1을 Cnet으로 설정해야 함\n"
                    f"  4) PLC 전원 꺼짐 또는 STOP 상태\n"
                    f"  5) 국번(Station) 불일치 → PLC 국번과 config 일치 확인"
                )
            buffer.extend(header)

            # 헤더 바이트 검증
            if header[0] not in (ACK, NAK):
                # ACK/NAK가 아닌 바이트 → 보레이트 불일치 가능성 높음
                # 추가 바이트를 좀 더 읽어서 진단에 활용
                extra = self._serial.read(min(20, MAX_FRAME_SIZE))
                buffer.extend(extra)
                hex_str = " ".join(f"{b:02X}" for b in buffer)
                ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in buffer)
                raise IOError(
                    f"예상치 못한 응답 헤더: 0x{header[0]:02X}\n"
                    f"  (ACK=0x06 또는 NAK=0x15를 기대했으나 0x{header[0]:02X} 수신)\n"
                    f"  수신 데이터 hex dump ({len(buffer)} bytes):\n"
                    f"    HEX:   {hex_str}\n"
                    f"    ASCII: {ascii_str}\n"
                    f"  가능한 원인:\n"
                    f"  1) 보레이트 불일치 → 가장 흔한 원인! 데이터가 깨져서 엉뚱한 바이트가 옴\n"
                    f"     config: {self._baudrate}bps → PLC 설정과 일치하는지 확인\n"
                    f"  2) 패리티/스톱비트 불일치\n"
                    f"  3) 다른 장비(HMI)가 동시에 응답"
                )

            # 2. ETX를 만날 때까지 읽기
            bytes_read = 1
            while bytes_read < MAX_FRAME_SIZE:
                byte = self._serial.read(1)
                if not byte:
                    hex_str = " ".join(f"{b:02X}" for b in buffer)
                    raise TimeoutError(
                        f"응답 수신 중 타임아웃 (ETX를 기다리는 중, {bytes_read}바이트 수신됨)\n"
                        f"  지금까지 수신된 데이터:\n"
                        f"    HEX: {hex_str}\n"
                        f"  가능한 원인:\n"
                        f"  1) 프레임이 잘려서 도착 → 케이블 접촉 불량\n"
                        f"  2) 보레이트 불일치로 ETX(0x03) 바이트가 깨짐\n"
                        f"  3) PLC 응답이 비정상적으로 끊김"
                    )
                buffer.extend(byte)
                bytes_read += 1
                if byte[0] == ETX:
                    break
            else:
                hex_str = " ".join(f"{b:02X}" for b in buffer[:50])
                raise IOError(
                    f"프레임 크기 초과 ({MAX_FRAME_SIZE}바이트 이상, ETX 미발견)\n"
                    f"  수신 데이터 앞부분: {hex_str} ...\n"
                    f"  → 보레이트 불일치로 쓰레기 데이터가 계속 들어올 수 있습니다"
                )

            # 3. BCC 2바이트 읽기 (ASCII hex)
            bcc = self._serial.read(2)
            if len(bcc) < 2:
                hex_str = " ".join(f"{b:02X}" for b in buffer)
                raise TimeoutError(
                    f"BCC 수신 타임아웃 ({len(bcc)}/2 바이트만 수신)\n"
                    f"  지금까지 수신된 프레임:\n"
                    f"    HEX: {hex_str}\n"
                    f"  → 프레임 끝부분이 잘림. 케이블 접촉 불량 가능성"
                )
            buffer.extend(bcc)

        except (serial.SerialException, OSError) as e:
            if "device" in str(e).lower() or "disconnected" in str(e).lower():
                raise IOError(
                    f"시리얼 장치가 분리되었습니다: {e}\n"
                    f"  → USB-RS232C 케이블이 빠졌을 수 있습니다"
                ) from e
            raise
        finally:
            # timeout 복원
            if timeout > 0:
                try:
                    self._serial.timeout = self._timeout
                except (serial.SerialException, OSError):
                    pass

        return bytes(buffer)

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open
