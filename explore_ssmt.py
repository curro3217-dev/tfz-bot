"""
EXPLORACIÓN (retrospectiva, NO veredicto): "Quarterly Theory SSMT Strategy".

Núcleo falsable: cuando dos activos MUY correlacionados divergen (SMT) entre dos
quarters consecutivos de 90min (SSMT), el quarter siguiente (Q3) REVIERTE en la
dirección predicha. Si esa divergencia no predice nada, toda la estrategia (entrada
por engulfing/PSP, highest-prob pair, 3R) no tiene base.

Es la primera prueba CRUZADA del proyecto (dos activos), y a favor: objetivo 3R
(con 3R el break-even es ~25% de acierto, no 50% como el No Wick). En cripto el
análogo de EURUSD/GBPUSD son dos majors correlacionados (BTC/ETH el principal).

QUARTERS: 90min = 6 velas de 15m, alineados a rejilla fija (timestamp // 90min).
  Nota honesta: en FX el quarter se ancla a la apertura de sesión (Londres/NY); en
  cripto 24/7 el ancla es arbitrario -> se prueban 2 anclas (0 y 45min) como robustez.
~10 días de historia (1 régimen: julio-2026 bajista) -> PRIMER read, no veredicto.

DEFINICIÓN SSMT (sellada, antes de mirar resultados), entre quarter q y q+1:
  hh(X) = high[q+1] > high[q]   (¿hizo máximo más alto?)
  ll(X) = low[q+1]  < low[q]    (¿hizo mínimo más bajo?)
  SSMT BAJISTA (predice Q3 abajo): hh(A) != hh(B)  (uno hace HH, el otro no)
    -> par operado = el MÁS DÉBIL = el que NO hizo HH. Se pone SHORT.
  SSMT ALCISTA (predice Q3 arriba): ll(A) != ll(B)  (uno hace LL, el otro no)
    -> par operado = el MÁS FUERTE = el que NO hizo LL. Se pone LONG.
  Filtro "conflicting SSMT" (regla suya): si hay bajista Y alcista a la vez -> SKIP.
  (Se OMITEN los filtros difusos no reproducibles: news 8:30 NY, "out of tandem",
   equal highs/lows cerca del stop. Se anota.)

PRIMARIO: retorno de Q3 en la dirección predicha, sobre el par operado, entrada al
  OPEN de Q3, salida al CLOSE de Q3. ret = d*(closeQ3-openQ3)/openQ3*100 - COST.
  Hay señal real si la media neta es > 0 con IC95 excluyendo cero.

SECUNDARIO (su modelo 3R): entrada al open de Q3 del par operado, stop en el
  extremo del par que formó el SSMT (su high de q+1 si short / su low de q+1 si long),
  con suelo mínimo MIN_STOP_PCT; objetivo 3R. Primer toque en velas 15m siguientes
  (ambos en la misma vela -> stop). Con 3R el break-even ≈ 25% de acierto.
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
import numpy as np
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv

COST = (0.02 + 0.025) * 2
Q_MS = 90 * 60 * 1000          # 90 min en ms
MIN_STOP_PCT = 0.10            # suelo del stop, % del precio (~"5 pips")
RR = 3.0
PAIRS = [("BTC", "ETH"), ("ETH", "SOL"), ("BTC", "SOL"), ("BNB", "ETH")]


def _load(sym):
    tfc = config_for_timeframe(TFZConfig(), "15m")
    df = fetch_ohlcv(sym + "/USDT:USDT", "15m", limit=1000, config=tfc)
    ts_ms = df["timestamp"].astype("int64").tolist()  # datetime64[ms] -> ya es ms
    O = df["open"].astype(float).tolist(); H = df["high"].astype(float).tolist()
    L = df["low"].astype(float).tolist(); C = df["close"].astype(float).tolist()
    return {int(t): (O[i], H[i], L[i], C[i]) for i, t in enumerate(ts_ms)}


def _quarters(dA, dB, anchor_ms):
    """Agrupa timestamps comunes en quarters de 90min; devuelve lista alineada de
    dicts por quarter con high/low/open/close de A y B, en orden temporal."""
    common = sorted(set(dA) & set(dB))
    buckets = {}
    for ts in common:
        qid = (ts - anchor_ms) // Q_MS
        buckets.setdefault(qid, []).append(ts)
    out = []
    for qid in sorted(buckets):
        tss = sorted(buckets[qid])
        if len(tss) < 4:            # quarter incompleto -> fuera
            continue
        A = [dA[t] for t in tss]; B = [dB[t] for t in tss]
        out.append({
            "qid": qid, "tss": tss,
            "Ah": max(x[1] for x in A), "Al": min(x[2] for x in A),
            "Ao": A[0][0], "Ac": A[-1][3],
            "Bh": max(x[1] for x in B), "Bl": min(x[2] for x in B),
            "Bo": B[0][0], "Bc": B[-1][3]})
    return out


def _bracket(series, start_ts, d, entry, stop):
    """Camina velas 15m desde start_ts; 3R. Devuelve pnl neto o None."""
    R = abs(entry - stop)
    if R <= 0:
        return None
    target = entry + d * RR * R
    tss = sorted(t for t in series if t >= start_ts)
    for t in tss[:200]:
        _o, hi, lo, _c = series[t]
        hit_stop = (lo <= stop) if d == 1 else (hi >= stop)
        hit_tp = (hi >= target) if d == 1 else (lo <= target)
        if hit_stop:
            return d * (stop - entry) / entry * 100 - COST
        if hit_tp:
            return d * (target - entry) / entry * 100 - COST
    return None


def run(anchor_ms, label):
    prim, prim_dir = [], {1: [], -1: []}
    brk = []
    n_sig = n_conf = 0
    for a, b in PAIRS:
        try:
            dA = _load(a); dB = _load(b)
        except Exception:
            continue
        qs = _quarters(dA, dB, anchor_ms)
        for k in range(len(qs) - 2):
            q1, q2, q3 = qs[k], qs[k + 1], qs[k + 2]
            if q2["qid"] != q1["qid"] + 1 or q3["qid"] != q2["qid"] + 1:
                continue                       # quarters no adyacentes
            hhA = q2["Ah"] > q1["Ah"]; hhB = q2["Bh"] > q1["Bh"]
            llA = q2["Al"] < q1["Al"]; llB = q2["Bl"] < q1["Bl"]
            bear = hhA != hhB
            bull = llA != llB
            if bear and bull:
                n_conf += 1
                continue                        # filtro: conflicting SSMT
            if not (bear or bull):
                continue
            n_sig += 1
            if bear:
                d = -1
                weakA = not hhA                 # el que NO hizo HH = más débil
                pair = "A" if weakA else "B"
            else:
                d = 1
                strongA = not llA               # el que NO hizo LL = más fuerte
                pair = "A" if strongA else "B"
            o = q3["Ao"] if pair == "A" else q3["Bo"]
            c = q3["Ac"] if pair == "A" else q3["Bc"]
            prim.append(d * (c - o) / o * 100 - COST)
            prim_dir[d].append(d * (c - o) / o * 100 - COST)
            # 3R bracket
            entry = o
            if d == -1:
                struct = q2["Ah"] if pair == "A" else q2["Bh"]
                stop = max(struct, entry * (1 + MIN_STOP_PCT / 100))
            else:
                struct = q2["Al"] if pair == "A" else q2["Bl"]
                stop = min(struct, entry * (1 - MIN_STOP_PCT / 100))
            series = dA if pair == "A" else dB
            r = _bracket(series, q3["tss"][0], d, entry, stop)
            if r is not None:
                brk.append(r)

    def line(name, arr):
        if not arr:
            print(f"  {name}: sin datos"); return
        x = np.array(arr); se = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0
        print(f"  {name:30s} n={len(x):4d} | acierto {(x>0).mean()*100:4.1f}% | "
              f"media {x.mean():+.4f}% | IC95 [{x.mean()-1.96*se:+.4f}, {x.mean()+1.96*se:+.4f}]")

    print(f"\n=== SSMT ancla {label} (4 pares correlacionados, 90min quarters, ~10 dias) ===")
    print(f"señales SSMT: {n_sig} | descartadas por conflicting: {n_conf}")
    print("PRIMARIO — reversion en Q3 (neto, par operado):")
    line("todas", prim)
    line("alcistas (long stronger)", prim_dir[1])
    line("bajistas (short weaker)", prim_dir[-1])
    print(f"SECUNDARIO — bracket 3R (break-even ~25% acierto antes de costes):")
    line("3R", brk)


def main():
    run(0, "0min")
    run(45 * 60 * 1000, "45min")


if __name__ == "__main__":
    main()
