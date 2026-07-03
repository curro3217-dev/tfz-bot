"""
EXPLORACIÓN #24: BOOTSTRAP POR CLÚSTERES del vie->sáb (2026-07-03).

Todos los IC95 reportados hasta ahora tratan cada trade como independiente, pero
los 42 símbolos comparten sábado (correlados) -> el IC real es más ancho. Aquí se
cuantifica con CLUSTER BOOTSTRAP: se remuestrean SÁBADOS enteros (con reemplazo,
10.000 veces) y se mira la distribución de la media. Es el test que decide si la
significancia del efecto sobrevive a la correlación.

Se aplica a: (a) regla base 42 símbolos, (b) filtro |vie|>=3%, (c) año a año.
Solo lectura. Uso: python explore_friday_bootstrap.py
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
N_BOOT = 10_000
rng = np.random.default_rng(42)


def cluster_boot(por_sabado):
    """por_sabado: lista de arrays (trades de cada sábado). Devuelve IC95 de la
    media global remuestreando sábados enteros."""
    k = len(por_sabado)
    medias = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = rng.integers(0, k, k)
        medias[b] = np.concatenate([por_sabado[i] for i in idx]).mean()
    return np.percentile(medias, [2.5, 97.5]), medias


def linea(por_sabado, lbl):
    todos = np.concatenate(por_sabado)
    (lo, hi), _ = cluster_boot(por_sabado)
    sig = "EXCLUYE 0" if lo > 0 or hi < 0 else "incluye 0"
    return (f"  {lbl:16} sáb {len(por_sabado):3d} | trades {len(todos):5d} | "
            f"exp {todos.mean():+.3f}% | IC95-cluster [{lo:+.3f},{hi:+.3f}] {sig}")


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    base, filt = {}, {}
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        daily = d.set_index("timestamp")["close"].resample("1D").last().dropna()
        ret = daily.pct_change()
        for t in daily.index:
            if t.weekday() != 5:
                continue
            t_f = t - pd.Timedelta(days=1)
            if t_f not in ret.index or pd.isna(ret.get(t)):
                continue
            fr = ret[t_f]
            if pd.isna(fr) or fr == 0:
                continue
            pnl = float(np.sign(fr) * ret[t] * 100 - COST)
            base.setdefault(t, []).append(pnl)
            if abs(fr) >= 0.03:
                filt.setdefault(t, []).append(pnl)

    b = [np.array(v) for v in base.values()]
    f = [np.array(v) for v in filt.values()]
    print(f"=== BOOTSTRAP POR CLÚSTERES ({N_BOOT} remuestreos de sábados enteros) ===")
    print(linea(b, "regla base"))
    print(linea(f, "filtro |vie|>=3%"))
    print("\nPor año (regla base):")
    for y in (2024, 2025, 2026):
        by = [np.array(v) for t, v in base.items() if t.year == y]
        if len(by) >= 10:
            print(linea(by, str(y)))


if __name__ == "__main__":
    main()
