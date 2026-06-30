"""
Validacion del MICRO-PULLBACK (Warrior Trading): en momentum alcista, una pausa corta
(vela de maximo mas bajo) que se mantiene sobre la 9 EMA, y entrada LONG cuando la vela
siguiente rompe el maximo de la pausa. Stop = minimo de la pausa. TP = RR*riesgo.
Control: long aleatorio en tendencia con MISMO stop/RR (para ver si el patron aporta).
"""
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from swings import compute_trend_strength

UNI = open("_universe.txt").read().split(",")
TFS = ["5m", "15m", "1h"]
TREND_MIN = 1.0
MAXHOLD = 60
COST = 0.12

_c = {}
def load(sym, tf):
    if (sym, tf) not in _c:
        tfc = config_for_timeframe(TFZConfig(), tf)
        try:
            df = fetch_ohlcv_cached(sym, tf, limit=2500, config=tfc)
            tr = np.array([compute_trend_strength(df, tf, i) for i in range(len(df))]) if len(df) >= 300 else None
            _c[(sym, tf)] = (df, tr) if tr is not None else None
        except Exception:
            _c[(sym, tf)] = None
    return _c[(sym, tf)]

def sim(entry, sl, tp, high, low, close, i, n):
    end = min(i + MAXHOLD, n)
    for k in range(i + 1, end):
        if low[k] <= sl: return (sl - entry) / entry * 100 - COST
        if high[k] >= tp: return (tp - entry) / entry * 100 - COST
    return (close[end - 1] - entry) / entry * 100 - COST

def run(rr, control=False, only_tf=None):
    trades = []
    for sym in UNI:
        d = None
        for tf in (TFS if only_tf is None else [only_tf]):
            dd = load(sym, tf)
            if not dd: continue
            df, trend = dd
            close, high, low = df["close"].values, df["high"].values, df["low"].values
            ts = df["timestamp"].astype(str).values
            ema9 = pd.Series(close).ewm(span=9, adjust=False).mean().values
            n = len(df); i = 30
            while i < n - 1:
                ok = False; entry = sl = None
                if trend[i] >= TREND_MIN:
                    if not control:
                        # micro-pullback: i-1 es pausa (maximo mas bajo), sobre la 9EMA,
                        # y la vela i rompe el maximo de i-1
                        if (high[i-1] < high[i-2] and low[i-1] >= ema9[i-1]
                                and high[i] > high[i-1] and close[i-2] > close[i-5]):
                            entry = high[i-1]; sl = low[i-1]; ok = True
                    else:
                        # control: long en tendencia, stop a la misma distancia tipica (1%)
                        if i % 7 == 0:
                            entry = close[i]; sl = entry * 0.99; ok = True
                if ok and entry > sl:
                    risk = entry - sl; tp = entry + rr * risk
                    pnl = sim(entry, sl, tp, high, low, close, i, n)
                    trades.append((sym, ts[i], pnl)); i += 3; continue
                i += 1
    return trades

def rep(t, lab):
    if not t: print(f"  {lab}: 0"); return
    a = np.array([x[2] for x in t])
    bysym = {}
    for x in t: bysym.setdefault(x[0], []).append(x)
    oos = []
    for s, tt in bysym.items(): tt.sort(key=lambda z: z[1]); oos += tt[:len(tt)//2]
    oe = np.mean([x[2] for x in oos]) if oos else 0
    print(f"  {lab:20s}: {len(a):4d} tr | win {(a>0).mean()*100:4.1f}% | exp {a.mean():+.3f}% | OOS {oe:+.3f}%")

print("=== POR TEMPORALIDAD (RR 3) ===")
for tf in TFS:
    rep(run(3, only_tf=tf), f"micro-pb {tf}")
    rep(run(3, control=True, only_tf=tf), f"  control {tf}")
