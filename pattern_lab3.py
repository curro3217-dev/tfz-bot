"""PATTERN LAB — Tanda 3: PATRONES DE INDICADORES (evento-estudio point-in-time).

Misma metodologia pre-registrada (h=5 primario, exceso vs deriva, BH, OOS, liston costes).
Patrones: RSI saliendo de sobreventa/sobrecompra, divergencias regulares y ocultas de RSI,
cruces MACD, cruce dorado/de la muerte (SMA50/200), squeeze de Bollinger con ruptura,
toques de banda (reversion), y cruce EMA 9/21. Todos los indicadores son rolling (solo pasado).
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


def ema(x, span):
    a = 2.0 / (span + 1)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def rsi_wilder(C, period=14):
    d = np.diff(C, prepend=C[0])
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    au = np.empty_like(C); ad = np.empty_like(C)
    au[0] = up[0]; ad[0] = dn[0]
    a = 1.0 / period
    for i in range(1, len(C)):
        au[i] = a * up[i] + (1 - a) * au[i - 1]
        ad[i] = a * dn[i] + (1 - a) * ad[i - 1]
    rs = au / np.maximum(ad, 1e-12)
    return 100 - 100 / (1 + rs)


def sma(x, p):
    out = np.full(len(x), np.nan)
    cs = np.cumsum(x)
    out[p - 1:] = (cs[p - 1:] - np.concatenate(([0], cs[:-p]))) / p
    return out


def detect(O, H, L, C):
    n = len(C)
    R = rsi_wilder(C)
    macd = ema(C, 12) - ema(C, 26)
    sig = ema(macd, 9)
    s20, s50, s200 = sma(C, 20), sma(C, 50), sma(C, 200)
    std20 = np.full(n, np.nan)
    for i in range(19, n):
        std20[i] = C[i - 19:i + 1].std(ddof=0)
    bb_up = s20 + 2 * std20
    bb_dn = s20 - 2 * std20
    bw = (bb_up - bb_dn) / np.maximum(s20, 1e-12)
    e9, e21 = ema(C, 9), ema(C, 21)
    up_tr = C > s20
    dn_tr = C < s20

    P = defaultdict(list)
    for i in range(220, n):
        # RSI saliendo de zonas extremas
        if R[i - 1] < 30 <= R[i]:
            P["rsi_sale_sobreventa"].append((i, +1))
        if R[i - 1] > 70 >= R[i]:
            P["rsi_sale_sobrecompra"].append((i, -1))

        # divergencias RSI vs precio (ventana 20, referencia = extremo previo)
        j = i - 20 + int(np.argmin(L[i - 20:i]))
        if L[i] < L[j] and R[i] > R[j] + 2:
            P["divergencia_alcista"].append((i, +1))
        if L[i] > L[j] and R[i] < R[j] - 2 and up_tr[i]:
            P["div_oculta_alcista"].append((i, +1))
        k = i - 20 + int(np.argmax(H[i - 20:i]))
        if H[i] > H[k] and R[i] < R[k] - 2:
            P["divergencia_bajista"].append((i, -1))
        if H[i] < H[k] and R[i] > R[k] + 2 and dn_tr[i]:
            P["div_oculta_bajista"].append((i, -1))

        # cruces MACD
        if macd[i - 1] <= sig[i - 1] and macd[i] > sig[i]:
            P["macd_cruce_alcista"].append((i, +1))
        if macd[i - 1] >= sig[i - 1] and macd[i] < sig[i]:
            P["macd_cruce_bajista"].append((i, -1))

        # cruce dorado / de la muerte
        if not np.isnan(s200[i]) and s50[i - 1] <= s200[i - 1] and s50[i] > s200[i]:
            P["cruce_dorado"].append((i, +1))
        if not np.isnan(s200[i]) and s50[i - 1] >= s200[i - 1] and s50[i] < s200[i]:
            P["cruce_muerte"].append((i, -1))

        # squeeze de Bollinger (ancho en minimo de 100) + ruptura
        if not np.isnan(bw[i]) and bw[i - 1] <= np.nanmin(bw[i - 100:i]) * 1.10:
            if C[i - 1] <= bb_up[i - 1] and C[i] > bb_up[i]:
                P["squeeze_ruptura_arriba"].append((i, +1))
            if C[i - 1] >= bb_dn[i - 1] and C[i] < bb_dn[i]:
                P["squeeze_ruptura_abajo"].append((i, -1))

        # toque de banda (reversion clasica)
        if C[i - 1] >= bb_dn[i - 1] and C[i] < bb_dn[i]:
            P["bb_toque_inferior"].append((i, +1))
        if C[i - 1] <= bb_up[i - 1] and C[i] > bb_up[i]:
            P["bb_toque_superior"].append((i, -1))

        # cruce EMA 9/21
        if e9[i - 1] <= e21[i - 1] and e9[i] > e21[i]:
            P["ema9_21_alcista"].append((i, +1))
        if e9[i - 1] >= e21[i - 1] and e9[i] < e21[i]:
            P["ema9_21_bajista"].append((i, -1))
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
            n = len(C)
            fwd = {h: (C[h:] - C[:-h]) / C[:-h] * 100 for h in HORIZONS}
            base = {h: np.nanmean(fwd[h]) for h in HORIZONS}
            half = n // 2
            for name, lst in detect(O, Hh, Ll, C).items():
                for i, d in lst:
                    if i + max(HORIZONS) >= n:
                        continue
                    ev[(name, tf)].append([d * (fwd[h][i] - base[h]) for h in HORIZONS] + [0 if i < half else 1])

    print(f"PATTERN LAB tanda 3 (indicadores) | series: {used} | h=5 primario | criterio: BH q<0.05 + OOS + edge>{COST}%\n")
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
