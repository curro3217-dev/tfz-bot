"""
EXPLORACIÓN #7: ESTACIONALIDAD POR HORA DEL DÍA (UTC) (2026-07-03).

¿Hay horas/sesiones del día con retorno medio sistemático en el universo?
(análogo intradía del efecto día-de-semana que encontró el vie->sáb).

Disciplina anti-espejismo:
  - DESCUBRIR en 2024+2025: media por hora UTC y por sesión de 8h.
  - VALIDAR en 2026: ¿las mejores/peores horas del IS repiten señal en OOS?
  - dato = DÍA (media entre símbolos de esa hora ese día): inmune a correlación.
  - listón de realidad: una operación de 1h cuesta 0.09% i/v -> la media por hora
    tiene que superarlo para ser operable; si no, es curiosidad, no estrategia.

Solo lectura. Uso: python explore_hourday.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST = (0.02 + 0.025) * 2
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]
SESIONES = {"Asia 00-08": range(0, 8), "Europa 08-16": range(8, 16),
            "USA 16-24": range(16, 24)}


def resumen(g):
    p = np.asarray(g, dtype=float)
    if len(p) < 30:
        return None
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    return m, m - 1.96 * se, m + 1.96 * se, len(p)


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    frames = []
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        d = d.set_index("timestamp")
        r = d["close"].pct_change() * 100
        frames.append(r.rename(s))
    R = pd.concat(frames, axis=1)
    # dato = media entre símbolos por vela (1 dato por hora de reloj)
    m = R.mean(axis=1).dropna()
    df = pd.DataFrame({"r": m})
    df["hora"] = df.index.hour
    df["fecha"] = df.index.date
    df["is_"] = df.index.year < 2026

    print("=== MEDIA POR HORA UTC (bruto, %/hora; dato = media del universo por vela) ===")
    print(f"{'hora':>4} {'IS 24-25':>22} {'OOS 2026':>22}  ¿repite?")
    filas = []
    for h in range(24):
        a = resumen(df[(df.hora == h) & df.is_]["r"])
        b = resumen(df[(df.hora == h) & ~df.is_]["r"])
        if not a or not b:
            continue
        rep = "SI" if np.sign(a[0]) == np.sign(b[0]) else "no"
        filas.append((h, a, b, rep))
        print(f"{h:4d} {a[0]:+.4f} [{a[1]:+.4f},{a[2]:+.4f}] "
              f"{b[0]:+.4f} [{b[1]:+.4f},{b[2]:+.4f}]  {rep}")

    print(f"\n(listón operable 1h: {COST:.2f}% i/v -> hace falta |media| > {COST:.2f}%)")

    print("\n=== SESIONES de 8h (bruto por sesión = suma de sus horas) ===")
    df["ses"] = df["hora"].apply(
        lambda h: next(k for k, v in SESIONES.items() if h in v))
    diario = df.groupby(["fecha", "ses", "is_"])["r"].sum().reset_index()
    for ses in SESIONES:
        a = resumen(diario[(diario.ses == ses) & diario.is_]["r"])
        b = resumen(diario[(diario.ses == ses) & ~diario.is_]["r"])
        if not a or not b:
            continue
        rep = "SI" if np.sign(a[0]) == np.sign(b[0]) else "no"
        print(f"  {ses:14} IS {a[0]:+.3f}%/ses [{a[1]:+.3f},{a[2]:+.3f}] | "
              f"OOS {b[0]:+.3f}% [{b[1]:+.3f},{b[2]:+.3f}]  repite:{rep} "
              f"(listón {COST:.2f}%)")


if __name__ == "__main__":
    main()
