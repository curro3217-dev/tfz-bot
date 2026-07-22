"""FORWARD PAPER pre-registrado: fenomenos especificos de MOVERS (universo point-in-time
por construccion: se mide sobre los movers VIVOS del scanner en cada momento).

Dos hipotesis selladas (2026-07-16), nacidas del Pattern Lab y NO medibles hacia atras
por el sesgo de seleccion del universo (murieron en majors, viven solo en movers):
  H1 "decaimiento post-pump": divergencia oculta bajista RSI en 1h -> SHORT 5 velas.
  H2 "ruptura con volumen":  primer cierre sobre el max de 20 velas con RVOL>=2 en 1h
                              -> LONG 5 velas.

Mecanica: cada ejecucion (cada ciclo del bot en GitHub) mira SOLO la ultima vela 1h
CERRADA de cada mover vivo; si hay señal, la registra (dedup por simbolo+patron+vela).
Salida fija a las 5 velas 1h (mismo horizonte que el evento-estudio), PnL neto de 0.24%.

CRITERIO PRE-REGISTRADO (evaluacion UNICA a 100 señales por hipotesis, Bonferroni x2):
  media neta > +0.20%/señal con IC95 excluyendo cero -> pasa a considerarse edge real.
  Si no -> se archiva. PROHIBIDO tocar definiciones/umbrales durante la medicion.
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import argparse
import sqlite3
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv
from pattern_lab3 import rsi_wilder, sma

COST = 0.24
HOLD = 5  # velas 1h


def detect_at_last_closed(df):
    """Devuelve lista de (patron, dir, ts, precio) SOLO para la ultima vela cerrada."""
    O = df["open"].values.astype(float); H = df["high"].values.astype(float)
    L = df["low"].values.astype(float); C = df["close"].values.astype(float)
    V = df["volume"].values.astype(float)
    n = len(C)
    i = n - 2  # ultima CERRADA (la n-1 puede estar formandose)
    if i < 230:
        return []
    out = []
    R = rsi_wilder(C)
    s20 = sma(C, 20)
    # H1: divergencia oculta bajista (definicion EXACTA de pattern_lab3)
    k = i - 20 + int(np.argmax(H[i - 20:i]))
    if H[i] < H[k] and R[i] > R[k] + 2 and C[i] < s20[i]:
        out.append(("div_oculta_bajista", -1, str(df["timestamp"].iloc[i]), float(C[i])))
    # H2: ruptura de max20 con volumen (definicion EXACTA de pattern_lab45)
    cs = np.cumsum(V)
    v20 = (cs[i - 1] - cs[i - 21]) / 20
    if v20 > 0:
        hh = H[i - 20:i].max()
        prev_hh = H[i - 21:i - 1].max()
        if C[i] > hh and C[i - 1] <= prev_hh and V[i] / v20 >= 2:
            out.append(("ruptura_con_volumen", +1, str(df["timestamp"].iloc[i]), float(C[i])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="postpump_paper.db")
    args = ap.parse_args()
    conn = sqlite3.connect(args.db)
    conn.execute("""CREATE TABLE IF NOT EXISTS señales (
        symbol TEXT, pattern TEXT, ts TEXT, dir INTEGER, entry REAL,
        exit_price REAL, pnl_net REAL, status TEXT DEFAULT 'open',
        PRIMARY KEY (symbol, pattern, ts))""")

    # universo vivo (point-in-time): scanner; fallback al fichero
    try:
        from scanner_bridge import get_perp_watchlist
        syms = get_perp_watchlist()
    except Exception:
        syms = [s.strip() for s in open("_universe.txt").read().split(",") if s.strip()]
    tfc = config_for_timeframe(TFZConfig(), "1h")

    nuevos = cerrados = 0
    for sym in syms:
        try:
            df = fetch_ohlcv(sym, "1h", limit=300, config=tfc)
        except Exception:
            continue
        if len(df) < 240:
            continue
        # 1) registrar señales nuevas en la ultima vela cerrada
        for pat, d, ts, px in detect_at_last_closed(df):
            cur = conn.execute("INSERT OR IGNORE INTO señales(symbol,pattern,ts,dir,entry) VALUES (?,?,?,?,?)",
                               (sym, pat, ts, d, px))
            if cur.rowcount:
                nuevos += 1
                print(f"  [señal] {pat:20s} {sym:18s} @ {ts} entry {px:.6g}")
        # 2) resolver señales abiertas con HOLD velas cumplidas
        tss = df["timestamp"].astype(str).tolist()
        for symbol, pat, ts, d, entry in conn.execute(
                "SELECT symbol,pattern,ts,dir,entry FROM señales WHERE status='open' AND symbol=?", (sym,)).fetchall():
            if ts not in tss:
                continue
            idx = tss.index(ts)
            if idx + HOLD <= len(df) - 2:  # la vela de salida ya esta cerrada
                exit_px = float(df["close"].iloc[idx + HOLD])
                pnl = d * (exit_px - entry) / entry * 100 - COST
                conn.execute("UPDATE señales SET exit_price=?, pnl_net=?, status='closed' "
                             "WHERE symbol=? AND pattern=? AND ts=?", (exit_px, pnl, symbol, pat, ts))
                cerrados += 1
    conn.commit()

    # resumen
    print(f"\npostpump_paper: {nuevos} señales nuevas, {cerrados} resueltas este ciclo")
    for pat, in conn.execute("SELECT DISTINCT pattern FROM señales").fetchall():
        rows = [r[0] for r in conn.execute(
            "SELECT pnl_net FROM señales WHERE pattern=? AND status='closed'", (pat,)).fetchall()]
        no = conn.execute("SELECT COUNT(*) FROM señales WHERE pattern=? AND status='open'", (pat,)).fetchone()[0]
        if rows:
            a = np.array(rows)
            se = a.std(ddof=1) / np.sqrt(len(a)) if len(a) > 1 else 0
            print(f"  {pat:22s} cerradas {len(a):4d} (abiertas {no}) | media neta {a.mean():+.3f}% "
                  f"| IC95 [{a.mean()-1.96*se:+.3f}, {a.mean()+1.96*se:+.3f}] | objetivo: 100 señales")
        else:
            print(f"  {pat:22s} cerradas 0 (abiertas {no})")
    conn.close()


if __name__ == "__main__":
    main()
