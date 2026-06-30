"""Descarga la lista de servidores VPN GRATIS de VPN Gate (Univ. de Tsukuba, Japon),
elige el mejor de un pais NO bloqueado por Binance/Bybit y escribe vpn.ovpn.
Uso: python vpn_pick.py JP   (o KR, etc.)"""
import urllib.request, base64, csv, ssl, sys

ctx = ssl._create_unverified_context()
country = sys.argv[1] if len(sys.argv) > 1 else "JP"
url = "https://www.vpngate.net/api/iphone/"
data = urllib.request.urlopen(url, context=ctx, timeout=60).read().decode("utf-8", "replace")
lines = [l for l in data.splitlines() if l.strip()]
hdr_i = next(i for i, l in enumerate(lines) if l.startswith("#HostName"))
header = lines[hdr_i].lstrip("#").split(",")
idx = {name: i for i, name in enumerate(header)}
rows = list(csv.reader([l for l in lines[hdr_i + 1:] if not l.startswith("*")]))

best = None
for r in rows:
    if len(r) <= idx.get("OpenVPN_ConfigData_Base64", 14):
        continue
    try:
        if r[idx["CountryShort"]].upper() == country.upper() and r[idx["OpenVPN_ConfigData_Base64"]]:
            score = int(r[idx["Score"]])
            if best is None or score > best[0]:
                best = (score, r)
    except Exception:
        continue

if not best:
    print(f"sin servidor para {country}"); sys.exit(1)
conf = base64.b64decode(best[1][idx["OpenVPN_ConfigData_Base64"]]).decode("utf-8", "replace")
with open("vpn.ovpn", "w") as f:
    f.write(conf)
print(f"servidor {country}: {best[1][idx['HostName']]} {best[1][idx['IP']]} (score {best[0]})")
