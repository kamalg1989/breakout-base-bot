# ==============================================
# 🚀 FINAL SYSTEM (ENHANCED LABELS)
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
from matplotlib.patches import Patch

from reportlab.platypus import SimpleDocTemplate, Image, Spacer
from reportlab.lib.pagesizes import letter

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

    df.index = pd.to_datetime(df.index)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df[['Open','High','Low','Close','Volume']].dropna()


def to_weekly(df):
    df.index = pd.to_datetime(df.index)

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
# CHART ENGINE
# ==========================
def plot_chart(stock, save_path):

    df = fetch(stock)
    df_weekly = to_weekly(df.copy())

    for ema in [10,21,50,200]:
        df[f'EMA{ema}'] = df['Close'].ewm(span=ema).mean()
        df_weekly[f'EMA{ema}'] = df_weekly['Close'].ewm(span=ema).mean()

    recent = df.tail(20)
    breakout = recent['High'].max()
    base_low = recent['Low'].min()
    base_high = recent['High'].max()

    mc = mpf.make_marketcolors(
        up='green', down='red',
        volume={'up':'green','down':'red'}
    )

    style = mpf.make_mpf_style(base_mpf_style='yahoo', marketcolors=mc)

    apds = [
        mpf.make_addplot(df['EMA10'], color='black'),
        mpf.make_addplot(df['EMA21'], color='red'),
        mpf.make_addplot(df['EMA50'], color='blue'),
        mpf.make_addplot(df['EMA200'], color='purple'),
    ]

    apds_w = [
        mpf.make_addplot(df_weekly['EMA10'], color='black'),
        mpf.make_addplot(df_weekly['EMA21'], color='red'),
        mpf.make_addplot(df_weekly['EMA50'], color='blue'),
        mpf.make_addplot(df_weekly['EMA200'], color='purple'),
    ]

    legend_elements = [
        Patch(facecolor='black', label='EMA10'),
        Patch(facecolor='red', label='EMA21'),
        Patch(facecolor='blue', label='EMA50'),
        Patch(facecolor='purple', label='EMA200')
    ]

    # DAILY
    fig1, axlist1 = mpf.plot(
        df, type='candle', style=style, addplot=apds,
        volume=True, returnfig=True,
        figsize=(10,6), datetime_format='%b-%y', xrotation=20
    )

    ax1 = axlist1[0]
    ax1.axhline(breakout, linestyle='--', color='green')
    ax1.axhspan(base_low, base_high, alpha=0.1)
    ax1.legend(handles=legend_elements, loc='upper left')

    # ✅ ENHANCED TITLE
    ax1.set_title(f"{stock} (Daily)", fontsize=14, fontweight='bold')

    daily_path = save_path.replace(".png","_d.png")
    fig1.savefig(daily_path, dpi=180, bbox_inches='tight', pad_inches=0)
    plt.close(fig1)

    # WEEKLY
    fig2, axlist2 = mpf.plot(
        df_weekly, type='candle', style=style, addplot=apds_w,
        volume=True, returnfig=True,
        figsize=(10,6), datetime_format='%b-%y', xrotation=20
    )

    ax2 = axlist2[0]
    ax2.legend(handles=legend_elements, loc='upper left')

    # ✅ ENHANCED TITLE
    ax2.set_title(f"{stock} (Weekly)", fontsize=14, fontweight='bold')

    weekly_path = save_path.replace(".png","_w.png")
    fig2.savefig(weekly_path, dpi=180, bbox_inches='tight', pad_inches=0)
    plt.close(fig2)

    # MERGE
    fig = plt.figure(figsize=(10,9))

    ax1 = fig.add_subplot(2,1,1)
    ax1.imshow(plt.imread(daily_path))
    ax1.axis('off')

    ax2 = fig.add_subplot(2,1,2)
    ax2.imshow(plt.imread(weekly_path))
    ax2.axis('off')

    plt.subplots_adjust(hspace=0.08)

    plt.savefig(save_path, dpi=180, bbox_inches='tight', pad_inches=0.05)
    plt.close()

    print("✅ Chart:", stock)


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

    elements = []
    trade_map = {}

    for s in shortlist:

        img = f"{folder}/{s}.png"
        plot_chart(s, img)

        df = fetch(s)
        entry, sl, qty = create_trade(df)
        trade_map[s] = (entry, sl, qty)

        elements.append(Image(img, width=520, height=420))
        elements.append(Spacer(1,10))

    pdf_path = f"{folder}/charts.pdf"
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    doc.build(elements)

    send_document(pdf_path, "📄 Charts")


# ==========================
# RUN
# ==========================
if __name__ == "__main__":
    run()
