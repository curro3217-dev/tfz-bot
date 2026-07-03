"""
EXPLORACIÓN #17: FEAR & GREED contrarian (2026-07-03).

Índice diario de alternative.me (2018-02 -> hoy, gratis). HIPÓTESIS PRE-ESPECIFICADAS
(el folclore clásico, fijado antes de mirar):
  H1: MIEDO extremo (valor <= 20) -> LONG BTC los siguientes 7 días
  H2: CODICIA extrema (valor >= 80) -> SHORT BTC los siguientes 7 días
Episodios NO solapados: solo cuenta el PRIMER día que se entra en la zona extrema
(una racha = una señal). Neto de costes MEXC. IS 2018-2023 / OOS 2024-2026.
También se mira ETH con las mismas señales (el índice es de mercado).

Solo lectura. Uso: python explore_feargreed.py
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


def fng():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    r = urllib.request.urlopen("https://api.alternative.me/fng/?limit=0&format=json",
                               context=ctx, timeout=30)
    d = json.loads(r.read())["data"]
    return pd.Series({pd.to_datetime(int(x["timestamp"]), unit="s").normalize():
                      float(x["value"]) for x in d}).sort_index()


def episodios(v, cond):
    """Primer día de cada racha donde cond(valor) es True."""
    mask = cond(v)
    return v.index[mask & ~mask.shift(1, fill_value=False)]


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
    v = fng()
    print(f"F&G: {len(v)} días, {v.index[0].date()} -> {v.index[-1].date()}")
    ex = ccxt.binance({"enableRateLimit": True, "timeout": 20000})
    if os.environ.get("INSECURE_SSL") == "1":
        ex.verify = False
    ex.load_markets()
    for coin in ("BTC", "ETH"):
        c = daily_history(ex, f"{coin}/USDT")
        px = pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): x[4] for x in c})
        print(f"\n=== {coin} (episodios no solapados, hold {HOLD_D}d, neto) ===")
        for nombre, idx, sgn in (
                ("H1 miedo<=20 LONG", episodios(v, lambda s: s <= 20), 1),
                ("H2 codicia>=80 SHORT", episodios(v, lambda s: s >= 80), -1)):
            pnls = []
            for t in idx:
                t_exit = t + pd.Timedelta(days=HOLD_D)
                if t not in px.index or t_exit not in px.index:
                    continue
                pnls.append({"y": t.year,
                             "p": sgn * (px[t_exit] - px[t]) / px[t] * 100 - COST})
            df = pd.DataFrame(pnls)
            if not len(df):
                print(f"  {nombre}: sin episodios con precio")
                continue
            print(f"  {nombre}:")
            print(stats_line(df["p"].values, "TOTAL"))
            print(stats_line(df[df.y <= 2023]["p"].values, "IS 2018-23"))
            print(stats_line(df[df.y >= 2024]["p"].values, "OOS 2024-26"))


if __name__ == "__main__":
    main()
