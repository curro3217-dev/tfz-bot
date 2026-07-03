"""
EXPLORACIÓN #8: SEGUIMIENTO DE TENDENCIA Donchian diario (2026-07-03).

La familia clásica de los CTAs, aún no probada en el universo: entrar cuando el
cierre rompe el canal de N días y salir cuando rompe el canal contrario de M días.
  - variantes: (N=20, M=10) y (N=55, M=20), long-short y long-only
  - señal con el cierre del día t -> posición DESDE el día t+1 (sin look-ahead;
    el canal usa máximos/mínimos de los N días ANTERIORES, excluyendo t)
  - costes MEXC por transacción (0.045% por lado: comisión taker + slippage)
  - dato estadístico = DÍA de cartera (media de los 20 símbolos ese día)
  - IS = 2024+2025 | OOS = 2026

Solo lectura. Uso: python explore_trend.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST_SIDE = 0.02 + 0.025   # % por transacción (entrada O salida)
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]


def positions(daily, n, m, long_only):
    """Serie de posición diaria (-1/0/+1) con el estado del canal Donchian."""
    hi_n = daily["high"].rolling(n).max().shift(1)
    lo_n = daily["low"].rolling(n).min().shift(1)
    hi_m = daily["high"].rolling(m).max().shift(1)
    lo_m = daily["low"].rolling(m).min().shift(1)
    c = daily["close"]
    pos = pd.Series(0.0, index=daily.index)
    p = 0.0
    for i in range(len(daily)):
        if np.isnan(hi_n.iloc[i]) or np.isnan(lo_m.iloc[i]):
            pos.iloc[i] = 0.0
            continue
        if p == 0:
            if c.iloc[i] > hi_n.iloc[i]:
                p = 1.0
            elif c.iloc[i] < lo_n.iloc[i] and not long_only:
                p = -1.0
        elif p > 0 and c.iloc[i] < lo_m.iloc[i]:
            p = 0.0
        elif p < 0 and c.iloc[i] > hi_m.iloc[i]:
            p = 0.0
        pos.iloc[i] = p
    return pos


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    p = p[~np.isnan(p)]
    if len(p) < 60:
        return f"  {lbl:14} n {len(p):4d} (pocos días)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"  {lbl:14} n {len(p):4d} días | media {m:+.4f}%/día "
            f"[{lo:+.4f},{hi:+.4f}] {sig} | anualizado ~{m*365:+.0f}%")


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    dailies = {}
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        g = d.set_index("timestamp").resample("1D").agg(
            {"high": "max", "low": "min", "close": "last"}).dropna()
        if len(g) >= 200:
            dailies[s] = g

    for (n, m) in ((20, 10), (55, 20)):
        for long_only in (False, True):
            port = {}
            n_tx = 0
            for s, g in dailies.items():
                pos = positions(g, n, m, long_only)
                ret = g["close"].pct_change() * 100
                tx = pos.diff().abs().fillna(0)        # cambios de posición
                n_tx += int((tx > 0).sum())
                pnl = pos.shift(1) * ret - tx * COST_SIDE
                for t, v in pnl.dropna().items():
                    port.setdefault(t, []).append(v)
            serie = pd.Series({t: np.mean(v) for t, v in sorted(port.items())})
            lbl = f"D{n}/{m} {'long-only' if long_only else 'long-short'}"
            print(f"\n[{lbl}] transacciones totales: {n_tx}")
            print(stats_line(serie.values, "TOTAL"))
            print(stats_line(serie[serie.index.year < 2026].values, "IS 2024-25"))
            print(stats_line(serie[serie.index.year >= 2026].values, "OOS 2026"))


if __name__ == "__main__":
    main()
