"""
EXPLORACIÓN #11: OPEN INTEREST + precio, los 4 cuadrantes clásicos (2026-07-03).

Datos: OI diario de BYBIT (~6-7 meses disponibles por API) + precios de la cache.
HIPÓTESIS PRE-ESPECIFICADAS (tabla clásica de lectura del OI, fijadas ANTES de
mirar los resultados — si no salen así, no hay señal; no se busca otra cosa):
  Q1 precio↑ OI↑  -> dinero nuevo comprando  -> MAÑANA sigue subiendo (long)
  Q2 precio↓ OI↑  -> dinero nuevo vendiendo  -> mañana sigue bajando (short)
  Q3 precio↑ OI↓  -> cierre de cortos        -> subida sin gasolina (fade/short)
  Q4 precio↓ OI↓  -> cierre de largos        -> caída sin gasolina (rebote/long)
También: ratio long/short de Bybit en extremos (crowding -> contrarian).

Estadística: dato = DÍA de cartera (media entre símbolos con ese cuadrante ese
día); split temporal 70/30. Retornos BRUTOS del día siguiente + veredicto neto
(coste 0.09% i/v si se operase cada día). Solo lectura.

Uso: python explore_oi.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import time
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached, create_exchange

COST = (0.02 + 0.025) * 2
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]
Q_NOMBRES = {(1, 1): "Q1 p+ oi+ (esperado: long)",
             (-1, 1): "Q2 p- oi+ (esperado: short)",
             (1, -1): "Q3 p+ oi- (esperado: short)",
             (-1, -1): "Q4 p- oi- (esperado: long)"}
ESPERADO = {(1, 1): 1, (-1, 1): -1, (1, -1): -1, (-1, -1): 1}


def hist_paginada(fetch, sym, tf="1d", pages=4, key="timestamp"):
    out = []; end = None
    for _ in range(pages):
        try:
            params = {} if end is None else {"endTime": end}
            h = fetch(sym, tf, limit=200, params=params)
        except Exception:
            break
        if not h:
            break
        out = h + out
        end = h[0][key] - 1
        if len(h) < 200:
            break
        time.sleep(0.3)
    seen = set(); res = []
    for x in sorted(out, key=lambda z: z[key]):
        if x[key] not in seen:
            seen.add(x[key]); res.append(x)
    return res


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    p = p[~np.isnan(p)]
    if len(p) < 25:
        return f"    {lbl:34} n {len(p):4d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return f"    {lbl:34} n {len(p):4d} | media {m:+.3f}%/día [{lo:+.3f},{hi:+.3f}] {sig}"


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    ex = create_exchange("bybit")
    ex.load_markets()

    quad_days = {}   # (quad) -> {fecha: [ret_siguiente,...]}
    ls_days = {"crowd_long (ratio>q80, contrarian short)": {},
               "crowd_short (ratio<q20, contrarian long)": {}}
    for s in SYMS:
        sym = f"{s}/USDT:USDT"
        oi_h = hist_paginada(ex.fetch_open_interest_history, sym)
        if len(oi_h) < 60:
            print(f"  {s}: OI insuf ({len(oi_h)})")
            continue
        oi = pd.Series({pd.to_datetime(x["timestamp"], unit="ms"):
                        x.get("openInterestAmount") or x.get("openInterestValue")
                        for x in oi_h}).astype(float)
        doi = np.sign(oi.pct_change())
        try:
            d = fetch_ohlcv_cached(sym, "1h", limit=20000, config=cfg)
        except Exception:
            continue
        daily = d.set_index("timestamp")["close"].resample("1D").last().dropna()
        ret = daily.pct_change() * 100
        rnext = ret.shift(-1)
        for t in oi.index:
            if t not in ret.index or pd.isna(ret[t]) or pd.isna(rnext.get(t, np.nan)):
                continue
            dv = doi.get(t, np.nan)
            if pd.isna(dv):
                continue
            q = (int(np.sign(ret[t])), int(dv))
            if q in Q_NOMBRES:
                quad_days.setdefault(q, {}).setdefault(t, []).append(rnext[t])
        # ratio long/short: extremos historicos del propio simbolo (solo pasado seria
        # lo suyo; aqui quantil de toda la muestra -> version rapida, se anota)
        try:
            ls_h = hist_paginada(ex.fetch_long_short_ratio_history, sym)
            lsr = pd.Series({pd.to_datetime(x["timestamp"], unit="ms"):
                             x["longShortRatio"] for x in ls_h}).astype(float)
            q80, q20 = lsr.quantile(0.8), lsr.quantile(0.2)
            for t, v in lsr.items():
                if t not in rnext.index or pd.isna(rnext[t]):
                    continue
                if v >= q80:
                    ls_days["crowd_long (ratio>q80, contrarian short)"].setdefault(
                        t, []).append(-rnext[t])
                elif v <= q20:
                    ls_days["crowd_short (ratio<q20, contrarian long)"].setdefault(
                        t, []).append(rnext[t])
        except Exception:
            pass
        print(f"  {s}: OI {len(oi)} días")

    print(f"\n=== CUADRANTES precio×OI -> retorno del DÍA SIGUIENTE (bruto) ===")
    print(f"    (para operarlo a diario haría falta superar ~{COST:.2f}% de coste)")
    for q, name in Q_NOMBRES.items():
        dd = quad_days.get(q, {})
        serie = pd.Series({t: np.mean(v) for t, v in sorted(dd.items())})
        if not len(serie):
            continue
        cut = int(len(serie) * 0.7)
        # signo esperado aplicado -> "pnl de la hipótesis"
        exp_dir = ESPERADO[q]
        print(f"\n  {name}")
        print(stats_line(serie.values * exp_dir, "hipótesis TOTAL (bruto)"))
        print(stats_line(serie.values[:cut] * exp_dir, "IS 70%"))
        print(stats_line(serie.values[cut:] * exp_dir, "OOS 30%"))

    print(f"\n=== RATIO LONG/SHORT en extremos (contrarian, bruto) ===")
    for name, dd in ls_days.items():
        serie = pd.Series({t: np.mean(v) for t, v in sorted(dd.items())})
        if not len(serie):
            continue
        cut = int(len(serie) * 0.7)
        print(f"\n  {name}")
        print(stats_line(serie.values, "TOTAL (bruto)"))
        print(stats_line(serie.values[:cut], "IS 70%"))
        print(stats_line(serie.values[cut:], "OOS 30%"))
    print("\nNOTA: umbrales q80/q20 del ratio usan TODA la muestra (rápido) -> si algo")
    print("sale vivo, repetir con umbral solo-pasado antes de creérselo.")


if __name__ == "__main__":
    main()
