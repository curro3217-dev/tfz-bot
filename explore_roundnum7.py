"""Mas variantes de salida para la ruptura del numero redondo al alza (buscar la cola
tipo VELVET): objetivo lejano fijo (RR alto) y AGUANTAR mientras la tendencia siga
positiva. Round vs control. Mira expectancy, sum, OOS y los 3 mayores ganadores."""
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
            "VELVET/USDT:USDT","ESPORTS/USDT:USDT","SIREN/USDT:USDT","BEAT/USDT:USDT","H/USDT:USDT"]
TFS = ["5m","15m","1h"]
TREND_MIN=1.0; INIT_SL=0.01; COST=0.12; MAXBARS=500

def lvl(p, anti):
    s=10**math.floor(math.log10(p)); off=0.5*s if anti else 0.0
    return round((p-off)/s)*s+off, s

_c={}
def load(sym,tf):
    if (sym,tf) in _c: return _c[(sym,tf)]
    tfc=config_for_timeframe(TFZConfig(),tf)
    try: df=fetch_ohlcv_cached(sym,tf,limit=2500,config=tfc)
    except Exception: _c[(sym,tf)]=None; return None
    if len(df)<300: _c[(sym,tf)]=None; return None
    tr=np.array([compute_trend_strength(df,tf,i) for i in range(len(df))])
    _c[(sym,tf)]=(df,tr); return _c[(sym,tf)]

def run(anti, mode):
    out=[]
    for sym in UNIVERSE:
        for tf in TFS:
            d=load(sym,tf)
            if not d: continue
            df,trend=d
            close,high,low=df["close"].values,df["high"].values,df["low"].values
            ts=df["timestamp"].astype(str).values; n=len(df); i=205
            while i<n-1:
                if trend[i]>=TREND_MIN:
                    L,s=lvl(close[i],anti)
                    if close[i-1]<=L<close[i] and (close[i]-L)/L<0.01:
                        entry=close[i]; sl0=entry*(1-INIT_SL); end=min(i+MAXBARS,n)
                        exitp=close[end-1]; k=i+1
                        if mode in ("tp10","tp20"):
                            tp=entry*(1+(0.10 if mode=="tp10" else 0.20))
                            for k in range(i+1,end):
                                if low[k]<=sl0: exitp=sl0; break
                                if high[k]>=tp: exitp=tp; break
                        else:  # trend_hold: aguanta hasta que la tendencia se vuelva <=0 o salte el stop
                            for k in range(i+1,end):
                                if low[k]<=sl0: exitp=sl0; break
                                if trend[k]<=0: exitp=close[k]; break
                        pnl=(exitp-entry)/entry*100-COST
                        out.append((sym,ts[i],pnl)); i=k+1; continue
                i+=1
    return out

def rep(x,lab):
    if not x: print(f"  {lab}: 0"); return
    a=np.array([t[2] for t in x]); n=len(a)
    bysym={}
    for t in x: bysym.setdefault(t[0],[]).append(t)
    oos=[]
    for sy,tt in bysym.items(): tt.sort(key=lambda z:z[1]); oos+=tt[:len(tt)//2]
    oe=np.mean([t[2] for t in oos]) if oos else 0
    top=[f"{v:+.0f}%" for v in sorted(a)[-3:]]
    print(f"  {lab:14s}: {n:4d} tr | win {(a>0).mean()*100:4.1f}% | exp {a.mean():+.3f}% | sum {a.sum():+.0f}% | OOS {oe:+.3f}% | top3 {top}")

for mode in ("tp10","tp20","trend_hold"):
    print(f"\n== salida: {mode} ==")
    rep(run(False,mode),"REDONDO break")
    rep(run(True,mode),"ANTI (control)")
