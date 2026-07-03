"""
EXPLORACIÓN #6: MOMENTUM CROSS-SECTIONAL semanal (2026-07-03).

La construcción con más respaldo académico en cripto que aún no habíamos probado:
cada lunes 00:00 UTC, rankear el universo por su retorno de formación (7 o 30 días),
LONG el top-3 y SHORT el bottom-3, mantener 7 días. También variante long-only.

Disciplina anti-espejismo (lecciones del 2026-07-03):
  - IS = 2024+2025 (descubrir) | OOS = 2026 (validar). Solo cuenta el OOS.
  - dato = SEMANA de cartera (no trade): inmune a la correlación entre símbolos.
  - costes MEXC verificados (0.09% i/v por unidad de capital y semana).
  - todas las variantes en la MISMA tanda, mismos datos.

Solo lectura, no toca nada del bot. Uso: python explore_xsmom.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST = (0.02 + 0.025) * 2
N = 3          # tamaño de cada pata
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    if len(p) < 8:
        return f"  {lbl:26} n {len(p):3d} (pocas semanas)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"  {lbl:26} n {len(p):3d} sem | exp {m:+.3f}%/sem "
            f"[{lo:+.3f},{hi:+.3f}] {sig} | suma {p.sum():+.0f}%")


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    closes = {}
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        closes[s] = d.set_index("timestamp")["close"].resample("1D").last().dropna()
    px = pd.DataFrame(closes).dropna(how="all")
    lunes = [t for t in px.index if t.weekday() == 0]

    res = {}   # (form, modo) -> [(fecha, pnl_semana)]
    for form in (7, 30):
        for i, t in enumerate(lunes):
            t7 = t + pd.Timedelta(days=7)
            if t - pd.Timedelta(days=form) < px.index[0] or t7 not in px.index:
                continue
            t0 = t - pd.Timedelta(days=form)
            if t0 not in px.index:
                continue
            f_ret = (px.loc[t] / px.loc[t0] - 1).dropna()
            h_ret = (px.loc[t7] / px.loc[t] - 1)
            f_ret = f_ret[h_ret[f_ret.index].notna()]
            if len(f_ret) < 10:
                continue
            rank = f_ret.sort_values()
            top, bot = rank.index[-N:], rank.index[:N]
            long_r = h_ret[top].mean() * 100
            short_r = h_ret[bot].mean() * 100
            res.setdefault((form, "L-S"), []).append((t, (long_r - short_r) / 2 - COST))
            res.setdefault((form, "long-only"), []).append((t, long_r - COST))

    print(f"=== XS-MOMENTUM semanal: long top-{N} / short bottom-{N} de {len(closes)} "
          f"símbolos, costes MEXC ===")
    for key in sorted(res):
        form, modo = key
        rows = res[key]
        is_p = [p for t, p in rows if t.year < 2026]
        oos_p = [p for t, p in rows if t.year >= 2026]
        print(f"\n[formación {form}d | {modo}]")
        print(stats_line([p for _, p in rows], "TOTAL"))
        print(stats_line(is_p, "IS  2024-2025"))
        print(stats_line(oos_p, "OOS 2026"))
    print("\nRegla: solo cuenta si el IS y el OOS apuntan igual y el OOS no lo niega.")


if __name__ == "__main__":
    main()
