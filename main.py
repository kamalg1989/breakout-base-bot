# ==============================================
# 🚀 BREAKOUT BASE SYSTEM (DEBUG + STABLE VERSION)
# ==============================================

import os
import time
import pandas as pd
import yfinance as yf
import requests
from datetime import datetime, time as dtime
import pytz

# ==========================
# CONFIG
# ==========================
USE_CHARTINK = False          # 🔴 Set True if using CSV
CSV_PATH = "chartink.csv"     # Path to your CSV

MIN_CLOSE = 50
MIN_VOLUME = 200000
BREAKOUT_THRESHOLD = 0.98     # relaxed from 1.0
MAX_STOCKS = 20

# ==========================
# CHARTINK PARSER
# ==========================
def load_chartink_csv(path):
    df = pd.read_csv(path)

    column_map = {
        "Symbol": "Ticker",
        "Close Price": "Close",
        "Total Traded Volume": "Volume"
    }

    df = df.rename(columns=column_map)

    if "Ticker" not in df.columns:
        raise Exception("❌ Ticker column missing in CSV")

    df["Ticker"] = df["Ticker"].astype(str)

    # Normalize NSE format
    df["Ticker"] = df["Ticker"].apply(
        lambda x: x if x.endswith(".NS") else x + ".NS"
    )

    return df[["Ticker"]].dropna().drop_duplicates()

# ==========================
# NSE STOCKS (fallback)
# ==========================
def get_nifty500():
    url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        data = requests.get(url, headers=headers).json()
        return [
            d['symbol'] + ".NS"
            for d in data['data']
            if "NIFTY" not in d['symbol']
        ]
    except:
        return []

# ==========================
# DATA
# ==========================
def fetch(stock):
    for _ in range(3):
        try:
            df = yf.download(stock, period="6mo", interval="1d", progress=False)
            if not df.empty:
                return df
        except:
            pass
        time.sleep(0.3)
    return pd.DataFrame()

def clean(df):
    if df.empty:
        return df

    cols = ['Open','High','Low','Close','Volume']
    if not all(c in df.columns for c in cols):
        return pd.DataFrame()

    df = df[cols].copy()

    for c in cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    return df.dropna()

def remove_live(df):
    india = pytz.timezone("Asia/Kolkata")
    now = datetime.now(india)

    if len(df) == 0:
        return df

    if df.index[-1].date() == now.date() and now.time() < dtime(15, 30):
        return df.iloc[:-1]

    return df

# ==========================
# LOGIC
# ==========================
def is_weekly_uptrend(df):
    w = df.resample('W').last()
    if len(w) < 5:
        return False

    return w['Close'].iloc[-1] > w['Close'].iloc[-4]

def is_base(df):
    recent = df.tail(20)
    high = recent['High'].max()
    low = recent['Low'].min()

    # tight range
    return (high - low) / low < 0.15

def is_breakout(df):
    recent = df.tail(20)
    resistance = recent['High'].max()
    close = df['Close'].iloc[-1]

    return close >= resistance * BREAKOUT_THRESHOLD

# ==========================
# LOAD STOCKS
# ==========================
if USE_CHARTINK:
    df_input = load_chartink_csv(CSV_PATH)
    stocks = df_input["Ticker"].tolist()
else:
    stocks = get_nifty500()

print("Total input stocks:", len(stocks))

# ==========================
# DEBUG COUNTERS
# ==========================
total = len(stocks)
weekly_pass = 0
base_pass = 0
breakout_pass = 0
data_fail = 0

shortlist = []

# ==========================
# MAIN LOOP
# ==========================
for s in stocks:

    df = fetch(s)

    if df.empty:
        data_fail += 1
        continue

    df = clean(remove_live(df))

    if df.empty:
        data_fail += 1
        continue

    latest = df.iloc[-1]

    # Basic filters
    if latest['Close'] < MIN_CLOSE or latest['Volume'] < MIN_VOLUME:
        continue

    # WEEKLY
    if not is_weekly_uptrend(df):
        continue
    weekly_pass += 1

    # BASE
    if not is_base(df):
        continue
    base_pass += 1

    # BREAKOUT
    if not is_breakout(df):
        continue
    breakout_pass += 1

    shortlist.append(s)

    if len(shortlist) >= MAX_STOCKS:
        break

# ==========================
# DEBUG OUTPUT
# ==========================
print("\n========== DEBUG ==========")
print("Total:", total)
print("Data Fail:", data_fail)
print("After Weekly:", weekly_pass)
print("After Base:", base_pass)
print("After Breakout:", breakout_pass)
print("Final Shortlist:", len(shortlist))
print("===========================\n")

print("Shortlist:", shortlist)

# ==========================
# QUICK DIAGNOSIS
# ==========================
if weekly_pass == 0:
    print("⚠️ Issue: Weekly trend filter too strict or market weak")

elif base_pass == 0:
    print("⚠️ Issue: Base detection too strict")

elif breakout_pass == 0:
    print("⚠️ Issue: Breakout condition too strict")

elif len(shortlist) == 0:
    print("⚠️ No trades — likely market condition")

else:
    print("✅ System working — trades found")