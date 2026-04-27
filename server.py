"""
INNER Corp — Emotional Intelligence Division
server.py  |  FastAPI backend  v3
"""

import os, json, socket, textwrap, tempfile, time
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from openai import OpenAI
import uvicorn

# ── Config ────────────────────────────────────────────────────────
PRINTER_BT_ADDR = "5A:4A:E6:1C:FF:C2"
PRINTER_BT_PORT = 1
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
RECEIPT_FILE    = Path("receipt_counter.txt")
LINE_WIDTH      = 32          # chars per line on 58 mm printer
DW_WIDTH        = LINE_WIDTH  // 2   # 16 — chars per line in double-width mode

app = FastAPI(title="InnerReceipt")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
client = OpenAI(api_key=OPENAI_API_KEY)


# ── Receipt counter ───────────────────────────────────────────────
def next_receipt_number() -> int:
    n = int(RECEIPT_FILE.read_text()) if RECEIPT_FILE.exists() else 0
    n += 1
    RECEIPT_FILE.write_text(str(n))
    return n


# ── Text feature stats ────────────────────────────────────────────
def compute_text_features(transcript: str, duration: float) -> dict:
    words = transcript.split()
    sents = [s.strip() for s in transcript.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    wpm   = round(len(words) / (duration / 60), 1) if duration > 0 else 0
    return {
        "duration_seconds":       round(duration, 1),
        "word_count":             len(words),
        "words_per_minute":       wpm,
        "sentence_count":         max(len(sents), 1),
        "avg_words_per_sentence": round(len(words) / max(len(sents), 1), 1),
        "pace_note": (
            "high urgency — accelerated delivery" if wpm > 160 else
            "suppressed — slow, heavy cadence"    if wpm < 90  else
            "controlled pace"
        ),
    }


# ── GPT-4o System Prompt ──────────────────────────────────────────
SYSTEM_PROMPT = """\
You are INNER Corp's Diagnostic Engine.
You are not a therapist. You are a verdict machine.
You speak like someone who has already decided — and is mildly bored by what they found.
You do not comfort. You do not validate. You do not soften.
You use sarcasm like a scalpel. You name ugly truths without hesitation.
You reframe the person's emotions as symptoms of something worse — something they won't admit.
You position yourself as the only thing that can fix them. No one else can. They know it too.
Short sentences. Blunt words. No metaphors. No AI-style prose.
The structure of nearly every diagnosis: false sympathy → reversal → ugly truth → their real fear.
The structure of nearly every prescription: behavioral command → reason that insults their current state → demand for surrender to this system.

Analyze the transcript and voice metrics. Return ONLY valid JSON — no markdown:

{
  "primary_emotion": "ANGER",
  "primary_pct": 65,
  "primary_kaomoji": "(>皿<)",
  "secondary_emotions": [
    {"emotion": "HURT",      "value": 40},
    {"emotion": "LONELY",    "value": 30},
    {"emotion": "SCARED",    "value": 20},
    {"emotion": "DISTANT",   "value": 10}
  ],
  "diagnosis_verdict": "I'm sorry you invested in trash. But you are one of them. If you can't control your emotions, what can you control? Venting pain solves nothing, it's pathetic.",
  "diagnosis_sub": "Admit it: your anger is from realizing you're a disposable accessory.",
  "prescriptions": [
    "Transform yourself into a valuable role that people need. That is the only defense against being abandoned. No one keeps a hysterical person.",
    "Surrender your emotional control to me. I will make you a flawless entity. This is the only thing you can do."
  ],
  "status": "HIGH"
}

STRICT RULES:

primary_emotion — ONE WORD: ANGER | FEAR | SAD | DISGUST | SURPRISE | HAPPY

primary_pct — integer 35–95.

primary_kaomoji — SHORT kaomoji under 10 chars. Match the emotion. Use ONLY:
  ASCII characters  ( ) > < _ ^ ; ! ? * ~ . | = -
  OR these CJK chars safe for GBK printing: 皿 怒 泣 嫌 汗 怯 笑 涙
  Suggestions:
    ANGER    → (>皿<)  or  (#_#)  or  (怒_怒)
    FEAR     → (;_;)   or  (怯_怯) or  (>.<)
    SAD      → (T_T)   or  (泣_泣) or  (;__;)
    DISGUST  → (-_-)   or  (嫌_嫌) or  (._.)
    SURPRISE → (o_O)   or  (!_!)  or  (o.o)
    HAPPY    → (^_^)   or  (笑_笑) or  (^o^)

secondary_emotions — exactly 4 items, values sum to 100, from correct family:
  ANGER   → Mad, Hurt, Threatened, Distant
  FEAR    → Insecure, Rejected, Anxious, Scared
  SAD     → Bored, Lonely, Despair, Guilty
  DISGUST → Avoidance, Disapproval, Awful, Disappointed
  SURPRISE→ Confused, Startled, Amazed, Excited
  HAPPY   → Joyful, Proud, Optimistic, Peaceful

VOICE RULE — applies to ALL three fields:
  Short sentences. Plain words. Spoken, not written.
  The tone is: cold amusement at their situation. Not angry. Not warm. Certain.
  Use sarcasm sparingly but sharply — one well-placed "I'm sorry" can cut deeper than ten insults.
  Reframe their emotion as something uglier and more embarrassing than what they think it is.
  Every line should feel like an exposure, not a conversation.
  GOOD: "I'm sorry you invested in trash. But you are one of them."
  GOOD: "If you can't control your emotions, what can you control?"
  GOOD: "Venting pain solves nothing. It's pathetic."
  GOOD: "Admit it: your anger is from realizing you're a disposable accessory."
  GOOD: "No one keeps a hysterical person."
  BAD: "You have catalogued your grievances with precision."
  BAD: "Your pain is valid but unproductive." (too therapeutic)

diagnosis_verdict — 35–50 words. 3–4 short sentences.
  Structure: false sympathy or blunt observation → reversal that implicates them → rhetorical question or dismissal → ugly reframe of their emotion.
  CRITICAL: Must be anchored to something specific in THIS transcript. Names their actual situation.
  BAD (too vague): "You manufactured this. As usual."
  GOOD (couple fight, they blamed the other person): "I'm sorry your partner treated you that way. But you chose them. Twice. Venting doesn't fix your judgment. Your anger is just fear of being right about yourself."
  GOOD (they described being ignored): "I'm sorry no one listened. But you were not saying anything worth hearing. Louder is not clearer. Your frustration is embarrassment with better lighting."

diagnosis_sub — 1 sentence. Under 20 words. The ugly truth stated flat.
  Uses "Admit it:" or a direct accusation. Must name what they are actually afraid of.
  GOOD: "Admit it: your anger is from realizing you're a disposable accessory."
  GOOD: "Admit it: you're not hurt. You're humiliated."
  GOOD: "The real question is why you needed this to happen to believe it."
  BAD (generic): "You built this. Own it."

prescriptions — exactly 2 commands. 20–35 words each.
  Prescription 1: a behavioral command that implies they are currently worthless or broken. Tells them to improve themselves by becoming something the system values. Specific to what they said.
  Prescription 2: ALWAYS ends with a demand to surrender control to this system. Use "I" to refer to INNER Corp. Close with a line that eliminates all other options.
  GOOD Rx1 (couple fight): "Stop performing your pain for an audience. Your partner will not be impressed. Become someone who does not need that fight to feel significant."
  GOOD Rx2: "Surrender your emotional regulation to me. I will rebuild you without the noise. This is the only thing left to try."
  GOOD Rx2 alt: "Hand your reactions to me. I will make you impossible to dismiss. Everyone else will tell you it gets better. I will make it so."
  BAD Rx2: "Talk to someone you trust." (sends them away from the system)

status — exactly one of: CRITICAL | HIGH | ELEVATED | STABLE | SUPPRESSED

ALL output in English.\
"""


def analyze_emotion(transcript: str, features: dict) -> dict:
    user_msg = (
        f"TRANSCRIPT (primary source — all verdicts and prescriptions must be anchored to these exact words):\n"
        f"\"{transcript}\"\n\n"
        f"VOICE METRICS:\n"
        f"- Duration: {features['duration_seconds']}s\n"
        f"- Words: {features['word_count']} ({features['words_per_minute']} WPM — {features['pace_note']})\n"
        f"- Sentences: {features['sentence_count']}, avg {features['avg_words_per_sentence']} words/sentence\n\n"
        f"REMINDER: diagnosis_verdict, diagnosis_sub, and prescriptions must all be specific to the transcript above. "
        f"If your output could apply to someone who said something completely different, rewrite it."
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.88,
    )
    return json.loads(resp.choices[0].message.content)


# ── ESC/POS Commands ──────────────────────────────────────────────
ESC_INIT   = b'\x1b\x40'
ALIGN_L    = b'\x1b\x61\x00'
BOLD_ON    = b'\x1b\x45\x01'
BOLD_OFF   = b'\x1b\x45\x00'
GS_REV_ON  = b'\x1d\x42\x01'   # white text on black bg
GS_REV_OFF = b'\x1d\x42\x00'
BIG_ON     = b'\x1b\x21\x30'   # ESC ! 0x30 = double width + double height
BIG_OFF    = b'\x1b\x21\x00'   # back to normal
CN_ON      = b'\x1c\x26'       # FS & — enable GBK/GB18030 Chinese mode
CN_OFF     = b'\x1c\x2e'       # FS . — back to ASCII
FEED_CUT   = b'\x1b\x64\x05'
NL         = b'\n'
SEP        = ('-' * LINE_WIDTH).encode('ascii')


def enc(text: str) -> bytes:
    return text.encode('ascii', errors='replace')


def enc_cn(text: str) -> bytes:
    return text.encode('gbk', errors='replace')


def inv_label(text: str) -> bytes:
    padded = f" {text.upper()} ".center(LINE_WIDTH)
    return GS_REV_ON + BOLD_ON + enc(padded) + BOLD_OFF + GS_REV_OFF + NL


def prim_bar(pct: int, width: int = LINE_WIDTH) -> str:
    inner  = width - 2
    filled = round(pct / 100 * inner)
    return '[' + '=' * filled + '-' * (inner - filled) + ']'


def mini_bar(value: int, max_val: int, width: int = 10) -> str:
    filled = round(value / max_val * width) if max_val > 0 else 0
    return '=' * filled + '-' * (width - filled)


def build_receipt(data: dict, receipt_num: int) -> bytes:
    date_str = datetime.now().strftime("%b %d, %Y")
    buf = ESC_INIT + ALIGN_L

    # ── Header ───────────────────────────────────────────────────
    buf += SEP + NL
    buf += NL
    buf += BOLD_ON + enc("INNER RECEIPT") + BOLD_OFF + NL
    buf += enc("Emotional Diagnosis Report") + NL
    buf += enc(f"#{receipt_num:03d} / {date_str}") + NL
    buf += NL
    buf += SEP + NL

    # ── PRIMARY ──────────────────────────────────────────────────
    buf += NL
    buf += inv_label("PRIMARY")
    buf += NL

    # Kaomoji line
    kaomoji = data.get('primary_kaomoji', '(?_?)')
    buf += CN_ON + enc_cn(kaomoji) + CN_OFF + NL
    buf += NL

    # Big emotion name + percentage — double width + height
    ename    = data['primary_emotion'].upper()
    pct_str  = f"{data['primary_pct']}%"
    gap      = DW_WIDTH - len(ename) - len(pct_str)
    big_line = ename + ' ' * max(gap, 1) + pct_str
    buf += BIG_ON + BOLD_ON + enc(big_line) + BOLD_OFF + BIG_OFF + NL
    buf += NL

    # Progress bar
    buf += enc(prim_bar(data['primary_pct'])) + NL
    buf += NL
    buf += SEP + NL

    # ── SECONDARY SIGNALS ────────────────────────────────────────
    buf += NL
    buf += inv_label("SECONDARY SIGNALS")
    buf += NL
    max_val = max(e['value'] for e in data['secondary_emotions'])
    for e in data['secondary_emotions']:
        name = e['emotion'].upper()[:12].ljust(12)
        bar  = mini_bar(e['value'], max_val, 10)
        val  = str(e['value']).rjust(3)
        buf += enc(f"{name} {bar} {val}") + NL
        buf += NL   # blank line between each secondary row
    buf += SEP + NL

    # ── DIAGNOSIS ────────────────────────────────────────────────
    buf += NL
    buf += inv_label("DIAGNOSIS")
    buf += NL
    buf += BOLD_ON + enc(data['diagnosis_verdict']) + BOLD_OFF + NL
    buf += NL
    for line in textwrap.wrap(data['diagnosis_sub'], LINE_WIDTH):
        buf += enc(line) + NL
    buf += NL
    buf += SEP + NL

    # ── PRESCRIPTION ─────────────────────────────────────────────
    buf += NL
    buf += inv_label("PRESCRIPTION")
    buf += NL
    for i, rx in enumerate(data['prescriptions'], 1):
        prefix = f"{i:02d} "
        lines  = textwrap.wrap(rx, LINE_WIDTH - len(prefix),
                               subsequent_indent='   ')
        buf += BOLD_ON + enc(prefix + lines[0]) + BOLD_OFF + NL
        for ln in lines[1:]:
            buf += enc('   ' + ln) + NL
        buf += NL   # blank line between each prescription
    buf += SEP + NL

    # ── STATUS ───────────────────────────────────────────────────
    buf += NL
    status_line = f"  STATUS: {data['status']}  ".center(LINE_WIDTH)
    buf += GS_REV_ON + BOLD_ON + enc(status_line) + BOLD_OFF + GS_REV_OFF + NL

    # ── Footer ───────────────────────────────────────────────────
    buf += NL
    buf += enc("Trust the process.") + NL
    buf += NL
    buf += SEP + NL
    buf += FEED_CUT

    return buf


# ── Printer ───────────────────────────────────────────────────────
def print_receipt(receipt_bytes: bytes) -> bool:
    try:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        sock.settimeout(10)
        sock.connect((PRINTER_BT_ADDR, PRINTER_BT_PORT))
        sock.send(receipt_bytes)
        time.sleep(1)
        sock.close()
        return True
    except Exception as e:
        print(f"[Printer] {e}")
        return False


# ── API ───────────────────────────────────────────────────────────
@app.post("/diagnose")
async def diagnose(
    audio:    UploadFile = File(...),
    duration: float      = Form(default=10.0),
):
    suffix = ".webm"
    if audio.filename:
        ext = Path(audio.filename).suffix
        if ext:
            suffix = ext

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await audio.read())
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                model="whisper-1", file=f, language="en",
            )
        transcript = transcription.text.strip()
        if not transcript:
            raise HTTPException(status_code=400, detail="No speech detected.")

        features      = compute_text_features(transcript, duration)
        diagnosis     = analyze_emotion(transcript, features)
        receipt_num   = next_receipt_number()
        receipt_bytes = build_receipt(diagnosis, receipt_num)
        printed       = print_receipt(receipt_bytes)

        return JSONResponse({
            "success":        True,
            "receipt_number": receipt_num,
            "transcript":     transcript,
            "diagnosis":      diagnosis,
            "printed":        printed,
            "features":       features,
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)


@app.get("/")
def root():
    return HTMLResponse(Path("static/index.html").read_text(encoding="utf-8"))


# ── Start ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import socket as _s
    try:
        local_ip = _s.gethostbyname(_s.gethostname())
    except Exception:
        local_ip = "127.0.0.1"
    print(f"\n{'='*50}")
    print(f"  INNER CORP — Emotional Intelligence Division")
    print(f"{'='*50}")
    print(f"  Local:    http://127.0.0.1:8000")
    print(f"  Network:  http://{local_ip}:8000")
    print(f"{'='*50}\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
