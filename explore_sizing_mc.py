"""
EXPLORACIÓN #29: SIZING POR RIESGO + MONTE CARLO DE CAPITAL (2026-07-03).

1. SIZING del vie->sáb: ¿mejora pesar cada moneda por 1/volatilidad (mismo riesgo
   por posición) en vez de a partes iguales? Vol = desviación de retornos diarios
   30d, SOLO pasado. Se compara el ratio media/vol de la serie semanal.
2. MONTE CARLO de la cartera combinada (3 mangas, serie semanal 2024-26): 10.000
   caminos de 3 años remuestreando semanas enteras (bloques de 4 para respetar
   rachas), con interés compuesto, a 1x y 2x. Se reporta mediana final,
   percentil 5/95, prob. de drawdown >30% y prob. de acabar en pérdidas.
   ADVERTENCIA: remuestrear historia asume que el futuro se parece al pasado;
   es una foto del RIESGO, no una promesa de retorno.

Solo lectura. Uso: python explore_sizing_mc.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from explore_portfolio import manga_viernes, manga_prima, DESDE, SYMS

COST = (0.02 + 0.025) * 2
rng = np.random.default_rng(7)


def manga_viernes_riskparity(cfg):
    por_sab = {}
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        daily = d.set_index("timestamp")["close"].resample("1D").last().dropna()
        ret = daily.pct_change()
        vol30 = ret.rolling(30).std().shift(1) * 100   # solo pasado
        for t in daily.index:
            if t.weekday() != 5 or t < DESDE:
                continue
            t_f = t - pd.Timedelta(days=1)
            if t_f not in ret.index or pd.isna(ret.get(t)):
                continue
            fr = ret[t_f]
            v = vol30.get(t_f, np.nan)
            if pd.isna(fr) or fr == 0 or pd.isna(v) or v <= 0:
                continue
            pnl = np.sign(fr) * ret[t] * 100 - COST
            por_sab.setdefault(t, []).append((pnl, 1.0 / v))
    out = {}
    for t, pares in por_sab.items():
        p = np.array([x for x, _ in pares]); w = np.array([x for _, x in pares])
        out[t] = float((p * w).sum() / w.sum())
    return pd.Series(out).sort_index()


def ratio(w):
    w = w.fillna(0)
    return w.mean() / w.std(ddof=1) * np.sqrt(52) if w.std(ddof=1) > 0 else 0


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    eq = manga_viernes(cfg)
    rp = manga_viernes_riskparity(cfg)
    idx = pd.date_range(DESDE, pd.Timestamp.now().normalize(), freq="W")
    w_eq = eq.groupby(pd.Grouper(freq="W")).sum().reindex(idx).fillna(0)
    w_rp = rp.groupby(pd.Grouper(freq="W")).sum().reindex(idx).fillna(0)
    print("1. SIZING del vie->sáb (serie semanal 2024-26):")
    print(f"   pesos iguales : media {w_eq.mean():+.3f}%/sem | ratio {ratio(w_eq):+.2f}")
    print(f"   riesgo igual  : media {w_rp.mean():+.3f}%/sem | ratio {ratio(w_rp):+.2f}")

    # cartera combinada (reutiliza las mangas de explore_portfolio)
    p_btc = manga_prima("BTC/USD", "BTC/USDT")
    p_eth = manga_prima("ETH/USD", "ETH/USDT")
    w_btc = p_btc.groupby(pd.Grouper(freq="W")).sum().reindex(idx).fillna(0)
    w_eth = p_eth.groupby(pd.Grouper(freq="W")).sum().reindex(idx).fillna(0)
    combo = ((w_eq + w_btc + w_eth) / 3).values / 100   # fracción semanal

    print("\n2. MONTE CARLO cartera combinada (bloques de 4 semanas, 3 años, 10k caminos):")
    n_sem = 156
    bloques = [combo[i:i + 4] for i in range(0, len(combo) - 3)]
    for lev in (1.0, 2.0):
        finales, dd30, perdida = [], 0, 0
        for _ in range(10_000):
            path = np.concatenate(
                [bloques[rng.integers(0, len(bloques))] for _ in range(n_sem // 4)])
            eqty = np.cumprod(1 + lev * path)
            finales.append(eqty[-1])
            dd = (eqty / np.maximum.accumulate(eqty) - 1).min()
            dd30 += dd <= -0.30
            perdida += eqty[-1] < 1
        f = np.array(finales)
        print(f"   {lev:.0f}x: mediana x{np.median(f):.2f} | p5 x{np.percentile(f,5):.2f} "
              f"| p95 x{np.percentile(f,95):.2f} | P(DD>30%) {dd30/100:.1f}% | "
              f"P(perder) {perdida/100:.1f}%")
    print("\n(remuestrea 2024-26: si el régimen cambia, esto no aplica; foto de riesgo)")


if __name__ == "__main__":
    main()
