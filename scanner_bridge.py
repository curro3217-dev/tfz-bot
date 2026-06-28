"""
Bridge between the coin-selection bot and the TFZ engine.

The selector is the user's Binance-futures movers scanner. This bridge runs one
scan and converts the picks into ccxt perpetual symbols the TFZ engine consumes.

Portable by design (works on Windows PC and on a Linux VPS):
  1. If the external scanner.py is reachable (env TFZ_SCANNER_DIR, the Windows
     default path, or next to this file) -> use its exact logic.
  2. Otherwise -> use a built-in copy of the same filter (same Binance endpoint
     and thresholds), so the bot needs no external file on a server.

  from scanner_bridge import get_perp_watchlist
  symbols = get_perp_watchlist()   # ['ESPORTS/USDT:USDT', ...]
"""

import os
import sys
import json
import ssl
import urllib.request

# --- Selector parameters (mirror the user's scanner.py) ---------------------
_FAPI_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"
_MIN_VOLUME_USD = 100_000_000
_MIN_CHANGE_PCT = 10.0
_QUOTE = "USDT"
_EXCLUDE = {"BTC", "ETH", "SOL", "BNB", "USDC", "USD1", "XAUT"}

_SCANNER_DIRS = [
    os.environ.get("TFZ_SCANNER_DIR", ""),
    r"C:\Users\jarta\Desktop\binance-volume-scanner",
    os.path.dirname(__file__),
]


def _ssl_ctx():
    ctx = ssl.create_default_context()
    if os.environ.get("INSECURE_SSL") == "1":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _external_scanner():
    """Return the user's scanner module if its scanner.py is reachable, else None."""
    for d in _SCANNER_DIRS:
        if d and os.path.exists(os.path.join(d, "scanner.py")):
            if d not in sys.path:
                sys.path.insert(0, d)
            try:
                import scanner
                return scanner
            except Exception:
                return None
    return None


def _builtin_movers():
    """Self-contained copy of the scanner's filter (Binance fapi 24h tickers)."""
    req = urllib.request.Request(_FAPI_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=_ssl_ctx(), timeout=15) as r:
        tickers = json.loads(r.read().decode())
    out = []
    for t in tickers:
        sym = t.get("symbol", "")
        if not sym.endswith(_QUOTE):
            continue
        try:
            price = float(t["lastPrice"]); vol = float(t["quoteVolume"])
            chg = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            continue
        base = sym[:-len(_QUOTE)]
        if vol < _MIN_VOLUME_USD or base in _EXCLUDE or abs(chg) < _MIN_CHANGE_PCT:
            continue
        out.append({"symbol": sym, "base": base, "price": price,
                    "volume_24h": vol, "change_24h": chg})
    out.sort(key=lambda x: -abs(x["change_24h"]))
    return out


def get_movers(max_symbols=None):
    """Run one scan and return the picks (list of dicts). Prefers the external
    scanner, falls back to the built-in copy."""
    os.environ.setdefault("INSECURE_SSL", os.environ.get("INSECURE_SSL", "0"))
    sc = _external_scanner()
    if sc is not None:
        try:
            coins = sc.filter_and_sort(sc.fetch_tickers())
        except Exception:
            coins = _builtin_movers()
    else:
        coins = _builtin_movers()
    return coins[:max_symbols] if max_symbols else coins


def to_perp_symbol(base: str) -> str:
    """Binance-futures base -> ccxt linear-perp symbol."""
    return f"{base}/USDT:USDT"


def get_perp_watchlist(max_symbols=None):
    """The selector's current movers as ccxt perpetual symbols."""
    return [to_perp_symbol(c["base"]) for c in get_movers(max_symbols)]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=None)
    args = ap.parse_args()
    src = "external scanner" if _external_scanner() else "built-in copy"
    movers = get_movers(args.max)
    print(f"Selector ({src}) returned {len(movers)} movers:\n")
    print(f"  {'symbol':<14} {'perp (ccxt)':<22} {'chg%':>8} {'vol':>10}")
    print(f"  {'-'*14} {'-'*22} {'-'*8} {'-'*10}")
    for c in movers:
        print(f"  {c['symbol']:<14} {to_perp_symbol(c['base']):<22} "
              f"{c['change_24h']:>+7.2f}% {c['volume_24h']/1e6:>8.0f}M")
