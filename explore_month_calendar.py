"""
EXPLORACIÓN #18: CALENDARIO MENSUAL — vencimiento de opciones y cambio de mes (2026-07-03).

Dos anomalías documentadas fuera de cripto, probadas aquí con BTC/ETH (Binance spot
diario 2018->hoy). HIPÓTESIS PRE-ESPECIFICADAS:
  H1 (vencimiento Deribit, último viernes de mes): deriva NEGATIVA los 3 días antes
     y POSITIVA los 3 días después ("post-expiry rally" del folclore de opciones).
  H2 (turn-of-month, documentado en bolsa): retorno POSITIVO en la ventana último
     día del mes + 3 primeros del siguiente, frente al resto de días.
Retornos diarios BRUTOS (una anomalía de deriva se mide así; el coste se aplica si
algún día se operase). IS 2018-2023 / OOS 2024-2026.

Solo lectura. Uso: python explore_month_calendar.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
import ccxt
from explore_friday_history import daily_history


def ultimo_viernes(y, m):
    t = pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)
    while t.weekday() != 4:
        t -= pd.Timedelta(days=1)
    return t


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    p = p[~np.isnan(p)]
    if len(p) < 20:
        return f"    {lbl:22} n {len(p):4d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return f"    {lbl:22} n {len(p):4d} | media {m:+.3f}%/día [{lo:+.3f},{hi:+.3f}] {sig}"


def main():
    ex = ccxt.binance({"enableRateLimit": True, "timeout": 20000})
    if os.environ.get("INSECURE_SSL") == "1":
        ex.verify = False
    ex.load_markets()
    for coin in ("BTC", "ETH"):
        c = daily_history(ex, f"{coin}/USDT")
        px = pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): x[4] for x in c})
        ret = px.pct_change() * 100
        d = pd.DataFrame({"r": ret}).dropna()
        # H1: distancia al vencimiento (último viernes de mes)
        expiries = set()
        for y in range(d.index[0].year, d.index[-1].year + 1):
            for m in range(1, 13):
                expiries.add(ultimo_viernes(y, m))
        dist = {}
        for t in d.index:
            deltas = [(t - e).days for e in expiries if abs((t - e).days) <= 3]
            if deltas:
                dist[t] = min(deltas, key=abs)
        d["dist"] = pd.Series(dist)
        # H2: turn-of-month (último día del mes y 3 primeros)
        d["tom"] = (d.index.day >= d.index.days_in_month) | (d.index.day <= 3)
        for per, g in (("IS 2018-23", d[d.index.year <= 2023]),
                       ("OOS 2024-26", d[d.index.year >= 2024])):
            print(f"\n=== {coin} {per} ===")
            print(stats_line(g[g["dist"].isin([-3, -2, -1])]["r"], "H1 pre-expiry (-3..-1)"))
            print(stats_line(g[g["dist"].isin([1, 2, 3])]["r"], "H1 post-expiry (+1..+3)"))
            print(stats_line(g[g.tom]["r"], "H2 turn-of-month"))
            print(stats_line(g[~g.tom & g["dist"].isna()]["r"], "resto de días"))


if __name__ == "__main__":
    main()
