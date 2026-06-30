"""
Estrategia "imán de números redondos": en tendencia alcista y cerca (por debajo) de
un número redondo, comprar con objetivo = el número redondo. ¿Lo toca? ¿hay edge OOS?

Número redondo RELATIVO al precio: paso = 10^floor(log10(precio)) / 2
  precio ~70  -> paso 5   (..65,70,75..)
  precio ~1.8 -> paso 0.5 (1.5,2.0..)
  precio ~0.07-> paso 0.005
Mide winrate, expectancy y split OOS. Control incluido: mismo trade pero con objetivo
en un precio NO redondo a la misma distancia (para ver si la "redondez" aporta de verdad).
"""
import math
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from swings import compute_trend_strength

UNIVERSE = ["DOGE/USDT:USDT", "XRP/USDT:USDT", "SOL/USDT:USDT", "AVAX/USDT:USDT",
            "BNB/USDT:USDT", "NEAR/USDT:USDT", "ADA/USDT:USDT", "LINK/USDT:USDT",
            "SUI/USDT:USDT", "WLD/USDT:USDT", "AAVE/USDT:USDT", "ENA/USDT:USDT"]
TFS = ["5m", "15m"]
MAX_HOLD = 60
COST = 0.10  # % ida y vuelta

def rstep(p):
    return 10 ** math.floor(math.log10(p))   # NUMEROS ENTEROS FUERTES (10,100,1.0,0.10) -> donde SI hay iman

def near_round_above(p):
    s = rstep(p)
    L = math.ceil(p / s) * s
    if abs(L - p) < 1e-12:  # justo en el nivel -> coger el siguiente
        L += s
    return L, s

# cache de datos + tendencia precalculada
_data = {}
def load(sym, tf):
    key = (sym, tf)
    if key in _data:
        return _data[key]
    tfc = config_for_timeframe(TFZConfig(), tf)
    try:
        df = fetch_ohlcv_cached(sym, tf, limit=1000, config=tfc)
    except Exception:
        _data[key] = None; return None
    if len(df) < 250:
        _data[key] = None; return None
    trend = np.array([compute_trend_strength(df, tf, i) for i in range(len(df))])
    _data[key] = (df, trend)
    return _data[key]

def run(near_pct, sl_ratio, trend_min, control=False):
    trades = []
    for sym in UNIVERSE:
        for tf in TFS:
            d = load(sym, tf)
            if not d:
                continue
            df, trend = d
            close = df["close"].values; high = df["high"].values
            low = df["low"].values; ts = df["timestamp"].astype(str).values
            i = 200
            n = len(df)
            while i < n - 1:
                p = close[i]
                L, s = near_round_above(p)
                gap = (L - p) / p
                if 0 < gap <= near_pct and trend[i] >= trend_min:
                    entry = p
                    tp = L if not control else entry + (L - entry) * 1.37  # control: objetivo NO redondo, distancia parecida
                    reward = tp - entry
                    sl = entry - reward * sl_ratio
                    end = min(i + MAX_HOLD, n)
                    out = "timeout"; brk = end - 1
                    for j in range(i + 1, end):
                        if high[j] >= tp:
                            out = "win"; brk = j; break
                        if low[j] <= sl:
                            out = "loss"; brk = j; break
                    if out == "win":
                        pnl = (tp - entry) / entry * 100 - COST
                    elif out == "loss":
                        pnl = (sl - entry) / entry * 100 - COST
                    else:
                        pnl = (close[brk] - entry) / entry * 100 - COST
                    trades.append((sym, ts[i], out, pnl))
                    i = brk + 1
                    continue
                i += 1
    return trades

def stats(trades):
    n = len(trades)
    if n == 0:
        return "  (0 trades)"
    wins = sum(1 for t in trades if t[2] == "win")
    pnl = sum(t[3] for t in trades)
    exp = pnl / n
    # OOS: mitad antigua por simbolo
    bysym = {}
    for t in trades:
        bysym.setdefault(t[0], []).append(t)
    oos = []
    for s, ts in bysym.items():
        ts.sort(key=lambda x: x[1])
        oos += ts[:len(ts) // 2]
    oexp = (sum(t[3] for t in oos) / len(oos)) if oos else 0
    return f"  {n:4d} tr | win {100*wins/n:4.1f}% | exp {exp:+.3f}% | sum {pnl:+.0f}% | OOS exp {oexp:+.3f}%"

print("=== IMAN NUMEROS REDONDOS (long, TP=nivel redondo) ===")
for near in (0.01, 0.015, 0.02):
    for slr in (0.5, 1.0):
        for tmin in (0.0, 1.0):
            t = run(near, slr, tmin)
            print(f"near {near*100:.1f}% sl {slr} trend>={tmin}: {stats(t)}")
print("\n=== CONTROL (mismo setup, objetivo NO redondo a distancia parecida) ===")
print(f"near 1.5% sl 1.0 trend>=1.0: {stats(run(0.015, 1.0, 1.0, control=True))}")
