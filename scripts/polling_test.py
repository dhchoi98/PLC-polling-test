"""반복 폴링 + 소요 시간 측정 (핵심 테스트 #1)

--debug 옵션으로 TX/RX 프레임을 hex로 볼 수 있다.
"""

import argparse
import csv
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.drivers.base import PLCError, PLCNAKError, PLCProtocolError
from src.utils import load_config, setup_logging, create_transport, create_driver, get_connection_info


def main():
    parser = argparse.ArgumentParser(description="반복 폴링 + 소요 시간 측정")
    parser.add_argument("--debug", action="store_true", help="디버그 모드 (TX/RX hex dump 출력)")
    parser.add_argument("-c", "--config", default="config.yaml", help="설정 파일 경로")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logger = setup_logging(log_level)

    # --- 0단계: 설정 파일 로드 ---
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(f"[FAIL] {e}")
        return

    try:
        transport = create_transport(config)
        conn_info = get_connection_info(config)
    except Exception as e:
        print(f"[FAIL] Transport 생성 실패: {e}")
        return

    driver = create_driver(config, transport)

    polling_cfg = config.get("polling", {})
    interval = polling_cfg.get("interval_sec", 1.0)
    duration = polling_cfg.get("duration_sec", 60)
    log_file = polling_cfg.get("log_file", "polling_results.csv")

    cycle_times = []
    read_times = []
    error_count = 0
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 10

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
    except PLCNAKError as e:
        print(f"[FAIL] PLC 에러:\n{e}")
        driver.disconnect()
        return
    except PLCProtocolError as e:
        print(f"[FAIL] 프로토콜 에러:\n{e}")
        driver.disconnect()
        return
    except IOError as e:
        print(f"[FAIL] 통신 에러:\n{e}")
        driver.disconnect()
        return
    except Exception as e:
        print(f"[FAIL] 예기치 않은 에러: {type(e).__name__}: {e}")
        driver.disconnect()
        return

    print(f"[INFO] 폴링 시작: 주기={interval}초, 지속={duration}초")
    print("[INFO] Ctrl+C로 중지\n")

    try:
        with open(log_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["cycle", "timestamp", "device", "address", "value", "elapsed_ms"])

            start_time = time.perf_counter()
            cycle = 0

            while time.perf_counter() - start_time < duration:
                cycle += 1
                cycle_start = time.perf_counter()

                for dev_cfg in config["plc"].get("devices", []):
                    device = dev_cfg["device"]
                    address = dev_cfg["address"]
                    count = dev_cfg["count"]
                    dev_type = dev_cfg["type"]

                    try:
                        read_start = time.perf_counter()
                        if dev_type == "word":
                            values = driver.read_words(device, address, count)
                        else:
                            values = driver.read_bits(device, address, count)
                        read_elapsed = (time.perf_counter() - read_start) * 1000
                        read_times.append(read_elapsed)
                        consecutive_errors = 0  # 성공 시 리셋

                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        for i, v in enumerate(values):
                            writer.writerow([
                                cycle, timestamp, device, address + i,
                                int(v) if isinstance(v, bool) else v,
                                f"{read_elapsed:.1f}",
                            ])

                    except TimeoutError as e:
                        error_count += 1
                        consecutive_errors += 1
                        logger.error(f"사이클 {cycle} 타임아웃: {device}{address} ({e})")
                    except PLCNAKError as e:
                        error_count += 1
                        consecutive_errors += 1
                        logger.error(f"사이클 {cycle} PLC 에러: {e}")
                    except PLCProtocolError as e:
                        error_count += 1
                        consecutive_errors += 1
                        logger.error(f"사이클 {cycle} 프로토콜 에러: {e}")
                    except Exception as e:
                        error_count += 1
                        consecutive_errors += 1
                        logger.error(f"사이클 {cycle} 에러: {type(e).__name__}: {e}")

                    # 연속 에러가 너무 많으면 중단
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        print(f"\n[STOP] 연속 {MAX_CONSECUTIVE_ERRORS}회 에러 발생 — 폴링 중단")
                        print("  → 케이블 분리, PLC 전원 끊김, 보레이트 불안정 등 확인")
                        raise KeyboardInterrupt  # 통계 출력으로 넘어가기

                cycle_elapsed = (time.perf_counter() - cycle_start) * 1000
                cycle_times.append(cycle_elapsed)

                status = f"  사이클 {cycle}: {cycle_elapsed:.1f}ms"
                if error_count > 0:
                    status += f" (에러 누적: {error_count})"
                print(status, end="\r")

                # 다음 사이클까지 대기
                sleep_time = interval - (time.perf_counter() - cycle_start)
                if sleep_time > 0:
                    time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n\n[INFO] 폴링 중지됨")
    except IOError as e:
        print(f"\n[FAIL] 파일 에러: {e}")
    except Exception as e:
        print(f"\n[FAIL] 예기치 않은 에러: {type(e).__name__}: {e}")
    finally:
        driver.disconnect()

    # 통계 출력
    if cycle_times:
        print(f"\n{'=' * 40}")
        print("폴링 테스트 결과")
        print(f"{'=' * 40}")
        print(f"총 사이클: {len(cycle_times)}")
        if read_times:
            print(f"1회 읽기 평균: {sum(read_times) / len(read_times):.1f}ms")
            print(f"1회 읽기 최소: {min(read_times):.1f}ms")
            print(f"1회 읽기 최대: {max(read_times):.1f}ms")
        print(f"전체 사이클 평균: {sum(cycle_times) / len(cycle_times):.1f}ms")
        print(f"통신 에러: {error_count}회")
        if error_count > 0:
            error_rate = error_count / len(cycle_times) * 100
            print(f"에러율: {error_rate:.1f}%")
        print(f"결과 파일: {log_file}")


if __name__ == "__main__":
    main()
