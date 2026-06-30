"""Test desde el runner de GitHub (IP EE.UU.): ¿algun dominio REGIONAL/alternativo de
Bybit o Binance responde con velas en vez de 403/451? Lee tambien el cuerpo del error
para distinguir bloqueo CloudFront/geo de un fallo de DNS.
"""
import ssl, urllib.request, urllib.error, time, socket

ctx = ssl.create_default_context()
socket.setdefaulttimeout(15)

def test(name, url):
    t = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            data = r.read()
        body = data[:120].decode("utf-8", "replace")
        ok = '"retCode":0' in body or '"result"' in body or len(data) > 200
        print(f"  {'VELAS' if ok else 'RESP '} {name}: HTTP {r.status}, {len(data)}b, {time.time()-t:.1f}s | {body[:80]}")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read()[:140].decode("utf-8", "replace").replace("\n", " ")
        except Exception:
            pass
        print(f"  BLOCK {name}: HTTP {e.code} | {body[:110]}")
    except Exception as e:
        print(f"  FAIL  {name}: {type(e).__name__} - {str(e)[:80]}")

KL = "/v5/market/kline?category=linear&symbol=DOGEUSDT&interval=5&limit=5"

print("== BYBIT: dominio principal (control, esperamos 403) ==")
test("api.bybit.com", "https://api.bybit.com" + KL)

print("\n== BYBIT: dominios alternativos / regionales ==")
for host in [
    "api.bytick.com",      # dominio espejo historico de Bybit
    "api.bybit.eu",        # EU/EEA
    "api.bytick.nl",       # Paises Bajos
    "api.bybit.nl",
    "api.bybit-tr.com",    # Turquia
    "api.bybit.kz",        # Kazajistan (tentativo)
    "api.bybitglobal.com",
]:
    test(host, f"https://{host}" + KL)

print("\n== BINANCE: alternativos (por comparar) ==")
test("data-api.binance.vision SPOT", "https://data-api.binance.vision/api/v3/klines?symbol=DOGEUSDT&interval=5m&limit=5")
test("fapi.binance.com FUT (control 451)", "https://fapi.binance.com/fapi/v1/klines?symbol=DOGEUSDT&interval=5m&limit=5")
test("fapi1.binance.com", "https://fapi1.binance.com/fapi/v1/klines?symbol=DOGEUSDT&interval=5m&limit=5")
print("\nFIN")
