"""
EXPLORACIÓN #26: PRIMA COMPUESTA (2 venues USD) + BARRIDO DE HORIZONTE (2026-07-03).

1. COMPUESTA: ¿mejora exigir que la prima esté alta en Coinbase Y en Bitstamp a la
   vez (z medio de ambos >= 1)? Bitstamp da BTC/USD con historia profunda. Se compara
   contra la señal solo-Coinbase en el MISMO periodo común (comparación limpia).
2. HORIZONTE: la regla sellada usa 7 días. ¿Cómo reparte el edge en 3/7/14 días?
   (descriptivo: la regla sellada NO cambia; esto informa a futuras variantes que
   necesitarían su propio pre-registro).

Solo lectura. Uso: python explore_premium_composite.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from explore_premium import cierres, episodios

COST = (0.02 + 0.025) * 2


def stats(p):
    p = np.asarray(p, dtype=float)
    if len(p) < 8:
        return f"n {len(p):3d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    sig = "EXCLUYE 0" if m - 1.96 * se > 0 or m + 1.96 * se < 0 else "incluye 0"
    return f"n {len(p):3d} | {m:+.2f}% [{m-1.96*se:+.2f},{m+1.96*se:+.2f}] {sig}"


def z_serie(cb, ref):
    df = pd.DataFrame({"a": cb, "b": ref}).dropna()
    prem = (df["a"] / df["b"] - 1) * 100
    return ((prem - prem.rolling(90).mean().shift(1))
            / prem.rolling(90).std().shift(1)).dropna()


def pnl_holds(px, idx, holds=(3, 7, 14)):
    out = {h: [] for h in holds}
    for t in idx:
        for h in holds:
            t1 = t + pd.Timedelta(days=h)
            if t in px.index and t1 in px.index:
                out[h].append((px[t1] - px[t]) / px[t] * 100 - COST)
    return out


def main():
    cb = cierres("coinbaseexchange", "BTC/USD")
    bs = cierres("bitstamp", "BTC/USD")
    bn = cierres("binance", "BTC/USDT")
    z_cb = z_serie(cb, bn)
    z_bs = z_serie(bs, bn)
    comun = z_cb.index.intersection(z_bs.index)
    z_cb, z_bs = z_cb[comun], z_bs[comun]
    z_comp = (z_cb + z_bs) / 2
    px = bn
    print(f"periodo común: {comun[0].date()} -> {comun[-1].date()} ({len(comun)} días)")

    print("\n1. SOLO COINBASE vs COMPUESTA (mismo periodo, hold 7d):")
    solo = pnl_holds(px, episodios(z_cb, lambda s: s >= 1), holds=(7,))[7]
    comp = pnl_holds(px, episodios(z_comp, lambda s: s >= 1), holds=(7,))[7]
    print(f"   solo CB    {stats(solo)}")
    print(f"   compuesta  {stats(comp)}")

    print("\n2. BARRIDO DE HORIZONTE (señal solo-CB, misma tanda):")
    hh = pnl_holds(px, episodios(z_cb, lambda s: s >= 1))
    for h, p in hh.items():
        pa = np.asarray(p)
        print(f"   hold {h:2d}d  {stats(pa)} | por día de exposición "
              f"{pa.mean()/h:+.3f}%")


if __name__ == "__main__":
    main()
