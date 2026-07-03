"""
PAPER independiente de la PRIMA DE COINBASE (2026-07-03). BD propia, no toca nada
del bot ni de las otras mediciones.

REGLAS MEDIDAS (explore_premium + analyze_premium + explore_premium_family): cuando
la prima de Coinbase (precio USD en Coinbase vs USDT en MEXC; correlación 0.992 con
la pata Binance, que está geo-bloqueada en GitHub) cruza z >= +1 (z-score móvil de
90 días, SOLO pasado, episodios no solapados: cuenta el PRIMER día del cruce),
LONG 7 días. DOS reglas independientes, cada una con su prima y su moneda:
  BTC: histórico +2.46%/7d, exceso +1.67% sobre deriva, 8/9 años (+2025 negativo)
  ETH: histórico +3.35%/7d, exceso +2.4%, 8/9 años (2022 y 2025 flojos), OOS +3.62%

CRITERIOS PRE-REGISTRADOS (sellados 2026-07-03, antes de dato alguno): a >=30
episodios de cada regla, hay edge si su media es > +1.0%/7d (BTC) / > +1.5%/7d (ETH)
con IC95 excluyendo cero. La que no lo cumpla, se retira. Ritmo histórico ~20-25
episodios/año por moneda. FORWARD-ONLY (episodios >= hoy).

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
# (moneda, símbolo Coinbase, símbolo MEXC, listón del criterio %/7d)
REGLAS = [("BTC", "BTC/USD", "BTC/USDT", 1.0),
          ("ETH", "ETH/USD", "ETH/USDT", 1.5)]


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS prem_trades (
        symbol TEXT, entry_date TEXT, z REAL, entry_px REAL,
        status TEXT DEFAULT 'open', exit_date TEXT, exit_px REAL, pnl_pct REAL,
        PRIMARY KEY (symbol, entry_date))""")
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


def zeta(ex_cb, ex_mx, sym_cb, sym_mx):
    cb = _closes(ex_cb, sym_cb)
    mx = _closes(ex_mx, sym_mx)
    df = pd.DataFrame({"cb": cb, "mx": mx}).dropna()
    prem = (df["cb"] / df["mx"] - 1) * 100
    z = ((prem - prem.rolling(90).mean().shift(1))
         / prem.rolling(90).std().shift(1)).dropna()
    return z, df["mx"]


def run(conn):
    ex_cb = _ex("coinbaseexchange")
    ex_mx = _ex("mexc")
    for moneda, sym_cb, sym_mx, _ in REGLAS:
        try:
            z, px = zeta(ex_cb, ex_mx, sym_cb, sym_mx)
        except Exception as e:
            print(f"  {moneda}: error de datos {e}")
            continue
        hoy = z.index[-1]
        # cerrar vencidos
        for t in conn.execute("SELECT * FROM prem_trades WHERE status='open' AND "
                              "symbol=?", (moneda,)).fetchall():
            entry = pd.Timestamp(t["entry_date"])
            t_exit = entry + pd.Timedelta(days=HOLD_D)
            if t_exit in px.index:
                exit_px = float(px[t_exit])
                pnl = (exit_px - t["entry_px"]) / t["entry_px"] * 100 - COST
                conn.execute("UPDATE prem_trades SET status='closed', exit_date=?, "
                             "exit_px=?, pnl_pct=? WHERE symbol=? AND entry_date=?",
                             (str(t_exit.date()), exit_px, round(pnl, 4),
                              moneda, t["entry_date"]))
                conn.commit()
                print(f"  [closed] {moneda} {t['entry_date']} -> {pnl:+.2f}%")
        # abrir si el ULTIMO día cerrado es un CRUCE (episodio nuevo) y es >= START
        if hoy >= START and z.iloc[-1] >= Z_THR and (len(z) < 2 or z.iloc[-2] < Z_THR):
            cur = conn.execute(
                "INSERT OR IGNORE INTO prem_trades (symbol, entry_date, z, entry_px) "
                "VALUES (?,?,?,?)",
                (moneda, str(hoy.date()), float(z.iloc[-1]), float(px[hoy])))
            conn.commit()
            if cur.rowcount:
                print(f"  [opened] {moneda} {hoy.date()} z={z.iloc[-1]:+.2f}")
                try:  # aviso informativo (fail-silent; solo donde TFZ_TELEGRAM=1)
                    from notify import send_telegram
                    send_telegram(f"📊 <b>Prima Coinbase {moneda}</b>: episodio nuevo "
                                  f"(z={z.iloc[-1]:+.2f}). Medición paper 7d en curso "
                                  f"({hoy.date()}). No es orden de operar.")
                except Exception:
                    pass
        print(f"  {moneda}: z del último día cerrado ({hoy.date()}) = "
              f"{z.iloc[-1]:+.2f} (umbral +{Z_THR})")


def status(conn):
    print(f"\nPREMIUM PAPER — BD {DB}")
    for moneda, _, _, liston in REGLAS:
        rows = conn.execute("SELECT pnl_pct FROM prem_trades WHERE status='closed' "
                            "AND symbol=?", (moneda,)).fetchall()
        n_open = conn.execute("SELECT COUNT(*) FROM prem_trades WHERE status='open' "
                              "AND symbol=?", (moneda,)).fetchone()[0]
        p = np.array([r["pnl_pct"] for r in rows if r["pnl_pct"] is not None])
        linea = f"  {moneda}: abiertos {n_open} | cerrados {len(p)}/30"
        if len(p) >= 2:
            se = p.std(ddof=1) / np.sqrt(len(p))
            linea += (f" | media {p.mean():+.2f}%/7d [{p.mean()-1.96*se:+.2f},"
                      f"{p.mean()+1.96*se:+.2f}]")
        linea += f" | criterio: > +{liston:.1f}% excluyendo 0"
        print(linea)


def main():
    conn = _conn()
    if "--status" in sys.argv:
        status(conn)
        return
    run(conn)
    status(conn)


if __name__ == "__main__":
    main()
