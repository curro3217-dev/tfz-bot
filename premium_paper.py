"""
PAPER independiente de la PRIMA DE COINBASE (2026-07-03). BD propia, no toca nada
del bot ni de las otras mediciones.

REGLA MEDIDA (explore_premium + analyze_premium): cuando la prima de Coinbase
(BTC/USD en Coinbase vs BTC/USDT en MEXC; correlación 0.992 con la pata Binance,
que está geo-bloqueada en GitHub) cruza z >= +1 (z-score móvil de 90 días, SOLO
pasado, episodios no solapados: cuenta el PRIMER día del cruce), LONG BTC 7 días.
Histórico 2018-2026: +2.46%/7d medio, +1.67% de exceso sobre deriva, 8/9 años
positivos PERO 2025 negativo (-0.45%) -> por eso se mide forward antes de nada.

CRITERIO PRE-REGISTRADO (sellado 2026-07-03): a >=30 episodios, hay edge si la
media es > +1.0%/7d con IC95 excluyendo cero. Si no, se retira. Ritmo histórico
~20-25 episodios/año -> veredicto en ~1.5 años. FORWARD-ONLY (episodios >= hoy).

Uso: python premium_paper.py          (una pasada: cierra vencidos, abre si hay cruce)
     python premium_paper.py --status
Env: TFZ_PREM_DB para separar cuentas (PC vs GitHub).
"""
import os
# INSECURE_SSL lo pone el .cmd del PC; en GitHub va SSL verificado.

import sys
import sqlite3
import numpy as np
import pandas as pd
import ccxt

DB = os.environ.get("TFZ_PREM_DB",
                    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "premium_paper.db"))
START = pd.Timestamp("2026-07-03")
Z_THR = 1.0
HOLD_D = 7
COST = (0.02 + 0.025) * 2


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS prem_trades (
        entry_date TEXT PRIMARY KEY, z REAL, entry_px REAL,
        status TEXT DEFAULT 'open', exit_date TEXT, exit_px REAL, pnl_pct REAL)""")
    c.commit()
    return c


def _ex(name):
    ex = getattr(ccxt, name)({"enableRateLimit": True, "timeout": 20000})
    if os.environ.get("INSECURE_SSL") == "1":
        ex.verify = False
    ex.load_markets()
    return ex


def _closes(ex, sym, limit=130):
    c = ex.fetch_ohlcv(sym, "1d", limit=limit)
    s = pd.Series({pd.to_datetime(x[0], unit="ms").normalize(): float(x[4])
                   for x in c}).sort_index()
    return s.iloc[:-1]   # la última vela diaria puede estar EN FORMACIÓN -> fuera


def zeta():
    cb = _closes(_ex("coinbaseexchange"), "BTC/USD")
    mx = _closes(_ex("mexc"), "BTC/USDT")
    df = pd.DataFrame({"cb": cb, "mx": mx}).dropna()
    prem = (df["cb"] / df["mx"] - 1) * 100
    z = ((prem - prem.rolling(90).mean().shift(1))
         / prem.rolling(90).std().shift(1)).dropna()
    return z, df["mx"]


def run(conn):
    z, px = zeta()
    hoy = z.index[-1]
    # cerrar vencidos
    for t in conn.execute("SELECT * FROM prem_trades WHERE status='open'").fetchall():
        entry = pd.Timestamp(t["entry_date"])
        t_exit = entry + pd.Timedelta(days=HOLD_D)
        if t_exit in px.index:
            exit_px = float(px[t_exit])
            pnl = (exit_px - t["entry_px"]) / t["entry_px"] * 100 - COST
            conn.execute("UPDATE prem_trades SET status='closed', exit_date=?, "
                         "exit_px=?, pnl_pct=? WHERE entry_date=?",
                         (str(t_exit.date()), exit_px, round(pnl, 4), t["entry_date"]))
            conn.commit()
            print(f"  [closed] {t['entry_date']} -> {pnl:+.2f}%")
    # abrir si el ULTIMO día cerrado es un CRUCE (episodio nuevo) y es >= START
    if hoy >= START and z.iloc[-1] >= Z_THR and (len(z) < 2 or z.iloc[-2] < Z_THR):
        cur = conn.execute(
            "INSERT OR IGNORE INTO prem_trades (entry_date, z, entry_px) VALUES (?,?,?)",
            (str(hoy.date()), float(z.iloc[-1]), float(px[hoy])))
        conn.commit()
        if cur.rowcount:
            print(f"  [opened] {hoy.date()} z={z.iloc[-1]:+.2f} px={px[hoy]:.0f}")
    print(f"  z del último día cerrado ({hoy.date()}): {z.iloc[-1]:+.2f} "
          f"(umbral +{Z_THR})")


def status(conn):
    rows = conn.execute(
        "SELECT pnl_pct FROM prem_trades WHERE status='closed'").fetchall()
    n_open = conn.execute(
        "SELECT COUNT(*) FROM prem_trades WHERE status='open'").fetchone()[0]
    p = np.array([r["pnl_pct"] for r in rows if r["pnl_pct"] is not None])
    print(f"\nPREMIUM PAPER — BD {DB}")
    print(f"  abiertos {n_open} | cerrados {len(p)} / 30 del criterio")
    if len(p) >= 2:
        se = p.std(ddof=1) / np.sqrt(len(p))
        print(f"  media {p.mean():+.2f}%/7d [IC95 {p.mean()-1.96*se:+.2f},"
              f"{p.mean()+1.96*se:+.2f}] | criterio: > +1.0% excluyendo 0")


def main():
    conn = _conn()
    if "--status" in sys.argv:
        status(conn)
        return
    run(conn)
    status(conn)


if __name__ == "__main__":
    main()
