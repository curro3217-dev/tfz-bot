"""
EXPLORACIÓN #37: SPILLOVER MACRO (SPX, DXY) + KIMCHI PREMIUM (2026-07-04).

HIPÓTESIS PRE-ESPECIFICADAS:
  H1 (risk-on): semana del S&P 500 POSITIVA -> BTC sube la semana siguiente.
  H2 (dólar): semana del DXY POSITIVA -> BTC BAJA la semana siguiente.
  H3 (kimchi): prima de Upbit (BTC/KRW vs BTC/USDT×KRWUSD) con z>=+1 (90d solo
      pasado, episodios) -> demanda coreana -> long BTC 7d.
Alineación sin look-ahead: señal = semana macro que CIERRA el viernes; posición =
semana cripto del sábado 00:00 al sábado siguiente. IS <=2023 / OOS 2024-26.

Solo lectura. Uso: python explore_macro.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
import ccxt
import yfinance as yf
from curl_cffi import requests as cfr
from explore_friday_history import daily_history
from explore_premium import episodios

COST = (0.02 + 0.025) * 2


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    p = p[~np.isnan(p)]
    if len(p) < 10:
        return f"    {lbl:10} n {len(p):4d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:10} n {len(p):4d} | win {(p>0).mean()*100:4.0f}% | "
            f"exp {m:+.2f}%/sem [{lo:+.2f},{hi:+.2f}] {sig}")


def bloque(rows, titulo):
    print(f"\n[{titulo}]")
    print(stats_line([p for _, p in rows], "TOTAL"))
    print(stats_line([p for y, p in rows if y <= 2023], "IS <=23"))
    print(stats_line([p for y, p in rows if y >= 2024], "OOS 24-26"))


def main():
    s = cfr.Session(verify=False, impersonate="chrome")
    macro = yf.download(["^GSPC", "DX-Y.NYB", "KRW=X"], start="2018-01-01",
                        progress=False, auto_adjust=True, session=s)["Close"]
    ex = ccxt.binance({"enableRateLimit": True, "timeout": 20000})
    if os.environ.get("INSECURE_SSL") == "1":
        ex.verify = False
    ex.load_markets()
    c = daily_history(ex, "BTC/USDT")
    btc = pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): x[4] for x in c})

    # H1/H2: semana macro (cierre viernes) -> semana cripto (sáb->sáb)
    wk = macro.resample("W-FRI").last()
    for nombre, col, sgn in (("H1 S&P risk-on (seguir)", "^GSPC", 1),
                             ("H2 DXY (contrario)", "DX-Y.NYB", -1)):
        mom = wk[col].pct_change()
        rows = []
        for t, v in mom.items():
            if pd.isna(v) or v == 0:
                continue
            t0 = t + pd.Timedelta(days=1)          # sábado
            t1 = t0 + pd.Timedelta(days=7)
            if t0 not in btc.index or t1 not in btc.index:
                continue
            pnl = sgn * np.sign(v) * (btc[t1] - btc[t0]) / btc[t0] * 100 - COST
            rows.append((t.year, float(pnl)))
        bloque(rows, nombre)

    # H3: kimchi premium (Upbit BTC/KRW)
    try:
        up = ccxt.upbit({"enableRateLimit": True, "timeout": 20000})
        if os.environ.get("INSECURE_SSL") == "1":
            up.verify = False
        up.load_markets()
        ck = daily_history(up, "BTC/KRW")
        krw = pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): x[4]
                         for x in ck})
        fx = macro["KRW=X"]                        # USD/KRW
        kimchi = (krw / fx.reindex(krw.index).ffill() / btc - 1) * 100
        kimchi = kimchi.dropna()
        z = ((kimchi - kimchi.rolling(90).mean().shift(1))
             / kimchi.rolling(90).std().shift(1)).dropna()
        print(f"\nkimchi: {len(z)} días desde {z.index[0].date()} | hoy "
              f"{kimchi.iloc[-1]:+.2f}% (z={z.iloc[-1]:+.2f})")
        rows = []
        for t in episodios(z, lambda v: v >= 1):
            t1 = t + pd.Timedelta(days=7)
            if t in btc.index and t1 in btc.index:
                rows.append((t.year, (btc[t1] - btc[t]) / btc[t] * 100 - COST))
        bloque(rows, "H3 kimchi z>=+1 -> long BTC 7d")
    except Exception as e:
        print(f"\nkimchi no disponible: {e}")


if __name__ == "__main__":
    main()
