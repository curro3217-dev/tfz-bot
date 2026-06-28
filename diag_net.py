"""Diagnostico de red desde el runner: que endpoints de exchange son alcanzables."""
import ssl, urllib.request, time
ctx = ssl.create_default_context()

def test(name, url):
    try:
        t = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 diag"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            data = r.read()
        print(f"  OK   {name}: HTTP {r.status}, {len(data)} bytes, {time.time()-t:.1f}s")
    except Exception as e:
        print(f"  FAIL {name}: {type(e).__name__} - {str(e)[:90]}")

print("== endpoints directos ==")
test("Binance fapi ticker (scanner)", "https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=DOGEUSDT")
test("Binance fapi klines", "https://fapi.binance.com/fapi/v1/klines?symbol=DOGEUSDT&interval=5m&limit=5")
test("Binance fapi exchangeInfo", "https://fapi.binance.com/fapi/v1/exchangeInfo")
test("Binance SPOT api", "https://api.binance.com/api/v3/exchangeInfo?symbol=DOGEUSDT")
test("Bybit v5 klines", "https://api.bybit.com/v5/market/kline?category=linear&symbol=DOGEUSDT&interval=5&limit=5")

print("== ccxt ==")
try:
    import ccxt
    t = time.time(); ex = ccxt.binance({"options": {"defaultType": "future"}}); ex.load_markets()
    print(f"  OK   ccxt.binance load_markets: {len(ex.markets)} mercados, {time.time()-t:.1f}s")
    o = ex.fetch_ohlcv("DOGE/USDT:USDT", "5m", limit=5)
    print(f"  OK   ccxt.binance fetch_ohlcv: {len(o)} velas")
except Exception as e:
    print(f"  FAIL ccxt.binance: {type(e).__name__} - {str(e)[:120]}")
try:
    import ccxt
    ex = ccxt.bybit({"options": {"defaultType": "swap"}}); ex.load_markets()
    print(f"  OK   ccxt.bybit load_markets: {len(ex.markets)} mercados")
except Exception as e:
    print(f"  FAIL ccxt.bybit: {type(e).__name__} - {str(e)[:120]}")
print("FIN")
