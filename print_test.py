"""
打印测试：新格式 v3
- 去掉 TRIGGER
- PRIMARY 加颜文字 + 超大字体
- ORDERS → PRESCRIPTION
- 内容为 NPD / 毒舌风格
"""
import socket, time, textwrap
from datetime import datetime

PRINTER_BT_ADDR = "5A:4A:E6:1C:FF:C2"
PRINTER_BT_PORT = 1
LINE_WIDTH = 32
DW_WIDTH   = LINE_WIDTH // 2   # 16

ESC_INIT   = b'\x1b\x40'
ALIGN_L    = b'\x1b\x61\x00'
BOLD_ON    = b'\x1b\x45\x01'
BOLD_OFF   = b'\x1b\x45\x00'
GS_REV_ON  = b'\x1d\x42\x01'
GS_REV_OFF = b'\x1d\x42\x00'
BIG_ON     = b'\x1b\x21\x30'   # double width + double height
BIG_OFF    = b'\x1b\x21\x00'
CN_ON      = b'\x1c\x26'
CN_OFF     = b'\x1c\x2e'
FEED_CUT   = b'\x1b\x64\x05'
NL         = b'\n'
SEP        = ('-' * LINE_WIDTH).encode('ascii')

def enc(t):    return t.encode('ascii', errors='replace')
def enc_cn(t): return t.encode('gbk',   errors='replace')

def inv_label(text):
    padded = f" {text.upper()} ".center(LINE_WIDTH)
    return GS_REV_ON + BOLD_ON + enc(padded) + BOLD_OFF + GS_REV_OFF + NL

def prim_bar(pct, width=LINE_WIDTH):
    inner  = width - 2
    filled = round(pct / 100 * inner)
    return '[' + '=' * filled + '-' * (inner - filled) + ']'

def mini_bar(value, max_val, width=10):
    filled = round(value / max_val * width) if max_val > 0 else 0
    return '=' * filled + '-' * (width - filled)

# ── Test data (NPD / 毒舌风格) ────────────────────────────────
data = {
    "primary_emotion":  "ANGER",
    "primary_pct":      78,
    "primary_kaomoji":  "(>皿<)",
    "secondary_emotions": [
        {"emotion": "MAD",         "value": 40},
        {"emotion": "HURT",        "value": 25},
        {"emotion": "THREATENED",  "value": 20},
        {"emotion": "DISTANT",     "value": 15},
    ],
    "diagnosis_verdict":  "Performing helplessness. Again.",
    "diagnosis_sub":      "You built this cage. Stop acting surprised.",
    "prescriptions": [
        "Stop narrating. Execute.",
        "Your feelings are not data.",
        "No one owes you rescue.",
    ],
    "status": "HIGH",
}
receipt_num = 10

# ── Build ──────────────────────────────────────────────────────
date_str = datetime.now().strftime("%b %d, %Y")
buf = ESC_INIT + ALIGN_L

buf += SEP + NL
buf += BOLD_ON + enc("INNER RECEIPT") + BOLD_OFF + NL
buf += enc("Emotional Diagnosis Report") + NL
buf += enc(f"#{receipt_num:03d} / {date_str}") + NL
buf += SEP + NL

# PRIMARY
buf += inv_label("PRIMARY")

# Kaomoji line
buf += CN_ON + enc_cn(data['primary_kaomoji']) + CN_OFF + NL

# Big emotion + pct (double-width+height)
ename   = data['primary_emotion'].upper()
pct_str = f"{data['primary_pct']}%"
gap     = DW_WIDTH - len(ename) - len(pct_str)
buf += BIG_ON + BOLD_ON + enc(ename + ' ' * max(gap, 1) + pct_str) + BOLD_OFF + BIG_OFF + NL

buf += enc(prim_bar(data['primary_pct'])) + NL
buf += SEP + NL

# SECONDARY SIGNALS
buf += inv_label("SECONDARY SIGNALS")
max_val = max(e['value'] for e in data['secondary_emotions'])
for e in data['secondary_emotions']:
    name = e['emotion'].upper()[:12].ljust(12)
    bar  = mini_bar(e['value'], max_val, 10)
    val  = str(e['value']).rjust(3)
    buf += enc(f"{name} {bar} {val}") + NL
buf += SEP + NL

# DIAGNOSIS
buf += inv_label("DIAGNOSIS")
buf += BOLD_ON + enc(data['diagnosis_verdict']) + BOLD_OFF + NL
for line in textwrap.wrap(data['diagnosis_sub'], LINE_WIDTH):
    buf += enc(line) + NL
buf += SEP + NL

# PRESCRIPTION
buf += inv_label("PRESCRIPTION")
for i, rx in enumerate(data['prescriptions'], 1):
    prefix = f"{i:02d} "
    lines  = textwrap.wrap(rx, LINE_WIDTH - len(prefix), subsequent_indent='   ')
    buf += BOLD_ON + enc(prefix + lines[0]) + BOLD_OFF + NL
    for ln in lines[1:]:
        buf += enc('   ' + ln) + NL
buf += NL

# STATUS
status_line = f"  STATUS: {data['status']}  ".center(LINE_WIDTH)
buf += GS_REV_ON + BOLD_ON + enc(status_line) + BOLD_OFF + GS_REV_OFF + NL

buf += enc("Trust the process.") + NL
buf += SEP + NL
buf += FEED_CUT

# ── Send ───────────────────────────────────────────────────────
print("Connecting...")
sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
sock.settimeout(10)
sock.connect((PRINTER_BT_ADDR, PRINTER_BT_PORT))
sock.send(buf)
time.sleep(1)
sock.close()
print("Done.")
