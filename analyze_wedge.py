"""
ROBUSTEZ del "Wedge Up -> short" (lecciones del funding aplicadas) (2026-07-06).

El patron dispara muchisimo (~3/semana/moneda) -> hold 5d = solapamiento brutal.
Controles:
  1. SIN SOLAPAR: 1 señal por simbolo cada 5 dias.
  2. DERIVA: retorno corto de TODAS las ventanas de 5d del mismo periodo (¿es
     solo "estar corto en un mercado que cae"?). Exceso = señal - deriva.
  3. Por simbolo (cuantos positivos) y por trimestre (estabilidad).
Solo lectura. Uso: python analyze_wedge.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from explore_patterns import detect_wedge, SYMS, COST, HOLD_D


def stats(p):
    p = np.asarray(p, dtype=float)
    if len(p) < 25:
        return f"n {len(p):5d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    sig = "EXCLUYE 0" if m - 1.96 * se > 0 or m + 1.96 * se < 0 else "incluye 0"
    return f"n {len(p):5d} | {m:+.3f}% [{m-1.96*se:+.3f},{m+1.96*se:+.3f}] {sig}"


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    señal, deriva = [], []
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        day = (d.set_index("timestamp")
               .resample("1D").agg({"open": "first", "high": "max",
                                    "low": "min", "close": "last"}).dropna())
        df = day.rename(columns={"open": "Open", "high": "High",
                                 "low": "Low", "close": "Close"}).copy()
        df = detect_wedge(df)
        closes = day["close"]
        # deriva: TODAS las ventanas de 5d (retorno corto neto)
        for i in range(1, len(day) - 1 - HOLD_D):
            deriva.append((day.index[i].year,
                           -(closes.iloc[i + 1 + HOLD_D] - closes.iloc[i + 1])
                           / closes.iloc[i + 1] * 100 - COST))
        # señal SIN SOLAPAR: 1 por simbolo cada HOLD_D dias
        marcas = df["wedge_pattern"].dropna()
        last_i = -99
        for t, patron in marcas.items():
            if str(patron) != "Wedge Up":
                continue
            i = day.index.get_loc(t)
            if i - last_i < HOLD_D or i + 1 + HOLD_D >= len(day):
                continue
            last_i = i
            pnl = -(closes.iloc[i + 1 + HOLD_D] - closes.iloc[i + 1]) \
                / closes.iloc[i + 1] * 100 - COST
            señal.append((s, day.index[i], float(pnl)))

    sdf = pd.DataFrame(señal, columns=["sym", "t", "p"])
    ddf = pd.DataFrame(deriva, columns=["y", "p"])
    print("1. SIN SOLAPAR (1/simbolo/5d):")
    print(f"   señal  {stats(sdf['p'].values)}")
    for y in (2024, 2025, 2026):
        g = sdf[sdf.t.dt.year == y]["p"].values
        dv = ddf[ddf.y == y]["p"].values
        exceso = (g.mean() - dv.mean()) if len(g) >= 25 else np.nan
        print(f"   {y}: señal {stats(g)} | deriva corta {dv.mean():+.3f}% | "
              f"exceso {exceso:+.3f}%")
    per = sdf.groupby("sym")["p"].mean()
    print(f"2. simbolos positivos: {(per > 0).sum()}/{len(per)}")
    sdf["q"] = sdf["t"].dt.to_period("Q").astype(str)
    print("3. por trimestre:")
    for q, g in sdf.groupby("q"):
        print(f"   {q}: {stats(g['p'].values)}")


if __name__ == "__main__":
    main()
