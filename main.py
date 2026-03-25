# ==============================================
# 🚀 BREAKOUT SYSTEM (TELEGRAM + DHAN EXECUTION)
# ==============================================

import os
import json
import time
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
from flask import Flask, request

# ==========================
# CONFIG
# ==========================
CAPITAL = 1000000
RISK_PER_TRADE = 0.01
STATE_FILE = "trades.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DHAN_CLIENT_ID = os.getenv("DHAN_CLIENT_ID")
DHAN_ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")

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
# DHAN ORDER
# ==========================
def place_order(stock, qty):

    url = "https://api.dhan.co/orders"

    payload = {
        "dhanClientId": DHAN_CLIENT_ID,
        "transactionType": "BUY",
        "exchangeSegment": "NSE_EQ",
        "productType": "CNC",
        "orderType": "MARKET",
        "securityId": stock.replace(".NS",""),
        "quantity": qty
    }

    headers = {
        "access-token": DHAN_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    r = requests.post(url, json=payload, headers=headers)

    return r.json()

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
        "stock": stock,
        "entry": round(entry,2),
        "L1": round(L1,2),
        "hard_sl": round(hard_sl,2),
        "qty": qty,
        "status": "PENDING"
    }

# ==========================
# SCAN + ALERT
# ==========================
def scan_and_alert():

    stocks = ["RELIANCE.NS","TECHM.NS","PERSISTENT.NS","GRANULES.NS"]  # replace with your shortlist

    state = load_state()

    for s in stocks:

        df = clean(fetch(s))
        if df.empty:
            continue

        if not is_valid(df):
            continue

        trade = create_trade(s, df)

        state[s] = trade

        msg = f"""
📈 *TRADE ALERT*

{ s }

Entry: {trade['entry']}
L1: {trade['L1']}
SL (8%): {trade['hard_sl']}
Qty: {trade['qty']}
"""

        buttons = [[
            {"text": "✅ Confirm Buy", "callback_data": f"BUY|{s}"}
        ]]

        send_telegram(msg, buttons)

    save_state(state)

# ==========================
# WEBHOOK (TELEGRAM)
# ==========================
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.json

    if "callback_query" in data:

        query = data["callback_query"]
        action, stock = query["data"].split("|")

        state = load_state()
        trade = state.get(stock)

        if not trade:
            return "OK"

        if action == "BUY":

            res = place_order(stock, trade["qty"])

            trade["status"] = "ACTIVE"
            state[stock] = trade
            save_state(state)

            send_telegram(f"🟢 ORDER PLACED: {stock}")

    return "OK"

# ==========================
# SET TELEGRAM WEBHOOK
# ==========================
def set_webhook():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    requests.post(url, data={"url": WEBHOOK_URL})

# ==========================
# MAIN
# ==========================
if __name__ == "__main__":

    # Step 1: scan and send alerts
    scan_and_alert()

    # Step 2: start webhook server
    set_webhook()

    app.run(host="0.0.0.0", port=8000)