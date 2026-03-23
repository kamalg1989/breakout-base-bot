# ==============================================
# 🚀 ELITE SYSTEM (FINAL HARDENED VERSION)
# ==============================================

import os
import re
import time
import pandas as pd
import yfinance as yf
import mplfinance as mpf
from datetime import datetime, time as dtime
import pytz
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# PDF
from reportlab.platypus import SimpleDocTemplate, Image, Spacer, Paragraph
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet

# ==========================
# CRITICAL FIX (DB LOCK)
# ==========================
yf.set_tz_cache_location(None)

# ==========================
# CONFIG
# ==========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==========================
# REMOVE INCOMPLETE CANDLE
# ==========================
def remove_incomplete_candle(df):
    if df is None or df.empty:
        return df

    india = pytz.timezone("Asia/Kolkata")
    now = datetime.now(india)

    if df.index[-1].date() != now.date():
        return df

    if now.time() < dtime(15, 30):
        return df.iloc[:-1]

    return df

# ==========================
# CLEAN OHLCV (FINAL FIX)
# ==========================
def clean_ohlcv(df):

    if df is None or df.empty:
        return pd.DataFrame()

    # Fix MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = ['Open','High','Low','Close','Volume']

    if not all(col in df.columns for col in required):
        return pd.DataFrame()

    df = df[required].copy()

    for col in required:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.dropna()

    return df

# ==========================
# WEEKLY RESAMPLE
# ==========================
def resample_weekly(df):
    return df.resample('W').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }).dropna()

# ==========================
# SYMBOL VALIDATION
# ==========================
def is_valid_symbol(symbol):
    return re.match(r'^[A-Z&]+$', symbol) is not None

# ==========================
# NSE STOCKS
# ==========================
def get_all_nse_stocks():

    indices = [
        "NIFTY 50","NIFTY NEXT 50","NIFTY 500",
        "NIFTY MIDCAP 150","NIFTY SMALLCAP 250",
        "NIFTY BANK","NIFTY IT","NIFTY PHARMA",
        "NIFTY AUTO","NIFTY FMCG","NIFTY METAL",
        "NIFTY ENERGY","NIFTY INFRA","NIFTY PSU BANK"
    ]

    headers = {"User-Agent": "Mozilla/5.0"}
    stocks = set()

    for index in indices:
        try:
            url = f"https://www.nseindia.com/api/equity-stockIndices?index={index.replace(' ', '%20')}"
            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                continue

            data = response.json()

            if 'data' not in data:
                continue

            for item in data['data']:
                symbol = item['symbol']

                if is_valid_symbol(symbol):
                    stocks.add(symbol + ".NS")

        except:
            continue

    stocks_list = sorted(list(stocks))
    print(f"📊 Unique stocks count: {len(stocks_list)}")

    return stocks_list

# ==========================
# STRICT
# ==========================
def process_stock_strict(stock):

    time.sleep(0.1)

    try:
        df = yf.download(stock, period="4mo", auto_adjust=True, progress=False)

        if df is None or df.empty or len(df) < 80:
            return None

        df = remove_incomplete_candle(df)
        df = clean_ohlcv(df)

        if df.empty:
            return None

        latest = df.iloc[-1]

        if latest['Close'] < 50 or latest['Volume'] < 200000:
            return None

        df['EMA50'] = df['Close'].ewm(span=50).mean()
        df['EMA200'] = df['Close'].ewm(span=200).mean()

        if not (latest['Close'] > df['EMA50'].iloc[-1] > df['EMA200'].iloc[-1]):
            return None

        base = df.tail(25)

        if (base['High'].max() - base['Low'].min()) / base['Low'].min() * 100 > 18:
            return None

        return stock

    except:
        return None

# ==========================
# FALLBACK
# ==========================
def process_stock_fallback(stock):

    time.sleep(0.1)

    try:
        df = yf.download(stock, period="3mo", auto_adjust=True, progress=False)

        if df is None or df.empty or len(df) < 30:
            return None

        df = remove_incomplete_candle(df)
        df = clean_ohlcv(df)

        if df.empty:
            return None

        latest = df.iloc[-1]

        if latest['Close'] < 50:
            return None

        if latest['Close'] < 0.8 * df['High'].tail(20).max():
            return None

        return stock + " (F)"

    except:
        return None

# ==========================
# MAIN
# ==========================
BASE_DIR = "charts"
os.makedirs(BASE_DIR, exist_ok=True)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUTPUT_DIR = os.path.join(BASE_DIR, f"run_{timestamp}")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"📁 Run folder: {OUTPUT_DIR}")

stocks_all = get_all_nse_stocks()

shortlist = []

# ==========================
# STRICT
# ==========================
print("\n🔍 Running STRICT...\n")

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(process_stock_strict, s) for s in stocks_all]

    for f in as_completed(futures):
        res = f.result()
        if res:
            shortlist.append(res)

print(f"\n📊 Strict: {len(shortlist)}")

# ==========================
# FALLBACK
# ==========================
if len(shortlist) == 0:

    print("\n⚠️ Running FALLBACK...\n")

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_stock_fallback, s) for s in stocks_all]

        for f in as_completed(futures):
            res = f.result()

            if res:
                shortlist.append(res)

            if len(shortlist) >= 5:
                break

# FINAL SAFETY
if len(shortlist) == 0:
    print("\n🚨 Using TOP STOCKS fallback\n")
    shortlist = stocks_all[:5]

print(f"\n📊 Final Shortlist: {len(shortlist)}")

stocks = [s.replace(" (F)", "") for s in shortlist[:10]]

# ==========================
# CHARTS
# ==========================
valid_stocks = []

print("\n📈 Generating charts...\n")

for stock in stocks:
    try:
        data = yf.download(stock, period="6mo", auto_adjust=True, progress=False)

        data = remove_incomplete_candle(data)
        df = clean_ohlcv(data)

        if df.empty:
            continue

        weekly = resample_weekly(df)

        if weekly.empty:
            continue

        d_path = f"{OUTPUT_DIR}/{stock}_Daily.png"
        w_path = f"{OUTPUT_DIR}/{stock}_Weekly.png"

        mpf.plot(df, type='candle', volume=True, savefig=d_path)
        mpf.plot(weekly, type='candle', volume=True, savefig=w_path)

        valid_stocks.append(stock)
        print(f"✅ {stock}")

    except Exception as e:
        print(f"⚠️ {stock}: {e}")

# ==========================
# TELEGRAM
# ==========================
def send_msg(txt):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": txt}
    )

if not valid_stocks:
    send_msg("⚠️ No valid charts generated today")

    # GitHub artifact fix
    with open(f"{OUTPUT_DIR}/empty.txt", "w") as f:
        f.write("No charts")

    exit()

msg = "📊 Daily Breakout Report\n\n"
msg += "\n".join(valid_stocks[:5])

send_msg(msg)

print("✅ DONE")
