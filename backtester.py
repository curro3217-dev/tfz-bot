import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from signals import Signal
from swings import compute_atr
from config import TFZConfig


@dataclass
class TradeResult:
    signal_id: str
    exit_price: float
    exit_reason: str  # "tp_hit", "sl_hit", "breakeven", "stale", "counter_sweep"
    exit_idx: int
    pnl_pct: float
    duration_candles: int
    max_drawdown_pct: float
    max_runup_pct: float
    moved_to_breakeven: bool = False
    breakeven_at_candle: int = 0


@dataclass
class BacktestMetrics:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakevens: int = 0
    win_rate: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_rr_actual: float = 0.0
    avg_duration: float = 0.0
    total_pnl_pct: float = 0.0
    sharpe_ratio: float = 0.0

    by_formation: Dict[str, Dict] = field(default_factory=dict)
    by_score_range: Dict[str, Dict] = field(default_factory=dict)
    by_direction: Dict[str, Dict] = field(default_factory=dict)
    by_timeframe: Dict[str, Dict] = field(default_factory=dict)
    by_sweep: Dict[str, Dict] = field(default_factory=dict)


def run_backtest(
    df: pd.DataFrame,
    signals: List[Signal],
    cfg: TFZConfig = None,
) -> tuple[List[TradeResult], BacktestMetrics]:
    cfg = cfg or TFZConfig()
    results: List[TradeResult] = []

    # Round-trip cost: commission + slippage on entry AND exit (2 sides each).
    total_cost = (cfg.commission_pct + cfg.slippage_pct) * 2
    _tf_min = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60}

    for sig in signals:
        result = _simulate_trade(df, sig, cfg)
        if result:
            cost = total_cost
            # Perp funding: paid roughly every 8h of holding time.
            if cfg.funding_pct_per_8h > 0:
                hours = result.duration_candles * _tf_min.get(sig.timeframe, 15) / 60.0
                cost += cfg.funding_pct_per_8h * (hours / 8.0)
            result.pnl_pct = round(result.pnl_pct - cost, 4)
            results.append(result)

    metrics = _compute_metrics(signals, results)
    return results, metrics


def _simulate_trade(
    df: pd.DataFrame,
    sig: Signal,
    cfg: TFZConfig,
) -> Optional[TradeResult]:
    start = sig.trigger_idx + 1
    if start >= len(df):
        return None

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    atr = compute_atr(df, cfg.atr_period)

    entry = sig.entry_price
    sl = sig.stop_loss
    tp = sig.take_profit
    current_sl = sl
    moved_be = False
    be_candle = 0

    max_dd = 0.0
    max_runup = 0.0
    peak_high = entry  # máximo a favor (long) para el trailing
    peak_low = entry   # mínimo a favor (short) para el trailing

    # Parcial: estado [tomado?, contribución del parcial en %]. _pf mezcla el PnL
    # final: si se tomó parcial, = contrib_parcial + pm_resto*(1-size); si no, = pm.
    _ps = [False, 0.0]
    if cfg.partial_enabled:
        if sig.direction == "long":
            partial_level = entry + cfg.partial_frac * (tp - entry)
        else:
            partial_level = entry - cfg.partial_frac * (entry - tp)
    def _pf(pm):
        return (_ps[1] + pm * (1 - cfg.partial_size)) if _ps[0] else pm

    for i in range(start, min(start + 200, len(df))):
        if sig.direction == "long":
            runup = (highs[i] - entry) / entry * 100
            dd = (entry - lows[i]) / entry * 100
        else:
            runup = (entry - lows[i]) / entry * 100
            dd = (highs[i] - entry) / entry * 100

        max_runup = max(max_runup, runup)
        max_dd = max(max_dd, dd)
        peak_high = max(peak_high, highs[i])
        peak_low = min(peak_low, lows[i])

        # Toma de beneficios PARCIAL: al alcanzar partial_level, banca partial_size
        # de la posición y mueve el stop del resto a breakeven.
        if cfg.partial_enabled and not _ps[0]:
            hit = (sig.direction == "long" and highs[i] >= partial_level) or \
                  (sig.direction == "short" and lows[i] <= partial_level)
            if hit:
                pm_p = (partial_level - entry) / entry * 100 if sig.direction == "long" \
                    else (entry - partial_level) / entry * 100
                _ps[0] = True
                _ps[1] = pm_p * cfg.partial_size
                current_sl = entry  # resto a breakeven
                moved_be = True

        # Check SL hit
        if sig.direction == "long" and lows[i] <= current_sl:
            exit_price = current_sl
            pnl = (exit_price - entry) / entry * 100
            reason = "breakeven" if moved_be and abs(pnl) < 0.05 else "sl_hit"
            return TradeResult(
                signal_id=sig.id, exit_price=exit_price, exit_reason=reason,
                exit_idx=i, pnl_pct=round(_pf(pnl), 4), duration_candles=i - sig.trigger_idx,
                max_drawdown_pct=round(max_dd, 4), max_runup_pct=round(max_runup, 4),
                moved_to_breakeven=moved_be, breakeven_at_candle=be_candle,
            )
        elif sig.direction == "short" and highs[i] >= current_sl:
            exit_price = current_sl
            pnl = (entry - exit_price) / entry * 100
            reason = "breakeven" if moved_be and abs(pnl) < 0.05 else "sl_hit"
            return TradeResult(
                signal_id=sig.id, exit_price=exit_price, exit_reason=reason,
                exit_idx=i, pnl_pct=round(_pf(pnl), 4), duration_candles=i - sig.trigger_idx,
                max_drawdown_pct=round(max_dd, 4), max_runup_pct=round(max_runup, 4),
                moved_to_breakeven=moved_be, breakeven_at_candle=be_candle,
            )

        # Check TP hit
        if sig.direction == "long" and highs[i] >= tp:
            exit_price = tp
            pnl = (exit_price - entry) / entry * 100
            return TradeResult(
                signal_id=sig.id, exit_price=exit_price, exit_reason="tp_hit",
                exit_idx=i, pnl_pct=round(_pf(pnl), 4), duration_candles=i - sig.trigger_idx,
                max_drawdown_pct=round(max_dd, 4), max_runup_pct=round(max_runup, 4),
                moved_to_breakeven=moved_be, breakeven_at_candle=be_candle,
            )
        elif sig.direction == "short" and lows[i] <= tp:
            exit_price = tp
            pnl = (entry - exit_price) / entry * 100
            return TradeResult(
                signal_id=sig.id, exit_price=exit_price, exit_reason="tp_hit",
                exit_idx=i, pnl_pct=round(_pf(pnl), 4), duration_candles=i - sig.trigger_idx,
                max_drawdown_pct=round(max_dd, 4), max_runup_pct=round(max_runup, 4),
                moved_to_breakeven=moved_be, breakeven_at_candle=be_candle,
            )

        # Move to breakeven logic (spec §10.3)
        if not moved_be and sig.consolidation:
            consol_rh = sig.consolidation["range_high"]
            consol_rl = sig.consolidation["range_low"]
            curr_atr = atr[i] if i < len(atr) and not np.isnan(atr[i]) else 0

            if sig.direction == "long":
                retest_zone = consol_rh + curr_atr * cfg.retest_atr_mult
                if lows[i] <= retest_zone and closes[i] > consol_rh:
                    if max_runup > 0.3:
                        current_sl = entry
                        moved_be = True
                        be_candle = i - sig.trigger_idx
            else:
                retest_zone = consol_rl - curr_atr * cfg.retest_atr_mult
                if highs[i] >= retest_zone and closes[i] < consol_rl:
                    if max_runup > 0.3:
                        current_sl = entry
                        moved_be = True
                        be_candle = i - sig.trigger_idx

        # BE-LOCK por runup: cuando el trade ya ha corrido +be_lock_runup_r R a favor,
        # mover el SL a la entrada (sin pérdida) y dejarlo ahí. NO es trailing (no sube
        # más, no toca el techo del TP gordo): solo evita que un corredor probado acabe
        # en pérdida total. 0 = desactivado.
        if (cfg.be_lock_runup_r > 0 and not moved_be
                and max_runup >= cfg.be_lock_runup_r * sig.risk_pct):
            risk_abs = abs(entry - sl)            # 1R en precio
            if sig.direction == "long":
                current_sl = entry + cfg.be_lock_to_r * risk_abs
            else:
                current_sl = entry - cfg.be_lock_to_r * risk_abs
            moved_be = True
            be_candle = i - sig.trigger_idx

        # Trailing stop (chandelier): tras +trail_activate_r R, subir el SL a
        # trail_atr_mult x ATR del máximo alcanzado; SOLO sube, nunca baja.
        if cfg.trail_enabled and max_runup >= cfg.trail_activate_r * sig.risk_pct:
            t_atr = atr[i] if i < len(atr) and not np.isnan(atr[i]) else 0
            if sig.direction == "long":
                new_sl = peak_high - cfg.trail_atr_mult * t_atr
                if new_sl > current_sl:
                    current_sl = new_sl
            else:
                new_sl = peak_low + cfg.trail_atr_mult * t_atr
                if new_sl < current_sl:
                    current_sl = new_sl

        candles_in = i - sig.trigger_idx

        # F1 management (método de Mark): si el breakout no ha funcionado en pocas
        # velas, cortar al precio actual (~breakeven) en vez de esperar el stop.
        # Convierte las pérdidas de −2% de los falsos breakouts en ~0.
        if cfg.f1_mgmt and sig.formation_type == "F1":
            if candles_in >= cfg.f1_be_candles and max_runup < cfg.f1_be_min_runup:
                exit_price = closes[i]
                pnl = (exit_price - entry) / entry * 100 if sig.direction == "long" \
                    else (entry - exit_price) / entry * 100
                return TradeResult(
                    signal_id=sig.id, exit_price=exit_price, exit_reason="f1_mgmt",
                    exit_idx=i, pnl_pct=round(_pf(pnl), 4), duration_candles=candles_in,
                    max_drawdown_pct=round(max_dd, 4), max_runup_pct=round(max_runup, 4),
                    moved_to_breakeven=moved_be, breakeven_at_candle=be_candle,
                )

        # Stale trade exit (spec §12.2)
        if candles_in >= cfg.stale_candles:
            net_progress = runup - max_dd
            if net_progress < 1.0:
                exit_price = closes[i]
                pnl = (exit_price - entry) / entry * 100 if sig.direction == "long" \
                    else (entry - exit_price) / entry * 100
                return TradeResult(
                    signal_id=sig.id, exit_price=exit_price, exit_reason="stale",
                    exit_idx=i, pnl_pct=round(_pf(pnl), 4), duration_candles=candles_in,
                    max_drawdown_pct=round(max_dd, 4), max_runup_pct=round(max_runup, 4),
                    moved_to_breakeven=moved_be, breakeven_at_candle=be_candle,
                )

    # If we reach 200 candles without resolution, close at market
    if start + 200 <= len(df):
        i = start + 199
        exit_price = closes[i]
        pnl = (exit_price - entry) / entry * 100 if sig.direction == "long" \
            else (entry - exit_price) / entry * 100
        return TradeResult(
            signal_id=sig.id, exit_price=exit_price, exit_reason="timeout",
            exit_idx=i, pnl_pct=round(_pf(pnl), 4), duration_candles=200,
            max_drawdown_pct=round(max_dd, 4), max_runup_pct=round(max_runup, 4),
            moved_to_breakeven=moved_be, breakeven_at_candle=be_candle,
        )

    return None


def _compute_metrics(
    signals: List[Signal],
    results: List[TradeResult],
) -> BacktestMetrics:
    m = BacktestMetrics()
    if not results:
        return m

    sig_map = {s.id: s for s in signals}
    pnls = [r.pnl_pct for r in results]

    m.total_trades = len(results)
    m.wins = sum(1 for p in pnls if p > 0.05)
    m.losses = sum(1 for p in pnls if p < -0.05)
    m.breakevens = m.total_trades - m.wins - m.losses
    m.win_rate = m.wins / m.total_trades * 100 if m.total_trades > 0 else 0

    win_pnls = [p for p in pnls if p > 0.05]
    loss_pnls = [p for p in pnls if p < -0.05]

    m.avg_win_pct = float(np.mean(win_pnls)) if win_pnls else 0
    m.avg_loss_pct = float(np.mean(loss_pnls)) if loss_pnls else 0

    total_gains = sum(win_pnls) if win_pnls else 0
    total_losses = abs(sum(loss_pnls)) if loss_pnls else 0
    m.profit_factor = total_gains / total_losses if total_losses > 0 else float("inf")

    m.expectancy = float(np.mean(pnls))
    m.total_pnl_pct = sum(pnls)
    m.avg_duration = float(np.mean([r.duration_candles for r in results]))

    # Max drawdown (cumulative equity curve)
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    drawdowns = peak - equity
    m.max_drawdown_pct = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0

    # Sharpe
    if len(pnls) > 1 and np.std(pnls) > 0:
        m.sharpe_ratio = float(np.mean(pnls) / np.std(pnls) * np.sqrt(len(pnls)))
    else:
        m.sharpe_ratio = 0

    # Avg actual R:R
    actual_rrs = []
    for r in results:
        sig = sig_map.get(r.signal_id)
        if sig and sig.risk_pct > 0:
            actual_rrs.append(r.pnl_pct / sig.risk_pct)
    m.avg_rr_actual = float(np.mean(actual_rrs)) if actual_rrs else 0

    # Segmentation
    m.by_formation = _segment(signals, results, lambda s: s.formation_type)
    m.by_direction = _segment(signals, results, lambda s: s.direction)
    m.by_timeframe = _segment(signals, results, lambda s: s.timeframe)
    m.by_sweep = _segment(signals, results, lambda s: "with_sweep" if s.sweep else "no_sweep")

    score_ranges = [(70, 75), (75, 80), (80, 85), (85, 90), (90, 100)]
    m.by_score_range = {}
    for lo, hi in score_ranges:
        key = f"{lo}-{hi}"
        matching_sigs = [s for s in signals if lo <= s.total_score < hi]
        matching_ids = {s.id for s in matching_sigs}
        matching_results = [r for r in results if r.signal_id in matching_ids]
        if matching_results:
            mpnls = [r.pnl_pct for r in matching_results]
            m.by_score_range[key] = {
                "trades": len(matching_results),
                "win_rate": sum(1 for p in mpnls if p > 0.05) / len(mpnls) * 100,
                "avg_pnl": float(np.mean(mpnls)),
                "total_pnl": sum(mpnls),
            }

    return m


def _segment(
    signals: List[Signal],
    results: List[TradeResult],
    key_fn,
) -> Dict[str, Dict]:
    sig_map = {s.id: s for s in signals}
    groups: Dict[str, List[float]] = {}

    for r in results:
        sig = sig_map.get(r.signal_id)
        if not sig:
            continue
        key = key_fn(sig)
        groups.setdefault(key, []).append(r.pnl_pct)

    out = {}
    for key, pnls in groups.items():
        out[key] = {
            "trades": len(pnls),
            "win_rate": sum(1 for p in pnls if p > 0.05) / len(pnls) * 100,
            "avg_pnl": round(float(np.mean(pnls)), 4),
            "total_pnl": round(sum(pnls), 4),
        }
    return out
