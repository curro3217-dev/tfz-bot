"""
EXPLORACIÓN: ¿el FILTRO DE SELECCIÓN de Krasnov (mover extremo + cerca de máximos)
separa los ganadores de los perdedores DENTRO de los trades del bot?

De reverse_features (krasnov-tracker): lo que Krasnov OPERA vs lo que DESCARTA se
distingue por mov_24h (~59% vs 15%) y pos_rango (~0.77 vs 0.56). Aquí aplicamos ESO
a los 389 micro_pullback cerrados del bot: para cada trade calculamos, EN SU ENTRADA,
el movimiento de 24h y la posición en el rango; luego comparamos el PnL (ya calculado
por el bot, no se recalcula) de los que pasan el filtro vs los que no.

Si el filtro separa (los "mover extremo + cerca de máximos" ganan y el resto pierde),
es un candidato de filtro real para las alertas F -> se sellaria forward.
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
import sqlite3
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv

BASE = os.path.dirname(os.path.abspath(__file__))


def _load(db):
    try:
        c = sqlite3.connect("file:" + db + "?mode=ro", uri=True)
        cur = c.execute("SELECT symbol,entry_ts,pnl_pct FROM paper_trades WHERE status='closed'")
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur]
    except Exception:
        return []


def _features(sym, entry_ts):
    """mov_24h (%) y pos_rango (0-1) en el momento de la entrada, desde 1h MEXC."""
    cfg = config_for_timeframe(TFZConfig(), "1h")
    wdt = pd.Timestamp(entry_ts)
    since = int((wdt - pd.Timedelta(hours=30)).timestamp() * 1000)
    try:
        df = fetch_ohlcv(sym, "1h", limit=40, since=since, config=cfg)
    except Exception:
        return None
    if df is None or len(df) < 24:
        return None
    ts = df["timestamp"].astype("int64").values
    i = int(np.searchsorted(ts, int(wdt.timestamp() * 1000)))
    i = min(max(i, 24), len(df) - 1)
    C = df["close"].values.astype(float); H = df["high"].values.astype(float); L = df["low"].values.astype(float)
    mov24 = (C[i] / C[i - 24] - 1) * 100
    hi = H[i - 24:i + 1].max(); lo = L[i - 24:i + 1].min()
    pos = (C[i] - lo) / (hi - lo) if hi > lo else 0.5
    return mov24, pos


def main():
    trades = _load(os.path.join(BASE, "tfz_data.db")) + _load(os.path.join(BASE, "github_state/tfz_data.db"))
    rows = []
    for t in trades:
        f = _features(t["symbol"], t["entry_ts"])
        if f:
            rows.append((f[0], f[1], t["pnl_pct"]))
    a = np.array(rows)   # cols: mov24, pos, pnl
    print(f"trades con features: {len(a)} de {len(trades)}")
    print(f"mov_24h del universo del bot: mediana {np.median(a[:,0]):.1f}% | p90 {np.percentile(a[:,0],90):.1f}%")
    print(f"media PnL global: {a[:,2].mean():+.3f}%\n")

    def grupo(mask, nombre):
        g = a[mask]
        if len(g) < 5:
            print(f"  {nombre:34s} n={len(g):3d} (pocos)"); return
        se = g[:, 2].std(ddof=1) / np.sqrt(len(g))
        print(f"  {nombre:34s} n={len(g):3d} | media {g[:,2].mean():+.3f}% | "
              f"win {(g[:,2]>0).mean()*100:4.1f}% | IC95 [{g[:,2].mean()-1.96*se:+.3f},{g[:,2].mean()+1.96*se:+.3f}]")

    print("=== por FILTRO de Krasnov (mover extremo + cerca de máximos) ===")
    for thr in [20, 30, 40, 50]:
        grupo((a[:, 0] >= thr) & (a[:, 1] >= 0.7), f"mov24>={thr}% & pos>=0.70")
    print("  --- solo una condicion ---")
    grupo(a[:, 0] >= 40, "mov24 >= 40% (solo)")
    grupo(a[:, 1] >= 0.7, "pos >= 0.70 (solo)")
    grupo((a[:, 0] < 20), "mov24 < 20% (los flojos)")


if __name__ == "__main__":
    main()
