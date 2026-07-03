"""
EXPLORACIÓN #36: AMPLITUD (alt-season) + VOLUMEN CRECIENTE (2026-07-04).

1. AMPLITUD: % de las 38 alts del universo ganando a BTC a 30 días (solo pasado).
   HIPÓTESIS pre-especificadas: amplitud ALTA (>60%) = alt-season en marcha ->
   la cesta de alts SIGUE ganando a BTC la semana siguiente (momentum de régimen);
   amplitud BAJA (<40%) -> sigue perdiendo. Se mide alts-vs-BTC (neutral a mercado,
   2 patas) semanal, lunes, hold 7d.
2. VOLUMEN CRECIENTE: ranking semanal por crecimiento del volumen USD (media 7d
   vs media 30d previa, solo pasado); long top-5 / short bottom-5, hold 7d.
Datos Binance diario 2018-26. Dato = semana. IS <=2023 / OOS 2024-26.

Solo lectura. Uso: python explore_breadth.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
import ccxt
from explore_friday_history import daily_history, SYMS

COST = (0.02 + 0.025) * 2
N = 5


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    if len(p) < 10:
        return f"    {lbl:12} n {len(p):4d} (pocas semanas)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:12} n {len(p):4d} sem | exp {m:+.3f}%/sem "
            f"[{lo:+.3f},{hi:+.3f}] {sig}")


def main():
    ex = ccxt.binance({"enableRateLimit": True, "timeout": 20000})
    if os.environ.get("INSECURE_SSL") == "1":
        ex.verify = False
    ex.load_markets()
    closes, vols = {}, {}
    for s in SYMS:
        sym = f"{s}/USDT"
        if sym not in ex.markets:
            continue
        c = daily_history(ex, sym)
        if len(c) < 300:
            continue
        idx = pd.to_datetime([x[0] for x in c], unit="ms").normalize()
        closes[s] = pd.Series([x[4] for x in c], index=idx)
        vols[s] = pd.Series([x[4] * x[5] for x in c], index=idx)
    px = pd.DataFrame(closes)
    alts = [c for c in px.columns if c != "BTC"]
    lunes = [t for t in px.index if t.weekday() == 0]

    # 1. amplitud
    r30 = px.pct_change(30).shift(1)
    breadth = (r30[alts].gt(r30["BTC"], axis=0)).mean(axis=1)
    rows = []
    for t in lunes:
        t7 = t + pd.Timedelta(days=7)
        if t not in breadth.index or t7 not in px.index or pd.isna(breadth[t]):
            continue
        alt_next = (px.loc[t7, alts] / px.loc[t, alts] - 1).mean() * 100
        btc_next = (px.loc[t7, "BTC"] / px.loc[t, "BTC"] - 1) * 100
        spread = alt_next - btc_next
        if breadth[t] > 0.6:
            rows.append((t.year, spread - 2 * COST))       # long alts / short BTC
        elif breadth[t] < 0.4:
            rows.append((t.year, -spread - 2 * COST))      # short alts / long BTC
    print("[1. AMPLITUD alt-season (régimen >60% / <40%, 2 patas)]")
    print(stats_line([p for _, p in rows], "TOTAL"))
    print(stats_line([p for y, p in rows if y <= 2023], "IS <=23"))
    print(stats_line([p for y, p in rows if y >= 2024], "OOS 24-26"))

    # 2. volumen creciente
    vol_usd = pd.DataFrame(vols)
    vgrow = (vol_usd.rolling(7).mean() / vol_usd.rolling(30).mean().shift(7)).shift(1)
    rows = []
    for t in lunes:
        t7 = t + pd.Timedelta(days=7)
        if t not in vgrow.index or t7 not in px.index:
            continue
        f = vgrow.loc[t].dropna()
        h = (px.loc[t7] / px.loc[t] - 1) * 100
        f = f[h[f.index].notna()]
        if len(f) < 2 * N + 2:
            continue
        rank = f.sort_values()
        pnl = (h[rank.index[-N:]].mean() - h[rank.index[:N]].mean()) / 2 - COST
        rows.append((t.year, pnl))
    print("\n[2. VOLUMEN CRECIENTE (long top-5 / short bottom-5)]")
    print(stats_line([p for _, p in rows], "TOTAL"))
    print(stats_line([p for y, p in rows if y <= 2023], "IS <=23"))
    print(stats_line([p for y, p in rows if y >= 2024], "OOS 24-26"))


if __name__ == "__main__":
    main()
