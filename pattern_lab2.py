"""PATTERN LAB — Tanda 2: ESTRUCTURA / PRICE ACTION (evento-estudio point-in-time).

Misma metodologia pre-registrada que la tanda 1 (pattern_lab.py):
- deteccion solo-pasado; exceso vs deriva del simbolo/TF; h=5 primario; p unilateral;
- Benjamini-Hochberg por tanda; OOS por mitades; liston de costes 0.24%.
Patrones: inside bar (ruptura arriba/abajo), outside bar, pin bar, ruptura de maximo/
minimo de 20 velas, fakeout (ruptura intrabar fallida), retest de nivel roto, BOS
(ruptura de swing confirmado) y CHoCH (BOS contra la tendencia previa).
Los swings se usan CONFIRMADOS (orden 3 -> conocidos 3 velas despues), sin futuro.
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
COST = 0.24


def detect(O, H, L, C):
    n = len(C)
    rng = np.maximum(H - L, 1e-12)
    upw = H - np.maximum(O, C)
    low = np.minimum(O, C) - L
    bull = C > O
    bear = C < O
    sma20 = np.full(n, np.nan)
    cs = np.cumsum(C)
    sma20[19:] = (cs[19:] - np.concatenate(([0], cs[:-20]))) / 20
    up_tr = C > sma20
    dn_tr = C < sma20

    # maximos/minimos de las 20 velas ANTERIORES (sin incluir la actual)
    hh20 = np.full(n, np.nan)
    ll20 = np.full(n, np.nan)
    for i in range(20, n):
        hh20[i] = H[i - 20:i].max()
        ll20[i] = L[i - 20:i].min()

    P = defaultdict(list)
    last_bo_up = None   # (idx, nivel) de la ultima ruptura alcista de 20
    last_bo_dn = None
    last_sh = None      # ultimo swing high CONFIRMADO (nivel)
    last_sl = None
    ORD = 3

    for i in range(25, n):
        # swings confirmados: la vela i-ORD es swing si es extremo de [i-2*ORD .. i]
        j = i - ORD
        if j - ORD >= 0:
            win_h = H[j - ORD: i + 1]
            win_l = L[j - ORD: i + 1]
            if H[j] == win_h.max():
                last_sh = H[j]
            if L[j] == win_l.min():
                last_sl = L[j]

        # inside bar (i-1 dentro de i-2) + ruptura en i
        if H[i - 1] <= H[i - 2] and L[i - 1] >= L[i - 2]:
            if C[i] > H[i - 2]:
                P["inside_ruptura_arriba"].append((i, +1))
            elif C[i] < L[i - 2]:
                P["inside_ruptura_abajo"].append((i, -1))

        # outside bar (envuelve el rango anterior), direccion del cierre
        if H[i] > H[i - 1] and L[i] < L[i - 1]:
            if bull[i]:
                P["outside_alcista"].append((i, +1))
            elif bear[i]:
                P["outside_bajista"].append((i, -1))

        # pin bar (mecha >= 2/3 del rango, cierre en el tercio opuesto)
        if low[i] >= 0.66 * rng[i] and C[i] >= L[i] + 0.66 * rng[i] and dn_tr[i]:
            P["pin_bar_alcista"].append((i, +1))
        if upw[i] >= 0.66 * rng[i] and C[i] <= L[i] + 0.34 * rng[i] and up_tr[i]:
            P["pin_bar_bajista"].append((i, -1))

        # ruptura de maximo/minimo de 20 velas (primer cierre fuera)
        if not np.isnan(hh20[i]):
            if C[i] > hh20[i] and C[i - 1] <= hh20[i - 1]:
                P["ruptura_max20"].append((i, +1))
                last_bo_up = (i, hh20[i])
            if C[i] < ll20[i] and C[i - 1] >= ll20[i - 1]:
                P["ruptura_min20"].append((i, -1))
                last_bo_dn = (i, ll20[i])

            # fakeout: rompe intrabar pero CIERRA de vuelta dentro
            if H[i] > hh20[i] and C[i] < hh20[i]:
                P["fakeout_techo"].append((i, -1))
            if L[i] < ll20[i] and C[i] > ll20[i]:
                P["fakeout_suelo"].append((i, +1))

        # retest del nivel roto (dentro de 8 velas tras la ruptura): toca y aguanta
        if last_bo_up and 0 < i - last_bo_up[0] <= 8:
            lvl = last_bo_up[1]
            if L[i] <= lvl * 1.002 and C[i] > lvl:
                P["retest_alcista"].append((i, +1))
                last_bo_up = None
        if last_bo_dn and 0 < i - last_bo_dn[0] <= 8:
            lvl = last_bo_dn[1]
            if H[i] >= lvl * 0.998 and C[i] < lvl:
                P["retest_bajista"].append((i, -1))
                last_bo_dn = None

        # BOS / CHoCH sobre swings confirmados
        if last_sh is not None and C[i] > last_sh and C[i - 1] <= last_sh:
            if dn_tr[i]:
                P["choch_alcista"].append((i, +1))
            else:
                P["bos_alcista"].append((i, +1))
            last_sh = None
        if last_sl is not None and C[i] < last_sl and C[i - 1] >= last_sl:
            if up_tr[i]:
                P["choch_bajista"].append((i, -1))
            else:
                P["bos_bajista"].append((i, -1))
            last_sl = None
    return P


def norm_sf(t):
    return 0.5 * math.erfc(t / math.sqrt(2))


def main():
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
            O = df["open"].values.astype(float); Hh = df["high"].values.astype(float)
            Ll = df["low"].values.astype(float); C = df["close"].values.astype(float)
            n = len(C)
            fwd = {h: (C[h:] - C[:-h]) / C[:-h] * 100 for h in HORIZONS}
            base = {h: np.nanmean(fwd[h]) for h in HORIZONS}
            half = n // 2
            for name, lst in detect(O, Hh, Ll, C).items():
                for i, d in lst:
                    if i + max(HORIZONS) >= n:
                        continue
                    ev[(name, tf)].append([d * (fwd[h][i] - base[h]) for h in HORIZONS] + [0 if i < half else 1])

    print(f"PATTERN LAB tanda 2 (estructura/price action) | series: {used} | h=5 primario | "
          f"criterio: BH q<0.05 + OOS + edge>{COST}%\n")
    rows = []
    for (name, tf), lst in ev.items():
        a = np.array(lst)
        if len(a) < 30:
            continue
        e5 = a[:, 1]
        m = e5.mean(); sd = e5.std(ddof=1); nn = len(e5)
        t = m / (sd / math.sqrt(nn)) if sd > 0 else 0.0
        p = norm_sf(t)
        old = e5[a[:, 3] == 0]; new = e5[a[:, 3] == 1]
        agree = len(old) > 5 and len(new) > 5 and np.sign(old.mean()) == np.sign(new.mean()) == np.sign(m)
        rows.append([name, tf, nn, a[:, 0].mean(), m, a[:, 2].mean(), t, p, agree])
    rows.sort(key=lambda r: r[7])
    mt = len(rows)
    for k, r in enumerate(rows, 1):
        r.append(r[7] * mt / k)
    for k in range(len(rows) - 2, -1, -1):
        rows[k][9] = min(rows[k][9], rows[k + 1][9])

    print(f"{'patron':24s} {'tf':>3s} {'n':>5s} {'h1':>7s} {'h5':>7s} {'h20':>7s} {'t':>6s} {'q(BH)':>7s} {'OOS':>4s}  veredicto")
    print("-" * 102)
    surv = []
    for name, tf, nn, e1, e5m, e20, t, p, agree, q in rows:
        passes = q < 0.05 and agree and e5m > COST
        tag = "*** PASA ***" if passes else ("(señal, no pasa)" if q < 0.05 and e5m > 0 else "")
        if passes:
            surv.append((name, tf))
        print(f"{name:24s} {tf:>3s} {nn:>5d} {e1:>+6.3f}% {e5m:>+6.3f}% {e20:>+6.3f}% {t:>6.2f} {q:>7.3f} {'si' if agree else 'no':>4s}  {tag}")
    print(f"\nSUPERVIVIENTES: {surv if surv else 'NINGUNO'}")


if __name__ == "__main__":
    main()
