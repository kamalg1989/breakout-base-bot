# ==============================================
# 🚀 BREAKOUT SYSTEM (CHART + ALERT + BUTTON)
# ==============================================

import os
import json
import requests
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

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

def send_chart(image_path, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"

    with open(image_path, "rb") as img:
        requests.post(url, files={"photo": img}, data={
            "chat_id": CHAT_ID,
            "caption": caption
        })

# ==========================
# DATA
# ==========================
def fetch(stock, interval="1d", period="3mo"):
    try:
        return yf.download(stock, period=period, interval=interval, progress=False)
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
# CHART GENERATION
# ==========================
def generate_chart(df, stock, filename):

    plt.figure(figsize=(10,5))
    plt.plot(df['Close'])
    plt.title(stock)
    plt.xlabel("Date")
    plt.ylabel("Price")

    plt.grid()
    plt.tight_layout()

    plt.savefig(filename)
    plt.close()

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

        df_daily = clean(fetch(s, "1d", "3mo"))
        df_weekly = clean(fetch(s, "1wk", "6mo"))

        if df_daily.empty:
            continue

        if not is_valid(df_daily):
            continue

        trade = create_trade(s, df_daily)
        if not trade or trade["qty"] <= 0:
            continue

        # ==========================
        # GENERATE CHARTS
        # ==========================
        daily_file = f"{s}_daily.png"
        weekly_file = f"{s}_weekly.png"

        generate_chart(df_daily, f"{s} Daily", daily_file)

        if not df_weekly.empty:
            generate_chart(df_weekly, f"{s} Weekly", weekly_file)

        # ==========================
        # MESSAGE
        # ==========================
        msg = f"""
📈 *TRADE ALERT*

*{s}*

Entry: `{trade['entry']}`
L1: `{trade['L1']}`
SL (8%): `{trade['hard_sl']}`
Qty: `{trade['qty']}`

_Risk Managed | Breakout Base_
"""

        callback = f"BUY|{s}|{trade['qty']}"

        buttons = [[
            {"text": "✅ Confirm Buy", "callback_data": callback}
        ]]

        # ==========================
        # SEND
        # ==========================
        send_telegram(msg, buttons)

        send_chart(daily_file, f"{s} Daily Chart")

        if not df_weekly.empty:
            send_chart(weekly_file, f"{s} Weekly Chart")

        # ==========================
        # CLEANUP
        # ==========================
        try:
            os.remove(daily_file)
            if os.path.exists(weekly_file):
                os.remove(weekly_file)
        except:
            pass


if __name__ == "__main__":
    scan_and_alert()
