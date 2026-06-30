"""
Test del VOLUMEN RELATIVO (RVOL, idea de Warrior Trading) sobre los trades que YA
tenemos. Para cada trade: RVOL = volumen de la vela de entrada / media de las ultimas
N velas. Pregunta: ¿los trades con RVOL alto rinden mejor? Si si -> filtro de calidad.
Post-hoc: NO modifica ml_dataset (no contamina). Lee un CSV de trades existente.
Uso:  python explore_rvol.py [csv]   (def ml_dataset_basef.csv)
"""
import sys
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

CSV = sys.argv[1] if len(sys.argv) > 1 else "ml_dataset_basef.csv"
N = 20  # ventana para la media de volumen

df = pd.read_csv(CSV)
f = df[(df["total_score"] >= 60) & (df["rr_ratio"] >= 6)].copy()
print(f"{CSV}: {len(f)} trades (60/6)")

# cache de velas por symbol/tf
_c = {}
def candles(sym, tf):
    if (sym, tf) not in _c:
        tfc = config_for_timeframe(TFZConfig(), tf)
        try:
            _c[(sym, tf)] = fetch_ohlcv_cached(sym, tf, limit=2500, config=tfc)
        except Exception:
            _c[(sym, tf)] = None
    return _c[(sym, tf)]

rvols = []
for _, r in f.iterrows():
    c = candles(r["symbol"], r["timeframe"])
    rv = np.nan
    if c is not None:
        s = c["timestamp"].astype(str)
        idx = s.index[s <= str(r["entry_ts"])]
        if len(idx) > N:
            j = int(idx[-1])
            base = c["volume"].iloc[j - N:j].mean()
            if base and base > 0:
                rv = c["volume"].iloc[j] / base
    rvols.append(rv)
f["rvol"] = rvols
f = f[f["rvol"].notna()]
print(f"con RVOL calculado: {len(f)}")

def stats(d):
    n = len(d)
    if n == 0:
        return "(0)"
    w = (d["pnl_pct"] > 0).mean() * 100
    e = d["pnl_pct"].mean()
    o = []
    for sym, g in d.groupby("symbol"):
        g = g.sort_values("entry_ts")
        o.append(g.iloc[:len(g)//2])
    oe = pd.concat(o)["pnl_pct"].mean() if o else 0
    return f"{n:5d} tr | win {w:4.1f}% | exp {e:+.3f}% | OOS {oe:+.3f}%"

print(f"\nGLOBAL: {stats(f)}")
print("\n=== por banda de RVOL ===")
for lo, hi in [(0, 1), (1, 2), (2, 3), (3, 5), (5, 1e9)]:
    b = f[(f["rvol"] >= lo) & (f["rvol"] < hi)]
    lab = f">={lo}x" if hi > 1e8 else f"{lo}-{hi}x"
    print(f"  RVOL {lab:8s}: {stats(b)}")
print("\n=== umbral: trades con RVOL >= X ===")
for thr in (1.5, 2, 3):
    print(f"  RVOL>={thr}: {stats(f[f['rvol']>=thr])}")
