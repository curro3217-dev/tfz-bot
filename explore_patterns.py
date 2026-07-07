"""
EXPLORACIÓN #38: PATRONES CHARTISTAS (TradingPatternScanner) (2026-07-06).

Librería pip `tradingpattern` (white07S). OJO verificado en su código: los
detectores usan shift(-1) -> la marca del día t REQUIERE el día t+1 (look-ahead).
Corrección aplicada: la señal marcada en t se opera al CIERRE de t+1 (cuando ya
es conocible), hold 5 días (pre-especificado), dirección clásica del patrón:
  - Head and Shoulder -> SHORT | Inverse H&S -> LONG
  - Double Top -> SHORT | Double Bottom -> LONG
  - Wedge Up -> SHORT | Wedge Down -> LONG (convención clásica de cuña)
42 símbolos, diario de la cache (2024-26), costes MEXC. IS 24-25 / OOS 2026.

Solo lectura. Uso: python explore_patterns.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
# Detectores REPLICADOS de tradingpatterns 0.0.5 (white07S) con dos arreglos:
# (1) columnas de patron con dtype object (pandas 4 rechaza texto sobre float64);
# (2) misma logica EXACTA, incluido su shift(-1) -> por eso la senal se opera con
#     +1 dia de retraso mas abajo (correccion de look-ahead documentada).


def detect_head_shoulder(df, window=3):
    hi, lo = df["High"], df["Low"]
    hmax = hi.rolling(window).max()
    lmin = lo.rolling(window).min()
    m_hs = ((hmax > hi.shift(1)) & (hmax > hi.shift(-1))
            & (hi < hi.shift(1)) & (hi < hi.shift(-1)))
    m_inv = ((lmin < lo.shift(1)) & (lmin < lo.shift(-1))
             & (lo > lo.shift(1)) & (lo > lo.shift(-1)))
    col = pd.Series(pd.NA, index=df.index, dtype="object")
    col[m_hs] = "Head and Shoulder"
    col[m_inv] = "Inverse Head and Shoulder"
    df["head_shoulder_pattern"] = col
    return df


def detect_double_top_bottom(df, window=3, threshold=0.05):
    hi, lo = df["High"], df["Low"]
    hmax = hi.rolling(window).max()
    lmin = lo.rolling(window).min()
    rango_prev = (hi.shift(1) - lo.shift(1)) <= threshold * (hi.shift(1) + lo.shift(1)) / 2
    rango_next = (hi.shift(-1) - lo.shift(-1)) <= threshold * (hi.shift(-1) + lo.shift(-1)) / 2
    m_top = ((hmax >= hi.shift(1)) & (hmax >= hi.shift(-1))
             & (hi < hi.shift(1)) & (hi < hi.shift(-1)) & rango_prev & rango_next)
    m_bot = ((lmin <= lo.shift(1)) & (lmin <= lo.shift(-1))
             & (lo > lo.shift(1)) & (lo > lo.shift(-1)) & rango_prev & rango_next)
    col = pd.Series(pd.NA, index=df.index, dtype="object")
    col[m_top] = "Double Top"
    col[m_bot] = "Double Bottom"
    df["double_pattern"] = col
    return df


def detect_wedge(df, window=3):
    hi, lo = df["High"], df["Low"]
    hmax = hi.rolling(window).max()
    lmin = lo.rolling(window).min()
    t_hi = hi.rolling(window).apply(
        lambda x: 1 if (x.iloc[-1] - x.iloc[0]) > 0 else
        (-1 if (x.iloc[-1] - x.iloc[0]) < 0 else 0))
    t_lo = lo.rolling(window).apply(
        lambda x: 1 if (x.iloc[-1] - x.iloc[0]) > 0 else
        (-1 if (x.iloc[-1] - x.iloc[0]) < 0 else 0))
    m_up = (hmax >= hi.shift(1)) & (lmin <= lo.shift(1)) & (t_hi == 1) & (t_lo == 1)
    m_dn = (hmax <= hi.shift(1)) & (lmin >= lo.shift(1)) & (t_hi == -1) & (t_lo == -1)
    col = pd.Series(pd.NA, index=df.index, dtype="object")
    col[m_up] = "Wedge Up"
    col[m_dn] = "Wedge Down"
    df["wedge_pattern"] = col
    return df

COST = (0.02 + 0.025) * 2
HOLD_D = 5
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM",
        "DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
        "1000PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
        "BTC","ETH","BNB","XRP"]
DIRECCION = {"Head and Shoulder": -1, "Inverse Head and Shoulder": +1,
             "Double Top": -1, "Double Bottom": +1,
             "Wedge Up": -1, "Wedge Down": +1}


def stats_line(p, lbl):
    p = np.asarray(p, dtype=float)
    if len(p) < 30:
        return f"    {lbl:10} n {len(p):5d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:10} n {len(p):5d} | win {(p>0).mean()*100:4.1f}% | "
            f"exp {m:+.3f}% [{lo:+.3f},{hi:+.3f}] {sig}")


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    res = {}
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        day = (d.set_index("timestamp")
               .resample("1D").agg({"open": "first", "high": "max",
                                    "low": "min", "close": "last"}).dropna())
        df = day.rename(columns={"open": "Open", "high": "High",
                                 "low": "Low", "close": "Close"}).copy()
        try:
            df = detect_head_shoulder(df)
            df = detect_double_top_bottom(df)
            df = detect_wedge(df)
        except Exception as e:
            print(f"  {s}: detector fallo ({e})")
            continue
        closes = day["close"]
        cols = {"head_shoulder_pattern": None, "double_pattern": None,
                "wedge_pattern": None}
        for col in list(cols):
            if col not in df.columns:
                continue
            marcas = df[col].dropna()
            for t, patron in marcas.items():
                sgn = DIRECCION.get(str(patron))
                if sgn is None:
                    continue
                i = day.index.get_loc(t)
                # señal conocible al cierre de t+1 (por el shift(-1) del detector)
                if i + 1 + HOLD_D >= len(day):
                    continue
                entry = closes.iloc[i + 1]
                exit_ = closes.iloc[i + 1 + HOLD_D]
                pnl = sgn * (exit_ - entry) / entry * 100 - COST
                res.setdefault(str(patron), []).append(
                    (day.index[i].year, float(pnl)))

    for patron in sorted(res):
        rows = res[patron]
        print(f"\n[{patron} -> {'short' if DIRECCION[patron]<0 else 'long'} {HOLD_D}d]")
        print(stats_line([p for _, p in rows], "TOTAL"))
        print(stats_line([p for y, p in rows if y < 2026], "IS 24-25"))
        print(stats_line([p for y, p in rows if y >= 2026], "OOS 2026"))


if __name__ == "__main__":
    main()
