# ==============================================
# 🚀 BREAKOUT BASE SYSTEM (WITH POSITION SIZING)
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
CAPITAL = 1000000        # total capital (₹)
RISK_PER_TRADE = 0.01    # 1% risk

MIN_CLOSE = 50
MIN_VOLUME = 200000
BREAKOUT_THRESHOLD = 0.98
MAX_STOCKS = 10

# ==========================
# NSE STOCKS
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

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

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

    return (high - low) / low < 0.15

def is_breakout(df):
    recent = df.tail(20)
    resistance = recent['High'].max()
    close = df['Close'].iloc[-1]

    return close >= resistance * BREAKOUT_THRESHOLD

# ==========================
# POSITION SIZING
# ==========================
def calculate_position(df):

    # Signal candle = last completed candle
    signal = df.iloc[-1]

    H1 = signal['High']
    L1 = signal['Low']

    entry = H1
    hard_sl = entry * 0.92

    risk_amount = CAPITAL * RISK_PER_TRADE
    risk_per_share = entry - hard_sl

    if risk_per_share <= 0:
        return None

    qty = int(risk_amount / risk_per_share)
    capital_used = qty * entry

    return {
        "entry": round(entry, 2),
        "L1": round(L1, 2),
        "hard_sl": round(hard_sl, 2),
        "qty": qty,
        "capital": round(capital_used, 0)
    }

# ==========================
# MAIN
# ==========================
stocks = get_nifty500()

print("Total input stocks:", len(stocks))

weekly_pass = 0
base_pass = 0
breakout_pass = 0
data_fail = 0

trades = []

# ==========================
# LOOP
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

    if latest['Close'] < MIN_CLOSE or latest['Volume'] < MIN_VOLUME:
        continue

    if not is_weekly_uptrend(df):
        continue
    weekly_pass += 1

    if not is_base(df):
        continue
    base_pass += 1

    if not is_breakout(df):
        continue
    breakout_pass += 1

    pos = calculate_position(df)

    if pos and pos["qty"] > 0:
        trades.append({
            "stock": s,
            **pos
        })

    if len(trades) >= MAX_STOCKS:
        break

# ==========================
# DEBUG
# ==========================
print("\n========== DEBUG ==========")
print("After Weekly:", weekly_pass)
print("After Base:", base_pass)
print("After Breakout:", breakout_pass)
print("Trades:", len(trades))
print("===========================\n")

# ==========================
# OUTPUT
# ==========================
if not trades:
    print("❌ NO TRADES")
else:
    print("\n🎯 TRADE SETUPS\n")

    for t in trades:
        print(f"""
{t['stock']}

Entry (H1): {t['entry']}
L1: {t['L1']}
Hard SL (8%): {t['hard_sl']}

Qty: {t['qty']}
Capital Used: ₹{t['capital']}
""")