"""
Out-of-sample validation.

Fetches a long history per symbol/TF, splits it into two halves:
  - OOS  (older half)  -> data the methodology was NEVER tuned against
  - IS   (recent half) -> the period we hand-tuned on (mass_backtest)

Runs the identical signal pipeline on each half and compares expectancy,
win rate and PnL. If the edge survives on the OOS half, it is not overfit.

Usage: python validate_oos.py [--candles 20000]
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
    if not kwargs.get("timeout"):
        kwargs["timeout"] = (10, 20)  # (connect, read) — never hang forever
    return _orig_send(self, request, **kwargs)
_radapt.HTTPAdapter.send = _nosslcheck_send

import argparse
import json
from datetime import datetime

from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv
from swings import detect_swings, compute_trend_strength
from levels import detect_horizontal_levels, detect_diagonal_levels
from consolidation import detect_consolidations
from sweep import detect_sweeps
from filters import check_chart_quality
from formations import detect_formations
from signals import generate_signals
from backtester import run_backtest

from mass_backtest import SYMBOLS, TIMEFRAMES


def run_period(df, symbol, timeframe, tf_cfg, step=200):
    """Run the windowed signal pipeline + backtest on a single df slice."""
    if len(df) < 200:
        return None

    window_size = min(400, len(df))
    all_signals = []

    for w_start in range(0, len(df) - window_size, step):
        window = df.iloc[w_start:w_start + window_size].reset_index(drop=True)

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
        trend = compute_trend_strength(window, timeframe, current_idx)
        signals = generate_signals(
            window, formations, symbol, timeframe, tf_cfg,
            trend_strength=trend, is_bear_market=False,
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
        return {"trades": 0, "wins": 0, "total_pnl": 0.0, "expectancy": 0.0,
                "win_rate": 0.0, "by_formation": {}}

    results, metrics = run_backtest(df, all_signals, tf_cfg)

    # Compounded equity curve: sequential trades (by entry), fixed-fractional
    # 1% risk per trade. R-multiple = net_pnl / risk_pct. This turns the flat
    # sum-of-% into a realistic capital multiple with a real drawdown.
    sig_map = {s.id: s for s in all_signals}
    risk_frac = 0.01
    equity, peak, max_dd = 1.0, 1.0, 0.0
    ordered = sorted(results, key=lambda r: sig_map[r.signal_id].trigger_idx
                     if r.signal_id in sig_map else 0)
    for r in ordered:
        sig = sig_map.get(r.signal_id)
        rp = sig.risk_pct if sig and sig.risk_pct > 0 else 1.0
        R = r.pnl_pct / rp
        equity *= (1 + risk_frac * R)
        if equity <= 0:
            equity = 1e-9
            break
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        max_dd = max(max_dd, dd)

    # Per-trade (score, net pnl) so the caller can sweep score thresholds.
    trades_detail = []
    for r in results:
        sig = sig_map.get(r.signal_id)
        if sig:
            trades_detail.append((sig.total_score, r.pnl_pct))

    return {
        "trades": metrics.total_trades,
        "wins": metrics.wins,
        "total_pnl": metrics.total_pnl_pct,
        "expectancy": metrics.expectancy,
        "win_rate": metrics.win_rate,
        "by_formation": metrics.by_formation,
        "equity_mult": equity,
        "equity_maxdd": max_dd,
        "trades_detail": trades_detail,
    }


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return 0.0
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def agg(results):
    trades = sum(r["trades"] for r in results)
    wins = sum(r["wins"] for r in results)
    pnl = sum(r["total_pnl"] for r in results)
    wr = wins / trades * 100 if trades else 0
    exp = pnl / trades if trades else 0
    # Per-symbol compounded equity (only symbols that actually traded)
    mults = [r["equity_mult"] for r in results if r.get("trades", 0) > 0]
    dds = [r["equity_maxdd"] for r in results if r.get("trades", 0) > 0]
    return {
        "trades": trades, "wins": wins, "pnl": pnl, "wr": wr, "exp": exp,
        "median_mult": _median(mults), "median_dd": _median(dds),
        "pct_profitable": sum(1 for m in mults if m > 1.0) / len(mults) * 100 if mults else 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candles", "-n", type=int, default=20000,
                        help="Total candles to fetch; split in half (OOS/IS)")
    parser.add_argument("--step", type=int, default=200,
                        help="Window step in candles (higher = faster, dedup removes overlap)")
    parser.add_argument("--max-symbols", type=int, default=None,
                        help="Limit number of symbols (for a faster preliminary run)")
    parser.add_argument("--score-floor", type=int, default=None,
                        help="Override score_minimo to collect lower-score trades for a threshold sweep")
    parser.add_argument("--perp", action="store_true",
                        help="Validate on USDT perpetuals (BASE/USDT:USDT) with funding cost")
    parser.add_argument("--funding", type=float, default=0.01,
                        help="Perp funding %% per 8h when --perp (default 0.01)")
    parser.add_argument("--symbols", default=None,
                        help="Comma-separated symbol override (e.g. the scanner's movers)")
    args = parser.parse_args()

    base = TFZConfig()
    if args.score_floor is not None:
        base.score_minimo = args.score_floor
        base.bear_score_minimo = args.score_floor
    if args.perp:
        base.funding_pct_per_8h = args.funding
    total = args.candles
    half = total // 2
    step = args.step
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
    else:
        symbols = SYMBOLS[:args.max_symbols] if args.max_symbols else SYMBOLS
    if args.perp:
        symbols = [s + ":USDT" if s.endswith("/USDT") and not s.endswith(":USDT") else s
                   for s in symbols]

    print("=" * 80)
    print("  TFZ OUT-OF-SAMPLE VALIDATION")
    print(f"  {len(symbols)} symbols x {len(TIMEFRAMES)} TF | {total} candles -> 2 x {half} | step {step}")
    print(f"  OOS = older half (never tuned) | IS = recent half (tuned)")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80 + "\n")

    oos_results, is_results = [], []
    detail = []
    n = len(symbols) * len(TIMEFRAMES)
    i = 0

    for symbol in symbols:
        for tf in TIMEFRAMES:
            i += 1
            tf_cfg = config_for_timeframe(base, tf)
            try:
                df = fetch_ohlcv(symbol, tf, limit=total, config=tf_cfg)
            except Exception as e:
                print(f"[{i}/{n}] {symbol} {tf}... ERROR: {e}")
                continue

            if len(df) < total * 0.6:
                print(f"[{i}/{n}] {symbol} {tf}... insufficient data ({len(df)})")
                continue

            mid = len(df) // 2
            df_oos = df.iloc[:mid].reset_index(drop=True)
            df_is = df.iloc[mid:].reset_index(drop=True)

            try:
                r_oos = run_period(df_oos, symbol, tf, tf_cfg, step=step)
                r_is = run_period(df_is, symbol, tf, tf_cfg, step=step)
            except Exception as e:
                print(f"[{i}/{n}] {symbol} {tf}... PROCESSING ERROR: {e}")
                continue
            if r_oos:
                oos_results.append(r_oos)
            if r_is:
                is_results.append(r_is)

            ot = r_oos["trades"] if r_oos else 0
            it = r_is["trades"] if r_is else 0
            op = r_oos["total_pnl"] if r_oos else 0
            ip = r_is["total_pnl"] if r_is else 0
            print(f"[{i}/{n}] {symbol:12s} {tf:>4s} | "
                  f"OOS {ot:2d}tr {op:+6.1f}% | IS {it:2d}tr {ip:+6.1f}%")

            detail.append({
                "symbol": symbol, "timeframe": tf,
                "oos": r_oos, "is": r_is,
            })

    a_oos = agg(oos_results)
    a_is = agg(is_results)

    print("\n" + "=" * 80)
    print("  RESULTS: OUT-OF-SAMPLE  vs  IN-SAMPLE")
    print("=" * 80)
    print(f"\n  {'metric':<14s} {'OOS (older)':>16s} {'IS (recent)':>16s}")
    print(f"  {'-'*14} {'-'*16} {'-'*16}")
    print(f"  {'trades':<14s} {a_oos['trades']:>16d} {a_is['trades']:>16d}")
    print(f"  {'win rate':<14s} {a_oos['wr']:>15.1f}% {a_is['wr']:>15.1f}%")
    print(f"  {'total PnL':<14s} {a_oos['pnl']:>+15.1f}% {a_is['pnl']:>+15.1f}%")
    print(f"  {'expectancy':<14s} {a_oos['exp']:>+15.3f}% {a_is['exp']:>+15.3f}%")
    print(f"\n  Compounded equity per symbol (1% risk/trade, sequential):")
    print(f"  {'median mult':<14s} {a_oos['median_mult']:>15.2f}x {a_is['median_mult']:>15.2f}x")
    print(f"  {'median maxDD':<14s} {a_oos['median_dd']:>15.1f}% {a_is['median_dd']:>15.1f}%")
    print(f"  {'% profitable':<14s} {a_oos['pct_profitable']:>15.1f}% {a_is['pct_profitable']:>15.1f}%")

    # Degradation: how much worse is OOS vs IS?
    if a_is["exp"] != 0:
        degr = (a_oos["exp"] - a_is["exp"]) / abs(a_is["exp"]) * 100
        print(f"\n  Expectancy OOS vs IS: {degr:+.1f}%")
        if a_oos["exp"] > 0 and degr > -40:
            print("  VERDICT: edge holds out-of-sample (positive, <40% degradation)")
        elif a_oos["exp"] > 0:
            print("  VERDICT: edge survives but degrades notably out-of-sample")
        else:
            print("  VERDICT: edge does NOT hold out-of-sample (likely overfit)")

    # Per-formation OOS
    fagg = {}
    for r in oos_results:
        for fname, fd in r.get("by_formation", {}).items():
            if fname not in fagg:
                fagg[fname] = {"trades": 0, "pnl": 0.0}
            fagg[fname]["trades"] += fd["trades"]
            fagg[fname]["pnl"] += fd["total_pnl"]
    if fagg:
        print(f"\n  OOS by formation:")
        for fname, fd in sorted(fagg.items(), key=lambda x: x[1]["pnl"], reverse=True):
            print(f"    {fname:20s} | {fd['trades']:3d} trades | PnL {fd['pnl']:+.1f}%")

    # Score-threshold sweep (only meaningful when --score-floor lowered the bar)
    oos_td = [t for r in oos_results for t in r.get("trades_detail", [])]
    is_td = [t for r in is_results for t in r.get("trades_detail", [])]
    if oos_td and min(s for s, _ in oos_td) < 70:
        print(f"\n  Score-threshold sweep (expectancy / trades):")
        print(f"  {'thresh':>6s} {'OOS exp':>10s} {'OOS n':>7s} {'IS exp':>10s} {'IS n':>7s}")
        print(f"  {'-'*6} {'-'*10} {'-'*7} {'-'*10} {'-'*7}")
        for t in [50, 55, 60, 65, 70, 75, 80]:
            o = [p for s, p in oos_td if s >= t]
            ii = [p for s, p in is_td if s >= t]
            oe = sum(o) / len(o) if o else 0
            ie = sum(ii) / len(ii) if ii else 0
            print(f"  {t:>6d} {oe:>+9.3f}% {len(o):>7d} {ie:>+9.3f}% {len(ii):>7d}")

    out = os.path.join(os.path.dirname(__file__), "validation_oos.json")
    with open(out, "w") as f:
        json.dump({"oos": a_oos, "is": a_is, "detail": detail}, f, indent=2, default=str)
    print(f"\n  Saved: {out}")
    print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
