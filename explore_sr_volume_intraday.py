"""
EXPLORACIÓN #41: S/R + VOLUMEN INTRADÍA, VENTANA DE 2 HORAS (2026-07-10).

Variante de la #40 adaptada a la restricción del usuario: operar SOLO ~2 horas
al día y cerrar TODO antes de acabar la ventana (nada queda abierto).

VENTANA: las 2 horas UTC consecutivas con MÁS volumen mediano negociado en
todo el periodo (criterio objetivo que NO mira retornos; se imprime la tabla
de volumen por hora para que el usuario pueda elegir otra ventana — la
constante WINDOW_START_UTC se puede cambiar y re-ejecutar).

NIVELES: idénticos a la #40 (100% causales): swings diarios k=3 confirmados
con retardo, clúster 0.5%, mín 2 toques, ventana 90 días. Se calculan una vez
al día con datos de días ANTERIORES.

SESIÓN de 2 velas 1h [t1, t2]. Dos momentos de entrada, ambos al CIERRE de la
vela (señal y volumen ya conocidos, sin mirar dentro de la vela):
  - al cierre de t0 (la vela previa a la sesión) -> hold 2h
  - al cierre de t1 -> hold 1h
Salida SIEMPRE al cierre de t2 (fin de sesión). Máx 1 trade/día por familia.

HIPÓTESIS (mismas 8 familias que #40; la única diferencia con/sin volumen es
el filtro: volumen de la vela > 2x la media de ESA MISMA hora en los últimos
20 días — corrige el patrón diario de volumen; desplazada, causal):
  H1 rup+vol / H2 ruptura / H3 reb+vol / H4 rebote, cada una L y S.

Costes MEXC por trade. IS 2024-25 / OOS 2026. Deriva: retorno incondicional
de la sesión (entrar cierre t0, salir cierre t2, long sin coste). Dato
estadístico = trade (símbolos comparten día -> IC optimistas).

Solo lectura. Uso: python explore_sr_volume_intraday.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST = (0.02 + 0.025) * 2
SWING_K = 3
LOOKBACK_D = 90
CLUSTER_TOL = 0.005
TOUCH_TOL = 0.005
VOL_MULT = 2.0
WINDOW_START_UTC = None  # None = auto (2h consecutivas con más volumen)
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
    data = {}
    volhour = {}  # hora UTC -> lista de volúmenes en USDT (mediana luego)
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        d = d.set_index("timestamp")
        data[s] = d
        usd = d["volume"] * d["close"]
        for h, g in usd.groupby(d.index.hour):
            volhour.setdefault(h, []).append(float(g.median()))

    # ---- elección de ventana por volumen (mediana entre símbolos, normalizada)
    med = {h: float(np.median(v)) for h, v in volhour.items()}
    tot = sum(med.values())
    print("\n[VOLUMEN por hora UTC — mediana entre símbolos, % del día]"
          "  (Madrid verano = UTC+2)")
    for h in range(24):
        pct = med.get(h, 0) / tot * 100
        bar = "#" * int(round(pct * 4))
        print(f"    {h:02d} UTC ({(h+2)%24:02d} Madrid) {pct:4.1f}% {bar}")
    if WINDOW_START_UTC is None:
        best = max(range(24), key=lambda h: med.get(h, 0) + med.get((h+1) % 24, 0))
    else:
        best = WINDOW_START_UTC
    t1h, t2h = best, (best + 1) % 24
    t0h = (best - 1) % 24
    print(f"\nVENTANA elegida: {t1h:02d}:00-{(t2h+1)%24:02d}:00 UTC "
          f"= {(t1h+2)%24:02d}:00-{(t2h+3)%24:02d}:00 Madrid (verano). "
          f"Señales al cierre de {t0h:02d}h y {t1h:02d}h UTC; todo cerrado "
          f"al cierre de {t2h:02d}h UTC.")

    fams = ["H1 rup+vol L", "H1 rup+vol S", "H2 ruptura L", "H2 ruptura S",
            "H3 reb+vol L", "H3 reb+vol S", "H4 rebote  L", "H4 rebote  S"]
    res = {f: [] for f in fams}
    base = []

    for s, d in data.items():
        day = d.resample("1D").agg({"open": "first", "high": "max", "low": "min",
                                    "close": "last", "volume": "sum"}).dropna()
        if len(day) < LOOKBACK_D + 30:
            continue
        sw_hi, sw_lo = find_swings(day, SWING_K)
        dclose = day["close"].values
        didx = {t: i for i, t in enumerate(day.index)}

        hh = d.copy()
        hh["hour"] = hh.index.hour
        # media de volumen de la MISMA hora, últimos 20 días, desplazada
        hh["vma_hora"] = hh.groupby("hour")["volume"].transform(
            lambda x: x.rolling(20).mean().shift(1))
        c = hh["close"].values
        lo = hh["low"].values
        hi = hh["high"].values
        vol = hh["volume"].values
        vma = hh["vma_hora"].values
        hours = hh["hour"].values
        times = hh.index
        n = len(hh)

        # niveles por día (causales), cacheados
        lvl_cache = {}

        def levels_for(dt):
            key = dt.normalize()
            if key in lvl_cache:
                return lvl_cache[key]
            t = didx.get(key)
            out = (None, None)
            if t is not None and t >= LOOKBACK_D:
                cp = dclose[t - 1]
                rp = [p for i, p, cf in sw_hi if cf < t and i >= t - LOOKBACK_D]
                sp = [p for i, p, cf in sw_lo if cf < t and i >= t - LOOKBACK_D]
                Rs = [p for p, _ in cluster_levels(rp, CLUSTER_TOL) if p > cp]
                Ss = [p for p, _ in cluster_levels(sp, CLUSTER_TOL) if p < cp]
                out = (min(Rs, default=None), max(Ss, default=None))
            lvl_cache[key] = out
            return out

        for b in range(25, n - 2):
            if hours[b] not in (t0h, t1h):
                continue
            # localizar el cierre de t2 (fin de sesión)
            off = 2 if hours[b] == t0h else 1
            if b + off >= n:
                continue
            # comprobar que las velas siguientes son consecutivas (sin huecos)
            if (times[b + off] - times[b]).total_seconds() != off * 3600:
                continue
            R, S = levels_for(times[b])
            if R is None and S is None:
                continue
            exit_px = c[b + off]
            ret_l = (exit_px - c[b]) / c[b] * 100 - COST
            ret_s = -(exit_px - c[b]) / c[b] * 100 - COST
            y = times[b].year
            hi_vol = (not np.isnan(vma[b])) and vma[b] > 0 and \
                     vol[b] > VOL_MULT * vma[b]

            if hours[b] == t0h:
                base.append((y, (exit_px - c[b]) / c[b] * 100))

            day_key = times[b].normalize()

            def fire(fam, ret):
                if not res[fam] or res[fam][-1][2] != day_key:
                    res[fam].append((y, ret, day_key))

            if R is not None and c[b] > R and c[b - 1] <= R:
                fire("H2 ruptura L", ret_l)
                if hi_vol:
                    fire("H1 rup+vol L", ret_l)
            if S is not None and c[b] < S and c[b - 1] >= S:
                fire("H2 ruptura S", ret_s)
                if hi_vol:
                    fire("H1 rup+vol S", ret_s)
            if S is not None and lo[b] <= S * (1 + TOUCH_TOL) and c[b] > S \
                    and c[b - 1] > S:
                fire("H4 rebote  L", ret_l)
                if hi_vol:
                    fire("H3 reb+vol L", ret_l)
            if R is not None and hi[b] >= R * (1 - TOUCH_TOL) and c[b] < R \
                    and c[b - 1] < R:
                fire("H4 rebote  S", ret_s)
                if hi_vol:
                    fire("H3 reb+vol S", ret_s)

    print(f"\nSímbolos con datos: {len(data)}/{len(SYMS)}")
    print("\n[DERIVA: sesión completa (2h) incondicional, LONG sin coste]")
    print(stats_line([r for _, r in base], "TODOS"))
    print(stats_line([r for y, r in base if y < 2026], "IS 24-25"))
    print(stats_line([r for y, r in base if y >= 2026], "OOS 2026"))

    for f in fams:
        rows = res[f]
        print(f"\n[{f}]")
        print(stats_line([p for _, p, _ in rows], "TOTAL"))
        print(stats_line([p for y, p, _ in rows if y < 2026], "IS 24-25"))
        print(stats_line([p for y, p, _ in rows if y >= 2026], "OOS 2026"))


if __name__ == "__main__":
    main()
