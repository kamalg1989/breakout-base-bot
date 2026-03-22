# ==============================================
# FULL AUTOMATION: CSV → CHARTS → GPT ANALYSIS
# ==============================================

import os
import pandas as pd
import yfinance as yf
import mplfinance as mpf
import zipfile
import matplotlib.pyplot as plt
import shutil
from datetime import datetime
import glob
from openai import OpenAI

# ==========================
# 🔑 SET YOUR API KEY
# ==========================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ==========================
# CREATE RUN FOLDER
# ==========================
BASE_DIR = "charts"
os.makedirs(BASE_DIR, exist_ok=True)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUTPUT_DIR = os.path.join(BASE_DIR, f"run_{timestamp}")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"📁 Run folder: {OUTPUT_DIR}")

# ==========================
# AUTO LOAD CSV
# ==========================
csv_files = glob.glob("*.csv")

if not csv_files:
    raise FileNotFoundError("❌ No CSV file found")

CSV_FILE = csv_files[0]
print(f"📄 Using CSV: {CSV_FILE}")

df_csv = pd.read_csv(CSV_FILE)

stocks = df_csv["Symbol"].dropna().tolist()
stocks = [s.strip() + ".NS" for s in stocks]

# ==========================
# DATA PREP
# ==========================
def prepare_data(df):

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required_cols = ['Open','High','Low','Close','Volume']
    if not all(col in df.columns for col in required_cols):
        return None

    df = df[required_cols].dropna()

    if df.empty:
        return None

    # EMAs
    df['EMA10'] = df['Close'].ewm(span=10).mean()
    df['EMA21'] = df['Close'].ewm(span=21).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()
    df['EMA200'] = df['Close'].ewm(span=200).mean()

    return df

# ==========================
# WEEKLY
# ==========================
def resample_weekly(df):
    return df.resample('W').agg({
        'Open':'first',
        'High':'max',
        'Low':'min',
        'Close':'last',
        'Volume':'sum'
    }).dropna()

# ==========================
# PLOT CHART
# ==========================
def plot_chart(df, stock, timeframe):

    if df is None or df.empty:
        print(f"Skipping {stock} ({timeframe})")
        return

    apds = []

    if df['EMA10'].notna().sum() > 5:
        apds.append(mpf.make_addplot(df['EMA10'], color='purple'))

    if df['EMA21'].notna().sum() > 5:
        apds.append(mpf.make_addplot(df['EMA21'], color='cyan'))

    if df['EMA50'].notna().sum() > 5:
        apds.append(mpf.make_addplot(df['EMA50'], color='blue'))

    if df['EMA200'].notna().sum() > 5:
        apds.append(mpf.make_addplot(df['EMA200'], color='orange'))

    filename = f"{OUTPUT_DIR}/{stock}_{timeframe}.png"

    fig, axes = mpf.plot(
        df,
        type='candle',
        style='yahoo',
        volume=True,
        addplot=apds if apds else None,
        title=f"{stock} {timeframe}",
        figsize=(12,8),
        returnfig=True
    )

    axes[0].legend(
        ['EMA10', 'EMA21', 'EMA50', 'EMA200'],
        loc='upper left'
    )

    fig.savefig(filename)
    plt.close(fig)

# ==========================
# GENERATE CHARTS
# ==========================
for stock in stocks:

    print(f"Processing {stock}...")

    try:
        data = yf.download(stock, period="6mo", auto_adjust=True)

        if data.empty:
            continue

        df_daily = prepare_data(data)
        plot_chart(df_daily, stock, "Daily")

        df_weekly = resample_weekly(data)
        df_weekly = prepare_data(df_weekly)
        plot_chart(df_weekly, stock, "Weekly")

    except Exception as e:
        print(f"Error {stock}: {e}")
        continue

print("\n✅ Charts generated!")

# ==========================
# CREATE ZIP
# ==========================
zip_name = f"{OUTPUT_DIR}.zip"

with zipfile.ZipFile(zip_name, 'w') as z:
    for f in os.listdir(OUTPUT_DIR):
        z.write(os.path.join(OUTPUT_DIR, f), arcname=f"charts/{f}")

print(f"📦 ZIP ready: {zip_name}")

# ==========================
# SEND TO GPT
# ==========================
print("🚀 Sending to GPT...")

file = client.files.create(
    file=open(zip_name, "rb"),
    purpose="assistants"
)

# 🔥 YOUR FULL SYSTEM PROMPT (IMPORTANT)
PROMPT = """
You are a professional stock trading assistant.

Analyze the uploaded charts using breakout-base strategy.

Give STRICT output:

1. Summary Table:
Stock | Trend | Stage | Base | Volume | Setup | Pattern | Score | Decision

2. Execution Table:
Stock | Action | Entry | Stop Loss | Setup | Pattern | Score

3. Final Picks (Top 2)

Rules:
- Focus on base quality
- Prefer tight base
- Only valid patterns
- No pattern → no buy
"""

response = client.responses.create(
    model="gpt-4.1",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": PROMPT},
                {"type": "input_file", "file_id": file.id}
            ]
        }
    ]
)

print("\n📊 GPT OUTPUT:\n")
print(response.output_text)

# ==========================
# SAVE OUTPUT
# ==========================
with open(f"{OUTPUT_DIR}/gpt_output.txt", "w") as f:
    f.write(response.output_text)

print("\n✅ Output saved!")
