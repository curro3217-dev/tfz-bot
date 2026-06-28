"""
TFZ Bot v1 — Trading From Zero Signal & Backtesting Engine

Usage:
    python main.py analyze BTC/USDT --timeframe 15m
    python main.py backtest BTC/USDT --timeframe 15m --candles 2000
    python main.py backtest BTC/USDT --timeframe 5m,15m --candles 3000
"""

import os
import ssl

if os.environ.get("INSECURE_SSL") == "1":
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
import sys
from pathlib import Path

import pandas as pd

from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv
from swings import detect_swings, get_swing_highs, get_swing_lows, compute_trend_strength
from levels import detect_horizontal_levels, detect_diagonal_levels
from consolidation import detect_consolidations
from sweep import detect_sweeps
from filters import check_chart_quality, check_pullback_distance
from formations import detect_formations
from signals import generate_signals
from backtester import run_backtest, BacktestMetrics
from database import get_connection, init_db, save_backtest_batch
from snapshot import generate_snapshot


def analyze(
    symbol: str,
    timeframe: str,
    candles: int = 500,
    trend_strength: float = None,
    is_bear: bool = False,
    cfg: TFZConfig = None,
    save_db: bool = True,
    save_snapshots: bool = True,
):
    cfg = cfg or TFZConfig()
    tf_cfg = config_for_timeframe(cfg, timeframe)

    print(f"\n{'='*60}")
    print(f"  TFZ Analysis: {symbol} | {timeframe} | {candles} candles")
    print(f"{'='*60}")

    # 1. Fetch data
    print("\n[1/7] Fetching candles...")
    df = fetch_ohlcv(symbol, timeframe, limit=candles, config=tf_cfg)
    print(f"  Got {len(df)} candles from {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")

    # 2. Detect swings
    print("[2/7] Detecting swing points...")
    swings = detect_swings(df, tf_cfg)
    sh = get_swing_highs(swings)
    sl = get_swing_lows(swings)
    print(f"  Found {len(sh)} swing highs, {len(sl)} swing lows")

    # 3. Chart quality filter
    print("[3/7] Checking chart quality...")
    quality = check_chart_quality(df, swings, tf_cfg)
    if not quality.passed:
        print(f"  REJECTED: {quality.reason}")
        return None, None
    print(f"  PASSED (wick ratio: {quality.wick_ratio_median:.2f}, gaps: {quality.gap_count})")

    # 4. Detect structure
    print("[4/7] Detecting structure...")
    current_price = float(df["close"].iloc[-1])
    current_idx = len(df) - 1

    h_levels = detect_horizontal_levels(swings, current_price, tf_cfg, total_candles=len(df))
    d_levels = detect_diagonal_levels(swings, current_price, tf_cfg)

    level_prices = [l.price for l in h_levels]
    consolidations = detect_consolidations(df, tf_cfg, level_prices)
    sweeps_list = detect_sweeps(df, h_levels, tf_cfg)

    print(f"  Horizontal levels: {len(h_levels)}")
    for lev in h_levels[:5]:
        tag = " [EQUAL]" if lev.is_equal_hl else ""
        print(f"    {lev.side:>5} | {lev.price:.4g} | {lev.touches}t | score: {lev.score:.0f}{tag}")
    print(f"  Diagonal levels: {len(d_levels)}")
    print(f"  Consolidations: {len(consolidations)}")
    for c in consolidations[-3:]:
        active = " [ACTIVE]" if c.is_active else ""
        print(f"    [{c.start_idx}-{c.end_idx}] range: {c.range_pct:.2f}% | dur: {c.duration} | score: {c.score:.0f}{active}")
    print(f"  Sweeps: {len(sweeps_list)}")
    for sw in sweeps_list[:3]:
        print(f"    {sw.sweep_type} @ {sw.level_price:.4g} | depth: {sw.depth_pct:.2f}% | score: {sw.score:.0f}")

    # 5. Detect formations
    print("[5/7] Detecting formations...")
    formations = detect_formations(
        h_levels, d_levels, consolidations, sweeps_list,
        current_price, current_idx, tf_cfg,
    )
    print(f"  Found {len(formations)} formations")
    for f in formations[:5]:
        print(f"    {f.type} {f.direction} | {len(f.levels)} levels | bonus: +{f.score_bonus}")

    # 6. Generate signals
    print("[6/7] Generating signals...")
    if trend_strength is None:
        trend_strength = compute_trend_strength(df, timeframe, current_idx)
        print(f"  Trend strength (auto): {trend_strength:+.2f}% over ~1d")
    signals = generate_signals(
        df, formations, symbol, timeframe, tf_cfg,
        trend_strength=trend_strength, is_bear_market=is_bear,
    )
    print(f"  Generated {len(signals)} signals")
    for sig in signals[:5]:
        print(f"    [{sig.id}] {sig.direction} {sig.formation_type} | "
              f"entry: {sig.entry_price:.4g} | SL: {sig.stop_loss:.4g} | "
              f"TP: {sig.take_profit:.4g} | R:R {sig.rr_ratio} | score: {sig.total_score}")
        print(f"      breakdown: {sig.score_breakdown}")

    # 7. Save & snapshot
    if save_db and signals:
        print("[7/7] Saving to database...")
        conn = get_connection()
        init_db(conn)
        for sig in signals:
            from database import save_signal
            save_signal(conn, sig)
        conn.close()
        print(f"  Saved {len(signals)} signals")

    if save_snapshots and signals:
        print("  Generating snapshots...")
        for sig in signals[:3]:
            path = generate_snapshot(df, sig, h_levels, d_levels, consolidations)
            if path:
                print(f"    Saved: {path}")

    return signals, df


def backtest(
    symbol: str,
    timeframes: list,
    candles: int = 2000,
    trend_strength: float = None,
    is_bear: bool = False,
    cfg: TFZConfig = None,
):
    cfg = cfg or TFZConfig()

    all_signals = []
    all_results = []
    all_metrics = []

    for tf in timeframes:
        tf_cfg = config_for_timeframe(cfg, tf)

        print(f"\n{'='*60}")
        print(f"  TFZ Backtest: {symbol} | {tf} | {candles} candles")
        print(f"{'='*60}")

        print("\nFetching candles...")
        df = fetch_ohlcv(symbol, tf, limit=candles, config=tf_cfg)
        print(f"Got {len(df)} candles")

        # Sliding window analysis
        window_size = 400
        step = 50
        tf_signals = []

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

            window_trend = trend_strength if trend_strength is not None \
                else compute_trend_strength(window, tf, current_idx)
            signals = generate_signals(
                window, formations, symbol, tf, tf_cfg,
                trend_strength=window_trend, is_bear_market=is_bear,
            )

            # Adjust trigger_idx to global index
            for sig in signals:
                sig.trigger_idx += w_start

            tf_signals.extend(signals)

        # Deduplicate signals (same trigger candle)
        seen = set()
        unique = []
        for sig in tf_signals:
            key = (sig.trigger_idx, sig.direction)
            if key not in seen:
                seen.add(key)
                unique.append(sig)
        tf_signals = unique

        print(f"\nTotal signals found: {len(tf_signals)}")

        # Run backtest
        if tf_signals:
            results, metrics = run_backtest(df, tf_signals, tf_cfg)
            all_signals.extend(tf_signals)
            all_results.extend(results)
            all_metrics.append((tf, metrics))

            _print_metrics(tf, metrics)

            # Save to DB
            conn = get_connection()
            init_db(conn)
            save_backtest_batch(conn, tf_signals, results)
            conn.close()

            # Snapshots for best and worst trades
            if results:
                sorted_res = sorted(results, key=lambda r: r.pnl_pct, reverse=True)
                sig_map = {s.id: s for s in tf_signals}

                print("\n  Generating snapshots for top/bottom trades...")
                for r in sorted_res[:2] + sorted_res[-2:]:
                    sig = sig_map.get(r.signal_id)
                    if sig:
                        swings = detect_swings(df, tf_cfg)
                        h_lev = detect_horizontal_levels(swings, sig.entry_price, tf_cfg, len(df))
                        path = generate_snapshot(df, sig, h_lev)
                        if path:
                            print(f"    [{r.pnl_pct:+.2f}%] {path}")

    return all_signals, all_results, all_metrics


def _print_metrics(tf: str, m: BacktestMetrics):
    print(f"\n{'-'*50}")
    print(f"  BACKTEST RESULTS — {tf}")
    print(f"{'-'*50}")
    print(f"  Total trades:   {m.total_trades}")
    print(f"  Wins:           {m.wins} ({m.win_rate:.1f}%)")
    print(f"  Losses:         {m.losses}")
    print(f"  Breakevens:     {m.breakevens}")
    print(f"  Total PnL:      {m.total_pnl_pct:+.2f}%")
    print(f"  Avg win:        {m.avg_win_pct:+.2f}%")
    print(f"  Avg loss:       {m.avg_loss_pct:+.2f}%")
    print(f"  Profit factor:  {m.profit_factor:.2f}")
    print(f"  Expectancy:     {m.expectancy:+.4f}%")
    print(f"  Avg R:R actual: {m.avg_rr_actual:.2f}")
    print(f"  Max drawdown:   {m.max_drawdown_pct:.2f}%")
    print(f"  Sharpe ratio:   {m.sharpe_ratio:.2f}")
    print(f"  Avg duration:   {m.avg_duration:.0f} candles")

    if m.by_formation:
        print(f"\n  By formation:")
        for k, v in m.by_formation.items():
            print(f"    {k:20s} | {v['trades']:3d} trades | WR: {v['win_rate']:.1f}% | PnL: {v['total_pnl']:+.2f}%")

    if m.by_score_range:
        print(f"\n  By score range:")
        for k, v in m.by_score_range.items():
            print(f"    {k:20s} | {v['trades']:3d} trades | WR: {v['win_rate']:.1f}% | PnL: {v['total_pnl']:+.2f}%")

    if m.by_sweep:
        print(f"\n  By sweep:")
        for k, v in m.by_sweep.items():
            print(f"    {k:20s} | {v['trades']:3d} trades | WR: {v['win_rate']:.1f}% | PnL: {v['total_pnl']:+.2f}%")

    if m.by_direction:
        print(f"\n  By direction:")
        for k, v in m.by_direction.items():
            print(f"    {k:20s} | {v['trades']:3d} trades | WR: {v['win_rate']:.1f}% | PnL: {v['total_pnl']:+.2f}%")


def main():
    parser = argparse.ArgumentParser(description="TFZ Bot v1 — Signal & Backtesting Engine")
    sub = parser.add_subparsers(dest="command")

    # Analyze command
    p_analyze = sub.add_parser("analyze", help="Analyze a symbol for current setups")
    p_analyze.add_argument("symbol", help="e.g. BTC/USDT")
    p_analyze.add_argument("--timeframe", "-tf", default="15m")
    p_analyze.add_argument("--candles", "-n", type=int, default=500)
    p_analyze.add_argument("--trend", type=float, default=None,
                           help="Trend strength in pct (auto-computed from data if omitted)")
    p_analyze.add_argument("--bear", action="store_true", help="Bear market mode")
    p_analyze.add_argument("--no-db", action="store_true")
    p_analyze.add_argument("--no-snapshots", action="store_true")

    # Backtest command
    p_bt = sub.add_parser("backtest", help="Backtest on historical data")
    p_bt.add_argument("symbol", help="e.g. BTC/USDT")
    p_bt.add_argument("--timeframe", "-tf", default="15m", help="Comma-separated: 5m,15m")
    p_bt.add_argument("--candles", "-n", type=int, default=2000)
    p_bt.add_argument("--trend", type=float, default=None,
                      help="Trend strength in pct (auto-computed per window if omitted)")
    p_bt.add_argument("--bear", action="store_true")

    # Paper trading command
    p_paper = sub.add_parser("paper", help="Run one paper-trading cycle (update + scan + report)")
    p_paper.add_argument("--timeframe", "-tf", default="5m,15m", help="Comma-separated: 5m,15m")
    p_paper.add_argument("--symbols", default=None, help="Comma-separated manual override of the watchlist")
    p_paper.add_argument("--watchlist", choices=["scanner", "majors"], default="scanner",
                         help="Watchlist source when --symbols not given (default: scanner movers)")
    p_paper.add_argument("--fresh", type=int, default=2,
                         help="Accept signals triggered within the last N candles (match to run cadence)")
    p_paper.add_argument("--ml-cutoff", type=float, default=0.55,
                         help="ML win-probability gate (default 0.55)")
    p_paper.add_argument("--no-ml", action="store_true", help="Disable the ML quality filter")
    p_paper.add_argument("--filter", choices=["ml", "profit"], default="ml",
                         help="Acceptance filter: 'ml' (win-prob gate) or 'profit' (score+RR, "
                              "keeps high-RR asymmetric winners the ML wrongly discards)")
    p_paper.add_argument("--min-score", type=float, default=60.0,
                         help="profit filter: minimum total_score (default 60)")
    p_paper.add_argument("--min-rr", type=float, default=8.0,
                         help="profit filter: minimum rr_ratio (default 8)")
    p_paper.add_argument("--status", action="store_true", help="Only print status, no update/scan")
    p_paper.add_argument("--enable-f1", action="store_true",
                         help="Enable F1 (breakout-to-liquidity, Mark's primary setup)")
    p_paper.add_argument("--f1-retest", action="store_true",
                         help="F1 entry on the retest-that-holds (validated +edge under profit filter)")

    # Portfolio command — cartera simulada $50 (riesgo 1%/trade)
    sub.add_parser("portfolio", help="Estado de la cartera simulada de $50")

    # Scan command — read-only: list current setups for manual testing
    p_scan = sub.add_parser("scan", help="List current entries from the scanner's coins (read-only)")
    p_scan.add_argument("--timeframe", "-tf", default="5m,15m")
    p_scan.add_argument("--symbols", default=None, help="Comma-separated manual override")
    p_scan.add_argument("--watchlist", choices=["scanner", "majors"], default="scanner")
    p_scan.add_argument("--fresh", type=int, default=20,
                        help="Show setups triggered within the last N candles (default 20)")
    p_scan.add_argument("--ml-cutoff", type=float, default=0.55)
    p_scan.add_argument("--all", action="store_true", help="Show all setups, not just ML-approved")

    # Execution command (testnet-first, dry-run by default)
    p_tr = sub.add_parser("trade", help="Execution cycle: place (or simulate) orders from signals")
    p_tr.add_argument("--timeframe", "-tf", default="5m,15m")
    p_tr.add_argument("--symbols", default=None, help="Comma-separated manual override")
    p_tr.add_argument("--watchlist", choices=["scanner", "majors"], default="scanner")
    p_tr.add_argument("--fresh", type=int, default=2)
    p_tr.add_argument("--ml-cutoff", type=float, default=0.55)
    p_tr.add_argument("--no-ml", action="store_true")
    p_tr.add_argument("--filter", choices=["ml", "profit"], default="ml",
                      help="Acceptance filter: 'ml' (win-prob) or 'profit' (score+RR, same as paper)")
    p_tr.add_argument("--min-score", type=float, default=60.0, help="profit filter: min total_score")
    p_tr.add_argument("--min-rr", type=float, default=8.0, help="profit filter: min rr_ratio")
    p_tr.add_argument("--exchange", default="bybit", choices=["bybit", "binance", "hyperliquid"],
                      help="Execution venue (hyperliquid = DEX, no KYC, wallet auth, testnet)")
    p_tr.add_argument("--risk", type=float, default=1.0, help="%% equity risked per trade")
    p_tr.add_argument("--leverage", type=int, default=3)
    p_tr.add_argument("--max-positions", type=int, default=3)
    p_tr.add_argument("--live-testnet", action="store_true",
                      help="Actually send orders to the Bybit TESTNET (needs testnet API keys)")
    p_tr.add_argument("--i-understand-live", action="store_true",
                      help="Required, with --live-testnet OFF, to trade REAL money (not recommended)")
    p_tr.add_argument("--check", action="store_true",
                      help="Connection test only: verify testnet keys, show equity & positions")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "analyze":
        analyze(
            args.symbol,
            args.timeframe,
            candles=args.candles,
            trend_strength=args.trend,
            is_bear=args.bear,
            save_db=not args.no_db,
            save_snapshots=not args.no_snapshots,
        )

    elif args.command == "backtest":
        timeframes = [t.strip() for t in args.timeframe.split(",")]
        backtest(
            args.symbol,
            timeframes,
            candles=args.candles,
            trend_strength=args.trend,
            is_bear=args.bear,
        )

    elif args.command == "paper":
        from paper import run_cycle, print_status, DEFAULT_WATCHLIST
        from database import get_connection, init_db
        if args.status:
            conn = get_connection()
            init_db(conn)
            print_status(conn)
            conn.close()
        else:
            timeframes = [t.strip() for t in args.timeframe.split(",")]
            symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
            source = "scanner" if args.watchlist == "scanner" else "majors"
            cfg = TFZConfig()
            cfg.funding_pct_per_8h = 0.01  # perp funding (igual que la validación; el usuario opera perps)
            if args.enable_f1:
                cfg.enable_f1 = True
            if args.f1_retest:
                cfg.f1_retest_entry = True
            run_cycle(symbols=symbols, timeframes=timeframes, cfg=cfg, fresh_lookback=args.fresh,
                      ml_cutoff=args.ml_cutoff, use_ml=not args.no_ml, watchlist_source=source,
                      filter_mode=args.filter, min_score=args.min_score, min_rr=args.min_rr)

    elif args.command == "portfolio":
        from portfolio import print_portfolio
        print_portfolio()

    elif args.command == "scan":
        from paper import collect_setups, resolve_watchlist
        timeframes = [t.strip() for t in args.timeframe.split(",")]
        symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
        source = "scanner" if args.watchlist == "scanner" else "majors"
        symbols = resolve_watchlist(symbols, source, verbose=True)
        print(f"\n  Escaneando {len(symbols)} monedas x {len(timeframes)} TF "
              f"(setups de las ultimas {args.fresh} velas)...")
        rows = collect_setups(symbols, timeframes, TFZConfig(), fresh_lookback=args.fresh,
                              ml_cutoff=args.ml_cutoff)
        if not args.all:
            rows = [r for r in rows if r["win_prob"] is None or r["win_prob"] >= args.ml_cutoff]
        if not rows:
            print("\n  No hay setups frescos ahora mismo (es normal: son escasos).")
            print("  Prueba --fresh 50 para ver setups algo mas antiguos, o --all para verlos todos.\n")
            return
        print(f"\n  {'#':<3}{'moneda':<18}{'TF':<5}{'dir':<6}{'hora ES':>8}"
              f"{'entry':>12}{'SL':>12}{'TP':>12}{'R:R':>6}{'win%':>6}{'resultado':>12}")
        print("  " + "-" * 109)
        for i, r in enumerate(rows, 1):
            wp = f"{r['win_prob']*100:.0f}" if r['win_prob'] is not None else "-"
            res = r['outcome']
            if r['out_pnl'] is not None:
                res = f"{r['outcome']} {r['out_pnl']:+.1f}%"
            print(f"  {i:<3}{r['symbol']:<18}{r['tf']:<5}{r['direction']:<6}{r['time_es']:>8}"
                  f"{r['entry']:>12.6g}{r['sl']:>12.6g}{r['tp']:>12.6g}{r['rr']:>6.1f}"
                  f"{wp:>6}{res:>12}")
        print(f"\n  {len(rows)} setup(s). 'resultado' = lo que ha hecho desde que se activo "
              f"(TP/SL/abierto), calculado por el bot.")
        print(f"  win% = probabilidad de ganar segun el ML | 'hora ES' = activacion (España, CEST).")
        print("  Recuerda: son para que TU las testees a mano. El bot no opera nada.\n")
        return

    elif args.command == "trade":
        from execution import run_execution_cycle, ExecutionConfig, Executor
        if args.check:
            ex = Executor(ExecutionConfig(exchange=args.exchange,
                                          testnet=not args.i_understand_live, dry_run=False,
                                          confirm_live=args.i_understand_live))
            print(f"\n  Connection check | mode: {ex.mode}")
            try:
                eq = ex.get_equity()
                pos = ex.open_positions()
                print(f"  OK - equity: {eq:.2f} USDT | open positions: {len(pos)}")
                for p in pos:
                    print(f"    {p.get('symbol')} {p.get('side')} {p.get('contracts')}")
            except Exception as e:
                print(f"  FAILED: {e}")
            return
        # Safe by default: simulate. --live-testnet sends to sandbox.
        # --i-understand-live sends REAL orders (heavily discouraged).
        if args.i_understand_live:
            ecfg = ExecutionConfig(exchange=args.exchange, testnet=False, dry_run=False,
                                   confirm_live=True, risk_per_trade_pct=args.risk,
                                   leverage=args.leverage, max_open_positions=args.max_positions)
            print("\n*** WARNING: REAL-MONEY trading enabled. This places live orders. ***\n")
        elif args.live_testnet:
            ecfg = ExecutionConfig(exchange=args.exchange, testnet=True, dry_run=False,
                                   risk_per_trade_pct=args.risk, leverage=args.leverage,
                                   max_open_positions=args.max_positions)
        else:
            ecfg = ExecutionConfig(exchange=args.exchange, testnet=True, dry_run=True,
                                   risk_per_trade_pct=args.risk, leverage=args.leverage,
                                   max_open_positions=args.max_positions)
        timeframes = [t.strip() for t in args.timeframe.split(",")]
        symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
        source = "scanner" if args.watchlist == "scanner" else "majors"
        run_execution_cycle(symbols=symbols, timeframes=timeframes, exec_cfg=ecfg,
                            fresh_lookback=args.fresh, ml_cutoff=args.ml_cutoff,
                            use_ml=not args.no_ml, watchlist_source=source,
                            filter_mode=args.filter, min_score=args.min_score, min_rr=args.min_rr)


if __name__ == "__main__":
    main()
