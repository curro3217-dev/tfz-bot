"""
EXPLORACIÓN #1: reversión a la media BTC-NEUTRAL (residual).
En vez del precio absoluto, opera el RATIO moneda/BTC: cuando una moneda se mueve
de MÁS respecto a BTC (z-score del ratio extremo), se apuesta a que el residuo
revierte. Aísla el componente idiosincrático (lo que la literatura da Sharpe ~2.3).
  - long  coin cuando z(ratio) < -Z  (la moneda cayó de más vs BTC) -> espera catch-up
  - short coin cuando z(ratio) > +Z
  - salida: z vuelve a 0 (TP) / z se extiende a -Z_stop (SL) / max_hold velas
Neto de costes (0.2% ida-vuelta + funding). Uso: python explore_residual_mr.py
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

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST = (0.075 + 0.025) * 2  # % ida y vuelta
FUND = 0.01                  # %/8h aprox

def zscore(x, n=50):
    s = pd.Series(x)
    return ((s - s.rolling(n).mean()) / s.rolling(n).std()).values

def sim(coin_df, btc_df, tf, Z=2.0, Zstop=3.5, max_hold=48, n=50):
    m = pd.merge(coin_df[["timestamp","close"]], btc_df[["timestamp","close"]],
                 on="timestamp", suffixes=("","_btc"))
    if len(m) < n + 60:
        return []
    ratio = (m["close"] / m["close_btc"]).values
    z = zscore(ratio, n)
    closes = m["close"].values
    tfmin = {"5m":5,"15m":15,"1h":60}.get(tf,15)
    pnls = []
    i = n + 1
    while i < len(z) - 1:
        if np.isnan(z[i]):
            i += 1; continue
        direction = None
        if z[i] <= -Z and z[i-1] > -Z:
            direction = "long"
        elif z[i] >= Z and z[i-1] < Z:
            direction = "short"
        if direction is None:
            i += 1; continue
        entry = closes[i]
        exit_px = None
        for j in range(i+1, min(i+1+max_hold, len(z))):
            if np.isnan(z[j]):
                continue
            if direction == "long":
                if z[j] >= 0 or z[j] <= -Zstop:
                    exit_px = closes[j]; hold = j-i; break
            else:
                if z[j] <= 0 or z[j] >= Zstop:
                    exit_px = closes[j]; hold = j-i; break
        if exit_px is None:
            exit_px = closes[min(i+max_hold, len(z)-1)]; hold = max_hold
        if direction == "long":
            pnl = (exit_px-entry)/entry*100
        else:
            pnl = (entry-exit_px)/entry*100
        pnl -= COST + FUND*(hold*tfmin/60/8)
        pnls.append(round(pnl,4))
        i += hold + 1  # no solapar
    return pnls

def main():
    SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
            "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]
    base = TFZConfig()
    allp = []
    for tf in ["15m"]:
        cfg = config_for_timeframe(base, tf)
        btc = fetch_ohlcv_cached("BTC/USDT:USDT", tf, limit=20000, config=cfg)
        for s in SYMS:
            try:
                d = fetch_ohlcv_cached(f"{s}/USDT:USDT", tf, limit=20000, config=cfg)
            except Exception:
                continue
            if len(d) < 500:
                continue
            allp += sim(d, btc, tf)
            print(f"  {s:7} {tf} acumulado {len(allp)}")
    p = np.array(allp)
    print("\n=== REVERSIÓN RESIDUAL BTC-NEUTRAL (15m), neto ===")
    if len(p)==0:
        print("sin señales"); return
    print(f"trades {len(p)} | winrate {(p>0).mean()*100:.1f}% | exp {p.mean():+.3f}% | sumPnL {p.sum():.0f}% | avgW {p[p>0].mean():+.2f}% avgL {p[p<0].mean():+.2f}%")

if __name__ == "__main__":
    main()
