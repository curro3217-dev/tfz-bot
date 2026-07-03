"""
ROBUSTEZ del contrarian de funding (lee funding_deep_trades.csv, solo lectura).

Cuatro pruebas de estrés sobre la variante estrella (contrarian, hold 24h):
  1. SIN crédito de funding: ¿el edge está en el PRECIO o en el crédito aproximado
     de cobrar funding (que se acredita a la tasa del extremo, favorable)?
  2. SIN solapamiento: 1 señal por símbolo cada 24h (la batería cuenta el mismo
     movimiento hasta 3 veces, funding cada 8h con hold 24h).
  3. Por símbolo: ¿cuántos símbolos son positivos? (¿edge repartido o 2 monedas?)
  4. Por trimestre: ¿estable en el tiempo o un solo periodo bueno?

Uso: python analyze_funding_deep.py [umbral]   (umbral 0.05 por defecto)
"""
import os
import sys
import numpy as np
import pandas as pd

COST_MEXC = (0.02 + 0.025) * 2
CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "funding_deep_trades.csv")


def stats_line(p):
    p = np.asarray(p, dtype=float)
    if len(p) < 2:
        return "n<2"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"n {len(p):5d} | win {(p > 0).mean() * 100:4.1f}% | exp {m:+.3f}% "
            f"[{lo:+.3f},{hi:+.3f}] {sig}")


def main():
    umbral = float(sys.argv[1]) if len(sys.argv) > 1 else 0.05
    df = pd.read_csv(CSV)
    d = df[(df["umbral"] == umbral) & (df["hold_h"] == 24)].copy()
    d = d.sort_values(["symbol", "ts"]).reset_index(drop=True)
    # PnL contrarian: contra la masa (funding + -> short)
    d["pnl_precio"] = np.where(d["rate"] > 0, -d["ret_long"], d["ret_long"]) - COST_MEXC
    d["pnl_full"] = d["pnl_precio"] + d["fund"]
    print(f"contrarian hold 24h umbral {umbral:.0%} — {len(d)} señales\n")
    print(f"  CON crédito funding : {stats_line(d['pnl_full'])}")
    print(f"  SOLO PRECIO         : {stats_line(d['pnl_precio'])}")
    print(f"  (crédito medio de funding: {d['fund'].mean():+.3f}%/trade)")

    # 2. sin solapamiento: 1 señal por símbolo cada 24h
    keep = []
    for sym, g in d.groupby("symbol"):
        last = -np.inf
        for i, t in zip(g.index, g["ts"]):
            if t >= last + 24 * 3600 * 1000:
                keep.append(i); last = t
    nd = d.loc[keep]
    print(f"\n  SIN SOLAPAR (1/símbolo/24h):")
    print(f"  CON crédito funding : {stats_line(nd['pnl_full'])}")
    print(f"  SOLO PRECIO         : {stats_line(nd['pnl_precio'])}")

    # 3. por símbolo (sin solapar, con funding)
    print("\n  Por símbolo (sin solapar):")
    pos = 0
    for sym, g in nd.groupby("symbol"):
        m = g["pnl_full"].mean()
        pos += m > 0
        print(f"    {sym:7} n {len(g):4d} exp {m:+.3f}%")
    print(f"  símbolos positivos: {pos}/{nd['symbol'].nunique()}")

    # 4. por trimestre (sin solapar, con funding)
    nd = nd.copy()
    nd["q"] = pd.to_datetime(nd["ts"], unit="ms").dt.to_period("Q").astype(str)
    print("\n  Por trimestre (sin solapar):")
    for q, g in nd.groupby("q"):
        print(f"    {q}: {stats_line(g['pnl_full'])}")


if __name__ == "__main__":
    main()
