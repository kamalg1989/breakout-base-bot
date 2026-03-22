# ==============================================
# 🚀 PRODUCTION: NSE → SCREENER → CHARTS → GPT
# ==============================================

import os
import pandas as pd
import yfinance as yf
import mplfinance as mpf
import zipfile
import matplotlib.pyplot as plt
import time
from datetime import datetime
import requests
from openai import OpenAI

# ==========================
# 🔑 API KEY
# ==========================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ==========================
# FETCH NSE STOCKS
# ==========================
def get_all_nse_stocks():

    indices = [
        "NIFTY 500",
        "NIFTY MIDCAP 150",
        "NIFTY SMALLCAP 250"
    ]

    headers = {"User-Agent": "Mozilla/5.0"}
    all_stocks = set()

    for index in indices:
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={index.replace(' ', '%20')}"

        try:
            data = requests.get(url, headers=headers).json()

            for item in data['data']:
                symbol = item['symbol']

                if not symbol.isalpha():
                    continue

                all_stocks.add(symbol + ".NS")

        except:
            continue

    return list(all_stocks)

# ==========================
# CREATE RUN FOLDER
# ==========================
BASE_DIR = "charts"
os.makedirs(BASE_DIR, exist_ok=True)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUTPUT_DIR = os.path.join(BASE_DIR, f"run_{timestamp}")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"📁 Run folder: {OUTPUT_DIR}")

# ==========================
# GET STOCK UNIVERSE
# ==========================
STOCK_UNIVERSE = get_all_nse_stocks()
print(f"📊 Total stocks fetched: {len(STOCK_UNIVERSE)}")

# ==========================
# SCREENER + PREFILTER + BASE
# ==========================
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

        # ===== PREFILTER =====
        price = float(latest['Close'])
        volume = float(latest['Volume'])

        if price < 50 or volume < 200000:
            continue

        # ===== INDICATORS =====
        df['EMA50'] = df['Close'].ewm(span=50).mean()
        df['EMA200'] = df['Close'].ewm(span=200).mean()
        df['Vol_Avg'] = df['Volume'].rolling(20).mean()
        df['High_20'] = df['High'].rolling(20).max()

        latest = df.iloc[-1]

        # ===== TREND =====
        cond1 = (
            latest['Close'] > latest['EMA50'] > latest['EMA200']
        )

        # ===== BREAKOUT =====
        cond2 = (
            pd.notna(latest['High_20']) and
            latest['Close'] >= 0.90 * latest['High_20']
        )

        # ===== VOLUME =====
        cond3 = (
            pd.notna(latest['Vol_Avg']) and
            latest['Volume'] >= 0.8 * latest['Vol_Avg']
        )

        # ===== BASE (TIGHTENED) =====
        recent = df.tail(20)
        range_pct = (recent['High'].max() - recent['Low'].min()) / recent['Low'].min() * 100

        base_cond = range_pct < 15

        if cond1 and cond2 and cond3 and base_cond:
            shortlist.append(stock)
            print(f"✅ {stock}")

        time.sleep(0.15)

    except:
        continue

print(f"\n📊 Shortlisted Stocks: {len(shortlist)}")

# ==========================
# LIMIT
# ==========================
stocks = shortlist[:20]

if len(stocks) == 0:
    print("❌ No stocks shortlisted. Exiting.")
    exit()

# ==========================
# DATA PREP
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
        'Open':'first',
        'High':'max',
        'Low':'min',
        'Close':'last',
        'Volume':'sum'
    }).dropna()

# ==========================
# PLOT
# ==========================
def plot_chart(df, stock, timeframe):

    if df is None or df.empty:
        return

    apds = []
    labels = []

    for ema, color in zip(
        ['EMA10','EMA21','EMA50','EMA200'],
        ['purple','cyan','blue','orange']
    ):
        if df[ema].notna().sum() > 5:
            apds.append(mpf.make_addplot(df[ema], color=color))
            labels.append(ema)

    filename = f"{OUTPUT_DIR}/{stock}_{timeframe}.png"

    fig, axes = mpf.plot(
        df,
        type='candle',
        style='yahoo',
        volume=True,
        addplot=apds if apds else None,
        title=f"{stock} {timeframe}",
        figsize=(12,8),
        returnfig=True
    )

    if labels:
        axes[0].legend(labels)

    fig.savefig(filename)
    plt.close(fig)

# ==========================
# GENERATE CHARTS
# ==========================
print("\n📈 Generating Charts...\n")

for stock in stocks:

    try:
        data = yf.download(stock, period="6mo", auto_adjust=True, progress=False)

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        df_daily = prepare_data(data)
        plot_chart(df_daily, stock, "Daily")

        df_weekly = resample_weekly(data)
        df_weekly = prepare_data(df_weekly)
        plot_chart(df_weekly, stock, "Weekly")

        time.sleep(0.15)

    except:
        continue

print("\n✅ Charts generated!")

# ==========================
# ZIP
# ==========================
zip_name = f"{OUTPUT_DIR}.zip"

with zipfile.ZipFile(zip_name, 'w') as z:
    for f in os.listdir(OUTPUT_DIR):
        z.write(os.path.join(OUTPUT_DIR, f), arcname=f"charts/{f}")

print(f"📦 ZIP ready: {zip_name}")

# ==========================
# GPT
# ==========================
print("\n🚀 Sending to GPT...\n")

file = client.files.create(file=open(zip_name, "rb"), purpose="assistants")

PROMPT = """[PASTE YOUR FULL SYSTEM PROMPT HERE]"""

response = client.responses.create(
    model="gpt-4.1-mini",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": PROMPT},
                {"type": "input_file", "file_id": file.id}
            ]
        }
    ]
)

print("\n📊 GPT OUTPUT:\n")
print(response.output_text)

# SAVE
with open(f"{OUTPUT_DIR}/gpt_output.txt", "w") as f:
    f.write(response.output_text)

print("\n✅ COMPLETE — SYSTEM RUN SUCCESSFUL!")
