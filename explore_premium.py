"""
EXPLORACIÓN #20: PRIMA DE COINBASE (demanda USA) (2026-07-03).

Prima = precio BTC en Coinbase (USD, institucional/retail USA) vs Binance (USDT,
resto del mundo). Literatura y folclore: prima alta = demanda americana fuerte.
HIPÓTESIS PRE-ESPECIFICADAS (episodios no solapados, z-score móvil 90d SOLO pasado):
  H1: z >= +1 (prima anormalmente alta)  -> LONG BTC 7 días
  H2: z <= -1 (descuento anormal)        -> SHORT BTC 7 días
Neto de costes MEXC. IS 2018-2023 / OOS 2024-2026.

Solo lectura. Uso: python explore_premium.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
import ccxt
from explore_friday_history import daily_history

COST = (0.02 + 0.025) * 2
HOLD_D = 7


def cierres(ex_name, sym):
    ex = getattr(ccxt, ex_name)({"enableRateLimit": True, "timeout": 20000})
    if os.environ.get("INSECURE_SSL") == "1":
        ex.verify = False
    ex.load_markets()
    c = daily_history(ex, sym)
    return pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): x[4] for x in c})


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
    cb = cierres("coinbaseexchange", "BTC/USD")
    bn = cierres("binance", "BTC/USDT")
    df = pd.DataFrame({"cb": cb, "bn": bn}).dropna()
    prem = (df["cb"] / df["bn"] - 1) * 100
    mu = prem.rolling(90).mean().shift(1)
    sd = prem.rolling(90).std().shift(1)
    z = ((prem - mu) / sd).dropna()
    print(f"prima Coinbase: {len(z)} días, {z.index[0].date()} -> {z.index[-1].date()} "
          f"| media {prem.mean():+.4f}% | hoy z={z.iloc[-1]:+.2f}")
    px = df["bn"]
    for nombre, idx, sgn in (
            ("H1 z>=+1 LONG", episodios(z, lambda s: s >= 1), 1),
            ("H2 z<=-1 SHORT", episodios(z, lambda s: s <= -1), -1)):
        pnls = []
        for t in idx:
            t_exit = t + pd.Timedelta(days=HOLD_D)
            if t not in px.index or t_exit not in px.index:
                continue
            pnls.append({"y": t.year,
                         "p": sgn * (px[t_exit] - px[t]) / px[t] * 100 - COST})
        d = pd.DataFrame(pnls)
        print(f"  {nombre}:")
        print(stats_line(d["p"].values, "TOTAL"))
        print(stats_line(d[d.y <= 2023]["p"].values, "IS 2018-23"))
        print(stats_line(d[d.y >= 2024]["p"].values, "OOS 2024-26"))


if __name__ == "__main__":
    main()
