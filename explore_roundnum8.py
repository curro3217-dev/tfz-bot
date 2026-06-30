"""
TU metodo: en tendencia alcista fuerte, entrar LEJOS del numero redondo, objetivo = el
siguiente numero redondo grande de arriba, stop que se va SUBIENDO (trailing).
Mide edge + control (objetivo redondo vs no-redondo a la misma distancia) + OOS.
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
            "VELVET/USDT:USDT","ESPORTS/USDT:USDT","SIREN/USDT:USDT","BEAT/USDT:USDT","H/USDT:USDT"]
TFS = ["15m","1h"]            # tendencias grandes -> TF altas (tus trades de +19/+43%)
MINGAP, MAXGAP = 0.03, 0.50   # el redondo entre +3% y +50% (entras LEJOS)
INIT_SL = 0.03; COST = 0.12; MAXBARS = 800

def tgt_above(p, anti):
    s = 10 ** math.floor(math.log10(p)) / 2   # niveles 5/10/15/20 .. 0.05/0.10
    off = 0.5*s if anti else 0.0
    return (math.floor((p-off)/s)+1)*s + off

_c={}
def load(sym,tf):
    if (sym,tf) in _c: return _c[(sym,tf)]
    tfc=config_for_timeframe(TFZConfig(),tf)
    try: df=fetch_ohlcv_cached(sym,tf,limit=2500,config=tfc)
    except Exception: _c[(sym,tf)]=None; return None
    if len(df)<300: _c[(sym,tf)]=None; return None
    tr=np.array([compute_trend_strength(df,tf,i) for i in range(len(df))])
    _c[(sym,tf)]=(df,tr); return _c[(sym,tf)]

def run(anti, trend_min, trail):
    out=[]
    for sym in UNIVERSE:
        for tf in TFS:
            d=load(sym,tf)
            if not d: continue
            df,trend=d
            close,high,low=df["close"].values,df["high"].values,df["low"].values
            ts=df["timestamp"].astype(str).values; n=len(df); i=205
            while i<n-1:
                if trend[i]>=trend_min:
                    p=close[i]; L=tgt_above(p,anti); gap=(L-p)/p
                    if MINGAP<=gap<=MAXGAP:
                        entry=p; peak=high[i]; sl0=entry*(1-INIT_SL)
                        end=min(i+MAXBARS,n); exitp=close[end-1]; k=i+1
                        for k in range(i+1,end):
                            peak=max(peak,high[k])
                            cur_sl=max(sl0, peak*(1-trail))
                            if high[k]>=L: exitp=L; break          # TP en el redondo
                            if low[k]<=cur_sl: exitp=cur_sl; break # trailing
                        pnl=(exitp-entry)/entry*100-COST
                        out.append((sym,ts[i],pnl)); i=k+1; continue
                i+=1
    return out

def rep(x,lab):
    if not x: print(f"  {lab}: 0"); return
    a=np.array([t[2] for t in x]);
    bysym={}
    for t in x: bysym.setdefault(t[0],[]).append(t)
    oos=[]
    for sy,tt in bysym.items(): tt.sort(key=lambda z:z[1]); oos+=tt[:len(tt)//2]
    oe=np.mean([t[2] for t in oos]) if oos else 0
    top=[f"{v:+.0f}%" for v in sorted(a)[-3:]]
    print(f"  {lab:14s}: {len(a):4d} tr | win {(a>0).mean()*100:4.1f}% | exp {a.mean():+.3f}% | sum {a.sum():+.0f}% | OOS {oe:+.3f}% | top3 {top}")

for tmin in (1.0, 3.0):
    for trail in (0.08, 0.15):
        print(f"\n== tendencia>={tmin}, trailing {trail*100:.0f}% ==")
        rep(run(False,tmin,trail),"REDONDO TP")
        rep(run(True,tmin,trail),"ANTI (control)")
