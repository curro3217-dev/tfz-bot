"""
ROBUSTEZ de la prima de Coinbase (H1: prima alta -> long BTC 7d) (2026-07-03).

Controles obligatorios (lecciones del funding contrarian):
  1. DERIVA: comparar contra el retorno medio de 7d de TODOS los días del periodo
     (si BTC sube de fondo, cualquier "long a veces" parece listo).
  2. DOSIS-RESPUESTA: umbrales z >= 0.5 / 1.0 / 1.5 (debería crecer si es real).
  3. POR AÑO: tabla 2018..2026.
  4. TRANSFERENCIA: la misma señal (prima de BTC) aplicada a ETH.

Solo lectura. Uso: python analyze_premium.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
import ccxt
from explore_friday_history import daily_history
from explore_premium import cierres, episodios

COST = (0.02 + 0.025) * 2
HOLD_D = 7


def fwd7(px, idx, sgn=1):
    out = []
    for t in idx:
        t_exit = t + pd.Timedelta(days=HOLD_D)
        if t in px.index and t_exit in px.index:
            out.append((t, sgn * (px[t_exit] - px[t]) / px[t] * 100 - COST))
    return out


def stats(p):
    p = np.asarray(p, dtype=float)
    if len(p) < 8:
        return f"n {len(p):3d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    sig = "EXCLUYE 0" if m - 1.96 * se > 0 or m + 1.96 * se < 0 else "incluye 0"
    return f"n {len(p):3d} | {m:+.2f}%/7d [{m-1.96*se:+.2f},{m+1.96*se:+.2f}] {sig}"


def main():
    cb = cierres("coinbaseexchange", "BTC/USD")
    bn = cierres("binance", "BTC/USDT")
    df = pd.DataFrame({"cb": cb, "bn": bn}).dropna()
    prem = (df["cb"] / df["bn"] - 1) * 100
    z = ((prem - prem.rolling(90).mean().shift(1))
         / prem.rolling(90).std().shift(1)).dropna()
    px = df["bn"]

    # 1. control de deriva: 7d forward de TODOS los días (mismo rango que z)
    todos = fwd7(px, z.index)
    print("1. CONTROL DE DERIVA (todos los días, mismo periodo):")
    print(f"   {stats([p for _, p in todos])}")
    base = np.mean([p for _, p in todos])

    # 2. dosis-respuesta
    print("\n2. DOSIS-RESPUESTA por umbral (episodios no solapados, long):")
    for thr in (0.5, 1.0, 1.5):
        eps = fwd7(px, episodios(z, lambda s, t=thr: s >= t))
        p = [x for _, x in eps]
        print(f"   z>={thr}: {stats(p)} | exceso sobre deriva {np.mean(p)-base:+.2f}%")

    # 3. por año (umbral z>=1)
    print("\n3. POR AÑO (z>=1, long):")
    eps = fwd7(px, episodios(z, lambda s: s >= 1))
    d = pd.DataFrame(eps, columns=["t", "p"])
    d["y"] = d["t"].dt.year
    for y, g in d.groupby("y"):
        print(f"   {y}: {stats(g['p'].values)}")

    # 4. transferencia a ETH (misma señal de prima BTC)
    print("\n4. TRANSFERENCIA A ETH (señal de prima BTC, z>=1, long ETH):")
    eth = cierres("binance", "ETH/USDT")
    eps_e = fwd7(eth, episodios(z, lambda s: s >= 1))
    todos_e = fwd7(eth, z.index)
    print(f"   señal: {stats([p for _, p in eps_e])}")
    print(f"   deriva ETH: {stats([p for _, p in todos_e])} | exceso "
          f"{np.mean([p for _, p in eps_e]) - np.mean([p for _, p in todos_e]):+.2f}%")


if __name__ == "__main__":
    main()
