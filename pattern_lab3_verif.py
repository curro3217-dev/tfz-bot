"""Verificacion de los 2 supervivientes de la tanda 3 (div_oculta_bajista 1h, macd_cruce
bajista 1h) desde DOS angulos antes de dar veredicto firme:

1) CONTROL TONTO en el mismo universo: pseudo-patron "cruce bajo la SMA20" (= simplemente
   'empieza a bajar'). Si su edge corto es parecido al de los supervivientes, estos no
   aportan nada mas alla de "las caidas continuan en movers" (decaimiento post-pump).
2) REPLICACION en majors (1h y 4h): si el edge desaparece fuera del universo de movers,
   es propiedad del universo (seleccion), no del patron.
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
os.environ.setdefault("FREEZE_CACHE", "1")

import math
import numpy as np
from collections import defaultdict
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from pattern_lab3 import detect, sma, norm_sf

MOVERS = [s.strip() for s in open("_universe.txt").read().split(",") if s.strip()]
MAJORS = [f"{b}/USDT:USDT" for b in
          ("BTC ETH LTC BCH LINK ADA DOT ATOM FIL ETC TRX UNI ARB OP APT TON INJ TIA SEI ORDI").split()]
TARGETS = {"div_oculta_bajista", "macd_cruce_bajista"}
HORIZONS = [1, 5, 20]


def control_events(C):
    """Pseudo-patron: primer cierre por debajo de la SMA20 (= 'empieza a bajar')."""
    s20 = sma(C, 20)
    out = []
    for i in range(220, len(C)):
        if not np.isnan(s20[i]) and C[i - 1] >= s20[i - 1] and C[i] < s20[i]:
            out.append((i, -1))
    return out


def run_cell(label, uni, tf, limit):
    tfc = config_for_timeframe(TFZConfig(), tf)
    ev = defaultdict(list)
    for sym in uni:
        try:
            df = fetch_ohlcv_cached(sym, tf, limit=limit, config=tfc)
        except Exception:
            continue
        if len(df) < 400:
            continue
        O = df["open"].values.astype(float); H = df["high"].values.astype(float)
        L = df["low"].values.astype(float); C = df["close"].values.astype(float)
        n = len(C)
        fwd = {h: (C[h:] - C[:-h]) / C[:-h] * 100 for h in HORIZONS}
        base = {h: np.nanmean(fwd[h]) for h in HORIZONS}
        pats = {k: v for k, v in detect(O, H, L, C).items() if k in TARGETS}
        pats["CONTROL_bajo_sma20"] = control_events(C)
        for name, lst in pats.items():
            for i, d in lst:
                if i + max(HORIZONS) >= n:
                    continue
                ev[name].append(d * (fwd[5][i] - base[5]))
    print(f"--- {label} ---")
    for name in ["CONTROL_bajo_sma20", "div_oculta_bajista", "macd_cruce_bajista"]:
        a = np.array(ev.get(name, []))
        if len(a) < 30:
            print(f"  {name:22s} n={len(a):4d}  (insuficiente)")
            continue
        m = a.mean(); t = m / (a.std(ddof=1) / math.sqrt(len(a)))
        print(f"  {name:22s} n={len(a):4d}  edge h5 {m:+.3f}%  t={t:+.2f}  p={norm_sf(t):.4f}")
    print()


print("VERIFICACION supervivientes tanda 3 (edge h5 en la direccion del patron)\n")
run_cell("MOVERS 1h (la celda original)", MOVERS, "1h", 1500)
run_cell("MAJORS 1h (replicacion)", MAJORS, "1h", 3000)
run_cell("MAJORS 4h (replicacion)", MAJORS, "4h", 1500)
