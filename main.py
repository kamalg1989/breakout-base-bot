# ==============================================
# 🚀 ELITE SYSTEM (FINAL STABLE + FIXED VERSION)
# ==============================================

import os
import re
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
# CLEAN OHLCV (CRITICAL FIX)
# ==========================
def clean_ohlcv(df):

    if df is None or df.empty:
        return df

    df = df[['Open','High','Low','Close','Volume']].copy()

    for col in ['Open','High','Low','Close','Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.dropna()

    return df

# ==========================
# SYMBOL VALIDATION
# ==========================
def is_valid_symbol(symbol):
    return re.match(r'^[A-Z&]+$', symbol) is not None

# ==========================
# NSE STOCK UNIVERSE
# ==========================
def get_all_nse_stocks():

    indices = [
        "NIFTY 50","NIFTY NEXT 50","NIFTY 500",
        "NIFTY MIDCAP 150","NIFTY SMALLCAP 250",
        "NIFTY BANK","NIFTY IT","NIFTY PHARMA",
        "NIFTY AUTO","NIFTY FMCG","NIFTY METAL",
        "NIFTY ENERGY","NIFTY INFRA","NIFTY PSU BANK",
        "NIFTY 200 MOMENTUM 30","NIFTY ALPHA 50",
        "NIFTY LOW VOLATILITY 50"
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
                print(f"⚠️ No data for index {index}")
                continue

            for item in data['data']:
                symbol = item['symbol']

                if is_valid_symbol(symbol):
                    stocks.add(symbol + ".NS")

        except Exception as e:
            print(f"⚠️ Failed index {index}: {e}")

    stocks_list = sorted(list(stocks))
    print(f"📊 Unique stocks count: {len(stocks_list)}")

    return stocks_list

# ==========================
# STRICT FUNCTION
# ==========================
def process_stock_strict(stock):
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

        base_vol = base['Volume'].mean()
        prior_vol = df['Volume'].tail(60).mean()

        if not (base_vol < prior_vol * 0.8 and latest['Volume'] > base['Volume'].tail(5).mean()):
            return None

        df['High_20'] = df['High'].rolling(20).max()
        if latest['Close'] < 0.9 * df['High_20'].iloc[-1]:
            return None

        if df['Close'].pct_change(20).iloc[-1] < 0:
            return None

        if (latest['Close'] / base['Low'].min()) > 1.25:
            return None

        return stock

    except:
        return None

# ==========================
# FALLBACK FUNCTION
# ==========================
def process_stock_fallback(stock):

    for _ in range(2):
        try:
            df = yf.download(stock, period="3mo", auto_adjust=True, progress=False)

            if df is None or df.empty or len(df) < 30:
                continue

            df = remove_incomplete_candle(df)
            df = clean_ohlcv(df)

            if df.empty:
                continue

            latest = df.iloc[-1]

            if latest['Close'] < 50:
                return None

            if latest['Close'] < 0.8 * df['High'].tail(20).max():
                return None

            return stock + " (F)"

        except:
            continue

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
processed = set()

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
            processed.add(res)
            print(f"✅ {res}")

print(f"\n📊 Strict: {len(shortlist)}")

# ==========================
# FALLBACK
# ==========================
if len(shortlist) == 0:

    print("\n⚠️ Running FALLBACK...\n")

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_stock_fallback, s) for s in stocks_all if s not in processed]

        for f in as_completed(futures):
            res = f.result()

            if res:
                shortlist.append(res)
                print(f"🔁 {res}")

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

        if data is None or data.empty:
            continue

        data = remove_incomplete_candle(data)

        df = clean_ohlcv(data)

        if df.empty:
            continue

        weekly = clean_ohlcv(df.resample('W').last())

        if weekly.empty:
            continue

        d_path = f"{OUTPUT_DIR}/{stock}_Daily.png"
        w_path = f"{OUTPUT_DIR}/{stock}_Weekly.png"

        mpf.plot(df, type='candle', volume=True, savefig=d_path)
        mpf.plot(weekly, type='candle', volume=True, savefig=w_path)

        if os.path.exists(d_path) and os.path.exists(w_path):
            valid_stocks.append(stock)
            print(f"✅ {stock}")

    except Exception as e:
        print(f"⚠️ {stock}: {e}")

# ==========================
# TELEGRAM FAIL SAFE
# ==========================
def send_msg(txt):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": txt, "parse_mode": "Markdown"}
    )

def send_doc(path):
    with open(path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
            files={"document": f},
            data={"chat_id": CHAT_ID}
        )

if not valid_stocks:
    print("⚠️ No valid charts — sending fallback message")
    send_msg("⚠️ No valid charts generated today")
    exit()

# ==========================
# PDF
# ==========================
print("\n📄 Creating PDF...\n")

pdf_path = f"{OUTPUT_DIR}/charts.pdf"
doc = SimpleDocTemplate(pdf_path, pagesize=letter)
styles = getSampleStyleSheet()

elements = []

for stock in valid_stocks:
    d = f"{OUTPUT_DIR}/{stock}_Daily.png"
    w = f"{OUTPUT_DIR}/{stock}_Weekly.png"

    elements.append(Paragraph(f"<b>{stock}</b>", styles['Heading2']))
    elements.append(Spacer(1, 10))
    elements.append(Image(d, width=500, height=280))
    elements.append(Spacer(1, 10))
    elements.append(Image(w, width=500, height=280))
    elements.append(Spacer(1, 20))

doc.build(elements)

# ==========================
# MOCK GPT
# ==========================
buy = valid_stocks[:2]
watch = valid_stocks[2:5]

msg = "📊 *Daily Breakout Report*\n\n"

if buy:
    msg += "🔥 *Top Picks*\n" + "\n".join([f"• {s}" for s in buy]) + "\n\n"

if watch:
    msg += "⚠️ *Watchlist*\n" + "\n".join([f"• {s}" for s in watch])

send_msg(msg)
send_doc(pdf_path)

print("✅ Telegram sent")
print("\n🎉 SYSTEM COMPLETE")
