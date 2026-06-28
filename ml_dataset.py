"""
Build a labeled dataset for the ML signal-quality filter.

Runs the windowed pipeline across the universe, and for every signal records its
features + the trade outcome (net of costs). Generates with a LOW score floor so
the full quality spectrum is captured -- the model must see losers too.

Output: ml_dataset.csv  (one row per trade)

Usage: python -u ml_dataset.py [--candles 20000] [--step 100] [--score-floor 40]
"""

import os
os.environ.setdefault("INSECURE_SSL", "1")
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests.adapters as _radapt
_orig_send = _radapt.HTTPAdapter.send
def _ns(self, request, **kwargs):
    kwargs["verify"] = False
    if not kwargs.get("timeout"):
        kwargs["timeout"] = (10, 20)
    return _orig_send(self, request, **kwargs)
_radapt.HTTPAdapter.send = _ns

import argparse
import csv
from datetime import datetime

from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv, fetch_ohlcv_cached
from swings import detect_swings, compute_trend_strength
from levels import detect_horizontal_levels, detect_diagonal_levels
from consolidation import detect_consolidations
from sweep import detect_sweeps
from filters import check_chart_quality
from formations import detect_formations
from signals import generate_signals
from backtester import run_backtest
from mass_backtest import SYMBOLS, TIMEFRAMES

FEATURES = [
    "tf_minutes", "direction_long", "formation_F2", "formation_F3", "formation_F4",
    "total_score", "trend_alignment", "liquidity_levels", "consolidation_score",
    "sweep_score", "cascade_levels", "distance_quality", "rr_quality",
    "rr_ratio", "risk_pct", "trend_strength",
    "num_levels", "max_touches", "avg_level_score",
    "consol_duration", "consol_quality", "sweep_depth", "has_sweep", "is_cascade",
    "sweep_vol_ratio", "reclaim_body_atr", "trigger_body_atr",
]

_TF_MIN = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}


def _row(sig, trend, pnl):
    sb = sig.score_breakdown
    levels = sig.levels or []
    consol = sig.consolidation or {}
    sweep = sig.sweep or {}
    ftype = sig.formation_type
    return {
        "tf_minutes": _TF_MIN.get(sig.timeframe, 15),
        "direction_long": 1 if sig.direction == "long" else 0,
        "formation_F2": 1 if ftype == "F2" else 0,
        "formation_F3": 1 if ftype == "F3" else 0,
        "formation_F4": 1 if ftype == "F4_manipulation" else 0,
        "total_score": sig.total_score,
        "trend_alignment": sb.get("trend_alignment", 0),
        "liquidity_levels": sb.get("liquidity_levels", 0),
        "consolidation_score": sb.get("consolidation", 0),
        "sweep_score": sb.get("sweep", 0),
        "cascade_levels": sb.get("cascade_levels", 0),
        "distance_quality": sb.get("distance_quality", 0),
        "rr_quality": sb.get("rr_quality", 0),
        "rr_ratio": sig.rr_ratio,
        "risk_pct": sig.risk_pct,
        "trend_strength": round(trend, 3),
        "num_levels": len(levels),
        "max_touches": max((l.get("touches", 0) for l in levels), default=0),
        "avg_level_score": round(sum(l.get("score", 0) for l in levels) / len(levels), 1) if levels else 0,
        "consol_duration": consol.get("duration", 0),
        "consol_quality": consol.get("score", 0),
        "sweep_depth": sweep.get("depth_pct", 0),
        "has_sweep": 1 if sig.sweep else 0,
        "is_cascade": 1 if ftype == "F3" else 0,
        "sweep_vol_ratio": sweep.get("vol_ratio", 1.0),
        "reclaim_body_atr": sweep.get("reclaim_body_atr", 0.0),
        "trigger_body_atr": getattr(sig, "trigger_body_atr", 0.0),
        # meta / label
        "pnl_pct": round(pnl, 4),
        "win": 1 if pnl > 0 else 0,
        "symbol": sig.symbol,
        "timeframe": sig.timeframe,
        "entry_ts": str(sig.timestamp),
    }


def collect(df, symbol, tf, tf_cfg, step, bypass_quality=False):
    window_size = min(400, len(df))
    all_signals, trend_at, quality_at = [], {}, {}
    for w_start in range(0, len(df) - window_size, step):
        window = df.iloc[w_start:w_start + window_size].reset_index(drop=True)
        swings = detect_swings(window, tf_cfg)
        q = check_chart_quality(window, swings, tf_cfg).passed
        if not q and not bypass_quality:
            continue
        cp = float(window["close"].iloc[-1])
        cidx = len(window) - 1
        h = detect_horizontal_levels(swings, cp, tf_cfg, total_candles=len(window))
        d = detect_diagonal_levels(swings, cp, tf_cfg)
        consols = detect_consolidations(window, tf_cfg, [l.price for l in h])
        sweeps = detect_sweeps(window, h, tf_cfg)
        forms = detect_formations(h, d, consols, sweeps, cp, cidx, tf_cfg)
        trend = compute_trend_strength(window, tf, cidx, hours=tf_cfg.trend_lookback_hours)
        sigs = generate_signals(window, forms, symbol, tf, tf_cfg,
                                trend_strength=trend, is_bear_market=False)
        for s in sigs:
            s.trigger_idx += w_start
            trend_at[s.id] = trend
            quality_at[s.id] = 1 if q else 0
        all_signals.extend(sigs)

    seen, unique = set(), []
    for s in all_signals:
        k = (s.trigger_idx, s.direction)
        if k not in seen:
            seen.add(k)
            unique.append(s)
    if not unique:
        return []
    results, _ = run_backtest(df, unique, tf_cfg)
    smap = {s.id: s for s in unique}
    closes_full = df["close"].values
    highs_full = df["high"].values
    lows_full = df["low"].values
    vol_full = df["volume"].values
    L_intra = {"1m": 240, "5m": 48, "15m": 16, "1h": 4}.get(tf, 16)  # ~4h
    N_vwap = {"1m": 1440, "5m": 288, "15m": 96, "1h": 24}.get(tf, 96)  # VWAP anclado ~24h
    rows = []
    for r in results:
        s = smap.get(r.signal_id)
        if s:
            row = _row(s, trend_at.get(s.id, 0.0), r.pnl_pct)
            gi = s.trigger_idx
            if 0 < gi < len(closes_full):
                ref = closes_full[max(0, gi - L_intra)]
                row["trend_intraday"] = round((closes_full[gi] - ref) / ref * 100, 3) if ref > 0 else 0.0
                a = max(0, gi - N_vwap)
                tp = (highs_full[a:gi+1] + lows_full[a:gi+1] + closes_full[a:gi+1]) / 3
                vv = vol_full[a:gi+1]
                vwap = float((tp * vv).sum() / vv.sum()) if vv.sum() > 0 else closes_full[gi]
                row["vwap_dist"] = round((closes_full[gi] - vwap) / vwap * 100, 3) if vwap > 0 else 0.0
            else:
                row["trend_intraday"] = 0.0
                row["vwap_dist"] = 0.0
            row["quality_pass"] = quality_at.get(s.id, 1)
            row["f4_has_consol"] = 1 if getattr(s, "f4_has_consol", False) else 0
            rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candles", "-n", type=int, default=20000)
    ap.add_argument("--step", type=int, default=100)
    ap.add_argument("--score-floor", type=int, default=40)
    ap.add_argument("--max-symbols", type=int, default=None)
    ap.add_argument("--perp", action="store_true",
                    help="Build on USDT perpetuals (BASE/USDT:USDT) with funding cost")
    ap.add_argument("--funding", type=float, default=0.01)
    ap.add_argument("--extra-symbols", default=None,
                    help="Comma-separated coins to ADD to the default set (e.g. scanner movers)")
    ap.add_argument("--symbols", default=None,
                    help="Comma-separated symbols to REPLACE the default universe")
    ap.add_argument("--out", default="ml_dataset.csv", help="Output CSV filename")
    ap.add_argument("--enable-f1", action="store_true",
                    help="Enable F1 setups (2 levels + consolidation, no sweep) for testing")
    ap.add_argument("--no-cache", action="store_true",
                    help="Disable the local candle cache (re-download everything)")
    ap.add_argument("--f1-mgmt", action="store_true",
                    help="Apply Mark-style F1 management (early breakeven exit)")
    ap.add_argument("--f1-retest", action="store_true",
                    help="F1 entry on the retest-that-holds instead of the breakout candle")
    ap.add_argument("--sl-offset", type=float, default=None,
                    help="Override sl_atr_offset_mult (stop buffer in ATR; default 0.1)")
    ap.add_argument("--trail", type=float, default=None,
                    help="Enable chandelier trailing stop at this ATR multiple (e.g. 3.0)")
    ap.add_argument("--be-lock", type=float, default=None,
                    help="Mover SL tras +N R de runup y dejarlo (no trailing). Ej 5.0")
    ap.add_argument("--be-lock-to", type=float, default=0.0,
                    help="A dónde mover el SL al activar el be-lock, en R (0=breakeven, 3=asegura +3R)")
    ap.add_argument("--trail-activate", type=float, default=None,
                    help="Activar el trailing solo tras +N R de runup (def 1.0; tardío = 5/6)")
    ap.add_argument("--no-quality", action="store_true",
                    help="Bypass the chart-quality filter (tag each trade with quality_pass 1/0)")
    ap.add_argument("--partial", default=None,
                    help="Partial TP: 'frac,size' e.g. '0.5,0.5' (toma size en frac del camino al TP)")
    ap.add_argument("--f4-consol", action="store_true",
                    help="F4 solo si hubo consolidación previa cerca del nivel (criterio Mark)")
    ap.add_argument("--stale", type=int, default=None,
                    help="Override stale_candles (velas sin avance antes de salir; default 30)")
    ap.add_argument("--timeframes", default=None,
                    help="Coma-separados, sobrescribe TIMEFRAMES (e.g. '1m,5m,15m')")
    ap.add_argument("--trend-hours", type=float, default=None,
                    help="Ventana en horas del trend gate (default 24; prueba 12/6)")
    ap.add_argument("--trend-block", type=float, default=None,
                    help="Override trend_block_pct; pon 999 para DESACTIVAR el gate")
    args = ap.parse_args()
    _fetch = fetch_ohlcv if args.no_cache else fetch_ohlcv_cached

    base = TFZConfig()
    base.score_minimo = args.score_floor
    base.bear_score_minimo = args.score_floor
    if args.enable_f1:
        base.enable_f1 = True
    if args.f1_mgmt:
        base.f1_mgmt = True
    if args.f1_retest:
        base.f1_retest_entry = True
    if args.sl_offset is not None:
        base.sl_atr_offset_mult = args.sl_offset
    if args.partial is not None:
        f, s = args.partial.split(",")
        base.partial_enabled = True
        base.partial_frac = float(f)
        base.partial_size = float(s)
    if args.f4_consol:
        base.f4_require_consol = True
    if args.stale is not None:
        base.stale_candles = args.stale
    if args.trend_hours is not None:
        base.trend_lookback_hours = args.trend_hours
    if args.trend_block is not None:
        base.trend_block_pct = args.trend_block
    if args.trail is not None:
        base.trail_enabled = True
        base.trail_atr_mult = args.trail
    if args.trail_activate is not None:
        base.trail_activate_r = args.trail_activate
    if args.be_lock is not None:
        base.be_lock_runup_r = args.be_lock
        base.be_lock_to_r = args.be_lock_to
    if args.perp:
        base.funding_pct_per_8h = args.funding
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
    else:
        symbols = SYMBOLS[:args.max_symbols] if args.max_symbols else list(SYMBOLS)
    if args.extra_symbols:
        symbols = symbols + [s.strip() for s in args.extra_symbols.split(",")]
    if args.perp:
        symbols = [s + ":USDT" if s.endswith("/USDT") and not s.endswith(":USDT") else s
                   for s in symbols]

    out = os.path.join(os.path.dirname(__file__), args.out)
    cols = FEATURES + ["trend_intraday", "vwap_dist", "quality_pass", "f4_has_consol", "pnl_pct", "win", "symbol", "timeframe", "entry_ts"]
    timeframes = [t.strip() for t in args.timeframes.split(",")] if args.timeframes else list(TIMEFRAMES)
    n = len(symbols) * len(timeframes)
    total_rows = 0
    i = 0

    print(f"Building ML dataset: {len(symbols)} symbols x {len(timeframes)} TF {timeframes}, "
          f"floor {args.score_floor}, step {args.step}")
    print(f"Started: {datetime.now().strftime('%H:%M:%S')}")

    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for symbol in symbols:
            for tf in timeframes:
                i += 1
                tf_cfg = config_for_timeframe(base, tf)
                try:
                    df = _fetch(symbol, tf, limit=args.candles, config=tf_cfg)
                except Exception as e:
                    print(f"[{i}/{n}] {symbol} {tf} ERROR: {e}")
                    continue
                if len(df) < 500:
                    print(f"[{i}/{n}] {symbol} {tf} insufficient ({len(df)})")
                    continue
                rows = collect(df, symbol, tf, tf_cfg, args.step, bypass_quality=args.no_quality)
                for row in rows:
                    writer.writerow(row)
                total_rows += len(rows)
                f.flush()
                print(f"[{i}/{n}] {symbol:12s} {tf:>3s} | {len(rows):4d} trades | total {total_rows}")

    print(f"\nSaved {total_rows} rows -> {out}")
    print(f"Finished: {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
