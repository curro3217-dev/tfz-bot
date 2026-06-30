"""Test EXHAUSTIVO de MEXC desde el runner de GitHub (IP EE.UU.):
- ¿Responde MEXC con velas? (la pregunta clave: no esta geo-bloqueado como Binance/Bybit)
- Cobertura: cuantas de las 30 monedas del bot existen en MEXC perp (con mapeo de nombres)
- Profundidad: baja ~1000 velas por moneda en 1h / 15m / 5m
Reporta por moneda y un resumen final.
"""
import time

UNIVERSE = ("SOL VELVET LAB AGLD HYPE SPCX ZEC XRP SOXL SNDK MU SLX AAVE CL RE DOGE "
            "WLD SYN NEAR BNB BEAT JTO MAGMA SUI 1000PEPE MSTR ALLO PUNDIX WIF AVAX").split()
TFS = ["1h", "15m", "5m"]
LIMIT = 1000

import ccxt
ex = ccxt.mexc({"enableRateLimit": True, "timeout": 25000, "options": {"defaultType": "swap"}})
t0 = time.time()
mk = ex.load_markets()
swaps = {s for s, m in mk.items() if m.get("swap") and m.get("settle") == "USDT"}
print(f"MEXC load_markets OK: {len(mk)} mercados, {len(swaps)} perp USDT, {time.time()-t0:.1f}s\n")

def resolve(base):
    """Devuelve el simbolo MEXC para una base del bot, probando alternativas."""
    cands = [f"{base}/USDT:USDT"]
    if base.startswith("1000"):
        cands.append(f"{base[4:]}/USDT:USDT")          # 1000PEPE -> PEPE (misma % )
    cands.append(f"{base}STOCK/USDT:USDT")              # acciones tokenizadas
    for c in cands:
        if c in swaps:
            return c
    return None

ok_coins, miss, total_candles = [], [], 0
print(f"{'MONEDA':10s} {'SIMBOLO MEXC':20s} {'1h':>6s} {'15m':>6s} {'5m':>6s}  ultima_close")
print("-" * 70)
for base in UNIVERSE:
    sym = resolve(base)
    if not sym:
        miss.append(base)
        print(f"{base:10s} {'(no existe)':20s}    -      -      -")
        continue
    counts, last = [], None
    for tf in TFS:
        try:
            o = ex.fetch_ohlcv(sym, tf, limit=LIMIT)
            counts.append(len(o)); total_candles += len(o)
            if tf == "1h" and o:
                last = o[-1][4]
        except Exception as e:
            counts.append(-1)
    flag = "" if all(c > 0 for c in counts) else "  <-- fallo en alguna TF"
    ok_coins.append(base)
    note = f"  ({sym.split('/')[0]})" if sym.split('/')[0] != base else ""
    print(f"{base:10s} {sym:20s} {counts[0]:>6d} {counts[1]:>6d} {counts[2]:>6d}  {last}{flag}{note}")

print("-" * 70)
print(f"\nRESUMEN:")
print(f"  Monedas con datos en MEXC: {len(ok_coins)}/{len(UNIVERSE)} ({100*len(ok_coins)//len(UNIVERSE)}%)")
print(f"  No encontradas: {', '.join(miss) if miss else '(ninguna)'}")
print(f"  Total velas descargadas: {total_candles}")
print(f"  MEXC alcanzable desde GitHub: {'SI' if total_candles > 0 else 'NO'}")
print("FIN")
