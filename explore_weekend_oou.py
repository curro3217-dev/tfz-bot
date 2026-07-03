"""
EXPLORACIÓN #10: REPLICACIÓN FUERA-DE-UNIVERSO del momentum vie->sáb (2026-07-03).

El vie->sáb sobrevivió todo en NUESTROS 20 símbolos. Prueba definitiva de que no es
un artefacto del universo elegido: la MISMA regla, sin tocar nada, en:
  - 20 alts NUEVAS (jamás usadas en ninguna exploración nuestra)
  - los majors (BTC, ETH, BNB, XRP)
Si replica ahí, es propiedad del mercado; si no, era suerte de universo.

Regla idéntica a weekend_paper: dirección = signo del retorno del viernes,
mantener el sábado (24h), neto de costes MEXC. Por año, IC95.

Solo lectura. Uso: python explore_weekend_oou.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST = (0.02 + 0.025) * 2
NUEVAS = ["DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
          "1000PEPE","HBAR","ALGO","VET","ICP","POL","GALA","SAND","EOS","KAVA"]
MAJORS = ["BTC","ETH","BNB","XRP"]


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    if len(p) < 30:
        return f"    {lbl:12} n {len(p):4d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:12} n {len(p):4d} | win {(p>0).mean()*100:4.1f}% | "
            f"exp {m:+.3f}% [{lo:+.3f},{hi:+.3f}] {sig}")


def friday_trades(syms, cfg):
    rows = []
    ok_syms = []
    for s in syms:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception as e:
            print(f"    {s}: sin datos ({e})")
            continue
        if len(d) < 24 * 60:
            print(f"    {s}: historia corta ({len(d)} velas)")
            continue
        daily = d.set_index("timestamp")["close"].resample("1D").last().dropna()
        ret = daily.pct_change()
        for t in daily.index:
            if t.weekday() != 5:
                continue
            t_fri = t - pd.Timedelta(days=1)
            if t_fri not in ret.index or t not in ret.index:
                continue
            fr, sr = ret[t_fri], ret[t]
            if pd.isna(fr) or pd.isna(sr) or fr == 0:
                continue
            rows.append({"sym": s, "t": t, "pnl": float(np.sign(fr) * sr * 100 - COST)})
        ok_syms.append(s)
    return pd.DataFrame(rows), ok_syms


def report(df, titulo):
    print(f"\n=== {titulo} ({df['sym'].nunique()} símbolos, {len(df)} trades) ===")
    print(stats_line(df["pnl"].values, "TOTAL"))
    for y, g in df.groupby(df["t"].dt.year):
        print(stats_line(g["pnl"].values, str(y)))
    per = df.groupby("sym")["pnl"].mean()
    print(f"    símbolos positivos: {(per > 0).sum()}/{len(per)}")


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    print("bajando/leyendo alts nuevas...")
    alts, _ = friday_trades(NUEVAS, cfg)
    print("bajando/leyendo majors...")
    majors_df, _ = friday_trades(MAJORS, cfg)
    if len(alts):
        report(alts, "ALTS NUEVAS (fuera de universo)")
    if len(majors_df):
        report(majors_df, "MAJORS (BTC/ETH/BNB/XRP)")


if __name__ == "__main__":
    main()
