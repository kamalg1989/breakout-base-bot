# ==============================================
# 🚀 FINAL SYSTEM (PDF-QUALITY CHARTS FIXED)
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

    return list(stocks)


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
# ✅ FIXED CHART ENGINE
# ==========================
def plot_chart(stock, save_path):

    df = fetch(stock)
    df_weekly = to_weekly(df.copy())

    # EMA
    for ema in [10,21,50,200]:
        df[f'EMA{ema}'] = df['Close'].ewm(span=ema).mean()
        df_weekly[f'EMA{ema}'] = df_weekly['Close'].ewm(span=ema).mean()

    # breakout + base
    recent = df.tail(20)
    breakout = recent['High'].max()
    base_low = recent['Low'].min()
    base_high = recent['High'].max()

    # style
    mc = mpf.make_marketcolors(
        up='green', down='red',
        volume={'up':'green','down':'red'}
    )

    style = mpf.make_mpf_style(base_mpf_style='yahoo', marketcolors=mc)

    # EMA plots
    apds = [
        mpf.make_addplot(df['EMA10'], color='red'),
        mpf.make_addplot(df['EMA21'], color='purple'),
        mpf.make_addplot(df['EMA50'], color='blue'),
        mpf.make_addplot(df['EMA200'], color='orange'),
    ]

    apds_w = [
        mpf.make_addplot(df_weekly['EMA10'], color='red'),
        mpf.make_addplot(df_weekly['EMA21'], color='purple'),
        mpf.make_addplot(df_weekly['EMA50'], color='blue'),
        mpf.make_addplot(df_weekly['EMA200'], color='orange'),
    ]

    # DAILY
    fig1, axlist1 = mpf.plot(
        df,
        type='candle',
        style=style,
        addplot=apds,
        volume=True,  # ✅ FIX
        returnfig=True,
        figsize=(10,6),
        title=f"{stock} (Daily)"
    )

    ax1 = axlist1[0]
    ax1.axhline(breakout, linestyle='--', color='green')
    ax1.axhspan(base_low, base_high, alpha=0.1, color='blue')

    daily_path = save_path.replace(".png","_d.png")
    fig1.savefig(daily_path, dpi=150)
    plt.close(fig1)

    # WEEKLY
    fig2, axlist2 = mpf.plot(
        df_weekly,
        type='candle',
        style=style,
        addplot=apds_w,
        volume=True,
        returnfig=True,
        figsize=(10,6),
        title=f"{stock} (Weekly)"
    )

    weekly_path = save_path.replace(".png","_w.png")
    fig2.savefig(weekly_path, dpi=150)
    plt.close(fig2)

    # MERGE
    fig = plt.figure(figsize=(10,10))

    ax1 = fig.add_subplot(2,1,1)
    ax1.imshow(plt.imread(daily_path))
    ax1.axis('off')

    ax2 = fig.add_subplot(2,1,2)
    ax2.imshow(plt.imread(weekly_path))
    ax2.axis('off')

    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()

    print("✅ Chart:", stock)


# ==========================
# GPT
# ==========================
def gpt_decision(pdf_path):

    file = client.files.create(file=open(pdf_path,"rb"), purpose="assistants")

    PROMPT = """
You are an institutional trader.

Focus:
- Strong trend
- Tight base
- Volume breakout
- Clean risk

Score 0-10

Pick only >=7

Return:
FINAL PICKS:
- STOCK | Score | Reason
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

    send_document(pdf_path, "📄 Charts")

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
