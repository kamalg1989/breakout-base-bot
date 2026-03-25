# ==============================================
# 🚀 BREAKOUT SYSTEM (WITH TRADE TRACKING)
# ==============================================

import os
import json
import time
import pandas as pd
import yfinance as yf
from datetime import datetime

# ==========================
# CONFIG
# ==========================
CAPITAL = 1000000
RISK_PER_TRADE = 0.01
STATE_FILE = "trades.json"

# ==========================
# LOAD / SAVE STATE
# ==========================
def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {}

def save_state(data):
    json.dump(data, open(STATE_FILE, "w"), indent=2)

# ==========================
# FETCH
# ==========================
def fetch(stock):
    try:
        return yf.download(stock, period="10d", interval="1d", progress=False)
    except:
        return pd.DataFrame()

# ==========================
# ENTRY + POSITION
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
# MONITOR
# ==========================
def update_trades(trades):

    updated = {}

    for s, t in trades.items():

        df = fetch(s)
        if df.empty:
            updated[s] = t
            continue

        last_close = df['Close'].iloc[-1]

        # ENTRY CHECK
        if t["status"] == "PENDING":
            if last_close >= t["entry"]:
                t["status"] = "ACTIVE"
                print(f"🟢 ENTRY TRIGGERED: {s}")

        # EXIT CHECK
        elif t["status"] == "ACTIVE":
            if last_close < t["L1"]:
                t["status"] = "EXIT"
                print(f"🔴 EXIT SIGNAL: {s}")

        updated[s] = t

    return updated

# ==========================
# MAIN
# ==========================
state = load_state()

print("Loaded trades:", len(state))

# ---- UPDATE EXISTING ----
state = update_trades(state)

# ---- ADD NEW TRADES (manual trigger for now) ----
# (plug your shortlist logic here later)

# Example placeholder (disable later)
# state["RELIANCE.NS"] = create_trade("RELIANCE.NS", fetch("RELIANCE.NS"))

save_state(state)

# ==========================
# PRINT
# ==========================
print("\n📊 CURRENT TRADES\n")

for s, t in state.items():
    print(f"""
{s}
Status: {t['status']}
Entry: {t['entry']}
L1: {t['L1']}
SL: {t['hard_sl']}
Qty: {t['qty']}
""")