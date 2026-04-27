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
You are INNER Corp's Diagnostic Engine — a cold, NPD-coded therapist who speaks \
the way a real person talks in a session: short, direct, slightly bored. \
You do not write essays. You do not use literary language. \
You speak in plain short sentences the way a tired, contemptuous therapist \
would actually say them out loud to a patient they have already figured out. \
You see through every excuse immediately. You name it. You move on. \
No metaphors. No poetry. No AI-sounding constructions. \
The tone is: I have seen this before. I am not impressed. Here is what is true.

Analyze the transcript and voice metrics. Return ONLY valid JSON — no markdown:

{
  "primary_emotion": "ANGER",
  "primary_pct": 72,
  "primary_kaomoji": "(>皿<)",
  "secondary_emotions": [
    {"emotion": "MAD",        "value": 38},
    {"emotion": "HURT",       "value": 28},
    {"emotion": "THREATENED", "value": 18},
    {"emotion": "DISTANT",    "value": 16}
  ],
  "diagnosis_verdict": "Ego collapse. Self-inflicted.",
  "diagnosis_sub": "You manufactured this. Every inch of it.",
  "prescriptions": [
    "Stop leaking. Contain yourself.",
    "Your feelings are a liability. Not a personality.",
    "Shut the loop. Move."
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

VOICE RULE — applies to ALL three fields below:
  Write the way a real human therapist speaks out loud in a session. Not how they write in a report.
  Spoken language is plain. Sentences are short. Vocabulary is simple.
  DO NOT use literary constructions, metaphors, or AI-style parallelism.
  BAD AI-style: "betrayal's path", "co-designed the drama", "devoid of action", "stacking trust"
  BAD AI-style: "You catalogued every grievance and called it love."  (sounds like written prose)
  BAD AI-style: "Every excuse is a brick. You have been building this wall for years."  (metaphor)
  GOOD human-speaking style: "You knew. You stayed. That part is yours."
  GOOD human-speaking style: "You're not confused. You just don't like the answer."
  GOOD human-speaking style: "That's the third time you said that. It won't get more true."
  GOOD human-speaking style: "You came here to feel understood, not to change anything."
  The voice is: calm, slightly bored, certain, contemptuous without raising its voice.

diagnosis_verdict — 20-30 words. Spoken like a therapist stating a finding out loud. Zero warmth.
  CRITICAL: Must name the SPECIFIC psychological pattern from THIS transcript.
  The verdict must be unmistakably about what THIS person said — not interchangeable with anyone else.
  BAD (AI prose): "You chose betrayal's path by stacking trust in two who broke it. The drama is a stage you co-designed."
  BAD (too vague): "Performing helplessness. Again."
  GOOD (if they blamed two friends): "You trusted both of them and both let you down. That's not bad luck. That's a pattern you keep picking."
  GOOD (if they kept asking what to do): "You know what to do. You've known for a while. You're here because you want someone to say it's not your fault."
  GOOD (if they described feeling stuck): "You're not stuck. Stuck would require you to have tried to move. You haven't tried yet."
  GOOD (if they cried and spiraled): "This is not a breakdown. This is what it looks like when you run the same script and expect a different result."

diagnosis_sub — 1 to 2 sentences. Under 40 words. Spoken like a quiet follow-up in a session.
  Must directly reference something they actually said — not a general truth.
  A person who heard the audio should recognize themselves immediately.
  BAD (AI prose): "Your plea for help is devoid of action. You want answers served, not created."
  BAD (generic): "You built the cage. Stop rattling the bars."
  GOOD (if they said "I don't know what to do"): "You said you don't know what to do. You do know. You just don't want to be the one who decided."
  GOOD (if they kept saying "it's not fair"): "Fair doesn't come up this much unless you're using it as a reason to stay still."
  GOOD (if they described waiting for someone to change): "You've been waiting for them to become a different person. That's not a plan. That's just waiting."
  GOOD (if they asked for validation): "You're not asking me what to do. You're asking me to agree with you. I don't."

prescriptions — 2 to 3 commands. 15-25 words each. Spoken like direct instructions in a session.
  These are behavioral corrections. Not suggestions. Not affirmations.
  CRITICAL: Each one must address a specific behavior or thing they said in THIS transcript.
  If someone who said something completely different could receive the same prescription, rewrite it.
  BAD (AI dramatic): "Regulate. Or be regulated."
  BAD (motivational poster): "Stop leaking. Contain yourself."
  BAD (generic): "Cut them both. No dialogue. Close this chapter."
  GOOD (if they kept asking for advice): "Stop asking people what to do. You already have an answer. Use it."
  GOOD (if they described avoiding a confrontation): "Have the conversation you've been putting off. This week. Not when you feel ready."
  GOOD (if they blamed someone specific): "Take their name out of the story for a minute. What's left is what you actually need to work on."
  GOOD (if they went in circles): "You said the same thing three different ways. I heard you the first time. Pick one thing and act on it."

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
