"""
EXPLORACIÓN (no integrado): estrategia de reversión a la media, complemento de Mark.
Mark opera los movimientos (breakout/liquidez); esto operaría los RANGOS:
  - long  cuando el precio se estira por DEBAJO de la banda de Bollinger inferior + RSI<30
  - short cuando se estira por ENCIMA de la superior + RSI>70
  - solo en mercado NO tendencial (|trend 1d| < 5%)
  - TP = media (banda central, SMA20); SL = extremo reciente - buffer ATR
Perfil esperado: ALTO winrate, RR BAJO (~1-2) — lo contrario a Mark.

Pasa las señales por NUESTRO backtester (costes + funding) para ver si hay edge,
antes de decidir integrarla. Uso: python explore_meanrev.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests.adapters as _ra
_os = _ra.HTTPAdapter.send
def _s(self, r, **k):
    k["verify"] = False
    k.setdefault("timeout", (10, 20))
    return _os(self, r, **k)
_ra.HTTPAdapter.send = _s

import uuid
import numpy as np
import pandas as pd

from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from swings import compute_atr, compute_trend_strength
from signals import Signal
from backtester import run_backtest


def rsi(closes, period=14):
    delta = np.diff(closes, prepend=closes[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    ag = pd.Series(gain).ewm(alpha=1/period, adjust=False).mean().values
    al = pd.Series(loss).ewm(alpha=1/period, adjust=False).mean().values
    rs = np.divide(ag, al, out=np.zeros_like(ag), where=al != 0)
    return 100 - 100 / (1 + rs)


def meanrev_signals(df, symbol, tf, cfg, bb_p=20, bb_std=2.0, rsi_os=30, rsi_ob=70,
                    sl_atr=1.0, min_rr=1.0, range_max=5.0):
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    ma = pd.Series(closes).rolling(bb_p).mean().values
    sd = pd.Series(closes).rolling(bb_p).std().values
    upper = ma + bb_std * sd
    lower = ma - bb_std * sd
    r = rsi(closes, 14)
    atr = compute_atr(df, cfg.atr_period)
    sigs = []
    for i in range(bb_p + 1, len(df) - 1):
        if np.isnan(ma[i]) or np.isnan(atr[i]) or atr[i] <= 0:
            continue
        trend = compute_trend_strength(df, tf, i)
        if abs(trend) >= range_max:
            continue  # solo en rango
        # ENTRADA POR CONFIRMACIÓN: la vela anterior estuvo FUERA de la banda
        # (sobreextendida) y la actual CIERRA de vuelta dentro -> la reversión ya
        # empezó. No se cogen cuchillos cayendo.
        long_now = closes[i-1] < lower[i-1] and closes[i] >= lower[i] and r[i] < 50
        short_now = closes[i-1] > upper[i-1] and closes[i] <= upper[i] and r[i] > 50
        direction = None
        if long_now:
            direction = "long"
        elif short_now:
            direction = "short"
        if direction is None:
            continue
        entry = closes[i]
        if direction == "long":
            sl = lows[i] - sl_atr * atr[i]
            tp = ma[i]  # media
        else:
            sl = highs[i] + sl_atr * atr[i]
            tp = ma[i]
        if (direction == "long" and not (sl < entry < tp)) or \
           (direction == "short" and not (tp < entry < sl)):
            continue
        risk = abs(entry - sl) / entry * 100
        rr = abs(tp - entry) / abs(entry - sl)
        if rr < min_rr or risk > cfg.max_risk_pct:
            continue
        sigs.append(Signal(
            id=str(uuid.uuid4())[:8], timestamp=df["timestamp"].iloc[i], symbol=symbol,
            timeframe=tf, direction=direction, formation_type="MEANREV",
            entry_price=entry, stop_loss=sl, take_profit=tp,
            risk_pct=round(risk, 4), rr_ratio=round(rr, 2), trigger_idx=i,
        ))
    return sigs


def main():
    SYMS = ["AAVE", "ADA", "ATOM", "AVAX", "DOT", "INJ", "NEAR", "OP", "UNI", "SOL",
            "LINK", "SUI", "SEI", "TIA", "ENA", "ONDO", "FET", "RENDER", "CRV", "XLM"]
    base = TFZConfig()
    base.funding_pct_per_8h = 0.01
    allp = []
    for s in SYMS:
        sym = f"{s}/USDT:USDT"
        for tf in ["5m", "15m"]:
            cfg = config_for_timeframe(base, tf)
            try:
                df = fetch_ohlcv_cached(sym, tf, limit=20000, config=cfg)
            except Exception as e:
                print(f"{s} {tf} ERR {e}"); continue
            if len(df) < 500:
                continue
            sigs = meanrev_signals(df, sym, tf, cfg)
            if not sigs:
                continue
            res, _ = run_backtest(df, sigs, cfg)
            allp += [r.pnl_pct for r in res]
        print(f"  {s:7} acumulado: {len(allp)} trades")
    p = np.array(allp)
    if len(p) == 0:
        print("sin señales"); return
    print("\n=== REVERSIÓN A LA MEDIA (Bollinger+RSI en rango), neto de costes ===")
    print(f"trades   : {len(p)}")
    print(f"winrate  : {(p>0).mean()*100:.1f}%")
    print(f"expectancy: {p.mean():+.3f}% / trade")
    print(f"sumPnL   : {p.sum():.0f}%")
    print(f"avg win  : {p[p>0].mean():+.2f}%  | avg loss: {p[p<0].mean():+.2f}%")


if __name__ == "__main__":
    main()
