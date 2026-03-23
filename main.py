# ==============================================
# 🚀 ELITE SYSTEM: NSE → SCREENER → PDF → GPT → TELEGRAM
# ==============================================

import os
import pandas as pd
import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt
import time
from datetime import datetime, time as dtime
import pytz
import requests
from openai import OpenAI

# PDF
from reportlab.platypus import SimpleDocTemplate, Image, Spacer, Paragraph
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet

# ==========================
# 🔑 API
# ==========================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==========================
# 🧠 REMOVE INCOMPLETE CANDLE
# ==========================
def remove_incomplete_candle(df):

    if df is None or df.empty:
        return df

    india = pytz.timezone("Asia/Kolkata")
    now = datetime.now(india)

    last_date = df.index[-1].date()

    if last_date != now.date():
        return df

    market_close = dtime(15, 30)

    if now.time() < market_close:
        return df.iloc[:-1]

    return df

# ==========================
# FETCH NSE STOCKS
# ==========================
def get_all_nse_stocks():
    indices = ["NIFTY 500", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"]
    headers = {"User-Agent": "Mozilla/5.0"}

    stocks = set()

    for index in indices:
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={index.replace(' ', '%20')}"
        try:
            data = requests.get(url, headers=headers).json()
            for item in data['data']:
                symbol = item['symbol']
                if symbol.isalpha():
                    stocks.add(symbol + ".NS")
        except:
            continue

    return list(stocks)

# ==========================
# CREATE FOLDER
# ==========================
BASE_DIR = "charts"
os.makedirs(BASE_DIR, exist_ok=True)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUTPUT_DIR = os.path.join(BASE_DIR, f"run_{timestamp}")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"📁 Run folder: {OUTPUT_DIR}")

# ==========================
# 🚀 ELITE SCREENER
# ==========================
STOCK_UNIVERSE = get_all_nse_stocks()
print(f"📊 Total stocks: {len(STOCK_UNIVERSE)}")

shortlist = []

print("\n🔍 Running ELITE Screener...\n")

for stock in STOCK_UNIVERSE:

    try:
        df = yf.download(stock, period="4mo", auto_adjust=True, progress=False)
        df = remove_incomplete_candle(df)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty or len(df) < 80:
            continue

        df = df[['Open','High','Low','Close','Volume']].dropna()
        latest = df.iloc[-1]

        # Liquidity
        if latest['Close'] < 50 or latest['Volume'] < 200000:
            continue

        # Trend
        df['EMA50'] = df['Close'].ewm(span=50).mean()
        df['EMA200'] = df['Close'].ewm(span=200).mean()

        if not (latest['Close'] > df['EMA50'].iloc[-1] > df['EMA200'].iloc[-1]):
            continue

        # Base
        base = df.tail(25)
        base_high = base['High'].max()
        base_low = base['Low'].min()

        range_pct = (base_high - base_low) / base_low * 100
        if range_pct > 18:
            continue

        if len(base) < 15:
            continue

        # Volume (IFP)
        base_vol = base['Volume'].mean()
        prior_vol = df['Volume'].tail(60).mean()

        vol_dry = base_vol < prior_vol * 0.8
        vol_expand = latest['Volume'] > base['Volume'].tail(5).mean()

        if not (vol_dry and vol_expand):
            continue

        # Breakout proximity
        df['High_20'] = df['High'].rolling(20).max()
        if latest['Close'] < 0.9 * df['High_20'].iloc[-1]:
            continue

        # Relative strength
        df['Return_20'] = df['Close'].pct_change(20)
        if df['Return_20'].iloc[-1] < 0:
            continue

        # Avoid extended
        if (latest['Close'] / base_low) > 1.25:
            continue

        # Pullback quality
        pullback = (base_high - latest['Close']) / base_high
        if pullback > 0.15:
            continue

        shortlist.append(stock)
        print(f"✅ {stock}")

        time.sleep(0.05)

    except:
        continue

print(f"\n📊 Shortlisted: {len(shortlist)}")

stocks = shortlist[:10]

if not stocks:
    print("❌ No stocks found")
    exit()

# ==========================
# PREP
# ==========================
def prepare_data(df):

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[['Open','High','Low','Close','Volume']].dropna()

    df['EMA10'] = df['Close'].ewm(span=10).mean()
    df['EMA21'] = df['Close'].ewm(span=21).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()
    df['EMA200'] = df['Close'].ewm(span=200).mean()

    return df

def resample_weekly(df):
    return df.resample('W').agg({
        'Open':'first','High':'max','Low':'min',
        'Close':'last','Volume':'sum'
    }).dropna()

# ==========================
# PLOT
# ==========================
def plot_chart(df, stock, timeframe):

    apds, labels = [], []

    for ema, color in zip(
        ['EMA10','EMA21','EMA50','EMA200'],
        ['purple','cyan','blue','orange']
    ):
        if df[ema].notna().sum() > 5:
            apds.append(mpf.make_addplot(df[ema], color=color))
            labels.append(ema)

    filename = f"{OUTPUT_DIR}/{stock}_{timeframe}.png"

    fig, axes = mpf.plot(
        df, type='candle', style='yahoo',
        volume=True, addplot=apds,
        returnfig=True
    )

    if labels:
        axes[0].legend(labels)

    fig.savefig(filename)
    plt.close(fig)

# ==========================
# GENERATE CHARTS
# ==========================
print("\n📈 Generating charts...\n")

for stock in stocks:
    try:
        data = yf.download(stock, period="6mo", auto_adjust=True, progress=False)
        data = remove_incomplete_candle(data)

        df_daily = prepare_data(data)
        plot_chart(df_daily, stock, "Daily")

        df_weekly = resample_weekly(data)
        df_weekly = prepare_data(df_weekly)
        plot_chart(df_weekly, stock, "Weekly")

        time.sleep(0.1)

    except:
        continue

print("✅ Charts ready")

# ==========================
# PDF
# ==========================
print("\n📄 Creating PDF...\n")

pdf_path = f"{OUTPUT_DIR}/charts.pdf"

doc = SimpleDocTemplate(pdf_path, pagesize=letter)
styles = getSampleStyleSheet()

elements = []

for stock in stocks:

    elements.append(Paragraph(f"<b>{stock}</b>", styles['Heading2']))
    elements.append(Spacer(1, 10))

    daily = f"{OUTPUT_DIR}/{stock}_Daily.png"
    weekly = f"{OUTPUT_DIR}/{stock}_Weekly.png"

    if os.path.exists(daily):
        elements.append(Image(daily, width=500, height=280))
        elements.append(Spacer(1, 10))

    if os.path.exists(weekly):
        elements.append(Image(weekly, width=500, height=280))
        elements.append(Spacer(1, 20))

doc.build(elements)

print(f"📄 PDF created: {pdf_path}")

# ==========================
# GPT
# ==========================
print("\n🚀 Sending PDF to GPT...\n")

file = client.files.create(file=open(pdf_path, "rb"), purpose="assistants")

PROMPT = """
You are a professional breakout-base trading system.

STRICT SYSTEM:
Chartink → Focus → Trade → Base → Entry Pattern → Execute

You MUST follow this system exactly. No deviations.

You are analyzing ONLY the charts provided in the PDF.

---

STEP 1 — WEEKLY TREND

Classify:
- Uptrend / Sideways / Downtrend

---

STEP 2 — BASE ANALYSIS (MANDATORY SCORING)

Base = accumulation zone.

Score each:

1. Trend (0–2)
- Price > EMA50 > EMA200 → 2
- Near EMA200 → 1
- Else → 0 (Reject)

2. Structure Tightness (0–3)
- <10% → 3
- 10–20% → 2
- 20–30% → 1
- >30% → 0 (Reject)

3. Volume (0–2)
- Contraction in base + expansion near highs → 2
- Stable → 1
- Weak → 0

4. Pullback Quality (0–2)
- Shallow & controlled → 2
- Moderate → 1
- Sharp → 0

5. EMA Behavior (0–1)
- EMA50 flat/rising → 1
- Falling → 0

Base Score = total (0–10)

Convert:
- 8–10 → Base = 3 (Tight)
- 6–7 → Base = 2
- 4–5 → Base = 1
- ≤3 → Base = 0 (Reject)

---

STEP 3 — VOLUME

- Strong → 3
- Moderate → 2
- Weak → 1

---

STEP 4 — SETUP

- Breakout → 3
- Retest → 3
- Pullback → 2
- None → 0

---

STEP 5 — PATTERN (MANDATORY)

Allowed:
- Trend Bar → 3
- Pin Bar → 2
- HH-HL → 2
- Inside Bar → 2

If no pattern → DO NOT BUY

---

STEP 6 — ENTRY

Entry:
- Above pattern high

Stop Loss:
- Below pattern low OR base low

---

STEP 7 — STAGE SCORING

- Base 1 → 2
- Base 2 → 2
- Base 3 → 1
- Late → 0

---

STEP 8 — FINAL SCORE

Score = Base + Stage + Volume + Setup + Pattern
(Max = 14)

---

STEP 9 — DECISION RULE

- Base = 0 → AVOID
- Pattern = 0 → DO NOT BUY

Score:
- ≥11 → BUY
- 8–10 → WATCH
- ≤7 → AVOID

---

STEP 10 — OUTPUT FORMAT (STRICT)

📊 Summary Table

Stock | Trend | Stage | Base | Volume | Setup | Pattern | Score | Decision | Confidence

---

🎯 Execution Table

Stock | Action | Entry | Stop Loss | Setup | Pattern | Score

---

✅ Final Picks

Primary: Top 1–2 stocks  
Secondary: Optional 1  

---

⚠️ Notes

- Max 4 bullets
- Why selected
- Why rejected

---

STRICT RULES:

- No base → No trade
- No pattern → No BUY
- Prefer tight base
- Prefer early stage
- Avoid extended stocks

---

IMPORTANT:

Analyze ONLY the charts provided.
Do NOT ask for more charts.
Do NOT give generic explanation.
Follow scoring strictly.
"""

response = client.responses.create(
    model="gpt-4.1-mini",
    input=[{
        "role": "user",
        "content": [
            {"type": "input_text", "text": PROMPT},
            {"type": "input_file", "file_id": file.id}
        ]
    }]
)

print("\n📊 GPT OUTPUT:\n")
print(response.output_text)

# ==========================
# TELEGRAM
# ==========================
print("\n📲 Sending to Telegram...\n")

def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=payload)

def send_document(file_path):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    with open(file_path, "rb") as f:
        requests.post(url, files={"document": f}, data={"chat_id": CHAT_ID})

msg = "📊 *Daily Breakout Report*\n\n"

if "Final Picks" in response.output_text:
    msg += response.output_text.split("Final Picks")[-1][:1000]
else:
    msg += response.output_text[:1000]

send_message(msg)
send_document(pdf_path)

print("✅ Telegram sent!")

print("\n🎉 ELITE SYSTEM RUN COMPLETE")
