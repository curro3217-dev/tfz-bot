import uuid
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from formations import Formation
from levels import HorizontalLevel
from swings import compute_atr
from config import TFZConfig


@dataclass
class Signal:
    id: str
    timestamp: pd.Timestamp
    symbol: str
    timeframe: str
    direction: str  # "long" or "short"
    formation_type: str

    entry_price: float
    stop_loss: float
    take_profit: float
    risk_pct: float
    rr_ratio: float

    levels: List[Dict] = field(default_factory=list)
    consolidation: Optional[Dict] = None
    sweep: Optional[Dict] = None

    score_breakdown: Dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0

    trigger_idx: int = 0
    trigger_body_atr: float = 0.0  # cuerpo de la vela de entrada / ATR (fuerza del breakout/reclaim)
    f4_has_consol: bool = False    # F4: hubo consolidación previa cerca del nivel (criterio Mark)


def generate_signals(
    df: pd.DataFrame,
    formations: List[Formation],
    symbol: str,
    timeframe: str,
    cfg: TFZConfig = None,
    trend_strength: float = 0.0,  # from coin selector: % move in 1d/7d
    is_bear_market: bool = False,
) -> List[Signal]:
    cfg = cfg or TFZConfig()
    atr = compute_atr(df, cfg.atr_period)
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    opens = df["open"].values
    vols = df["volume"].values if "volume" in df.columns else np.ones(len(closes))

    signals: List[Signal] = []

    for formation in formations:
        consol = formation.consolidation

        # Find trigger candle
        trigger_idx = _find_trigger(df, formation, cfg)
        if trigger_idx is None:
            continue

        # FILTRO RVOL (volumen relativo, idea de Warrior Trading): vol de la vela trigger
        # / media de las 20 anteriores. Validado OOS: en 1m exigir >=2 casi DOBLA la
        # expectancy (+2.7->+4.4%) y sube aciertos a 62%; en 15m >=1.5 mejora leve; en 5m
        # no aporta (rvol_min=0). Limpia las rupturas en volumen bajo (ruido). Por TF.
        if getattr(cfg, "rvol_min", 0.0) > 0 and trigger_idx >= 20:
            _vbm = vols[trigger_idx - 20:trigger_idx].mean()
            _rvol = (vols[trigger_idx] / _vbm) if _vbm > 0 else 0.0
            if _rvol < cfg.rvol_min:
                continue

        entry_price = closes[trigger_idx]
        current_atr = atr[trigger_idx] if not np.isnan(atr[trigger_idx]) else atr[~np.isnan(atr)][-1]
        sl_offset = current_atr * cfg.sl_atr_offset_mult

        # Stop-loss
        if formation.direction == "long":
            if consol:
                stop_loss = consol.range_low - sl_offset
            elif formation.sweep:
                stop_loss = lows[formation.sweep.sweep_idx] - sl_offset
            else:
                stop_loss = entry_price * (1 - cfg.max_risk_pct / 100)
        else:
            if consol:
                stop_loss = consol.range_high + sl_offset
            elif formation.sweep:
                stop_loss = highs[formation.sweep.sweep_idx] + sl_offset
            else:
                stop_loss = entry_price * (1 + cfg.max_risk_pct / 100)

        # Risk check
        risk_pct = abs(entry_price - stop_loss) / entry_price * 100
        max_risk = cfg.bear_max_risk_pct if is_bear_market else cfg.max_risk_pct
        if risk_pct > max_risk:
            continue

        # Take-profit
        take_profit = _compute_tp(formation, entry_price, stop_loss, cfg, is_bear_market)
        if take_profit is None:
            continue

        # R:R check
        rr = abs(take_profit - entry_price) / abs(entry_price - stop_loss) if abs(entry_price - stop_loss) > 0 else 0
        if rr < cfg.min_rr:
            continue

        # Trend gate (spec §9.2/§13): never trade against a clear trend. Applies
        # to ALL formations, including F4 -- a long in a downtrend / short in an
        # uptrend is a counter-trend loser (validated on data). Ranging market
        # (|trend| < trend_block_pct) allows either direction.
        if abs(trend_strength) >= cfg.trend_block_pct:
            counter_trend = (
                (formation.direction == "long" and trend_strength < 0)
                or (formation.direction == "short" and trend_strength > 0)
            )
            if counter_trend:
                continue

        # VWAP anclado ~24h: premiar entradas alineadas (long sobre VWAP / short bajo).
        _nv = {"1m": 1440, "5m": 288, "15m": 96, "1h": 24}.get(timeframe, 96)
        _a = max(0, trigger_idx - _nv)
        _tp = (highs[_a:trigger_idx + 1] + lows[_a:trigger_idx + 1] + closes[_a:trigger_idx + 1]) / 3
        _vv = vols[_a:trigger_idx + 1]
        _vwap = float((_tp * _vv).sum() / _vv.sum()) if _vv.sum() > 0 else closes[trigger_idx]
        vwap_dist = (closes[trigger_idx] - _vwap) / _vwap * 100 if _vwap > 0 else 0.0

        # Scoring
        score_min = cfg.bear_score_minimo if is_bear_market else cfg.score_minimo
        breakdown = _compute_score(formation, rr, trend_strength, symbol, cfg, vwap_dist)
        total = sum(breakdown.values())

        if total < score_min:
            continue

        ts = df["timestamp"].iloc[trigger_idx] if "timestamp" in df.columns else pd.Timestamp.now()
        _ta = atr[trigger_idx] if trigger_idx < len(atr) and not np.isnan(atr[trigger_idx]) else 0.0
        trigger_body_atr = round(abs(closes[trigger_idx] - opens[trigger_idx]) / _ta, 3) if _ta > 0 else 0.0

        sig = Signal(
            id=str(uuid.uuid4())[:8],
            timestamp=ts,
            symbol=symbol,
            timeframe=timeframe,
            direction=formation.direction,
            formation_type=formation.type,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_pct=round(risk_pct, 4),
            rr_ratio=round(rr, 2),
            levels=[
                {"price": l.price, "touches": l.touches, "score": round(l.score, 1)}
                for l in formation.levels
            ],
            consolidation={
                "range_high": consol.range_high,
                "range_low": consol.range_low,
                "duration": consol.duration,
                "score": round(consol.score, 1),
            } if consol else None,
            sweep={
                "type": formation.sweep.sweep_type,
                "depth_pct": round(formation.sweep.depth_pct, 3),
                "score": round(formation.sweep.score, 1),
                "vol_ratio": formation.sweep.vol_ratio,
                "reclaim_body_atr": formation.sweep.reclaim_body_atr,
            } if formation.sweep else None,
            score_breakdown=breakdown,
            total_score=round(total, 1),
            trigger_idx=trigger_idx,
            trigger_body_atr=trigger_body_atr,
            f4_has_consol=getattr(formation, "f4_has_consol", False),
        )
        signals.append(sig)

    signals.sort(key=lambda s: s.total_score, reverse=True)
    return signals


def _find_trigger(
    df: pd.DataFrame,
    formation: Formation,
    cfg: TFZConfig,
) -> Optional[int]:
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    consol = formation.consolidation

    if consol is None:
        # F4 manipulation: trigger at reclaim
        if formation.sweep:
            idx = formation.sweep.reclaim_idx
            if idx < len(closes):
                return idx
        return None

    search_start = consol.end_idx if not consol.is_active else consol.start_idx + consol.duration // 2
    rh, rl = consol.range_high, consol.range_low
    use_retest = cfg.f1_retest_entry and formation.type == "F1"

    for i in range(search_start, len(closes)):
        if formation.direction == "long" and closes[i] > rh and closes[i] > closes[i - 1]:
            if not use_retest:
                return i
            # Retest-hold: tras el breakout, el precio vuelve a tocar el nivel y
            # CIERRA por encima (aguanta). Si cierra de vuelta dentro -> falso.
            for r in range(i + 1, min(i + 1 + cfg.f1_retest_window, len(closes))):
                if closes[r] < rh:
                    break
                if lows[r] <= rh * (1 + cfg.f1_retest_tol) and closes[r] > rh:
                    return r
        elif formation.direction == "short" and closes[i] < rl and closes[i] < closes[i - 1]:
            if not use_retest:
                return i
            for r in range(i + 1, min(i + 1 + cfg.f1_retest_window, len(closes))):
                if closes[r] > rl:
                    break
                if highs[r] >= rl * (1 - cfg.f1_retest_tol) and closes[r] < rl:
                    return r

    return None


def _compute_tp(
    formation: Formation,
    entry: float,
    stop: float,
    cfg: TFZConfig,
    is_bear: bool,
) -> Optional[float]:
    if not formation.levels:
        return None

    if formation.direction == "long":
        tp_level = max(l.price for l in formation.levels)
        if tp_level <= entry:
            tp_level = entry + abs(entry - stop) * cfg.min_rr
    else:
        tp_level = min(l.price for l in formation.levels)
        if tp_level >= entry:
            tp_level = entry - abs(entry - stop) * cfg.min_rr

    if is_bear:
        dist_pct = abs(tp_level - entry) / entry * 100
        if dist_pct > cfg.bear_tp_distance:
            if formation.direction == "long":
                tp_level = entry + (tp_level - entry) * cfg.bear_tp_factor
            else:
                tp_level = entry - (entry - tp_level) * cfg.bear_tp_factor

    return tp_level


def _compute_score(
    formation: Formation,
    rr: float,
    trend_strength: float,
    symbol: str,
    cfg: TFZConfig,
    vwap_dist: float = 0.0,
) -> Dict[str, float]:

    # Trend alignment (0-20), spec §9.2/§13.
    # ALL setups (F1/F2/F3 AND F4) must go WITH the trend: counter-trend earns
    # nothing. (Clearly counter-trend signals are already blocked upstream in
    # generate_signals; this scoring just rewards trend magnitude when aligned.)
    abs_trend = abs(trend_strength)

    def _magnitude_score(t):
        if t >= 10:
            return 20
        if t >= 5:
            return 10
        return 5

    aligned = (
        (formation.direction == "long" and trend_strength > 0)
        or (formation.direction == "short" and trend_strength < 0)
    )
    if aligned:
        trend_score = _magnitude_score(abs_trend)
    elif abs_trend >= 5:
        trend_score = 0  # clearly counter-trend
    else:
        trend_score = 5  # ranging market, no strong trend either way

    # Liquidity levels (0-20)
    if formation.levels:
        avg_level_score = sum(l.score for l in formation.levels) / len(formation.levels)
        num_levels = min(len(formation.levels), 3)
        liq_score = (avg_level_score / 100 * 15) + (num_levels / 3 * 5)
    else:
        liq_score = 0

    # Consolidation (0-15)
    if formation.consolidation:
        consol_score = formation.consolidation.score / 100 * 15
    else:
        consol_score = 0

    # Sweep (0-15)
    if formation.sweep and formation.sweep.score > 60:
        sweep_score = 15
    elif formation.sweep and formation.sweep.score >= 30:
        sweep_score = 7
    else:
        sweep_score = 0

    # Cascade (0-10)
    if formation.is_cascade:
        cascade_score = min((formation.cascade_count - 1) * 10, 30)
        cascade_score = min(cascade_score, 10)
    else:
        cascade_score = 0

    # Distance quality (0-10)
    if len(formation.levels) >= 2:
        prices = sorted(l.price for l in formation.levels)
        dists = []
        for i in range(len(prices) - 1):
            d = abs(prices[i + 1] - prices[i]) / min(prices[i + 1], prices[i]) * 100
            dists.append(d)
        avg_dist = sum(dists) / len(dists)
        dist_max = cfg.get_dist_max(symbol)
        dist_score = 10 * max(0, 1.0 - avg_dist / dist_max)
    else:
        dist_score = 0

    # R:R quality (0-10)
    if rr >= 5.0:
        rr_score = 10
    elif rr >= 4.0:
        rr_score = 7
    elif rr >= 3.0:
        rr_score = 5
    else:
        rr_score = 0

    # VWAP alignment (0-8): premia long sobre VWAP / short bajo VWAP (Warrior). Suave:
    # suma puntos a los alineados sin penalizar a los contra (validado: alineados +3.91%
    # vs contra +2.47%/trade, robusto OOS).
    aligned_dist = vwap_dist if formation.direction == "long" else -vwap_dist
    vwap_score = min(max(aligned_dist, 0.0) * 2.0, 8.0)

    return {
        "trend_alignment": round(trend_score, 1),
        "liquidity_levels": round(liq_score, 1),
        "consolidation": round(consol_score, 1),
        "sweep": round(sweep_score, 1),
        "cascade_levels": round(cascade_score, 1),
        "distance_quality": round(dist_score, 1),
        "rr_quality": round(rr_score, 1),
        "vwap": round(vwap_score, 1),
    }
