import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List
from config import TFZConfig


@dataclass
class SwingPoint:
    index: int
    price: float
    timestamp: pd.Timestamp
    type: str  # "high" or "low"


def compute_atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    tr = np.zeros(len(df))
    tr[0] = high[0] - low[0]
    for i in range(1, len(df)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )

    atr = np.zeros(len(df))
    atr[:period] = np.nan
    atr[period] = np.mean(tr[1 : period + 1])
    for i in range(period + 1, len(df)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


def compute_trend_strength(
    df: pd.DataFrame,
    timeframe: str = "15m",
    idx: int = None,
    hours: float = 4.0,
) -> float:
    """Tendencia RECIENTE: pendiente de regresión lineal sobre las últimas `hours`
    horas de cierres, como % implícito a lo largo de la recta. Positive = sube,
    negative = baja.

    Antes era un 2-puntos (precio de ahora vs el de hace 24h) que ignoraba la forma
    intermedia: una moneda que pumpeaba y luego se desplomaba salía "alcista" porque
    el punto de partida estaba bajo. Ahora la regresión capta la DIRECCIÓN real visible
    (el bot "ve" lo que ve el ojo en el gráfico) y la ventana es reciente (def 4h, no 24h).
    """
    closes = df["close"].values
    if idx is None:
        idx = len(closes) - 1
    if idx <= 1:
        return 0.0

    candles_per_hour = {
        "1m": 60, "3m": 20, "5m": 12, "15m": 4,
        "30m": 2, "1h": 1, "4h": 0.25, "1d": 1/24,
    }
    lookback = max(2, int(candles_per_hour.get(timeframe, 4) * hours))
    start = max(0, idx - lookback)
    seg = closes[start:idx + 1]
    if len(seg) < 2 or seg[0] <= 0:
        return 0.0
    x = np.arange(len(seg))
    slope = np.polyfit(x, seg, 1)[0]            # precio por vela (recta de mejor ajuste)
    return float(slope * len(seg) / seg[0] * 100)  # % implícito a lo largo de la ventana


def detect_swings(df: pd.DataFrame, cfg: TFZConfig = None) -> List[SwingPoint]:
    cfg = cfg or TFZConfig()
    n = cfg.swing_order
    highs = df["high"].values
    lows = df["low"].values
    timestamps = df["timestamp"].values

    atr = compute_atr(df, cfg.atr_period)
    noise_threshold = atr * cfg.noise_threshold_mult

    swings: List[SwingPoint] = []
    last_sh_price = None
    last_sl_price = None

    for i in range(n, len(df) - n):
        window_high = highs[i - n : i + n + 1]
        window_low = lows[i - n : i + n + 1]

        is_sh = highs[i] == np.max(window_high)
        is_sl = lows[i] == np.min(window_low)

        nt = noise_threshold[i] if not np.isnan(noise_threshold[i]) else 0

        if is_sh:
            if last_sh_price is None or abs(highs[i] - last_sh_price) >= nt:
                if not swings or (i - swings[-1].index >= cfg.min_swing_separation
                                  or swings[-1].type != "high"):
                    sp = SwingPoint(
                        index=i,
                        price=highs[i],
                        timestamp=pd.Timestamp(timestamps[i]),
                        type="high",
                    )
                    swings.append(sp)
                    last_sh_price = highs[i]

        if is_sl:
            if last_sl_price is None or abs(lows[i] - last_sl_price) >= nt:
                if not swings or (i - swings[-1].index >= cfg.min_swing_separation
                                  or swings[-1].type != "low"):
                    sp = SwingPoint(
                        index=i,
                        price=lows[i],
                        timestamp=pd.Timestamp(timestamps[i]),
                        type="low",
                    )
                    swings.append(sp)
                    last_sl_price = lows[i]

    return swings


def get_swing_highs(swings: List[SwingPoint]) -> List[SwingPoint]:
    return [s for s in swings if s.type == "high"]


def get_swing_lows(swings: List[SwingPoint]) -> List[SwingPoint]:
    return [s for s in swings if s.type == "low"]
