import pandas as pd
import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt

# ==========================
# FETCH DATA
# ==========================
def fetch(stock):
    df = yf.download(stock, period="6mo", auto_adjust=True, progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df[['Open','High','Low','Close','Volume']].dropna()

# ==========================
# WEEKLY
# ==========================
def to_weekly(df):
    return df.resample('W').agg({
        'Open':'first',
        'High':'max',
        'Low':'min',
        'Close':'last',
        'Volume':'sum'
    }).dropna()

# ==========================
# ADD EMA
# ==========================
def add_ema(df):
    df['EMA10'] = df['Close'].ewm(span=10).mean()
    df['EMA21'] = df['Close'].ewm(span=21).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()
    df['EMA200'] = df['Close'].ewm(span=200).mean()
    return df

# ==========================
# CORE PLOT
# ==========================
def plot_chart(stock):

    df = fetch(stock)
    df = add_ema(df)

    df_weekly = to_weekly(df.copy())
    df_weekly = add_ema(df_weekly)

    # ======================
    # LOGIC
    # ======================
    recent = df.tail(20)

    breakout = recent['High'].max()
    base_low = recent['Low'].min()
    base_high = recent['High'].max()

    df['vol_avg'] = df['Volume'].rolling(20).mean()
    df['vol_spike'] = df['Volume'] > 1.5 * df['vol_avg']

    trend = "Uptrend" if df.iloc[-1]['EMA50'] > df.iloc[-1]['EMA200'] else "Downtrend"

    # ======================
    # FIGURE
    # ======================
    fig = plt.figure(figsize=(10, 8))

    # ----------------------
    # DAILY
    # ----------------------
    ax1 = fig.add_subplot(2,1,1)

    apds = [
        mpf.make_addplot(df['EMA10'], ax=ax1, color='purple'),
        mpf.make_addplot(df['EMA21'], ax=ax1, color='cyan'),
        mpf.make_addplot(df['EMA50'], ax=ax1, color='blue'),
        mpf.make_addplot(df['EMA200'], ax=ax1, color='orange'),
    ]

    mpf.plot(df,
             type='candle',
             ax=ax1,
             style='yahoo',
             addplot=apds,
             volume=False)

    # Breakout line
    ax1.axhline(breakout, linestyle='--', color='green', linewidth=1)

    # Base box
    ax1.axhspan(base_low, base_high, alpha=0.15, color='grey')

    # Trend label
    ax1.text(0.01, 0.95, f"{stock} - DAILY ({trend})",
             transform=ax1.transAxes,
             fontsize=10,
             verticalalignment='top')

    ax1.legend(['EMA10','EMA21','EMA50','EMA200'])

    # ----------------------
    # WEEKLY
    # ----------------------
    ax2 = fig.add_subplot(2,1,2)

    apds2 = [
        mpf.make_addplot(df_weekly['EMA10'], ax=ax2, color='purple'),
        mpf.make_addplot(df_weekly['EMA21'], ax=ax2, color='cyan'),
        mpf.make_addplot(df_weekly['EMA50'], ax=ax2, color='blue'),
        mpf.make_addplot(df_weekly['EMA200'], ax=ax2, color='orange'),
    ]

    mpf.plot(df_weekly,
             type='candle',
             ax=ax2,
             style='yahoo',
             addplot=apds2,
             volume=True)

    ax2.text(0.01, 0.95, f"{stock} - WEEKLY",
             transform=ax2.transAxes,
             fontsize=10,
             verticalalignment='top')

    ax2.legend(['EMA10','EMA21','EMA50','EMA200'])

    # ----------------------
    # SAVE
    # ----------------------
    plt.tight_layout()
    plt.savefig(f"{stock}.png")
    plt.close()

    print(f"✅ Chart saved: {stock}.png")

# ==========================
# TEST
# ==========================
if __name__ == "__main__":
    plot_chart("RELIANCE.NS")
