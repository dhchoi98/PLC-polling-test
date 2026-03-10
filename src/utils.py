import logging
import yaml
from pathlib import Path
from typing import Any, Dict

from src.transport.base import Transport


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """로깅 설정"""
    logger = logging.getLogger("plc_test")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def bytes_to_hex(data: bytes) -> str:
    """바이트를 보기 좋은 hex 문자열로 변환"""
    return " ".join(f"{b:02X}" for b in data)


def hex_dump(data: bytes, label: str = "") -> str:
    """디버깅용 hex dump — 에러 발생 시 원본 데이터를 볼 수 있게"""
    if not data:
        return f"{label}(빈 데이터)"
    hex_str = " ".join(f"{b:02X}" for b in data)
    ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    lines = [f"{label}({len(data)} bytes):"]
    lines.append(f"  HEX: {hex_str}")
    lines.append(f"  ASCII: {ascii_str}")
    return "\n".join(lines)


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """YAML 설정 파일 로드 + 기본 검증"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"설정 파일을 찾을 수 없습니다: {config_path}\n"
            f"  → 프로젝트 루트에 config.yaml이 있는지 확인하세요.\n"
            f"  → 현재 작업 디렉토리: {Path.cwd()}"
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(
            f"config.yaml 파싱 실패 (YAML 문법 오류):\n  {e}"
        )

    if config is None:
        raise ValueError("config.yaml이 비어있습니다")

    validate_config(config)
    return config


def validate_config(config: Dict[str, Any]) -> None:
    """config.yaml 필수 필드 검증 — 현장 가서 헤매지 않도록 미리 잡아냄"""
    # plc 섹션
    if "plc" not in config:
        raise ValueError("config.yaml에 'plc' 섹션이 없습니다")

    plc = config["plc"]

    # 연결 방식
    conn_type = plc.get("connection", "serial")
    if conn_type not in ("serial", "ethernet"):
        raise ValueError(
            f"지원하지 않는 connection 값: '{conn_type}'\n"
            f"  → 'serial' 또는 'ethernet'만 가능합니다"
        )

    # 시리얼 설정 검증
    if conn_type == "serial":
        if "serial" not in plc:
            raise ValueError(
                "connection이 'serial'인데 serial 설정이 없습니다\n"
                "  → config.yaml에 serial: 섹션을 추가하세요"
            )
        scfg = plc["serial"]
        _validate_serial_config(scfg)

    # 이더넷 설정 검증
    if conn_type == "ethernet":
        if "ethernet" not in plc:
            raise ValueError(
                "connection이 'ethernet'인데 ethernet 설정이 없습니다\n"
                "  → config.yaml에 ethernet: 섹션을 추가하세요"
            )
        ecfg = plc["ethernet"]
        _validate_ethernet_config(ecfg)

    # 디바이스 목록 검증
    if "devices" in plc:
        for i, dev in enumerate(plc["devices"]):
            _validate_device_config(dev, i)


def _validate_serial_config(cfg: dict) -> None:
    """시리얼 설정 필수 필드 + 범위 검증"""
    required = ["port", "baudrate", "bytesize", "parity", "stopbits", "timeout"]
    for field in required:
        if field not in cfg:
            raise ValueError(
                f"serial 설정에 '{field}' 필드가 없습니다\n"
                f"  → config.yaml의 serial: 섹션에 {field}을 추가하세요"
            )

    # 포트명 검증
    port = cfg["port"]
    if not isinstance(port, str) or not port.strip():
        raise ValueError(f"serial.port 값이 비어있습니다 → COM 포트 번호를 입력하세요")

    # 보레이트 범위
    baudrate = cfg["baudrate"]
    valid_baudrates = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
    if baudrate not in valid_baudrates:
        raise ValueError(
            f"serial.baudrate 값이 비정상적입니다: {baudrate}\n"
            f"  → 허용: {valid_baudrates}\n"
            f"  → PLC의 Cnet 설정(XG5000)에서 보레이트를 확인하세요"
        )

    # 바이트 사이즈
    if cfg["bytesize"] not in (7, 8):
        raise ValueError(f"serial.bytesize는 7 또는 8이어야 합니다: {cfg['bytesize']}")

    # 패리티
    if cfg["parity"] not in ("none", "even", "odd"):
        raise ValueError(
            f"serial.parity 값이 잘못됐습니다: '{cfg['parity']}'\n"
            f"  → 'none', 'even', 'odd' 중 하나"
        )

    # 스톱비트
    if cfg["stopbits"] not in (1, 2):
        raise ValueError(f"serial.stopbits는 1 또는 2여야 합니다: {cfg['stopbits']}")

    # 타임아웃
    timeout = cfg["timeout"]
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError(f"serial.timeout은 0보다 커야 합니다: {timeout}")
    if timeout > 10:
        raise ValueError(
            f"serial.timeout이 너무 큽니다: {timeout}초\n"
            f"  → 보통 1~3초 권장. 10초 이상이면 설정 실수 가능성"
        )


def _validate_ethernet_config(cfg: dict) -> None:
    """이더넷 설정 필수 필드 + 범위 검증"""
    required = ["host", "port", "timeout"]
    for field in required:
        if field not in cfg:
            raise ValueError(
                f"ethernet 설정에 '{field}' 필드가 없습니다\n"
                f"  → config.yaml의 ethernet: 섹션에 {field}을 추가하세요"
            )

    host = cfg["host"]
    if not isinstance(host, str) or not host.strip():
        raise ValueError("ethernet.host 값이 비어있습니다 → IP 주소를 입력하세요")

    port = cfg["port"]
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise ValueError(f"ethernet.port 범위 오류: {port} (1~65535)")

    timeout = cfg["timeout"]
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError(f"ethernet.timeout은 0보다 커야 합니다: {timeout}")


def _validate_device_config(dev: dict, index: int) -> None:
    """디바이스 설정 검증"""
    required = ["device", "address", "count", "type"]
    for field in required:
        if field not in dev:
            name = dev.get("name", f"#{index}")
            raise ValueError(
                f"devices[{name}]에 '{field}' 필드가 없습니다"
            )

    if dev["type"] not in ("word", "bit"):
        raise ValueError(
            f"devices[{dev.get('name', index)}].type은 'word' 또는 'bit'이어야 합니다: "
            f"'{dev['type']}'"
        )

    if dev["count"] < 1:
        raise ValueError(
            f"devices[{dev.get('name', index)}].count는 1 이상이어야 합니다: {dev['count']}"
        )

    if dev["type"] == "word" and dev["count"] > 60:
        raise ValueError(
            f"devices[{dev.get('name', index)}].count가 60을 초과합니다: {dev['count']}\n"
            f"  → SB 연속 읽기는 최대 60워드(120바이트)"
        )


def create_transport(config: Dict[str, Any]) -> Transport:
    """config.yaml의 connection 설정에 따라 Transport 생성"""
    conn_type = config["plc"].get("connection", "serial")
    protocol = config["plc"].get("protocol", "xgt-cnet")

    if conn_type == "serial":
        from src.transport.serial_transport import SerialTransport
        cfg = config["plc"]["serial"]
        return SerialTransport(
            port=cfg["port"],
            baudrate=cfg["baudrate"],
            bytesize=cfg["bytesize"],
            parity=cfg["parity"],
            stopbits=cfg["stopbits"],
            timeout=cfg["timeout"],
        )
    elif conn_type == "ethernet":
        cfg = config["plc"]["ethernet"]
        if protocol == "xgt-fenet":
            from src.transport.fenet_transport import FEnetTransport
            return FEnetTransport(
                host=cfg["host"],
                port=cfg.get("port", 2004),
                timeout=cfg.get("timeout", 2.0),
            )
        else:
            from src.transport.tcp_transport import TCPTransport
            return TCPTransport(
                host=cfg["host"],
                port=cfg["port"],
                timeout=cfg["timeout"],
            )
    else:
        raise ValueError(f"지원하지 않는 연결 방식: {conn_type}")


def create_driver(config: Dict[str, Any], transport: Transport):
    """config.yaml의 protocol 설정에 따라 PLC 드라이버 생성"""
    protocol = config["plc"].get("protocol", "xgt-cnet")

    if protocol in ("xgt", "xgt-cnet"):
        from src.drivers.xgt_protocol import XGTProtocolDriver
        return XGTProtocolDriver(transport)
    elif protocol == "xgt-fenet":
        from src.drivers.xgt_fenet import XGTFEnetDriver
        slot = config["plc"].get("fenet_slot", 0)
        return XGTFEnetDriver(transport, slot=slot)
    else:
        raise ValueError(
            f"지원하지 않는 프로토콜: '{protocol}'\n"
            f"  → 'xgt-cnet' (시리얼/Cnet) 또는 'xgt-fenet' (이더넷/FEnet)"
        )


def get_connection_info(config: Dict[str, Any]) -> str:
    """연결 정보를 사람이 읽기 좋은 문자열로 반환"""
    conn_type = config["plc"].get("connection", "serial")
    if conn_type == "serial":
        cfg = config["plc"]["serial"]
        return f"{cfg['port']} @ {cfg['baudrate']}bps (시리얼)"
    elif conn_type == "ethernet":
        cfg = config["plc"]["ethernet"]
        protocol = config["plc"].get("protocol", "xgt-cnet")
        proto_label = "FEnet" if protocol == "xgt-fenet" else "이더넷"
        return f"{cfg['host']}:{cfg['port']} ({proto_label})"
    return conn_type
