"""
Walk-forward / live-logic replay.

Replays the EXACT production config (mover coins, score>=60, ML gate, costs +
funding) across all available history and reports performance MONTH BY MONTH,
plus a compounded equity curve. Gives "months of live trading" in minutes
instead of waiting for real time to pass.

Usage: python -u walkforward.py [--candles 20000] [--step 100] [--ml-cutoff 0.50]
"""

import os
os.environ.setdefault("INSECURE_SSL", "1")
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests.adapters as _ra
_orig = _ra.HTTPAdapter.send
def _ns(self, r, **k):
    k["verify"] = False
    if not k.get("timeout"):
        k["timeout"] = (10, 20)
    return _orig(self, r, **k)
_ra.HTTPAdapter.send = _ns

import argparse
from collections import defaultdict
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
import ml_filter

TIMEFRAMES = ["5m", "15m"]

# Mover-type coins with enough history (what the scanner actually picks)
MOVERS = ["SIREN", "ESPORTS", "COAI", "EVAA", "BEAT", "STG", "H", "MEGA",
          "SOXL", "RIF", "VELVET", "TRUMP", "NEAR", "ADA", "WLD", "ZEC", "JTO"]


def run_symbol(df, symbol, tf, tf_cfg, ml_cutoff, step):
    window_size = min(400, len(df))
    all_sigs, trend_at = [], {}
    for w in range(0, len(df) - window_size, step):
        window = df.iloc[w:w + window_size].reset_index(drop=True)
        swings = detect_swings(window, tf_cfg)
        if not check_chart_quality(window, swings, tf_cfg).passed:
            continue
        cp = float(window["close"].iloc[-1]); ci = len(window) - 1
        h = detect_horizontal_levels(swings, cp, tf_cfg, total_candles=len(window))
        d = detect_diagonal_levels(swings, cp, tf_cfg)
        consols = detect_consolidations(window, tf_cfg, [l.price for l in h])
        sweeps = detect_sweeps(window, h, tf_cfg)
        forms = detect_formations(h, d, consols, sweeps, cp, ci, tf_cfg)
        trend = compute_trend_strength(window, tf, ci)
        sigs = generate_signals(window, forms, symbol, tf, tf_cfg,
                                trend_strength=trend, is_bear_market=False)
        for s in sigs:
            s.trigger_idx += w
            trend_at[s.id] = trend
        all_sigs.extend(sigs)

    seen, uniq = set(), []
    for s in all_sigs:
        k = (s.trigger_idx, s.direction)
        if k not in seen:
            seen.add(k); uniq.append(s)

    # Apply the LIVE ML gate
    kept = []
    for s in uniq:
        p = ml_filter.predict_win_prob(s, trend_at.get(s.id, 0.0))
        if p is None or p >= ml_cutoff:
            kept.append(s)
    if not kept:
        return []

    results, _ = run_backtest(df, kept, tf_cfg)
    smap = {s.id: s for s in kept}
    rows = []
    for r in results:
        s = smap.get(r.signal_id)
        if s:
            rows.append((str(s.timestamp), r.pnl_pct, s.risk_pct))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candles", "-n", type=int, default=20000)
    ap.add_argument("--step", type=int, default=100)
    ap.add_argument("--ml-cutoff", type=float, default=0.50)
    args = ap.parse_args()

    base = TFZConfig()          # production: score_minimo=60
    base.funding_pct_per_8h = 0.01
    symbols = [f"{b}/USDT:USDT" for b in MOVERS]

    print("=" * 72)
    print("  TFZ WALK-FORWARD (replay de la logica en vivo)")
    print(f"  {len(symbols)} movers x {len(TIMEFRAMES)} TF | score>=60 | ML>="
          f"{args.ml_cutoff} | costes+funding")
    print(f"  Started: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 72 + "\n")

    all_trades = []
    n = len(symbols) * len(TIMEFRAMES); i = 0
    for sym in symbols:
        for tf in TIMEFRAMES:
            i += 1
            tf_cfg = config_for_timeframe(base, tf)
            try:
                df = fetch_ohlcv(sym, tf, limit=args.candles, config=tf_cfg)
            except Exception as e:
                print(f"[{i}/{n}] {sym} {tf} ERROR: {str(e)[:50]}"); continue
            if len(df) < 1000:
                print(f"[{i}/{n}] {sym} {tf} pocos datos ({len(df)})"); continue
            try:
                rows = run_symbol(df, sym, tf, tf_cfg, args.ml_cutoff, args.step)
            except Exception as e:
                print(f"[{i}/{n}] {sym} {tf} PROC ERROR: {str(e)[:50]}"); continue
            all_trades.extend(rows)
            print(f"[{i}/{n}] {sym:18s} {tf:>3s} | {len(rows):3d} trades (ML-aprobados)")

    if not all_trades:
        print("\nSin trades. Nada que agregar."); return

    # Group by month
    by_month = defaultdict(list)
    for ts, pnl, risk in all_trades:
        by_month[ts[:7]].append(pnl)

    print("\n" + "=" * 72)
    print("  RESULTADO MES A MES (lo que el bot en vivo habria hecho)")
    print("=" * 72)
    print(f"\n  {'mes':<9}{'trades':>8}{'win%':>8}{'PnL%':>10}{'exp/trade':>11}")
    print(f"  {'-'*9}{'-'*8}{'-'*8}{'-'*10}{'-'*11}")
    for mes in sorted(by_month):
        p = by_month[mes]
        wr = sum(1 for x in p if x > 0.05) / len(p) * 100
        print(f"  {mes:<9}{len(p):>8}{wr:>7.1f}%{sum(p):>+9.1f}%{sum(p)/len(p):>+10.3f}%")

    pnls = [t[1] for t in all_trades]
    wr = sum(1 for x in pnls if x > 0.05) / len(pnls) * 100
    print(f"\n  {'TOTAL':<9}{len(pnls):>8}{wr:>7.1f}%{sum(pnls):>+9.1f}%{sum(pnls)/len(pnls):>+10.3f}%")

    # Compounded equity (sequential by entry time, 1% risk/trade)
    ordered = sorted(all_trades, key=lambda t: t[0])
    eq, peak, maxdd = 1.0, 1.0, 0.0
    for ts, pnl, risk in ordered:
        R = pnl / risk if risk and risk > 0 else 0
        eq *= (1 + 0.01 * R)
        if eq <= 0:
            eq = 1e-9; break
        peak = max(peak, eq); maxdd = max(maxdd, (peak - eq) / peak * 100)
    print(f"\n  Capital compuesto (1% riesgo/trade, secuencial): {eq:.2f}x | maxDD {maxdd:.1f}%")
    print(f"\n  Finished: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
