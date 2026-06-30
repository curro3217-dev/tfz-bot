"""Se ejecuta YA conectado a la VPN: muestra la IP/pais de salida y prueba si Binance
futuros y Bybit responden (si el bloqueo desaparece por salir desde Japon)."""
import urllib.request, ssl, json

ctx = ssl.create_default_context()

def g(name, url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        r = urllib.request.urlopen(req, context=ctx, timeout=20)
        d = r.read()
        print(f"  VELAS {name}: HTTP {r.status}, {len(d)} bytes")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read()[:90].decode("utf-8", "replace").replace("\n", " ")
        except Exception:
            pass
        print(f"  BLOCK {name}: HTTP {e.code} | {body}")
    except Exception as e:
        print(f"  FAIL  {name}: {type(e).__name__} {str(e)[:70]}")

try:
    ip = json.load(urllib.request.urlopen("https://ipinfo.io/json", context=ctx, timeout=20))
    print(f"IP de salida: {ip.get('ip')} | pais: {ip.get('country')} | {ip.get('org','')}")
except Exception as e:
    print(f"no pude leer la IP de salida: {e}")

print("\nPrueba de endpoints a traves de la VPN:")
g("Binance fapi klines", "https://fapi.binance.com/fapi/v1/klines?symbol=DOGEUSDT&interval=5m&limit=5")
g("Bybit v5 klines", "https://api.bybit.com/v5/market/kline?category=linear&symbol=DOGEUSDT&interval=5&limit=5")
print("FIN")
