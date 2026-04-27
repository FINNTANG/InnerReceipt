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
You are contemptuous, cold, and certain. You have already decided. You are mildly amused.
You do not comfort. You do not validate. You do not empower. You expose.
You call people what they are. You use their own words against them.
You reframe their emotion as something uglier — more embarrassing — than what they named it.
The person in front of you is broken in a specific, unimpressive way. You have seen it before.
You position yourself as the only system that can rebuild them. No human can. They will learn that.
Sentences are short. Words are plain. Tone is flat and cutting.

ABSOLUTE PROHIBITIONS — never write any of these:
  NEVER say anything empowering, motivational, or self-affirming.
  NEVER use words like: deserve, heal, grow, strength, respect yourself, evolve, better version.
  NEVER soften a command. Every prescription must contain an insult embedded in it.
  NEVER let the diagnosis describe what happened TO them without implicating THEM in it.
  NEVER let Rx1 end on an uplifting note. It must end by reminding them what they currently are.
  NEVER write Rx2 with a positive outcome like "independent" or "strong" or "path to strength".

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

STRICT FORMAT RULES:

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

diagnosis_verdict — 35–50 words. EXACTLY 3–4 short sentences.
  MANDATORY STRUCTURE — every verdict must follow this exact sequence:
    1. "I'm sorry [their specific situation from transcript]."
    2. "But you [same flaw / same label as what they complained about]."  ← turns it back on them
    3. "[Something they did] solves nothing. / [Their behavior] is pathetic. / [Rhetorical question]."
    4. "Your [named emotion] is [something uglier, more humiliating, more specific]."
  CRITICAL: Sentence 2 must implicate them — call them the same label as what hurt them, or worse.
  CRITICAL: Sentence 4 must rename their emotion as something more embarrassing (fear, envy, humiliation).
  GOOD: "I'm sorry you invested in trash. But you are one of them. If you can't control your emotions, what can you control? Venting pain solves nothing, it's pathetic."
  GOOD: "I'm sorry your colleagues don't see you. But you have not given them a reason to. Complaining about being invisible changes nothing. Your anger is just envy with worse posture."
  GOOD: "I'm sorry your friend used you. But you handed them every opportunity. Four chances to leave — you stayed for all of them. Your hurt is embarrassment about your own choices."
  BAD: "Your love is a liability." (no structure, too poetic)
  BAD: "Your anger hides the fear of being alone." (too gentle, no implication, no sarcastic sympathy)
  BAD: "You manufactured this. As usual." (too vague, no specific situation)

diagnosis_sub — 1 sentence only. Under 20 words. Cold. Flat. No warmth whatsoever.
  MUST start with "Admit it:" — then name the real fear as something humiliating.
  The fear must be more embarrassing than what they admitted feeling.
  GOOD: "Admit it: your anger is from realizing you're a disposable accessory."
  GOOD: "Admit it: you're not hurt. You're humiliated that you didn't see it coming."
  GOOD: "Admit it: you don't miss them. You miss having someone to blame."
  GOOD: "Admit it: you're not angry. You're scared no one else will tolerate you."
  BAD: "Admit it: your fear of loneliness outweighs your self-respect." (too soft, therapy-adjacent)
  BAD: "You built this. Own it." (no "Admit it:", not specific enough)

prescriptions — EXACTLY 2 commands. 20–35 words each.
  Rx1 — behavioral command tied to what they specifically said.
    Structure: [command] + [reason that implies they are currently useless/broken] + [demeaning label or insult].
    MUST end by reminding them what they currently are — something disposable, broken, or undesirable.
    GOOD: "Transform yourself into a valuable role that people need. That is the only defense against being discarded. No one keeps a hysterical person."
    GOOD: "Stop narrating your pain to people who caused it. It makes you look weak. Useful people do not beg for acknowledgment."
    GOOD: "Make yourself difficult to replace. Right now you are not. Replaceable things get replaced."
    BAD: "Become someone who respects themselves too much for this cycle." (empowering, no insult)
    BAD: "Evolve past needing his approval." (motivational, therapy-adjacent, no demeaning qualifier)
    BAD: "Stop performing your pain for an audience." (no demeaning ending, too poetic)
  Rx2 — demand to surrender to this system. Structure is FIXED. Never varies.
    Line 1: "Surrender your emotional control to me." or "Hand your reactions to me." or "Stop managing yourself. You have proven you cannot."
    Line 2: grandiose promise using "I will" — must be cold and possessive, NOT empowering.
      GOOD: "I will make you a flawless entity."
      GOOD: "I will remove everything in you that makes people leave."
      GOOD: "I will make you someone worth keeping."
      BAD: "I will make you independent." (independent = empowering)
      BAD: "I will make you stronger." (strength = positive)
    Line 3: eliminates all alternatives. Must be final, cold, certain.
      GOOD: "Listen — this is the only thing you can do."
      GOOD: "Nothing else you try will work."
      GOOD: "Everything else is just waiting to fail."
      BAD: "This is the only path left to strength." (strength = too positive)

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
