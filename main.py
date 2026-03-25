# ==============================================
# 🚀 BREAKOUT SYSTEM (STATELESS TELEGRAM ALERTS)
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

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==========================
# TELEGRAM
# ==========================
def send_telegram(msg, buttons=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }

    if buttons:
        payload["reply_markup"] = json.dumps({
            "inline_keyboard": buttons
        })

    requests.post(url, data=payload)

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

    if risk_per_share <= 0:
        return None

    qty = int(risk_amt / risk_per_share)

    return {
        "entry": round(entry, 2),
        "L1": round(L1, 2),
        "hard_sl": round(hard_sl, 2),
        "qty": qty
    }

# ==========================
# MAIN
# ==========================
def scan_and_alert():

    stocks = ["RELIANCE.NS","TECHM.NS","PERSISTENT.NS","GRANULES.NS"]

    for s in stocks:

        df = clean(fetch(s))
        if df.empty:
            continue

        if not is_valid(df):
            continue

        trade = create_trade(s, df)
        if not trade or trade["qty"] <= 0:
            continue

        msg = f"""
📈 *TRADE ALERT*

{s}

Entry: {trade['entry']}
L1: {trade['L1']}
SL (8%): {trade['hard_sl']}
Qty: {trade['qty']}
"""

        # 🔥 Stateless payload (critical)
        callback = f"BUY|{s}|{trade['qty']}"

        buttons = [[
            {"text": "✅ Confirm Buy", "callback_data": callback}
        ]]

        send_telegram(msg, buttons)


if __name__ == "__main__":
    scan_and_alert()