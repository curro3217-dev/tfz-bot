import os
import sqlite3
import json
from pathlib import Path
from typing import List, Optional
from signals import Signal
from backtester import TradeResult


# Ruta de la BD. Override por env TFZ_DB para correr una cuenta paper SEPARADA (p.ej.
# el bot de GitHub usa github_state/tfz_data.db y no pisa la del PC, asi se pueden
# comparar las dos en paralelo). Sin la env, usa la de siempre junto al codigo.
DB_PATH = Path(os.environ.get("TFZ_DB") or (Path(__file__).parent / "tfz_data.db"))


def get_connection(db_path: str = None) -> sqlite3.Connection:
    path = db_path or str(DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            direction TEXT,
            formation_type TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            risk_pct REAL,
            rr_ratio REAL,
            total_score REAL,
            score_breakdown TEXT,
            levels TEXT,
            consolidation TEXT,
            sweep TEXT,
            trigger_idx INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS trade_results (
            signal_id TEXT PRIMARY KEY REFERENCES signals(id),
            exit_price REAL,
            exit_reason TEXT,
            exit_idx INTEGER,
            pnl_pct REAL,
            duration_candles INTEGER,
            max_drawdown_pct REAL,
            max_runup_pct REAL,
            moved_to_breakeven INTEGER,
            breakeven_at_candle INTEGER
        );

        CREATE TABLE IF NOT EXISTS paper_trades (
            id TEXT PRIMARY KEY,
            symbol TEXT,
            timeframe TEXT,
            direction TEXT,
            formation_type TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            risk_pct REAL,
            rr_ratio REAL,
            total_score REAL,
            consol_high REAL,
            consol_low REAL,
            opened_at TEXT,
            entry_ts TEXT,
            status TEXT DEFAULT 'open',
            exit_price REAL,
            exit_reason TEXT,
            exit_ts TEXT,
            pnl_pct REAL
        );

        CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
        CREATE INDEX IF NOT EXISTS idx_signals_tf ON signals(timeframe);
        CREATE INDEX IF NOT EXISTS idx_signals_score ON signals(total_score);
        CREATE INDEX IF NOT EXISTS idx_results_reason ON trade_results(exit_reason);
        CREATE INDEX IF NOT EXISTS idx_paper_status ON paper_trades(status);
        CREATE INDEX IF NOT EXISTS idx_paper_symbol ON paper_trades(symbol);
    """)
    conn.commit()


def save_signal(conn: sqlite3.Connection, sig: Signal):
    conn.execute(
        """INSERT OR REPLACE INTO signals
           (id, timestamp, symbol, timeframe, direction, formation_type,
            entry_price, stop_loss, take_profit, risk_pct, rr_ratio,
            total_score, score_breakdown, levels, consolidation, sweep, trigger_idx)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            sig.id,
            str(sig.timestamp),
            sig.symbol,
            sig.timeframe,
            sig.direction,
            sig.formation_type,
            sig.entry_price,
            sig.stop_loss,
            sig.take_profit,
            sig.risk_pct,
            sig.rr_ratio,
            sig.total_score,
            json.dumps(sig.score_breakdown),
            json.dumps(sig.levels),
            json.dumps(sig.consolidation) if sig.consolidation else None,
            json.dumps(sig.sweep) if sig.sweep else None,
            sig.trigger_idx,
        ),
    )
    conn.commit()


def save_result(conn: sqlite3.Connection, result: TradeResult):
    conn.execute(
        """INSERT OR REPLACE INTO trade_results
           (signal_id, exit_price, exit_reason, exit_idx, pnl_pct,
            duration_candles, max_drawdown_pct, max_runup_pct,
            moved_to_breakeven, breakeven_at_candle)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            result.signal_id,
            result.exit_price,
            result.exit_reason,
            result.exit_idx,
            result.pnl_pct,
            result.duration_candles,
            result.max_drawdown_pct,
            result.max_runup_pct,
            int(result.moved_to_breakeven),
            result.breakeven_at_candle,
        ),
    )
    conn.commit()


def save_backtest_batch(
    conn: sqlite3.Connection,
    signals: List[Signal],
    results: List[TradeResult],
):
    for sig in signals:
        save_signal(conn, sig)
    for res in results:
        save_result(conn, res)


def open_paper_trade(conn: sqlite3.Connection, sig: "Signal", entry_ts: str):
    """Record a new open paper position from a fresh signal."""
    consol = sig.consolidation or {}
    conn.execute(
        """INSERT OR IGNORE INTO paper_trades
           (id, symbol, timeframe, direction, formation_type, entry_price,
            stop_loss, take_profit, risk_pct, rr_ratio, total_score,
            consol_high, consol_low, opened_at, entry_ts, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'), ?, 'open')""",
        (
            sig.id, sig.symbol, sig.timeframe, sig.direction, sig.formation_type,
            sig.entry_price, sig.stop_loss, sig.take_profit, sig.risk_pct,
            sig.rr_ratio, sig.total_score,
            consol.get("range_high"), consol.get("range_low"),
            str(entry_ts),
        ),
    )
    conn.commit()


def get_open_paper_trades(conn: sqlite3.Connection, symbol: str = None,
                          timeframe: str = None) -> List[dict]:
    where = ["status = 'open'"]
    params = []
    if symbol:
        where.append("symbol = ?")
        params.append(symbol)
    if timeframe:
        where.append("timeframe = ?")
        params.append(timeframe)
    rows = conn.execute(
        f"SELECT * FROM paper_trades WHERE {' AND '.join(where)} ORDER BY opened_at",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def close_paper_trade(conn: sqlite3.Connection, trade_id: str, exit_price: float,
                      exit_reason: str, exit_ts: str, pnl_pct: float):
    conn.execute(
        """UPDATE paper_trades
           SET status='closed', exit_price=?, exit_reason=?, exit_ts=?, pnl_pct=?
           WHERE id=?""",
        (exit_price, exit_reason, str(exit_ts), pnl_pct, trade_id),
    )
    conn.commit()


def paper_stats(conn: sqlite3.Connection) -> dict:
    """Aggregate performance of closed paper trades."""
    rows = conn.execute(
        "SELECT pnl_pct, exit_reason FROM paper_trades WHERE status='closed'"
    ).fetchall()
    pnls = [r["pnl_pct"] for r in rows if r["pnl_pct"] is not None]
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0.05)
    losses = sum(1 for p in pnls if p < -0.05)
    n_open = conn.execute(
        "SELECT COUNT(*) c FROM paper_trades WHERE status='open'"
    ).fetchone()["c"]
    return {
        "closed": n,
        "open": n_open,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / n * 100 if n else 0,
        "total_pnl": sum(pnls),
        "expectancy": sum(pnls) / n if n else 0,
        "best": max(pnls) if pnls else 0,
        "worst": min(pnls) if pnls else 0,
    }


def query_signals(
    conn: sqlite3.Connection,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    min_score: Optional[float] = None,
    formation_type: Optional[str] = None,
    limit: int = 100,
) -> List[dict]:
    where = []
    params = []

    if symbol:
        where.append("s.symbol = ?")
        params.append(symbol)
    if timeframe:
        where.append("s.timeframe = ?")
        params.append(timeframe)
    if min_score is not None:
        where.append("s.total_score >= ?")
        params.append(min_score)
    if formation_type:
        where.append("s.formation_type = ?")
        params.append(formation_type)

    where_clause = " AND ".join(where) if where else "1=1"

    rows = conn.execute(
        f"""SELECT s.*, r.exit_price, r.exit_reason, r.pnl_pct,
                   r.duration_candles, r.max_drawdown_pct, r.moved_to_breakeven
            FROM signals s
            LEFT JOIN trade_results r ON s.id = r.signal_id
            WHERE {where_clause}
            ORDER BY s.timestamp DESC
            LIMIT ?""",
        params + [limit],
    ).fetchall()

    return [dict(r) for r in rows]
