"""
Helper de FUNDING (perpetuos MEXC, intervalo 8h) + diagnóstico de materialidad.

Motivo: TODAS las mediciones dicen "funding NO modelado". El usuario opera perps,
así que un hold que cruza timestamps de funding paga/cobra funding. Este módulo
(a) da la función reutilizable para calcular el funding de una posición, y
(b) como diagnóstico, cuantifica cuánto pesa el funding en nuestros holds típicos
(weekend 24h, EMA/Ichimoku días, premium 7d) para decidir si hay que incorporarlo.

Convención: en perps, si la tasa es POSITIVA los LARGOS pagan a los cortos. Por eso
la contribución del funding al PnL de una posición es:
    funding_pct = -direction * sum(tasas de los timestamps cruzados) * 100
(long con tasas positivas -> funding negativo = coste).

NO toca ninguna medición sellada: es un módulo aparte + informativo, como
slippage_probe. Cachea el histórico por símbolo en el proceso.
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
import time
import numpy as np

_CACHE = {}


def _history(symbol, want_since_ms):
    """Histórico de funding [(ts_ms, rate), ...] desde want_since_ms (paginado)."""
    key = symbol
    if key in _CACHE and _CACHE[key][0] <= want_since_ms:
        return _CACHE[key][1]
    from data_fetcher import _get_exchange
    ex = _get_exchange("mexc")
    out = []
    since = want_since_ms
    for _ in range(20):                       # tope de páginas
        try:
            batch = ex.fetch_funding_rate_history(symbol, since=since, limit=200)
        except Exception:
            break
        if not batch:
            break
        for r in batch:
            out.append((int(r["timestamp"]), float(r["fundingRate"])))
        nxt = batch[-1]["timestamp"] + 1
        if nxt <= since or len(batch) < 200:
            since = nxt
            break
        since = nxt
        time.sleep(ex.rateLimit / 1000)
    out = sorted(set(out))
    _CACHE[key] = (want_since_ms, out)
    return out


def funding_pct(symbol, entry_ts_ms, exit_ts_ms, direction):
    """Contribución del funding al PnL (%) de una posición mantenida
    (entry_ts, exit_ts] en la dirección dada (1 long, -1 short)."""
    hist = _history(symbol, entry_ts_ms - 8 * 3600 * 1000)
    s = sum(rate for ts, rate in hist if entry_ts_ms < ts <= exit_ts_ms)
    return -direction * s * 100


def _diag():
    """Diagnóstico: cuánto pesa el funding en nuestros holds típicos."""
    SYMS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "AVAX", "LINK", "ADA", "SUI",
            "ENA", "OP", "ARB", "1000PEPE", "WLD", "FET", "INJ", "TIA", "NEAR", "APT"]
    now = int(time.time() * 1000)
    since = now - 12 * 24 * 3600 * 1000        # ~12 días
    per8h_abs, per8h_signed = [], []
    for s in SYMS:
        h = _history(s + "/USDT:USDT", since)
        rates = [r for _, r in h]
        if len(rates) < 5:
            continue
        per8h_abs.append(np.mean(np.abs(rates)) * 100)
        per8h_signed.append(np.mean(rates) * 100)
    a = np.array(per8h_abs); sg = np.array(per8h_signed)
    print("=== FUNDING — materialidad (MEXC, ~12 dias, 20 símbolos) ===")
    print(f"tasa por 8h: |media| {a.mean():.4f}% | media con signo {sg.mean():+.4f}% "
          f"(positivo = largos pagan)")
    print(f"\ncoste de funding por HOLD (direccional, escenario 'largo en mercado")
    print(f"con funding positivo' = viento en contra típico):")
    COST_TX = (0.02 + 0.025) * 2
    for horas, nombre in [(1, "postpump / F alertas (~1h)"),
                          (24, "weekend vie->sab (24h)"),
                          (72, "EMA/Ichimoku (~3 dias)"),
                          (168, "premium Coinbase (7 dias)")]:
        n8 = horas / 8.0
        cost = sg.mean() * n8                   # % que paga un largo de media
        print(f"  {nombre:34s}: ~{n8:.1f} pagos | funding ~{cost:+.4f}% "
              f"| vs coste tx {COST_TX:.2f}%  ({abs(cost)/COST_TX*100:.0f}% del coste tx)")
    print(f"\nNota: el signo real depende de la dirección y del régimen de funding;")
    print(f"esto es la magnitud típica para dimensionar si merece modelarlo.")


if __name__ == "__main__":
    _diag()
