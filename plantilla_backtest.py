"""
PLANTILLA de backtest rápido (2026-07-14) — el bucle de "The Backtest Machine"
(articular -> codificar -> correr -> leer) con las herramientas de la casa.
Solo lectura: no toca BDs ni mediciones. Ver PLANTILLA_BACKTEST.md para el flujo
completo y los prompts.

CÓMO SE USA: copia este archivo (p.ej. bt_mi_estrategia.py), edita el bloque
ESTRATEGIA (la función `position` y PARAM_GRID) y córrelo. La infraestructura
(datos MEXC, fills en la apertura siguiente, costes, meseta, IS/OOS, buy&hold)
ya está montada y es la misma para todas las pruebas -> comparaciones limpias.

Convenciones fijas (no tocar al comparar estrategias entre sí):
  - señal SOLO con la vela cerrada; fill en la APERTURA de la vela siguiente
  - costes modelo MEXC 0.045%/lado (0.09% ida+vuelta); funding NO modelado
  - meseta obligatoria: una estrategia real es meseta, no pico
  - IS/OOS: OOS = último año; si solo funciona en uno de los dos, no vale
"""
import sys
import numpy as np
import pandas as pd
from config import TFZConfig
from data_fetcher import fetch_ohlcv

# ======================= ESTRATEGIA (edita este bloque) =======================
NOMBRE = "EMA cross (ejemplo)"
SYMBOL = "BTC/USDT:USDT"
TIMEFRAME = "1d"          # cualquier tf soportado: 15m, 1h, 4h, 1d...
VELAS = 1200              # cuántas velas descargar (incluye calentamiento)
OOS_DESDE = "2025-07-14"  # el último año se reserva como out-of-sample


def position(df: pd.DataFrame, fast=9, slow=21) -> pd.Series:
    """Devuelve la posición DESEADA tras cada cierre: +1 largo, 0 plano, -1 corto.
    Solo puede usar información disponible AL CIERRE de cada vela (nada de
    mirar el futuro: cualquier rolling/shift debe ser causal)."""
    f = df["close"].ewm(span=fast, adjust=False).mean()
    s = df["close"].ewm(span=slow, adjust=False).mean()
    return pd.Series(np.where(f > s, 1, 0), index=df.index)


# Variantes para el test de meseta (la primera es la "oficial")
PARAM_GRID = [dict(fast=9, slow=21), dict(fast=8, slow=20), dict(fast=10, slow=22),
              dict(fast=12, slow=26), dict(fast=5, slow=15)]
# ==============================================================================

COST_SIDE = 0.045  # % por lado, modelo MEXC


def backtest(df, pos):
    """Fills en la apertura siguiente al cambio de posición; devuelve métricas."""
    pos = pos.shift(1).fillna(0)          # la posición decidida al cierre t opera en t+1
    px_in = df["open"]                    # fill = apertura de la vela donde se entra
    cambios = pos.diff().fillna(pos)
    trades, entry_px, entry_i, side = [], None, None, 0
    for i in range(len(df)):
        if cambios.iloc[i] == 0:
            continue
        if side != 0:                     # cerrar lo abierto
            ret = side * (px_in.iloc[i] / entry_px - 1) * 100 - 2 * COST_SIDE
            trades.append(ret)
        side = int(pos.iloc[i])
        entry_px = px_in.iloc[i] if side != 0 else None
    if side != 0:                         # cierre a mercado al final
        trades.append(side * (df["close"].iloc[-1] / entry_px - 1) * 100 - 2 * COST_SIDE)
    # equity diaria para el drawdown
    ret_v = df["close"].pct_change().fillna(0) * pos
    eq = (1 + ret_v).cumprod()
    dd = ((eq - eq.cummax()) / eq.cummax()).min() * 100
    t = np.array(trades)
    wins, losses = t[t > 0], t[t <= 0]
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else float("inf")
    total = (np.prod(1 + t / 100) - 1) * 100 if len(t) else 0.0
    return dict(n=len(t), wr=len(wins) / len(t) * 100 if len(t) else 0,
                pf=pf, ret=total, dd=dd)


def linea(tag, m):
    pf = f"{m['pf']:5.2f}" if m["pf"] != float("inf") else "  inf"
    print(f"  {tag:<22} n={m['n']:>3}  WR {m['wr']:5.1f}%  PF {pf}  "
          f"ret {m['ret']:+8.1f}%  maxDD {m['dd']:6.1f}%")


def main():
    print(f"{NOMBRE} — {SYMBOL} {TIMEFRAME} — {VELAS} velas, costes "
          f"{2*COST_SIDE:.2f}% i/v, fill apertura siguiente")
    df = fetch_ohlcv(SYMBOL, TIMEFRAME, limit=VELAS, config=TFZConfig())
    df = df.sort_values("timestamp").reset_index(drop=True)[:-1]  # fuera la vela viva
    print(f"datos: {df['timestamp'].iloc[0].date()} -> {df['timestamp'].iloc[-1].date()}")

    # buy & hold como listón
    bh_eq = df["close"] / df["close"].iloc[0]
    bh_dd = ((bh_eq - bh_eq.cummax()) / bh_eq.cummax()).min() * 100
    print(f"\nbuy&hold: ret {(bh_eq.iloc[-1]-1)*100:+.1f}%  maxDD {bh_dd:.1f}%")

    print("\nMESETA (todo el rango):")
    for p in PARAM_GRID:
        linea(str(p), backtest(df, position(df, **p)))

    corte = df["timestamp"] < pd.Timestamp(OOS_DESDE)
    d_is, d_oos = df[corte].reset_index(drop=True), df[~corte].reset_index(drop=True)
    print(f"\nIS (hasta {OOS_DESDE}) vs OOS (desde {OOS_DESDE}), parámetros oficiales:")
    if len(d_is) > 50:
        linea("IS", backtest(d_is, position(d_is, **PARAM_GRID[0])))
    if len(d_oos) > 50:
        linea("OOS", backtest(d_oos, position(d_oos, **PARAM_GRID[0])))

    print("\nRecordatorios: n>=20 trades o es anécdota | meseta, no pico | "
          "funding no incluido | el veredicto final es el forward test.")


if __name__ == "__main__":
    main()
