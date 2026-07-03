"""
EXPLORACIÓN #22: GOOGLE TRENDS — atención del público (2026-07-03).

Datos semanales de búsquedas de "bitcoin" (5 años, pytrends). HIPÓTESIS
PRE-ESPECIFICADAS (literatura de atención, Da et al. y equivalentes cripto):
  H1: pico de atención (z >= +1 sobre 52 semanas, SOLO pasado; episodios no
      solapados) -> retorno de BTC POSITIVO la semana siguiente (entra retail).
  H2: pico EXTREMO (z >= +2) -> las 4 semanas siguientes NEGATIVAS (blow-off).
La semana de Trends cierra el domingo; la posición se toma el lunes -> sin
look-ahead. IS = hasta 2024 / OOS = 2025-26 (Trends solo da 5 años).

Solo lectura. Uso: python explore_trends.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
import ccxt
from pytrends.request import TrendReq
from explore_friday_history import daily_history

COST = (0.02 + 0.025) * 2


def trends_semanal(term="bitcoin", intentos=3):
    for i in range(intentos):
        try:
            pt = TrendReq(hl="en-US", tz=0, requests_args={"verify": False})
            pt.build_payload([term], timeframe="today 5-y")
            df = pt.interest_over_time()
            if len(df):
                return df[term]
        except Exception as e:
            print(f"  intento {i+1}: {type(e).__name__}")
    raise RuntimeError("Trends no responde")


def episodios(z, cond):
    mask = cond(z)
    return z.index[mask & ~mask.shift(1, fill_value=False)]


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    if len(p) < 8:
        return f"    {lbl:12} n {len(p):3d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:12} n {len(p):3d} | win {(p>0).mean()*100:4.0f}% | "
            f"exp {m:+.2f}% [{lo:+.2f},{hi:+.2f}] {sig}")


def main():
    s = trends_semanal()
    print(f"Trends 'bitcoin': {len(s)} semanas, {s.index[0].date()} -> "
          f"{s.index[-1].date()}")
    z = ((s - s.rolling(52).mean().shift(1)) / s.rolling(52).std().shift(1)).dropna()

    ex = ccxt.binance({"enableRateLimit": True, "timeout": 20000})
    if os.environ.get("INSECURE_SSL") == "1":
        ex.verify = False
    ex.load_markets()
    c = daily_history(ex, "BTC/USDT")
    px = pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): x[4] for x in c})

    def ret_futuro(t_domingo, semanas):
        t0 = t_domingo + pd.Timedelta(days=1)          # lunes
        t1 = t0 + pd.Timedelta(weeks=semanas)
        if t0 in px.index and t1 in px.index:
            return (px[t1] - px[t0]) / px[t0] * 100 - COST
        return None

    for nombre, thr, semanas, sgn in (("H1 z>=+1, semana sig. LONG", 1.0, 1, 1),
                                      ("H2 z>=+2, 4 semanas SHORT", 2.0, 4, -1)):
        rows = []
        for t in episodios(z, lambda v, th=thr: v >= th):
            r = ret_futuro(t, semanas)   # retorno LONG neto de costes
            if r is not None:
                # short = invertir el bruto y volver a restar el coste
                pnl = r if sgn > 0 else -(r + COST) - COST
                rows.append({"y": t.year, "p": pnl})
        d = pd.DataFrame(rows)
        print(f"\n  {nombre}:")
        if not len(d):
            print("    sin episodios")
            continue
        print(stats_line(d["p"].values, "TOTAL"))
        print(stats_line(d[d.y <= 2024]["p"].values, "IS 21-24"))
        print(stats_line(d[d.y >= 2025]["p"].values, "OOS 25-26"))


if __name__ == "__main__":
    main()
