"""
EXPLORACIÓN #27: SIMULACIÓN DE CARTERA COMBINADA 2024-2026 (2026-07-03).

Tres mangas con 1/3 del capital cada una, con las reglas TAL CUAL están selladas:
  A) vie->sáb (42 símbolos, media por sábado)
  B) prima Coinbase BTC (episodios z>=1, long 7d)
  C) prima Coinbase ETH (ídem)
Serie SEMANAL de cada manga (semanas sin señal = 0) y combinada = media de las tres.
Métricas: retorno anualizado, vol semanal, peor semana, drawdown máximo, ratio
media/vol semanal. OJO: esto es HISTÓRICO con las reglas ya validadas/candidatas —
sirve para ver la forma de la cartera, no como promesa (las mediciones forward
son las que mandan).

Solo lectura. Uso: python explore_portfolio.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from explore_premium import cierres, episodios

COST = (0.02 + 0.025) * 2
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM",
        "DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
        "1000PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
        "BTC","ETH","BNB","XRP"]
DESDE = pd.Timestamp("2024-01-01")


def manga_viernes(cfg):
    por_sab = {}
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        daily = d.set_index("timestamp")["close"].resample("1D").last().dropna()
        ret = daily.pct_change()
        for t in daily.index:
            if t.weekday() != 5 or t < DESDE:
                continue
            t_f = t - pd.Timedelta(days=1)
            if t_f not in ret.index or pd.isna(ret.get(t)):
                continue
            fr = ret[t_f]
            if pd.isna(fr) or fr == 0:
                continue
            por_sab.setdefault(t, []).append(np.sign(fr) * ret[t] * 100 - COST)
    return pd.Series({t: np.mean(v) for t, v in por_sab.items()}).sort_index()


def manga_prima(sym_cb, sym_bn):
    cb = cierres("coinbaseexchange", sym_cb)
    bn = cierres("binance", sym_bn)
    df = pd.DataFrame({"cb": cb, "bn": bn}).dropna()
    prem = (df.cb / df.bn - 1) * 100
    z = ((prem - prem.rolling(90).mean().shift(1))
         / prem.rolling(90).std().shift(1)).dropna()
    px = df.bn
    out = {}
    for t in episodios(z, lambda s: s >= 1):
        if t < DESDE:
            continue
        t1 = t + pd.Timedelta(days=7)
        if t in px.index and t1 in px.index:
            out[t] = (px[t1] - px[t]) / px[t] * 100 - COST
    return pd.Series(out).sort_index()


def metricas(w, lbl):
    w = w.fillna(0)
    m, sd = w.mean(), w.std(ddof=1)
    cum = w.cumsum()
    dd = (cum - cum.cummax()).min()
    anual = m * 52
    ratio = m / sd * np.sqrt(52) if sd > 0 else 0
    print(f"  {lbl:12} anual~{anual:+6.1f}% | vol sem {sd:4.2f}% | peor sem "
          f"{w.min():+.2f}% | DD máx {dd:+.2f}% | ratio {ratio:+.2f}")
    return w


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    fri = manga_viernes(cfg)
    p_btc = manga_prima("BTC/USD", "BTC/USDT")
    p_eth = manga_prima("ETH/USD", "ETH/USDT")

    # a serie semanal (semana que termina en domingo)
    idx = pd.date_range(DESDE, pd.Timestamp.now().normalize(), freq="W")
    w_fri = fri.groupby(pd.Grouper(freq="W")).sum().reindex(idx)
    w_btc = p_btc.groupby(pd.Grouper(freq="W")).sum().reindex(idx)
    w_eth = p_eth.groupby(pd.Grouper(freq="W")).sum().reindex(idx)

    print(f"=== CARTERA COMBINADA 2024-2026 ({len(idx)} semanas, 1/3 por manga) ===")
    a = metricas(w_fri, "vie->sáb")
    b = metricas(w_btc, "prima BTC")
    c = metricas(w_eth, "prima ETH")
    combo = (a + b + c) / 3
    metricas(combo, "COMBINADA")
    print(f"\n  correlaciones semanales: fri-BTC {a.corr(b):+.2f} | "
          f"fri-ETH {a.corr(c):+.2f} | BTC-ETH {b.corr(c):+.2f}")
    print("  (semanas sin señal cuentan como 0: capital parado, sin coste)")


if __name__ == "__main__":
    main()
