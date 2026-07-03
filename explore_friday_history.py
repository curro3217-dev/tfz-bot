"""
EXPLORACIÓN #16: PROFUNDIDAD HISTÓRICA del vie->sáb (2018-2026) (2026-07-03).

Todo lo validado hasta ahora cubre 2024-2026 (límite de la cache 1h). Aquí se estira
con velas DIARIAS de Binance SPOT (la serie más larga disponible; para un patrón de
precio puro el spot vale igual que el perp). Pregunta: ¿el efecto es persistente
(existía en 2019-2023, incluido el bajista de 2022) o nació en 2024 (riesgo de moda)?

Misma regla: dirección = signo del viernes (día UTC), mantener el sábado, neto de
costes MEXC. Universos: los 42 de weekend_paper (spot: sin sufijo perp; 1000PEPE ->
PEPE). Por año, IC95, nº de símbolos con datos.

Solo lectura. Uso: python explore_friday_history.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import time
import numpy as np
import pandas as pd
import ccxt

COST = (0.02 + 0.025) * 2
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM",
        "DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
        "PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
        "BTC","ETH","BNB","XRP"]
DESDE = int(pd.Timestamp("2018-01-01").timestamp() * 1000)


def daily_history(ex, sym):
    out = []
    since = DESDE
    while True:
        try:
            c = ex.fetch_ohlcv(sym, "1d", since=since, limit=1000)
        except Exception:
            return out
        if not c:
            break
        if out and c[0][0] <= out[-1][0]:
            c = [x for x in c if x[0] > out[-1][0]]
            if not c:
                break
        out += c
        if len(c) < 2:
            break
        since = out[-1][0] + 1
        time.sleep(ex.rateLimit / 1000)
    return out


def stats_line(p, lbl, nsym):
    p = np.asarray(p, dtype=float)
    if len(p) < 30:
        return f"  {lbl:6} n {len(p):5d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"  {lbl:6} n {len(p):5d} ({nsym:2d} símb) | win {(p>0).mean()*100:4.1f}% | "
            f"exp {m:+.3f}% [{lo:+.3f},{hi:+.3f}] {sig}")


def main():
    ex = ccxt.binance({"enableRateLimit": True, "timeout": 20000})
    if os.environ.get("INSECURE_SSL") == "1":
        ex.verify = False
    ex.load_markets()
    rows = []
    for s in SYMS:
        sym = f"{s}/USDT"
        if sym not in ex.markets:
            print(f"  {s}: no está en Binance spot")
            continue
        c = daily_history(ex, sym)
        if len(c) < 120:
            print(f"  {s}: historia corta ({len(c)} días)")
            continue
        df = pd.DataFrame(c, columns=["ts", "o", "h", "l", "close", "v"])
        df["t"] = pd.to_datetime(df["ts"], unit="ms")
        daily = df.set_index("t")["close"]
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
            rows.append({"sym": s, "year": t.year,
                         "pnl": float(np.sign(fr) * ret[t] * 100 - COST),
                         "fri_abs": abs(fr) * 100})
        print(f"  {s}: {len(c)} días desde {df['t'].iloc[0].date()}")

    d = pd.DataFrame(rows)
    print(f"\n=== vie->sáb por AÑO (Binance spot, neto costes MEXC) ===")
    for y in sorted(d["year"].unique()):
        g = d[d.year == y]
        print(stats_line(g["pnl"].values, str(y), g["sym"].nunique()))
    print(f"\n=== con filtro |viernes| >= 3% (criterio secundario) ===")
    f = d[d.fri_abs >= 3.0]
    for y in sorted(f["year"].unique()):
        g = f[f.year == y]
        print(stats_line(g["pnl"].values, str(y), g["sym"].nunique()))


if __name__ == "__main__":
    main()
