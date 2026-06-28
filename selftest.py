"""
Prueba de reproducibilidad: genera las señales sobre las MISMAS velas (hasta una
hora fija, ya cerradas) y saca un hash. Si el hash en tu PC == el de GitHub Actions,
el bot opera EXACTAMENTE igual en ambos sitios (aunque cambien el SO y la versión
de Python). Uso:  python selftest.py
"""
import hashlib
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from swings import detect_swings, compute_trend_strength
from levels import detect_horizontal_levels, detect_diagonal_levels
from consolidation import detect_consolidations
from sweep import detect_sweeps
from formations import detect_formations
from filters import check_chart_quality
from signals import generate_signals

CUTOFF = "2026-06-28 21:00:00"   # UTC, fijo: ambos entornos ven las mismas velas
SYMS = ["DOGE/USDT:USDT", "XRP/USDT:USDT", "SOL/USDT:USDT", "AVAX/USDT:USDT",
        "BNB/USDT:USDT", "NEAR/USDT:USDT"]
TFS = ["1m", "5m", "15m"]

cfg = TFZConfig()
out = []
print(f"corte (UTC): {CUTOFF}")
for sym in SYMS:
    for tf in TFS:
        tfc = config_for_timeframe(cfg, tf)
        try:
            df = fetch_ohlcv_cached(sym, tf, limit=1500, config=tfc)
        except Exception as e:
            print(f"  {sym} {tf}: fetch error {e}")
            continue
        df = df[df["timestamp"].astype(str) <= CUTOFF].tail(600).reset_index(drop=True)
        if len(df) < 200:
            continue
        sw = detect_swings(df, tfc)
        if not check_chart_quality(df, sw, tfc).passed:
            continue
        cp = float(df["close"].iloc[-1])
        ci = len(df) - 1
        hl = detect_horizontal_levels(sw, cp, tfc, total_candles=len(df))
        dl = detect_diagonal_levels(sw, cp, tfc)
        cons = detect_consolidations(df, tfc, [l.price for l in hl])
        swp = detect_sweeps(df, hl, tfc)
        fm = detect_formations(hl, dl, cons, swp, cp, ci, tfc)
        tr = compute_trend_strength(df, tf, ci)
        for s in generate_signals(df, fm, sym, tf, tfc, trend_strength=tr, is_bear_market=False):
            out.append(f"{sym.split('/')[0]}|{tf}|{s.direction}|{s.formation_type}|"
                       f"{round(s.entry_price, 6)}|{round(s.stop_loss, 6)}|"
                       f"{round(s.take_profit, 6)}|{round(s.total_score, 1)}|{round(s.rr_ratio, 2)}")
out.sort()
blob = "\n".join(out)
h = hashlib.sha256(blob.encode()).hexdigest()[:16]
print(f"\nSEÑALES generadas: {len(out)}")
for line in out:
    print("  " + line)
print(f"\nHASH: {h}")
