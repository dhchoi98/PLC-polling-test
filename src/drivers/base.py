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
