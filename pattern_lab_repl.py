"""PATTERN LAB — REPLICACION de los 2 candidatos de la tanda 2 en DATOS INDEPENDIENTES.

Candidatos (definicion EXACTA de pattern_lab2.detect, sin retocar nada):
  - ruptura_max20 (primer cierre sobre el maximo de las 20 velas previas), long
  - retest_alcista (vuelve al nivel roto en <=8 velas y aguanta), long

Celdas de replicacion (datos que la tanda 2 NO vio):
  A) 20 monedas MAJORS (fuera del universo de movers), 1h, ~3000 velas
  B) las mismas majors, 4h
  C) el universo de movers, 4h (misma poblacion, agregacion distinta; independencia parcial)

CRITERIO PRE-REGISTRADO (escrito antes de ejecutar): un candidato CONFIRMA si
  (1) edge h=5 positivo en LAS TRES celdas, y
  (2) al menos una celda con q(BH sobre las 6 pruebas)<0.05 y edge>0.24%.
Si no confirma -> se archiva como ruido correlacionado (sin segundas oportunidades).
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
os.environ.setdefault("FREEZE_CACHE", "1")

import math
import numpy as np
from collections import defaultdict
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from pattern_lab2 import detect  # MISMAS definiciones, cero retoques

MOVERS = [s.strip() for s in open("_universe.txt").read().split(",") if s.strip()]
MAJORS = [f"{b}/USDT:USDT" for b in
          ("BTC ETH LTC BCH LINK ADA DOT ATOM FIL ETC TRX UNI ARB OP APT TON INJ TIA SEI ORDI").split()]
TARGETS = {"ruptura_max20", "retest_alcista"}
HORIZONS = [1, 5, 20]
COST = 0.24
CELLS = [("A_majors_1h", MAJORS, "1h", 3000),
         ("B_majors_4h", MAJORS, "4h", 1500),
         ("C_movers_4h", MOVERS, "4h", 1500)]


def norm_sf(t):
    return 0.5 * math.erfc(t / math.sqrt(2))


rows = []
for cell, uni, tf, limit in CELLS:
    tfc = config_for_timeframe(TFZConfig(), tf)
    ev = defaultdict(list)
    used = 0
    for sym in uni:
        try:
            df = fetch_ohlcv_cached(sym, tf, limit=limit, config=tfc)
        except Exception:
            continue
        if len(df) < 300:
            continue
        used += 1
        O = df["open"].values.astype(float); H = df["high"].values.astype(float)
        L = df["low"].values.astype(float); C = df["close"].values.astype(float)
        n = len(C)
        fwd = {h: (C[h:] - C[:-h]) / C[:-h] * 100 for h in HORIZONS}
        base = {h: np.nanmean(fwd[h]) for h in HORIZONS}
        half = n // 2
        for name, lst in detect(O, H, L, C).items():
            if name not in TARGETS:
                continue
            for i, d in lst:
                if i + max(HORIZONS) >= n:
                    continue
                ev[name].append([d * (fwd[h][i] - base[h]) for h in HORIZONS] + [0 if i < half else 1])
    for name in sorted(TARGETS):
        a = np.array(ev.get(name, []))
        if len(a) < 30:
            rows.append([name, cell, used, len(a), None, None, None, None, False])
            continue
        e5 = a[:, 1]
        m = e5.mean(); sd = e5.std(ddof=1); nn = len(e5)
        t = m / (sd / math.sqrt(nn)) if sd > 0 else 0.0
        old = e5[a[:, 3] == 0]; new = e5[a[:, 3] == 1]
        agree = len(old) > 5 and len(new) > 5 and np.sign(old.mean()) == np.sign(new.mean()) == np.sign(m)
        rows.append([name, cell, used, nn, a[:, 0].mean(), m, a[:, 2].mean(), t, agree])

# BH sobre las pruebas validas
valid = [r for r in rows if r[5] is not None]
valid.sort(key=lambda r: norm_sf(r[7]))
for k, r in enumerate(valid, 1):
    r.append(norm_sf(r[7]) * len(valid) / k)
for k in range(len(valid) - 2, -1, -1):
    valid[k][9] = min(valid[k][9], valid[k + 1][9])

print("REPLICACION candidatos tanda 2 | criterio: signo + en las 3 celdas Y >=1 celda q<0.05 con edge>0.24%\n")
print(f"{'candidato':ls18s}".replace("ls18s", "18s") if False else f"{'candidato':18s} {'celda':14s} {'series':>6s} {'n':>5s} {'h1':>7s} {'h5':>7s} {'h20':>7s} {'t':>6s} {'q':>6s} {'OOS':>4s}")
print("-" * 92)
per = defaultdict(dict)
for r in rows:
    name, cell, used, nn = r[0], r[1], r[2], r[3]
    if r[5] is None:
        print(f"{name:18s} {cell:14s} {used:>6d} {nn:>5d}  (muestra insuficiente)")
        continue
    e1, m, e20, t, agree = r[4], r[5], r[6], r[7], r[8]
    q = r[9] if len(r) > 9 else float('nan')
    per[name][cell] = (m, q, agree)
    print(f"{name:18s} {cell:14s} {used:>6d} {nn:>5d} {e1:>+6.3f}% {m:>+6.3f}% {e20:>+6.3f}% {t:>6.2f} {q:>6.3f} {'si' if agree else 'no':>4s}")

print("\nVEREDICTO:")
for name in sorted(TARGETS):
    cells = per.get(name, {})
    if len(cells) < 3:
        print(f"  {name}: INSUFICIENTE (faltan celdas)")
        continue
    all_pos = all(v[0] > 0 for v in cells.values())
    strong = any(v[1] < 0.05 and v[0] > COST for v in cells.values())
    print(f"  {name}: {'CONFIRMA' if all_pos and strong else 'NO confirma'} "
          f"(signo+ en 3 celdas: {'si' if all_pos else 'NO'}; celda fuerte: {'si' if strong else 'NO'})")
