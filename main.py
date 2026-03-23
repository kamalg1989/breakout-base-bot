# ==============================================
# 🚀 ELITE SYSTEM (FINAL VERSION)
# NSE → SCREENER → PDF → GPT → CLEAN TELEGRAM
# ==============================================

import os
import pandas as pd
import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt
from datetime import datetime, time as dtime
import pytz
import requests
from openai import OpenAI

# PDF
from reportlab.platypus import SimpleDocTemplate, Image, Spacer, Paragraph
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet

# ==========================
# 🔧 CONFIG
# ==========================
DEBUG = False

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

    if now.time() < dtime(15, 30):
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

        if df.empty or len(df) < 80:
            continue

        df = df[['Open','High','Low','Close','Volume']].dropna()
        latest = df.iloc[-1]

        if latest['Close'] < 50 or latest['Volume'] < 200000:
            continue

        df['EMA50'] = df['Close'].ewm(span=50).mean()
        df['EMA200'] = df['Close'].ewm(span=200).mean()

        if not (latest['Close'] > df['EMA50'].iloc[-1] > df['EMA200'].iloc[-1]):
            continue

        base = df.tail(25)
        base_high = base['High'].max()
        base_low = base['Low'].min()

        range_pct = (base_high - base_low) / base_low * 100
        if range_pct > 18:
            continue

        base_vol = base['Volume'].mean()
        prior_vol = df['Volume'].tail(60).mean()

        vol_dry = base_vol < prior_vol * 0.8
        vol_expand = latest['Volume'] > base['Volume'].tail(5).mean()

        if not (vol_dry and vol_expand):
            continue

        df['High_20'] = df['High'].rolling(20).max()
        if latest['Close'] < 0.9 * df['High_20'].iloc[-1]:
            continue

        df['Return_20'] = df['Close'].pct_change(20)
        if df['Return_20'].iloc[-1] < 0:
            continue

        if (latest['Close'] / base_low) > 1.25:
            continue

        shortlist.append(stock)
        print(f"✅ {stock}")

    except:
        continue

print(f"\n📊 Strict Shortlist: {len(shortlist)}")

# ==========================
# 🔁 FALLBACK (FIXED + RELIABLE)
# ==========================
if len(shortlist) == 0:

    print("\n⚠️ Running fallback...\n")

    for stock in STOCK_UNIVERSE:

        try:
            df = yf.download(stock, period="3mo", auto_adjust=True, progress=False)

            if df is None or df.empty or len(df) < 30:
                continue

            df = remove_incomplete_candle(df)

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df[['Open','High','Low','Close','Volume']].dropna()

            if df.empty:
                continue

            latest = df.iloc[-1]

            # ✅ ONLY BASIC FILTERS (RELAXED)
            if latest['Close'] < 50:
                continue

            # 👉 REMOVE EMA restriction (IMPORTANT FIX)

            # ✅ SIMPLE MOMENTUM
            recent_high = df['High'].tail(20).max()

            if latest['Close'] < 0.8 * recent_high:
                continue

            shortlist.append(f"{stock} (F)")
            print(f"🔁 {stock}")

            # ✅ LIMIT OUTPUT
            if len(shortlist) >= 5:
                break

        except Exception as e:
            print(f"⚠️ Error fallback {stock}: {e}")
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
# CHARTS
# ==========================
print("\n📈 Generating charts...\n")

for stock in stocks:
    try:
        data = yf.download(stock, period="6mo", auto_adjust=True, progress=False)
        data = remove_incomplete_candle(data)

        df_daily = prepare_data(data)
        df_weekly = prepare_data(resample_weekly(data))

        mpf.plot(df_daily, type='candle', volume=True,
                 savefig=f"{OUTPUT_DIR}/{stock}_Daily.png")

        mpf.plot(df_weekly, type='candle', volume=True,
                 savefig=f"{OUTPUT_DIR}/{stock}_Weekly.png")

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

    elements.append(Image(f"{OUTPUT_DIR}/{stock}_Daily.png", width=500, height=280))
    elements.append(Spacer(1, 10))
    elements.append(Image(f"{OUTPUT_DIR}/{stock}_Weekly.png", width=500, height=280))
    elements.append(Spacer(1, 20))

doc.build(elements)

print("📄 PDF ready")
# ==========================
# 🚀 MOCK GPT (TEST MODE)
# ==========================
print("\n🧪 Using MOCK GPT...\n")

# Split shortlist
clean_stocks = [s.replace(" (F)", "") for s in shortlist]

buy = clean_stocks[:2]
watch = clean_stocks[2:5]
avoid = []

# Create mock response text (for logs)
mock_response = "MOCK GPT OUTPUT\n\n"

if buy:
    mock_response += "Top Picks:\n"
    for s in buy:
        mock_response += f"{s} → Score 12 (BUY)\n"

if watch:
    mock_response += "\nWatchlist:\n"
    for s in watch:
        mock_response += f"{s} → Score 9 (WATCH)\n"

print(mock_response)

# ==========================
# 📲 TELEGRAM (CLEAN FORMAT)
# ==========================
print("\n📲 Sending Telegram...\n")

def send_message(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "Markdown"
        }
    )

def send_document(path):
    with open(path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
            files={"document": f},
            data={"chat_id": CHAT_ID}
        )

# ==========================
# 🧠 BUILD CLEAN MESSAGE
# ==========================
msg = "📊 *Daily Breakout Report*\n\n"

# BUY
if buy:
    msg += "🔥 *Top Picks*\n"
    for s in buy:
        msg += f"• {s}\n"
    msg += "\n"

# WATCH
if watch:
    msg += "⚠️ *Watchlist*\n"
    for s in watch:
        msg += f"• {s}\n"
    msg += "\n"

# NO TRADE CASE
if not buy and not watch:
    msg += "❌ No valid setups today\n"

# SEND
send_message(msg)
send_document(pdf_path)

print("✅ Telegram sent!")
print("\n🎉 SYSTEM COMPLETE (MOCK MODE)")
