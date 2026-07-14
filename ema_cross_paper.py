"""
PAPER independiente del CRUCE EMA 9/21 DIARIO en BTC (2026-07-14). NO toca el bot
principal: BD propia (ema_cross_paper.db), proceso propio, nada compartido con la
medición congelada de micro_pullback ni con weekend/premium.

ORIGEN: chuleta "The Backtest Machine" (Miles Deutscher). Réplica verificada el
2026-07-14 con datos MEXC BTC/USDT 1d (jul-2023 -> jul-2026, comisión 0.1%/lado,
fill en la apertura siguiente): 23 trades, WR 34.8%, PF 3.11, +159.8% vs +104.1%
buy&hold, maxDD -27.3% vs -53.0%. Test de meseta OK (8/20 +166%, 10/22 +193%,
12/26 +152%; solo 5/15 flojea) -> no es un pico curvado.

REGLA (idéntica al backtest; no se modifica):
  - velas DIARIAS de BTC/USDT:USDT (cierre 00:00 UTC), señal SOLO en vela cerrada
  - EMA9 cruza sobre EMA21 al cierre -> largo 100%; cruza debajo -> plano
  - fill = APERTURA de la vela siguiente (como en el backtest) | solo largos, sin
    apalancamiento | costes modelo MEXC 0.09% ida+vuelta | FUNDING NO MODELADO
    (aviso: con holds de semanas en perps puede restar ~0.02-0.03%/día si es
    positivo; se anota como salvedad, no se estima)

FORWARD-ONLY: solo se registran cruces cuyo CIERRE de señal es >= START_TS
(pre-registro 2026-07-14). El cruce alcista del 2026-07-10 (posición ya abierta
al pre-registrar) NO cuenta: se espera al siguiente ciclo completo.

CRITERIO (anotado al sellar): con ~6 trades/año en 1 solo símbolo no cabe un
criterio estadístico serio a corto plazo (20 trades ~ 3 años). Lo que se mide y
compara desde el pre-registro: equity de la regla vs buy&hold y fidelidad de los
fills vs la réplica del backtest. Sin veredicto de edge hasta tener muestra.

Idempotente (INSERT OR IGNORE, reconstruye desde velas cerradas): da igual correrlo
tarde o varias veces; los días sin cruce no hace NADA (esa disciplina ES la regla).

Uso (pensado para tarea diaria tras el cierre 00:00 UTC):
  python ema_cross_paper.py            # registra cruces pendientes ya cerrados
  python ema_cross_paper.py --status   # estado, trades y comparación vs B&H
Env: TFZ_EMA_DB para separar cuentas (PC vs GitHub). Aviso Telegram de cruce nuevo
solo donde TFZ_TELEGRAM=1 (patrón premium_paper).
"""
import os
# OJO: aquí NO se fuerza INSECURE_SSL (esto corre también en GitHub, donde el SSL
# funciona bien). En el PC lo pone run_ema_paper.cmd, como run_weekend_paper.cmd.

import sys
import sqlite3
import pandas as pd
from config import TFZConfig
from data_fetcher import fetch_ohlcv

DB = os.environ.get("TFZ_EMA_DB",
                    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "ema_cross_paper.db"))
START_TS = pd.Timestamp("2026-07-14")   # pre-registro: solo señales con cierre >= aquí
SYM = "BTC/USDT:USDT"
FAST, SLOW = 9, 21
COST = (0.02 + 0.025) * 2               # % ida+vuelta, modelo MEXC (como weekend)
WARMUP = 300                            # velas 1d para que las EMAs converjan


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS ema_events (
        signal_date TEXT PRIMARY KEY,   -- fecha del CIERRE diario que generó el cruce
        direction   TEXT,               -- 'up' (entrar largo) / 'dn' (salir a plano)
        fill_date   TEXT,               -- día de la vela cuya APERTURA es el fill
        fill_px     REAL)""")
    c.commit()
    return c


def _avisar(texto):
    try:  # aviso informativo (fail-silent; solo donde TFZ_TELEGRAM=1)
        from notify import send_telegram
        send_telegram(texto)
    except Exception:
        pass


def record_pending(conn, verbose=True):
    """Registra cada cruce >= START ya CERRADO cuya vela siguiente ya exista
    (su apertura es el fill). Reconstruye desde velas, así que es inmune a
    correr tarde o a saltarse días."""
    df = fetch_ohlcv(SYM, "1d", limit=WARMUP, config=TFZConfig())
    df = df.sort_values("timestamp").reset_index(drop=True)
    hoy_utc = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    f = df["close"].ewm(span=FAST, adjust=False).mean()
    s = df["close"].ewm(span=SLOW, adjust=False).mean()
    added = 0
    for i in range(1, len(df) - 1):
        d = df["timestamp"].iloc[i]
        if d < START_TS or d >= hoy_utc:      # señal solo en vela CERRADA
            continue
        up = f.iloc[i] > s.iloc[i] and f.iloc[i - 1] <= s.iloc[i - 1]
        dn = f.iloc[i] < s.iloc[i] and f.iloc[i - 1] >= s.iloc[i - 1]
        if not (up or dn):
            continue
        nxt = df.iloc[i + 1]                  # su OPEN queda fijado al abrir el día
        cur = conn.execute(
            "INSERT OR IGNORE INTO ema_events VALUES (?,?,?,?)",
            (str(d.date()), "up" if up else "dn",
             str(nxt["timestamp"].date()), float(nxt["open"])))
        conn.commit()
        if cur.rowcount:
            added += 1
            lado = "CRUCE ALCISTA -> largo" if up else "CRUCE BAJISTA -> plano"
            if verbose:
                print(f"  [reg] {d.date()} {lado}, fill {nxt['open']:.0f} "
                      f"({nxt['timestamp'].date()})")
            _avisar(f"📈 <b>EMA 9/21 BTC diario</b>: {lado} al cierre del "
                    f"{d.date()}. Fill paper {nxt['open']:.0f}. "
                    f"Medición forward, no es orden de operar.")
    # estado actual informativo
    ult = df["timestamp"].iloc[-2].date()  # última vela cerrada
    print(f"  EMAs al cierre del {ult}: EMA9 {f.iloc[-2]:.0f} "
          f"{'>' if f.iloc[-2] > s.iloc[-2] else '<'} EMA21 {s.iloc[-2]:.0f} "
          f"({'zona larga' if f.iloc[-2] > s.iloc[-2] else 'zona plana'})")
    if added == 0:
        print("  sin cruces nuevos: hoy no se hace nada (la disciplina ES la regla)")
    return df, added


def status(conn, df=None):
    rows = conn.execute(
        "SELECT * FROM ema_events ORDER BY signal_date").fetchall()
    print(f"\nEMA CROSS PAPER — BD {DB}")
    print(f"  eventos registrados: {len(rows)} (solo señales >= {START_TS.date()})")
    if not rows:
        print("  aún sin cruces medibles: la posición pre-registro no cuenta;")
        print("  se espera el primer cruce POSTERIOR al 2026-07-14.")
        return
    # emparejar up -> dn en trades
    trades, entry = [], None
    for r in rows:
        if r["direction"] == "up" and entry is None:
            entry = r
        elif r["direction"] == "dn" and entry is not None:
            pnl = (r["fill_px"] / entry["fill_px"] - 1) * 100 - COST
            trades.append((entry["fill_date"], r["fill_date"],
                           entry["fill_px"], r["fill_px"], pnl))
            entry = None
    for t in trades:
        print(f"  {t[0]} -> {t[1]}: {t[2]:.0f} -> {t[3]:.0f}  {t[4]:+.2f}%")
    if entry is not None:
        print(f"  ABIERTA desde {entry['fill_date']} a {entry['fill_px']:.0f}")
    if trades:
        eq = 100.0
        for t in trades:
            eq *= 1 + t[4] / 100
        wins = [t for t in trades if t[4] > 0]
        print(f"  cerradas: {len(trades)} | ganadoras: {len(wins)} | "
              f"equity regla: {eq - 100:+.2f}%")
        if df is not None:
            px0 = next(r["fill_px"] for r in rows if r["direction"] == "up")
            bh = (df["close"].iloc[-2] / px0 - 1) * 100 - COST
            print(f"  buy&hold desde el primer fill: {bh:+.2f}% (mismo rango)")
    print("  salvedad fija: funding de perps NO incluido en el PnL paper.")


def main():
    conn = _conn()
    if "--status" in sys.argv:
        df = fetch_ohlcv(SYM, "1d", limit=WARMUP, config=TFZConfig())
        df = df.sort_values("timestamp").reset_index(drop=True)
        status(conn, df)
        return
    df, _ = record_pending(conn)
    status(conn, df)


if __name__ == "__main__":
    main()
