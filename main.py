# ==============================================
# 🚀 BREAKOUT BOT (FIXED + STABLE + IMPROVED)
# ==============================================

import os
import json
import time
import requests
import pandas as pd
import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt
from datetime import datetime
from openai import OpenAI
from matplotlib.patches import Patch
from reportlab.platypus import SimpleDocTemplate, Image, Spacer
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader

# ==========================
# CONFIG
# ==========================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CAPITAL = float(os.getenv("CAPITAL", 1000000))


# ==========================
# TELEGRAM
# ==========================
def send_message(text, buttons=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }

    if buttons:
        payload["reply_markup"] = json.dumps({"inline_keyboard": buttons})

    requests.post(url, data=payload)


def send_document(path, caption=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    with open(path, "rb") as f:
        requests.post(url, files={"document": f},
                      data={"chat_id": CHAT_ID, "caption": caption or ""})


# ==========================
# NSE STOCK FETCH (FIXED)
# ==========================
def get_stocks():
    headers = {"User-Agent": "Mozilla/5.0"}

    session = requests.Session()
    session.get("https://www.nseindia.com", headers=headers)

    indices = ["NIFTY 500", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"]

    stocks = set()

    for index in indices:
        try:
            url = f"https://www.nseindia.com/api/equity-stockIndices?index={index.replace(' ', '%20')}"
            res = session.get(url, headers=headers, timeout=10)
            data = res.json()

            for item in data.get("data", []):
                symbol = item.get("symbol")
                if symbol and symbol.isalpha():
                    stocks.add(symbol + ".NS")

            time.sleep(0.3)

        except Exception as e:
            print("NSE ERROR:", e)

    return list(stocks)


# ==========================
# DATA
# ==========================
def fetch(stock):
    df = yf.download(stock, period="6mo", auto_adjust=True, progress=False)
    df.index = pd.to_datetime(df.index)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df[['Open','High','Low','Close','Volume']].dropna()


def to_weekly(df):
    return df.resample('W').agg({
        'Open':'first','High':'max','Low':'min',
        'Close':'last','Volume':'sum'
    }).dropna()


# ==========================
# FILTER (IMPROVED)
# ==========================
def filter_stock(df):

    if len(df) < 50:
        return False

    df['EMA50'] = df['Close'].ewm(span=50).mean()
    df['EMA200'] = df['Close'].ewm(span=200).mean()

    cond1 = df.iloc[-1]['Close'] > df.iloc[-1]['EMA50'] > df.iloc[-1]['EMA200']

    recent = df.tail(20)
    base_range = (recent['High'].max() - recent['Low'].min()) / recent['Low'].min()
    cond2 = base_range < 0.15

    vol_avg = df['Volume'].rolling(20).mean()
    cond3 = df.iloc[-1]['Volume'] > 1.5 * vol_avg.iloc[-1]

    # breakout confirmation
    breakout = df['High'].shift(1).rolling(20).max()
    cond4 = df.iloc[-1]['Close'] >= breakout.iloc[-1]

    return cond1 and cond2 and cond3 and cond4


# ==========================
# TRADE LOGIC (FIXED)
# ==========================
def create_trade(df):

    recent = df.tail(20)

    entry = float(recent['High'].max())
    exit_price = float(recent['Low'].tail(5).min())

    risk_per_share = entry - exit_price

    if risk_per_share <= 0:
        return None

    risk_amt = CAPITAL * 0.0025
    qty_risk = int(risk_amt / risk_per_share)

    max_capital_per_trade = CAPITAL * 0.10
    qty_cap = int(max_capital_per_trade / entry)

    qty = min(qty_risk, qty_cap)

    if qty <= 0:
        return None

    return round(entry, 2), round(exit_price, 2), qty


# ==========================
# CHART ENGINE
# ==========================
def plot_chart(stock, df, save_path):

    df_weekly = to_weekly(df.copy())

    for ema in [10,21,50,200]:
        df[f'EMA{ema}'] = df['Close'].ewm(span=ema).mean()
        df_weekly[f'EMA{ema}'] = df_weekly['Close'].ewm(span=ema).mean()

    recent = df.tail(20)
    breakout = recent['High'].max()
    base_low = recent['Low'].min()
    base_high = recent['High'].max()

    mc = mpf.make_marketcolors(up='green', down='red')
    style = mpf.make_mpf_style(base_mpf_style='yahoo', marketcolors=mc)

    apds = [mpf.make_addplot(df[f'EMA{e}']) for e in [10,21,50,200]]
    apds_w = [mpf.make_addplot(df_weekly[f'EMA{e}']) for e in [10,21,50,200]]

    # DAILY
    fig1, ax1 = mpf.plot(df, type='candle', style=style, addplot=apds,
                         volume=True, returnfig=True)

    ax1[0].axhline(breakout, linestyle='--')
    ax1[0].axhspan(base_low, base_high, alpha=0.1)
    fig1.savefig("d.png")
    plt.close(fig1)

    # WEEKLY
    fig2, ax2 = mpf.plot(df_weekly, type='candle', style=style,
                         addplot=apds_w, volume=True, returnfig=True)

    fig2.savefig("w.png")
    plt.close(fig2)

    # MERGE
    fig = plt.figure(figsize=(10,8))
    a1 = fig.add_subplot(2,1,1)
    a1.imshow(plt.imread("d.png")); a1.axis('off')

    a2 = fig.add_subplot(2,1,2)
    a2.imshow(plt.imread("w.png")); a2.axis('off')

    plt.savefig(save_path)
    plt.close()


# ==========================
# PDF
# ==========================
def build_pdf(images, path):

    doc = SimpleDocTemplate(path, pagesize=letter)
    elements = []

    for img_path in images:
        img = ImageReader(img_path)
        w, h = img.getSize()
        scale = min(doc.width / w, doc.height * 0.9 / h)

        elements.append(Image(img_path, width=w*scale, height=h*scale))
        elements.append(Spacer(1, 10))

    doc.build(elements)


# ==========================
# GPT
# ==========================
def gpt_decision(pdf_path):

    file = client.files.create(file=open(pdf_path,"rb"), purpose="assistants")

    PROMPT = """
Return ONLY JSON.

Filter best breakout stocks.
Reject weak setups.

Format:
{
 "picks":[
  {"stock":"ABC.NS","score":8,"quality":"STRONG","reason":"...","entry_type":"Trend"}
 ]
}
"""

    res = client.responses.create(
        model="gpt-5-mini",
        input=[{
            "role":"user",
            "content":[
                {"type":"input_text","text":PROMPT},
                {"type":"input_file","file_id":file.id}
            ]
        }]
    )

    return res.output_text


def parse_gpt_output(output):
    try:
        return json.loads(output).get("picks", [])
    except:
        return []


# ==========================
# MAIN
# ==========================
def run():

    stocks = get_stocks()

    df_cache = {}
    shortlist = []

    for s in stocks:
        try:
            df = fetch(s)
            df_cache[s] = df

            if filter_stock(df):
                shortlist.append(s)

            time.sleep(0.2)

        except Exception as e:
            print("ERROR:", s, e)

    shortlist = shortlist[:10]

    folder = f"run_{datetime.now().strftime('%H%M%S')}"
    os.makedirs(folder, exist_ok=True)

    images = []
    trade_map = {}

    for s in shortlist:

        df = df_cache[s]

        img = f"{folder}/{s}.png"
        plot_chart(s, df.copy(), img)
        images.append(img)

        trade_map[s] = create_trade(df)

    pdf_path = f"{folder}/charts.pdf"
    build_pdf(images, pdf_path)

    send_document(pdf_path, "📄 Charts sent to GPT")

    output = gpt_decision(pdf_path)
    send_message(f"GPT RAW:\n{output[:1000]}")

    picks = parse_gpt_output(output)

    if not picks:
        picks = [{"stock": s, "score": 7, "quality": "Fallback", "reason": "Auto pick", "entry_type": "N/A"} for s in shortlist[:3]]

    for p in picks:

        s = p["stock"]
        trade = trade_map.get(s)

        if not trade:
            continue

        entry, exit_price, qty = trade

        msg = f"""
📈 *FINAL TRADE*

{s}
Score: {p['score']} ({p['quality']})

Entry: `{entry}`
Exit: `{exit_price}`
Qty: `{qty}`

Reason: {p['reason']}
"""

        buttons = [[{
            "text":"✅ Confirm Buy",
            "callback_data":f"BUY|{s}|{qty}|{exit_price}"
        }]]

        send_message(msg, buttons)


if __name__ == "__main__":
    run()
