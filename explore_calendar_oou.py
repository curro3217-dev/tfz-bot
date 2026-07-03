"""
EXPLORACIÓN #12: MATRIZ CALENDARIO COMPLETA, dentro y fuera de universo (2026-07-03).

El barrido original (explore_weekend) señaló 4 candidatos de calendario (momentum
diario: señal = signo del día D, mantener el día D+1):
  PRE-ESPECIFICADOS (antes de mirar esta tanda):
    - señal MIÉRCOLES (mantener jueves): momentum POSITIVO (pasó 2/3 años en universo)
    - señal VIERNES (mantener sábado):   momentum POSITIVO (ya replicado, referencia)
    - señal DOMINGO (mantener lunes):    momentum NEGATIVO -> candidato REVERSAL
    - señal LUNES (mantener martes):     momentum NEGATIVO -> candidato REVERSAL
Aquí: los 7 días × 3 años × 2 universos (los 20 de siempre y los 22 nuevos/majors),
neto de costes MEXC. Un candidato solo VALE si el signo esperado aparece en los DOS
universos y en los 3 años (mismo listón que superó el viernes). El resto de celdas
se imprime como contexto, no como cantera de nuevas hipótesis.

Solo lectura. Uso: python explore_calendar_oou.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST = (0.02 + 0.025) * 2
U_ORIG = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
          "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]
U_NUEVO = ["DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
           "1000PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
           "BTC","ETH","BNB","XRP"]
DIAS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]


def momentum_diario(syms, cfg):
    rows = []
    for s in syms:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        daily = d.set_index("timestamp")["close"].resample("1D").last().dropna()
        ret = daily.pct_change()
        r_next = ret.shift(-1)
        ok = ret.notna() & r_next.notna() & (ret != 0)
        pnl = (np.sign(ret[ok]) * r_next[ok] * 100) - COST
        for t, p in pnl.items():
            rows.append({"wd": t.weekday(), "year": t.year, "pnl": p})
    return pd.DataFrame(rows)


def celda(g):
    p = g["pnl"].values
    if len(p) < 30:
        return "   (pocos)   "
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    star = "*" if (m - 1.96 * se > 0 or m + 1.96 * se < 0) else " "
    return f"{m:+.3f}{star} n{len(p):4d}"


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    for nombre, syms in (("UNIVERSO ORIGINAL (20)", U_ORIG),
                         ("UNIVERSO NUEVO (22, incl. majors)", U_NUEVO)):
        df = momentum_diario(syms, cfg)
        print(f"\n=== {nombre} — momentum señal día D -> mantener D+1, neto "
              f"(* = IC95 excluye 0) ===")
        print(f"{'señal':>6} {'2024':>16} {'2025':>16} {'2026':>16}")
        for wd in range(7):
            fila = [f"{DIAS[wd]:>6}"]
            for y in (2024, 2025, 2026):
                g = df[(df.wd == wd) & (df.year == y)]
                fila.append(f"{celda(g):>16}")
            print(" ".join(fila))
    print("\nCandidatos pre-especificados: mie(+), vie(+ ya validado), dom(-), lun(-).")
    print("Listón: mismo signo esperado en los 3 años Y en los dos universos.")


if __name__ == "__main__":
    main()
