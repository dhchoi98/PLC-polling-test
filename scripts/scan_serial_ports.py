"""사용 가능한 시리얼 포트 스캔

PLC 연결 전 먼저 실행하여 USB-RS232C 컨버터가 어느 COM 포트로 잡혔는지 확인한다.
이 스크립트는 PLC에 아무것도 보내지 않는다 — OS에서 포트 목록만 조회.
"""

import sys
import platform

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[FAIL] pyserial이 설치되지 않았습니다")
    print("  → pip install pyserial")
    sys.exit(1)


def main():
    print(f"[INFO] OS: {platform.system()} {platform.release()}")
    print(f"[INFO] Python: {sys.version.split()[0]}")
    print(f"[INFO] pyserial: {serial.__version__}")
    print()

    ports = serial.tools.list_ports.comports()

    if not ports:
        print("[WARN] 사용 가능한 시리얼 포트가 없습니다!")
        print()
        print("  확인 사항:")
        print("  1) USB-RS232C 컨버터가 PC에 물리적으로 연결되어 있는가?")
        print("  2) 컨버터 드라이버가 설치되어 있는가?")
        print("     → Windows: 장치관리자 → 포트(COM & LPT) 확인")
        print("     → 드라이버 없으면 컨버터 제조사 사이트에서 다운로드")
        print("  3) USB 허브를 쓰고 있다면 직접 PC USB 포트에 꽂아보기")
        print("  4) 케이블이 불량이 아닌지 다른 케이블로 시도")
        return

    print(f"[OK] 발견된 시리얼 포트: {len(ports)}개\n")

    for i, port in enumerate(ports, 1):
        print(f"  [{i}] 포트: {port.device}")
        print(f"      설명: {port.description}")
        print(f"      HWID: {port.hwid}")

        # USB 장치인지 판별
        if port.vid is not None:
            print(f"      USB VID:PID: {port.vid:04X}:{port.pid:04X}")
            if port.manufacturer:
                print(f"      제조사: {port.manufacturer}")
            if port.serial_number:
                print(f"      시리얼번호: {port.serial_number}")
            print(f"      → USB-시리얼 컨버터 감지됨")
        elif "bluetooth" in (port.description or "").lower():
            print(f"      → Bluetooth 포트 (PLC 연결 불가)")
        else:
            print(f"      → 내장 시리얼 포트 또는 기타")

        # 포트 열기 테스트
        try:
            s = serial.Serial(port.device, baudrate=9600, timeout=0.1)
            s.close()
            print(f"      → 포트 열기: 성공 (사용 가능)")
        except serial.SerialException as e:
            err_str = str(e).lower()
            if "access" in err_str or "denied" in err_str or "busy" in err_str:
                print(f"      → 포트 열기: 실패 (다른 프로그램이 사용 중)")
                print(f"         HMI, XG5000, 또는 다른 터미널이 점유 중일 수 있음")
            else:
                print(f"      → 포트 열기: 실패 ({e})")

        print()

    # config.yaml 안내
    print("  ─────────────────────────────────────")
    print(f"  config.yaml의 serial.port를 위 포트 중 하나로 설정하세요.")
    print(f"  예: port: \"{ports[0].device}\"")

    # USB 컨버터가 있는지 판별
    usb_ports = [p for p in ports if p.vid is not None]
    if usb_ports:
        print(f"\n  USB-시리얼 컨버터 추천: {usb_ports[0].device}")
    else:
        print(f"\n  [WARN] USB-시리얼 컨버터가 감지되지 않았습니다.")
        print(f"         내장 포트를 사용하거나, 컨버터 연결을 확인하세요.")


if __name__ == "__main__":
    main()
