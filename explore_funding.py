"""
EXPLORACIÓN #2 y #3: estrategias de FUNDING en perps.

#2 FUNDING COMO SEÑAL (contrarian): cuando el funding es extremo (longs o shorts
   masificados), apostar al giro. funding muy POSITIVO -> short; muy NEGATIVO -> long.
   Mantener `hold_h` horas, medir el movimiento de precio neto de costes + funding.

#3 FUNDING ARBITRAGE (carry, delta-neutral): long spot / short perp cobra el funding
   cuando es positivo. Se calcula el YIELD anualizado medio del funding por moneda,
   neto de comisiones. No es direccional (no hay winrate), es rendimiento de carry.

Uso: python explore_funding.py
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

import time
import numpy as np
import pandas as pd
import ccxt
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached, create_exchange

# 2026-07-03: migrado a MEXC (funding del venue real del bot; antes Bybit) y el
# neto del contrarian (#2) se reporta con AMBOS modelos de coste en la MISMA tanda
# (mismas señales, solo cambia el coste -> comparacion limpia):
COST_OLD  = (0.075 + 0.025) * 2  # % ida y vuelta, modelo antiguo bybit/binance
COST_MEXC = (0.02  + 0.025) * 2  # % ida y vuelta, MEXC taker verificado por API
EXCHANGE = os.environ.get("FUND_EX", "mexc")   # FUND_EX=bybit para reproducir lo viejo
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]

def get_ex():
    ex = create_exchange(EXCHANGE)   # SSL/defaultType centralizados en data_fetcher
    ex.load_markets(); return ex

def funding_hist(ex, sym, pages=6):
    """~pages*200 eventos de funding (8h c/u). Pagina hacia atrás."""
    out=[]; until=None
    for _ in range(pages):
        try:
            params={} if until is None else {'until':until}
            h=ex.fetch_funding_rate_history(sym, limit=200, params=params)
        except Exception:
            break
        if not h: break
        out = h + out
        until = h[0]['timestamp']-1
        if len(h)<200: break
        time.sleep(ex.rateLimit/1000)
    # dedup
    seen=set(); res=[]
    for x in sorted(out,key=lambda z:z['timestamp']):
        if x['timestamp'] not in seen:
            seen.add(x['timestamp']); res.append(x)
    return res

def main():
    ex=get_ex()
    base=TFZConfig(); cfg=config_for_timeframe(base,"1h")
    sig_pnls=[]; carry_rows=[]
    for s in SYMS:
        sym=f"{s}/USDT:USDT"
        fh=funding_hist(ex,sym)
        if len(fh)<50:
            print(f"  {s}: funding insuf ({len(fh)})"); continue
        rates=np.array([x['fundingRate'] for x in fh])
        fts=np.array([x['timestamp'] for x in fh])
        # ---- #3 carry: yield anualizado del funding (3 pagos/dia) ----
        ann = rates.mean()*3*365*100  # % anual (cobrando el funding medio)
        carry_rows.append((s, rates.mean()*100, ann))
        # ---- #2 señal contrarian: funding extremo (deciles) ----
        hi=np.quantile(rates,0.9); lo=np.quantile(rates,0.1)
        try:
            d=fetch_ohlcv_cached(sym,"1h",limit=20000,config=cfg)
        except Exception:
            continue
        # FIX 2026-07-03: la columna llega como datetime64[ms] (parquet), no [ns];
        # el viejo `astype("int64")//10**6` daba una escala 1000x menor -> searchsorted
        # nunca casaba y el test #2 reportaba "sin señales" SIEMPRE (tambien en Bybit).
        ts=d["timestamp"].values.astype("datetime64[ms]").astype("int64")
        cl=d["close"].values
        hold_h=8
        for r,t in zip(rates,fts):
            if r<hi and r>lo:  # solo extremos
                continue
            idx=np.searchsorted(ts,t)
            if idx<=0 or idx+hold_h>=len(ts): continue
            entry=cl[idx]; ex_px=cl[idx+hold_h]
            direction = "short" if r>0 else "long"  # contrarian
            pnl=(entry-ex_px)/entry*100 if direction=="short" else (ex_px-entry)/entry*100
            # el contrarian al funding positivo (short) COBRA funding; negativo (long) tambien cobra
            pnl += abs(r)*100  # cobra ~1 pago de funding a su favor
            sig_pnls.append(round(pnl,4))  # BRUTO; el coste se aplica al reportar (2 modelos)
        print(f"  {s:7} funding {len(fh)} ev | carry {ann:+.1f}%/año | señales acum {len(sig_pnls)}")

    print("\n=== #3 FUNDING CARRY (yield anualizado por cobrar funding, neto aprox) ===")
    carry_rows.sort(key=lambda x:-x[2])
    for s,m,a in carry_rows:
        print(f"  {s:7} funding medio {m:+.4f}%/8h -> {a:+.1f}%/año")
    arr=np.array([a for _,_,a in carry_rows])
    print(f"  MEDIA universo: {arr.mean():+.1f}%/año | positivos: {(arr>0).sum()}/{len(arr)}")

    print(f"\n=== #2 FUNDING COMO SEÑAL (contrarian, hold 8h) — funding de {EXCHANGE} ===")
    if sig_pnls:
        for label, cost in (("coste ANTIGUO (0.2% i/v)", COST_OLD),
                            ("coste MEXC (0.09% i/v)", COST_MEXC)):
            p=np.array(sig_pnls)-cost
            print(f"  [{label}] trades {len(p)} | winrate {(p>0).mean()*100:.1f}% | "
                  f"exp {p.mean():+.3f}% | sumPnL {p.sum():.0f}% | "
                  f"avgW {p[p>0].mean():+.2f}% avgL {p[p<0].mean():+.2f}%")
    else:
        print("sin señales")

if __name__ == "__main__":
    main()
