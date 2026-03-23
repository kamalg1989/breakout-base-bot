# ==============================================
# 🚀 BREAKOUT BASE SYSTEM (FINAL PRO VERSION)
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

# ==========================
# CONFIG
# ==========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==========================
# SAFE FETCH (STABLE)
# ==========================
def fetch_data(stock, period):

    for _ in range(3):
        try:
            df = yf.Ticker(stock).history(period=period, auto_adjust=True)

            if df is not None and not df.empty:
                return df

        except:
            pass

        time.sleep(0.5)

    return pd.DataFrame()

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
# CLEAN DATA
# ==========================
def clean_ohlcv(df):

    if df is None or df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = ['Open','High','Low','Close','Volume']

    if not all(col in df.columns for col in required):
        return pd.DataFrame()

    df = df[required].copy()

    for col in required:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    return df.dropna()

# ==========================
# WEEKLY RESAMPLE
# ==========================
def resample_weekly(df):

    return df.resample('W').agg({
        'Open':'first',
        'High':'max',
        'Low':'min',
        'Close':'last',
        'Volume':'sum'
    }).dropna()

# ==========================
# SYMBOL FILTER
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
        "NIFTY AUTO","NIFTY FMCG","NIFTY METAL"
    ]

    headers = {"User-Agent": "Mozilla/5.0"}
    stocks = set()

    for index in indices:
        try:
            url = f"https://www.nseindia.com/api/equity-stockIndices?index={index.replace(' ', '%20')}"
            res = requests.get(url, headers=headers)

            if res.status_code != 200:
                continue

            data = res.json()

            if 'data' not in data:
                continue

            for item in data['data']:
                symbol = item['symbol']

                if is_valid_symbol(symbol):
                    stocks.add(symbol + ".NS")

        except:
            continue

    stocks_list = sorted(list(stocks))
    print(f"📊 Total stocks: {len(stocks_list)}")

    return stocks_list

# ==========================
# TELEGRAM
# ==========================
def send_msg(txt):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": txt}
    )

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
# ELITE SCREENER (PDF ALIGNED)
# ==========================
print("\n🔍 Running ELITE Screener...\n")

for stock in stocks_all:

    df = fetch_data(stock, "4mo")

    if df.empty or len(df) < 100:
        continue

    df = remove_incomplete_candle(df)
    df = clean_ohlcv(df)

    if df.empty:
        continue

    latest = df.iloc[-1]

    # --------------------------
    # 1. Liquidity
    # --------------------------
    if latest['Close'] < 50 or latest['Volume'] < 200000:
        continue

    # --------------------------
    # 2. Trend (Institutional bias)
    # --------------------------
    df['EMA50'] = df['Close'].ewm(span=50).mean()
    df['EMA200'] = df['Close'].ewm(span=200).mean()

    if not (latest['Close'] > df['EMA50'].iloc[-1] > df['EMA200'].iloc[-1]):
        continue

    # --------------------------
    # 3. Base (Accumulation)
    # --------------------------
    base = df.tail(30)

    base_high = base['High'].max()
    base_low = base['Low'].min()

    range_pct = (base_high - base_low) / base_low * 100

    if range_pct > 20:
        continue

    # --------------------------
    # 4. Controlled pullback
    # --------------------------
    drawdown = (base_high - base_low) / base_high * 100

    if drawdown > 25:
        continue

    # --------------------------
    # 5. Volume contraction (IFP)
    # --------------------------
    base_vol = base['Volume'].mean()
    prior_vol = df['Volume'].iloc[-90:-30].mean()

    if base_vol > prior_vol:
        continue

    # --------------------------
    # 6. Breakout proximity
    # --------------------------
    recent_high = df['High'].tail(20).max()

    if latest['Close'] < 0.9 * recent_high:
        continue

    # --------------------------
    # 7. Not extended
    # --------------------------
    if (latest['Close'] / base_low) > 1.3:
        continue

    shortlist.append(stock)
    print(f"✅ {stock}")

print(f"\n📊 Final Shortlist: {len(shortlist)}")

# ==========================
# CHART GENERATION
# ==========================
valid_stocks = []

print("\n📈 Generating charts...\n")

for stock in shortlist[:5]:

    data = fetch_data(stock, "6mo")

    if data.empty:
        continue

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

# ==========================
# TELEGRAM OUTPUT
# ==========================
if not valid_stocks:
    send_msg("⚠️ No valid breakout-base setups today")
    exit()

msg = "📊 Breakout Base Report\n\n"
msg += "\n".join(valid_stocks)

send_msg(msg)

print("\n✅ SYSTEM COMPLETE")
