"""
EXPLORACIÓN #34: EVENTOS FOMC (2026-07-04).

Fechas de anuncio verificadas en federalreserve.gov (2021-2026, 44 reuniones).
HIPÓTESIS PRE-ESPECIFICADAS (de la literatura de acciones, Lucca-Moench):
  H1 "deriva pre-FOMC": retorno POSITIVO el día antes + día del anuncio.
  H2 "resaca": los 2 días siguientes al anuncio, sin dirección clara (control).
Se mide BTC y la cesta de alts por separado (bruto, %/día por ventana), con
IS = 2021-2024 / OOS = 2025-2026. Listón operable: 0.09% i/v.

Solo lectura. Uso: python explore_fomc.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
import ccxt
from explore_friday_history import daily_history

FOMC = [
    "2021-01-27","2021-03-17","2021-04-28","2021-06-16","2021-07-28","2021-09-22",
    "2021-11-03","2021-12-15",
    "2022-01-26","2022-03-16","2022-05-04","2022-06-15","2022-07-27","2022-09-21",
    "2022-11-02","2022-12-14",
    "2023-02-01","2023-03-22","2023-05-03","2023-06-14","2023-07-26","2023-09-20",
    "2023-11-01","2023-12-13",
    "2024-01-31","2024-03-20","2024-05-01","2024-06-12","2024-07-31","2024-09-18",
    "2024-11-07","2024-12-18",
    "2025-01-29","2025-03-19","2025-05-07","2025-06-18","2025-07-30","2025-09-17",
    "2025-10-29","2025-12-10",
    "2026-01-28","2026-03-18","2026-04-29","2026-06-17",
]
ALTS = ["SOL","DOGE","ADA","LINK","AVAX","LTC","XRP","DOT","UNI","ATOM"]


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    p = p[~np.isnan(p)]
    if len(p) < 8:
        return f"    {lbl:14} n {len(p):3d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:14} n {len(p):3d} | media {m:+.2f}% [{lo:+.2f},{hi:+.2f}] {sig}")


def ventana(ret, fecha, d0, d1):
    """retorno acumulado de los días [fecha+d0 .. fecha+d1], NaN si falta alguno"""
    tot = 0.0
    for k in range(d0, d1 + 1):
        t = fecha + pd.Timedelta(days=k)
        if t not in ret.index or pd.isna(ret[t]):
            return np.nan
        tot += ret[t]
    return tot


def main():
    ex = ccxt.binance({"enableRateLimit": True, "timeout": 20000})
    if os.environ.get("INSECURE_SSL") == "1":
        ex.verify = False
    ex.load_markets()

    series = {"BTC": None, "cesta alts": None}
    c = daily_history(ex, "BTC/USDT")
    series["BTC"] = pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): x[4]
                               for x in c}).pct_change() * 100
    alts = []
    for s in ALTS:
        c = daily_history(ex, f"{s}/USDT")
        alts.append(pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): x[4]
                               for x in c}).pct_change() * 100)
    series["cesta alts"] = pd.concat(alts, axis=1).mean(axis=1)

    fechas = [pd.Timestamp(f) for f in FOMC]
    for nombre, ret in series.items():
        print(f"\n=== {nombre} alrededor del FOMC (bruto) ===")
        for lbl, d0, d1 in (("H1 pre+día (-1..0)", -1, 0),
                            ("H2 resaca (+1..+2)", 1, 2)):
            vals = [(f.year, ventana(ret, f, d0, d1)) for f in fechas]
            print(f"  {lbl}:")
            print(stats_line([v for _, v in vals], "TOTAL"))
            print(stats_line([v for y, v in vals if y <= 2024], "IS 21-24"))
            print(stats_line([v for y, v in vals if y >= 2025], "OOS 25-26"))


if __name__ == "__main__":
    main()
