"""
PAPER independiente del ICHIMOKU DIARIO en BTC (2026-07-15). NO toca el bot
principal ni las demás mediciones: BD propia (ichimoku_paper.db), proceso propio.
Gemelo de ema_cross_paper.py — juntos miden la agresiva (EMA) vs el paracaídas.

ORIGEN: tanda de 6 estrategias clásicas del 2026-07-15 (ver CHANGELOG). Batería
pasada con datos Binance BTC/USDT 1d 2020->2026: meseta OK (7 configs vecinas,
+900..+1400%), total +1218% vs +834% aguantar, maxDD -35.9% vs -76.6%. Su edge
histórico es DEFENSIVO: 2022 -22% vs -64% B&H; en años alcistas gana MENOS que
aguantar (2024 +48% vs +121%). OJO: último año (jul-25->jul-26) -10.2%, 0/5
ganadoras — como toda seguidora de tendencia en lateral. Por eso se mide forward.

REGLA (congelada; parámetros estándar, no optimizados):
  - velas DIARIAS de BTC/USDT:USDT, señal SOLO en vela cerrada
  - nube = máx(senkou A, senkou B) con Tenkan 9 / Kijun 26 / Senkou B 52,
    desplazamiento 26 (todo causal: la nube de hoy se calculó hace 26 días)
  - cierre por ENCIMA de la nube -> largo 100%; por debajo o dentro -> plano
  - fill = APERTURA de la vela siguiente | solo largos | costes MEXC 0.09% i/v
  - FUNDING NO MODELADO (misma salvedad que ema_cross_paper)

FORWARD-ONLY: solo cuentan cambios de estado cuyo cierre de señal es >= START_TS
(pre-registro 2026-07-15). El estado en que esté BTC al sellar NO cuenta: se
espera el primer ciclo completo. Sin criterio estadístico sellado (~7 trades/año);
se mide equity vs buy&hold y, sobre todo, comparación con ema_cross_paper.

Uso:  python ichimoku_paper.py            # registra cambios pendientes
      python ichimoku_paper.py --status   # estado y trades
Env: TFZ_ICHI_DB para separar cuentas (PC vs GitHub). Aviso Telegram solo donde
TFZ_TELEGRAM=1.
"""
import os
# OJO: aquí NO se fuerza INSECURE_SSL (corre también en GitHub). En el PC lo pone
# run_ichimoku_paper.cmd.

import sys
import sqlite3
import pandas as pd
from config import TFZConfig
from data_fetcher import fetch_ohlcv

DB = os.environ.get("TFZ_ICHI_DB",
                    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "ichimoku_paper.db"))
START_TS = pd.Timestamp("2026-07-15")   # pre-registro: solo señales con cierre >= aquí
SYM = "BTC/USDT:USDT"
TENKAN, KIJUN, SENKOU_B, DESP = 9, 26, 52, 26
COST = (0.02 + 0.025) * 2               # % ida+vuelta, modelo MEXC
WARMUP = 300


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS ichi_events (
        signal_date TEXT PRIMARY KEY,   -- fecha del CIERRE diario del cambio de estado
        direction   TEXT,               -- 'up' (sobre la nube -> largo) / 'dn' (plano)
        fill_date   TEXT, fill_px REAL)""")
    c.commit()
    return c


def _avisar(texto):
    try:
        from notify import send_telegram
        send_telegram(texto)
    except Exception:
        pass


def _posicion(df):
    """Serie 0/1: 1 = cierre por encima de la nube (todo causal)."""
    tenkan = (df["high"].rolling(TENKAN).max() + df["low"].rolling(TENKAN).min()) / 2
    kijun = (df["high"].rolling(KIJUN).max() + df["low"].rolling(KIJUN).min()) / 2
    sen_a = ((tenkan + kijun) / 2).shift(DESP)
    sen_b = ((df["high"].rolling(SENKOU_B).max()
              + df["low"].rolling(SENKOU_B).min()) / 2).shift(DESP)
    nube = pd.concat([sen_a, sen_b], axis=1).max(axis=1)
    return (df["close"] > nube).astype(int), nube


def record_pending(conn, verbose=True):
    """Registra cada cambio de estado >= START ya CERRADO cuya vela siguiente
    exista (su apertura es el fill). Idempotente, inmune a correr tarde."""
    df = fetch_ohlcv(SYM, "1d", limit=WARMUP, config=TFZConfig())
    df = df.sort_values("timestamp").reset_index(drop=True)
    hoy_utc = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    pos, nube = _posicion(df)
    added = 0
    for i in range(1, len(df) - 1):
        d = df["timestamp"].iloc[i]
        if d < START_TS or d >= hoy_utc:
            continue
        if pos.iloc[i] == pos.iloc[i - 1]:
            continue
        up = pos.iloc[i] == 1
        nxt = df.iloc[i + 1]
        cur = conn.execute(
            "INSERT OR IGNORE INTO ichi_events VALUES (?,?,?,?)",
            (str(d.date()), "up" if up else "dn",
             str(nxt["timestamp"].date()), float(nxt["open"])))
        conn.commit()
        if cur.rowcount:
            added += 1
            lado = "SOBRE LA NUBE -> largo" if up else "BAJO LA NUBE -> plano"
            if verbose:
                print(f"  [reg] {d.date()} {lado}, fill {nxt['open']:.0f} "
                      f"({nxt['timestamp'].date()})")
            _avisar(f"☁️ <b>Ichimoku BTC diario</b>: {lado} al cierre del "
                    f"{d.date()}. Fill paper {nxt['open']:.0f}. "
                    f"Medición forward, no es orden de operar.")
    ult = df["timestamp"].iloc[-2].date()
    estado = "sobre la nube (zona larga)" if pos.iloc[-2] == 1 else "bajo/dentro de la nube (zona plana)"
    print(f"  al cierre del {ult}: cierre {df['close'].iloc[-2]:.0f}, "
          f"techo de la nube {nube.iloc[-2]:.0f} -> {estado}")
    if added == 0:
        print("  sin cambios nuevos: hoy no se hace nada")
    return df, added


def status(conn, df=None):
    rows = conn.execute(
        "SELECT * FROM ichi_events ORDER BY signal_date").fetchall()
    print(f"\nICHIMOKU PAPER — BD {DB}")
    print(f"  eventos registrados: {len(rows)} (solo señales >= {START_TS.date()})")
    if not rows:
        print("  aún sin cambios medibles: el estado al pre-registrar no cuenta;")
        print("  se espera el primer cambio POSTERIOR al 2026-07-15.")
        return
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
