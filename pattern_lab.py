"""PATTERN LAB — Tanda 1: PATRONES DE VELAS JAPONESAS (evento-estudio point-in-time).

Metodologia (pre-registrada, lecciones del programa de edges):
- Point-in-time: cada patron se detecta en la vela i usando SOLO velas <= i (cero futuro).
- Evento-estudio: retorno a h velas vista (h=5 PRIMARIO, fijado de antemano; h=1 y h=20
  informativos) MENOS la deriva media del propio simbolo/TF (control de regimen alcista).
- Direccion hipotetizada de antemano por patron (alcista/bajista): edge = dir * exceso.
- Anti data-snooping: p-valor unilateral + correccion Benjamini-Hochberg sobre TODOS los
  tests de la tanda (probando ~40 combinaciones, ~2 saldrian "buenas" por azar sin esto).
- OOS: el signo del edge debe COINCIDIR en la mitad antigua y la reciente.
- CRITERIO PRE-REGISTRADO para pasar a la siguiente fase (trade-sim / forward):
  BH q<0.05 Y mismo signo en ambas mitades Y |edge| a h=5 > 0.24% (costes ida y vuelta).
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
os.environ.setdefault("FREEZE_CACHE", "1")

import math
import numpy as np
from collections import defaultdict
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

UNI = [s.strip() for s in open("_universe.txt").read().split(",") if s.strip()]
TFS = ["15m", "1h"]
CANDLES = 1500
HORIZONS = [1, 5, 20]
H_PRIMARY = 5
COST = 0.24  # % ida y vuelta (comision+slippage), para el liston del criterio


def detect_patterns(O, H, L, C):
    """Devuelve dict nombre -> lista de (idx, dir) con dir +1 alcista / -1 bajista.
    Todas las condiciones usan solo velas <= idx (point-in-time)."""
    n = len(C)
    rng = np.maximum(H - L, 1e-12)
    body = np.abs(C - O)
    upw = H - np.maximum(O, C)
    low = np.minimum(O, C) - L
    bull = C > O
    bear = C < O
    sma20 = np.full(n, np.nan)
    cs = np.cumsum(C)
    sma20[19:] = (cs[19:] - np.concatenate(([0], cs[:-20]))) / 20
    up_tr = C > sma20      # contexto de tendencia (para reversales)
    dn_tr = C < sma20

    P = defaultdict(list)
    for i in range(21, n):
        r, b, uw, lw = rng[i], body[i], upw[i], low[i]
        doji = b <= 0.10 * r
        # --- una vela ---
        if doji and uw >= 0.60 * r and lw <= 0.10 * r and up_tr[i]:
            P["doji_lapida"].append((i, -1))
        if doji and lw >= 0.60 * r and uw <= 0.10 * r and dn_tr[i]:
            P["doji_libelula"].append((i, +1))
        if lw >= 2 * b and uw <= 0.15 * r and b > 0:
            if dn_tr[i]:
                P["martillo"].append((i, +1))
            elif up_tr[i]:
                P["hombre_colgado"].append((i, -1))
        if uw >= 2 * b and lw <= 0.15 * r and b > 0:
            if dn_tr[i]:
                P["martillo_invertido"].append((i, +1))
            elif up_tr[i]:
                P["estrella_fugaz"].append((i, -1))
        if b >= 0.95 * r:
            P["marubozu_alcista" if bull[i] else "marubozu_bajista"].append((i, +1 if bull[i] else -1))
        # --- dos velas ---
        pb, pr = body[i - 1], rng[i - 1]
        top_prev, bot_prev = max(O[i - 1], C[i - 1]), min(O[i - 1], C[i - 1])
        top_cur, bot_cur = max(O[i], C[i]), min(O[i], C[i])
        if bear[i - 1] and bull[i] and bot_cur <= bot_prev and top_cur >= top_prev and b > pb and dn_tr[i - 1]:
            P["envolvente_alcista"].append((i, +1))
        if bull[i - 1] and bear[i] and bot_cur <= bot_prev and top_cur >= top_prev and b > pb and up_tr[i - 1]:
            P["envolvente_bajista"].append((i, -1))
        if pb >= 0.6 * pr and top_cur <= top_prev and bot_cur >= bot_prev:
            if bear[i - 1] and dn_tr[i - 1]:
                P["harami_cross_alc" if doji else "harami_alcista"].append((i, +1))
            if bull[i - 1] and up_tr[i - 1]:
                P["harami_cross_baj" if doji else "harami_bajista"].append((i, -1))
        mid_prev = (O[i - 1] + C[i - 1]) / 2
        if bear[i - 1] and bull[i] and O[i] <= C[i - 1] and C[i] > mid_prev and C[i] < O[i - 1] and dn_tr[i - 1]:
            P["linea_penetrante"].append((i, +1))
        if bull[i - 1] and bear[i] and O[i] >= C[i - 1] and C[i] < mid_prev and C[i] > O[i - 1] and up_tr[i - 1]:
            P["nube_negra"].append((i, -1))
        tol = 0.10 * (r + pr) / 2
        if abs(L[i] - L[i - 1]) <= tol and bear[i - 1] and bull[i] and dn_tr[i - 1]:
            P["pinzas_suelo"].append((i, +1))
        if abs(H[i] - H[i - 1]) <= tol and bull[i - 1] and bear[i] and up_tr[i - 1]:
            P["pinzas_techo"].append((i, -1))
        # --- tres velas ---
        b2, r2 = body[i - 2], rng[i - 2]
        if (bear[i - 2] and b2 >= 0.6 * r2 and body[i - 1] <= 0.3 * rng[i - 1]
                and bull[i] and C[i] > (O[i - 2] + C[i - 2]) / 2 and dn_tr[i - 2]):
            P["estrella_manana"].append((i, +1))
        if (bull[i - 2] and b2 >= 0.6 * r2 and body[i - 1] <= 0.3 * rng[i - 1]
                and bear[i] and C[i] < (O[i - 2] + C[i - 2]) / 2 and up_tr[i - 2]):
            P["estrella_tarde"].append((i, -1))
        if all(bull[i - k] and body[i - k] >= 0.5 * rng[i - k] for k in range(3)) \
                and C[i] > C[i - 1] > C[i - 2] \
                and bot_cur >= bot_prev and min(O[i-1], C[i-1]) >= min(O[i-2], C[i-2]):
            P["tres_soldados"].append((i, +1))
        if all(bear[i - k] and body[i - k] >= 0.5 * rng[i - k] for k in range(3)) \
                and C[i] < C[i - 1] < C[i - 2] \
                and top_cur <= top_prev and max(O[i-1], C[i-1]) <= max(O[i-2], C[i-2]):
            P["tres_cuervos"].append((i, -1))
        if (bear[i - 2] and body[i - 2] >= 0.6 * rng[i - 2]
                and max(O[i-1], C[i-1]) <= max(O[i-2], C[i-2]) and min(O[i-1], C[i-1]) >= min(O[i-2], C[i-2])
                and bull[i] and C[i] > max(O[i - 2], C[i - 2])):
            P["tres_dentro_arriba"].append((i, +1))
        if (bull[i - 2] and body[i - 2] >= 0.6 * rng[i - 2]
                and max(O[i-1], C[i-1]) <= max(O[i-2], C[i-2]) and min(O[i-1], C[i-1]) >= min(O[i-2], C[i-2])
                and bear[i] and C[i] < min(O[i - 2], C[i - 2])):
            P["tres_dentro_abajo"].append((i, -1))
    return P


def norm_sf(t):
    """P(Z > t) unilateral, aproximacion normal."""
    return 0.5 * math.erfc(t / math.sqrt(2))


def main():
    # eventos[(patron, tf)] = lista de (signed_excess_h1, _h5, _h20, mitad)
    ev = defaultdict(list)
    used = 0
    for tf in TFS:
        tfc = config_for_timeframe(TFZConfig(), tf)
        for sym in UNI:
            try:
                df = fetch_ohlcv_cached(sym, tf, limit=CANDLES, config=tfc)
            except Exception:
                continue
            if len(df) < 300:
                continue
            used += 1
            O = df["open"].values.astype(float)
            H = df["high"].values.astype(float)
            L = df["low"].values.astype(float)
            C = df["close"].values.astype(float)
            n = len(C)
            # deriva media del simbolo/TF por horizonte (control): media de todos los fwd
            fwd = {}
            for h in HORIZONS:
                r = (C[h:] - C[:-h]) / C[:-h] * 100
                fwd[h] = r
            base = {h: np.nanmean(fwd[h]) for h in HORIZONS}
            pats = detect_patterns(O, H, L, C)
            half = n // 2
            for name, lst in pats.items():
                for i, d in lst:
                    if i + max(HORIZONS) >= n:
                        continue
                    row = []
                    for h in HORIZONS:
                        row.append(d * (fwd[h][i] - base[h]))
                    row.append(0 if i < half else 1)
                    ev[(name, tf)].append(row)

    print(f"PATTERN LAB tanda 1 (velas) | series usadas: {used} | "
          f"horizonte primario h={H_PRIMARY} velas | criterio: BH q<0.05 + OOS mismo signo + edge>{COST}%\n")

    rows = []
    for (name, tf), lst in ev.items():
        a = np.array(lst)
        if len(a) < 30:
            continue  # muestra minima
        e5 = a[:, 1]
        m = e5.mean(); sd = e5.std(ddof=1); nn = len(e5)
        t = m / (sd / math.sqrt(nn)) if sd > 0 else 0.0
        p = norm_sf(t)  # unilateral: hipotesis = edge positivo en la direccion del patron
        old = e5[a[:, 3] == 0]; new = e5[a[:, 3] == 1]
        agree = len(old) > 5 and len(new) > 5 and np.sign(old.mean()) == np.sign(new.mean()) == np.sign(m)
        rows.append([name, tf, nn, a[:, 0].mean(), m, a[:, 2].mean(), t, p, agree])

    # Benjamini-Hochberg sobre toda la tanda
    rows.sort(key=lambda r: r[7])
    mt = len(rows)
    for k, r in enumerate(rows, 1):
        r.append(r[7] * mt / k)  # q aprox
    # asegurar monotonicidad
    for k in range(len(rows) - 2, -1, -1):
        rows[k][9] = min(rows[k][9], rows[k + 1][9])

    print(f"{'patron':22s} {'tf':>3s} {'n':>5s} {'h1':>7s} {'h5':>7s} {'h20':>7s} {'t':>6s} {'q(BH)':>7s} {'OOS':>4s}  veredicto")
    print("-" * 100)
    surv = []
    for r in rows:
        name, tf, nn, e1, e5m, e20, t, p, agree, q = r
        passes = q < 0.05 and agree and abs(e5m) > COST and e5m > 0
        tag = "*** PASA ***" if passes else ("(señal, no pasa)" if q < 0.05 and e5m > 0 else "")
        if passes:
            surv.append((name, tf))
        print(f"{name:22s} {tf:>3s} {nn:>5d} {e1:>+6.3f}% {e5m:>+6.3f}% {e20:>+6.3f}% {t:>6.2f} {q:>7.3f} {'si' if agree else 'no':>4s}  {tag}")

    print(f"\nSUPERVIVIENTES (pasan el criterio pre-registrado): {surv if surv else 'NINGUNO'}")
    print("Nota: h1/h5/h20 = exceso de retorno medio en la DIRECCION del patron, ya restada la deriva del simbolo.")


if __name__ == "__main__":
    main()
