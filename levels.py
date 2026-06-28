import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from itertools import combinations
from swings import SwingPoint
from config import TFZConfig


@dataclass
class HorizontalLevel:
    price: float
    touches: int
    first_touch_idx: int
    last_touch_idx: int
    side: str  # "above" or "below"
    is_equal_hl: bool = False
    score: float = 0.0
    swing_indices: List[int] = field(default_factory=list)


@dataclass
class DiagonalLevel:
    slope: float  # price per candle
    intercept: float
    touches: int
    first_idx: int
    last_idx: int
    side: str
    touch_indices: List[int] = field(default_factory=list)
    score: float = 0.0

    def price_at(self, index: int) -> float:
        return self.slope * index + self.intercept


def _cluster_swings(swings: List[SwingPoint], tol: float) -> List[List[SwingPoint]]:
    if not swings:
        return []

    sorted_sw = sorted(swings, key=lambda s: s.price)
    clusters: List[List[SwingPoint]] = [[sorted_sw[0]]]

    for sw in sorted_sw[1:]:
        cluster_median = np.median([s.price for s in clusters[-1]])
        dist = abs(sw.price - cluster_median) / min(sw.price, cluster_median)
        if dist <= tol:
            clusters[-1].append(sw)
        else:
            clusters.append([sw])

    return clusters


def detect_horizontal_levels(
    swings: List[SwingPoint],
    current_price: float,
    cfg: TFZConfig = None,
    total_candles: int = 0,
) -> List[HorizontalLevel]:
    cfg = cfg or TFZConfig()

    highs = [s for s in swings if s.type == "high"]
    lows = [s for s in swings if s.type == "low"]

    levels: List[HorizontalLevel] = []

    for swing_group, side_default in [(highs, "above"), (lows, "below")]:
        clusters = _cluster_swings(swing_group, cfg.cluster_tol)

        for cluster in clusters:
            touches = len(cluster)
            if touches < cfg.min_touches:
                continue

            prices = [s.price for s in cluster]
            level_price = float(np.median(prices))
            first_idx = min(s.index for s in cluster)
            last_idx = max(s.index for s in cluster)
            age = last_idx - first_idx

            if age < cfg.min_level_age and touches < 3:
                continue

            side = "above" if level_price > current_price else "below"

            is_equal = False
            if touches >= 2:
                max_dist = max(
                    abs(p - level_price) / level_price for p in prices
                )
                if max_dist <= cfg.equal_hl_tol:
                    is_equal = True

            # Scoring (spec §3.3)
            touch_score = min(touches, 4) * 25
            age_factor = min(age / 50, 1.0) if age > 0 else 0
            age_score = age_factor * 15
            recency = 1.0 if (total_candles - last_idx) <= 30 else 0.5
            recency_score = recency * 10
            score = touch_score + age_score + recency_score

            if is_equal:
                score += cfg.equal_hl_bonus

            score = min(score, 100)

            levels.append(HorizontalLevel(
                price=level_price,
                touches=touches,
                first_touch_idx=first_idx,
                last_touch_idx=last_idx,
                side=side,
                is_equal_hl=is_equal,
                score=score,
                swing_indices=[s.index for s in cluster],
            ))

    levels.sort(key=lambda l: l.score, reverse=True)
    return levels


def detect_diagonal_levels(
    swings: List[SwingPoint],
    current_price: float,
    cfg: TFZConfig = None,
) -> List[DiagonalLevel]:
    cfg = cfg or TFZConfig()

    highs = [s for s in swings if s.type == "high"]
    lows = [s for s in swings if s.type == "low"]

    diagonals: List[DiagonalLevel] = []

    for swing_group, side_type in [(highs, "above"), (lows, "below")]:
        if len(swing_group) < 3:
            continue

        for a, b in combinations(swing_group, 2):
            if a.index == b.index:
                continue
            if a.index > b.index:
                a, b = b, a

            dx = b.index - a.index
            if dx == 0:
                continue
            slope = (b.price - a.price) / dx
            intercept = a.price - slope * a.index

            avg_price = (a.price + b.price) / 2
            total_span = b.index - a.index
            if total_span == 0 or avg_price == 0:
                continue
            slope_pct = abs(slope) * total_span / avg_price * 100
            if slope_pct > cfg.max_slope_pct:
                continue

            touch_indices = [a.index, b.index]
            for c in swing_group:
                if c.index in (a.index, b.index):
                    continue
                expected = slope * c.index + intercept
                if expected == 0:
                    continue
                dist = abs(c.price - expected) / expected
                if dist <= cfg.tol_diagonal:
                    touch_indices.append(c.index)

            total_touches = len(touch_indices)
            if total_touches < 3:
                continue

            first_idx = min(touch_indices)
            last_idx = max(touch_indices)
            line_length = last_idx - first_idx

            side = side_type
            mid_price = slope * ((first_idx + last_idx) / 2) + intercept
            if mid_price < current_price:
                side = "below"
            elif mid_price > current_price:
                side = "above"

            # Scoring (spec §4.4)
            touch_s = min(total_touches, 5) * 20
            flatness = max(0, 1.0 - slope_pct / cfg.max_slope_pct) * 20
            length_s = min(line_length / 50, 1.0) * 10
            score = min(touch_s + flatness + length_s, 100)

            diagonals.append(DiagonalLevel(
                slope=slope,
                intercept=intercept,
                touches=total_touches,
                first_idx=first_idx,
                last_idx=last_idx,
                side=side,
                touch_indices=sorted(touch_indices),
                score=score,
            ))

    # Deduplicate similar trendlines
    diagonals.sort(key=lambda d: d.score, reverse=True)
    filtered: List[DiagonalLevel] = []
    for d in diagonals:
        is_dup = False
        for existing in filtered:
            price_diff = abs(d.price_at(d.last_idx) - existing.price_at(d.last_idx))
            if existing.price_at(d.last_idx) != 0:
                if price_diff / existing.price_at(d.last_idx) < cfg.tol_diagonal:
                    is_dup = True
                    break
        if not is_dup:
            filtered.append(d)

    return filtered


def filter_levels_by_distance(
    levels: List[HorizontalLevel],
    max_dist_pct: float,
) -> List[List[HorizontalLevel]]:
    if len(levels) < 2:
        return []

    sorted_levels = sorted(levels, key=lambda l: l.price)

    # Build groups where the total span (first to last) stays within max_dist_pct
    groups: List[List[HorizontalLevel]] = []

    for i in range(len(sorted_levels)):
        group = [sorted_levels[i]]
        for j in range(i + 1, len(sorted_levels)):
            span = (sorted_levels[j].price - sorted_levels[i].price) / sorted_levels[i].price * 100
            if span <= max_dist_pct:
                group.append(sorted_levels[j])
            else:
                break
        if len(group) >= 2:
            groups.append(group)

    # Deduplicate: remove groups that are strict subsets of larger groups
    groups.sort(key=lambda g: len(g), reverse=True)
    final: List[List[HorizontalLevel]] = []
    seen_sets: List[set] = []
    for g in groups:
        g_set = {l.price for l in g}
        is_subset = any(g_set <= s for s in seen_sets)
        if not is_subset:
            final.append(g)
            seen_sets.append(g_set)

    return final
