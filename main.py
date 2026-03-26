# ==============================================
# 🚀 FINAL SYSTEM (INSTITUTIONAL + SCORE OVERLAY)
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
# NSE STOCK FETCH (FIXED)
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
# TRADE
# ==========================
def create_trade(df):
    entry = df.iloc[-1]['High']
    sl = entry * 0.92
    qty = int((CAPITAL * RISK_PER_TRADE) / (entry - sl))
    return round(entry,2), round(sl,2), qty


# ==========================
# GPT PARSE
# ==========================
def parse_gpt_output(output):

    scores = {}
    picks = []

    for line in output.split("\n"):
        if "|" in line and "-" in line:
            try:
                parts = line.replace("-", "").split("|")
                stock = parts[0].strip()
                score = float(parts[1].strip())

                scores[stock] = score

                if score >= 7:
                    picks.append(stock)

            except:
                continue

    return scores, picks


# ==========================
# SCORE STYLE
# ==========================
def score_style(score):

    if score >= 8:
        return "green", "STRONG"
    elif score >= 7:
        return "yellow", "MODERATE"
    else:
        return "red", "WEAK"


# ==========================
# CHART ENGINE
# ==========================
def plot_chart(stock, save_path, score=None):

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

    ax = ax1[0]
    ax.axhline(breakout, linestyle='--', color='green')
    ax.axhspan(base_low, base_high, alpha=0.1)
    ax.legend(handles=legend)

    if score is not None:
        color, label = score_style(score)
        ax.text(
            0.78, 0.92,
            f"{score}/10\n{label}",
            transform=ax.transAxes,
            fontsize=11,
            fontweight='bold',
            bbox=dict(facecolor=color, alpha=0.6)
        )

    ax.set_title(f"{stock} (Daily)", fontsize=14, fontweight='bold')

    fig1.savefig("d.png", dpi=200, bbox_inches='tight', pad_inches=0)
    plt.close(fig1)

    fig2, ax2 = mpf.plot(
        df_weekly, type='candle', style=style,
        volume=True, returnfig=True,
        figsize=(12,6), datetime_format='%b-%y'
    )

    ax2[0].set_title(f"{stock} (Weekly)", fontsize=14, fontweight='bold')

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
# PDF
# ==========================
def build_pdf(images, path):

    doc = SimpleDocTemplate(path, pagesize=letter)
    elements = []

    for img_path in images:

        img = ImageReader(img_path)
        w, h = img.getSize()

        page_w, page_h = letter
        scale = min((page_w-20)/w, (page_h-20)/h)

        elements.append(Image(img_path, width=w*scale, height=h*scale))
        elements.append(Spacer(1,8))

    doc.build(elements)


# ==========================
# GPT
# ==========================
def gpt_decision(pdf_path):

    file = client.files.create(file=open(pdf_path,"rb"), purpose="assistants")

    PROMPT = """
Institutional breakout system.

Score each stock (0-10)
Pick >=7

Return:
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

    scores, picks = parse_gpt_output(output)

    images_scored = []
    for s in shortlist:
        img = f"{folder}/{s}_scored.png"
        plot_chart(s, img, score=scores.get(s))
        images_scored.append(img)

    pdf_path2 = f"{folder}/charts_scored.pdf"
    build_pdf(images_scored, pdf_path2)

    send_document(pdf_path2, "📊 Charts with Scores")

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
