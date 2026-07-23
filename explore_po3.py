"""
EXPLORACIÓN (retrospectiva, NO veredicto): ICT "AMD / Power of Three (PO3)".

Núcleo falsable: tras una "manipulación" (pinchazo fuera de un rango de acumulación
que VUELVE dentro = barrido de liquidez / falso breakout), el precio REVIERTE en
sentido contrario (distribución) lo bastante para dar >=2R antes de tocar el stop
(el extremo de la manipulación). Si eso no pasa mejor que el azar, la estrategia no
tiene base — da igual la definición exacta de "2 STDV" o iFVG.

Es un patrón distinto a lo ya enterrado: no es continuación (#42) ni divergencia
cruzada (#43), es REVERSIÓN tras barrido de rango. Objetivo 2R -> break-even ~33%.

Universo FIJO (42 símbolos del weekend, sin sesgo de selección), perps MEXC, 15m,
~10 días (1 régimen: jul-2026 bajista). La estrategia es 1m NQ; en 15m el patrón es
más grueso pero igual de definible -> PRIMER read, no veredicto. Coste 0.09%.

DEFINICIÓN (sellada antes de mirar resultados):
  RANGO de acumulación = últimas K=20 velas, por CUERPOS (spec): rhigh = max(open,close),
    rlow = min(open,close) sobre la ventana. Filtro "es un rango, no tendencia":
    |close[i-1]-close[i-K]| <= 0.5*(rhigh-rlow).
  MANIPULACIÓN arriba (predice distribución ABAJO): en las últimas M=3 velas antes de
    i, alguna HIGH supera rhigh (pincha), y la vela i CIERRA de vuelta por debajo de
    rhigh (snap-back). manip_high = max high del pinchazo.
  MANIPULACIÓN abajo -> simétrico (pincha rlow, cierra por encima) -> distribución ARRIBA.
  ENTRADA (Trigger #2, box boundary retest, el objetivo sin iFVG): dentro de RETEST=5
    velas tras el snap-back, si el precio vuelve al borde (short: high>=rhigh) se entra
    en el borde. Si no hay retest -> no trade.
  STOP = manip_high (+BUFFER) para short / manip_low (-BUFFER) para long.
  OBJETIVO = 2R en sentido reversión (R = |entry-stop|). (La spec pide >=2R; el 2R es
    su mínimo. Primer toque stop/target; ambos en la misma vela -> stop, pesimista.)
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
import numpy as np
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv

COST = (0.02 + 0.025) * 2
K = 20          # ventana del rango
M = 3           # velas del pinchazo
RETEST = 5      # ventana para el retest del borde
BUFFER = 0.05   # % colchón del stop
RR = 2.0        # objetivo (minimo que exige la estrategia)
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM",
        "DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
        "1000PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
        "BTC","ETH","BNB","XRP"]


def _bracket(H, L, start, d, entry, stop, target):
    n = len(H)
    for j in range(start, n):
        hi, lo = H[j], L[j]
        hit_stop = (lo <= stop) if d == 1 else (hi >= stop)
        hit_tp = (hi >= target) if d == 1 else (lo <= target)
        if hit_stop:
            return d * (stop - entry) / entry * 100 - COST
        if hit_tp:
            return d * (target - entry) / entry * 100 - COST
    return None


def main():
    res, res_dir = [], {1: [], -1: []}
    n_sig = 0
    tfc = config_for_timeframe(TFZConfig(), "15m")
    for sym in SYMS:
        try:
            df = fetch_ohlcv(sym + "/USDT:USDT", "15m", limit=1000, config=tfc)
        except Exception:
            continue
        O = df["open"].values.astype(float); H = df["high"].values.astype(float)
        L = df["low"].values.astype(float); C = df["close"].values.astype(float)
        bodyhi = np.maximum(O, C); bodylo = np.minimum(O, C)
        n = len(C)
        for i in range(K + M, n - 1):
            w0, w1 = i - K, i               # ventana del rango [i-K, i-1]
            rhigh = bodyhi[w0:w1].max(); rlow = bodylo[w0:w1].min()
            width = rhigh - rlow
            if width <= 0:
                continue
            if abs(C[i - 1] - C[w0]) > 0.5 * width:   # filtro: debe ser rango, no tendencia
                continue
            poke = range(i - M, i)          # velas del pinchazo (antes de i)
            # manipulación ARRIBA -> short
            mh = max((H[j] for j in poke if H[j] > rhigh), default=None)
            if mh is not None and C[i] < rhigh:
                d = -1
                # retest del borde rhigh dentro de RETEST velas
                for j in range(i + 1, min(i + 1 + RETEST, n)):
                    if H[j] >= rhigh:
                        entry = rhigh; stop = mh * (1 + BUFFER / 100)
                        R = stop - entry
                        if R <= 0:
                            break
                        target = entry - RR * R
                        r = _bracket(H, L, j + 1, d, entry, stop, target)
                        if r is not None:
                            res.append(r); res_dir[d].append(r); n_sig += 1
                        break
                continue
            # manipulación ABAJO -> long
            ml = min((L[j] for j in poke if L[j] < rlow), default=None)
            if ml is not None and C[i] > rlow:
                d = 1
                for j in range(i + 1, min(i + 1 + RETEST, n)):
                    if L[j] <= rlow:
                        entry = rlow; stop = ml * (1 - BUFFER / 100)
                        R = entry - stop
                        if R <= 0:
                            break
                        target = entry + RR * R
                        r = _bracket(H, L, j + 1, d, entry, stop, target)
                        if r is not None:
                            res.append(r); res_dir[d].append(r); n_sig += 1
                        break

    def line(name, arr):
        if not arr:
            print(f"  {name}: sin datos"); return
        x = np.array(arr); se = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0
        print(f"  {name:30s} n={len(x):4d} | acierto {(x>0).mean()*100:4.1f}% | "
              f"media {x.mean():+.4f}% | IC95 [{x.mean()-1.96*se:+.4f}, {x.mean()+1.96*se:+.4f}]")

    print(f"=== EXPLORACION PO3 (retrospectiva, 42 symbols, 15m, ~10 dias) ===")
    print(f"señales (manipulacion+retest resueltas): {n_sig}")
    print(f"objetivo 2R -> break-even ~33.3% acierto ANTES de costes:")
    line("todas", res)
    line("distribucion abajo (short)", res_dir[-1])
    line("distribucion arriba (long)", res_dir[1])


if __name__ == "__main__":
    main()
