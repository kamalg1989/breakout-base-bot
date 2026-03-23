# ==============================================
# 🚀 BREAKOUT BASE SYSTEM (FINAL STABLE VERSION)
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
# STRICT GPT PROMPT
# ==========================
GPT_PROMPT = """
You are a professional breakout-base trading system.

Follow STRICTLY:

STEP 1 — WEEKLY
Trend + Stage (Base1/2/3/Late)

STEP 2 — BASE SCORE (0–10)
Trend, Tightness, Volume, Pullback, EMA

STEP 3 — VOLUME (1–3)
STEP 4 — SETUP (0–3)
STEP 5 — PATTERN (MANDATORY)
If no pattern → DO NOT BUY

STEP 6 — ENTRY & SL

STEP 7 — FINAL SCORE (max 14)

STEP 8 — DECISION
≥11 BUY
8–10 WATCH
≤7 AVOID

OUTPUT:

📊 Summary Table
🎯 Execution Table
✅ Final Picks
⚠️ Notes

RULES:
- No base → reject
- No pattern → DO NOT BUY
- Max 2–3 trades
"""

# ==========================
# SAFE FETCH
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
def clean_ohlcv(df):
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
# REMOVE INCOMPLETE CANDLE
# ==========================
def remove_incomplete_candle(df):
    india = pytz.timezone("Asia/Kolkata")
    now = datetime.now(india)

    if df.index[-1].date() == now.date() and now.time() < dtime(15, 30):
        return df.iloc[:-1]

    return df

# ==========================
# WEEKLY
# ==========================
def resample_weekly(df):
    return df.resample('W').agg({
        'Open':'first',
        'High':'max',
        'Low':'min',
        'Close':'last',
        'Volume':'sum'
    }).dropna()

# ==========================
# NSE STOCKS (FIXED)
# ==========================
def get_all_nse_stocks():

    url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        data = requests.get(url, headers=headers).json()

        stocks = []

        for d in data['data']:
            symbol = d['symbol']

            if "NIFTY" in symbol:
                continue

            if not re.match(r'^[A-Z&]+$', symbol):
                continue

            stocks.append(symbol + ".NS")

        return stocks

    except:
        return []

# ==========================
# TELEGRAM
# ==========================
def send_msg(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text}
    )

def send_doc(path):
    with open(path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
            files={"document": f},
            data={"chat_id": CHAT_ID}
        )

# ==========================
# MAIN
# ==========================
date_str = datetime.now().strftime("%Y-%m-%d")
OUTPUT_DIR = f"charts/run_{date_str}"
os.makedirs(OUTPUT_DIR, exist_ok=True)

stocks = get_all_nse_stocks()

print(f"📊 Total stocks: {len(stocks)}")

shortlist = []

print("🔍 Screening...")

for stock in stocks:

    df = fetch_data(stock, "3mo")

    if df.empty or len(df) < 60:
        continue

    df = clean_ohlcv(remove_incomplete_candle(df))

    if df.empty:
        continue

    latest = df.iloc[-1]

    if latest['Close'] < 50 or latest['Volume'] < 200000:
        continue

    recent_high = df['High'].rolling(20).max().iloc[-1]

    if latest['Close'] < 0.85 * recent_high:
        continue

    shortlist.append(stock)

    if len(shortlist) >= 8:
        break

print(f"📊 Shortlist: {len(shortlist)}")

# ==========================
# PDF
# ==========================
pdf_path = f"{OUTPUT_DIR}/breakout_report_{date_str}.pdf"
doc = SimpleDocTemplate(pdf_path, pagesize=letter)
styles = getSampleStyleSheet()

elements = []

for stock in shortlist:

    data = fetch_data(stock, "6mo")
    df = clean_ohlcv(remove_incomplete_candle(data))

    if df.empty:
        continue

    weekly = resample_weekly(df)

    d_path = f"{OUTPUT_DIR}/{stock}_D.png"
    w_path = f"{OUTPUT_DIR}/{stock}_W.png"

    mpf.plot(df, type='candle', volume=True, savefig=d_path)
    mpf.plot(weekly, type='candle', volume=True, savefig=w_path)

    elements.append(Paragraph(f"<b>STOCK: {stock}</b>", styles['Heading2']))
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
# GPT (FIXED FILE UPLOAD)
# ==========================
print("🚀 GPT Analysis...")

uploaded = client.files.create(
    file=open(pdf_path, "rb"),
    purpose="assistants"
)

response = client.responses.create(
    model="gpt-5.3",
    input=[{
        "role": "user",
        "content": [
            {"type": "input_text", "text": GPT_PROMPT},
            {"type": "input_file", "file_id": uploaded.id}
        ]
    }]
)

output = response.output_text

print(output)

# ==========================
# TELEGRAM SPLIT
# ==========================
sections = [
    "📊 Summary Table",
    "🎯 Execution Table",
    "✅ Final Picks",
    "⚠️ Notes"
]

for section in sections:
    if section in output:
        part = output.split(section)[1].split("📊" if section != "📊 Summary Table" else "🎯")[0]
        send_msg(section + part)

send_doc(pdf_path)

print("✅ DONE")
