"""Diagnose why F1/F2/F3 barely fire."""
import os
os.environ.setdefault("INSECURE_SSL", "1")
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import urllib3
urllib3.disable_warnings()
import requests.adapters as _ra
_orig = _ra.HTTPAdapter.send
def _ns(self, req, **kw):
    kw["verify"] = False
    return _orig(self, req, **kw)
_ra.HTTPAdapter.send = _ns

from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv
from swings import detect_swings
from levels import detect_horizontal_levels, detect_diagonal_levels, filter_levels_by_distance
from consolidation import detect_consolidations
from sweep import detect_sweeps
from formations import detect_formations, _consol_aligned

cfg = config_for_timeframe(TFZConfig(), "15m")
df = fetch_ohlcv("ETH/USDT", "15m", limit=1000, config=cfg)

for w_start in range(0, len(df) - 400, 100):
    window = df.iloc[w_start:w_start+400].reset_index(drop=True)
    swings = detect_swings(window, cfg)
    cp = float(window["close"].iloc[-1])
    cidx = len(window) - 1

    h_levels = detect_horizontal_levels(swings, cp, cfg, len(window))
    d_levels = detect_diagonal_levels(swings, cp, cfg)
    level_prices = [l.price for l in h_levels]
    consols = detect_consolidations(window, cfg, level_prices)
    sweeps = detect_sweeps(window, h_levels, cfg)

    above = [l for l in h_levels if l.side == "above"]
    below = [l for l in h_levels if l.side == "below"]

    formations = detect_formations(h_levels, d_levels, consols, sweeps, cp, cidx, cfg)
    by_type = {}
    for f in formations:
        by_type[f.type] = by_type.get(f.type, 0) + 1

    # Detailed diagnostics for one window
    if w_start == 0 or (len(above) >= 2 and len(consols) >= 1):
        print(f"\n--- Window [{w_start}:{w_start+400}] price={cp:.2f} ---")
        print(f"  H-levels: {len(h_levels)} (above={len(above)}, below={len(below)})")
        print(f"  Consols: {len(consols)}, Sweeps: {len(sweeps)}")
        print(f"  Formations: {by_type}")

        for direction, target in [("long", above), ("short", below)]:
            groups = filter_levels_by_distance(target, cfg.dist_max_altcoin)
            if not groups:
                print(f"  {direction}: 0 level groups (need 2+ levels within {cfg.dist_max_altcoin}%)")
                if target:
                    prices = sorted([l.price for l in target])
                    if len(prices) >= 2:
                        dists = []
                        for i in range(len(prices)-1):
                            d = (prices[i+1]-prices[i])/prices[i]*100
                            dists.append(d)
                        print(f"    level prices: {[f'{p:.2f}' for p in prices]}")
                        print(f"    pairwise dists: {[f'{d:.2f}%' for d in dists]}")
                continue

            for gi, g in enumerate(groups):
                aligned_consols = [c for c in consols if _consol_aligned(c, g, direction)]
                lprices = [l.price for l in g]
                print(f"  {direction} group {gi}: {len(g)} levels at {[f'{p:.2f}' for p in lprices]}")
                print(f"    aligned consols: {len(aligned_consols)}/{len(consols)}")
                if not aligned_consols and consols:
                    nearest = min(l.price for l in g) if direction == "long" else max(l.price for l in g)
                    for c in consols[-3:]:
                        if direction == "long":
                            gap = (nearest - c.range_high) / nearest * 100
                            print(f"    consol [{c.start_idx}-{c.end_idx}] high={c.range_high:.2f} vs nearest_level={nearest:.2f} gap={gap:.2f}%")
                        else:
                            gap = (c.range_low - nearest) / nearest * 100
                            print(f"    consol [{c.start_idx}-{c.end_idx}] low={c.range_low:.2f} vs nearest_level={nearest:.2f} gap={gap:.2f}%")

        if w_start > 500:
            break
