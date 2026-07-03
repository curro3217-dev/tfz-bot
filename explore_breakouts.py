"""
EXPLORACIÓN #30: RUPTURAS INTRADÍA CLÁSICAS (2026-07-03).

Tres familias no probadas aún, con velas 1h (42 símbolos, 2024-2026):
  A. VOLATILITY BREAKOUT (Larry Williams): entrar cuando el precio cruza
     apertura_del_día ± 0.5×ATR20 (de días ANTERIORES); salir al cierre del día.
  B. NR7: si ayer fue el rango más estrecho de los últimos 7 días, hoy operar la
     ruptura del máximo/mínimo de ayer (stop de entrada); salir al cierre del día.
  D. PICO DE VOLUMEN: volumen de ayer > 3× media 20d -> hoy ir en la dirección
     que marcó ayer (bar diario completo).
Entrada al precio de ruptura (detectada con el recorrido 1h), costes MEXC por
trade. IS 2024-25 / OOS 2026. Dato estadístico = trade (se anota que los días
comparten fecha entre símbolos -> IC optimistas; solo pasa al siguiente nivel
lo que sobreviva claramente).

Solo lectura. Uso: python explore_breakouts.py
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
    if len(p) < 30:
        return f"    {lbl:10} n {len(p):5d} (pocos)"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"    {lbl:10} n {len(p):5d} | win {(p>0).mean()*100:4.1f}% | "
            f"exp {m:+.3f}% [{lo:+.3f},{hi:+.3f}] {sig}")


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    res = {"A vol-breakout": [], "B NR7": [], "D vol-spike": []}
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        d = d.set_index("timestamp")
        day = d.resample("1D").agg({"open": "first", "high": "max", "low": "min",
                                    "close": "last", "volume": "sum"}).dropna()
        rng_ = day["high"] - day["low"]
        atr20 = rng_.rolling(20).mean().shift(1)
        nr7 = rng_ == rng_.rolling(7).min()
        vma20 = day["volume"].rolling(20).mean().shift(1)
        horas = {t: g for t, g in d.groupby(d.index.normalize())}

        for i in range(21, len(day) - 1):
            t = day.index[i]
            hh = horas.get(t)
            if hh is None or len(hh) < 20:
                continue
            o, cl = day["open"].iloc[i], day["close"].iloc[i]
            a = atr20.iloc[i]
            year = t.year
            # A. volatility breakout
            if not np.isnan(a):
                up, dn = o + 0.5 * a, o - 0.5 * a
                for _, h in hh.iterrows():
                    if h["high"] >= up:
                        res["A vol-breakout"].append(
                            (year, (cl - up) / up * 100 - COST))
                        break
                    if h["low"] <= dn:
                        res["A vol-breakout"].append(
                            (year, (dn - cl) / dn * 100 - COST))
                        break
            # B. NR7 (ayer estrecho -> hoy romper el rango de ayer)
            if nr7.iloc[i - 1]:
                hi_y, lo_y = day["high"].iloc[i - 1], day["low"].iloc[i - 1]
                for _, h in hh.iterrows():
                    if h["high"] >= hi_y:
                        res["B NR7"].append((year, (cl - hi_y) / hi_y * 100 - COST))
                        break
                    if h["low"] <= lo_y:
                        res["B NR7"].append((year, (lo_y - cl) / lo_y * 100 - COST))
                        break
            # D. pico de volumen ayer -> seguir hoy la dirección de ayer
            v_y, vm = day["volume"].iloc[i - 1], vma20.iloc[i - 1]
            if not np.isnan(vm) and vm > 0 and v_y > 3 * vm:
                dir_y = np.sign(day["close"].iloc[i - 1] - day["open"].iloc[i - 1])
                if dir_y != 0:
                    r = dir_y * (cl - o) / o * 100 - COST
                    res["D vol-spike"].append((year, r))

    for k, rows in res.items():
        print(f"\n[{k}]")
        p_all = [p for _, p in rows]
        print(stats_line(p_all, "TOTAL"))
        print(stats_line([p for y, p in rows if y < 2026], "IS 24-25"))
        print(stats_line([p for y, p in rows if y >= 2026], "OOS 2026"))


if __name__ == "__main__":
    main()
