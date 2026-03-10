"""여러 디바이스 순차 읽기 시간 측정 (핵심 테스트 #2)

동일 PLC에 연속 읽기를 20번 반복 수행하여,
20대 PLC를 순차 폴링하는 것과 유사한 시간을 측정한다.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.drivers.base import PLCError, PLCNAKError, PLCProtocolError
from src.utils import load_config, setup_logging, create_transport, create_driver, get_connection_info


REPEAT_COUNT = 20  # 20대 PLC 시뮬레이션


def main():
    parser = argparse.ArgumentParser(description="순차 읽기 시간 측정")
    parser.add_argument("--debug", action="store_true", help="디버그 모드 (TX/RX hex dump 출력)")
    parser.add_argument("-n", "--repeat", type=int, default=REPEAT_COUNT, help=f"반복 횟수 (기본: {REPEAT_COUNT})")
    parser.add_argument("-c", "--config", default="config.yaml", help="설정 파일 경로")
    args = parser.parse_args()

    repeat_count = args.repeat
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

    # 첫 번째 워드 디바이스 설정 사용
    word_devices = [d for d in config["plc"].get("devices", []) if d["type"] == "word"]
    if not word_devices:
        print("[FAIL] config.yaml에 type='word' 디바이스가 없습니다")
        return

    dev_cfg = word_devices[0]
    device = dev_cfg["device"]
    address = dev_cfg["address"]
    count = dev_cfg["count"]

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
    except Exception as e:
        print(f"[FAIL] 통신 에러: {type(e).__name__}: {e}")
        driver.disconnect()
        return

    print(f"\n{'=' * 50}")
    print(f"순차 읽기 시간 측정 ({repeat_count}회 반복)")
    print(f"읽기 대상: {device}{address}~{device}{address + count - 1} ({count}워드)")
    print(f"{'=' * 50}\n")

    try:
        times = []
        error_count = 0

        for i in range(repeat_count):
            try:
                start = time.perf_counter()
                values = driver.read_words(device, address, count)
                elapsed = (time.perf_counter() - start) * 1000
                times.append(elapsed)
                print(f"  {i + 1:2d}회차: {elapsed:.1f}ms")
            except TimeoutError as e:
                error_count += 1
                print(f"  {i + 1:2d}회차: [TIMEOUT] {e}")
            except PLCNAKError as e:
                error_count += 1
                print(f"  {i + 1:2d}회차: [PLC ERR] {e}")
            except PLCProtocolError as e:
                error_count += 1
                print(f"  {i + 1:2d}회차: [PROTO ERR] {e}")
            except Exception as e:
                error_count += 1
                print(f"  {i + 1:2d}회차: [{type(e).__name__}] {e}")

        if times:
            total = sum(times)
            avg = total / len(times)

            print(f"\n{'---' * 15}")
            print(f"성공: {len(times)}/{repeat_count}회")
            if error_count > 0:
                print(f"에러: {error_count}회")
            print(f"합계: {total:.1f}ms")
            print(f"평균: {avg:.1f}ms/회")
            print(f"{'---' * 15}")

            # 에러 포함하여 추정 (에러 시에도 타임아웃 시간이 소요됨)
            estimated = avg * repeat_count
            print(f"\n{repeat_count}대 PLC 순차 폴링 추정 시간: 약 {estimated:.0f}ms ({estimated / 1000:.1f}초)")

            if estimated < 1000:
                verdict = "1초 폴링 주기 가능"
            elif estimated < 5000:
                verdict = "5초 폴링 주기 가능"
            else:
                verdict = "폴링 주기 검토 필요"
            print(f"→ 판단: {verdict}")
        else:
            print(f"\n[FAIL] 모든 읽기가 실패했습니다 ({error_count}회 에러)")
            print("  → 케이블, 보레이트, PLC 상태를 확인하세요")

    except Exception as e:
        print(f"[FAIL] {type(e).__name__}: {e}")
    finally:
        driver.disconnect()
        print("\n[INFO] 연결 종료")


if __name__ == "__main__":
    main()
