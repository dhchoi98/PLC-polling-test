"""PLC 메모리 영역 스캔

지정한 디바이스 영역을 범위로 읽어서 터미널에 표시한다.
0이 아닌 주소를 찾아 래더 프로그램에서 실제 사용 중인 영역을 추정할 수 있다.

사용 예:
  python scripts/memory_scan.py                         # D0~D999 전체 스캔
  python scripts/memory_scan.py -d D -s 0 -e 199        # D0~D199 스캔
  python scripts/memory_scan.py -d M -s 0 -e 255 --bit  # M0~M255 비트 스캔
  python scripts/memory_scan.py --nonzero                # 0이 아닌 값만 표시
  python scripts/memory_scan.py --debug                  # TX/RX hex dump 출력
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.drivers.xgt_protocol import XGTProtocolDriver, XGTNAKError, XGTBCCError
from src.utils import load_config, setup_logging, create_transport, get_connection_info


# 1회 읽기 최대 워드 수 (너무 크면 PLC가 거부할 수 있음)
MAX_CHUNK_SIZE = 32


def scan_words(driver, device, start, end, chunk_size):
    """워드 디바이스 영역을 청크 단위로 읽기"""
    results = {}
    errors = []
    addr = start
    total = end - start + 1
    while addr <= end:
        count = min(chunk_size, end - addr + 1)
        try:
            values = driver.read_words(device, addr, count)
            for i, v in enumerate(values):
                results[addr + i] = v
        except TimeoutError as e:
            errors.append((addr, addr + count - 1, "타임아웃", str(e)))
            print(f"  [TIMEOUT] {device}{addr}~{device}{addr + count - 1}: 응답 없음")
        except XGTNAKError as e:
            errors.append((addr, addr + count - 1, "NAK", str(e)))
            print(f"  [NAK] {device}{addr}~{device}{addr + count - 1}: {e}")
        except XGTBCCError as e:
            errors.append((addr, addr + count - 1, "BCC", str(e)))
            print(f"  [BCC] {device}{addr}~{device}{addr + count - 1}: 데이터 깨짐")
        except Exception as e:
            errors.append((addr, addr + count - 1, type(e).__name__, str(e)))
            print(f"  [ERR] {device}{addr}~{device}{addr + count - 1}: {type(e).__name__}: {e}")

        done = min(addr + count - start, total)
        pct = done / total * 100
        print(f"  스캔 진행: {pct:.0f}% ({done}/{total})", end="\r")
        addr += count

    print(f"  스캔 완료: 100% ({total}/{total})    ")  # 줄 클리어
    return results, errors


def scan_bits(driver, device, start, end, chunk_size):
    """비트 디바이스 영역을 읽기 (SS 개별 읽기)"""
    results = {}
    errors = []
    total = end - start + 1
    for addr in range(start, end + 1):
        try:
            values = driver.read_bits(device, addr, 1)
            results[addr] = values[0]
        except TimeoutError:
            errors.append((addr, addr, "타임아웃", ""))
            print(f"  [TIMEOUT] {device}{addr}")
        except XGTNAKError as e:
            errors.append((addr, addr, "NAK", str(e)))
            print(f"  [NAK] {device}{addr}: {e}")
        except Exception as e:
            errors.append((addr, addr, type(e).__name__, str(e)))

        done = addr - start + 1
        pct = done / total * 100
        print(f"  스캔 진행: {pct:.0f}% ({done}/{total})", end="\r")

    print(f"  스캔 완료: 100% ({total}/{total})    ")
    return results, errors


def print_word_results(device, results, nonzero_only):
    """워드 결과를 테이블 형태로 출력"""
    if nonzero_only:
        results = {a: v for a, v in results.items() if v != 0}

    if not results:
        print("\n  (결과 없음 — 모든 값이 0이거나 읽기 실패)")
        return

    print(f"\n  {'주소':<12} {'10진수':>8}  {'16진수':>8}  {'비고'}")
    print(f"  {'─' * 12} {'─' * 8}  {'─' * 8}  {'─' * 10}")

    for addr in sorted(results.keys()):
        v = results[addr]
        marker = "  ◀ non-zero" if v != 0 else ""
        print(f"  {device}{addr:<9} {v:>8}  0x{v:04X}    {marker}")


def print_bit_results(device, results, nonzero_only):
    """비트 결과를 테이블 형태로 출력"""
    if nonzero_only:
        results = {a: v for a, v in results.items() if v}

    if not results:
        print("\n  (결과 없음 — 모든 비트가 OFF이거나 읽기 실패)")
        return

    print(f"\n  {'주소':<12} {'상태':>6}  {'비고'}")
    print(f"  {'─' * 12} {'─' * 6}  {'─' * 10}")

    for addr in sorted(results.keys()):
        v = results[addr]
        state = "ON" if v else "OFF"
        marker = "  ◀ ON" if v else ""
        print(f"  {device}{addr:<9} {state:>6}  {marker}")


def print_summary(device, start, end, results, errors, is_bit, elapsed):
    """스캔 결과 요약"""
    total = end - start + 1
    read_ok = len(results)
    read_fail = len(errors)

    if is_bit:
        active = sum(1 for v in results.values() if v)
        label = "ON 비트"
    else:
        active = sum(1 for v in results.values() if v != 0)
        label = "non-zero 워드"

    print(f"\n{'=' * 50}")
    print(f"  스캔 범위 : {device}{start} ~ {device}{end} ({total}개)")
    print(f"  읽기 성공 : {read_ok}개")
    print(f"  읽기 실패 : {read_fail}개")
    print(f"  {label:<12}: {active}개")
    print(f"  소요 시간 : {elapsed:.0f}ms ({elapsed/1000:.1f}초)")

    if errors:
        print(f"\n  --- 에러 목록 ---")
        for s, e, etype, detail in errors[:10]:
            if s == e:
                print(f"  {device}{s}: [{etype}]")
            else:
                print(f"  {device}{s}~{device}{e}: [{etype}]")
        if len(errors) > 10:
            print(f"  ... 외 {len(errors) - 10}건")

    print(f"{'=' * 50}")


def main():
    parser = argparse.ArgumentParser(description="PLC 메모리 영역 스캔")
    parser.add_argument("-d", "--device", default="D", help="디바이스 타입 (기본: D)")
    parser.add_argument("-s", "--start", type=int, default=0, help="시작 주소 (기본: 0)")
    parser.add_argument("-e", "--end", type=int, default=999, help="끝 주소 (기본: 999)")
    parser.add_argument("--bit", action="store_true", help="비트 디바이스로 읽기 (M, P 등)")
    parser.add_argument("--nonzero", action="store_true", help="0이 아닌 값만 표시")
    parser.add_argument("--chunk", type=int, default=MAX_CHUNK_SIZE, help=f"1회 읽기 크기 (기본: {MAX_CHUNK_SIZE})")
    parser.add_argument("--debug", action="store_true", help="디버그 모드 (TX/RX hex dump)")
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

    driver = XGTProtocolDriver(transport)

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
    except XGTNAKError as e:
        print(f"[FAIL] PLC NAK 에러:\n{e}")
        driver.disconnect()
        return
    except XGTBCCError as e:
        print(f"[FAIL] BCC 에러:\n{e}")
        driver.disconnect()
        return
    except Exception as e:
        print(f"[FAIL] 통신 에러: {type(e).__name__}: {e}")
        driver.disconnect()
        return

    mode = "비트" if args.bit else "워드"
    print(f"[SCAN] {args.device}{args.start} ~ {args.device}{args.end} ({mode} 모드)")
    print(f"[INFO] 스캔 중...\n")

    try:
        scan_start = time.perf_counter()

        if args.bit:
            results, errors = scan_bits(driver, args.device, args.start, args.end, args.chunk)
            print_bit_results(args.device, results, args.nonzero)
        else:
            results, errors = scan_words(driver, args.device, args.start, args.end, args.chunk)
            print_word_results(args.device, results, args.nonzero)

        elapsed = (time.perf_counter() - scan_start) * 1000
        print_summary(args.device, args.start, args.end, results, errors, args.bit, elapsed)

    except KeyboardInterrupt:
        print("\n\n[INFO] 스캔 중단됨 (Ctrl+C)")
    except Exception as e:
        print(f"[FAIL] {type(e).__name__}: {e}")
    finally:
        driver.disconnect()
        print("[INFO] 연결 종료")


if __name__ == "__main__":
    main()
