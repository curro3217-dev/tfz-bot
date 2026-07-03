"""
EXPLORACIÓN #19: FESTIVOS de la bolsa USA — test del MECANISMO (2026-07-03).

Si el vie->sáb existe porque el fin de semana no operan las instituciones (ronda 8:
las anomalías de días laborables murieron con los ETFs), los festivos NYSE entre
semana deberían comportarse como sábados. HIPÓTESIS PRE-ESPECIFICADA: en un festivo
NYSE, ir en la dirección del retorno del día anterior (mismo esquema que el vie->sáb)
da expectancy POSITIVA. Se reporta aparte el subgrupo de festivos en lunes (su día
previo es domingo, también sin instituciones -> señal más débil en teoría).

Universo: los 42 de weekend_paper, velas 1h de la cache (2024 -> hoy), neto MEXC.
Solo lectura. Uso: python explore_holidays.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST = (0.02 + 0.025) * 2
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM",
        "DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
        "1000PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
        "BTC","ETH","BNB","XRP"]
# Festivos NYSE 2024-2026 (cerrado todo el día, entre semana)
FESTIVOS = [
    "2024-01-01","2024-01-15","2024-02-19","2024-03-29","2024-05-27","2024-06-19",
    "2024-07-04","2024-09-02","2024-11-28","2024-12-25",
    "2025-01-01","2025-01-20","2025-02-17","2025-04-18","2025-05-26","2025-06-19",
    "2025-07-04","2025-09-01","2025-11-27","2025-12-25",
    "2026-01-01","2026-01-19","2026-02-16","2026-04-03","2026-05-25","2026-06-19",
    "2026-07-03",
]


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    if len(p) < 20:
        return f"  {lbl:28} n {len(p):4d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"  {lbl:28} n {len(p):4d} | win {(p>0).mean()*100:4.1f}% | "
            f"exp {m:+.3f}% [{lo:+.3f},{hi:+.3f}] {sig}")


def main():
    festivos = {pd.Timestamp(f) for f in FESTIVOS}
    cfg = config_for_timeframe(TFZConfig(), "1h")
    rows = []
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        daily = d.set_index("timestamp")["close"].resample("1D").last().dropna()
        ret = daily.pct_change()
        for t in festivos:
            t_prev = t - pd.Timedelta(days=1)
            if t not in ret.index or t_prev not in ret.index:
                continue
            pr, hr = ret[t_prev], ret[t]
            if pd.isna(pr) or pd.isna(hr) or pr == 0:
                continue
            rows.append({"fecha": t, "lunes": t.weekday() == 0,
                         "pnl": float(np.sign(pr) * hr * 100 - COST)})
    df = pd.DataFrame(rows)
    print(f"=== MOMENTUM EN FESTIVOS NYSE (42 símbolos, {df['fecha'].nunique()} "
          f"festivos con datos, neto) ===")
    print(stats_line(df["pnl"].values, "TODOS los festivos"))
    print(stats_line(df[~df.lunes]["pnl"].values, "festivos NO-lunes (señal fuerte)"))
    print(stats_line(df[df.lunes]["pnl"].values, "festivos en lunes"))
    print("\nControl (contexto): el mismo esquema en TODOS los días laborables no")
    print("festivos ya se midió (~plano). El vie->sáb del mismo periodo: +0.5%.")
    por_fecha = df.groupby("fecha")["pnl"].mean().sort_values()
    print(f"peor festivo: {por_fecha.index[0].date()} {por_fecha.iloc[0]:+.2f}% | "
          f"mejor: {por_fecha.index[-1].date()} {por_fecha.iloc[-1]:+.2f}%")


if __name__ == "__main__":
    main()
