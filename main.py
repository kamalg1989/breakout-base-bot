# ==============================================
# 🚀 ELITE SYSTEM: NSE → SCREENER → PDF → GPT → TELEGRAM
# ==============================================

import os
import pandas as pd
import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt
import time
from datetime import datetime, time as dtime
import pytz
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
# 🧠 REMOVE INCOMPLETE CANDLE
# ==========================
def remove_incomplete_candle(df):

    if df is None or df.empty:
        return df

    india = pytz.timezone("Asia/Kolkata")
    now = datetime.now(india)

    last_date = df.index[-1].date()

    if last_date != now.date():
        return df

    market_close = dtime(15, 30)

    if now.time() < market_close:
        return df.iloc[:-1]

    return df

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
# 🚀 SCREENER (STRICT)
# ==========================
STOCK_UNIVERSE = get_all_nse_stocks()
print(f"📊 Total stocks: {len(STOCK_UNIVERSE)}")

shortlist = []

print("\n🔍 Running ELITE Screener...\n")

for stock in STOCK_UNIVERSE:

    try:
        df = yf.download(stock, period="4mo", auto_adjust=True, progress=False)
        df = remove_incomplete_candle(df)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty or len(df) < 80:
            continue

        df = df[['Open','High','Low','Close','Volume']].dropna()
        latest = df.iloc[-1]

        # Liquidity
        if latest['Close'] < 50 or latest['Volume'] < 200000:
            continue

        # Trend
        df['EMA50'] = df['Close'].ewm(span=50).mean()
        df['EMA200'] = df['Close'].ewm(span=200).mean()

        if not (latest['Close'] > df['EMA50'].iloc[-1] > df['EMA200'].iloc[-1]):
            continue

        # Base
        base = df.tail(25)
        base_high = base['High'].max()
        base_low = base['Low'].min()

        range_pct = (base_high - base_low) / base_low * 100
        if range_pct > 18:
            continue

        # Volume
        base_vol = base['Volume'].mean()
        prior_vol = df['Volume'].tail(60).mean()

        vol_dry = base_vol < prior_vol * 0.8
        vol_expand = latest['Volume'] > base['Volume'].tail(5).mean()

        if not (vol_dry and vol_expand):
            continue

        # Breakout
        df['High_20'] = df['High'].rolling(20).max()
        if latest['Close'] < 0.9 * df['High_20'].iloc[-1]:
            continue

        # Relative strength
        df['Return_20'] = df['Close'].pct_change(20)
        if df['Return_20'].iloc[-1] < 0:
            continue

        # Avoid extended
        if (latest['Close'] / base_low) > 1.25:
            continue

        shortlist.append(stock)
        print(f"✅ {stock}")

    except:
        continue

print(f"\n📊 Strict Shortlist: {len(shortlist)}")

# ==========================
# 🔁 FALLBACK SCREENER
# ==========================
if len(shortlist) == 0:

    print("\n⚠️ No stocks — running fallback...\n")

    for stock in STOCK_UNIVERSE:

        try:
            df = yf.download(stock, period="4mo", auto_adjust=True, progress=False)
            df = remove_incomplete_candle(df)

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            if df.empty or len(df) < 60:
                continue

            df = df[['Open','High','Low','Close','Volume']].dropna()
            latest = df.iloc[-1]

            if latest['Close'] < 50:
                continue

            df['EMA50'] = df['Close'].ewm(span=50).mean()
            if latest['Close'] < df['EMA50'].iloc[-1]:
                continue

            base = df.tail(20)
            base_high = base['High'].max()
            base_low = base['Low'].min()

            range_pct = (base_high - base_low) / base_low * 100
            if range_pct > 25:
                continue

            df['High_20'] = df['High'].rolling(20).max()
            if latest['Close'] < 0.85 * df['High_20'].iloc[-1]:
                continue

            shortlist.append(f"{stock} (F)")
            print(f"🔁 {stock}")

            if len(shortlist) >= 5:
                break

        except:
            continue

print(f"\n📊 Final Shortlist: {len(shortlist)}")

stocks = [s.replace(" (F)", "") for s in shortlist[:10]]

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
        data = remove_incomplete_candle(data)

        df_daily = prepare_data(data)
        plot_chart(df_daily, stock, "Daily")

        df_weekly = resample_weekly(data)
        df_weekly = prepare_data(df_weekly)
        plot_chart(df_weekly, stock, "Weekly")

    except:
        continue

print("✅ Charts ready")

# ==========================
# PDF
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
# GPT
# ==========================
print("\n🚀 Sending PDF to GPT...\n")

file = client.files.create(file=open(pdf_path, "rb"), purpose="assistants")

PROMPT = """Analyze ONLY charts provided using breakout-base system.

Strict scoring. No guessing.

Output:
Summary Table
Execution Table
Final Picks (Top 2)
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

# ==========================
# TELEGRAM
# ==========================
print("\n📲 Sending to Telegram...\n")

def send_message(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    )

def send_document(path):
    with open(path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
            files={"document": f},
            data={"chat_id": CHAT_ID}
        )

msg = "📊 *Daily Breakout Report*\n\n"
msg += response.output_text[:1000]

send_message(msg)
send_document(pdf_path)

print("✅ Telegram sent!")
print("\n🎉 SYSTEM COMPLETE")
