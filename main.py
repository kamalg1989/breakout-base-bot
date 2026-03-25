# ==============================================
# 🚀 FINAL SYSTEM (INSTITUTIONAL VERSION)
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
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CAPITAL = 1000000
RISK_PER_TRADE = 0.01

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


def send_document(path, caption=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    with open(path, "rb") as f:
        requests.post(url, files={"document": f},
                      data={"chat_id": CHAT_ID, "caption": caption or ""})


# ==========================
# NSE STOCK FETCH
# ==========================
def get_stocks():

    headers = {"User-Agent": "Mozilla/5.0"}

    indices = [
        "NIFTY 500",
        "NIFTY MIDCAP 150",
        "NIFTY SMALLCAP 250"
    ]

    stocks = set()

    for index in indices:
        try:
            url = f"https://www.nseindia.com/api/equity-stockIndices?index={index.replace(' ', '%20')}"
            res = requests.get(url, headers=headers, timeout=10)

            data = res.json()

            for item in data.get("data", []):
                symbol = item.get("symbol")

                if symbol and symbol.isalpha():
                    stocks.add(symbol + ".NS")

            time.sleep(0.5)

        except Exception as e:
            print("NSE fetch error:", e)

    stocks = list(stocks)
    print("Total stocks:", len(stocks))

    return stocks


# ==========================
# DATA
# ==========================
def fetch(stock):
    df = yf.download(stock, period="6mo", auto_adjust=True, progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df[['Open','High','Low','Close','Volume']].dropna()


def to_weekly(df):
    return df.resample('W').agg({
        'Open':'first','High':'max','Low':'min',
        'Close':'last','Volume':'sum'
    }).dropna()


# ==========================
# FILTER
# ==========================
def filter_stock(df):

    if len(df) < 50:
        return False

    df['EMA50'] = df['Close'].ewm(span=50).mean()
    df['EMA200'] = df['Close'].ewm(span=200).mean()

    cond1 = df.iloc[-1]['Close'] > df.iloc[-1]['EMA50'] > df.iloc[-1]['EMA200']

    recent = df.tail(20)
    base_range = (recent['High'].max() - recent['Low'].min()) / recent['Low'].min()
    cond2 = base_range < 0.15

    vol_avg = df['Volume'].rolling(20).mean()
    cond3 = df.iloc[-1]['Volume'] > 0.8 * vol_avg.iloc[-1]

    return cond1 and cond2 and cond3


# ==========================
# TRADE LOGIC
# ==========================
def create_trade(df):
    entry = df.iloc[-1]['High']
    sl = entry * 0.92
    qty = int((CAPITAL * RISK_PER_TRADE) / (entry - sl))
    return round(entry,2), round(sl,2), qty


# ==========================
# CHART
# ==========================
def plot_chart(stock, path):

    df = fetch(stock)
    df_weekly = to_weekly(df.copy())

    def add_ema(d):
        d['EMA10'] = d['Close'].ewm(span=10).mean()
        d['EMA21'] = d['Close'].ewm(span=21).mean()
        d['EMA50'] = d['Close'].ewm(span=50).mean()
        d['EMA200'] = d['Close'].ewm(span=200).mean()
        return d

    df = add_ema(df)
    df_weekly = add_ema(df_weekly)

    recent = df.tail(20)
    breakout = recent['High'].max()
    base_low = recent['Low'].min()
    base_high = recent['High'].max()

    trend = "Uptrend" if df.iloc[-1]['EMA50'] > df.iloc[-1]['EMA200'] else "Downtrend"

    mc = mpf.make_marketcolors(up='green', down='red', volume='blue')
    style = mpf.make_mpf_style(base_mpf_style='yahoo', marketcolors=mc)

    fig = plt.figure(figsize=(10,8))

    # DAILY
    ax1 = fig.add_subplot(4,1,1)
    ax1_vol = fig.add_subplot(4,1,2, sharex=ax1)

    apds = [
        mpf.make_addplot(df['EMA10'], ax=ax1),
        mpf.make_addplot(df['EMA21'], ax=ax1),
        mpf.make_addplot(df['EMA50'], ax=ax1),
        mpf.make_addplot(df['EMA200'], ax=ax1),
    ]

    mpf.plot(df, ax=ax1, volume=ax1_vol, style=style, addplot=apds)

    ax1.axhline(breakout, linestyle='--', color='green')
    ax1.axhspan(base_low, base_high, alpha=0.15)
    ax1.text(0.01,0.95,f"{stock} DAILY ({trend})", transform=ax1.transAxes)

    # WEEKLY
    ax2 = fig.add_subplot(4,1,3)
    ax2_vol = fig.add_subplot(4,1,4, sharex=ax2)

    apds2 = [
        mpf.make_addplot(df_weekly['EMA10'], ax=ax2),
        mpf.make_addplot(df_weekly['EMA21'], ax=ax2),
        mpf.make_addplot(df_weekly['EMA50'], ax=ax2),
        mpf.make_addplot(df_weekly['EMA200'], ax=ax2),
    ]

    mpf.plot(df_weekly, ax=ax2, volume=ax2_vol, style=style, addplot=apds2)

    ax2.text(0.01,0.95,f"{stock} WEEKLY", transform=ax2.transAxes)

    plt.tight_layout()
    plt.savefig(path)
    plt.close()


# ==========================
# GPT DECISION (ADVANCED)
# ==========================
def gpt_decision(pdf_path):

    file = client.files.create(file=open(pdf_path,"rb"), purpose="assistants")

    PROMPT = """
You are an institutional trader.

Focus on:
- Base formation
- Volume confirmation
- Clean breakout
- Risk control

Score each stock (0–10)

Only pick score >= 7

Return:

FINAL PICKS:
- STOCK | Score | Reason

EXECUTION:
- STOCK | Entry | StopLoss
"""

    res = client.responses.create(
        model="gpt-4.1-mini",
        input=[{
            "role":"user",
            "content":[
                {"type":"input_text","text":PROMPT},
                {"type":"input_file","file_id":file.id}
            ]
        }]
    )

    return res.output_text


# ==========================
# MAIN
# ==========================
def run():

    stocks = get_stocks()

    shortlist = []

    for s in stocks:
        try:
            df = fetch(s)
            if filter_stock(df):
                shortlist.append(s)
        except:
            continue

    shortlist = shortlist[:10]

    print("Shortlisted:", shortlist)

    folder = f"run_{datetime.now().strftime('%H%M%S')}"
    os.makedirs(folder, exist_ok=True)

    styles = getSampleStyleSheet()
    elements = []
    trade_map = {}

    for s in shortlist:

        img = f"{folder}/{s}.png"
        plot_chart(s, img)

        df = fetch(s)
        entry, sl, qty = create_trade(df)
        trade_map[s] = (entry, sl, qty)

        elements.append(Paragraph(f"<b>{s}</b>", styles['Heading2']))
        elements.append(Spacer(1,10))
        elements.append(Image(img, width=500, height=400))
        elements.append(Spacer(1,20))

    pdf_path = f"{folder}/charts.pdf"
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    doc.build(elements)

    send_document(pdf_path, "📄 Charts sent to GPT")

    output = gpt_decision(pdf_path)

    send_message(output[:3000])

    picks = [l.split("|")[0].replace("-","").strip()
             for l in output.split("\n") if l.startswith("-")]

    for s in picks:
        if s not in trade_map:
            continue

        entry, sl, qty = trade_map[s]

        msg = f"""
📈 *FINAL TRADE*

{s}

Entry: `{entry}`
SL: `{sl}`
Qty: `{qty}`
"""

        buttons = [[{"text":"✅ Confirm Buy","callback_data":f"BUY|{s}|{qty}"}]]

        send_message(msg, buttons)


# ==========================
# RUN
# ==========================
if __name__ == "__main__":
    run()
