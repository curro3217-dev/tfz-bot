"""
PAPER independiente de las ALERTAS F del ASISTENTE (pre-registro 2026-07-22).

Contexto: desde que se retiro micro_pullback (2026-07-16) el bot es asistente puro y
manda alertas F a Telegram, pero NADIE registraba si aciertan. El 35.2% del panel es
del micro_pullback muerto, no de esto. Esta medicion tapa ese agujero.

NO toca nada existente: BD propia (f_alerts_paper.db), proceso propio. La grabacion
vive en record_alert(), que paper.py llama fail-silent al enviar la alerta; si esto
falla, la alerta sale igual. No filtra ni altera ninguna señal.

REGLA MEDIDA (exactamente lo que te llega al Telegram, sin reinterpretar):
  - entrada = entry_price de la alerta; SL y TP = los de la alerta
  - se recorren las velas del MISMO timeframe ESTRICTAMENTE posteriores a la vela
    de la señal; gana el primer toque de SL o TP
  - si una MISMA vela toca los dos, se cuenta SL (criterio pesimista: dentro de la
    vela no se sabe el orden y no se va a suponer a favor)
  - timeout a TIMEOUT_BARS velas sin tocar ninguno -> salida a cierre
  - costes: modelo MEXC 0.09% ida+vuelta (el estandar de la casa). Funding NO modelado.

FORWARD-ONLY: solo alertas con vela >= START_TS. START_TS se sella DESPUES de haber
mirado las 3 alertas de ENA del 22-jul (SL tocado) -> esas quedan FUERA a proposito:
ya se conoce su resultado y meterlas contaminaria la muestra.

CRITERIO PRE-REGISTRADO (sellado 2026-07-22, antes de la primera alerta medida):
  PRIMARIO: a >=100 EPISODIOS resueltos, hay edge si la media neta por episodio es
  > +0.20% con IC95 excluyendo cero. Si no, se archiva.
  Un EPISODIO = alertas consecutivas del mismo simbolo/TF/direccion/formacion
  separadas por menos de EPISODE_GAP velas; cuenta solo la PRIMERA. Motivo: el
  dedup del bot es por VELA, asi que un mismo setup dispara varias alertas seguidas
  (el 22-jul, ENA disparo 3 en 27 min con el mismo SL/TP). Contarlas por separado
  inflaria n con datos casi identicos, igual que weekend_paper promedia por sabado.
  SECUNDARIO (descriptivo, NO decide): la misma media sobre TODAS las alertas, y el
  desglose por formacion. Se miran para entender, no para buscar un ganador.
  PROHIBIDO tocar definiciones/umbrales una vez haya el primer dato.

Uso:
  python f_alerts_paper.py            # resuelve las pendientes ya cerradas
  python f_alerts_paper.py --status   # estado y criterio
Env: TFZ_FALERTS_DB para separar cuentas (PC vs GitHub).
"""
import os
# OJO: aqui NO se fuerza INSECURE_SSL (esto corre tambien en GitHub, donde el SSL va
# bien). En el PC lo ponen los run_*.cmd, como en weekend_paper.

import sys
import sqlite3
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv

DB = os.environ.get("TFZ_FALERTS_DB",
                    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "f_alerts_paper.db"))
# Pre-registro: solo alertas cuya VELA sea >= aqui (UTC). 2026-07-22 19:30 UTC =
# 21:30 Madrid. Deja fuera las 3 de ENA de esa mañana, cuyo desenlace ya se miro.
START_TS = pd.Timestamp("2026-07-22 19:30:00")
COST = (0.02 + 0.025) * 2      # % ida+vuelta, modelo MEXC (igual que weekend/ema)
TIMEOUT_BARS = 96              # velas del propio TF (en 15m = 24h)
EPISODE_GAP = 4                # velas: separacion minima para considerar otro episodio
TARGET_EPISODES = 100          # evaluacion UNICA al llegar aqui
UMBRAL = 0.20                  # % neto por episodio


# Columnas de CONTEXTO (2026-07-23): guardadas para MEDIR luego si filtrar por
# contexto ayuda (RSI/RVOL/lado EMA200/room a estructura). NO cambian la señal ni el
# criterio sellado; son informativas. Idea nacida de dos alertas short contra soporte
# en sobreventa y volumen bajo (ENA/LDO) que el usuario detectó a ojo.
_CTX_COLS = ["rsi", "rvol", "ema200_dist", "room_pct"]


def _conn(db=None):
    c = sqlite3.connect(db or DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS alertas (
        symbol TEXT, timeframe TEXT, entry_ts TEXT, direction TEXT, formation TEXT,
        entry REAL, sl REAL, tp REAL, score REAL, rr REAL,
        sent_at TEXT, exit_price REAL, exit_reason TEXT, exit_ts TEXT,
        pnl_net REAL, status TEXT DEFAULT 'open',
        PRIMARY KEY (symbol, timeframe, entry_ts, direction, formation))""")
    # Migracion: añade las columnas de contexto si la BD es de antes (0 filas o no).
    existing = {r[1] for r in c.execute("PRAGMA table_info(alertas)")}
    for col in _CTX_COLS:
        if col not in existing:
            c.execute(f"ALTER TABLE alertas ADD COLUMN {col} REAL")
    c.commit()
    return c


def record_alert(sig, entry_ts, context=None) -> bool:
    """Graba una alerta F recien enviada. La llama paper.py fail-silent. Idempotente
    (misma clave que el dedup del bot). `context` = dict de _context_features (opcional,
    informativo). Devuelve True si se grabo."""
    try:
        if pd.Timestamp(str(entry_ts)) < START_TS:
            return False
        ctx = context or {}
        c = _conn()
        cur = c.execute(
            "INSERT OR IGNORE INTO alertas(symbol,timeframe,entry_ts,direction,"
            "formation,entry,sl,tp,score,rr,sent_at,rsi,rvol,ema200_dist,room_pct) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'),?,?,?,?)",
            (sig.symbol, sig.timeframe, str(entry_ts), sig.direction,
             sig.formation_type, float(sig.entry_price), float(sig.stop_loss),
             float(sig.take_profit), float(sig.total_score), float(sig.rr_ratio),
             ctx.get("rsi"), ctx.get("rvol"), ctx.get("ema200_dist"), ctx.get("room_pct")))
        c.commit()
        n = cur.rowcount
        c.close()
        return bool(n)
    except Exception:
        return False


def _resolve_one(row, df):
    """Devuelve (exit_price, reason, exit_ts) o None si aun no se puede cerrar."""
    tss = df["timestamp"].astype(str).tolist()
    if row["entry_ts"] not in tss:
        return None
    i0 = tss.index(row["entry_ts"])
    d = 1 if row["direction"] == "long" else -1
    sl, tp = row["sl"], row["tp"]
    # solo velas CERRADAS: la ultima del df puede estar formandose
    last_closed = len(df) - 2
    for i in range(i0 + 1, min(i0 + TIMEOUT_BARS, last_closed) + 1):
        hi, lo = float(df["high"].iloc[i]), float(df["low"].iloc[i])
        if d == 1:
            hit_sl, hit_tp = lo <= sl, hi >= tp
        else:
            hit_sl, hit_tp = hi >= sl, lo <= tp
        if hit_sl:                      # pesimista: SL manda si ambos en la misma vela
            return sl, "sl_hit", tss[i]
        if hit_tp:
            return tp, "tp_hit", tss[i]
    # timeout solo si la vela de salida ya esta cerrada
    it = i0 + TIMEOUT_BARS
    if it <= last_closed:
        return float(df["close"].iloc[it]), "timeout", tss[it]
    return None


def _episodios(rows):
    """Agrupa alertas consecutivas del mismo setup; devuelve la PRIMERA de cada
    episodio. rows debe venir ordenado por entry_ts."""
    vistos, out = {}, []
    for r in rows:
        k = (r["symbol"], r["timeframe"], r["direction"], r["formation"])
        t = pd.Timestamp(r["entry_ts"])
        tf_min = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}.get(r["timeframe"], 15)
        prev = vistos.get(k)
        if prev is None or (t - prev).total_seconds() / 60 > EPISODE_GAP * tf_min:
            out.append(r)
        vistos[k] = t
    return out


def _resumen(c):
    rows = c.execute("SELECT * FROM alertas ORDER BY entry_ts").fetchall()
    abiertas = [r for r in rows if r["status"] == "open"]
    cerradas = [r for r in rows if r["status"] == "closed"]
    print(f"F ALERTS PAPER — BD {DB}")
    print(f"  alertas registradas: {len(rows)} (solo velas >= {START_TS} UTC)")
    if not rows:
        print("  aun sin alertas medibles: se registran solo las POSTERIORES al")
        print(f"  pre-registro ({START_TS} UTC = 21:30 Madrid del 22-jul).")
        print(f"  criterio: > +{UMBRAL:.2f}% neto/episodio, IC95 excluyendo 0, a {TARGET_EPISODES} episodios")
        return
    eps = _episodios([r for r in rows if r["status"] == "closed"])
    def linea(nombre, arr, objetivo=None):
        if not arr:
            print(f"  {nombre:28s} cerradas 0")
            return
        a = np.array([r["pnl_net"] for r in arr])
        se = a.std(ddof=1) / np.sqrt(len(a)) if len(a) > 1 else 0.0
        w = (a > 0).sum()
        extra = f" | objetivo: {objetivo}" if objetivo else ""
        print(f"  {nombre:28s} n {len(a):4d} | aciertos {w/len(a)*100:4.1f}% | "
              f"media neta {a.mean():+.3f}% | IC95 [{a.mean()-1.96*se:+.3f}, "
              f"{a.mean()+1.96*se:+.3f}]{extra}")
    print(f"  abiertas: {len(abiertas)} | cerradas: {len(cerradas)}")
    print(f"  PRIMARIO (por episodio):")
    linea("todas las formaciones", eps, f"{TARGET_EPISODES} episodios")
    print(f"  criterio sellado: > +{UMBRAL:.2f}% con IC95 excluyendo 0 a {TARGET_EPISODES} episodios")
    print(f"  SECUNDARIO (descriptivo, NO decide):")
    linea("todas las alertas", cerradas)
    for (f,) in c.execute("SELECT DISTINCT formation FROM alertas ORDER BY formation").fetchall():
        linea(f"  formacion {f}", [r for r in eps if r["formation"] == f])
    for reason in ("tp_hit", "sl_hit", "timeout"):
        n = sum(1 for r in cerradas if r["exit_reason"] == reason)
        if n:
            print(f"    salidas por {reason:8s}: {n}")


def main():
    solo_status = "--status" in sys.argv
    c = _conn()
    if not solo_status:
        pend = c.execute("SELECT * FROM alertas WHERE status='open'").fetchall()
        resueltas = 0
        porsym = {}
        for r in pend:
            porsym.setdefault((r["symbol"], r["timeframe"]), []).append(r)
        for (sym, tf), rows in porsym.items():
            try:
                tfc = config_for_timeframe(TFZConfig(), tf)
                df = fetch_ohlcv(sym, tf, limit=TIMEOUT_BARS + 200, config=tfc)
            except Exception:
                continue
            for r in rows:
                res = _resolve_one(r, df)
                if not res:
                    continue
                px, reason, ets = res
                d = 1 if r["direction"] == "long" else -1
                pnl = d * (px - r["entry"]) / r["entry"] * 100 - COST
                c.execute("UPDATE alertas SET exit_price=?, exit_reason=?, exit_ts=?, "
                          "pnl_net=?, status='closed' WHERE symbol=? AND timeframe=? "
                          "AND entry_ts=? AND direction=? AND formation=?",
                          (px, reason, ets, pnl, r["symbol"], r["timeframe"],
                           r["entry_ts"], r["direction"], r["formation"]))
                resueltas += 1
                print(f"  [cierre] {r['symbol']:18s} {r['formation']:4s} {reason:8s} {pnl:+.2f}%")
        c.commit()
        print(f"\nf_alerts_paper: {resueltas} resueltas este ciclo")
    _resumen(c)
    c.close()


if __name__ == "__main__":
    main()
