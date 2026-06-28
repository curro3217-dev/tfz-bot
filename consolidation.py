import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional
from swings import compute_atr
from config import TFZConfig


@dataclass
class Consolidation:
    start_idx: int
    end_idx: int
    range_high: float
    range_low: float
    range_pct: float
    midpoint: float
    duration: int  # candles
    score: float = 0.0
    is_active: bool = False  # still consolidating at the end of data


def detect_consolidations(
    df: pd.DataFrame,
    cfg: TFZConfig = None,
    level_prices: Optional[List[float]] = None,
) -> List[Consolidation]:
    cfg = cfg or TFZConfig()

    atr_fast = _rolling_atr(df, cfg.atr_fast_period)
    atr_slow = _rolling_atr(df, cfg.atr_slow_period)

    safe_slow = np.where(atr_slow > 0, atr_slow, np.nan)
    compression = np.where(
        np.isnan(safe_slow), np.nan, atr_fast / safe_slow
    )

    consolidations: List[Consolidation] = []
    in_consol = False
    start = 0

    for i in range(cfg.atr_slow_period, len(df)):
        if np.isnan(compression[i]):
            continue

        if not in_consol and compression[i] <= cfg.compression_threshold:
            in_consol = True
            start = i
        elif in_consol and compression[i] > cfg.compression_exit:
            in_consol = False
            _try_add_consolidation(
                df, start, i, cfg, level_prices, consolidations, is_active=False
            )

    if in_consol:
        _try_add_consolidation(
            df, start, len(df) - 1, cfg, level_prices, consolidations, is_active=True
        )

    return consolidations


def _try_add_consolidation(
    df: pd.DataFrame,
    start: int,
    end: int,
    cfg: TFZConfig,
    level_prices: Optional[List[float]],
    out: List,
    is_active: bool,
):
    duration = end - start
    if duration < cfg.consolidation_min_duration:
        return

    highs = df["high"].values[start : end + 1]
    lows = df["low"].values[start : end + 1]

    range_high = float(np.max(highs))
    range_low = float(np.min(lows))

    if range_low == 0:
        return

    range_pct = (range_high - range_low) / range_low * 100

    if range_pct > cfg.consolidation_max_range:
        return
    if range_pct < cfg.consolidation_min_range:
        return

    midpoint = (range_high + range_low) / 2

    # Scoring (spec §5.3)
    duration_factor = min(duration / 30, 1.0)
    tightness_factor = max(0, 1.0 - range_pct / cfg.consolidation_max_range)

    position_factor = 0.5
    if level_prices:
        for lp in level_prices:
            dist_to_level = abs(lp - range_high) / range_high * 100 if lp > midpoint else \
                            abs(range_low - lp) / range_low * 100
            if range_pct > 0 and dist_to_level / range_pct < 2.0:
                position_factor = 1.0
                break

    score = (duration_factor * 30) + (tightness_factor * 30) + (position_factor * 40)
    score = min(score, 100)

    out.append(Consolidation(
        start_idx=start,
        end_idx=end,
        range_high=range_high,
        range_low=range_low,
        range_pct=range_pct,
        midpoint=midpoint,
        duration=duration,
        score=score,
        is_active=is_active,
    ))


def _rolling_atr(df: pd.DataFrame, period: int) -> np.ndarray:
    atr = compute_atr(df, period)
    return atr
