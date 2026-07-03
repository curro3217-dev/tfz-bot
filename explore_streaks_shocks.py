"""
EXPLORACIÓN #32: RACHAS, SHOCKS y RATIO ETH/BTC (2026-07-03).

Tres familias diarias no probadas (42 símbolos 2024-26, velas de la cache):
  1. RACHAS: tras k días seguidos en la misma dirección (k=3,4,5), retorno del
     día siguiente SI SE SIGUE la racha (continuation). Negativo = agotamiento.
  2. SHOCKS: tras un día con |ret| >= 7%, retorno de los 1 y 2 días siguientes
     EN LA DIRECCIÓN del shock (continuation). Se separa shock alcista/bajista.
  3. ETH/BTC: z-score 90d (solo pasado) del ratio; z <= -1 -> long ETH / short BTC
     7 días (reversión, 2 patas = 2x coste); z >= +1 -> lo contrario.
Criterio de supervivencia: IS (24-25) con IC95 excluyendo 0 Y OOS (2026) del mismo
signo. Las celdas de rachas/shocks son exploratorias (se declaran todas).

Solo lectura. Uso: python explore_streaks_shocks.py
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


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    if len(p) < 25:
        return f"    {lbl:22} n {len(p):5d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:22} n {len(p):5d} | win {(p>0).mean()*100:4.1f}% | "
            f"exp {m:+.3f}% [{lo:+.3f},{hi:+.3f}] {sig}")


def bloque(rows, titulo):
    print(f"\n[{titulo}]")
    print(stats_line([p for _, p in rows], "TOTAL"))
    print(stats_line([p for y, p in rows if y < 2026], "IS 24-25"))
    print(stats_line([p for y, p in rows if y >= 2026], "OOS 2026"))


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    daily = {}
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
            daily[s] = d.set_index("timestamp")["close"].resample("1D").last().dropna()
        except Exception:
            continue

    # 1. rachas y 2. shocks
    rachas = {k: [] for k in (3, 4, 5)}
    shocks = {("up", 1): [], ("up", 2): [], ("down", 1): [], ("down", 2): []}
    for s, px in daily.items():
        ret = px.pct_change() * 100
        sgn = np.sign(ret)
        streak = (sgn.groupby((sgn != sgn.shift()).cumsum()).cumcount() + 1) * sgn
        for i in range(1, len(ret) - 2):
            t = ret.index[i]
            y = t.year
            st = streak.iloc[i]
            for k in (3, 4, 5):
                if abs(st) == k:
                    rachas[k].append((y, float(np.sign(st) * ret.iloc[i + 1] - COST)))
            r = ret.iloc[i]
            if abs(r) >= 7:
                lado = "up" if r > 0 else "down"
                shocks[(lado, 1)].append((y, float(np.sign(r) * ret.iloc[i + 1] - COST)))
                r2 = (px.iloc[i + 2] / px.iloc[i] - 1) * 100
                shocks[(lado, 2)].append((y, float(np.sign(r) * r2 - COST)))

    for k, rows in rachas.items():
        bloque(rows, f"1. racha de {k} días -> seguir la racha 1 día")
    for (lado, h), rows in shocks.items():
        bloque(rows, f"2. shock {lado} >=7% -> seguir {h} día(s)")

    # 3. ETH/BTC ratio
    ratio = (daily["ETH"] / daily["BTC"]).dropna()
    z = ((ratio - ratio.rolling(90).mean().shift(1))
         / ratio.rolling(90).std().shift(1)).dropna()
    rows = []
    for t in z.index:
        t7 = t + pd.Timedelta(days=7)
        if t7 not in ratio.index:
            continue
        mov = (ratio[t7] / ratio[t] - 1) * 100
        if z[t] <= -1 and (z.get(t - pd.Timedelta(days=1), 0) > -1):
            rows.append((t.year, mov - 2 * COST))      # long ETH / short BTC
        elif z[t] >= 1 and (z.get(t - pd.Timedelta(days=1), 0) < 1):
            rows.append((t.year, -mov - 2 * COST))     # short ETH / long BTC
    bloque(rows, "3. reversión ETH/BTC (episodios z+-1, 7d, 2 patas)")


if __name__ == "__main__":
    main()
