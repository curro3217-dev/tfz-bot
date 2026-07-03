"""
EXPLORACIÓN #35: vie->sáb en la COLA LARGA de MEXC + EFECTO ESTRENO (2026-07-04).

1. COLA LARGA: la regla vie->sáb (sin tocar) sobre ~120 perps de MEXC que NUNCA
   hemos usado (excluye los 42 del universo actual). Velas 1d de MEXC directas.
   Si replica ahí, es candidata a ampliar universo en una futura revisión.
2. ESTRENO: retorno de los días 2-7 tras el listado (día 1 = primera vela diaria
   completa) — ¿las nuevas se desinflan (fade) o corren (momentum)? Se mide el
   retorno LONG bruto; listado = primera vela del contrato en MEXC (solo se usan
   contratos estrenados desde 2024-07 para tener fecha de estreno real dentro
   del histórico disponible).

Solo lectura. Uso: python explore_friday_universe.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import time
import numpy as np
import pandas as pd
from data_fetcher import create_exchange

COST = (0.02 + 0.025) * 2
YA_USADOS = {"AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
             "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM",
             "DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
             "1000PEPE","PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
             "BTC","ETH","BNB","XRP"}


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    if len(p) < 30:
        return f"    {lbl:12} n {len(p):5d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:12} n {len(p):5d} | win {(p>0).mean()*100:4.1f}% | "
            f"exp {m:+.3f}% [{lo:+.3f},{hi:+.3f}] {sig}")


def main():
    ex = create_exchange("mexc")
    ex.load_markets()
    # perps USDT lineales, ordenados, fuera del universo actual
    cands = sorted({m["base"] for m in ex.markets.values()
                    if m.get("swap") and m.get("quote") == "USDT"
                    and m["base"] not in YA_USADOS})
    print(f"candidatos cola larga: {len(cands)}")
    fri_rows, listing_rows = [], []
    usados = 0
    for base in cands:
        if usados >= 120:
            break
        sym = f"{base}/USDT:USDT"
        try:
            c = ex.fetch_ohlcv(sym, "1d", limit=1000)
            time.sleep(ex.rateLimit / 1000)
        except Exception:
            continue
        if len(c) < 60:
            continue
        usados += 1
        px = pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): x[4] for x in c})
        ret = px.pct_change()
        # 1. vie->sáb
        for t in px.index:
            if t.weekday() != 5:
                continue
            t_f = t - pd.Timedelta(days=1)
            if t_f not in ret.index or pd.isna(ret.get(t)):
                continue
            fr = ret[t_f]
            if pd.isna(fr) or fr == 0:
                continue
            fri_rows.append({"y": t.year,
                             "p": float(np.sign(fr) * ret[t] * 100 - COST)})
        # 2. estreno (solo si el contrato nació dentro de la ventana: <1000 velas)
        if len(c) < 990 and px.index[0] >= pd.Timestamp("2024-07-01"):
            if len(px) >= 8:
                r27 = (px.iloc[7] / px.iloc[1] - 1) * 100   # días 2..7 (long, bruto)
                listing_rows.append({"y": px.index[0].year, "p": float(r27)})

    d = pd.DataFrame(fri_rows)
    print(f"\n[1. vie->sáb en cola larga ({usados} monedas nunca usadas)]")
    print(stats_line(d["p"].values, "TOTAL"))
    for y in sorted(d["y"].unique()):
        print(stats_line(d[d.y == y]["p"].values, str(y)))

    e = pd.DataFrame(listing_rows)
    print(f"\n[2. estreno: retorno LONG bruto días 2-7 tras listado ({len(e)} estrenos)]")
    print(stats_line(e["p"].values, "TOTAL"))


if __name__ == "__main__":
    main()
