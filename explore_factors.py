"""
EXPLORACIÓN #33: FACTORES ACADÉMICOS cross-sectional (2026-07-04).

Tres factores documentados en la literatura (acciones y papers cripto), no
probados aún. Construcción semanal (lunes, señal SOLO con pasado, hold 7d,
long top-5 / short bottom-5 según el factor, costes MEXC por pata):
  1. MAX (lotería, Bali et al.): el máximo retorno diario de los últimos 7 días.
     Predicción: MAX alto -> peor retorno (se compra el boleto). SHORT MAX alto.
  2. LOW-VOL (BAB): desviación de retornos 30d. Predicción: vol baja rinde más
     por unidad de riesgo. LONG vol baja / SHORT vol alta.
  3. AMIHUD (iliquidez): media 30d de |ret|/volumen_usd. Predicción: prima de
     iliquidez -> LONG ilíquidas / SHORT líquidas.
Datos: Binance spot diario 2018-2026 (42 símbolos, cierre y volumen). Dato
estadístico = SEMANA de cartera. IS <=2023 / OOS 2024-26.

Solo lectura. Uso: python explore_factors.py
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
        vols[s] = pd.Series([x[4] * x[5] for x in c], index=idx)  # volumen USD
    px = pd.DataFrame(closes)
    vol_usd = pd.DataFrame(vols)
    ret = px.pct_change() * 100
    print(f"universo: {px.shape[1]} símbolos, {px.shape[0]} días")

    # señales (todas con shift(1): solo pasado en el lunes de formación)
    max7 = ret.rolling(7).max().shift(1)
    vol30 = ret.rolling(30).std().shift(1)
    amihud = (ret.abs() / vol_usd.replace(0, np.nan)).rolling(30).mean().shift(1)
    lunes = [t for t in px.index if t.weekday() == 0]

    # factor -> (señal, sentido: +1 = long ranking alto, -1 = long ranking bajo)
    factores = {"1. MAX/lotería (short alto)": (max7, -1),
                "2. LOW-VOL (long bajo)": (vol30, -1),
                "3. AMIHUD (long ilíquido)": (amihud, +1)}
    for nombre, (sig, sentido) in factores.items():
        rows = []
        for t in lunes:
            t7 = t + pd.Timedelta(days=7)
            if t not in sig.index or t7 not in px.index:
                continue
            f = sig.loc[t].dropna()
            h = (px.loc[t7] / px.loc[t] - 1) * 100
            f = f[h[f.index].notna()]
            if len(f) < 2 * N + 2:
                continue
            rank = f.sort_values()
            alto, bajo = rank.index[-N:], rank.index[:N]
            if sentido > 0:
                pnl = (h[alto].mean() - h[bajo].mean()) / 2 - COST
            else:
                pnl = (h[bajo].mean() - h[alto].mean()) / 2 - COST
            rows.append((t.year, pnl))
        print(f"\n[{nombre}]")
        print(stats_line([p for _, p in rows], "TOTAL"))
        print(stats_line([p for y, p in rows if y <= 2023], "IS <=23"))
        print(stats_line([p for y, p in rows if y >= 2024], "OOS 24-26"))


if __name__ == "__main__":
    main()
