"""
EXPLORACIÓN #15: DVOL de Deribit (volatilidad implícita, el "VIX cripto") (2026-07-03).

HIPÓTESIS PRE-ESPECIFICADAS (antes de mirar):
  H1: régimen de DVOL ALTO (por encima de la mediana móvil de 90 días, SOLO pasado)
      -> el retorno del universo al día siguiente es peor (risk-off persiste).
  H2: el momentum vie->sáb es MÁS FUERTE en régimen de DVOL alto (encaja con la
      dosis-respuesta por magnitud del viernes que mostró la anatomía #13).
Umbral móvil solo-pasado (mediana 90d) -> sin look-ahead. Split IS 2024-25 / OOS 2026.

Solo lectura. Uso: python explore_dvol.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import time
import numpy as np
import pandas as pd
import ccxt
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST = (0.02 + 0.025) * 2
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]


def dvol_diario():
    """DVOL diario de BTC via endpoint crudo (ccxt fetch_volatility_history ignora
    los parametros y solo da ~16 dias horarios; el endpoint con resolution=1D da
    ~900 dias de OHLC del indice; usamos el cierre)."""
    ex = ccxt.deribit()
    if os.environ.get("INSECURE_SSL") == "1":
        ex.verify = False
    end = int(time.time() * 1000)
    start = end - 950 * 86400_000
    r = ex.public_get_get_volatility_index_data({
        "currency": "BTC", "start_timestamp": start,
        "end_timestamp": end, "resolution": "1D"})
    data = r["result"]["data"]
    return pd.Series({pd.to_datetime(int(row[0]), unit="ms").normalize():
                      float(row[4]) for row in data}).sort_index()


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    p = p[~np.isnan(p)]
    if len(p) < 25:
        return f"    {lbl:26} n {len(p):4d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return f"    {lbl:26} n {len(p):4d} | media {m:+.3f}% [{lo:+.3f},{hi:+.3f}] {sig}"


def main():
    dv = dvol_diario()
    print(f"DVOL BTC: {len(dv)} días, de {dv.index[0].date()} a {dv.index[-1].date()}")
    regime_alto = dv > dv.rolling(90).median().shift(1)   # solo pasado

    cfg = config_for_timeframe(TFZConfig(), "1h")
    rets = {}
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        rets[s] = (d.set_index("timestamp")["close"]
                   .resample("1D").last().dropna().pct_change() * 100)
    R = pd.DataFrame(rets)
    uni = R.mean(axis=1)          # retorno diario medio del universo (bruto, long)

    print("\n=== H1: retorno del universo al día SIGUIENTE según régimen DVOL (bruto) ===")
    alin = pd.DataFrame({"r_next": uni.shift(-1), "alto": regime_alto}).dropna()
    alin["alto"] = alin["alto"].astype(bool)
    for per, g in (("IS 2024-25", alin[alin.index.year < 2026]),
                   ("OOS 2026", alin[alin.index.year >= 2026])):
        print(f"  {per}:")
        if not len(g):
            print("    (sin datos)")
            continue
        print(stats_line(g[g.alto]["r_next"].values, "DVOL alto"))
        print(stats_line(g[~g.alto]["r_next"].values, "DVOL bajo"))

    print("\n=== H2: momentum vie->sáb por régimen DVOL del viernes (neto) ===")
    ret = R
    filas = {"alto": [], "bajo": []}
    for s in SYMS:
        if s not in ret:
            continue
        r = ret[s]
        for t in r.index:
            if t.weekday() != 5:
                continue
            t_fri = t - pd.Timedelta(days=1)
            if t_fri not in r.index or pd.isna(r.get(t)) or pd.isna(r.get(t_fri)):
                continue
            if t_fri not in regime_alto.index or pd.isna(regime_alto.get(t_fri)):
                continue
            fr = r[t_fri]
            if fr == 0:
                continue
            pnl = np.sign(fr) * r[t] - COST
            filas["alto" if regime_alto[t_fri] else "bajo"].append((t.year, pnl))
    for reg, rows in filas.items():
        print(f"  DVOL {reg}:")
        arr = [p for _, p in rows]
        print(stats_line(arr, "TOTAL"))
        print(stats_line([p for y, p in rows if y < 2026], "IS 2024-25"))
        print(stats_line([p for y, p in rows if y >= 2026], "OOS 2026"))


if __name__ == "__main__":
    main()
