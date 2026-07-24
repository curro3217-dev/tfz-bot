"""
EXPLORACIÓN (retrospectiva, NO veredicto): el TIMING de entrada de Mark.

Pregunta falsable, nacida de DODOX y SKL (mismo coin/día/dirección: el bot entró
PRONTO y perdió, Mark esperó la RUPTURA y ganó +6/+7%):
  ¿entrar en la ruptura CONFIRMADA (una vela que CIERRA sobre el nivel) bate a
  entrar PRONTO (en el primer toque del nivel)?

El trade-off real: EARLY entra mejor de precio pero se come los fakeouts; CONFIRMED
entra peor (más arriba, tras el cierre) pero solo cuando la ruptura aguanta. ¿Cuál
gana neto? Eso es lo que Mark hace a ojo y aquí se mide.

Universo FIJO (42 símbolos del weekend), perps MEXC, 15m, ~10 días (1 régimen).
Mismo STOP y mismo OBJETIVO en las dos variantes; solo cambia el precio/timing de
entrada. Coste 0.09%. PRIMER read, no veredicto.

DEFINICIÓN (sellada):
  Consolidación = últimas K=20 velas por CUERPOS: level=max(open,close),
    llow=min(open,close). Filtro rango (no tendencia): |close[i-1]-close[i-K]|<=0.5*(level-llow),
    y el precio aún NO ha roto (close[i-1] < level).
  Ruptura buscada en las siguientes W=5 velas:
    EARLY  = primera vela con HIGH>=level -> entra en `level`.
    CONFIRMED = primera vela que CIERRA >= level -> entra en ese `close`.
  Ambas: stop = llow, objetivo = level + RR*(level-llow)  [MISMO precio para las dos].
  Long only (es continuación al alza). Primer toque stop/objetivo; empate -> stop.
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
import numpy as np
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv

COST = (0.02 + 0.025) * 2
K = 20        # ventana de consolidacion
W = 5         # ventana para que ocurra la ruptura
RR = 3.0      # objetivo (multiplo del rango de consolidacion)
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM",
        "DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
        "1000PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
        "BTC","ETH","BNB","XRP"]


def _resolve(H, L, start, entry, stop, target):
    n = len(H)
    for j in range(start, n):
        hit_stop = L[j] <= stop
        hit_tp = H[j] >= target
        if hit_stop:
            return (stop - entry) / entry * 100 - COST
        if hit_tp:
            return (target - entry) / entry * 100 - COST
    return None


def main():
    early, conf = [], []
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
        seen = set()
        for i in range(K, n - W):
            level = bodyhi[i - K:i].max(); llow = bodylo[i - K:i].min()
            rng = level - llow
            if rng <= 0 or abs(C[i - 1] - C[i - K]) > 0.5 * rng or C[i - 1] >= level:
                continue
            target = level + RR * rng
            ej = cj = None
            for j in range(i, min(i + W, n)):
                if ej is None and H[j] >= level:
                    ej = j
                if cj is None and C[j] >= level:
                    cj = j
                if ej is not None and cj is not None:
                    break
            if ej is None or ej in seen:
                continue
            seen.add(ej)
            # EARLY: entra en el nivel al primer toque
            r = _resolve(H, L, ej + 1, level, llow, target)
            if r is not None:
                early.append(r)
            # CONFIRMED: entra en el cierre de la vela que rompe (si la hay)
            if cj is not None:
                r2 = _resolve(H, L, cj + 1, float(C[cj]), llow, target)
                if r2 is not None:
                    conf.append(r2)

    def line(name, arr):
        if not arr:
            print(f"  {name}: sin datos"); return
        x = np.array(arr); se = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0
        print(f"  {name:34s} n={len(x):4d} | acierto {(x>0).mean()*100:4.1f}% | "
              f"media {x.mean():+.4f}% | IC95 [{x.mean()-1.96*se:+.4f}, {x.mean()+1.96*se:+.4f}]")

    print("=== TIMING: entrar PRONTO vs esperar la RUPTURA CONFIRMADA ===")
    print("(42 symbols, 15m, ~10 dias, objetivo 3R, mismo stop/objetivo, neto 0.09%)")
    line("EARLY (primer toque del nivel)", early)
    line("CONFIRMED (cierre sobre el nivel)", conf)
    if early and conf:
        de = np.array(early).mean(); dc = np.array(conf).mean()
        print(f"\n  diferencia CONFIRMED - EARLY: {dc-de:+.4f}%/trade "
              f"({'esperar la ruptura AYUDA' if dc>de else 'esperar NO ayuda'})")


if __name__ == "__main__":
    main()
