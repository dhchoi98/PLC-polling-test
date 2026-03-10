"""
XGT FEnet 이더넷 전송 계층

XBL-EMTA 등 FEnet 이더넷 모듈과 TCP 통신.
Cnet ASCII 프레임(ETX+BCC)과 달리, 바이너리 헤더의 Length 필드로 프레임 경계를 판단한다.
"""

import errno
import logging
import socket
import struct
from typing import Optional

from src.transport.base import Transport

logger = logging.getLogger("plc_test")

# FEnet 헤더 크기 (고정 20바이트)
FENET_HEADER_SIZE = 20


class FEnetTransport(Transport):
    """XGT FEnet TCP 전송 계층"""

    def __init__(
        self,
        host: str,
        port: int = 2004,
        timeout: float = 2.0,
    ):
        self._host = host
        self._port = port
        self._timeout = timeout
        self._socket: Optional[socket.socket] = None

    def open(self) -> None:
        if self._socket:
            return

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(self._timeout)

        try:
            self._socket.connect((self._host, self._port))
            logger.info(f"FEnet TCP 연결 열림: {self._host}:{self._port}")

        except socket.timeout:
            self._socket = None
            raise IOError(
                f"FEnet 연결 타임아웃: {self._host}:{self._port} ({self._timeout}초 대기)\n"
                f"  가능한 원인:\n"
                f"  1) IP 주소가 틀림 → XG5000에서 XBL-EMTA IP 확인\n"
                f"  2) XBL-EMTA 모듈 전원 꺼짐 또는 미장착\n"
                f"  3) PC와 PLC가 같은 네트워크에 없음 → IP 대역 확인\n"
                f"  4) 방화벽이 차단 중 → Windows 방화벽 예외 추가"
            )

        except ConnectionRefusedError:
            self._socket = None
            raise IOError(
                f"FEnet 연결 거부됨: {self._host}:{self._port}\n"
                f"  가능한 원인:\n"
                f"  1) 포트 번호가 틀림 → XBL-EMTA 기본 포트는 2004\n"
                f"  2) XBL-EMTA가 다른 연결로 점유 중\n"
                f"  3) 모듈이 정상 작동하지 않음"
            )

        except socket.gaierror as e:
            self._socket = None
            raise IOError(
                f"호스트 이름 해석 실패: '{self._host}'\n"
                f"  → IP 주소 형식이 맞는지 확인 (예: 192.168.0.50)\n"
                f"  원본 에러: {e}"
            )

        except OSError as e:
            self._socket = None
            if e.errno == errno.ENETUNREACH:
                raise IOError(
                    f"네트워크에 도달할 수 없음: {self._host}:{self._port}\n"
                    f"  → LAN 케이블 연결 확인\n"
                    f"  → PC IP와 XBL-EMTA IP가 같은 서브넷인지 확인"
                )
            raise IOError(f"FEnet 연결 실패: {self._host}:{self._port}\n  에러: {e}")

    def close(self) -> None:
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            logger.info(f"FEnet TCP 연결 닫힘: {self._host}:{self._port}")
        self._socket = None

    def send(self, data: bytes) -> None:
        if not self._socket:
            raise IOError("FEnet 연결이 열려있지 않습니다 → open()을 먼저 호출하세요")

        try:
            self._socket.sendall(data)
        except BrokenPipeError:
            raise IOError("FEnet 연결이 끊어졌습니다 → XBL-EMTA 상태 확인, 재연결 필요")
        except socket.timeout:
            raise IOError("FEnet 전송 타임아웃 → 네트워크 상태 확인")

    def receive(self, timeout: float = 0) -> bytes:
        """
        FEnet 바이너리 프레임 수신

        20바이트 헤더를 먼저 읽고, 헤더의 Length 필드(offset 16~17)만큼
        추가 데이터를 읽어서 전체 프레임을 반환한다.
        """
        if not self._socket:
            raise IOError("FEnet 연결이 열려있지 않습니다 → open()을 먼저 호출하세요")

        if timeout > 0:
            self._socket.settimeout(timeout)

        try:
            # 1. 20바이트 헤더 읽기
            try:
                header = self._recv_exact(FENET_HEADER_SIZE)
            except socket.timeout:
                raise TimeoutError(
                    f"PLC 응답 없음 (FEnet 헤더 수신 타임아웃, {self._timeout}초 대기)\n"
                    f"  → XBL-EMTA ↔ CPU 백플레인 연결 확인\n"
                    f"  → XG5000에서 FEnet 모듈 상태 확인"
                )

            # 2. 헤더에서 데이터 길이 추출 (offset 16, 리틀엔디안 uint16)
            data_length = struct.unpack_from("<H", header, 16)[0]

            if data_length > 4096:
                hex_str = " ".join(f"{b:02X}" for b in header)
                raise IOError(
                    f"FEnet 응답 데이터 길이 비정상: {data_length} 바이트\n"
                    f"  헤더: {hex_str}\n"
                    f"  → 잘못된 응답이거나 프로토콜 불일치"
                )

            # 3. 데이터 영역 읽기
            if data_length > 0:
                try:
                    data = self._recv_exact(data_length)
                except socket.timeout:
                    raise TimeoutError(
                        f"FEnet 데이터 수신 타임아웃 (헤더 수신 후, {data_length}바이트 대기)"
                    )
            else:
                data = b""

            return header + data

        except socket.timeout:
            raise TimeoutError(f"FEnet 응답 수신 타임아웃 ({self._host}:{self._port})")
        finally:
            if timeout > 0:
                try:
                    self._socket.settimeout(self._timeout)
                except OSError:
                    pass

    def _recv_exact(self, size: int) -> bytes:
        """정확히 size 바이트를 수신"""
        data = bytearray()
        while len(data) < size:
            try:
                chunk = self._socket.recv(size - len(data))
            except ConnectionResetError:
                raise IOError(
                    "FEnet 연결이 끊어졌습니다\n"
                    "  → XBL-EMTA 상태 확인, PLC 전원 확인"
                )
            if not chunk:
                raise IOError(
                    f"FEnet 연결이 끊어졌습니다 (EOF, {len(data)}/{size} 바이트 수신)\n"
                    f"  → XBL-EMTA 또는 PLC 상태 확인"
                )
            data.extend(chunk)
        return bytes(data)

    @property
    def is_open(self) -> bool:
        return self._socket is not None
