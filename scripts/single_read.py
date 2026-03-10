"""PLC 1회 읽기 테스트

가장 먼저 실행할 스크립트. PLC와 통신이 되는지 기본 확인.
--debug 옵션으로 TX/RX 프레임을 hex로 볼 수 있다.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.drivers.base import PLCError, PLCNAKError, PLCProtocolError
from src.utils import load_config, setup_logging, create_transport, create_driver, get_connection_info


def main():
    parser = argparse.ArgumentParser(description="PLC 1회 읽기 테스트")
    parser.add_argument("--debug", action="store_true", help="디버그 모드 (TX/RX hex dump 출력)")
    parser.add_argument("-c", "--config", default="config.yaml", help="설정 파일 경로")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logger = setup_logging(log_level)

    # --- 0단계: 설정 파일 로드 ---
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"[FAIL] {e}")
        return
    except ValueError as e:
        print(f"[FAIL] 설정 오류: {e}")
        return

    try:
        transport = create_transport(config)
        conn_info = get_connection_info(config)
    except Exception as e:
        print(f"[FAIL] Transport 생성 실패: {e}")
        return

    driver = create_driver(config, transport)

    # --- 1단계: 포트 열기 ---
    try:
        driver.connect()
        print(f"[1/2] 연결 열림: {conn_info}")
    except IOError as e:
        print(f"[FAIL] 연결 실패:\n{e}")
        return
    except Exception as e:
        print(f"[FAIL] 예기치 않은 연결 에러: {type(e).__name__}: {e}")
        return

    # --- 2단계: PLC 통신 확인 (D0 시험 읽기) ---
    try:
        test_val = driver.read_words("D", 0, 1)
        print(f"[2/2] PLC 통신 확인 완료 (D0 = {test_val[0]})")
    except TimeoutError as e:
        print(f"[FAIL] PLC 응답 없음:\n{e}")
        driver.disconnect()
        return
    except PLCProtocolError as e:
        print(f"[FAIL] 프로토콜 에러 (데이터 깨짐):\n{e}")
        driver.disconnect()
        return
    except PLCNAKError as e:
        print(f"[FAIL] PLC가 에러 응답 반환:\n{e}")
        driver.disconnect()
        return
    except IOError as e:
        print(f"[FAIL] 통신 에러:\n{e}")
        driver.disconnect()
        return
    except Exception as e:
        print(f"[FAIL] 예기치 않은 에러: {type(e).__name__}: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        driver.disconnect()
        return

    # --- 디바이스 읽기 ---
    print()
    devices = config["plc"].get("devices", [])
    if not devices:
        print("[INFO] config.yaml에 devices 목록이 없습니다. D0 읽기만 수행했습니다.")
        driver.disconnect()
        return

    try:
        for dev_cfg in devices:
            device = dev_cfg["device"]
            address = dev_cfg["address"]
            count = dev_cfg["count"]
            dev_type = dev_cfg["type"]
            name = dev_cfg.get("name", f"{device}{address}")

            start = time.perf_counter()

            try:
                if dev_type == "word":
                    values = driver.read_words(device, address, count)
                    result_str = ", ".join(
                        f"{device}{address + i}={v}" for i, v in enumerate(values)
                    )
                else:
                    values = driver.read_bits(device, address, count)
                    result_str = ", ".join(
                        f"{device}{address + i}={'ON' if v else 'OFF'}"
                        for i, v in enumerate(values)
                    )

                elapsed = (time.perf_counter() - start) * 1000
                print(f"[READ] [{name}] {result_str}")
                print(f"[OK] 소요 시간: {elapsed:.1f}ms")

            except TimeoutError as e:
                print(f"[FAIL] [{name}] 타임아웃:\n{e}")
            except PLCNAKError as e:
                print(f"[FAIL] [{name}] PLC 에러:\n{e}")
            except PLCProtocolError as e:
                print(f"[FAIL] [{name}] 프로토콜 에러:\n{e}")
            except Exception as e:
                print(f"[FAIL] [{name}] {type(e).__name__}: {e}")
                if args.debug:
                    import traceback
                    traceback.print_exc()
            print()

    finally:
        driver.disconnect()
        print("[INFO] 연결 종료")


if __name__ == "__main__":
    main()
