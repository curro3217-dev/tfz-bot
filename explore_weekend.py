"""
EXPLORACIÓN #5: EFECTO FIN DE SEMANA en momentum diario (2026-07-03).

Motivo: paper (Advances in Consumer Research, datos 2020-2025) que documenta que el
momentum en cripto rinde MÁS en fin de semana, sobre todo en altcoins. Aquí se prueba
en NUESTRO universo con NUESTROS datos (velas 1h de la cache, MEXC), sin fiarse.

Estrategia probada (momentum diario, la más simple posible, sin parámetros libres):
  a las 00:00 UTC, mirar el retorno de las últimas 24h; ir EN esa dirección 24h.
  Trades no solapados por símbolo. Neto de costes MEXC (0.09% i/v). El funding se
  ignora (~0.01%/día, simétrico long/short en media).

Se reporta por día de ENTRADA (lun..dom), agregado L-V vs S-D, con IC95. Regla: solo
"hay algo" si el IC95 excluye cero. Solo lectura, no toca nada del bot.

Uso: python explore_weekend.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST_MEXC = (0.02 + 0.025) * 2
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]
DIAS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]


def stats_line(p):
    p = np.array(p)
    if len(p) < 2:
        return "n<2"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"n {len(p):5d} | win {(p > 0).mean() * 100:4.1f}% | exp {m:+.3f}% "
            f"[{lo:+.3f},{hi:+.3f}] {sig}")


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    por_dia = {i: [] for i in range(7)}
    total_simbolos = 0
    for s in SYMS:
        sym = f"{s}/USDT:USDT"
        try:
            d = fetch_ohlcv_cached(sym, "1h", limit=20000, config=cfg)
        except Exception as e:
            print(f"  {s}: sin velas ({e})")
            continue
        d = d.set_index("timestamp")
        # cierre diario a las 00:00 UTC desde las velas 1h
        daily = d["close"].resample("1D").last().dropna()
        if len(daily) < 60:
            print(f"  {s}: pocos días ({len(daily)})")
            continue
        r_prev = daily.pct_change()            # retorno del día anterior (señal)
        r_next = daily.pct_change().shift(-1)  # retorno del día siguiente (resultado)
        ok = r_prev.notna() & r_next.notna() & (r_prev != 0)
        pnl = (np.sign(r_prev[ok]) * r_next[ok] * 100) - COST_MEXC
        for t, p in pnl.items():
            por_dia[t.weekday()].append(p)
        total_simbolos += 1
        print(f"  {s:7} {ok.sum()} días")

    print(f"\n=== MOMENTUM DIARIO POR DÍA DE ENTRADA ({total_simbolos} símbolos, "
          f"costes MEXC) ===")
    for i in range(7):
        print(f"  {DIAS[i]}  {stats_line(por_dia[i])}")
    lv = [p for i in range(5) for p in por_dia[i]]
    sd = [p for i in (5, 6) for p in por_dia[i]]
    print(f"\n  L-V {stats_line(lv)}")
    print(f"  S-D {stats_line(sd)}")
    print("\nNOTA: mismos días entre símbolos -> trades correlados, el IC95 real es")
    print("más ancho. El paper mide otra construcción (cross-section); esto es la")
    print("versión time-series aplicable a un bot de un solo símbolo por trade.")


if __name__ == "__main__":
    main()
