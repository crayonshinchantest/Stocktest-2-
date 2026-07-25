"""
Build the weekend email digest from output/paper_log.csv.
Writes:
  output/email_body.html    - the HTML email body
  output/email_subject.txt  - the subject line
Robust to a single-stock log (current) or a future multi-stock log (a 'stock'
column). No network needed - summarises what the daily job already recorded.
"""
import os, pandas as pd, datetime as dt

BASE=os.path.dirname(os.path.abspath(__file__))
LOG=f"{BASE}/output/paper_log.csv"
os.makedirs(f"{BASE}/output",exist_ok=True)

def esc(x): return str(x).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

if not os.path.exists(LOG):
    body="<p>No paper-trade log yet — the daily job hasn't recorded any rows.</p>"
    subject="Weekly Paper-Trade — no data yet"
else:
    df=pd.read_csv(LOG)
    df["date"]=pd.to_datetime(df["date"])
    df=df.sort_values("date")
    last=df.iloc[-1]
    week_cut=df["date"].max()-pd.Timedelta(days=7)
    wk=df[df["date"]>=week_cut]
    signals=wk[wk["entry_signal"].astype(str).str.lower().isin(["true","1"])]

    state=str(last["state"]); regime=str(last.get("regime","?"))
    asof=last["date"].date()
    fired = len(signals)>0
    banner = ("#e8f5e9","#1b5e20",f"🟢 {len(signals)} ENTRY SIGNAL(S) this week — review below") if fired \
        else ("#eceff1","#37474f","⚪ No entry signals this week — system stood aside")

    # week table
    cols=[c for c in ["date","close","rsi","macd_hist","regime","state","entry_signal"] if c in wk.columns]
    rows_html=""
    for _,r in wk.iterrows():
        hot = str(r.get("entry_signal")).lower() in ("true","1")
        bg = "#fff8e1" if hot else "#ffffff"
        tds="".join(f'<td style="padding:6px 10px;border-bottom:1px solid #eee;'
                    f'font-variant-numeric:tabular-nums;">{esc(r[c].date() if c=="date" else r[c])}</td>' for c in cols)
        rows_html+=f'<tr style="background:{bg}">{tds}</tr>'
    ths="".join(f'<th style="padding:6px 10px;text-align:left;border-bottom:2px solid #ddd;'
                f'font:600 11px system-ui;text-transform:uppercase;color:#789;">{esc(c)}</th>' for c in cols)

    subject=f"📈 Weekly Paper-Trade — {state}{' • SIGNAL' if fired else ''} (as of {asof})"
    body=f"""<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:0 auto;color:#1a2530">
      <h2 style="margin:0 0 4px">SunPharma Paper-Trade — Weekly Digest</h2>
      <div style="color:#789;font-size:13px;margin-bottom:16px">Week ending {asof} · v2 dip-buy + MACD confirm</div>
      <div style="background:{banner[0]};color:{banner[1]};padding:14px 16px;border-radius:10px;font-weight:600;margin-bottom:18px">{banner[2]}</div>
      <table style="border-collapse:collapse;width:100%;font-size:14px;margin-bottom:8px"><thead><tr>{ths}</tr></thead><tbody>{rows_html}</tbody></table>
      <div style="font-size:13px;color:#556">
        <b>Current state:</b> {state} · regime <b>{regime}</b> · last close {esc(last.get('close','?'))} ·
        RSI {esc(last.get('rsi','?'))} · MACD-hist {esc(last.get('macd_hist','?'))}<br>
        <b>This week:</b> {len(wk)} sessions logged, {len(signals)} entry signal(s).
      </div>
      <p style="font-size:12px;color:#9aa7b2;margin-top:20px;border-top:1px solid #eee;padding-top:12px">
        Automated research digest. Educational backtest/paper-trade, not investment advice.
        Full log: output/paper_log.csv in your repo.</p>
    </div>"""

open(f"{BASE}/output/email_body.html","w").write(body)
open(f"{BASE}/output/email_subject.txt","w").write(subject)
print("subject:",subject)
print("wrote output/email_body.html")
