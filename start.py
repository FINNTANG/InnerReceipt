"""
INNER Corp — 一键启动脚本
自动开启 HTTPS 隧道，iPhone 可直接访问
"""
import threading, time, os, sys

NGROK_TOKEN = "3CKKnexyMKTJLDNy3t6LzOncNny_55eswQpW9TPLPuyyvcP2d"
PORT        = 8000

# 切换到脚本所在目录，确保 server.py 能被正确导入
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

# ── 配置 ngrok ────────────────────────────────────────────────
from pyngrok import ngrok, conf
conf.get_default().auth_token = NGROK_TOKEN
ngrok.kill()   # 确保清理掉任何残留的旧隧道
time.sleep(1)

# ── 在子线程里启动 FastAPI ────────────────────────────────────
def run_server():
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, log_level="warning")

t = threading.Thread(target=run_server, daemon=True)
t.start()
time.sleep(2)   # 等服务器起来

# ── 开启 ngrok HTTPS 隧道 ─────────────────────────────────────
tunnel     = ngrok.connect(PORT, "http")
https_url  = tunnel.public_url

print("\n" + "="*54)
print("  INNER CORP — Emotional Intelligence Division")
print("="*54)
print(f"\n  [OK] 服务器已启动")
print(f"  [OK] HTTPS 隧道已创建\n")
print(f"  电脑浏览器:  http://127.0.0.1:{PORT}")
print(f"\n  +--------------------------------------------+")
print(f"  |  iPhone 输入或扫描以下地址:                |")
print(f"  |                                            |")
print(f"  |  {https_url:<42}  |")
print(f"  |                                            |")
print(f"  +--------------------------------------------+")
print(f"\n  麦克风: HTTPS [OK] — iOS Safari 可正常使用")
print(f"\n  按 Ctrl+C 关闭服务器")
print("="*54 + "\n")

# ── 打印二维码 ────────────────────────────────────────────────
try:
    import qrcode
    qr = qrcode.QRCode(border=1)
    qr.add_data(https_url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    print("  ^ 用手机相机扫描上方二维码直接打开\n")
except Exception:
    pass

# ── 保持运行 ─────────────────────────────────────────────────
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n  [关闭中...]")
    ngrok.kill()
