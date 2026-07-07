"""
EXPLORACIÓN #39: SMART MONEY CONCEPTS — FVG (2026-07-06).

Librería smartmoneyconcepts (joshyattridge, 1.8k*). AUDITADA: los swings (y todo
lo que depende de ellos: BOS/CHoCH/OB/liquidity) usan velas FUTURAS (before AND
after) -> inutilizables sin re-ingeniería de retardos. El FVG marca la vela
central t usando t+1 -> conocible al cierre de t+1: se opera AHÍ (+1 de retardo).

HIPÓTESIS PRE-ESPECIFICADAS (lectura SMC clásica: el hueco = agresión
institucional que continúa):
  H1: FVG alcista -> LONG al cierre de t+1, hold 3 días
  H2: FVG bajista -> SHORT al cierre de t+1, hold 3 días
42 símbolos, diario de cache (2024-26), costes MEXC. IS 24-25 / OOS 2026.

Solo lectura. Uso: python explore_smc.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from smartmoneyconcepts import smc

COST = (0.02 + 0.025) * 2
HOLD_D = 3
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM",
        "DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
        "1000PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
        "BTC","ETH","BNB","XRP"]


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    if len(p) < 30:
        return f"    {lbl:10} n {len(p):5d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:10} n {len(p):5d} | win {(p>0).mean()*100:4.1f}% | "
            f"exp {m:+.3f}% [{lo:+.3f},{hi:+.3f}] {sig}")


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    res = {1: [], -1: []}
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        day = (d.set_index("timestamp")
               .resample("1D").agg({"open": "first", "high": "max",
                                    "low": "min", "close": "last",
                                    "volume": "sum"}).dropna())
        try:
            f = smc.fvg(day)
        except Exception as e:
            print(f"  {s}: fvg fallo ({e})")
            continue
        closes = day["close"].values
        flags = f["FVG"].values
        for i in range(len(day)):
            v = flags[i]
            if np.isnan(v):
                continue
            # flag en t usa t+1 -> conocible al cierre de i+1; entrada ahí
            j = i + 1
            if j + HOLD_D >= len(day):
                continue
            pnl = int(v) * (closes[j + HOLD_D] - closes[j]) / closes[j] * 100 - COST
            res[int(v)].append((day.index[i].year, float(pnl)))

    for v, nombre in ((1, "H1 FVG alcista -> LONG 3d"),
                      (-1, "H2 FVG bajista -> SHORT 3d")):
        rows = res[v]
        print(f"\n[{nombre}]")
        print(stats_line([p for _, p in rows], "TOTAL"))
        print(stats_line([p for y, p in rows if y < 2026], "IS 24-25"))
        print(stats_line([p for y, p in rows if y >= 2026], "OOS 2026"))


if __name__ == "__main__":
    main()
