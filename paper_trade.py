"""
PAPER-TRADE HARNESS for the SunPharma Dip-Buy swing system, with the full
failsafe layer. Run it daily (after market close). It:
  1. pulls the latest data,
  2. runs the mechanical state machine over history (reproducible),
  3. tells you the CURRENT position and the exact ACTION for the next session
     (entry/exit levels, disaster stop, and risk-based position size),
  4. appends a dated snapshot to output/paper_log.csv so a forward paper
     track record accumulates.

Usage:  python3 paper_trade.py [capital_rupees]   (default 10,00,000)
Rules (must match backtest Config C + failsafes):
  regime  Close>SMA200 | entry RSI<35 or SMA50 pullback | exit RSI>55 or 20d
  disaster stop: Close<SMA200 or -3xATR  (survival only, not for edge)
  sizing: risk 1% of capital over the disaster-stop distance; leverage cap 2x
"""
import sys, os, datetime as dt
import numpy as np, pandas as pd

CAP = float(sys.argv[1]) if len(sys.argv)>1 else 1_000_000
RISK_PCT, LEV_CAP = 0.01, 2.0
BASE=os.path.dirname(os.path.abspath(__file__))   # portable: works on laptop AND cloud
os.makedirs(f"{BASE}/data",exist_ok=True); os.makedirs(f"{BASE}/output",exist_ok=True)
CSV=f"{BASE}/data/sunpharma.csv"; LOG=f"{BASE}/output/paper_log.csv"

# ---- refresh data (fall back to cached CSV if offline) ----
try:
    import yfinance as yf
    d=yf.download("SUNPHARMA.NS",period="max",auto_adjust=True,progress=False)
    if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
    d=d.dropna(); d.to_csv(CSV); src="live"
except Exception as e:
    src=f"cached ({e})"
df=pd.read_csv(CSV,parse_dates=["Date"],index_col="Date")
c,h,l,o=df["Close"],df["High"],df["Low"],df["Open"]
def sma(s,n):return s.rolling(n).mean()
def rsi(s,n=14):
    dd=s.diff();up=dd.clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
    dn=(-dd.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    return 100-100/(1+up/dn.replace(0,np.nan))
def ema(s,n):return s.ewm(span=n,adjust=False).mean()
tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
df["sma50"]=sma(c,50);df["sma200"]=sma(c,200);df["rsi"]=rsi(c,14);df["atr"]=tr.rolling(14).mean()
df["macd_hist"]=(ema(c,12)-ema(c,26))-ema(ema(c,12)-ema(c,26),9)   # v2: momentum confirm
df=df.dropna(subset=["sma200","rsi","atr","macd_hist"])

# v2 entry: dip-buy in uptrend, confirmed by MACD histogram > 0 (avoids falling
# knives -- the #1 loser trait). Note: validate per stock; a few names (e.g.
# SUNPHARMA) backtest better WITHOUT this filter. Set USE_MACD=False for v1.
USE_MACD=True
up=df["Close"]>df["sma200"]
dip=(df["rsi"]<35)|((df["Close"]<=df["sma50"]*1.01)&(df["Close"]>=df["sma50"]*0.97))
entry=up&dip&((df["macd_hist"]>0) if USE_MACD else True)

# ---- mechanical state machine over full history ----
dates=list(df.index);n=len(dates)
O=df["Open"].values;C=df["Close"].values;R=df["rsi"].values;A=df["atr"].values;S200=df["sma200"].values
ent=entry.values
pos=None; i=0; trades=[]
while i<n-1:
    if pos is None and ent[i]:
        pos=dict(ei=i+1,ep=O[i+1],atr0=A[i]); i+=1; continue
    if pos is not None:
        j=i
        # disaster stop or reversion exit, evaluated on close of day j
        if C[j]<S200[j] or C[j]<=pos["ep"]-3*pos["atr0"]:
            pos["xi"]=j; pos["xr"]="DISASTER-STOP"; trades.append(pos); pos=None; i+=1; continue
        if R[j]>55:
            pos["xi"]=j; pos["xr"]="RSI-reversion"; trades.append(pos); pos=None; i+=1; continue
        if (j-pos["ei"])>=20:
            pos["xi"]=j; pos["xr"]="time-stop"; trades.append(pos); pos=None; i+=1; continue
    i+=1

last=n-1; today=dates[last]
px=C[last]; rsi_now=R[last]; atr_now=A[last]; sma200_now=S200[last]
macd_now=df["macd_hist"].values[last]
in_regime = px>sma200_now

def money(x): return f"Rs {x:,.0f}"

print("="*66)
print(f" SUNPHARMA PAPER-TRADE  (v2: dip-buy + MACD confirm)  |  {today.date()}")
print(f" data: {src}")
print("="*66)
print(f" Last close  {money(px)}    RSI(14) {rsi_now:5.1f}    ATR {atr_now:6.1f}    "
      f"MACD-hist {macd_now:+.1f} ({'up-momo OK' if macd_now>0 else 'falling-blocked'})")
print(f" SMA200 {money(sma200_now)}   ->  regime: {'UPTREND (tradeable)' if in_regime else 'BELOW SMA200 (stand aside)'}")

if pos is not None:
    held=last-pos["ei"]
    stop_px=max(sma200_now, pos["ep"]-3*pos["atr0"])
    print(f"\n POSITION: LONG since {dates[pos['ei']].date()} @ {money(pos['ep'])}  ({held} days held)")
    print(f"   unrealized: {(px/pos['ep']-1)*100:+.1f}%")
    print(f"   ACTION for next session:")
    if rsi_now>55:            print(f"     -> EXIT at next open (RSI {rsi_now:.0f} > 55, reversion done)")
    elif held>=20:           print(f"     -> EXIT at next open (20-day time-stop reached)")
    elif px<stop_px:         print(f"     -> EXIT at next open (disaster stop hit)")
    else:                    print(f"     -> HOLD. Disaster stop {money(stop_px)}. Exit when RSI>55 or day 20.")
else:
    print(f"\n POSITION: FLAT")
    sig = bool(ent[last])
    if sig and in_regime:
        stop_dist=3*atr_now
        risk_amt=CAP*RISK_PCT
        notional=min(risk_amt/(stop_dist/px), CAP*LEV_CAP)   # 1% risk, capped at 2x
        qty=int(notional/px)
        print(f"   ENTRY SIGNAL today ({'RSI<35' if rsi_now<35 else 'SMA50 pullback'} + MACD>0 confirmed).")
        print(f"   ACTION for next session:")
        print(f"     -> BUY at next open (~{money(px)})")
        print(f"     -> disaster stop  {money(px-stop_dist)}  ({stop_dist/px*100:.1f}% away)")
        print(f"     -> size for {money(CAP)} @ 1% risk: {money(notional)} notional  (~{qty} shares, {notional/CAP:.2f}x)")
        print(f"     -> tail hedge: buy a ~5% OTM protective put against this")
    else:
        # explain WHICH gate is blocking, so the wait is informative
        dip_now = bool((rsi_now<35) or (df["sma50"].values[last]*0.97<=px<=df["sma50"].values[last]*1.01))
        if not in_regime:      reason="below SMA200 (no uptrend regime)"
        elif not dip_now:      reason="no dip yet (need RSI<35 or a pullback to SMA50)"
        elif macd_now<=0:      reason="dip present but MACD<0 -> falling knife, momentum not up yet"
        else:                  reason="conditions not aligned"
        print(f"   No entry. Blocked by: {reason}.")

# ---- append forward paper snapshot (dedupe: skip if this bar already logged,
#      so unattended holiday/weekend re-runs don't create duplicate rows) ----
row=dict(date=str(today.date()), close=round(px,1), rsi=round(rsi_now,1),
         macd_hist=round(macd_now,1), regime="up" if in_regime else "down",
         state="LONG" if pos is not None else "FLAT",
         entry_signal=bool(ent[last]))
already=False
if os.path.exists(LOG):
    try: already = pd.read_csv(LOG)["date"].astype(str).iloc[-1]==row["date"]
    except Exception: already=False
if already:
    print(f"\n snapshot for {row['date']} already logged - skipped (no new bar).")
else:
    pd.DataFrame([row]).to_csv(LOG, mode="a", header=not os.path.exists(LOG), index=False)
    print(f"\n snapshot appended -> output/paper_log.csv")
print(f" (mechanical record: {len(trades)} closed paper trades in history)")
