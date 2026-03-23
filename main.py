# ==============================================
# 🚀 ELITE SYSTEM (FINAL PRODUCTION VERSION)
# ==============================================

import os
import pandas as pd
import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt
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

    last_date = df.index[-1].date()

    if last_date != now.date():
        return df

    if now.time() < dtime(15, 30):
        return df.iloc[:-1]

    return df

# ==========================
# NSE STOCKS
# ==========================
def get_all_nse_stocks():
    indices = ["NIFTY 500", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"]
    headers = {"User-Agent": "Mozilla/5.0"}
    stocks = set()

    for index in indices:
        try:
            url = f"https://www.nseindia.com/api/equity-stockIndices?index={index.replace(' ', '%20')}"
            data = requests.get(url, headers=headers).json()
            for item in data['data']:
                if item['symbol'].isalpha():
                    stocks.add(item['symbol'] + ".NS")
        except:
            continue

    return list(stocks)

# ==========================
# STRICT FUNCTION (PARALLEL)
# ==========================
def process_stock_strict(stock):
    try:
        df = yf.download(stock, period="4mo", auto_adjust=True, progress=False)
        df = remove_incomplete_candle(df)

        if df is None or df.empty or len(df) < 80:
            return None

        df = df[['Open','High','Low','Close','Volume']].dropna()
        latest = df.iloc[-1]

        if latest['Close'] < 50 or latest['Volume'] < 200000:
            return None

        df['EMA50'] = df['Close'].ewm(span=50).mean()
        df['EMA200'] = df['Close'].ewm(span=200).mean()

        if not (latest['Close'] > df['EMA50'].iloc[-1] > df['EMA200'].iloc[-1]):
            return None

        base = df.tail(25)
        base_high = base['High'].max()
        base_low = base['Low'].min()

        if (base_high - base_low) / base_low * 100 > 18:
            return None

        base_vol = base['Volume'].mean()
        prior_vol = df['Volume'].tail(60).mean()

        if not (base_vol < prior_vol * 0.8 and latest['Volume'] > base['Volume'].tail(5).mean()):
            return None

        df['High_20'] = df['High'].rolling(20).max()
        if latest['Close'] < 0.9 * df['High_20'].iloc[-1]:
            return None

        df['Return_20'] = df['Close'].pct_change(20)
        if df['Return_20'].iloc[-1] < 0:
            return None

        if (latest['Close'] / base_low) > 1.25:
            return None

        return stock

    except:
        return None

# ==========================
# FALLBACK FUNCTION
# ==========================
def process_stock_fallback(stock):
    try:
        df = yf.download(stock, period="3mo", auto_adjust=True, progress=False)

        if df is None or df.empty or len(df) < 30:
            return None

        df = remove_incomplete_candle(df)
        df = df[['Open','High','Low','Close','Volume']].dropna()

        latest = df.iloc[-1]

        if latest['Close'] < 50:
            return None

        if latest['Close'] < 0.8 * df['High'].tail(20).max():
            return None

        return stock + " (F)"

    except:
        return None

# ==========================
# RUN
# ==========================
BASE_DIR = "charts"
os.makedirs(BASE_DIR, exist_ok=True)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUTPUT_DIR = os.path.join(BASE_DIR, f"run_{timestamp}")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"📁 Run folder: {OUTPUT_DIR}")

stocks_all = get_all_nse_stocks()
print(f"📊 Total stocks: {len(stocks_all)}")

# ==========================
# STRICT PARALLEL
# ==========================
shortlist = []

print("\n🔍 Running STRICT (Parallel)...\n")

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(process_stock_strict, s) for s in stocks_all]

    for f in as_completed(futures):
        res = f.result()
        if res:
            shortlist.append(res)
            print(f"✅ {res}")

print(f"\n📊 Strict: {len(shortlist)}")

# ==========================
# FALLBACK
# ==========================
if len(shortlist) == 0:

    print("\n⚠️ Running FALLBACK...\n")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_stock_fallback, s) for s in stocks_all]

        for f in as_completed(futures):
            res = f.result()
            if res:
                shortlist.append(res)
                print(f"🔁 {res}")

            if len(shortlist) >= 5:
                break

print(f"\n📊 Final Shortlist: {len(shortlist)}")

stocks = [s.replace(" (F)", "") for s in shortlist[:10]]

if not stocks:
    print("❌ No stocks found")
    exit()

# ==========================
# CHART GENERATION (SAFE)
# ==========================
def prepare(df):
    df = df[['Open','High','Low','Close','Volume']].dropna()
    return df

valid_stocks = []

print("\n📈 Generating charts...\n")

for stock in stocks:
    try:
        data = yf.download(stock, period="6mo", auto_adjust=True, progress=False)
        data = remove_incomplete_candle(data)

        if data is None or data.empty:
            continue

        df_d = prepare(data)
        df_w = prepare(data.resample('W').last())

        if df_d.empty or df_w.empty:
            continue

        d_path = f"{OUTPUT_DIR}/{stock}_Daily.png"
        w_path = f"{OUTPUT_DIR}/{stock}_Weekly.png"

        mpf.plot(df_d, type='candle', volume=True, savefig=d_path)
        mpf.plot(df_w, type='candle', volume=True, savefig=w_path)

        if os.path.exists(d_path) and os.path.exists(w_path):
            valid_stocks.append(stock)
            print(f"✅ {stock}")

    except Exception as e:
        print(f"⚠️ {stock}: {e}")

print(f"\n📊 Valid charts: {len(valid_stocks)}")

if not valid_stocks:
    print("❌ No valid charts")
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

    if not os.path.exists(d) or not os.path.exists(w):
        continue

    elements.append(Paragraph(f"<b>{stock}</b>", styles['Heading2']))
    elements.append(Spacer(1, 10))
    elements.append(Image(d, width=500, height=280))
    elements.append(Spacer(1, 10))
    elements.append(Image(w, width=500, height=280))
    elements.append(Spacer(1, 20))

doc.build(elements)
print("📄 PDF ready")

# ==========================
# MOCK GPT
# ==========================
print("\n🧪 MOCK GPT\n")

buy = valid_stocks[:2]
watch = valid_stocks[2:5]

# ==========================
# TELEGRAM
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

msg = "📊 *Daily Breakout Report*\n\n"

if buy:
    msg += "🔥 *Top Picks*\n" + "\n".join([f"• {s}" for s in buy]) + "\n\n"

if watch:
    msg += "⚠️ *Watchlist*\n" + "\n".join([f"• {s}" for s in watch])

send_msg(msg)
send_doc(pdf_path)

print("✅ Telegram sent")
print("\n🎉 SYSTEM COMPLETE")
