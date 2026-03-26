# ==============================================
# 🚀 FINAL SYSTEM (NO WHITESPACE – FIXED)
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
# CHART ENGINE (STRETCHED)
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

    # DAILY (wider)
    fig1, axlist1 = mpf.plot(
        df,
        type='candle',
        style=style,
        addplot=apds,
        volume=True,
        returnfig=True,
        figsize=(12,6),   # 🔥 wider
        datetime_format='%b-%y',
        xrotation=15
    )

    ax1 = axlist1[0]
    ax1.axhline(breakout, linestyle='--', color='green')
    ax1.axhspan(base_low, base_high, alpha=0.1)
    ax1.legend(handles=legend_elements, loc='upper left')
    ax1.set_title(f"{stock} (Daily)", fontsize=14, fontweight='bold')

    fig1.savefig("daily.png", dpi=200, bbox_inches='tight', pad_inches=0)
    plt.close(fig1)

    # WEEKLY
    fig2, axlist2 = mpf.plot(
        df_weekly,
        type='candle',
        style=style,
        addplot=apds_w,
        volume=True,
        returnfig=True,
        figsize=(12,6),
        datetime_format='%b-%y',
        xrotation=15
    )

    ax2 = axlist2[0]
    ax2.legend(handles=legend_elements, loc='upper left')
    ax2.set_title(f"{stock} (Weekly)", fontsize=14, fontweight='bold')

    fig2.savefig("weekly.png", dpi=200, bbox_inches='tight', pad_inches=0)
    plt.close(fig2)

    # MERGE (minimal gap)
    fig = plt.figure(figsize=(12,9))

    ax1 = fig.add_subplot(2,1,1)
    ax1.imshow(plt.imread("daily.png"))
    ax1.axis('off')

    ax2 = fig.add_subplot(2,1,2)
    ax2.imshow(plt.imread("weekly.png"))
    ax2.axis('off')

    plt.subplots_adjust(hspace=0.05)

    plt.savefig(save_path, dpi=200, bbox_inches='tight', pad_inches=0)
    plt.close()


# ==========================
# PDF (AUTO SCALE → KEY FIX)
# ==========================
def build_pdf(images, pdf_path):

    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    elements = []

    for img_path in images:

        img = ImageReader(img_path)
        w, h = img.getSize()

        page_w, page_h = letter

        scale = min((page_w-20)/w, (page_h-20)/h)

        elements.append(
            Image(img_path, width=w*scale, height=h*scale)
        )

        elements.append(Spacer(1,8))  # small gap

    doc.build(elements)


# ==========================
# MAIN
# ==========================
def run():

    stocks = ["RELIANCE.NS","TCS.NS","INFY.NS"]  # test

    folder = f"run_{datetime.now().strftime('%H%M%S')}"
    os.makedirs(folder, exist_ok=True)

    images = []

    for s in stocks:
        img = f"{folder}/{s}.png"
        plot_chart(s, img)
        images.append(img)

    pdf_path = f"{folder}/charts.pdf"

    build_pdf(images, pdf_path)

    send_document(pdf_path, "📄 Charts Ready")


# ==========================
# RUN
# ==========================
if __name__ == "__main__":
    run()
