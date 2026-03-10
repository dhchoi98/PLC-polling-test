from abc import ABC, abstractmethod


class Transport(ABC):
    @abstractmethod
    def open(self) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    @abstractmethod
    def send(self, data: bytes) -> None:
        ...

    @abstractmethod
    def receive(self, timeout: float = 1.0) -> bytes:
        ...

    @property
    @abstractmethod
    def is_open(self) -> bool:
        ...
