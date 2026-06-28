"""
Mass backtest across multiple symbols and timeframes.
Usage: python mass_backtest.py [--candles 1000] [--bear]
"""

import os
os.environ.setdefault("INSECURE_SSL", "1")

import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests.adapters as _radapt
_orig_send = _radapt.HTTPAdapter.send
def _nosslcheck_send(self, request, **kwargs):
    kwargs["verify"] = False
    return _orig_send(self, request, **kwargs)
_radapt.HTTPAdapter.send = _nosslcheck_send

import argparse
import json
import time
import traceback
import numpy as np
import pandas as pd
from datetime import datetime

from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv
from swings import detect_swings, get_swing_highs, get_swing_lows, compute_trend_strength
from levels import detect_horizontal_levels, detect_diagonal_levels
from consolidation import detect_consolidations
from sweep import detect_sweeps
from filters import check_chart_quality
from formations import detect_formations
from signals import generate_signals
from backtester import run_backtest, BacktestMetrics
from database import get_connection, init_db, save_backtest_batch
from snapshot import generate_snapshot


SYMBOLS = [
    # Top 10
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT",
    # Mid-cap activas
    "UNI/USDT", "NEAR/USDT", "APT/USDT", "SUI/USDT", "ARB/USDT",
    "OP/USDT", "FIL/USDT", "PEPE/USDT", "WIF/USDT", "FET/USDT",
    # Layer 1 / Layer 2  (FTM excluida: renombrada a Sonic, datos corruptos que crashean)
    "ATOM/USDT", "ICP/USDT", "INJ/USDT", "SEI/USDT", "TIA/USDT",
    "STX/USDT", "ALGO/USDT", "EGLD/USDT", "HBAR/USDT",
    # DeFi / Infra  (MKR excluida: datos insuficientes/renombrada)
    "AAVE/USDT", "LDO/USDT", "SNX/USDT", "CRV/USDT",
    "DYDX/USDT", "GMX/USDT", "PENDLE/USDT", "ONDO/USDT", "JUP/USDT",
    # Gaming / AI / Meme  (1000PEPE excluida: no existe en binance)
    "RENDER/USDT", "GRT/USDT", "IMX/USDT", "GALA/USDT", "SAND/USDT",
    "BONK/USDT", "FLOKI/USDT", "SHIB/USDT", "ORDI/USDT",
]

TIMEFRAMES = ["5m", "15m"]


def backtest_single(
    symbol: str,
    timeframe: str,
    candles: int,
    cfg: TFZConfig,
    is_bear: bool = False,
) -> dict:
    tf_cfg = config_for_timeframe(cfg, timeframe)

    try:
        df = fetch_ohlcv(symbol, timeframe, limit=candles, config=tf_cfg)
    except Exception as e:
        return {"symbol": symbol, "timeframe": timeframe, "error": str(e), "signals": 0}

    if len(df) < 200:
        return {"symbol": symbol, "timeframe": timeframe, "error": "insufficient data", "signals": 0}

    window_size = min(400, len(df))
    step = 50
    all_signals = []

    for w_start in range(0, len(df) - window_size, step):
        w_end = w_start + window_size
        window = df.iloc[w_start:w_end].reset_index(drop=True)

        swings = detect_swings(window, tf_cfg)
        quality = check_chart_quality(window, swings, tf_cfg)
        if not quality.passed:
            continue

        current_price = float(window["close"].iloc[-1])
        current_idx = len(window) - 1

        h_levels = detect_horizontal_levels(swings, current_price, tf_cfg, total_candles=len(window))
        d_levels = detect_diagonal_levels(swings, current_price, tf_cfg)
        level_prices = [l.price for l in h_levels]
        consolidations = detect_consolidations(window, tf_cfg, level_prices)
        sweeps_list = detect_sweeps(window, h_levels, tf_cfg)

        formations = detect_formations(
            h_levels, d_levels, consolidations, sweeps_list,
            current_price, current_idx, tf_cfg,
        )

        window_trend = compute_trend_strength(window, timeframe, current_idx)
        signals = generate_signals(
            window, formations, symbol, timeframe, tf_cfg,
            trend_strength=window_trend, is_bear_market=is_bear,
        )

        for sig in signals:
            sig.trigger_idx += w_start

        all_signals.extend(signals)

    # Deduplicate
    seen = set()
    unique = []
    for sig in all_signals:
        key = (sig.trigger_idx, sig.direction)
        if key not in seen:
            seen.add(key)
            unique.append(sig)
    all_signals = unique

    if not all_signals:
        return {
            "symbol": symbol, "timeframe": timeframe,
            "signals": 0, "trades": 0,
        }

    results, metrics = run_backtest(df, all_signals, tf_cfg)

    # Save to DB
    conn = get_connection()
    init_db(conn)
    save_backtest_batch(conn, all_signals, results)
    conn.close()

    # Generate snapshots for best trades
    sig_map = {s.id: s for s in all_signals}
    if results:
        best = sorted(results, key=lambda r: r.pnl_pct, reverse=True)[:2]
        for r in best:
            sig = sig_map.get(r.signal_id)
            if sig and r.pnl_pct > 1.0:
                try:
                    swings = detect_swings(df, tf_cfg)
                    h_lev = detect_horizontal_levels(swings, sig.entry_price, tf_cfg, len(df))
                    generate_snapshot(df, sig, h_lev)
                except Exception:
                    pass

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "signals": len(all_signals),
        "trades": metrics.total_trades,
        "wins": metrics.wins,
        "losses": metrics.losses,
        "breakevens": metrics.breakevens,
        "win_rate": round(metrics.win_rate, 1),
        "total_pnl": round(metrics.total_pnl_pct, 2),
        "avg_win": round(metrics.avg_win_pct, 2),
        "avg_loss": round(metrics.avg_loss_pct, 2),
        "profit_factor": round(metrics.profit_factor, 2),
        "expectancy": round(metrics.expectancy, 4),
        "max_dd": round(metrics.max_drawdown_pct, 2),
        "sharpe": round(metrics.sharpe_ratio, 2),
        "avg_duration": round(metrics.avg_duration, 0),
        "by_formation": metrics.by_formation,
        "by_sweep": metrics.by_sweep,
        "by_direction": metrics.by_direction,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candles", "-n", type=int, default=1000)
    parser.add_argument("--bear", action="store_true")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols override")
    args = parser.parse_args()

    symbols = SYMBOLS
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]

    cfg = TFZConfig()
    all_results = []

    print(f"\n{'='*80}")
    print(f"  TFZ MASS BACKTEST")
    print(f"  {len(symbols)} symbols x {len(TIMEFRAMES)} timeframes = {len(symbols) * len(TIMEFRAMES)} runs")
    print(f"  Candles per run: {args.candles}")
    print(f"  Bear mode: {args.bear}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")

    for i, symbol in enumerate(symbols):
        for tf in TIMEFRAMES:
            label = f"[{i*len(TIMEFRAMES) + TIMEFRAMES.index(tf) + 1}/{len(symbols)*len(TIMEFRAMES)}]"
            print(f"{label} {symbol} {tf}...", end=" ", flush=True)

            try:
                result = backtest_single(symbol, tf, args.candles, cfg, is_bear=args.bear)
                all_results.append(result)

                if result.get("error"):
                    print(f"ERROR: {result['error']}")
                elif result["trades"] == 0:
                    print(f"no signals")
                else:
                    pnl = result["total_pnl"]
                    wr = result["win_rate"]
                    pf = result["profit_factor"]
                    t = result["trades"]
                    sign = "+" if pnl >= 0 else ""
                    print(f"{t} trades | WR: {wr}% | PnL: {sign}{pnl}% | PF: {pf}")
            except Exception as e:
                print(f"EXCEPTION: {e}")
                all_results.append({"symbol": symbol, "timeframe": tf, "error": str(e), "signals": 0})

            time.sleep(0.5)  # rate limit courtesy

    # Aggregate results
    print(f"\n\n{'='*80}")
    print(f"  AGGREGATE RESULTS")
    print(f"{'='*80}")

    valid = [r for r in all_results if r.get("trades", 0) > 0]

    if not valid:
        print("\n  No trades found across all symbols/timeframes.")
        return

    total_trades = sum(r["trades"] for r in valid)
    total_wins = sum(r["wins"] for r in valid)
    total_losses = sum(r["losses"] for r in valid)
    total_pnl = sum(r["total_pnl"] for r in valid)
    all_pnls = []
    for r in valid:
        if r["trades"] > 0:
            all_pnls.extend([r["avg_win"]] * r["wins"])
            all_pnls.extend([r["avg_loss"]] * r["losses"])

    global_wr = total_wins / total_trades * 100 if total_trades > 0 else 0
    global_expectancy = np.mean(all_pnls) if all_pnls else 0

    print(f"\n  Total runs with trades: {len(valid)}/{len(all_results)}")
    print(f"  Total trades:           {total_trades}")
    print(f"  Total wins:             {total_wins} ({global_wr:.1f}%)")
    print(f"  Total losses:           {total_losses}")
    print(f"  Total PnL:              {total_pnl:+.2f}%")
    print(f"  Global expectancy:      {global_expectancy:+.4f}%")

    # By timeframe
    print(f"\n  By timeframe:")
    for tf in TIMEFRAMES:
        tf_results = [r for r in valid if r["timeframe"] == tf]
        if tf_results:
            tf_trades = sum(r["trades"] for r in tf_results)
            tf_wins = sum(r["wins"] for r in tf_results)
            tf_pnl = sum(r["total_pnl"] for r in tf_results)
            tf_wr = tf_wins / tf_trades * 100 if tf_trades > 0 else 0
            print(f"    {tf:>4s} | {tf_trades:3d} trades | WR: {tf_wr:.1f}% | PnL: {tf_pnl:+.2f}%")

    # By formation (aggregated)
    formation_agg = {}
    for r in valid:
        for fname, fdata in r.get("by_formation", {}).items():
            if fname not in formation_agg:
                formation_agg[fname] = {"trades": 0, "wins": 0, "pnl": 0}
            formation_agg[fname]["trades"] += fdata["trades"]
            formation_agg[fname]["wins"] += int(fdata["win_rate"] * fdata["trades"] / 100)
            formation_agg[fname]["pnl"] += fdata["total_pnl"]

    if formation_agg:
        print(f"\n  By formation:")
        for fname, fdata in sorted(formation_agg.items(), key=lambda x: x[1]["pnl"], reverse=True):
            wr = fdata["wins"] / fdata["trades"] * 100 if fdata["trades"] > 0 else 0
            print(f"    {fname:20s} | {fdata['trades']:3d} trades | WR: {wr:.1f}% | PnL: {fdata['pnl']:+.2f}%")

    # By sweep (aggregated)
    sweep_agg = {}
    for r in valid:
        for sname, sdata in r.get("by_sweep", {}).items():
            if sname not in sweep_agg:
                sweep_agg[sname] = {"trades": 0, "wins": 0, "pnl": 0}
            sweep_agg[sname]["trades"] += sdata["trades"]
            sweep_agg[sname]["wins"] += int(sdata["win_rate"] * sdata["trades"] / 100)
            sweep_agg[sname]["pnl"] += sdata["total_pnl"]

    if sweep_agg:
        print(f"\n  By sweep:")
        for sname, sdata in sorted(sweep_agg.items(), key=lambda x: x[1]["pnl"], reverse=True):
            wr = sdata["wins"] / sdata["trades"] * 100 if sdata["trades"] > 0 else 0
            print(f"    {sname:20s} | {sdata['trades']:3d} trades | WR: {wr:.1f}% | PnL: {sdata['pnl']:+.2f}%")

    # By direction (aggregated)
    dir_agg = {}
    for r in valid:
        for dname, ddata in r.get("by_direction", {}).items():
            if dname not in dir_agg:
                dir_agg[dname] = {"trades": 0, "wins": 0, "pnl": 0}
            dir_agg[dname]["trades"] += ddata["trades"]
            dir_agg[dname]["wins"] += int(ddata["win_rate"] * ddata["trades"] / 100)
            dir_agg[dname]["pnl"] += ddata["total_pnl"]

    if dir_agg:
        print(f"\n  By direction:")
        for dname, ddata in sorted(dir_agg.items(), key=lambda x: x[1]["pnl"], reverse=True):
            wr = ddata["wins"] / ddata["trades"] * 100 if ddata["trades"] > 0 else 0
            print(f"    {dname:20s} | {ddata['trades']:3d} trades | WR: {wr:.1f}% | PnL: {ddata['pnl']:+.2f}%")

    # Top performers
    profitable = sorted(valid, key=lambda r: r["total_pnl"], reverse=True)
    print(f"\n  Top 5 performers:")
    for r in profitable[:5]:
        print(f"    {r['symbol']:12s} {r['timeframe']:>4s} | {r['trades']:2d} trades | WR: {r['win_rate']:.1f}% | PnL: {r['total_pnl']:+.2f}% | PF: {r['profit_factor']}")

    print(f"\n  Bottom 5:")
    for r in profitable[-5:]:
        print(f"    {r['symbol']:12s} {r['timeframe']:>4s} | {r['trades']:2d} trades | WR: {r['win_rate']:.1f}% | PnL: {r['total_pnl']:+.2f}% | PF: {r['profit_factor']}")

    # Save summary
    summary_path = os.path.join(os.path.dirname(__file__), "backtest_summary.json")
    with open(summary_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Summary saved to: {summary_path}")

    print(f"\n  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
