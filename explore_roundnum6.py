"""
Variante 'DEJAR CORRER' (asimetrica, tipo VELVET +800%): romper el numero redondo
al alza y montarse el momentum con stop ceñido + TRAILING (sale a TRAIL% del maximo).
Pocos aciertos pero los pelotazos pagan. Round vs control. Mira la COLA (mayores
ganadores), expectancy, sum y OOS.
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
TFS = ["5m", "15m", "1h"]
TREND_MIN = 1.0
INIT_SL = 0.01     # stop inicial 1% bajo la entrada
COST = 0.12
MAXBARS = 500      # tope de velas (que pueda correr mucho)

def lvl(p, anti):
    s = 10 ** math.floor(math.log10(p)); off = 0.5*s if anti else 0.0
    # nivel redondo mas cercano (para detectar ruptura)
    return round((p-off)/s)*s + off, s

_c={}
def load(sym, tf):
    if (sym,tf) in _c: return _c[(sym,tf)]
    tfc=config_for_timeframe(TFZConfig(),tf)
    try: df=fetch_ohlcv_cached(sym,tf,limit=2500,config=tfc)
    except Exception: _c[(sym,tf)]=None; return None
    if len(df)<300: _c[(sym,tf)]=None; return None
    tr=np.array([compute_trend_strength(df,tf,i) for i in range(len(df))])
    _c[(sym,tf)]=(df,tr); return _c[(sym,tf)]

def run(anti, trail):
    out=[]   # (sym, ts, pnl)
    for sym in UNIVERSE:
        for tf in TFS:
            d=load(sym,tf)
            if not d: continue
            df,trend=d
            close,high,low=df["close"].values,df["high"].values,df["low"].values
            ts=df["timestamp"].astype(str).values; n=len(df); i=205
            while i<n-1:
                if trend[i]>=TREND_MIN:
                    L,s = lvl(close[i], anti)
                    # RUPTURA: vela anterior por debajo del nivel y esta lo cruza al alza
                    if close[i-1] <= L < close[i] and (close[i]-L)/L < 0.01:  # cruce limpio, no muy lejos
                        entry=close[i]; peak=high[i]; sl0=entry*(1-INIT_SL)
                        end=min(i+MAXBARS,n); exitp=close[end-1]; k=i+1
                        for k in range(i+1,end):
                            peak=max(peak,high[k])
                            cur_sl=max(sl0, peak*(1-trail))
                            if low[k]<=cur_sl: exitp=cur_sl; break
                        pnl=(exitp-entry)/entry*100 - COST
                        out.append((sym,ts[i],pnl)); i=k+1; continue
                i+=1
    return out

def rep(x,lab):
    if not x: print(f"  {lab}: 0"); return
    a=np.array([t[2] for t in x]); n=len(a)
    w=(a>0).mean()*100; e=a.mean(); s=a.sum()
    bysym={}
    for t in x: bysym.setdefault(t[0],[]).append(t)
    oos=[]
    for sy,tt in bysym.items(): tt.sort(key=lambda z:z[1]); oos+=tt[:len(tt)//2]
    oe=np.mean([t[2] for t in oos]) if oos else 0
    top=sorted(a)[-3:]
    print(f"  {lab:14s}: {n:4d} tr | win {w:4.1f}% | exp {e:+.3f}% | sum {s:+.0f}% | OOS {oe:+.3f}% | top3 {['%+.0f%%'%v for v in top]}")

for trail in (0.03, 0.05, 0.08):
    print(f"\n== trailing {trail*100:.0f}% del maximo, stop inicial {INIT_SL*100:.0f}% ==")
    rep(run(False,trail), "REDONDO break")
    rep(run(True,trail), "ANTI (control)")
