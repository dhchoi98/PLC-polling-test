"""PLC 메모리 인터랙티브 스캐너

실행 시 대화형으로 PLC 제조사, 프로토콜, 연결 방식을 선택한다.
config.yaml을 건드리지 않고 모든 설정을 런타임에 입력.

D 레지스터 전체를 스캔하여 값이 있는 주소만 터미널 + 로그 파일로 출력.

사용 예:
  python scripts/interactive_scan.py
  python scripts/interactive_scan.py --debug
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.drivers.base import PLCDriver, PLCError
from src.utils import setup_logging

# ──────────────────────────────────────────────
# 제조사 / 프로토콜 레지스트리
# 새 제조사·프로토콜은 여기에 항목만 추가하면 됨
# ──────────────────────────────────────────────

MANUFACTURERS = {
    "1": {
        "name": "LS Electric (LS산전)",
        "protocols": {
            "1": {
                "name": "XGT Cnet (시리얼 ASCII)",
                "connection": "serial",
                "driver": "xgt-cnet",
                "default_serial": {
                    "baudrate": 9600,
                    "bytesize": 8,
                    "parity": "none",
                    "stopbits": 1,
                    "timeout": 1.0,
                },
                "max_chunk": 32,
                "d_range": (0, 9999),
            },
            "2": {
                "name": "XGT FEnet (이더넷 바이너리)",
                "connection": "ethernet",
                "driver": "xgt-fenet",
                "default_ethernet": {
                    "port": 2004,
                    "timeout": 2.0,
                },
                "max_chunk": 60,
                "d_range": (0, 9999),
            },
            "3": {
                "name": "XGT Cnet over TCP (시리얼-이더넷 변환기)",
                "connection": "ethernet",
                "driver": "xgt-cnet",
                "default_ethernet": {
                    "port": 5000,
                    "timeout": 2.0,
                },
                "max_chunk": 32,
                "d_range": (0, 9999),
            },
        },
    },
    "2": {
        "name": "Mitsubishi (미쓰비시)",
        "protocols": {
            "1": {
                "name": "MC Protocol Binary (이더넷)",
                "connection": "ethernet",
                "driver": "mc-binary",
                "default_ethernet": {"port": 5000, "timeout": 2.0},
                "max_chunk": 960,
                "d_range": (0, 7999),
            },
            "2": {
                "name": "MC Protocol ASCII (시리얼/이더넷)",
                "connection": "serial",
                "driver": "mc-ascii",
                "default_serial": {
                    "baudrate": 9600,
                    "bytesize": 8,
                    "parity": "even",
                    "stopbits": 1,
                    "timeout": 1.0,
                },
                "max_chunk": 64,
                "d_range": (0, 7999),
            },
        },
    },
    "3": {
        "name": "Keyence (키엔스)",
        "protocols": {
            "1": {
                "name": "Upper Link (이더넷/시리얼)",
                "connection": "ethernet",
                "driver": "keyence-upper",
                "default_ethernet": {"port": 8501, "timeout": 2.0},
                "max_chunk": 256,
                "d_range": (0, 59999),
            },
        },
    },
    "4": {
        "name": "Panasonic (파나소닉)",
        "protocols": {
            "1": {
                "name": "MEWTOCOL (시리얼 RS-485)",
                "connection": "serial",
                "driver": "mewtocol",
                "default_serial": {
                    "baudrate": 9600,
                    "bytesize": 8,
                    "parity": "odd",
                    "stopbits": 1,
                    "timeout": 1.0,
                },
                "max_chunk": 32,
                "d_range": (0, 32764),
            },
            "2": {
                "name": "MEWTOCOL over TCP",
                "connection": "ethernet",
                "driver": "mewtocol-tcp",
                "default_ethernet": {"port": 9094, "timeout": 2.0},
                "max_chunk": 32,
                "d_range": (0, 32764),
            },
        },
    },
}

# 현재 구현 완료된 드라이버
IMPLEMENTED_DRIVERS = {"xgt-cnet", "xgt-fenet"}


# ──────────────────────────────────────────────
# 사용자 입력 헬퍼
# ──────────────────────────────────────────────

def ask_choice(prompt: str, options: dict) -> str:
    """번호 선택 입력"""
    print(f"\n{prompt}")
    for key, opt in options.items():
        name = opt["name"] if isinstance(opt, dict) else opt
        print(f"  [{key}] {name}")

    while True:
        choice = input("\n선택 > ").strip()
        if choice in options:
            return choice
        print(f"  잘못된 선택입니다. ({', '.join(options.keys())} 중 선택)")


def ask_input(prompt: str, default=None, cast=None):
    """기본값 있는 입력"""
    if default is not None:
        display = f"{prompt} [{default}]: "
    else:
        display = f"{prompt}: "

    while True:
        raw = input(display).strip()
        if not raw and default is not None:
            return default
        if not raw:
            print("  값을 입력해주세요.")
            continue
        if cast:
            try:
                return cast(raw)
            except (ValueError, TypeError):
                print(f"  잘못된 형식입니다.")
                continue
        return raw


def ask_serial_params(defaults: dict) -> dict:
    """시리얼 연결 파라미터 입력"""
    print("\n── 시리얼 연결 설정 ──")
    port = ask_input("COM 포트 (예: COM3, /dev/ttyUSB0)")
    baudrate = ask_input("보레이트", default=defaults["baudrate"], cast=int)
    bytesize = ask_input("데이터 비트 (7/8)", default=defaults["bytesize"], cast=int)
    parity = ask_input("패리티 (none/even/odd)", default=defaults["parity"])
    stopbits = ask_input("스톱 비트 (1/2)", default=defaults["stopbits"], cast=int)
    timeout = ask_input("타임아웃 (초)", default=defaults["timeout"], cast=float)
    return {
        "port": port,
        "baudrate": baudrate,
        "bytesize": bytesize,
        "parity": parity,
        "stopbits": stopbits,
        "timeout": timeout,
    }


def ask_ethernet_params(defaults: dict) -> dict:
    """이더넷 연결 파라미터 입력"""
    print("\n── 이더넷 연결 설정 ──")
    host = ask_input("PLC IP 주소 (예: 192.168.1.2)")
    port = ask_input("포트 번호", default=defaults["port"], cast=int)
    timeout = ask_input("타임아웃 (초)", default=defaults["timeout"], cast=float)
    return {
        "host": host,
        "port": port,
        "timeout": timeout,
    }


def ask_scan_range(d_range: tuple) -> tuple:
    """스캔 범위 입력"""
    d_min, d_max = d_range
    print(f"\n── D 레지스터 스캔 범위 (허용: D{d_min}~D{d_max}) ──")
    start = ask_input("시작 주소", default=d_min, cast=int)
    end = ask_input("끝 주소", default=d_max, cast=int)
    if start > end:
        start, end = end, start
    start = max(start, d_min)
    end = min(end, d_max)
    return start, end


# ──────────────────────────────────────────────
# 드라이버/트랜스포트 런타임 생성
# config.yaml 의존 없이 파라미터로 직접 생성
# ──────────────────────────────────────────────

def create_transport_runtime(driver_name: str, conn_type: str, params: dict):
    """런타임 파라미터로 Transport 인스턴스 생성"""
    if conn_type == "serial":
        from src.transport.serial_transport import SerialTransport
        return SerialTransport(
            port=params["port"],
            baudrate=params["baudrate"],
            bytesize=params["bytesize"],
            parity=params["parity"],
            stopbits=params["stopbits"],
            timeout=params["timeout"],
        )
    elif conn_type == "ethernet":
        if driver_name == "xgt-fenet":
            from src.transport.fenet_transport import FEnetTransport
            return FEnetTransport(
                host=params["host"],
                port=params.get("port", 2004),
                timeout=params.get("timeout", 2.0),
            )
        else:
            from src.transport.tcp_transport import TCPTransport
            return TCPTransport(
                host=params["host"],
                port=params["port"],
                timeout=params["timeout"],
            )
    raise ValueError(f"지원하지 않는 연결 방식: {conn_type}")


def create_driver_runtime(driver_name: str, transport, **kwargs) -> PLCDriver:
    """런타임 파라미터로 PLCDriver 인스턴스 생성"""
    if driver_name == "xgt-cnet":
        from src.drivers.xgt_protocol import XGTProtocolDriver
        station = kwargs.get("station", 0)
        return XGTProtocolDriver(transport, station=station)
    elif driver_name == "xgt-fenet":
        from src.drivers.xgt_fenet import XGTFEnetDriver
        slot = kwargs.get("fenet_slot", 0)
        return XGTFEnetDriver(transport, slot=slot)
    else:
        raise NotImplementedError(
            f"'{driver_name}' 드라이버는 아직 구현되지 않았습니다.\n"
            f"  현재 구현된 드라이버: {', '.join(sorted(IMPLEMENTED_DRIVERS))}"
        )


# ──────────────────────────────────────────────
# 스캔 로직
# ──────────────────────────────────────────────

def scan_d_registers(driver: PLCDriver, start: int, end: int,
                     chunk_size: int) -> tuple:
    """
    D 레지스터 범위를 청크 단위로 읽고 non-zero 값만 수집.
    진행률을 터미널에 실시간 표시.
    """
    results = {}
    errors = []
    total = end - start + 1
    addr = start

    while addr <= end:
        count = min(chunk_size, end - addr + 1)
        try:
            values = driver.read_words("D", addr, count)
            for i, v in enumerate(values):
                if v != 0:
                    results[addr + i] = v
        except Exception as e:
            errors.append((addr, addr + count - 1, type(e).__name__, str(e)))

        done = min(addr + count - start, total)
        pct = done / total * 100
        print(f"\r  스캔 진행: {pct:5.1f}% ({done}/{total})", end="", flush=True)
        addr += count

    print(f"\r  스캔 완료: 100.0% ({total}/{total})     ")
    return results, errors


def format_results_table(results: dict) -> list:
    """결과를 테이블 라인 리스트로 포맷"""
    lines = []
    if not results:
        lines.append("  (값이 있는 D 레지스터가 없습니다)")
        return lines

    lines.append(f"  {'주소':<12} {'10진수':>10}  {'16진수':>10}  {'부호있는값':>10}")
    lines.append(f"  {'─' * 12} {'─' * 10}  {'─' * 10}  {'─' * 10}")

    for addr in sorted(results.keys()):
        v = results[addr]
        signed = v if v < 32768 else v - 65536
        lines.append(f"  D{addr:<10} {v:>10}  0x{v:08X}  {signed:>10}")

    return lines


def write_log(filepath: str, header_lines: list, result_lines: list,
              summary_lines: list):
    """결과를 로그 파일로 저장"""
    with open(filepath, "w", encoding="utf-8") as f:
        for line in header_lines:
            f.write(line + "\n")
        f.write("\n")
        for line in result_lines:
            f.write(line + "\n")
        f.write("\n")
        for line in summary_lines:
            f.write(line + "\n")


# ──────────────────────────────────────────────
# 메인 흐름
# ──────────────────────────────────────────────

def main():
    print("=" * 56)
    print("  PLC 메모리 인터랙티브 스캐너")
    print("  D 레지스터 전체 스캔 → non-zero 값만 출력")
    print("=" * 56)

    # --debug 플래그
    debug = "--debug" in sys.argv
    log_level = logging.DEBUG if debug else logging.WARNING
    setup_logging(log_level)

    # ── 1. 제조사 선택 ──
    mfr_key = ask_choice("PLC 제조사를 선택하세요:", MANUFACTURERS)
    mfr = MANUFACTURERS[mfr_key]
    print(f"  → {mfr['name']}")

    # ── 2. 프로토콜 선택 ──
    proto_key = ask_choice("프로토콜을 선택하세요:", mfr["protocols"])
    proto = mfr["protocols"][proto_key]
    print(f"  → {proto['name']}")

    # 미구현 드라이버 체크
    if proto["driver"] not in IMPLEMENTED_DRIVERS:
        print(f"\n[INFO] '{proto['name']}' 드라이버는 아직 구현되지 않았습니다.")
        print(f"  현재 사용 가능: {', '.join(sorted(IMPLEMENTED_DRIVERS))}")
        print(f"  향후 드라이버를 추가하면 이 메뉴에서 바로 사용 가능합니다.")
        return

    # ── 3. 연결 파라미터 입력 ──
    conn_type = proto["connection"]
    if conn_type == "serial":
        conn_params = ask_serial_params(proto["default_serial"])
        conn_info = f"{conn_params['port']} @ {conn_params['baudrate']}bps (시리얼)"
    else:
        conn_params = ask_ethernet_params(proto["default_ethernet"])
        conn_info = f"{conn_params['host']}:{conn_params['port']} (이더넷)"

    # 프로토콜별 추가 파라미터
    extra_kwargs = {}
    if proto["driver"] == "xgt-fenet":
        extra_kwargs["fenet_slot"] = ask_input(
            "FEnet 모듈 슬롯 번호", default=0, cast=int
        )
    if proto["driver"] == "xgt-cnet":
        extra_kwargs["station"] = ask_input(
            "PLC 국번 (0~31, XG5000에서 확인)", default=0, cast=int
        )

    # ── 4. PLC 모델명 (로그 파일명용) ──
    plc_model = ask_input("PLC 모델명 (예: XBC-DR32H)", default="UNKNOWN")

    # ── 5. 스캔 범위 ──
    scan_start, scan_end = ask_scan_range(proto["d_range"])
    chunk_size = proto["max_chunk"]

    # ── 설정 확인 ──
    print(f"\n{'─' * 56}")
    print(f"  제조사   : {mfr['name']}")
    print(f"  프로토콜 : {proto['name']}")
    print(f"  연결     : {conn_info}")
    print(f"  모델명   : {plc_model}")
    print(f"  스캔 범위: D{scan_start} ~ D{scan_end} ({scan_end - scan_start + 1}개)")
    print(f"  청크 크기: {chunk_size} 워드/회")
    if "fenet_slot" in extra_kwargs:
        print(f"  FEnet 슬롯: {extra_kwargs['fenet_slot']}")
    if "station" in extra_kwargs:
        print(f"  PLC 국번  : {extra_kwargs['station']}")
    print(f"{'─' * 56}")

    confirm = input("\n시작하시겠습니까? (Y/n) > ").strip().lower()
    if confirm == "n":
        print("취소됨.")
        return

    # ── 5. 연결 ──
    print(f"\n[1/3] 연결 중... {conn_info}")
    try:
        transport = create_transport_runtime(proto["driver"], conn_type, conn_params)
        driver = create_driver_runtime(proto["driver"], transport, **extra_kwargs)
        driver.connect()
        print(f"  → 연결 성공")
    except Exception as e:
        print(f"[FAIL] 연결 실패:\n  {e}")
        return

    # ── 6. 통신 확인 ──
    print(f"[2/3] PLC 통신 확인 중...")
    try:
        test_val = driver.read_words("D", scan_start, 1)
        print(f"  → 통신 확인 완료 (D{scan_start} = {test_val[0]})")
    except Exception as e:
        print(f"[FAIL] 통신 실패:\n  {e}")
        driver.disconnect()
        return

    # ── 7. 전체 스캔 ──
    print(f"[3/3] D{scan_start}~D{scan_end} 스캔 시작...")
    scan_time_start = time.perf_counter()

    try:
        results, errors = scan_d_registers(
            driver, scan_start, scan_end, chunk_size
        )
        elapsed_ms = (time.perf_counter() - scan_time_start) * 1000
    except KeyboardInterrupt:
        elapsed_ms = (time.perf_counter() - scan_time_start) * 1000
        print("\n\n[INFO] 스캔 중단됨 (Ctrl+C)")
        driver.disconnect()
        return
    finally:
        driver.disconnect()

    # ── 8. 결과 출력 ──
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = scan_end - scan_start + 1

    header_lines = [
        f"PLC 메모리 스캔 결과",
        f"  시각       : {timestamp}",
        f"  제조사     : {mfr['name']}",
        f"  모델명     : {plc_model}",
        f"  프로토콜   : {proto['name']}",
        f"  연결       : {conn_info}",
        f"  스캔 범위  : D{scan_start} ~ D{scan_end} ({total}개)",
    ]

    result_lines = format_results_table(results)

    summary_lines = [
        f"{'=' * 56}",
        f"  스캔 요약",
        f"{'=' * 56}",
        f"  전체 주소  : {total}개",
        f"  non-zero   : {len(results)}개",
        f"  에러       : {len(errors)}개",
        f"  소요 시간  : {elapsed_ms:.0f}ms ({elapsed_ms / 1000:.1f}초)",
    ]
    if total > 0:
        summary_lines.append(
            f"  평균 속도  : {elapsed_ms / total:.2f}ms/워드"
        )

    if errors:
        summary_lines.append(f"\n  ── 에러 목록 (최대 10건) ──")
        for s, e, etype, detail in errors[:10]:
            summary_lines.append(f"  D{s}~D{e}: [{etype}]")
        if len(errors) > 10:
            summary_lines.append(f"  ... 외 {len(errors) - 10}건")

    summary_lines.append(f"{'=' * 56}")

    # 터미널 출력
    print()
    for line in header_lines:
        print(line)
    print()
    for line in result_lines:
        print(line)
    print()
    for line in summary_lines:
        print(line)

    # ── 9. 로그 파일 저장 ──
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # 파일명: scan_모델명_프로토콜_연결방식_날짜시간.log
    # 예: scan_XBC-DR32H_cnet_serial_20260311_173500.log
    proto_short = proto["driver"].replace("xgt-", "")  # cnet, fenet
    conn_short = conn_type  # serial, ethernet
    model_safe = plc_model.replace(" ", "-")
    log_filename = datetime.now().strftime(
        f"scan_{model_safe}_{proto_short}_{conn_short}_%Y%m%d_%H%M%S.log"
    )
    log_path = log_dir / log_filename

    write_log(str(log_path), header_lines, result_lines, summary_lines)
    print(f"\n[LOG] 결과 저장: {log_path}")


if __name__ == "__main__":
    main()
