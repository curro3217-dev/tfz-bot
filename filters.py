import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List
from swings import SwingPoint
from config import TFZConfig


@dataclass
class FilterResult:
    passed: bool
    reason: str = ""
    wick_ratio_median: float = 0.0
    gap_count: int = 0
    swing_count: int = 0


def check_chart_quality(
    df: pd.DataFrame,
    swings: List[SwingPoint],
    cfg: TFZConfig = None,
) -> FilterResult:
    cfg = cfg or TFZConfig()
    lookback = min(cfg.filter_lookback, len(df))
    tail = df.iloc[-lookback:]

    # Wick ratio test (spec §14.1)
    o = tail["open"].values
    h = tail["high"].values
    lo = tail["low"].values
    c = tail["close"].values

    candle_range = h - lo
    body = np.abs(c - o)
    safe_range = np.where(candle_range > 0, candle_range, np.nan)
    wick_ratio = np.where(
        np.isnan(safe_range), 0, (candle_range - body) / safe_range
    )
    wick_median = float(np.nanmedian(wick_ratio))

    if wick_median > cfg.wick_ratio_max:
        return FilterResult(
            passed=False,
            reason=f"Excessive wicks: median wick ratio {wick_median:.2f} > {cfg.wick_ratio_max}",
            wick_ratio_median=wick_median,
        )

    # Gap test (spec §14.1)
    closes_prev = tail["close"].values[:-1]
    opens_next = tail["open"].values[1:]
    gaps = np.abs(opens_next - closes_prev) / np.where(closes_prev > 0, closes_prev, 1) * 100
    gap_count = int(np.sum(gaps > cfg.gap_threshold))

    if gap_count > cfg.max_gap_count:
        return FilterResult(
            passed=False,
            reason=f"Too many gaps: {gap_count} > {cfg.max_gap_count}",
            wick_ratio_median=wick_median,
            gap_count=gap_count,
        )

    # Structure test (spec §14.1)
    start_idx = len(df) - 100 if len(df) > 100 else 0
    recent_swings = [s for s in swings if s.index >= start_idx]
    sh_count = sum(1 for s in recent_swings if s.type == "high")
    sl_count = sum(1 for s in recent_swings if s.type == "low")

    if sh_count < cfg.min_swings_required and sl_count < cfg.min_swings_required:
        return FilterResult(
            passed=False,
            reason=f"Insufficient structure: {sh_count} highs, {sl_count} lows (min {cfg.min_swings_required})",
            wick_ratio_median=wick_median,
            gap_count=gap_count,
            swing_count=sh_count + sl_count,
        )

    return FilterResult(
        passed=True,
        wick_ratio_median=wick_median,
        gap_count=gap_count,
        swing_count=sh_count + sl_count,
    )


def check_pullback_distance(
    current_price: float,
    level_price: float,
    cfg: TFZConfig = None,
) -> bool:
    cfg = cfg or TFZConfig()
    dist = abs(current_price - level_price) / current_price * 100
    return dist <= cfg.pullback_max


def check_sharp_dump(
    df: pd.DataFrame,
    level_price: float,
    lookback: int = 10,
    dump_threshold: float = 10.0,
) -> bool:
    if len(df) < lookback:
        return False
    tail = df.iloc[-lookback:]
    high_near_level = float(tail["high"].max())
    low_after = float(tail["low"].min())

    if high_near_level == 0:
        return False

    drop_pct = (high_near_level - low_after) / high_near_level * 100
    if drop_pct > dump_threshold and high_near_level >= level_price * 0.99:
        return True
    return False
