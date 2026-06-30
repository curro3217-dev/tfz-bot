"""
VARIANTES del numero redondo. Cuando el precio (en tendencia, acercandose por debajo)
TOCA un nivel entero, ¿que hace? Mide y opera dos variantes, redondo vs control:
  - BREAKOUT-long: entra al tocar, apuesta a que SIGUE subiendo.
  - FADE-short:    entra al tocar, apuesta a que se GIRA abajo.
Si el redondo rompe/rechaza mas que el anti-redondo -> hay edge direccional.
"""
import math
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from swings import compute_trend_strength

UNIVERSE = ["DOGE/USDT:USDT","XRP/USDT:USDT","SOL/USDT:USDT","AVAX/USDT:USDT","BNB/USDT:USDT",
            "NEAR/USDT:USDT","ADA/USDT:USDT","LINK/USDT:USDT","SUI/USDT:USDT","WLD/USDT:USDT",
            "AAVE/USDT:USDT","ENA/USDT:USDT","DOT/USDT:USDT","ATOM/USDT:USDT","INJ/USDT:USDT",
            "TIA/USDT:USDT","SEI/USDT:USDT","ARB/USDT:USDT","OP/USDT:USDT","LDO/USDT:USDT",
            "FIL/USDT:USDT","ALGO/USDT:USDT","CRV/USDT:USDT","GALA/USDT:USDT","XLM/USDT:USDT",
            "ONDO/USDT:USDT","PENDLE/USDT:USDT","WIF/USDT:USDT","JUP/USDT:USDT","RENDER/USDT:USDT"]
TFS = ["5m", "15m", "1h"]
APPROACH = 60     # velas para que se acerque y toque
POST = 30         # velas tras el toque para la variante
TREND_MIN = 1.0
NEARLO, NEARHI = 0.003, 0.012
TGT = 0.006       # objetivo/stop de la variante (0.6%)
COST = 0.10

def lvl_above(p, anti):
    s = 10 ** math.floor(math.log10(p))
    off = 0.5 * s if anti else 0.0
    return (math.floor((p - off) / s) + 1) * s + off

_c = {}
def load(sym, tf):
    if (sym,tf) in _c: return _c[(sym,tf)]
    tfc = config_for_timeframe(TFZConfig(), tf)
    try: df = fetch_ohlcv_cached(sym, tf, limit=1500, config=tfc)
    except Exception: _c[(sym,tf)]=None; return None
    if len(df) < 300: _c[(sym,tf)]=None; return None
    tr = np.array([compute_trend_strength(df, tf, i) for i in range(len(df))])
    _c[(sym,tf)] = (df, tr); return _c[(sym,tf)]

def run(anti, tgt):
    fd = []   # fade-short: (sym, ts, pnl)
    for sym in UNIVERSE:
        for tf in TFS:
            d = load(sym, tf)
            if not d: continue
            df, trend = d
            close, high, low = df["close"].values, df["high"].values, df["low"].values
            ts = df["timestamp"].astype(str).values
            n = len(df); i = 200
            while i < n - 1:
                p = close[i]
                if trend[i] >= TREND_MIN:
                    L = lvl_above(p, anti); gap = (L - p)/p
                    if NEARLO <= gap <= NEARHI:
                        tj = None
                        for j in range(i+1, min(i+APPROACH, n)):
                            if high[j] >= L: tj = j; break
                        if tj is not None:
                            e = L; end = min(tj+POST, n)
                            ft, fs = L*(1-tgt), L*(1+tgt); o=None
                            for k in range(tj+1, end):
                                if low[k]<=ft: o=(e-ft)/e*100-COST; break
                                if high[k]>=fs: o=(e-fs)/e*100-COST; break
                            if o is None: o=(e-close[end-1])/e*100-COST
                            fd.append((sym, ts[tj], o)); i = tj + 1; continue
                i += 1
    return fd

def rep(fd, lab):
    n=len(fd)
    if not n: print(f"  {lab}: 0"); return
    w=100*sum(1 for t in fd if t[2]>0)/n; e=sum(t[2] for t in fd)/n
    bysym={}
    for t in fd: bysym.setdefault(t[0],[]).append(t)
    oos=[]
    for s,tt in bysym.items(): tt.sort(key=lambda x:x[1]); oos+=tt[:len(tt)//2]
    oe=sum(t[2] for t in oos)/len(oos) if oos else 0
    print(f"  {lab:16s}: {n:4d} tr | win {w:4.1f}% | exp {e:+.3f}% | OOS {oe:+.3f}%")

print("FADE-SHORT en el nivel (resistencia). Robustez por tamaño de objetivo + OOS:")
for tgt in (0.004, 0.006, 0.008, 0.010):
    print(f"\n-- objetivo/stop {tgt*100:.1f}% --")
    rep(run(False, tgt), "REDONDO")
    rep(run(True, tgt), "ANTI (control)")
