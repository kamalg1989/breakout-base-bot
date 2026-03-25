# ==============================================
# 🚀 FINAL SYSTEM (PRODUCTION READY)
# Screener → Charts → PDF → GPT → Telegram → Button
# ==============================================

import os
import json
import time
import requests
import pandas as pd
import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt
from datetime import datetime
from openai import OpenAI

from reportlab.platypus import SimpleDocTemplate, Image, Spacer, Paragraph
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet

# ==========================
# CONFIG
# ==========================
CAPITAL = 1000000
RISK_PER_TRADE = 0.01

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==========================
# TELEGRAM
# ==========================
def send_message(text, buttons=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }

    if buttons:
        payload["reply_markup"] = json.dumps({"inline_keyboard": buttons})

    requests.post(url, data=payload)

def send_document(file_path):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    with open(file_path, "rb") as f:
        requests.post(url, files={"document": f}, data={"chat_id": CHAT_ID})

# ==========================
# NSE STOCKS
# ==========================
def get_nse_stocks():
    url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        data = requests.get(url, headers=headers).json()
        return [x['symbol'] + ".NS" for x in data['data'] if x['symbol'].isalpha()]
    except:
        return []

# ==========================
# DATA
# ==========================
def fetch(stock):
    df = yf.download(stock, period="6mo", auto_adjust=True, progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df[['Open','High','Low','Close','Volume']].dropna()

# ==========================
# STRICT SCREENER
# ==========================
def is_valid(df):

    df['EMA50'] = df['Close'].ewm(span=50).mean()
    df['EMA200'] = df['Close'].ewm(span=200).mean()
    df['Vol_Avg'] = df['Volume'].rolling(20).mean()
    df['High_20'] = df['High'].rolling(20).max()

    latest = df.iloc[-1]

    cond1 = latest['Close'] > latest['EMA50'] > latest['EMA200']
    cond2 = latest['Close'] >= 0.9 * latest['High_20']
    cond3 = latest['Volume'] >= 0.8 * latest['Vol_Avg']

    recent = df.tail(20)
    range_pct = (recent['High'].max() - recent['Low'].min()) / recent['Low'].min()

    return cond1 and cond2 and cond3 and range_pct < 0.15

# ==========================
# TRADE
# ==========================
def create_trade(df):
    row = df.iloc[-1]

    entry = row['High']
    sl = entry * 0.92

    risk = entry - sl
    qty = int((CAPITAL * RISK_PER_TRADE) / risk)

    return {
        "entry": round(entry,2),
        "sl": round(sl,2),
        "qty": qty
    }

# ==========================
# CHART
# ==========================
def plot_chart(df, stock, path):

    df['EMA10'] = df['Close'].ewm(span=10).mean()
    df['EMA21'] = df['Close'].ewm(span=21).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()
    df['EMA200'] = df['Close'].ewm(span=200).mean()

    apds = [
        mpf.make_addplot(df['EMA10'], color='purple'),
        mpf.make_addplot(df['EMA21'], color='cyan'),
        mpf.make_addplot(df['EMA50'], color='blue'),
        mpf.make_addplot(df['EMA200'], color='orange')
    ]

    fig, ax = mpf.plot(
        df,
        type='candle',
        style='yahoo',
        volume=True,
        addplot=apds,
        returnfig=True
    )

    fig.savefig(path)
    plt.close(fig)

# ==========================
# GPT RANKING
# ==========================
def gpt_select(stocks):

    prompt = f"""
Select best breakout trades.

Stocks:
{stocks}

Return ONLY top 2 symbols.
"""

    res = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    return res.output_text

# ==========================
# MAIN FLOW
# ==========================
def run():

    stocks = get_nse_stocks()
    shortlisted = []

    for s in stocks:
        try:
            df = fetch(s)

            if len(df) < 50:
                continue

            if df['Close'].iloc[-1] < 50:
                continue

            if not is_valid(df):
                continue

            shortlisted.append(s)

        except:
            continue

    print("Shortlisted:", len(shortlisted))

    # Limit for performance
    shortlisted = shortlisted[:10]

    # ==========================
    # CHARTS + PDF
    # ==========================
    folder = f"run_{datetime.now().strftime('%H%M%S')}"
    os.makedirs(folder, exist_ok=True)

    styles = getSampleStyleSheet()
    elements = []

    trade_map = {}

    for s in shortlisted:

        df = fetch(s)

        path = f"{folder}/{s}.png"
        plot_chart(df, s, path)

        trade = create_trade(df)
        trade_map[s] = trade

        elements.append(Paragraph(f"<b>{s}</b>", styles['Heading2']))
        elements.append(Spacer(1,10))
        elements.append(Image(path, width=500, height=300))
        elements.append(Spacer(1,20))

    pdf_path = f"{folder}/report.pdf"
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    doc.build(elements)

    # ==========================
    # GPT FILTER
    # ==========================
    picks = gpt_select(shortlisted)

    print("GPT Picks:", picks)

    # ==========================
    # TELEGRAM
    # ==========================
    send_document(pdf_path)

    for s in shortlisted:

        if s not in picks:
            continue

        t = trade_map[s]

        msg = f"""
📈 *TOP PICK*

*{s}*

Entry: `{t['entry']}`
SL: `{t['sl']}`
Qty: `{t['qty']}`
"""

        callback = f"BUY|{s}|{t['qty']}"

        buttons = [[{"text":"✅ Confirm Buy","callback_data":callback}]]

        send_message(msg, buttons)


# ==========================
# RUN
# ==========================
if __name__ == "__main__":
    run()
