from dataclasses import dataclass, field
from typing import List, Optional
from levels import HorizontalLevel, DiagonalLevel, filter_levels_by_distance
from consolidation import Consolidation
from sweep import LiquiditySweep
from config import TFZConfig


@dataclass
class Formation:
    type: str  # "F1", "F2", "F3", "F4_manipulation"
    direction: str  # "long" or "short"
    levels: List[HorizontalLevel] = field(default_factory=list)
    diagonal: Optional[DiagonalLevel] = None
    consolidation: Optional[Consolidation] = None
    sweep: Optional[LiquiditySweep] = None
    is_cascade: bool = False
    cascade_count: int = 0
    score_bonus: int = 0
    f4_has_consol: bool = False  # F4: ¿hubo consolidación previa cerca del nivel? (criterio Mark)


def detect_formations(
    h_levels: List[HorizontalLevel],
    d_levels: List[DiagonalLevel],
    consolidations: List[Consolidation],
    sweeps: List[LiquiditySweep],
    current_price: float,
    current_idx: int,
    cfg: TFZConfig = None,
) -> List[Formation]:
    cfg = cfg or TFZConfig()
    formations: List[Formation] = []

    above_levels = [l for l in h_levels if l.side == "above"]
    below_levels = [l for l in h_levels if l.side == "below"]

    for direction, target_levels in [("long", above_levels), ("short", below_levels)]:
        dist_max = cfg.dist_max_altcoin
        level_groups = filter_levels_by_distance(target_levels, dist_max)

        # Also allow single strong levels as F1 candidates
        for lev in target_levels:
            if lev.score >= 60 and lev.touches >= 2:
                already_in_group = any(
                    lev in g for g in level_groups
                )
                if not already_in_group:
                    level_groups.append([lev])

        for group in level_groups:
            for consol in consolidations:
                if not _consol_aligned(consol, group, direction):
                    continue

                relevant_sweeps = _find_relevant_sweeps(
                    sweeps, consol, direction
                )

                num_levels = len(group)
                is_cascade = num_levels >= 3

                if not relevant_sweeps:
                    # F1 (spec §7.1): dos niveles + consolidación, SIN sweep.
                    # Solo si está activado el flag y hay 2+ niveles (calidad).
                    if cfg.enable_f1 and num_levels >= 2:
                        formations.append(Formation(
                            type="F1",
                            direction=direction,
                            levels=group,
                            consolidation=consol,
                            sweep=None,
                            is_cascade=is_cascade,
                            cascade_count=num_levels if is_cascade else 0,
                            score_bonus=0,  # sin bonus de sweep
                        ))
                    continue

                f = Formation(
                    type="F2" if not is_cascade else "F3",
                    direction=direction,
                    levels=group,
                    consolidation=consol,
                    sweep=relevant_sweeps[0],
                    is_cascade=is_cascade,
                    cascade_count=num_levels if is_cascade else 0,
                    score_bonus=15 + (10 if is_cascade else 0),
                )
                formations.append(f)

    # F4: Manipulation sweep + reclaim
    for sw in sweeps:
        if not sw.has_continuation:
            continue
        if sw.score < 60:
            continue

        sw_direction = "long" if sw.sweep_type == "low_sweep" else "short"
        target = above_levels if sw_direction == "long" else below_levels

        if len(target) < 1:
            continue

        # Criterio de Mark: ¿hubo consolidación cerca del nivel ANTES del barrido?
        has_consol = _has_preceding_consol(sw, consolidations, cfg)
        if cfg.f4_require_consol and not has_consol:
            continue

        formations.append(Formation(
            type="F4_manipulation",
            direction=sw_direction,
            levels=target[:3],
            sweep=sw,
            score_bonus=15,
            f4_has_consol=has_consol,
        ))

    formations.sort(key=lambda f: f.score_bonus, reverse=True)
    return formations


def _has_preceding_consol(sw, consolidations, cfg) -> bool:
    """Criterio de Mark: ¿hubo una consolidación que terminó poco antes del barrido
    (<= f4_consol_window velas) y cerca del nivel barrido? Si el precio fue directo
    a barrer sin consolidar en la zona, devuelve False."""
    for c in consolidations:
        if c.end_idx > sw.sweep_idx:
            continue
        if sw.sweep_idx - c.end_idx > cfg.f4_consol_window:
            continue
        tol = (c.range_high - c.range_low) * 0.5 + c.range_low * 0.002
        if c.range_low - tol <= sw.level_price <= c.range_high + tol:
            return True
    return False


def _consol_aligned(
    consol: Consolidation,
    levels: List[HorizontalLevel],
    direction: str,
) -> bool:
    level_prices = [l.price for l in levels]
    level_median = sorted(level_prices)[len(level_prices) // 2]

    if direction == "long":
        return consol.midpoint < level_median * 1.005
    else:
        return consol.midpoint > level_median * 0.995


def _find_relevant_sweeps(
    sweeps: List[LiquiditySweep],
    consol: Consolidation,
    direction: str,
) -> List[LiquiditySweep]:
    relevant = []
    lookback = max(50, consol.duration * 3)
    for sw in sweeps:
        if direction == "long" and sw.sweep_type == "low_sweep":
            if sw.sweep_idx <= consol.end_idx + 10 and sw.sweep_idx >= consol.start_idx - lookback:
                relevant.append(sw)
        elif direction == "short" and sw.sweep_type == "high_sweep":
            if sw.sweep_idx <= consol.end_idx + 10 and sw.sweep_idx >= consol.start_idx - lookback:
                relevant.append(sw)
    relevant.sort(key=lambda s: s.score, reverse=True)
    return relevant
