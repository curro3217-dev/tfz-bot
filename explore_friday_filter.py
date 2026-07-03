"""
EXPLORACIÓN #14: filtro de MAGNITUD del vie->sáb — prueba de 6 celdas (2026-07-03).

La anatomía (#13) mostró dosis-respuesta: el edge crece con |ret. viernes|.
HIPÓTESIS PRE-ESPECIFICADA (umbral FIJO, elegido redondo y NO ajustado): operar solo
si |retorno del viernes| >= 3%. Listón idéntico al que pasó la regla base: expectancy
positiva con IC95 excluyendo 0 en los 3 años Y en los 2 universos (6/6 celdas).
Se reporta también la cobertura (qué % de trades sobrevive al filtro).

Solo lectura; la regla sellada de weekend_paper NO cambia con esto.
Uso: python explore_friday_filter.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST = (0.02 + 0.025) * 2
UMBRAL = 3.0   # % — fijo, pre-especificado
U_ORIG = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
          "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]
U_NUEVO = ["DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
           "1000PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
           "BTC","ETH","BNB","XRP"]


def friday_trades(syms, cfg):
    rows = []
    for s in syms:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        daily = d.set_index("timestamp")["close"].resample("1D").last().dropna()
        ret = daily.pct_change()
        for t in daily.index:
            if t.weekday() != 5:
                continue
            t_fri = t - pd.Timedelta(days=1)
            if t_fri not in ret.index or pd.isna(ret.get(t)):
                continue
            fr = ret[t_fri]
            if pd.isna(fr) or fr == 0:
                continue
            rows.append({"year": t.year, "fri_abs": abs(fr) * 100,
                         "pnl": float(np.sign(fr) * ret[t] * 100 - COST)})
    return pd.DataFrame(rows)


def celda(p):
    p = np.asarray(p, dtype=float)
    if len(p) < 30:
        return f"n {len(p):4d} (pocos)      "
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    star = "*" if m - 1.96 * se > 0 else (" (neg!)" if m + 1.96 * se < 0 else " ")
    return f"{m:+.3f}{star} n{len(p):4d} [{m-1.96*se:+.2f},{m+1.96*se:+.2f}]"


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    for nombre, syms in (("UNIVERSO ORIGINAL", U_ORIG), ("UNIVERSO NUEVO", U_NUEVO)):
        df = friday_trades(syms, cfg)
        f = df[df.fri_abs >= UMBRAL]
        print(f"\n=== {nombre} — filtro |viernes| >= {UMBRAL:.0f}% "
              f"(cobertura {len(f)/len(df)*100:.0f}% de los trades) ===")
        for y in (2024, 2025, 2026):
            print(f"  {y} filtrado: {celda(f[f.year==y]['pnl'].values)}   "
                  f"| sin filtro: {celda(df[df.year==y]['pnl'].values)}")


if __name__ == "__main__":
    main()
