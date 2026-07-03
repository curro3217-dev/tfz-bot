"""
EXPLORACIÓN #23: FAMILIA DE LA PRIMA + CORRELACIÓN DE CARTERA (2026-07-03).

Tres preguntas sobre la señal de prima (candidata en medición) y la cartera:
  1. ¿Existe la prima de ETH por sí misma? (ETH/USD Coinbase vs ETH/USDT Binance,
     mismo esqueleto z90 solo-pasado, episodios, long 7d)
  2. ¿La señal de prima de BTC mueve al UNIVERSO de alts? (long cartera de 20 alts
     7 días en cada episodio; control de deriva propio)
  3. ¿Cómo CORRELACIONAN los dos streams validados/candidatos (vie->sáb semanal y
     prima) ? Si es baja, la cartera combinada rinde más estable que cada pata.
Solo lectura. Uso: python explore_premium_family.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from explore_premium import cierres, episodios

COST = (0.02 + 0.025) * 2
HOLD_D = 7
ALTS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]


def stats(p):
    p = np.asarray(p, dtype=float)
    p = p[~np.isnan(p)]
    if len(p) < 8:
        return f"n {len(p):3d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    sig = "EXCLUYE 0" if m - 1.96 * se > 0 or m + 1.96 * se < 0 else "incluye 0"
    return f"n {len(p):3d} | {m:+.2f}% [{m-1.96*se:+.2f},{m+1.96*se:+.2f}] {sig}"


def z_de(prem):
    return ((prem - prem.rolling(90).mean().shift(1))
            / prem.rolling(90).std().shift(1)).dropna()


def main():
    # 1. prima de ETH propia
    cb_e = cierres("coinbaseexchange", "ETH/USD")
    bn_e = cierres("binance", "ETH/USDT")
    de = pd.DataFrame({"cb": cb_e, "bn": bn_e}).dropna()
    z_e = z_de((de["cb"] / de["bn"] - 1) * 100)
    px_e = de["bn"]
    rows = []
    for t in episodios(z_e, lambda s: s >= 1):
        t1 = t + pd.Timedelta(days=HOLD_D)
        if t in px_e.index and t1 in px_e.index:
            rows.append({"y": t.year, "p": (px_e[t1]-px_e[t])/px_e[t]*100 - COST})
    d = pd.DataFrame(rows)
    print("1. PRIMA DE ETH propia (z>=1 -> long ETH 7d):")
    print(f"   TOTAL  {stats(d['p'].values)}")
    print(f"   IS<=23 {stats(d[d.y <= 2023]['p'].values)}")
    print(f"   OOS>=24 {stats(d[d.y >= 2024]['p'].values)}")

    # 2. señal BTC -> universo de alts
    cb_b = cierres("coinbaseexchange", "BTC/USD")
    bn_b = cierres("binance", "BTC/USDT")
    db = pd.DataFrame({"cb": cb_b, "bn": bn_b}).dropna()
    z_b = z_de((db["cb"] / db["bn"] - 1) * 100)
    cfg = config_for_timeframe(TFZConfig(), "1h")
    alt_px = {}
    for s in ALTS:
        try:
            dd = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
            alt_px[s] = dd.set_index("timestamp")["close"].resample("1D").last().dropna()
        except Exception:
            pass
    A = pd.DataFrame(alt_px)
    eps = list(episodios(z_b, lambda s: s >= 1))
    sig_rows, base_rows = [], []
    for t in z_b.index:
        t1 = t + pd.Timedelta(days=HOLD_D)
        if t not in A.index or t1 not in A.index:
            continue
        r = ((A.loc[t1] / A.loc[t] - 1) * 100).dropna()
        if len(r) < 10:
            continue
        val = r.mean() - COST
        base_rows.append(val)
        if t in eps:
            sig_rows.append(val)
    print("\n2. SEÑAL DE PRIMA BTC -> cartera de 20 ALTS (long 7d):")
    print(f"   episodios {stats(sig_rows)}")
    print(f"   deriva alts (todos los días) {stats(base_rows)} | exceso "
          f"{np.mean(sig_rows) - np.mean(base_rows):+.2f}%")

    # 3. correlación de streams: vie->sáb semanal vs prima (por semana ISO)
    wk_fri = {}
    for s in ALTS:
        if s not in A:
            continue
        ret = A[s].pct_change()
        for t in A[s].index:
            if t.weekday() != 5:
                continue
            t_f = t - pd.Timedelta(days=1)
            if t_f not in ret.index or pd.isna(ret.get(t)) or pd.isna(ret.get(t_f)) \
               or ret[t_f] == 0:
                continue
            wk_fri.setdefault(t, []).append(np.sign(ret[t_f]) * ret[t] * 100 - COST)
    fri = pd.Series({t: np.mean(v) for t, v in wk_fri.items()}).sort_index()
    prem_ep = pd.Series({t: p for t, p in zip(
        [t for t in eps], [np.nan] * len(eps))})
    # pnl del episodio de prima (BTC) por semana en que ARRANCA
    prem_pnl = {}
    px_b = db["bn"]
    for t in eps:
        t1 = t + pd.Timedelta(days=HOLD_D)
        if t in px_b.index and t1 in px_b.index:
            prem_pnl[t] = (px_b[t1]-px_b[t])/px_b[t]*100 - COST
    prem_s = pd.Series(prem_pnl).sort_index()
    fri_w = fri.groupby(pd.Grouper(freq="W")).mean()
    prem_w = prem_s.groupby(pd.Grouper(freq="W")).mean()
    both = pd.DataFrame({"fri": fri_w, "prem": prem_w}).dropna()
    print(f"\n3. CORRELACIÓN de streams (semanas con ambos activos: {len(both)}):")
    if len(both) >= 10:
        print(f"   corr(vie->sáb, prima) = {both['fri'].corr(both['prem']):+.3f}")
    else:
        print("   pocas semanas coincidentes para correlación fiable")


if __name__ == "__main__":
    main()
