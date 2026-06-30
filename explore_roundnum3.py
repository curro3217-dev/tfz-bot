"""
Test definitivo del iman de numeros redondos (3 angulos a la vez):
 1) UNIVERSO grande + 1500 velas (mas muestra)
 2) CONTROL bien hecho: corre el MISMO trade sobre niveles REDONDOS y ANTI-redondos
    (multiplos desplazados s/2), comparado por CUBO DE DISTANCIA -> aisla la 'redondez'
 3) zona buena: solo entradas a 0.3-1.2% por debajo del nivel
Trade: long, entry=precio, TP=nivel, SL=entry - sl_ratio*(nivel-entry). En tendencia.
Reporta winrate/expectancy/OOS de REDONDO vs ANTI, global y por banda de distancia.
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
MAX_HOLD = 60
TREND_MIN = 1.0
SL_RATIO = 1.0
MIN_D, MAX_D = 0.003, 0.012   # zona buena: 0.3% - 1.2%
COST = 0.10

def lvl_above(p, anti):
    s = 10 ** math.floor(math.log10(p))            # ENTEROS fuertes
    off = 0.5 * s if anti else 0.0
    k = math.floor((p - off) / s) + 1
    return k * s + off

_cache = {}
def load(sym, tf):
    if (sym, tf) in _cache: return _cache[(sym, tf)]
    tfc = config_for_timeframe(TFZConfig(), tf)
    try: df = fetch_ohlcv_cached(sym, tf, limit=1500, config=tfc)
    except Exception: _cache[(sym,tf)] = None; return None
    if len(df) < 300: _cache[(sym,tf)] = None; return None
    trend = np.array([compute_trend_strength(df, tf, i) for i in range(len(df))])
    _cache[(sym,tf)] = (df, trend); return _cache[(sym,tf)]

def run(anti):
    trades = []
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
                    L = lvl_above(p, anti); gap = (L - p) / p
                    if MIN_D <= gap <= MAX_D:
                        entry = p; tp = L; reward = tp - entry; sl = entry - reward * SL_RATIO
                        end = min(i + MAX_HOLD, n); out = "timeout"; brk = end - 1
                        for j in range(i + 1, end):
                            if high[j] >= tp: out = "win"; brk = j; break
                            if low[j] <= sl: out = "loss"; brk = j; break
                        pnl = ((tp if out=="win" else sl if out=="loss" else close[brk]) - entry)/entry*100 - COST
                        trades.append((sym, ts[i], gap, out, pnl)); i = brk + 1; continue
                i += 1
    return trades

def rep(trades, label):
    n = len(trades)
    if not n: print(f"  {label}: 0 trades"); return
    w = sum(1 for t in trades if t[3]=="win"); s = sum(t[4] for t in trades)
    bysym = {}
    for t in trades: bysym.setdefault(t[0], []).append(t)
    oos = []
    for sy, tt in bysym.items():
        tt.sort(key=lambda x:x[1]); oos += tt[:len(tt)//2]
    oexp = sum(t[4] for t in oos)/len(oos) if oos else 0
    print(f"  {label:16s}: {n:4d} tr | win {100*w/n:4.1f}% | exp {s/n:+.3f}% | sum {s:+.0f}% | OOS {oexp:+.3f}%")

print(f"Universo {len(UNIVERSE)} monedas x {TFS} | zona {MIN_D*100:.1f}-{MAX_D*100:.1f}% | tendencia>={TREND_MIN} | sl {SL_RATIO}")
R = run(False); A = run(True)
print("\n=== REDONDO vs CONTROL (misma distancia, mismo trade) ===")
rep(R, "REDONDO")
rep(A, "ANTI (control)")
# por banda de distancia
print("\n=== por banda de distancia (expectancy) ===")
for lo, hi in [(0.003,0.006),(0.006,0.009),(0.009,0.012)]:
    rr = [t for t in R if lo<=t[2]<hi]; aa = [t for t in A if lo<=t[2]<hi]
    er = sum(t[4] for t in rr)/len(rr) if rr else 0; ea = sum(t[4] for t in aa)/len(aa) if aa else 0
    print(f"  {lo*100:.1f}-{hi*100:.1f}%: REDONDO {er:+.3f}% (n={len(rr)}) | ANTI {ea:+.3f}% (n={len(aa)}) | diff {er-ea:+.3f}%")
