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


def _bracket(H, L, start, d, entry, stop, target, cost):
    """Devuelve (net_pct, win_bool, gross_R) o None."""
    n = len(H)
    R = abs(entry - stop)
    for j in range(start, n):
        hi, lo = H[j], L[j]
        hit_stop = (lo <= stop) if d == 1 else (hi >= stop)
        hit_tp = (hi >= target) if d == 1 else (lo <= target)
        if hit_stop:
            return -R / entry * 100 - cost, False, -1.0
        if hit_tp:
            return d * (target - entry) / entry * 100 - cost, True, RR
    return None


def _signals(df):
    """Devuelve lista de trades: (R_pct, net_gross_cost0_pct, win_bool, gross_R)."""
    O = df["open"].values.astype(float); H = df["high"].values.astype(float)
    L = df["low"].values.astype(float); C = df["close"].values.astype(float)
    bodyhi = np.maximum(O, C); bodylo = np.minimum(O, C)
    n = len(C); out = []
    for i in range(K + M, n - 1):
        rhigh = bodyhi[i - K:i].max(); rlow = bodylo[i - K:i].min()
        width = rhigh - rlow
        if width <= 0 or abs(C[i - 1] - C[i - K]) > 0.5 * width:
            continue
        poke = range(i - M, i)
        mh = max((H[j] for j in poke if H[j] > rhigh), default=None)
        if mh is not None and C[i] < rhigh:
            for j in range(i + 1, min(i + 1 + RETEST, n)):
                if H[j] >= rhigh:
                    entry = rhigh; stop = mh * (1 + BUFFER / 100); R = stop - entry
                    if R <= 0:
                        break
                    b = _bracket(H, L, j + 1, -1, entry, stop, entry - RR * R, 0.0)
                    if b:
                        out.append((R / entry * 100, b[0], b[1], b[2]))
                    break
            continue
        ml = min((L[j] for j in poke if L[j] < rlow), default=None)
        if ml is not None and C[i] > rlow:
            for j in range(i + 1, min(i + 1 + RETEST, n)):
                if L[j] <= rlow:
                    entry = rlow; stop = ml * (1 - BUFFER / 100); R = entry - stop
                    if R <= 0:
                        break
                    b = _bracket(H, L, j + 1, 1, entry, stop, entry + RR * R, 0.0)
                    if b:
                        out.append((R / entry * 100, b[0], b[1], b[2]))
                    break
    return out


def run(tf):
    rows = []
    tfc = config_for_timeframe(TFZConfig(), tf)
    for sym in SYMS:
        try:
            df = fetch_ohlcv(sym + "/USDT:USDT", tf, limit=1000, config=tfc)
        except Exception:
            continue
        rows += _signals(df)
    if not rows:
        print(f"  {tf}: sin datos"); return
    a = np.array(rows)                 # cols: R_pct, gross_pct(cost0), win, gross_R
    Rp = a[:, 0]; grossR = a[:, 3]; win = a[:, 2]
    def net(cost):
        x = a[:, 1] - cost             # aplicar coste i/v sobre el bruto sin coste
        se = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0
        return x.mean(), x.mean() - 1.96 * se, x.mean() + 1.96 * se
    print(f"\n=== {tf} (n={len(a)}) ===")
    print(f"  R (stop) mediana {np.median(Rp):.3f}% | bruto {grossR.mean():+.3f} R/trade "
          f"| win {win.mean()*100:.1f}% (2R -> be 33%)")
    for cost, lab in [(COST, "coste 0.09% (optimista)"),
                      (0.24, "coste 0.24% (slippage realista)")]:
        m, lo, hi = net(cost)
        print(f"  neto {lab:32s}: {m:+.4f}% | IC95 [{lo:+.4f}, {hi:+.4f}] "
              f"| coste/R {cost/np.median(Rp):.2f}")


def main():
    print("=== PO3 por timeframe (42 symbols, ~1000 velas c/u, objetivo 2R) ===")
    for tf in ("15m", "1h", "4h", "1d"):
        run(tf)


if __name__ == "__main__":
    main()
