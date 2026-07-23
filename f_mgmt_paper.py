"""
PAPER pre-registrado: ¿la GESTIÓN de la operación rescata una señal floja?
(sellado 2026-07-22, idea del libro "How To Day Trade" de Ross Cameron).

Compara DOS formas de gestionar la MISMA señal F del asistente (lee la BD de
f_alerts_paper en SOLO-LECTURA, mode=ro -> imposible tocar esa medición ni las
señales). No genera ninguna señal nueva: reusa exactamente las alertas ya
pre-registradas en f_alerts_paper (mismo universo, mismo START_TS).

Los dos estilos, sobre cada alerta (entry/SL/TP/dirección/TF vienen de la alerta):
  A) FIJO (baseline, = lo que hace f_alerts_paper): gana el primer toque de SL o
     TP. Vela ambigua (ambos en la misma) -> SL (pesimista).
  B) GESTIONADO (Ross Cameron): vender la MITAD al llegar a 1R (= lo que se
     arriesgaba), mover el stop de la otra mitad a BREAKEVEN, y salir de esa
     mitad cuando el precio pierde la EMA9 del propio TF (cierre por debajo en
     long / por encima en short), o si toca breakeven, lo que ocurra antes.
     R = |entry - SL|; precio 1R = 2*entry - SL. Si SL se toca ANTES que 1R, la
     posición entera para en SL (= pérdida del baseline). Timeout a TIMEOUT_BARS.

Costes: (0.02+0.025)*2 = 0.09% i/v en AMBOS estilos (las comisiones son
proporcionales al tamaño: entrada 100% + dos salidas del 50% = mismo 0.09% que
una salida del 100%). Así la comparación es limpia en costes. Funding NO modelado.

CRITERIO PRE-REGISTRADO (sellado antes del primer dato):
  A >=100 EPISODIOS resueltos (mismo agrupado que f_alerts_paper: alertas
  consecutivas del mismo setup = 1 episodio), hay MEJORA de la gestión si la
  media de la diferencia PAREADA por episodio (gestionado - fijo) es > 0 con
  IC95 excluyendo cero. Si no -> la gestión no aporta y se archiva.
  Prohibido tocar definiciones/umbrales una vez haya el primer dato.

Uso:
  python f_mgmt_paper.py            # resuelve las pendientes ya cerradas
  python f_mgmt_paper.py --status   # estado y criterio
Env: TFZ_FALERTS_DB (fuente, solo-lectura) y TFZ_FMGMT_DB (destino).
"""
import os
import sys
import sqlite3
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv
from f_alerts_paper import START_TS, TIMEOUT_BARS, _episodios

SRC_DB = os.environ.get("TFZ_FALERTS_DB",
                        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "f_alerts_paper.db"))
DB = os.environ.get("TFZ_FMGMT_DB",
                    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "f_mgmt_paper.db"))
COST = (0.02 + 0.025) * 2      # % i/v, modelo MEXC (estándar de la casa)
EMA_LEN = 9                    # EMA de salida (Ross Cameron usa la 9)
TARGET_EPISODES = 100


def _conn(db=None):
    c = sqlite3.connect(db or DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS mgmt (
        symbol TEXT, timeframe TEXT, entry_ts TEXT, direction TEXT, formation TEXT,
        entry REAL, sl REAL, pnl_fixed REAL, pnl_managed REAL,
        exit_reason_mgmt TEXT, status TEXT DEFAULT 'open',
        PRIMARY KEY (symbol, timeframe, entry_ts, direction, formation))""")
    return c


def _ema(vals, n):
    return pd.Series(vals, dtype=float).ewm(span=n, adjust=False).mean().values


def _resolve_fixed(row, df, i0):
    """Primer toque de SL o TP; ambos en la misma vela -> SL. None si no cierra."""
    d = 1 if row["direction"] == "long" else -1
    entry, sl, tp = row["entry"], row["sl"], row["tp"]
    last_closed = len(df) - 2
    for i in range(i0 + 1, min(i0 + TIMEOUT_BARS, last_closed) + 1):
        hi, lo = float(df["high"].iloc[i]), float(df["low"].iloc[i])
        hit_sl = (lo <= sl) if d == 1 else (hi >= sl)
        hit_tp = (hi >= tp) if d == 1 else (lo <= tp)
        if hit_sl:
            return d * (sl - entry) / entry * 100 - COST
        if hit_tp:
            return d * (tp - entry) / entry * 100 - COST
    it = i0 + TIMEOUT_BARS
    if it <= last_closed:
        return d * (float(df["close"].iloc[it]) - entry) / entry * 100 - COST
    return None


def _resolve_managed(row, df, i0, ema):
    """Parcial en 1R + breakeven + trailing EMA9. Devuelve (pnl_net, motivo) o None."""
    d = 1 if row["direction"] == "long" else -1
    entry, sl = row["entry"], row["sl"]
    r_price = 2 * entry - sl            # precio a 1R (vale para long y short)
    r_pct = abs(entry - sl) / entry * 100
    last_closed = len(df) - 2
    end = min(i0 + TIMEOUT_BARS, last_closed)
    # Fase 1: buscar el primer toque de SL o 1R (SL pesimista si ambos a la vez)
    k = None
    for i in range(i0 + 1, end + 1):
        hi, lo = float(df["high"].iloc[i]), float(df["low"].iloc[i])
        hit_sl = (lo <= sl) if d == 1 else (hi >= sl)
        hit_1r = (hi >= r_price) if d == 1 else (lo <= r_price)
        if hit_sl:
            return d * (sl - entry) / entry * 100 - COST, "sl"      # posición entera para
        if hit_1r:
            k = i
            break
    if k is None:
        it = i0 + TIMEOUT_BARS
        if it <= last_closed:
            pnl = d * (float(df["close"].iloc[it]) - entry) / entry * 100
            return pnl - COST, "timeout_pre1R"
        return None
    # Fase 2: mitad ya vendida en 1R (+r_pct). La otra mitad: breakeven + EMA9.
    half1 = r_pct
    for j in range(k + 1, end + 1):
        hi, lo, cl = float(df["high"].iloc[j]), float(df["low"].iloc[j]), float(df["close"].iloc[j])
        be_hit = (lo <= entry) if d == 1 else (hi >= entry)
        if be_hit:
            half2 = 0.0                                             # breakeven
            return 0.5 * half1 + 0.5 * half2 - COST, "breakeven"
        lost_ema = (cl < ema[j]) if d == 1 else (cl > ema[j])
        if lost_ema:
            half2 = d * (cl - entry) / entry * 100
            return 0.5 * half1 + 0.5 * half2 - COST, "ema9"
    it = i0 + TIMEOUT_BARS
    if it <= last_closed:
        half2 = d * (float(df["close"].iloc[it]) - entry) / entry * 100
        return 0.5 * half1 + 0.5 * half2 - COST, "timeout"
    return None


def main():
    solo_status = "--status" in sys.argv
    c = _conn()
    if not solo_status:
        # universo = alertas ya pre-registradas en f_alerts_paper (solo-lectura)
        try:
            src = sqlite3.connect("file:" + SRC_DB + "?mode=ro", uri=True)
            src.row_factory = sqlite3.Row
            alerts = src.execute("SELECT * FROM alertas").fetchall()
            src.close()
        except Exception as e:
            print(f"f_mgmt_paper: no pude leer la fuente ({e})")
            alerts = []
        # sembrar las que falten (open); resolver luego
        for a in alerts:
            c.execute("INSERT OR IGNORE INTO mgmt(symbol,timeframe,entry_ts,direction,"
                      "formation,entry,sl) VALUES (?,?,?,?,?,?,?)",
                      (a["symbol"], a["timeframe"], a["entry_ts"], a["direction"],
                       a["formation"], a["entry"], a["sl"]))
        c.commit()
        # necesito sl/tp reales para resolver -> los traigo de la fuente por clave
        src_by_key = {(a["symbol"], a["timeframe"], a["entry_ts"], a["direction"],
                       a["formation"]): a for a in alerts}
        pend = c.execute("SELECT * FROM mgmt WHERE status='open'").fetchall()
        porsym = {}
        for r in pend:
            porsym.setdefault((r["symbol"], r["timeframe"]), []).append(r)
        resueltas = 0
        for (sym, tf), rows in porsym.items():
            try:
                tfc = config_for_timeframe(TFZConfig(), tf)
                df = fetch_ohlcv(sym, tf, limit=TIMEOUT_BARS + 80, config=tfc)
            except Exception:
                continue
            tss = df["timestamp"].astype(str).tolist()
            ema = _ema(df["close"].values, EMA_LEN)
            for r in rows:
                a = src_by_key.get((r["symbol"], r["timeframe"], r["entry_ts"],
                                    r["direction"], r["formation"]))
                if a is None or r["entry_ts"] not in tss:
                    continue
                i0 = tss.index(r["entry_ts"])
                row = {"direction": r["direction"], "entry": a["entry"],
                       "sl": a["sl"], "tp": a["tp"]}
                fx = _resolve_fixed(row, df, i0)
                mg = _resolve_managed(row, df, i0, ema)
                if fx is None or mg is None:
                    continue
                pnl_mg, motivo = mg
                c.execute("UPDATE mgmt SET pnl_fixed=?, pnl_managed=?, "
                          "exit_reason_mgmt=?, status='closed' WHERE symbol=? AND "
                          "timeframe=? AND entry_ts=? AND direction=? AND formation=?",
                          (fx, pnl_mg, motivo, r["symbol"], r["timeframe"],
                           r["entry_ts"], r["direction"], r["formation"]))
                resueltas += 1
                print(f"  [cierre] {r['symbol']:18s} {r['direction']:5s} | fijo {fx:+.2f}% "
                      f"| gestionado {pnl_mg:+.2f}% ({motivo})")
        c.commit()
        print(f"\nf_mgmt_paper: {resueltas} resueltas este ciclo")
    _resumen(c)
    c.close()


def _resumen(c):
    rows = c.execute("SELECT * FROM mgmt ORDER BY entry_ts").fetchall()
    cerradas = [r for r in rows if r["status"] == "closed"]
    abiertas = [r for r in rows if r["status"] == "open"]
    print(f"F MGMT PAPER — fijo vs gestionado (parcial 1R+BE+EMA9), BD {DB}")
    print(f"  alertas registradas: {len(rows)} | abiertas {len(abiertas)} | cerradas {len(cerradas)}")
    if not cerradas:
        print(f"  aun sin episodios cerrados. criterio: media de (gestionado - fijo)")
        print(f"  por episodio > 0 con IC95 excluyendo 0, a {TARGET_EPISODES} episodios.")
        return
    eps = _episodios(cerradas)          # 1 dato por episodio (la primera alerta)
    fx = np.array([r["pnl_fixed"] for r in eps])
    mg = np.array([r["pnl_managed"] for r in eps])
    dif = mg - fx
    def ic(a):
        se = a.std(ddof=1) / np.sqrt(len(a)) if len(a) > 1 else 0.0
        return a.mean(), a.mean() - 1.96 * se, a.mean() + 1.96 * se
    mf, _, _ = ic(fx); mm, _, _ = ic(mg); md, lo, hi = ic(dif)
    print(f"  PRIMARIO (por episodio, n={len(eps)}):")
    print(f"    FIJO       media {mf:+.3f}%/episodio")
    print(f"    GESTIONADO media {mm:+.3f}%/episodio")
    print(f"    DIFERENCIA (gest - fijo) {md:+.3f}% | IC95 [{lo:+.3f}, {hi:+.3f}]")
    print(f"  criterio: diferencia > 0 con IC95 excluyendo 0 a {TARGET_EPISODES} episodios")
    from collections import Counter
    mot = Counter(r["exit_reason_mgmt"] for r in cerradas)
    print(f"  SECUNDARIO (motivos de salida del gestionado): {dict(mot)}")


if __name__ == "__main__":
    main()
