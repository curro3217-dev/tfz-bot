"""
EXPLORACIÓN #4: PAIRS TRADING / STAT-ARB (familia Simons).
Para cada par de monedas correladas, opera el SPREAD (log precio A - beta*log B):
cuando el z-score del spread es extremo, long del rezagado / short del adelantado,
esperando que el spread revierta a su media. Market-neutral.
  - z(spread) > +Z  -> short A / long B   (A caro respecto a B)
  - z(spread) < -Z  -> long A / short B
  - salida: z vuelve a 0 / |z|>Zstop / max_hold
Solo pares con correlación alta (>0.8). Neto de costes (2 patas = 2x coste).
Uso: python explore_pairs.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
import ssl; ssl._create_default_https_context = ssl._create_unverified_context
import urllib3; urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests.adapters as _ra
_o=_ra.HTTPAdapter.send
def _s(self,r,**k):
    k["verify"]=False; k.setdefault("timeout",(10,20)); return _o(self,r,**k)
_ra.HTTPAdapter.send=_s

import itertools
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST = (0.075 + 0.025) * 2 * 2  # 2 patas, ida y vuelta cada una
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]

def main():
    base=TFZConfig(); cfg=config_for_timeframe(base,"15m")
    data={}
    for s in SYMS:
        try:
            d=fetch_ohlcv_cached(f"{s}/USDT:USDT","15m",limit=20000,config=cfg)
            data[s]=d[["timestamp","close"]].rename(columns={"close":s})
        except Exception:
            pass
    syms=list(data.keys())
    allp=[]; npairs=0
    for a,b in itertools.combinations(syms,2):
        m=pd.merge(data[a],data[b],on="timestamp")
        if len(m)<500: continue
        la=np.log(m[a].values); lb=np.log(m[b].values)
        if np.corrcoef(la,lb)[0,1] < 0.8:  # solo correladas
            continue
        npairs+=1
        beta=np.polyfit(lb,la,1)[0]
        spread=la-beta*lb
        sp=pd.Series(spread); z=((sp-sp.rolling(50).mean())/sp.rolling(50).std()).values
        Z,Zstop,max_hold=2.0,3.5,48
        i=51
        while i<len(z)-1:
            if np.isnan(z[i]): i+=1; continue
            d=None
            if z[i]>=Z and z[i-1]<Z: d="short_a"   # A caro
            elif z[i]<=-Z and z[i-1]>-Z: d="long_a"
            if d is None: i+=1; continue
            ea,eb=m[a].values[i],m[b].values[i]
            ex=None
            for j in range(i+1,min(i+1+max_hold,len(z))):
                if np.isnan(z[j]): continue
                if (d=="short_a" and (z[j]<=0 or z[j]>=Zstop)) or (d=="long_a" and (z[j]>=0 or z[j]<=-Zstop)):
                    ex=j; break
            if ex is None: ex=min(i+max_hold,len(z)-1)
            xa,xb=m[a].values[ex],m[b].values[ex]; hold=ex-i
            # pnl de las 2 patas
            if d=="short_a":
                pnl=(ea-xa)/ea*100 + (xb-eb)/eb*100
            else:
                pnl=(xa-ea)/ea*100 + (eb-xb)/eb*100
            pnl-=COST
            allp.append(round(pnl,4))
            i=ex+1
    p=np.array(allp)
    print(f"\n=== #4 PAIRS / STAT-ARB (15m, {npairs} pares corr>0.8), neto ===")
    if len(p):
        print(f"trades {len(p)} | winrate {(p>0).mean()*100:.1f}% | exp {p.mean():+.3f}% | sumPnL {p.sum():.0f}% | avgW {p[p>0].mean():+.2f}% avgL {p[p<0].mean():+.2f}%")
    else:
        print("sin señales")

if __name__ == "__main__":
    main()
