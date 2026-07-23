"""
EXPLORACIÓN (retrospectiva, NO veredicto): "The Bard FX / No Wick Strategy".

Premisa falsable central de la estrategia: una vela "no wick" (abre en su extremo
y se desplaza fuerte en una dirección) PREDICE CONTINUACIÓN en esa dirección. Si
esa premisa es falsa, todo lo demás (retest, stop tras estructura, 1:1) no tiene
base. Aquí se mide SOLO eso, de forma objetiva, sin las partes discrecionales
(market structure, swing highs, imbalances) que no se pueden reproducir sin
inventárselas.

Universo FIJO (sin sesgo de selección): los 42 símbolos del weekend_paper, perps
MEXC BASE/USDT:USDT. TF 15m (análogo intradía). ~10 días de historia (1 régimen:
julio-2026 bajista) -> es un PRIMER read, no un veredicto. Costes MEXC 0.09% i/v
(OJO: el diagnóstico slippage_probe del 23-jul sugiere que 0.025%/lado se queda
corto en alts finas -> el coste real sería MAYOR y esto es optimista).

DEFINICIÓN no-wick (sellada aquí, antes de mirar resultados):
  range = high-low (skip si 0); body = |close-open|
  no-wick ALCISTA (long) : close>open y (open-low) <= WICK_TOL*range y body >= BODY_MIN*range
  no-wick BAJISTA (short): close<open y (high-open) <= WICK_TOL*range y body >= BODY_MIN*range
  WICK_TOL = 0.10 (mecha del lado "sin mecha" <= 10% del rango, tolera ruido de tick)
  BODY_MIN = 0.50 (cuerpo >= 50% del rango -> vela de desplazamiento real)

PRIMARIO: continuación a horizonte fijo. Para una señal en la vela i, entrada al
  CIERRE de i, retorno en la dirección d tras HOLD velas:
  ret = d*(close[i+HOLD]-close[i])/close[i]*100 - COST.  HOLD = 9 (su "≤9 velas").
  Hay continuación real si la media neta es > 0 con IC95 excluyendo cero.

SECUNDARIO (color, su modelo 1:1): entrada al cierre, stop en el extremo opuesto de
  las últimas STRUCT velas +- buffer (proxy objetivo de "estructura reciente"),
  objetivo a 1:1. Primer toque de stop/target (ambos en la misma vela -> stop).
  Con 1:1 el break-even es 50% de acierto ANTES de costes; con costes hace falta más.
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
import numpy as np
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv

COST = (0.02 + 0.025) * 2
WICK_TOL = 0.10
BODY_MIN = 0.50
HOLD = 9
STRUCT = 10
BUFFER_PCT = 0.05          # % del precio, colchón del stop
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM",
        "DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
        "1000PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
        "BTC","ETH","BNB","XRP"]


def signals(O, H, L, C):
    """Devuelve lista (i, dir) de velas no-wick."""
    out = []
    for i in range(len(C)):
        rng = H[i] - L[i]
        if rng <= 0:
            continue
        body = abs(C[i] - O[i])
        if body < BODY_MIN * rng:
            continue
        if C[i] > O[i] and (O[i] - L[i]) <= WICK_TOL * rng:
            out.append((i, 1))
        elif C[i] < O[i] and (H[i] - O[i]) <= WICK_TOL * rng:
            out.append((i, -1))
    return out


def main():
    prim, prim_dir = [], {1: [], -1: []}
    brk = []
    n_sig = 0
    tfc = config_for_timeframe(TFZConfig(), "15m")
    for sym in SYMS:
        try:
            df = fetch_ohlcv(sym + "/USDT:USDT", "15m", limit=1000, config=tfc)
        except Exception:
            continue
        O = df["open"].values.astype(float); H = df["high"].values.astype(float)
        L = df["low"].values.astype(float); C = df["close"].values.astype(float)
        n = len(C)
        for i, d in signals(O, H, L, C):
            n_sig += 1
            # PRIMARIO: continuación a HOLD velas
            if i + HOLD < n:
                r = d * (C[i + HOLD] - C[i]) / C[i] * 100 - COST
                prim.append(r); prim_dir[d].append(r)
            # SECUNDARIO: bracket 1:1 con stop proxy-estructura
            if i < STRUCT:
                continue
            entry = C[i]
            if d == 1:
                stop = L[i - STRUCT:i + 1].min() * (1 - BUFFER_PCT / 100)
            else:
                stop = H[i - STRUCT:i + 1].max() * (1 + BUFFER_PCT / 100)
            R = abs(entry - stop)
            if R <= 0:
                continue
            target = entry + d * R
            res = None
            for j in range(i + 1, n):
                hi, lo = H[j], L[j]
                hit_stop = (lo <= stop) if d == 1 else (hi >= stop)
                hit_tp = (hi >= target) if d == 1 else (lo <= target)
                if hit_stop:
                    res = -R / entry * 100 - COST; break
                if hit_tp:
                    res = R / entry * 100 - COST; break
            if res is not None:
                brk.append(res)

    def line(name, arr):
        if not arr:
            print(f"  {name}: sin datos"); return
        a = np.array(arr); se = a.std(ddof=1) / np.sqrt(len(a)) if len(a) > 1 else 0
        w = (a > 0).mean() * 100
        print(f"  {name:28s} n={len(a):5d} | acierto {w:4.1f}% | media {a.mean():+.4f}% "
              f"| IC95 [{a.mean()-1.96*se:+.4f}, {a.mean()+1.96*se:+.4f}]")

    print(f"=== EXPLORACION no-wick (retrospectiva, 42 symbols, 15m, ~10 dias) ===")
    print(f"señales no-wick detectadas: {n_sig}")
    print(f"\nPRIMARIO — continuacion a {HOLD} velas (neto {COST:.2f}%):")
    line("todas", prim)
    line("solo long (no-wick alcista)", prim_dir[1])
    line("solo short (no-wick bajista)", prim_dir[-1])
    print(f"\nSECUNDARIO — bracket 1:1 (break-even ~50% acierto ANTES de costes):")
    line("1:1 stop proxy-estructura", brk)


if __name__ == "__main__":
    main()
