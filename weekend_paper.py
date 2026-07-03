"""
PAPER independiente del MOMENTUM VIERNES->SÁBADO (2026-07-03). NO toca el bot
principal: BD propia (weekend_paper.db), proceso propio, nada compartido con la
medición congelada de micro_pullback.

REGLA MEDIDA (la única variante que sobrevivió TODAS las pruebas de estrés en
explore_weekend + robustez; ver CHANGELOG 2026-07-03):
  - sábado 00:00 UTC: dirección = signo del retorno del VIERNES (00:00->24:00 UTC)
  - hold 24h exacto (salida domingo 00:00 UTC), cierres diarios desde velas 1h
  - universo: los 20 símbolos de siempre | costes: modelo MEXC (0.09% i/v)
  - histórico 2024/2025/2026: exp +0.55/+0.60/+0.56%/trade, IC95 excluye 0 los 3
    años; longs y shorts positivos; 17/18 símbolos; sin top-5 días +0.18% (cola gorda)

FORWARD-ONLY: solo se registran sábados POSTERIORES al pre-registro (START_TS).
Rellenar hacia atrás sería otro backtest, no una medición.

CRITERIO PRE-REGISTRADO (PROPUESTA, ajustable ANTES del primer sábado; después no
se toca): a >=20 sábados medidos, hay edge si la media de las MEDIAS SEMANALES
(1 dato por sábado, inmune a la correlación entre símbolos) es > +0.15% con IC95
excluyendo cero. Si no, se retira.

Uso (pensado para tarea programada cualquier momento tras el domingo 01:00 UTC):
  python weekend_paper.py            # registra los sábados pendientes ya cerrados
  python weekend_paper.py --status   # estado y criterio
Env: TFZ_WKND_DB para separar cuentas (PC vs GitHub).
"""
import os
# OJO: aqui NO se fuerza INSECURE_SSL (esto corre tambien en GitHub, donde el SSL
# funciona bien). En el PC lo pone run_weekend_paper.cmd, como run_tfz_paper.cmd.

import sys
import sqlite3
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv

DB = os.environ.get("TFZ_WKND_DB",
                    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "weekend_paper.db"))
START_TS = pd.Timestamp("2026-07-03 12:00:00")   # pre-registro: solo sábados >= aquí
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]
COST = (0.02 + 0.025) * 2


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS wknd_trades (
        symbol TEXT, sabado TEXT, direction TEXT,
        fri_ret REAL, sat_ret REAL, pnl_pct REAL,
        PRIMARY KEY (symbol, sabado))""")
    c.commit()
    return c


def record_pending(conn, cfg, verbose=True):
    """Registra cada sábado>=START ya CERRADO (domingo 00:00 pasado) no guardado."""
    added = 0
    for s in SYMS:
        sym = f"{s}/USDT:USDT"
        try:
            df = fetch_ohlcv(sym, "1h", limit=24 * 30, config=cfg)  # ~1 mes de velas
        except Exception as e:
            if verbose:
                print(f"  {s}: fetch error {e}")
            continue
        daily = df.set_index("timestamp")["close"].resample("1D").last().dropna()
        ret = daily.pct_change()
        for t in daily.index:
            # t etiqueta el día; el trade "sábado t" necesita viernes t-1 y domingo t+1
            if t.weekday() != 5 or t < START_TS:
                continue
            # ret[x] = retorno DURANTE el día x (cierre de x vs cierre de x-1).
            # señal = retorno del VIERNES (t-1d); resultado = retorno del SÁBADO (t).
            # t_sun en el índice garantiza que la última vela del sábado está CERRADA.
            t_fri, t_sun = t - pd.Timedelta(days=1), t + pd.Timedelta(days=1)
            if t_fri not in ret.index or t_sun not in daily.index:
                continue
            fri_ret, sat_ret = ret[t_fri], ret[t]
            if pd.isna(fri_ret) or pd.isna(sat_ret) or fri_ret == 0:
                continue
            pnl = float(np.sign(fri_ret) * sat_ret * 100 - COST)
            cur = conn.execute(
                "INSERT OR IGNORE INTO wknd_trades VALUES (?,?,?,?,?,?)",
                (sym, str(t.date()), "long" if fri_ret > 0 else "short",
                 float(fri_ret), float(sat_ret), round(pnl, 4)))
            conn.commit()
            if cur.rowcount:
                added += 1
                if verbose:
                    print(f"  [reg] {s:7} sabado {t.date()} "
                          f"{'long' if fri_ret > 0 else 'short'} {pnl:+.3f}%")
    return added


def status(conn):
    rows = conn.execute("SELECT sabado, pnl_pct FROM wknd_trades").fetchall()
    print(f"\nWEEKEND PAPER — BD {DB}")
    print(f"  trades registrados: {len(rows)} (solo sábados >= {START_TS.date()})")
    if not rows:
        print("  (el primer sábado medible es el siguiente al pre-registro)")
        return
    df = pd.DataFrame([dict(r) for r in rows])
    weekly = df.groupby("sabado")["pnl_pct"].mean()
    print(f"  sábados medidos: {len(weekly)}/20 mínimos del criterio")
    if len(weekly) >= 2:
        m = weekly.mean(); se = weekly.std(ddof=1) / np.sqrt(len(weekly))
        print(f"  media de medias semanales {m:+.3f}% "
              f"[IC95 {m-1.96*se:+.3f},{m+1.96*se:+.3f}] | criterio: > +0.15% excluyendo 0")


def main():
    conn = _conn()
    if "--status" in sys.argv:
        status(conn)
        return
    cfg = config_for_timeframe(TFZConfig(), "1h")
    record_pending(conn, cfg)
    status(conn)


if __name__ == "__main__":
    main()
