"""
Análisis post-trade (autopsia) determinista de cada trade cerrado.

NO inventa narrativas de "por qué" — registra FACTORES MEDIBLES que rodean el
cierre, calculados con las funciones canónicas del bot y datos de velas:
  - tendencia en la entrada (a favor / en contra) via compute_trend_strength
  - excursión máxima a favor (runup) y en contra (drawdown) en múltiplos de R
  - velas mantenido (salida rápida = chop)
  - movimiento de BTC durante el trade (a favor / en contra)
  - score de entrada
  - motivo de salida (ya almacenado)

Con muchos trades, el patrón de los perdedores/ganadores emerge solo a partir de
estos datos (no de opiniones). Se guarda en la tabla `trade_review`.
"""

import sqlite3
import pandas as pd

from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from swings import compute_trend_strength, compute_atr

_DIAS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]


def _idx_at(df, ts):
    """Índice de la última vela con timestamp <= ts (UTC)."""
    s = df["timestamp"].astype(str)
    m = s.index[s <= str(ts)]
    return int(m[-1]) if len(m) else None


def analyze_trade(trade: dict, cfg: TFZConfig = None) -> dict:
    """Calcula los factores deterministas de un trade YA cerrado."""
    cfg = cfg or TFZConfig()
    tfc = config_for_timeframe(cfg, trade["timeframe"])
    d = trade["direction"]
    e = float(trade["entry_price"])
    sl = float(trade["stop_loss"])
    pnl = float(trade["pnl_pct"] or 0)
    risk = abs(e - sl)
    df = fetch_ohlcv_cached(trade["symbol"], trade["timeframe"], limit=1000, config=tfc)

    outcome = "win" if pnl > 0.05 else ("loss" if pnl < -0.05 else "be")
    tags = []

    ei = _idx_at(df, trade["entry_ts"])
    xi = _idx_at(df, trade["exit_ts"])

    # Tendencia en la entrada (función canónica)
    trend = float(compute_trend_strength(df, trade["timeframe"], ei)) if ei is not None else 0.0
    counter = (d == "long" and trend < 0) or (d == "short" and trend > 0)
    tags.append(f"{'contra' if counter else 'a-favor'}-tendencia({trend:+.1f}%)")

    # Excursión máxima a favor / en contra, en múltiplos de R
    runup_r = dd_r = 0.0
    held = 0
    if ei is not None and xi is not None and xi > ei and risk > 0:
        seg = df.iloc[ei + 1:xi + 1]
        held = xi - ei
        if d == "long":
            runup_r = (seg["high"].max() - e) / risk
            dd_r = (e - seg["low"].min()) / risk
        else:
            runup_r = (e - seg["low"].min()) / risk
            dd_r = (seg["high"].max() - e) / risk
    if runup_r < 0.3:
        tags.append(f"nunca-en-beneficio(max+{runup_r:.1f}R)")
    elif outcome == "loss" and runup_r >= 1.0:
        tags.append(f"corrio+{runup_r:.1f}R-y-se-giro")
    elif outcome == "win":
        tags.append(f"corrio+{runup_r:.1f}R")
    if held and held <= 2:
        tags.append(f"salida-rapida({held}v)")

    # BTC durante el trade
    btc_move = None
    btc_adv = False
    try:
        b = fetch_ohlcv_cached("BTC/USDT:USDT", trade["timeframe"], limit=1000, config=tfc)
        bei = _idx_at(b, trade["entry_ts"])
        bxi = _idx_at(b, trade["exit_ts"])
        if bei is not None and bxi is not None and bxi >= bei:
            c0 = float(b["close"].iloc[bei])
            btc_move = (float(b["close"].iloc[bxi]) - c0) / c0 * 100
            btc_adv = (d == "long" and btc_move < -0.5) or (d == "short" and btc_move > 0.5)
            if btc_adv:
                tags.append(f"BTC-en-contra({btc_move:+.1f}%)")
            elif abs(btc_move) > 0.5:
                tags.append(f"BTC-a-favor({btc_move:+.1f}%)")
    except Exception:
        pass

    sc = float(trade["total_score"] or 0)
    if sc < 65:
        tags.append(f"score-bajo({sc:.0f})")

    # Contexto temporal (opened_at es hora local)
    hour = None
    weekday = None
    try:
        odt = pd.to_datetime(trade["opened_at"])
        hour = int(odt.hour)
        weekday = _DIAS[int(odt.dayofweek)]
    except Exception:
        pass

    # Volatilidad (ATR % del precio) y volumen relativo en la entrada
    atr_pct = None
    vol_ratio = None
    if ei is not None:
        try:
            atr = compute_atr(df, tfc.atr_period)
            if ei < len(atr) and not pd.isna(atr[ei]):
                atr_pct = round(float(atr[ei]) / e * 100, 3)
        except Exception:
            pass
        try:
            base = df["volume"].iloc[max(0, ei - 20):ei].mean()
            if base and base > 0:
                vol_ratio = round(float(df["volume"].iloc[ei]) / float(base), 2)
        except Exception:
            pass

    summary = (f"{outcome.upper()} {trade['exit_reason']} | "
               + " | ".join(tags) + f" | pnl {pnl:+.2f}%")

    return {
        "outcome": outcome,
        "trend_at_entry": round(trend, 2),
        "counter_trend": int(counter),
        "risk_pct": round(risk / e * 100, 3) if e else None,
        "max_runup_r": round(runup_r, 2),
        "max_dd_r": round(dd_r, 2),
        "candles_held": int(held),
        "btc_move_pct": round(btc_move, 2) if btc_move is not None else None,
        "btc_adverse": int(btc_adv),
        "hour": hour,
        "weekday": weekday,
        "atr_pct": atr_pct,
        "vol_ratio": vol_ratio,
        "tags": ",".join(tags),
        "summary": summary,
    }


def save_review(conn: sqlite3.Connection, trade_id: str, r: dict):
    conn.execute("""CREATE TABLE IF NOT EXISTS trade_review (
        trade_id TEXT PRIMARY KEY, outcome TEXT, trend_at_entry REAL, counter_trend INT,
        risk_pct REAL, max_runup_r REAL, max_dd_r REAL, candles_held INT,
        btc_move_pct REAL, btc_adverse INT, hour INT, weekday TEXT, atr_pct REAL,
        vol_ratio REAL, tags TEXT, summary TEXT, reviewed_at TEXT)""")
    conn.execute("""INSERT OR REPLACE INTO trade_review
        (trade_id,outcome,trend_at_entry,counter_trend,risk_pct,max_runup_r,max_dd_r,
         candles_held,btc_move_pct,btc_adverse,hour,weekday,atr_pct,vol_ratio,
         tags,summary,reviewed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))""",
        (trade_id, r["outcome"], r["trend_at_entry"], r["counter_trend"], r["risk_pct"],
         r["max_runup_r"], r["max_dd_r"], r["candles_held"], r["btc_move_pct"],
         r["btc_adverse"], r["hour"], r["weekday"], r["atr_pct"], r["vol_ratio"],
         r["tags"], r["summary"]))
    conn.commit()


def review_trade(conn: sqlite3.Connection, trade: dict, cfg: TFZConfig = None) -> dict:
    """Analiza UN trade cerrado y guarda su review. Fail-silent envuelto por el caller."""
    r = analyze_trade(trade, cfg)
    save_review(conn, trade["id"], r)
    return r


def review_all_closed(conn: sqlite3.Connection, cfg: TFZConfig = None,
                      today_only: bool = True, verbose: bool = True) -> int:
    """Aplica la autopsia a todos los trades cerrados (hoy por defecto)."""
    q = "SELECT * FROM paper_trades WHERE status='closed'"
    if today_only:
        q += " AND date(opened_at)=date('now','localtime')"
    q += " ORDER BY exit_ts"
    rows = [dict(r) for r in conn.execute(q).fetchall()]
    n = 0
    for t in rows:
        try:
            review_trade(conn, t, cfg)
            n += 1
        except Exception as ex:
            if verbose:
                print(f"  review fallo {t['symbol']}: {ex}")
    return n


def print_reviews(conn: sqlite3.Connection, today_only: bool = True, limit: int = 60):
    q = """SELECT pt.symbol, pt.timeframe, pt.direction, tr.summary
           FROM trade_review tr JOIN paper_trades pt ON pt.id=tr.trade_id"""
    if today_only:
        q += " WHERE date(pt.opened_at)=date('now','localtime')"
    q += " ORDER BY pt.exit_ts DESC LIMIT ?"
    rows = conn.execute(q, (limit,)).fetchall()
    print(f"\n=== AUTOPSIA DE TRADES ({'hoy' if today_only else 'todos'}) — {len(rows)} ===")
    for r in rows:
        print(f"  {r['symbol'].split('/')[0]:9s} {r['timeframe']:>3s} {r['direction']:5s}  {r['summary']}")
    # patrones agregados: ganadoras vs perdedoras
    where = "WHERE date(pt.opened_at)=date('now','localtime') " if today_only else ""
    agg = conn.execute("""SELECT outcome, COUNT(*) n, ROUND(AVG(counter_trend)*100) pct_contra,
        ROUND(AVG(btc_adverse)*100) pct_btc_contra, ROUND(AVG(max_runup_r),2) avg_runup,
        ROUND(AVG(atr_pct),2) avg_atr, ROUND(AVG(vol_ratio),2) avg_vol
        FROM trade_review tr JOIN paper_trades pt ON pt.id=tr.trade_id
        """ + where + "GROUP BY outcome").fetchall()
    print("\n  GANADORAS vs PERDEDORAS:")
    for a in agg:
        print(f"    {a['outcome']:5s}: {a['n']:3d} | contra-tend {a['pct_contra'] or 0:.0f}% | "
              f"BTC contra {a['pct_btc_contra'] or 0:.0f}% | corrio {a['avg_runup'] or 0:.1f}R | "
              f"volatilidad {a['avg_atr'] or 0:.2f}% | volumen x{a['avg_vol'] or 0:.1f}")
    # por dia de la semana y por hora
    for campo in ("weekday", "hour"):
        rows2 = conn.execute(f"""SELECT {campo} k, COUNT(*) n,
            SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) w, ROUND(AVG(pt.pnl_pct),2) pnl
            FROM trade_review tr JOIN paper_trades pt ON pt.id=tr.trade_id
            {where}GROUP BY {campo} ORDER BY pnl""").fetchall()
        if rows2:
            print(f"\n  POR {campo.upper()} (peor a mejor):")
            for x in rows2:
                print(f"    {str(x['k']):>4}: {x['n']:3d} trades | {x['w']} ganadas | pnl medio {x['pnl'] or 0:+.2f}%")


if __name__ == "__main__":
    from database import get_connection
    conn = get_connection()
    n = review_all_closed(conn, today_only=True)
    print(f"Analizados {n} trades cerrados de hoy.")
    print_reviews(conn, today_only=True)
