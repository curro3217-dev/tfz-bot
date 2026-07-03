"""
EXPLORACIÓN #31: PROXIMIDAD AL MÁXIMO DE 52 SEMANAS (George-Hwang) (2026-07-03).

Anomalía documentada en acciones: los activos CERCA de su máximo de 52 semanas
siguen subiendo (anclaje: la gente vende "porque está caro" y se equivoca).
Construcción semanal (lunes): ratio = cierre / máximo 252d (SOLO pasado);
LONG top-5 del universo, SHORT bottom-5, mantener 7 días. También long-only.
Datos: Binance spot diario 2018-2026 (42 símbolos, cada uno desde su listado;
solo entran los que ya tienen 252 días de historia). Dato = SEMANA de cartera.
IS <=2023 / OOS 2024-26.

Solo lectura. Uso: python explore_52whigh.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
import ccxt
from explore_friday_history import daily_history

COST = (0.02 + 0.025) * 2
N = 5
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM",
        "DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
        "PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
        "BTC","ETH","BNB","XRP"]


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    if len(p) < 10:
        return f"    {lbl:10} n {len(p):4d} (pocas semanas)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:10} n {len(p):4d} sem | exp {m:+.3f}%/sem "
            f"[{lo:+.3f},{hi:+.3f}] {sig} | suma {p.sum():+.0f}%")


def main():
    ex = ccxt.binance({"enableRateLimit": True, "timeout": 20000})
    if os.environ.get("INSECURE_SSL") == "1":
        ex.verify = False
    ex.load_markets()
    closes = {}
    for s in SYMS:
        sym = f"{s}/USDT"
        if sym not in ex.markets:
            continue
        c = daily_history(ex, sym)
        if len(c) < 300:
            continue
        closes[s] = pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): x[4]
                               for x in c})
    px = pd.DataFrame(closes)
    print(f"universo con historia: {px.shape[1]} símbolos, {px.shape[0]} días")
    ratio = px / px.rolling(252).max().shift(1)   # solo pasado
    lunes = [t for t in px.index if t.weekday() == 0]

    res = {"L-S": [], "long-only": []}
    for t in lunes:
        t7 = t + pd.Timedelta(days=7)
        if t not in ratio.index or t7 not in px.index:
            continue
        r = ratio.loc[t].dropna()
        h = (px.loc[t7] / px.loc[t] - 1) * 100
        r = r[h[r.index].notna()]
        if len(r) < 2 * N + 2:
            continue
        rank = r.sort_values()
        top, bot = rank.index[-N:], rank.index[:N]
        long_r = h[top].mean() - COST
        short_r = -h[bot].mean() - COST
        res["L-S"].append((t.year, (long_r + short_r) / 2))
        res["long-only"].append((t.year, long_r))

    for k, rows in res.items():
        print(f"\n[cerca-de-máximo-52s | {k}]")
        print(stats_line([p for _, p in rows], "TOTAL"))
        print(stats_line([p for y, p in rows if y <= 2023], "IS <=23"))
        print(stats_line([p for y, p in rows if y >= 2024], "OOS 24-26"))


if __name__ == "__main__":
    main()
