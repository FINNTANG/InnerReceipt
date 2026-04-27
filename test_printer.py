"""
M58-LL 蓝牙热敏打印机测试脚本
蓝牙地址: 5A:4A:E6:1C:FF:C2
"""

import sys
import socket
import struct
import time

PRINTER_BT_ADDR = "5A:4A:E6:1C:FF:C2"
PRINTER_BT_PORT = 1  # RFCOMM 标准串口服务端口

# ── 1. 列出所有串口 ──────────────────────────────────────────────
def list_serial_ports():
    print("\n[串口扫描]")
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        if ports:
            for p in ports:
                print(f"  {p.device:10s}  {p.description}")
        else:
            print("  未发现任何串口设备")
        return [p.device for p in ports]
    except Exception as e:
        print(f"  串口扫描失败: {e}")
        return []

# ── 2. 尝试用 Windows Bluetooth API 枚举已配对设备 ───────────────
def list_paired_bt_devices():
    print("\n[已配对蓝牙设备]")
    try:
        import win32com.client
        wmi = win32com.client.GetObject("winmgmts:")
        devices = wmi.InstancesOf("Win32_PnPEntity")
        bt_devices = [d.Name for d in devices if d.Name and "bluetooth" in d.Name.lower()]
        if bt_devices:
            for name in bt_devices:
                print(f"  {name}")
        else:
            print("  未发现蓝牙设备（或未配对）")
    except Exception as e:
        print(f"  无法枚举蓝牙设备: {e}")

# ── 3. 通过 RFCOMM Socket 直连打印机 ─────────────────────────────
def connect_and_print_socket():
    print(f"\n[Socket 直连] 目标: {PRINTER_BT_ADDR}  端口: {PRINTER_BT_PORT}")
    try:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        sock.settimeout(8)
        sock.connect((PRINTER_BT_ADDR, PRINTER_BT_PORT))
        print("  连接成功！正在发送打印指令...")

        # ESC/POS 指令序列
        ESC_INIT   = b'\x1b\x40'          # 初始化打印机
        ALIGN_CTR  = b'\x1b\x61\x01'      # 居中对齐
        ALIGN_L    = b'\x1b\x61\x00'      # 左对齐
        BOLD_ON    = b'\x1b\x45\x01'      # 加粗开
        BOLD_OFF   = b'\x1b\x45\x00'      # 加粗关
        FEED_CUT   = b'\x1b\x64\x05'      # 走纸5行
        CN_ON      = b'\x1c\x26'          # 开启中文双字节模式 (FS &)
        CN_OFF     = b'\x1c\x2e'          # 关闭中文模式，回到ASCII (FS .)
        NEWLINE    = b'\n'

        payload = (
            ESC_INIT
            + ALIGN_CTR
            + BOLD_ON
            + "Hello World!\n".encode("ascii")
            + BOLD_OFF
            + CN_ON                                      # 切换到中文模式
            + "蓝牙打印测试成功\n".encode("gbk")
            + CN_OFF                                     # 切回 ASCII 模式
            + "InnerReceipt App\n".encode("ascii")
            + NEWLINE
            + FEED_CUT
        )

        sock.send(payload)
        time.sleep(1)
        sock.close()
        print("  指令发送完毕，请查看打印机出纸。")
        return True

    except OSError as e:
        print(f"  Socket 连接失败: {e}")
        print("  提示: 请确认打印机已开机，且在 Windows 蓝牙设置中已配对。")
        return False

# ── 4. 通过串口 COM 口连接（备选方案） ──────────────────────────
def connect_via_comport(com_port: str):
    print(f"\n[串口连接] 端口: {com_port}")
    try:
        import serial
        with serial.Serial(com_port, baudrate=9600, timeout=3) as ser:
            print(f"  串口 {com_port} 打开成功，发送打印指令...")

            ESC_INIT  = b'\x1b\x40'
            ALIGN_CTR = b'\x1b\x61\x01'
            FEED_CUT  = b'\x1b\x64\x05'

            payload = (
                ESC_INIT
                + ALIGN_CTR
                + "Hello World! (COM)\n".encode("gbk")
                + "串口测试成功\n".encode("gbk")
                + b'\n'
                + FEED_CUT
            )
            ser.write(payload)
            time.sleep(1)
        print("  串口指令发送完毕。")
        return True
    except Exception as e:
        print(f"  串口连接失败: {e}")
        return False

# ── 5. 用 python-escpos 的 Bluetooth 类连接（需要 PyBluez） ─────
def connect_via_escpos_bluetooth():
    print("\n[python-escpos Bluetooth 类]")
    try:
        from escpos.printer import Bluetooth
        p = Bluetooth(PRINTER_BT_ADDR, port=PRINTER_BT_PORT)
        p.text("Hello World!\n")
        p.text("python-escpos 测试成功\n")
        p.cut()
        print("  python-escpos 打印成功！")
        return True
    except ImportError as e:
        print(f"  缺少依赖（通常需要 PyBluez）: {e}")
        return False
    except Exception as e:
        print(f"  python-escpos 连接失败: {e}")
        return False


# ── 主流程 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  M58-LL 蓝牙打印机连接测试")
    print(f"  目标蓝牙地址: {PRINTER_BT_ADDR}")
    print("=" * 50)

    # 扫描环境
    ports = list_serial_ports()
    list_paired_bt_devices()

    # 优先尝试 RFCOMM Socket 直连
    success = connect_and_print_socket()

    # Socket 失败时，尝试 python-escpos 内置 Bluetooth 类
    if not success:
        success = connect_via_escpos_bluetooth()

    # 如果发现 COM 口，也尝试串口
    if not success and ports:
        print("\n检测到以下串口，逐一尝试...")
        for port in ports:
            if connect_via_comport(port):
                break

    print("\n" + "=" * 50)
    print("测试结束。" if success else "所有方式均失败，请参考下方说明。")
    if not success:
        print("""
排查步骤:
  1. 确认打印机已开机（电源指示灯亮）
  2. 在 Windows 设置 > 蓝牙 中配对 "BlueTooth Printer"
     配对密码通常为 0000 或 1234
  3. 配对后在 设备管理器 > 端口(COM) 查看分配的 COM 口
  4. 修改脚本中 connect_via_comport 的端口号后重新运行
""")
    print("=" * 50)
