# ==============================================
# 🚀 FINAL SYSTEM (ENTRY / EXIT FIXED)
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
from reportlab.lib.utils import ImageReader

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

        except:
            continue

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
# TRADE LOGIC (FIXED)
# ==========================
def create_trade(df):

    last = df.iloc[-1]

    entry = float(last['High'])
    exit_price = float(last['Low'])

    risk_per_share = entry - exit_price

    if risk_per_share <= 0:
        return None

    risk_amt = CAPITAL * RISK_PER_TRADE
    qty = int(risk_amt / risk_per_share)

    return round(entry,2), round(exit_price,2), qty


# ==========================
# CHART ENGINE (UNCHANGED)
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

    legend = [
        Patch(facecolor='black', label='EMA10'),
        Patch(facecolor='red', label='EMA21'),
        Patch(facecolor='blue', label='EMA50'),
        Patch(facecolor='purple', label='EMA200')
    ]

    fig1, ax1 = mpf.plot(
        df, type='candle', style=style, addplot=apds,
        volume=True, returnfig=True,
        figsize=(12,6), datetime_format='%b-%y'
    )

    ax1[0].legend(handles=legend)
    ax1[0].set_title(f"{stock} (Daily)", fontsize=14)

    fig1.savefig("d.png", dpi=200, bbox_inches='tight', pad_inches=0)
    plt.close(fig1)

    fig2, ax2 = mpf.plot(
        df_weekly, type='candle', style=style,
        volume=True, returnfig=True,
        figsize=(12,6), datetime_format='%b-%y'
    )

    ax2[0].set_title(f"{stock} (Weekly)", fontsize=14)

    fig2.savefig("w.png", dpi=200, bbox_inches='tight', pad_inches=0)
    plt.close(fig2)

    fig = plt.figure(figsize=(12,9))

    a1 = fig.add_subplot(2,1,1)
    a1.imshow(plt.imread("d.png"))
    a1.axis('off')

    a2 = fig.add_subplot(2,1,2)
    a2.imshow(plt.imread("w.png"))
    a2.axis('off')

    plt.subplots_adjust(hspace=0.05)
    plt.savefig(save_path, dpi=200, bbox_inches='tight', pad_inches=0)
    plt.close()


# ==========================
# PDF BUILDER
# ==========================
def build_pdf(images, path):

    doc = SimpleDocTemplate(
        path,
        pagesize=letter,
        leftMargin=20,
        rightMargin=20,
        topMargin=20,
        bottomMargin=20
    )

    elements = []

    # ✅ TRUE SAFE AREA (critical fix)
    MAX_W = doc.width          # usable width
    MAX_H = doc.height * 0.90  # leave buffer (avoid overflow)

    for img_path in images:

        img = ImageReader(img_path)
        w, h = img.getSize()

        # scale safely within frame
        scale = min(MAX_W / w, MAX_H / h)

        new_w = w * scale
        new_h = h * scale

        elements.append(Image(img_path, width=new_w, height=new_h))
        elements.append(Spacer(1, 12))  # spacing between charts

    doc.build(elements)


# ==========================
# GPT
# ==========================
def gpt_decision(pdf_path):

    file = client.files.create(file=open(pdf_path,"rb"), purpose="assistants")

    PROMPT = """
You are an institutional breakout trader.

Score each stock (0–10)
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

    images = []
    trade_map = {}

    for s in shortlist:

        img = f"{folder}/{s}.png"
        plot_chart(s, img)
        images.append(img)

        df = fetch(s)
        trade_map[s] = create_trade(df)

    pdf_path = f"{folder}/charts.pdf"
    build_pdf(images, pdf_path)

    send_document(pdf_path, "📄 Charts sent to GPT")

    output = gpt_decision(pdf_path)
    send_message(output[:3000])

    picks = [l.split("|")[0].replace("-","").strip()
             for l in output.split("\n") if l.startswith("-")]

    for s in picks:
        if s not in trade_map:
            continue

        entry, exit_price, qty = trade_map[s]

        msg = f"""
📈 *FINAL TRADE*

{s}

Entry: `{entry}`
Exit: `{exit_price}`
Qty: `{qty}`
"""

        buttons = [[{"text":"✅ Confirm Buy","callback_data":f"BUY|{s}|{qty}"}]]

        send_message(msg, buttons)


# ==========================
# RUN
# ==========================
if __name__ == "__main__":
    run()
