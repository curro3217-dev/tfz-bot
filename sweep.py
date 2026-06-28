import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List
from levels import HorizontalLevel
from config import TFZConfig
from swings import compute_atr


@dataclass
class LiquiditySweep:
    level_price: float
    sweep_idx: int  # candle that broke the level
    reclaim_idx: int  # candle that reclaimed
    sweep_type: str  # "low_sweep" (bearish sweep) or "high_sweep" (bullish sweep)
    depth_pct: float
    candles_to_reclaim: int
    has_continuation: bool
    score: float = 0.0
    vol_ratio: float = 1.0          # volumen de la vela del sweep / media reciente (footprint)
    reclaim_body_atr: float = 0.0   # cuerpo de la vela de reclaim / ATR (fuerza/desplazamiento)


def detect_sweeps(
    df: pd.DataFrame,
    levels: List[HorizontalLevel],
    cfg: TFZConfig = None,
) -> List[LiquiditySweep]:
    cfg = cfg or TFZConfig()
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    opens = df["open"].values
    vols = df["volume"].values
    atr = compute_atr(df, cfg.atr_period)

    sweeps: List[LiquiditySweep] = []

    for level in levels:
        if level.side == "below":
            _detect_low_sweeps(
                highs, lows, closes, opens, vols, atr, level, cfg, sweeps
            )
        else:
            _detect_high_sweeps(
                highs, lows, closes, opens, vols, atr, level, cfg, sweeps
            )

    sweeps.sort(key=lambda s: s.score, reverse=True)
    return sweeps


def _sweep_quality(i, reclaim_idx, opens, closes, vols, atr):
    """Volumen relativo de la vela del sweep + fuerza (desplazamiento) del reclaim."""
    lo = max(0, i - 30)
    base = float(np.mean(vols[lo:i])) if i > lo else 0.0
    vol_ratio = float(vols[i] / base) if base > 0 else 1.0
    a = atr[reclaim_idx] if reclaim_idx < len(atr) and not np.isnan(atr[reclaim_idx]) else 0.0
    body = abs(closes[reclaim_idx] - opens[reclaim_idx])
    reclaim_body_atr = float(body / a) if a > 0 else 0.0
    return round(vol_ratio, 3), round(reclaim_body_atr, 3)


def _detect_low_sweeps(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    opens: np.ndarray,
    vols: np.ndarray,
    atr: np.ndarray,
    level: HorizontalLevel,
    cfg: TFZConfig,
    out: List[LiquiditySweep],
):
    price = level.price
    search_start = level.last_touch_idx + 1

    for i in range(search_start, len(lows)):
        if lows[i] >= price:
            continue

        depth_pct = (price - lows[i]) / price * 100
        if depth_pct > cfg.max_sweep_depth:
            continue

        reclaim_idx = None
        for k in range(i, min(i + cfg.reclaim_window + 1, len(closes))):
            if closes[k] > price:
                reclaim_idx = k
                break

        if reclaim_idx is None:
            continue

        has_continuation = False
        for j in range(reclaim_idx + 1, min(reclaim_idx + cfg.continuation_window + 1, len(highs))):
            if highs[j] > highs[i]:
                has_continuation = True
                break

        candles_to_reclaim = reclaim_idx - i

        speed = 1.0 - (candles_to_reclaim / cfg.max_sweep_candles) if cfg.max_sweep_candles > 0 else 0
        speed = max(0, speed)
        depth_q = 1.0 - (depth_pct / cfg.max_sweep_depth) if cfg.max_sweep_depth > 0 else 0
        depth_q = max(0, depth_q)
        cont_score = 1.0 if has_continuation else 0.0

        score = (speed * 30) + (depth_q * 30) + (cont_score * 40)
        score = min(score, 100)

        vol_ratio, reclaim_body_atr = _sweep_quality(i, reclaim_idx, opens, closes, vols, atr)
        out.append(LiquiditySweep(
            level_price=price,
            sweep_idx=i,
            reclaim_idx=reclaim_idx,
            sweep_type="low_sweep",
            depth_pct=depth_pct,
            candles_to_reclaim=candles_to_reclaim,
            has_continuation=has_continuation,
            score=score,
            vol_ratio=vol_ratio,
            reclaim_body_atr=reclaim_body_atr,
        ))
        break  # one sweep per level


def _detect_high_sweeps(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    opens: np.ndarray,
    vols: np.ndarray,
    atr: np.ndarray,
    level: HorizontalLevel,
    cfg: TFZConfig,
    out: List[LiquiditySweep],
):
    price = level.price
    search_start = level.last_touch_idx + 1

    for i in range(search_start, len(highs)):
        if highs[i] <= price:
            continue

        depth_pct = (highs[i] - price) / price * 100
        if depth_pct > cfg.max_sweep_depth:
            continue

        reclaim_idx = None
        for k in range(i, min(i + cfg.reclaim_window + 1, len(closes))):
            if closes[k] < price:
                reclaim_idx = k
                break

        if reclaim_idx is None:
            continue

        has_continuation = False
        for j in range(reclaim_idx + 1, min(reclaim_idx + cfg.continuation_window + 1, len(lows))):
            if lows[j] < lows[i]:
                has_continuation = True
                break

        candles_to_reclaim = reclaim_idx - i

        speed = 1.0 - (candles_to_reclaim / cfg.max_sweep_candles) if cfg.max_sweep_candles > 0 else 0
        speed = max(0, speed)
        depth_q = 1.0 - (depth_pct / cfg.max_sweep_depth) if cfg.max_sweep_depth > 0 else 0
        depth_q = max(0, depth_q)
        cont_score = 1.0 if has_continuation else 0.0

        score = (speed * 30) + (depth_q * 30) + (cont_score * 40)
        score = min(score, 100)

        vol_ratio, reclaim_body_atr = _sweep_quality(i, reclaim_idx, opens, closes, vols, atr)
        out.append(LiquiditySweep(
            level_price=price,
            sweep_idx=i,
            reclaim_idx=reclaim_idx,
            sweep_type="high_sweep",
            depth_pct=depth_pct,
            candles_to_reclaim=candles_to_reclaim,
            has_continuation=has_continuation,
            score=score,
            vol_ratio=vol_ratio,
            reclaim_body_atr=reclaim_body_atr,
        ))
        break
