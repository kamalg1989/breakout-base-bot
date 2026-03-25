# ==============================================
# 🚀 BREAKOUT SYSTEM (TELEGRAM ALERT ONLY)
# ==============================================

import os
import json
import requests
import pandas as pd
import yfinance as yf

# ==========================
# CONFIG
# ==========================
CAPITAL = 1000000
RISK_PER_TRADE = 0.01
STATE_FILE = "trades.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==========================
# STATE
# ==========================
def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {}

def save_state(data):
    json.dump(data, open(STATE_FILE, "w"), indent=2)

# ==========================
# TELEGRAM
# ==========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": msg
    })

# ==========================
# DATA
# ==========================
def fetch(stock):
    try:
        return yf.download(stock, period="3mo", interval="1d", progress=False)
    except:
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

# ==========================
# LOGIC
# ==========================
def is_valid(df):
    recent = df.tail(20)
    high = recent['High'].max()
    low = recent['Low'].min()
    return (high - low) / low < 0.15

# ==========================
# POSITION
# ==========================
def create_trade(stock, df):

    signal = df.iloc[-1]

    H1 = signal['High']
    L1 = signal['Low']

    entry = H1
    hard_sl = entry * 0.92

    risk_amt = CAPITAL * RISK_PER_TRADE
    risk_per_share = entry - hard_sl

    qty = int(risk_amt / risk_per_share)

    return {
        "entry": round(entry,2),
        "L1": round(L1,2),
        "hard_sl": round(hard_sl,2),
        "qty": qty,
        "status": "PENDING"
    }

# ==========================
# MAIN
# ==========================
def scan_and_alert():

    stocks = ["RELIANCE.NS","TECHM.NS","PERSISTENT.NS","GRANULES.NS"]

    state = load_state()

    for s in stocks:

        # Skip if already active/pending
        if s in state and state[s]["status"] != "EXIT":
            continue

        df = clean(fetch(s))
        if df.empty:
            continue

        if not is_valid(df):
            continue

        trade = create_trade(s, df)
        state[s] = trade

        msg = f"""
📈 TRADE ALERT

{s}

Entry: {trade['entry']}
L1: {trade['L1']}
SL: {trade['hard_sl']}
Qty: {trade['qty']}

👉 Place order manually
"""

        send_telegram(msg)

    save_state(state)

if __name__ == "__main__":
    scan_and_alert()