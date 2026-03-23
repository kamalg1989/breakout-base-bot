# ==============================================
# 🚀 BREAKOUT BASE SYSTEM (FINAL ELITE VERSION)
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
# GPT PROMPT (FINAL)
# ==========================
GPT_PROMPT = """
You are a professional breakout-base trading system.

STRICTLY FOLLOW:

1. Weekly trend + stage
2. Base scoring (0–10)
3. Volume strength
4. Setup
5. Pattern (MANDATORY)

If no pattern → DO NOT BUY

Score = Base + Stage + Volume + Setup + Pattern (max 14)

Decision:
≥11 BUY
8–10 WATCH
≤7 AVOID

Also provide:

• Market condition (overall)
• Watchlist (future candidates)

OUTPUT FORMAT:

📊 Summary Table
🎯 Execution Table
✅ Final Picks
⚠️ Market Context
📌 Watchlist
"""

# ==========================
# DATA
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

def remove_live(df):
    india = pytz.timezone("Asia/Kolkata")
    now = datetime.now(india)

    if df.index[-1].date() == now.date() and now.time() < dtime(15, 30):
        return df.iloc[:-1]
    return df

def weekly(df):
    return df.resample('W').agg({
        'Open':'first',
        'High':'max',
        'Low':'min',
        'Close':'last',
        'Volume':'sum'
    }).dropna()

# ==========================
# CHART
# ==========================
def plot_chart(df, path):

    df['EMA10'] = df['Close'].ewm(span=10).mean()
    df['EMA21'] = df['Close'].ewm(span=21).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()
    df['EMA200'] = df['Close'].ewm(span=200).mean()

    apds = [
        mpf.make_addplot(df['EMA10'], color='red'),
        mpf.make_addplot(df['EMA21'], color='blue'),
        mpf.make_addplot(df['EMA50'], color='purple'),
        mpf.make_addplot(df['EMA200'], color='cyan'),
    ]

    mc = mpf.make_marketcolors(
        up='green', down='red',
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
# FORMATTER (FINAL)
# ==========================
def parse_and_send(output):

    lines = output.split("\n")

    stocks = []
    market_context = ""
    watchlist = ""

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
                    "score": parts[7],
                    "decision": parts[-1]
                })

        if "Market" in line:
            market_context += line + "\n"

        if "Watchlist" in line or "Monitor" in line:
            watchlist += line + "\n"

    # ======================
    # MESSAGE 1 — SUMMARY
    # ======================
    msg1 = "📊 BREAKOUT SUMMARY\n\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for s in stocks:

        if "BUY" in s["decision"]:
            emoji = "🟢"
        elif "WATCH" in s["decision"]:
            emoji = "🟡"
        else:
            emoji = "🔴"

        msg1 += f"{emoji} {s['stock']} → {s['decision']} (Score: {s['score']})\n"
        msg1 += f"Stage: {s['stage']}\n"
        msg1 += f"Base: {s['base']}\n"
        msg1 += f"Volume: {s['volume']}\n"

        if s["setup"] != "None":
            msg1 += f"Setup: {s['setup']}\n"

        msg1 += f"Pattern: {s['pattern'] if s['pattern']!='None' else '❌ None'}\n"
        msg1 += "\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

    send_msg(msg1)

    # ======================
    # MESSAGE 2 — EXECUTION
    # ======================
    buys = [s for s in stocks if "BUY" in s["decision"]]

    if not buys:
        msg2 = """🎯 EXECUTION PLAN

━━━━━━━━━━━━━━━━━━━━━━

❌ NO VALID SETUPS

No stock meets breakout criteria

👉 DO NOTHING

━━━━━━━━━━━━━━━━━━━━━━"""
    else:
        msg2 = "🎯 EXECUTION PLAN\n\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for b in buys:
            msg2 += f"🟢 {b['stock']}\nSetup: {b['setup']}\n\n"

    msg2 += "\n⚠️ Risk: 1–2% per trade"
    send_msg(msg2)

    # ======================
    # MESSAGE 3 — FINAL PICKS
    # ======================
    if not buys:
        msg3 = """🔥 FINAL PICKS

❌ NO TRADES

Stay in CASH
"""
    else:
        msg3 = "🔥 FINAL PICKS\n\n"
        for b in buys[:2]:
            msg3 += f"• {b['stock']} ⭐\n"

    send_msg(msg3)

    # ======================
    # MESSAGE 4 — MARKET
    # ======================
    send_msg("⚠️ MARKET CONTEXT\n\n" + (market_context or "Market mixed / weak"))

    # ======================
    # MESSAGE 5 — WATCHLIST
    # ======================
    send_msg("📌 WATCHLIST\n\n" + (watchlist or "Monitor improving bases"))

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
    df = clean(remove_live(fetch_data(s, "3mo")))

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

    d = f"{OUT}/{s}_D.png"
    w_img = f"{OUT}/{s}_W.png"

    plot_chart(df, d)
    plot_chart(w, w_img)

    elements.append(Paragraph(f"<b>{s}</b>", styles['Heading2']))
    elements.append(Spacer(1, 10))
    elements.append(Image(d, width=450, height=250))
    elements.append(Spacer(1, 10))
    elements.append(Image(w_img, width=450, height=250))
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
parse_and_send(out)
send_doc(pdf)

print("✅ DONE")
