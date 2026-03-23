# ==============================================
# 🚀 BREAKOUT BASE SYSTEM (FINAL PRO VERSION)
# ==============================================

import os
import re
import time
import pandas as pd
import yfinance as yf
import mplfinance as mpf
from datetime import datetime, time as dtime
import pytz
import requests

from reportlab.platypus import SimpleDocTemplate, Image, Spacer, Paragraph
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet

from openai import OpenAI

# ==========================
# CONFIG
# ==========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# ==========================
# GPT PROMPT (STRICT)
# ==========================
GPT_PROMPT = """
You are a professional breakout-base trading system.

Follow STRICTLY:

STEP 1 — WEEKLY Trend & Stage
STEP 2 — BASE SCORE (0–10)
STEP 3 — VOLUME
STEP 4 — SETUP
STEP 5 — PATTERN (MANDATORY)

If no pattern → DO NOT BUY

Final Score (max 14)

Decision:
≥11 BUY
8–10 WATCH
≤7 AVOID

OUTPUT SECTIONS:

📊 Summary Table
🎯 Execution Table
✅ Final Picks
⚠️ Notes

Max 2–3 stocks.
"""

# ==========================
# FETCH
# ==========================
def fetch_data(stock, period):
    for _ in range(3):
        try:
            df = yf.Ticker(stock).history(period=period, auto_adjust=True)
            if not df.empty:
                return df
        except:
            pass
        time.sleep(0.5)
    return pd.DataFrame()

# ==========================
# CLEAN
# ==========================
def clean(df):
    if df.empty:
        return df

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    cols = ['Open','High','Low','Close','Volume']
    if not all(c in df.columns for c in cols):
        return pd.DataFrame()

    df = df[cols].copy()

    for c in cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    return df.dropna()

# ==========================
# REMOVE LIVE CANDLE
# ==========================
def remove_live(df):
    india = pytz.timezone("Asia/Kolkata")
    now = datetime.now(india)

    if df.index[-1].date() == now.date() and now.time() < dtime(15, 30):
        return df.iloc[:-1]

    return df

# ==========================
# WEEKLY
# ==========================
def weekly(df):
    return df.resample('W').agg({
        'Open':'first',
        'High':'max',
        'Low':'min',
        'Close':'last',
        'Volume':'sum'
    }).dropna()

# ==========================
# CHART (EMA + COLORS)
# ==========================
def plot_chart(df, path):

    df['EMA10'] = df['Close'].ewm(span=10).mean()
    df['EMA21'] = df['Close'].ewm(span=21).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()
    df['EMA200'] = df['Close'].ewm(span=200).mean()

    apds = [
        mpf.make_addplot(df['EMA10'], color='red', width=1),
        mpf.make_addplot(df['EMA21'], color='blue', width=1),
        mpf.make_addplot(df['EMA50'], color='purple', width=1.2),
        mpf.make_addplot(df['EMA200'], color='cyan', width=1.2),
    ]

    mc = mpf.make_marketcolors(
        up='green', down='red',
        wick='inherit', edge='inherit',
        volume='inherit'
    )

    style = mpf.make_mpf_style(marketcolors=mc)

    mpf.plot(
        df,
        type='candle',
        volume=True,
        addplot=apds,
        style=style,
        figsize=(10,6),
        savefig=path
    )

# ==========================
# NSE STOCKS
# ==========================
def get_stocks():
    url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        data = requests.get(url, headers=headers).json()
        return [
            d['symbol'] + ".NS"
            for d in data['data']
            if "NIFTY" not in d['symbol']
        ]
    except:
        return []

# ==========================
# TELEGRAM
# ==========================
def send_msg(txt):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": txt}
    )

def send_doc(path):
    with open(path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
            files={"document": f},
            data={"chat_id": CHAT_ID}
        )

# ==========================
# CARD FORMATTER (NEW)
# ==========================
def format_card_style(output):

    lines = output.split("\n")
    stocks = []

    for line in lines:
        if "|" in line and "Stock" not in line and "---" not in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]

            if len(parts) >= 8:
                stocks.append({
                    "stock": parts[0],
                    "stage": parts[2],
                    "base": parts[3],
                    "volume": parts[4],
                    "setup": parts[5],
                    "pattern": parts[6],
                    "decision": parts[-1]
                })

    msg = "📊 BREAKOUT SUMMARY\n\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for s in stocks:

        if "BUY" in s["decision"]:
            emoji = "🟢"
        elif "WATCH" in s["decision"]:
            emoji = "🟡"
        else:
            emoji = "🔴"

        msg += f"{emoji} {s['stock']} → {s['decision']}\n"
        msg += f"Stage: {s['stage']}\n"
        msg += f"Base: {s['base']}\n"
        msg += f"Volume: {s['volume']}\n"

        if s["setup"] != "None":
            msg += f"Setup: {s['setup']}\n"

        if s["pattern"] != "None":
            msg += f"Pattern: {s['pattern']}\n"
        else:
            msg += f"Pattern: ❌ None\n"

        msg += "\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

    return msg

# ==========================
# MAIN
# ==========================
date_str = datetime.now().strftime("%Y-%m-%d")
OUT = f"charts/run_{date_str}"
os.makedirs(OUT, exist_ok=True)

stocks = get_stocks()

print("🔍 Screening...")

shortlist = []

for s in stocks:
    df = fetch_data(s, "3mo")
    df = clean(remove_live(df))

    if df.empty:
        continue

    latest = df.iloc[-1]

    if latest['Close'] < 50 or latest['Volume'] < 200000:
        continue

    high = df['High'].rolling(20).max().iloc[-1]

    if latest['Close'] < 0.85 * high:
        continue

    shortlist.append(s)

    if len(shortlist) >= 8:
        break

print("📊 Shortlist:", len(shortlist))

# ==========================
# PDF
# ==========================
pdf = f"{OUT}/report_{date_str}.pdf"
doc = SimpleDocTemplate(pdf, pagesize=letter)
styles = getSampleStyleSheet()

elements = []

for s in shortlist:

    df = clean(remove_live(fetch_data(s, "6mo")))
    if df.empty:
        continue

    w = weekly(df)

    d_path = f"{OUT}/{s}_D.png"
    w_path = f"{OUT}/{s}_W.png"

    plot_chart(df, d_path)
    plot_chart(w, w_path)

    elements.append(Paragraph(f"<b>{s}</b>", styles['Heading2']))
    elements.append(Paragraph(f"DATE: {date_str}", styles['Normal']))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("DAILY", styles['Heading3']))
    elements.append(Image(d_path, width=450, height=250))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("WEEKLY", styles['Heading3']))
    elements.append(Image(w_path, width=450, height=250))
    elements.append(Spacer(1, 20))

doc.build(elements)

print("📄 PDF Ready")

# ==========================
# GPT
# ==========================
uploaded = client.files.create(
    file=open(pdf, "rb"),
    purpose="assistants"
)

response = client.responses.create(
    model="gpt-4.1",
    input=[{
        "role": "user",
        "content": [
            {"type": "input_text", "text": GPT_PROMPT},
            {"type": "input_file", "file_id": uploaded.id}
        ]
    }]
)

out = response.output_text
print(out)

# ==========================
# TELEGRAM
# ==========================
card_msg = format_card_style(out)

chunks = [card_msg[i:i+3500] for i in range(0, len(card_msg), 3500)]

for c in chunks:
    send_msg(c)

send_doc(pdf)

print("✅ DONE")
