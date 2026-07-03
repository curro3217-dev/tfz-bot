"""
EXPLORACIÓN #21: ACTIVIDAD ON-CHAIN de BTC (blockchain.com, gratis) (2026-07-03).

Literatura (uso de la red -> valor): el crecimiento de la actividad on-chain
anticiparía el precio. HIPÓTESIS PRE-ESPECIFICADAS (mismo esqueleto que #20:
z-score móvil 90d del crecimiento a 30 días, SOLO pasado, episodios no solapados):
  H1: z >= +1 (actividad acelerando)  -> LONG BTC 7 días
  H2: z <= -1 (actividad frenando)    -> SHORT BTC 7 días
Series: direcciones activas y nº de transacciones (se reportan por separado).
Neto de costes MEXC. IS 2018-2023 / OOS 2024-2026.

Solo lectura. Uso: python explore_onchain.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import json
import ssl
import urllib.request
import numpy as np
import pandas as pd
import ccxt
from explore_friday_history import daily_history

COST = (0.02 + 0.025) * 2
HOLD_D = 7
SERIES = {"direcciones activas": "n-unique-addresses",
          "transacciones/día": "n-transactions"}


def chart(nombre):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    url = (f"https://api.blockchain.info/charts/{nombre}"
           f"?timespan=9years&format=json&sampled=false")
    r = urllib.request.urlopen(url, context=ctx, timeout=30)
    d = json.loads(r.read())["values"]
    return pd.Series({pd.to_datetime(x["x"], unit="s").normalize(): float(x["y"])
                      for x in d}).sort_index()


def episodios(z, cond):
    mask = cond(z)
    return z.index[mask & ~mask.shift(1, fill_value=False)]


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    if len(p) < 10:
        return f"    {lbl:14} n {len(p):3d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:14} n {len(p):3d} | win {(p>0).mean()*100:4.0f}% | "
            f"exp {m:+.2f}%/{HOLD_D}d [{lo:+.2f},{hi:+.2f}] {sig}")


def main():
    ex = ccxt.binance({"enableRateLimit": True, "timeout": 20000})
    if os.environ.get("INSECURE_SSL") == "1":
        ex.verify = False
    ex.load_markets()
    c = daily_history(ex, "BTC/USDT")
    px = pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): x[4] for x in c})

    for etiqueta, serie_id in SERIES.items():
        s = chart(serie_id)
        # suavizar (media 7d) y crecimiento a 30 días
        g30 = s.rolling(7).mean().pct_change(30) * 100
        mu = g30.rolling(90).mean().shift(1)
        sd = g30.rolling(90).std().shift(1)
        z = ((g30 - mu) / sd).dropna()
        print(f"\n=== {etiqueta} ({len(s)} días, {s.index[0].date()} -> "
              f"{s.index[-1].date()}) ===")
        for nombre, idx, sgn in (
                ("H1 z>=+1 LONG", episodios(z, lambda v: v >= 1), 1),
                ("H2 z<=-1 SHORT", episodios(z, lambda v: v <= -1), -1)):
            pnls = []
            for t in idx:
                t_exit = t + pd.Timedelta(days=HOLD_D)
                if t not in px.index or t_exit not in px.index:
                    continue
                pnls.append({"y": t.year,
                             "p": sgn * (px[t_exit] - px[t]) / px[t] * 100 - COST})
            d = pd.DataFrame(pnls)
            if not len(d):
                print(f"  {nombre}: sin episodios")
                continue
            print(f"  {nombre}:")
            print(stats_line(d["p"].values, "TOTAL"))
            print(stats_line(d[d.y <= 2023]["p"].values, "IS 2018-23"))
            print(stats_line(d[d.y >= 2024]["p"].values, "OOS 2024-26"))


if __name__ == "__main__":
    main()
