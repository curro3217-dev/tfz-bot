"""
EXPLORACIÓN #25: PEG DE USDT (Kraken USDT/USD) (2026-07-03).

USDT cotizando sobre/bajo $1 refleja flujo de entrada/salida del ecosistema.
HIPÓTESIS PRE-ESPECIFICADAS (mecanismo clásico, fijado antes de mirar):
  H1: USDT con PRIMA (z >= +1) -> demanda por entrar -> LONG BTC 7 días
  H2: USDT con DESCUENTO (z <= -1) -> salida/estrés -> SHORT BTC 7 días
z-score móvil 90d SOLO pasado, episodios no solapados. IS <=2023 / OOS 2024-26.

Solo lectura. Uso: python explore_usdt_peg.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
import ccxt
from explore_friday_history import daily_history
from explore_premium import episodios

COST = (0.02 + 0.025) * 2
HOLD_D = 7


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    if len(p) < 10:
        return f"    {lbl:12} n {len(p):3d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:12} n {len(p):3d} | win {(p>0).mean()*100:4.0f}% | "
            f"exp {m:+.2f}%/7d [{lo:+.2f},{hi:+.2f}] {sig}")


def main():
    # Bitfinex: USDT/USD desde 2018 (Kraken corta en ~720 días por su API)
    kr = ccxt.bitfinex({"enableRateLimit": True, "timeout": 20000})
    if os.environ.get("INSECURE_SSL") == "1":
        kr.verify = False
    kr.load_markets()
    c = daily_history(kr, "USDT/USD")
    peg = pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): x[4] for x in c})
    print(f"USDT/USD Bitfinex: {len(peg)} días, {peg.index[0].date()} -> "
          f"{peg.index[-1].date()} | hoy {peg.iloc[-1]:.4f}")
    dev = (peg - 1) * 100
    z = ((dev - dev.rolling(90).mean().shift(1))
         / dev.rolling(90).std().shift(1)).dropna()

    bn = ccxt.binance({"enableRateLimit": True, "timeout": 20000})
    if os.environ.get("INSECURE_SSL") == "1":
        bn.verify = False
    bn.load_markets()
    cb = daily_history(bn, "BTC/USDT")
    px = pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): x[4] for x in cb})

    for nombre, idx, sgn in (
            ("H1 prima -> LONG", episodios(z, lambda s: s >= 1), 1),
            ("H2 descuento -> SHORT", episodios(z, lambda s: s <= -1), -1)):
        rows = []
        for t in idx:
            t1 = t + pd.Timedelta(days=HOLD_D)
            if t in px.index and t1 in px.index:
                rows.append({"y": t.year,
                             "p": sgn * (px[t1]-px[t])/px[t]*100 - COST})
        d = pd.DataFrame(rows)
        print(f"\n  {nombre}:")
        if not len(d):
            print("    sin episodios")
            continue
        print(stats_line(d["p"].values, "TOTAL"))
        print(stats_line(d[d.y <= 2023]["p"].values, "IS <=23"))
        print(stats_line(d[d.y >= 2024]["p"].values, "OOS 24-26"))


if __name__ == "__main__":
    main()
