# ==============================================
# 🚀 FINAL SYSTEM: NSE → SCREENER → PDF → GPT → TELEGRAM
# ==============================================

import os
import pandas as pd
import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt
import time
from datetime import datetime
import requests
from openai import OpenAI

# PDF
from reportlab.platypus import SimpleDocTemplate, Image, Spacer, Paragraph
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet

# ==========================
# 🔑 API
# ==========================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==========================
# FETCH NSE STOCKS
# ==========================
def get_all_nse_stocks():
    indices = ["NIFTY 500", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"]
    headers = {"User-Agent": "Mozilla/5.0"}

    stocks = set()

    for index in indices:
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={index.replace(' ', '%20')}"
        try:
            data = requests.get(url, headers=headers).json()
            for item in data['data']:
                symbol = item['symbol']
                if symbol.isalpha():
                    stocks.add(symbol + ".NS")
        except:
            continue

    return list(stocks)

# ==========================
# CREATE FOLDER
# ==========================
BASE_DIR = "charts"
os.makedirs(BASE_DIR, exist_ok=True)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUTPUT_DIR = os.path.join(BASE_DIR, f"run_{timestamp}")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"📁 Run folder: {OUTPUT_DIR}")

# ==========================
# SCREENER
# ==========================
STOCK_UNIVERSE = get_all_nse_stocks()
print(f"📊 Total stocks: {len(STOCK_UNIVERSE)}")

shortlist = []

print("\n🔍 Running Screener...\n")

for stock in STOCK_UNIVERSE:

    try:
        df = yf.download(stock, period="3mo", auto_adjust=True, progress=False)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty or len(df) < 50:
            continue

        df = df[['Open','High','Low','Close','Volume']].dropna()
        latest = df.iloc[-1]

        if latest['Close'] < 50 or latest['Volume'] < 200000:
            continue

        df['EMA50'] = df['Close'].ewm(span=50).mean()
        df['EMA200'] = df['Close'].ewm(span=200).mean()
        df['Vol_Avg'] = df['Volume'].rolling(20).mean()
        df['High_20'] = df['High'].rolling(20).max()

        latest = df.iloc[-1]

        cond1 = latest['Close'] > latest['EMA50'] > latest['EMA200']
        cond2 = latest['Close'] >= 0.90 * latest['High_20']
        cond3 = latest['Volume'] >= 0.8 * latest['Vol_Avg']

        recent = df.tail(20)
        range_pct = (recent['High'].max() - recent['Low'].min()) / recent['Low'].min() * 100

        if cond1 and cond2 and cond3 and range_pct < 15:
            shortlist.append(stock)
            print(f"✅ {stock}")

        time.sleep(0.1)

    except:
        continue

print(f"\n📊 Shortlisted: {len(shortlist)}")

stocks = shortlist[:10]

if not stocks:
    print("❌ No stocks found")
    exit()

# ==========================
# PREP
# ==========================
def prepare_data(df):

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[['Open','High','Low','Close','Volume']].dropna()

    df['EMA10'] = df['Close'].ewm(span=10).mean()
    df['EMA21'] = df['Close'].ewm(span=21).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()
    df['EMA200'] = df['Close'].ewm(span=200).mean()

    return df

def resample_weekly(df):
    return df.resample('W').agg({
        'Open':'first','High':'max','Low':'min',
        'Close':'last','Volume':'sum'
    }).dropna()

# ==========================
# PLOT
# ==========================
def plot_chart(df, stock, timeframe):

    apds, labels = [], []

    for ema, color in zip(
        ['EMA10','EMA21','EMA50','EMA200'],
        ['purple','cyan','blue','orange']
    ):
        if df[ema].notna().sum() > 5:
            apds.append(mpf.make_addplot(df[ema], color=color))
            labels.append(ema)

    filename = f"{OUTPUT_DIR}/{stock}_{timeframe}.png"

    fig, axes = mpf.plot(
        df, type='candle', style='yahoo',
        volume=True, addplot=apds,
        returnfig=True
    )

    if labels:
        axes[0].legend(labels)

    fig.savefig(filename)
    plt.close(fig)

# ==========================
# GENERATE CHARTS
# ==========================
print("\n📈 Generating charts...\n")

for stock in stocks:
    try:
        data = yf.download(stock, period="6mo", auto_adjust=True, progress=False)

        df_daily = prepare_data(data)
        plot_chart(df_daily, stock, "Daily")

        df_weekly = resample_weekly(data)
        df_weekly = prepare_data(df_weekly)
        plot_chart(df_weekly, stock, "Weekly")

        time.sleep(0.1)

    except:
        continue

print("✅ Charts ready")

# ==========================
# CREATE PDF
# ==========================
print("\n📄 Creating PDF...\n")

pdf_path = f"{OUTPUT_DIR}/charts.pdf"

doc = SimpleDocTemplate(pdf_path, pagesize=letter)
styles = getSampleStyleSheet()

elements = []

for stock in stocks:

    elements.append(Paragraph(f"<b>{stock}</b>", styles['Heading2']))
    elements.append(Spacer(1, 10))

    daily = f"{OUTPUT_DIR}/{stock}_Daily.png"
    weekly = f"{OUTPUT_DIR}/{stock}_Weekly.png"

    if os.path.exists(daily):
        elements.append(Image(daily, width=500, height=280))
        elements.append(Spacer(1, 10))

    if os.path.exists(weekly):
        elements.append(Image(weekly, width=500, height=280))
        elements.append(Spacer(1, 20))

doc.build(elements)

print(f"📄 PDF created: {pdf_path}")

# ==========================
# GPT (PDF INPUT)
# ==========================
print("\n🚀 Sending PDF to GPT...\n")

file = client.files.create(file=open(pdf_path, "rb"), purpose="assistants")

PROMPT = """Analyze charts using breakout-base strategy.

Give:
1. Summary Table
2. Execution Table
3. Final Picks (Top 2)

Rules:
- Prefer tight base
- No pattern → no buy
"""

response = client.responses.create(
    model="gpt-4.1-mini",
    input=[{
        "role": "user",
        "content": [
            {"type": "input_text", "text": PROMPT},
            {"type": "input_file", "file_id": file.id}
        ]
    }]
)

print("\n📊 GPT OUTPUT:\n")
print(response.output_text)

# SAVE
with open(f"{OUTPUT_DIR}/gpt_output.txt", "w") as f:
    f.write(response.output_text)

# ==========================
# TELEGRAM
# ==========================
print("\n📲 Sending to Telegram...\n")

def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=payload)

def send_document(file_path):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    with open(file_path, "rb") as f:
        requests.post(url, files={"document": f}, data={"chat_id": CHAT_ID})

# Cleaner message (only final picks)
msg = "📊 *Daily Breakout Report*\n\n"

if "Final Picks" in response.output_text:
    msg += response.output_text.split("Final Picks")[-1][:1000]
else:
    msg += response.output_text[:1000]

send_message(msg)
send_document(pdf_path)

print("✅ Telegram sent!")

print("\n🎉 SYSTEM COMPLETE — FULLY AUTOMATED")
