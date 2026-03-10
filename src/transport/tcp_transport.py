"""
TCP/IP 전송 계층

이더넷 직접 연결 또는 시리얼-이더넷 변환기를 통한 통신에 사용한다.
응답 수신 로직은 SerialTransport와 동일하게 ETX + BCC(2바이트 ASCII hex) 기반 프레임 감지.
"""

import errno
import logging
import socket
from typing import Optional

from src.transport.base import Transport

logger = logging.getLogger("plc_test")

# 응답 프레임 종료 감지용
ETX = 0x03
ACK = 0x06
NAK = 0x15

# 수신 버퍼 최대 크기 (무한 루프 방지)
MAX_FRAME_SIZE = 512


class TCPTransport(Transport):
    """TCP/IP 전송 계층"""

    def __init__(
        self,
        host: str,
        port: int = 2004,
        timeout: float = 1.0,
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
            logger.info(f"TCP 연결 열림: {self._host}:{self._port}")

        except socket.timeout:
            self._socket = None
            raise IOError(
                f"TCP 연결 타임아웃: {self._host}:{self._port} ({self._timeout}초 대기)\n"
                f"  가능한 원인:\n"
                f"  1) IP 주소가 틀림 → config.yaml의 ethernet.host 확인\n"
                f"  2) 시리얼-이더넷 변환기 전원 꺼짐\n"
                f"  3) PC와 변환기가 같은 네트워크에 없음 → IP 대역 확인\n"
                f"  4) 방화벽이 차단 중 → Windows 방화벽 예외 추가"
            )

        except ConnectionRefusedError:
            self._socket = None
            raise IOError(
                f"TCP 연결 거부됨: {self._host}:{self._port}\n"
                f"  가능한 원인:\n"
                f"  1) 포트 번호가 틀림 → config.yaml의 ethernet.port 확인\n"
                f"     (시리얼-이더넷 변환기 설정에서 포트 번호 확인)\n"
                f"  2) 변환기가 다른 포트를 사용 중\n"
                f"  3) 장비는 있으나 해당 포트에서 수신 대기하지 않음"
            )

        except socket.gaierror as e:
            self._socket = None
            raise IOError(
                f"호스트 이름 해석 실패: '{self._host}'\n"
                f"  → IP 주소 형식이 맞는지 확인 (예: 192.168.1.100)\n"
                f"  원본 에러: {e}"
            )

        except OSError as e:
            self._socket = None
            if e.errno == errno.ENETUNREACH:
                raise IOError(
                    f"네트워크에 도달할 수 없음: {self._host}:{self._port}\n"
                    f"  → PC의 네트워크 연결 상태 확인\n"
                    f"  → LAN 케이블이 연결되어 있는지 확인\n"
                    f"  → PC IP와 변환기 IP가 같은 서브넷인지 확인"
                )
            elif e.errno == errno.EHOSTUNREACH:
                raise IOError(
                    f"호스트에 도달할 수 없음: {self._host}:{self._port}\n"
                    f"  → 변환기 IP가 맞는지 확인\n"
                    f"  → cmd에서 'ping {self._host}' 시도"
                )
            raise IOError(
                f"TCP 연결 실패: {self._host}:{self._port}\n"
                f"  에러: {e}"
            )

    def close(self) -> None:
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            logger.info(f"TCP 연결 닫힘: {self._host}:{self._port}")
        self._socket = None

    def send(self, data: bytes) -> None:
        if not self._socket:
            raise IOError("TCP 연결이 열려있지 않습니다 → connect()를 먼저 호출하세요")

        try:
            self._socket.sendall(data)
        except BrokenPipeError:
            raise IOError(
                f"TCP 연결이 끊어졌습니다 (전송 중)\n"
                f"  → 변환기 상태 확인, 재연결 필요"
            )
        except socket.timeout:
            raise IOError(
                f"TCP 전송 타임아웃\n"
                f"  → 네트워크 상태 확인"
            )

    def receive(self, timeout: float = 0) -> bytes:
        """
        응답 프레임 수신

        SerialTransport와 동일한 로직:
        ACK/NAK 헤더 → ETX까지 읽기 → BCC 2바이트 읽기
        """
        if not self._socket:
            raise IOError("TCP 연결이 열려있지 않습니다 → connect()를 먼저 호출하세요")

        if timeout > 0:
            self._socket.settimeout(timeout)

        buffer = bytearray()

        try:
            # 1. 첫 바이트(ACK/NAK) 읽기
            try:
                header = self._recv_exact(1)
            except socket.timeout:
                raise TimeoutError(
                    f"PLC 응답 없음 (TCP 수신 타임아웃, {self._timeout}초 대기)\n"
                    f"  → 시리얼-이더넷 변환기 ↔ PLC 연결 확인\n"
                    f"  → 변환기의 시리얼 설정(보레이트 등)이 PLC와 일치하는지 확인"
                )
            buffer.extend(header)

            # 헤더 바이트 검증
            if header[0] not in (ACK, NAK):
                extra = b""
                try:
                    self._socket.settimeout(0.5)
                    extra = self._socket.recv(50)
                except (socket.timeout, OSError):
                    pass
                buffer.extend(extra)
                hex_str = " ".join(f"{b:02X}" for b in buffer)
                raise IOError(
                    f"예상치 못한 응답 헤더: 0x{header[0]:02X}\n"
                    f"  (ACK=0x06 또는 NAK=0x15를 기대)\n"
                    f"  수신 데이터: {hex_str}\n"
                    f"  → 변환기의 시리얼 보레이트가 PLC와 다를 수 있음"
                )

            # 2. ETX를 만날 때까지 읽기
            bytes_read = 1
            while bytes_read < MAX_FRAME_SIZE:
                try:
                    byte = self._recv_exact(1)
                except socket.timeout:
                    hex_str = " ".join(f"{b:02X}" for b in buffer)
                    raise TimeoutError(
                        f"TCP 응답 수신 중 타임아웃 (ETX 대기, {bytes_read}바이트 수신)\n"
                        f"  수신 데이터: {hex_str}\n"
                        f"  → 프레임이 잘렸을 수 있음"
                    )
                buffer.extend(byte)
                bytes_read += 1
                if byte[0] == ETX:
                    break
            else:
                hex_str = " ".join(f"{b:02X}" for b in buffer[:50])
                raise IOError(
                    f"프레임 크기 초과 ({MAX_FRAME_SIZE}바이트, ETX 미발견)\n"
                    f"  수신 앞부분: {hex_str} ...\n"
                    f"  → 보레이트 불일치로 쓰레기 데이터가 올 수 있음"
                )

            # 3. BCC 2바이트 읽기 (ASCII hex)
            try:
                bcc = self._recv_exact(2)
            except socket.timeout:
                hex_str = " ".join(f"{b:02X}" for b in buffer)
                raise TimeoutError(
                    f"BCC 수신 타임아웃\n"
                    f"  수신 프레임: {hex_str}"
                )
            buffer.extend(bcc)

        except socket.timeout:
            raise TimeoutError(
                f"TCP 응답 수신 타임아웃 ({self._host}:{self._port})"
            )
        finally:
            # timeout 복원
            if timeout > 0:
                try:
                    self._socket.settimeout(self._timeout)
                except OSError:
                    pass

        return bytes(buffer)

    def _recv_exact(self, size: int) -> bytes:
        """정확히 size 바이트를 수신"""
        data = bytearray()
        while len(data) < size:
            try:
                chunk = self._socket.recv(size - len(data))
            except ConnectionResetError:
                raise IOError(
                    f"TCP 연결이 상대방에 의해 끊어졌습니다\n"
                    f"  → 변환기 상태 확인, PLC 전원 확인"
                )
            if not chunk:
                raise IOError(
                    f"TCP 연결이 끊어졌습니다 (수신 중 EOF, {len(data)}/{size} 바이트 수신)\n"
                    f"  → 변환기 또는 PLC 상태 확인"
                )
            data.extend(chunk)
        return bytes(data)

    @property
    def is_open(self) -> bool:
        return self._socket is not None
