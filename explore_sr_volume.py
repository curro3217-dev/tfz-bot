"""
EXPLORACIÓN #40: SOPORTES/RESISTENCIAS HORIZONTALES + VOLUMEN (2026-07-10).

Estrategia basada EXCLUSIVAMENTE en soportes, resistencias y volumen (petición
del usuario). Diseño pre-especificado ANTES de mirar resultados:

NIVELES (100% causales, sin look-ahead):
  - Velas diarias (resample de la cache 1h). Swing high/low con k=3 días a cada
    lado -> un swing en el día i solo se CONOCE al cierre de i+3 (retardo real).
  - Cada día t se construyen niveles con los swings CONFIRMADOS de los últimos
    90 días: clúster por precio (tolerancia 0.5%, greedy como levels.py),
    mínimo 2 toques. Resistencia = clúster de highs por encima del cierre de
    ayer; soporte = clúster de lows por debajo. Se usa el nivel MÁS CERCANO.

HIPÓTESIS (4 familias x long/short, todas en la misma tanda para comparar
limpio; el filtro de volumen es la ÚNICA diferencia entre pares):
  H1 RUPTURA+VOL : cierre de t cruza la resistencia (ayer debajo) Y volumen de
                   t > 2x media 20d (desplazada) -> LONG al cierre de t.
                   Simétrico: pierde el soporte con volumen -> SHORT.
  H2 RUPTURA     : lo mismo SIN filtro de volumen (control: ¿aporta el volumen?)
  H3 REBOTE+VOL  : el low de t toca el soporte (±0.5%) y cierra POR ENCIMA, con
                   volumen > 2x media -> LONG. Simétrico en resistencia -> SHORT.
  H4 REBOTE      : lo mismo SIN filtro de volumen.

Salida: hold 3 días (cierre de t+3), como #39. Costes MEXC por trade. Una
posición por símbolo/familia (sin solapar). IS 2024-25 / OOS 2026. Control de
deriva: se imprime la media INCONDICIONAL del hold 3d por periodo (todos los
símbolo-días) para comparar contra "no hacer nada direccional". Dato
estadístico = trade (los días se comparten entre símbolos -> IC optimistas;
solo pasa de ronda lo que sobreviva claramente).

Solo lectura. Uso: python explore_sr_volume.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST = (0.02 + 0.025) * 2
HOLD_D = 3
SWING_K = 3          # días a cada lado para confirmar un swing
LOOKBACK_D = 90      # ventana de niveles
CLUSTER_TOL = 0.005  # 0.5% para agrupar swings en un nivel
TOUCH_TOL = 0.005    # 0.5% para contar "toque" en el rebote
VOL_MULT = 2.0       # volumen > 2x media 20d
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM",
        "DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
        "1000PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
        "BTC","ETH","BNB","XRP"]


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    if len(p) < 30:
        return f"    {lbl:14} n {len(p):5d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:14} n {len(p):5d} | win {(p>0).mean()*100:4.1f}% | "
            f"exp {m:+.3f}% [{lo:+.3f},{hi:+.3f}] {sig}")


def find_swings(day: pd.DataFrame, k: int):
    """Swing highs/lows con k velas a cada lado. Devuelve listas de
    (idx_del_swing, precio, idx_de_confirmación = idx+k)."""
    hi = day["high"].values
    lo = day["low"].values
    n = len(day)
    sw_hi, sw_lo = [], []
    for i in range(k, n - k):
        win_h = hi[i - k:i + k + 1]
        win_l = lo[i - k:i + k + 1]
        if hi[i] == win_h.max() and (win_h == hi[i]).sum() == 1:
            sw_hi.append((i, hi[i], i + k))
        if lo[i] == win_l.min() and (win_l == lo[i]).sum() == 1:
            sw_lo.append((i, lo[i], i + k))
    return sw_hi, sw_lo


def cluster_levels(points, tol):
    """Greedy por precio (como levels.py): devuelve [(precio_mediana, toques)]
    solo con >= 2 toques."""
    if not points:
        return []
    pts = sorted(points)
    clusters = [[pts[0]]]
    for p in pts[1:]:
        med = np.median(clusters[-1])
        if abs(p - med) / min(p, med) <= tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [(float(np.median(c)), len(c)) for c in clusters if len(c) >= 2]


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    fams = ["H1 rup+vol L", "H1 rup+vol S", "H2 ruptura L", "H2 ruptura S",
            "H3 reb+vol L", "H3 reb+vol S", "H4 rebote  L", "H4 rebote  S"]
    res = {f: [] for f in fams}
    base3 = []  # (año, retorno 3d incondicional long sin coste) para la deriva
    n_syms = 0

    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        d = d.set_index("timestamp")
        day = d.resample("1D").agg({"open": "first", "high": "max", "low": "min",
                                    "close": "last", "volume": "sum"}).dropna()
        if len(day) < LOOKBACK_D + 30:
            continue
        n_syms += 1
        sw_hi, sw_lo = find_swings(day, SWING_K)
        close = day["close"].values
        low = day["low"].values
        high = day["high"].values
        vol = day["volume"].values
        vma20 = day["volume"].rolling(20).mean().shift(1).values
        years = day.index.year.values
        n = len(day)

        for t in range(LOOKBACK_D, n - HOLD_D):
            base3.append((years[t], (close[t + HOLD_D] - close[t]) / close[t] * 100))

        # sin solapar: día del último exit por familia
        busy = {f: -1 for f in fams}

        for t in range(LOOKBACK_D, n - HOLD_D):
            c_prev, c_now = close[t - 1], close[t]
            # niveles con swings confirmados ANTES de t y dentro de la ventana
            res_pts = [p for i, p, cf in sw_hi if cf < t and i >= t - LOOKBACK_D]
            sup_pts = [p for i, p, cf in sw_lo if cf < t and i >= t - LOOKBACK_D]
            resist = [(p, tq) for p, tq in cluster_levels(res_pts, CLUSTER_TOL)
                      if p > c_prev]
            support = [(p, tq) for p, tq in cluster_levels(sup_pts, CLUSTER_TOL)
                       if p < c_prev]
            R = min((p for p, _ in resist), default=None)
            S = max((p for p, _ in support), default=None)

            hi_vol = (not np.isnan(vma20[t])) and vma20[t] > 0 and \
                     vol[t] > VOL_MULT * vma20[t]
            ret_l = (close[t + HOLD_D] - c_now) / c_now * 100 - COST
            ret_s = -(close[t + HOLD_D] - c_now) / c_now * 100 - COST
            y = years[t]

            def fire(fam, ret):
                if busy[fam] < t:
                    res[fam].append((y, ret))
                    busy[fam] = t + HOLD_D

            # RUPTURA de resistencia (long) / pérdida de soporte (short)
            if R is not None and c_now > R and c_prev <= R:
                fire("H2 ruptura L", ret_l)
                if hi_vol:
                    fire("H1 rup+vol L", ret_l)
            if S is not None and c_now < S and c_prev >= S:
                fire("H2 ruptura S", ret_s)
                if hi_vol:
                    fire("H1 rup+vol S", ret_s)

            # REBOTE en soporte (long) / rechazo en resistencia (short)
            if S is not None and low[t] <= S * (1 + TOUCH_TOL) and c_now > S \
                    and c_prev > S:
                fire("H4 rebote  L", ret_l)
                if hi_vol:
                    fire("H3 reb+vol L", ret_l)
            if R is not None and high[t] >= R * (1 - TOUCH_TOL) and c_now < R \
                    and c_prev < R:
                fire("H4 rebote  S", ret_s)
                if hi_vol:
                    fire("H3 reb+vol S", ret_s)

    print(f"\nSímbolos con datos: {n_syms}/{len(SYMS)}")
    b = np.asarray(base3, dtype=float)
    print("\n[DERIVA: hold 3d incondicional, LONG sin coste — para comparar]")
    print(stats_line([r for _, r in base3], "TODOS"))
    print(stats_line([r for y, r in base3 if y < 2026], "IS 24-25"))
    print(stats_line([r for y, r in base3 if y >= 2026], "OOS 2026"))

    for f in fams:
        rows = res[f]
        print(f"\n[{f}]")
        print(stats_line([p for _, p in rows], "TOTAL"))
        print(stats_line([p for y, p in rows if y < 2026], "IS 24-25"))
        print(stats_line([p for y, p in rows if y >= 2026], "OOS 2026"))


if __name__ == "__main__":
    main()
