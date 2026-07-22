"""COMPARACIÓN forward: mismo cruce EMA 9/21 BTC diario, DOS tamaños (1x vs GARCH).

Pre-registro 2026-07-22. NO toca la medición congelada de ema_cross_paper.py:
LEE su BD en solo-lectura (mismas señales garantizadas, invariante del conteo)
y solo añade el multiplicador GARCH de cada entrada en BD propia.

QUÉ MIDE: si el sizing por volatilidad (mult = target_vol / forecast_vol,
recortado a [0.25x, 2.0x], GARCH(1,1) walk-forward de garch_sizing.py) mejora
el riesgo del MISMO conjunto de trades. PnL sized = mult * (pnl_bruto - COST)
con el mult congelado en el fill de entrada.

TARGET PRE-REGISTRADO: 35% anual (risk-matched: vol realizada de la estrategia
a tamaño fijo en la réplica MEXC 2020->2026 fue 33.7%; guía del repo garchmethod
"target ≈ vol realizada de la propia estrategia"). En esa réplica SIN costes el
vol-targeting dio CAGR 12.3 vs 10.7, Sharpe 0.63 vs 0.47, maxDD -38.6 vs -60.2.
Esto es backtest, NO veredicto; lo que cuenta es esta medición forward.

SIN LOOKAHEAD AUNQUE SE CORRA TARDE: el walk-forward asigna a cada fecha un
forecast hecho SOLO con datos anteriores a su cierre, así que backfillear el
mult de una señal pasada da el mismo número que haberlo calculado aquel día.

CRITERIO (anotado al sellar, igual que ema_cross_paper): con ~6 trades/año no
hay estadística seria a corto plazo. Se reportan ambas equities, drawdown y
|PnL| por trade; SIN veredicto hasta ≥20 trades cerrados (~3 años). Salvedad
fija: funding de perps no modelado en ninguna de las dos variantes.

Idempotente (INSERT OR IGNORE, mult determinista). Uso tras el ciclo diario:
  python garch_sizing_paper.py            # asigna mult a eventos nuevos
  python garch_sizing_paper.py --status   # comparación 1x vs GARCH
Env: TFZ_EMA_DB (BD de eventos, la del EMA paper), TFZ_GARCHCMP_DB (BD propia).
"""
import os
import sys
import sqlite3
import numpy as np
import pandas as pd

from config import TFZConfig
from data_fetcher import fetch_ohlcv
from garch_sizing import _walkforward_garch, size_from_vol, PERIODS_PER_YEAR

EMA_DB = os.environ.get("TFZ_EMA_DB",
                        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "ema_cross_paper.db"))
DB = os.environ.get("TFZ_GARCHCMP_DB",
                    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "garch_sizing_paper.db"))
SYM = "BTC/USDT:USDT"
TARGET_VOL = 35.0                       # PRE-REGISTRADO 2026-07-22, no se cambia
COST = (0.02 + 0.025) * 2               # mismo modelo de costes que ema_cross_paper


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS sized_events (
        signal_date TEXT PRIMARY KEY,   -- misma clave que ema_events
        direction   TEXT,
        vol_ann     REAL,               -- forecast anualizado al cierre de señal
        mult        REAL,               -- target/vol recortado [0.25, 2.0]
        target      REAL)""")
    c.commit()
    return c


def _read_events():
    """Eventos del EMA paper, SOLO LECTURA (mode=ro: imposible tocar la BD)."""
    c = sqlite3.connect(f"file:{EMA_DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    rows = c.execute("SELECT * FROM ema_events ORDER BY signal_date").fetchall()
    c.close()
    return rows


def _mult_by_date():
    """Serie fecha -> (vol_ann, mult) del walk-forward sobre velas cerradas."""
    df = fetch_ohlcv(SYM, "1d", limit=3000, config=TFZConfig())
    df = df.sort_values("timestamp").reset_index(drop=True)
    d = df.iloc[:-1]                     # solo velas CERRADAS
    wf = _walkforward_garch(d["close"].to_numpy(dtype=float))
    if wf is None:
        return {}
    # walkforward indexa sobre retornos: fila i corresponde a la vela i+1 de d
    dates = d["timestamp"].iloc[1:].reset_index(drop=True)
    out = {}
    for i, v in enumerate(wf["fcast_vol"].values):
        if np.isnan(v):
            continue
        vol_ann = float(v) * np.sqrt(PERIODS_PER_YEAR)
        out[str(dates.iloc[i].date())] = (vol_ann, size_from_vol(vol_ann, TARGET_VOL))
    return out


def record_pending(conn, verbose=True):
    events = _read_events()
    if not events:
        print("  sin eventos en la BD del EMA paper: nada que dimensionar")
        return 0
    have = {r["signal_date"] for r in
            conn.execute("SELECT signal_date FROM sized_events").fetchall()}
    nuevos = [e for e in events if e["signal_date"] not in have]
    if not nuevos:
        print(f"  {len(events)} eventos, todos ya dimensionados")
        return 0
    mults = _mult_by_date()
    added = 0
    for e in nuevos:
        m = mults.get(e["signal_date"])
        if m is None:                    # vela aún no cubierta por el walk-forward
            continue
        conn.execute("INSERT OR IGNORE INTO sized_events VALUES (?,?,?,?,?)",
                     (e["signal_date"], e["direction"], round(m[0], 1),
                      round(m[1], 3), TARGET_VOL))
        conn.commit()
        added += 1
        if verbose:
            print(f"  [mult] {e['signal_date']} {e['direction']}: "
                  f"vol {m[0]:.0f}% -> tamaño {m[1]:.2f}x (target {TARGET_VOL:.0f}%)")
    return added


def status(conn):
    events = _read_events()
    sized = {r["signal_date"]: r for r in
             conn.execute("SELECT * FROM sized_events").fetchall()}
    print(f"\nGARCH SIZING PAPER — 1x vs GARCH (target {TARGET_VOL:.0f}%), BD {DB}")
    print(f"  eventos EMA: {len(events)} | dimensionados: {len(sized)}")
    trades, entry = [], None
    for e in events:
        if e["direction"] == "up" and entry is None:
            entry = e
        elif e["direction"] == "dn" and entry is not None:
            s = sized.get(entry["signal_date"])
            mult = s["mult"] if s else None
            raw = (e["fill_px"] / entry["fill_px"] - 1) * 100
            trades.append((entry["fill_date"], e["fill_date"], raw - COST,
                           mult * (raw - COST) if mult is not None else None, mult))
            entry = None
    for t in trades:
        gs = f"{t[3]:+.2f}% ({t[4]:.2f}x)" if t[3] is not None else "sin mult"
        print(f"  {t[0]} -> {t[1]}: fijo {t[2]:+.2f}% | GARCH {gs}")
    if entry is not None:
        s = sized.get(entry["signal_date"])
        ms = f"{s['mult']:.2f}x (vol {s['vol_ann']:.0f}%)" if s else "sin mult"
        print(f"  ABIERTA desde {entry['fill_date']}: tamaño GARCH {ms}")
    cerr = [t for t in trades if t[3] is not None]
    if cerr:
        eqf = eqg = 100.0
        for t in cerr:
            eqf *= 1 + t[2] / 100
            eqg *= 1 + t[3] / 100
        print(f"  cerradas comparables: {len(cerr)} | "
              f"equity fijo {eqf - 100:+.2f}% vs GARCH {eqg - 100:+.2f}%")
    print("  sin veredicto hasta >=20 trades cerrados; funding NO modelado.")


def main():
    conn = _conn()
    if "--status" not in sys.argv:
        record_pending(conn)
    status(conn)


if __name__ == "__main__":
    main()
