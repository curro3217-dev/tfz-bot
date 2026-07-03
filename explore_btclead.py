"""
EXPLORACIÓN #9: ¿BTC MANDA? (lead-lag BTC -> alts, diario) (2026-07-03).

Hipótesis de microestructura: el movimiento de BTC de hoy anticipa el de las alts
de mañana (las alts "siguen" al líder con retardo).
  - señal: signo del retorno diario de BTC del día t
  - posición: TODAS las alts del universo en esa dirección durante el día t+1
  - coste: solo al CAMBIAR de dirección (0.09% i/v el día del flip)
  - dato = DÍA de cartera | IS = 2024+2025 | OOS = 2026
  - control: comparar contra el momentum propio de cada alt (que ya sabemos ~plano)

Solo lectura. Uso: python explore_btclead.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST_RT = (0.02 + 0.025) * 2
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    p = p[~np.isnan(p)]
    if len(p) < 60:
        return f"  {lbl:14} n {len(p):4d} (pocos días)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"  {lbl:14} n {len(p):4d} días | media {m:+.4f}%/día "
            f"[{lo:+.4f},{hi:+.4f}] {sig} | anualizado ~{m*365:+.0f}%")


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    btc = fetch_ohlcv_cached("BTC/USDT:USDT", "1h", limit=20000, config=cfg)
    btc_d = btc.set_index("timestamp")["close"].resample("1D").last().dropna()
    btc_sig = np.sign(btc_d.pct_change())          # señal del día t

    alt_ret = {}
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        alt_ret[s] = (d.set_index("timestamp")["close"]
                      .resample("1D").last().dropna().pct_change() * 100)
    A = pd.DataFrame(alt_ret)

    # posición del día t+1 = señal de BTC del día t
    pos = btc_sig.reindex(A.index).shift(1)
    flip = (pos != pos.shift(1)) & pos.notna()
    port = (A.mul(pos, axis=0)).mean(axis=1) - flip * COST_RT
    port = port.dropna()

    print("=== BTC manda: signo de BTC(t) aplicado a las alts en t+1, neto ===")
    print(stats_line(port.values, "TOTAL"))
    print(stats_line(port[port.index.year < 2026].values, "IS 2024-25"))
    print(stats_line(port[port.index.year >= 2026].values, "OOS 2026"))

    # control: momentum propio de cada alt (signo propio en vez del de BTC)
    A = A.astype(float)
    own = pd.DataFrame(
        {s: np.sign(A[s].shift(1).fillna(0)) * A[s] for s in A}).mean(axis=1)
    own = own.dropna() - COST_RT * 0.5   # aprox: flip ~cada 2 días
    print("\n=== control: momentum propio de las alts (mismo esquema) ===")
    print(stats_line(own.values, "TOTAL"))
    print(stats_line(own[own.index.year < 2026].values, "IS 2024-25"))
    print(stats_line(own[own.index.year >= 2026].values, "OOS 2026"))


if __name__ == "__main__":
    main()
