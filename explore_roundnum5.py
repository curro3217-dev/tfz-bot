"""
Validacion EXTENDIDA del fade-short en resistencia de numero redondo.
Mas universo + mas histgrico, y angulos: por temporalidad, por moneda, estabilidad
temporal (tercios) y significancia estadistica (round vs control).
"""
import math
import numpy as np
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from swings import compute_trend_strength

UNIVERSE = ["DOGE/USDT:USDT","XRP/USDT:USDT","SOL/USDT:USDT","AVAX/USDT:USDT","BNB/USDT:USDT",
            "NEAR/USDT:USDT","ADA/USDT:USDT","LINK/USDT:USDT","SUI/USDT:USDT","WLD/USDT:USDT",
            "AAVE/USDT:USDT","ENA/USDT:USDT","DOT/USDT:USDT","ATOM/USDT:USDT","INJ/USDT:USDT",
            "TIA/USDT:USDT","SEI/USDT:USDT","ARB/USDT:USDT","OP/USDT:USDT","LDO/USDT:USDT",
            "FIL/USDT:USDT","ALGO/USDT:USDT","CRV/USDT:USDT","GALA/USDT:USDT","XLM/USDT:USDT",
            "ONDO/USDT:USDT","PENDLE/USDT:USDT","WIF/USDT:USDT","JUP/USDT:USDT","RENDER/USDT:USDT",
            "APT/USDT:USDT","UNI/USDT:USDT","FET/USDT:USDT","JTO/USDT:USDT","ZEC/USDT:USDT",
            "BCH/USDT:USDT","HYPE/USDT:USDT","1000PEPE/USDT:USDT","MU/USDT:USDT","SOXL/USDT:USDT"]
TFS = ["5m", "15m", "1h"]
APPROACH, POST = 60, 30
TREND_MIN, NEARLO, NEARHI, TGT, COST = 1.0, 0.003, 0.012, 0.006, 0.10

def lvl_above(p, anti):
    s = 10 ** math.floor(math.log10(p)); off = 0.5*s if anti else 0.0
    return (math.floor((p-off)/s)+1)*s + off

_c={}
def load(sym, tf):
    if (sym,tf) in _c: return _c[(sym,tf)]
    tfc=config_for_timeframe(TFZConfig(),tf)
    try: df=fetch_ohlcv_cached(sym,tf,limit=2500,config=tfc)
    except Exception: _c[(sym,tf)]=None; return None
    if len(df)<300: _c[(sym,tf)]=None; return None
    tr=np.array([compute_trend_strength(df,tf,i) for i in range(len(df))])
    _c[(sym,tf)]=(df,tr); return _c[(sym,tf)]

def run(anti):
    out=[]   # (sym, tf, ts, pnl)
    for sym in UNIVERSE:
        for tf in TFS:
            d=load(sym,tf)
            if not d: continue
            df,trend=d
            close,high,low=df["close"].values,df["high"].values,df["low"].values
            ts=df["timestamp"].astype(str).values; n=len(df); i=200
            while i<n-1:
                if trend[i]>=TREND_MIN:
                    L=lvl_above(close[i],anti); gap=(L-close[i])/close[i]
                    if NEARLO<=gap<=NEARHI:
                        tj=None
                        for j in range(i+1,min(i+APPROACH,n)):
                            if high[j]>=L: tj=j; break
                        if tj is not None:
                            e=L; end=min(tj+POST,n); ft,fs=L*(1-TGT),L*(1+TGT); o=None
                            for k in range(tj+1,end):
                                if low[k]<=ft: o=(e-ft)/e*100-COST; break
                                if high[k]>=fs: o=(e-fs)/e*100-COST; break
                            if o is None: o=(e-close[end-1])/e*100-COST
                            out.append((sym,tf,ts[tj],o)); i=tj+1; continue
                i+=1
    return out

R=run(False); A=run(True)
def st(x):
    a=np.array([t[3] for t in x]);
    return len(a), (a>0).mean()*100, a.mean(), a.std(), a.mean()/(a.std()/math.sqrt(len(a)))
nR,wR,eR,sR,tR = st(R); nA,wA,eA,sA,tA = st(A)
print(f"Universo {len(UNIVERSE)} x {TFS}, hasta 2500 velas, objetivo {TGT*100:.1f}%")
print(f"\nREDONDO: {nR} tr | win {wR:.1f}% | exp {eR:+.3f}% | t-stat {tR:+.1f} (>2 = significativo)")
print(f"CONTROL: {nA} tr | win {wA:.1f}% | exp {eA:+.3f}% | t-stat {tA:+.1f}")
# diff significancia
seR=sR/math.sqrt(nR); seA=sA/math.sqrt(nA); dz=(eR-eA)/math.sqrt(seR**2+seA**2)
print(f"DIFERENCIA redondo-control: {eR-eA:+.3f}% | z={dz:+.1f} (>2 = la redondez aporta de verdad)")

print("\n=== por temporalidad (REDONDO) ===")
for tf in TFS:
    x=[t for t in R if t[1]==tf]
    if x: n,w,e,_,tt=st(x); print(f"  {tf:>3s}: {n:4d} tr | win {w:.1f}% | exp {e:+.3f}% | t {tt:+.1f}")

print("\n=== por moneda (REDONDO): cuantas positivas ===")
pos=0; tot=0
for sym in UNIVERSE:
    x=[t[3] for t in R if t[0]==sym]
    if len(x)>=8:
        tot+=1;
        if np.mean(x)>0: pos+=1
print(f"  {pos}/{tot} monedas (con >=8 trades) tienen expectancy positiva")

print("\n=== estabilidad temporal (REDONDO, 3 tercios por fecha) ===")
Rs=sorted(R,key=lambda t:t[2]); th=len(Rs)//3
for idx,part in enumerate([Rs[:th],Rs[th:2*th],Rs[2*th:]]):
    n,w,e,_,tt=st(part); print(f"  tercio {idx+1}: {n:4d} tr | win {w:.1f}% | exp {e:+.3f}%")
