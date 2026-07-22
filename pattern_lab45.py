"""PATTERN LAB — Tandas 4+5: CHARTISTAS (con swings confirmados) + VOLUMEN.
Misma metodologia; BH sobre la familia CONJUNTA 4+5 (mas conservador).
Chartistas: doble/triple techo-suelo (ruptura de neckline), HCH e invertido, bandera
alcista/bajista (asta + consolidacion + ruptura), triangulo de contraccion.
Volumen: climax (capitulacion/blow-off), divergencia precio-volumen, divergencias OBV,
pullback seco en tendencia, ruptura de 20 con/sin volumen.
Todo point-in-time (swings confirmados con retardo de orden 3; nada usa futuro).
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
ORD = 3


def detect(O, H, L, C, V):
    n = len(C)
    P = defaultdict(list)
    sma20v = np.full(n, np.nan)
    cs = np.cumsum(V)
    sma20v[19:] = (cs[19:] - np.concatenate(([0], cs[:-20]))) / 20
    csc = np.cumsum(C)
    s20 = np.full(n, np.nan)
    s20[19:] = (csc[19:] - np.concatenate(([0], csc[:-20]))) / 20
    up_tr = C > s20
    dn_tr = C < s20
    obv = np.cumsum(np.sign(np.diff(C, prepend=C[0])) * V)

    sh = []  # swings high confirmados: (idx, precio)
    sl = []
    armed_dt = armed_db = armed_hch = armed_hchi = None

    for i in range(30, n):
        j = i - ORD
        if j - ORD >= 0:
            if H[j] == H[j - ORD:i + 1].max():
                sh.append((j, H[j]))
            if L[j] == L[j - ORD:i + 1].min():
                sl.append((j, L[j]))

        # ---- doble/triple techo (necklines armadas con swings confirmados) ----
        if len(sh) >= 2 and len(sl) >= 1:
            (i1, p1), (i2, p2) = sh[-2], sh[-1]
            if 5 <= i2 - i1 <= 40 and abs(p1 - p2) / p1 <= 0.005:
                valle = min(pl for (ii, pl) in sl if i1 <= ii <= i2) if any(i1 <= ii <= i2 for ii, _ in sl) else None
                if valle:
                    armed_dt = (i2, valle)
            if len(sh) >= 3:
                (i0, p0) = sh[-3]
                if abs(p0 - p1) / p0 <= 0.007 and abs(p1 - p2) / p1 <= 0.007 and 5 <= i2 - i0 <= 80:
                    valles = [pl for (ii, pl) in sl if i0 <= ii <= i2]
                    if valles:
                        armed_dt = (i2, min(valles), "triple")
                # HCH: hombro-cabeza-hombro
                if p1 > p0 * 1.005 and p1 > p2 * 1.005 and abs(p0 - p2) / p0 <= 0.01:
                    valles = [pl for (ii, pl) in sl if i0 <= ii <= i2]
                    if valles:
                        armed_hch = (i2, min(valles))
        if len(sl) >= 2 and len(sh) >= 1:
            (i1, p1), (i2, p2) = sl[-2], sl[-1]
            if 5 <= i2 - i1 <= 40 and abs(p1 - p2) / p1 <= 0.005:
                picos = [ph for (ii, ph) in sh if i1 <= ii <= i2]
                if picos:
                    armed_db = (i2, max(picos))
            if len(sl) >= 3:
                (i0, p0) = sl[-3]
                if p1 < p0 * 0.995 and p1 < p2 * 0.995 and abs(p0 - p2) / p0 <= 0.01:
                    picos = [ph for (ii, ph) in sh if i0 <= ii <= i2]
                    if picos:
                        armed_hchi = (i2, max(picos))

        # rupturas de neckline (solo una vez por patron armado)
        if armed_dt and i > armed_dt[0] + ORD and C[i] < armed_dt[1]:
            P["triple_techo" if len(armed_dt) == 3 else "doble_techo"].append((i, -1))
            armed_dt = None
        if armed_db and i > armed_db[0] + ORD and C[i] > armed_db[1]:
            P["doble_suelo"].append((i, +1))
            armed_db = None
        if armed_hch and i > armed_hch[0] + ORD and C[i] < armed_hch[1]:
            P["hch"].append((i, -1))
            armed_hch = None
        if armed_hchi and i > armed_hchi[0] + ORD and C[i] > armed_hchi[1]:
            P["hch_invertido"].append((i, +1))
            armed_hchi = None

        # ---- bandera (asta >=5% en 10 velas + consolidacion 5-15 + ruptura) ----
        for back in (8, 12):
            j0 = i - back
            if j0 - 10 < 0:
                continue
            pole = (C[j0] - C[j0 - 10]) / C[j0 - 10]
            cons_h = H[j0:i].max(); cons_l = L[j0:i].min()
            pole_abs = abs(C[j0] - C[j0 - 10])
            if pole_abs <= 0 or (cons_h - cons_l) > 0.5 * pole_abs:
                continue
            if pole >= 0.05 and C[i] > cons_h:
                P["bandera_alcista"].append((i, +1)); break
            if pole <= -0.05 and C[i] < cons_l:
                P["bandera_bajista"].append((i, -1)); break

        # ---- triangulo de contraccion (highs bajando, lows subiendo, rango encoge) ----
        if i >= 16:
            hs = H[i - 15:i]; ls = L[i - 15:i]
            x = np.arange(15)
            mh = np.polyfit(x, hs, 1)[0]; ml = np.polyfit(x, ls, 1)[0]
            contr = (hs[-5:].max() - ls[-5:].min()) < 0.7 * (hs[:5].max() - ls[:5].min())
            if mh < 0 and ml > 0 and contr:
                if C[i] > hs.max():
                    P["triangulo_arriba"].append((i, +1))
                elif C[i] < ls.min():
                    P["triangulo_abajo"].append((i, -1))

        # ---- VOLUMEN ----
        if not np.isnan(sma20v[i]) and sma20v[i] > 0:
            rv = V[i] / sma20v[i]
            if rv >= 4:
                if C[i] < O[i] and dn_tr[i]:
                    P["climax_capitulacion"].append((i, +1))
                if C[i] > O[i] and up_tr[i]:
                    P["climax_blowoff"].append((i, -1))
            # ruptura de max20 con/sin volumen
            hh20 = H[i - 20:i].max()
            if C[i] > hh20 and C[i - 1] <= H[i - 21:i - 1].max():
                P["ruptura_con_volumen" if rv >= 2 else ("ruptura_sin_volumen" if rv < 1 else "ruptura_vol_medio")].append((i, +1))
            # pullback seco: tendencia alcista, 3 velas rojas con volumen seco
            if up_tr[i] and all(C[i - k] < O[i - k] for k in range(3)) \
                    and V[i - 2:i + 1].mean() < 0.6 * sma20v[i]:
                P["pullback_seco"].append((i, +1))
        # divergencia precio-volumen en maximos
        j20 = i - 20 + int(np.argmax(H[i - 20:i]))
        if H[i] > H[j20] and V[i] < 0.7 * V[j20]:
            P["div_precio_volumen"].append((i, -1))
        # divergencias OBV
        jl = i - 20 + int(np.argmin(L[i - 20:i]))
        if L[i] < L[jl] and obv[i] > obv[jl]:
            P["obv_div_alcista"].append((i, +1))
        jh = i - 20 + int(np.argmax(H[i - 20:i]))
        if H[i] > H[jh] and obv[i] < obv[jh]:
            P["obv_div_bajista"].append((i, -1))
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
            if len(df) < 400:
                continue
            used += 1
            O = df["open"].values.astype(float); Hh = df["high"].values.astype(float)
            Ll = df["low"].values.astype(float); C = df["close"].values.astype(float)
            V = df["volume"].values.astype(float)
            n = len(C)
            fwd = {h: (C[h:] - C[:-h]) / C[:-h] * 100 for h in HORIZONS}
            base = {h: np.nanmean(fwd[h]) for h in HORIZONS}
            half = n // 2
            for name, lst in detect(O, Hh, Ll, C, V).items():
                for i, d in lst:
                    if i + max(HORIZONS) >= n:
                        continue
                    ev[(name, tf)].append([d * (fwd[h][i] - base[h]) for h in HORIZONS] + [0 if i < half else 1])

    print(f"PATTERN LAB tandas 4+5 (chartistas+volumen) | series: {used} | h=5 | BH conjunto | edge>{COST}%\n")
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

    print(f"{'patron':22s} {'tf':>3s} {'n':>5s} {'h1':>7s} {'h5':>7s} {'h20':>7s} {'t':>6s} {'q(BH)':>7s} {'OOS':>4s}  veredicto")
    print("-" * 100)
    surv = []
    for name, tf, nn, e1, e5m, e20, t, p, agree, q in rows:
        passes = q < 0.05 and agree and e5m > COST
        tag = "*** PASA ***" if passes else ("(señal, no pasa)" if q < 0.05 and e5m > 0 else "")
        if passes:
            surv.append((name, tf))
        print(f"{name:22s} {tf:>3s} {nn:>5d} {e1:>+6.3f}% {e5m:>+6.3f}% {e20:>+6.3f}% {t:>6.2f} {q:>7.3f} {'si' if agree else 'no':>4s}  {tag}")
    print(f"\nSUPERVIVIENTES: {surv if surv else 'NINGUNO'}")


if __name__ == "__main__":
    main()
