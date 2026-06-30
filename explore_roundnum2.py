"""
Comprobacion A FONDO del 'iman de numeros redondos' (multiples angulos):
MIDE EL FENOMENO PURO, no la economia del trade. Pregunta: en tendencia alcista y a
una distancia dada por debajo de un nivel, ¿el precio TOCA ese nivel mas a menudo si
es REDONDO que si NO lo es (control), a la MISMA distancia?

- Niveles redondos: multiplos de s.  Control (anti-redondo): multiplos de s desplazados s/2 (lo menos redondo).
- Se compara la TASA DE TOQUE (high alcanza el nivel en <=MAX_HOLD velas) por cubo de distancia.
- Dos rejillas: 'whole' (s=10^floor(log10 p)) y 'half' (s=eso/2). Varias temporalidades.
Si redondo NO supera a anti-redondo -> el iman no es real/operable.
"""
import math
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from swings import compute_trend_strength

UNIVERSE = ["DOGE/USDT:USDT", "XRP/USDT:USDT", "SOL/USDT:USDT", "AVAX/USDT:USDT",
            "BNB/USDT:USDT", "NEAR/USDT:USDT", "ADA/USDT:USDT", "LINK/USDT:USDT",
            "SUI/USDT:USDT", "WLD/USDT:USDT", "AAVE/USDT:USDT", "ENA/USDT:USDT"]
TFS = ["5m", "15m", "1h"]
MAX_HOLD = 60
TREND_MIN = 1.0
BUCKETS = [(0.0, 0.005), (0.005, 0.01), (0.01, 0.015), (0.015, 0.02)]

def base_d(p):
    return 10 ** math.floor(math.log10(p))

def nearest_above(p, s, anti=False):
    # niveles = k*s (redondo) o (k+0.5)*s (anti-redondo)
    off = 0.5 * s if anti else 0.0
    k = math.floor((p - off) / s) + 1
    return k * s + off

# acumuladores: tasa de toque por (grid, redondo/anti, bucket)
from collections import defaultdict
hit = defaultdict(lambda: [0, 0])   # clave -> [toques, total]

for sym in UNIVERSE:
    for tf in TFS:
        tfc = config_for_timeframe(TFZConfig(), tf)
        try:
            df = fetch_ohlcv_cached(sym, tf, limit=1500, config=tfc)
        except Exception:
            continue
        if len(df) < 300:
            continue
        close = df["close"].values; high = df["high"].values
        n = len(df)
        trend = np.array([compute_trend_strength(df, tf, i) for i in range(n)])
        # max futuro de highs en ventana MAX_HOLD
        fwd = np.array([high[i+1:i+1+MAX_HOLD].max() if i+1 < n else -1e18 for i in range(n)])
        for i in range(200, n-1):
            if trend[i] < TREND_MIN:
                continue
            p = close[i]
            d = base_d(p)
            for gridname, s in (("whole", d), ("half", d/2)):
                for anti in (False, True):
                    L = nearest_above(p, s, anti)
                    gap = (L - p) / p
                    for lo, hi in BUCKETS:
                        if lo < gap <= hi:
                            key = (gridname, "anti" if anti else "round", f"{lo*100:.1f}-{hi*100:.1f}%")
                            hit[key][1] += 1
                            if fwd[i] >= L:
                                hit[key][0] += 1
                            break

print(f"TENDENCIA alcista (trend>={TREND_MIN}), toque en <= {MAX_HOLD} velas. TF: {TFS}")
for grid in ("whole", "half"):
    print(f"\n=== rejilla {grid} ===  (paso = {'10^floor(log10 p)' if grid=='whole' else 'eso/2'})")
    print(f"  {'distancia':10s} {'REDONDO':>16s} {'ANTI(control)':>16s}  diff")
    for lo, hi in BUCKETS:
        b = f"{lo*100:.1f}-{hi*100:.1f}%"
        r = hit[(grid, "round", b)]; a = hit[(grid, "anti", b)]
        rr = 100*r[0]/r[1] if r[1] else 0
        ar = 100*a[0]/a[1] if a[1] else 0
        print(f"  {b:10s} {rr:6.1f}% (n={r[1]:5d}) {ar:6.1f}% (n={a[1]:5d})  {rr-ar:+.1f}pp")
