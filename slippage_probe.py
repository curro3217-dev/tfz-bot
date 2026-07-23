"""
COMPROBACIÓN de slippage (sellada 2026-07-23, aviso del libro de Ross Cameron:
"el slippage era la mayor variable" — el backtest bonito se muere en real si el
coste de cruzar el libro es mayor que el asumido).

Nuestro modelo de costes asume 0.025% de slippage POR LADO (dentro del COST =
(0.02+0.025)*2 = 0.09% i/v de todas las mediciones). Este script mide el slippage
REAL desde el order book de MEXC, en las MISMAS monedas y momentos en que alerta
el bot, para ver si ese 0.025% se queda corto en alts recién movidas.

NO es una medición de edge (no hay veredicto ni criterio de N trades): es un
DIAGNÓSTICO del supuesto de coste. Solo lee order books; no toca ninguna medición.

Qué mide, por sondeo:
  - half-spread % = (ask - bid) / 2 / mid * 100  (coste MÍNIMO de cruzar, por lado)
  - impacto por tamaño: recorre el libro para llenar N USD (compra y venta),
    VWAP vs mid -> slippage % por lado para 250/500/1000 USD de notional.
    (notional de cada nivel = precio * contratos * contractSize del mercado.)

Fuentes de datos:
  - 'alert'    : capturado al DISPARAR una alerta F (paper.py llama record_for_alert
                 fail-silent). Es el momento representativo (la moneda acaba de moverse).
  - 'snapshot' : sondeo manual de la watchlist de movers AHORA (para tener datos ya;
                 menos representativo que el momento exacto de la alerta).

Uso:
  python slippage_probe.py BTC/USDT:USDT   # sondeo suelto (imprime, no guarda)
  python slippage_probe.py --snapshot      # sondea los movers de ahora y guarda
  python slippage_probe.py --status        # compara lo medido vs el 0.025%/lado
Env: TFZ_SLIP_DB para separar cuentas.
"""
import os
import sys
import sqlite3
import numpy as np

ASSUMED_PER_SIDE = 0.025          # % slippage/lado que asume el modelo de costes
NOTIONALS = [250, 500, 1000]      # USD para el impacto por tamaño
DEFAULT_NOTIONAL = 500            # el que se guarda por alerta
DB = os.environ.get("TFZ_SLIP_DB",
                    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "slippage_probe.db"))


def _conn(db=None):
    c = sqlite3.connect(db or DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS probes (
        ts TEXT, symbol TEXT, source TEXT, direction TEXT,
        mid REAL, half_spread_pct REAL,
        buy_slip_pct REAL, sell_slip_pct REAL, notional REAL,
        filled_ok INTEGER)""")
    return c


def _walk(levels, contract_size, notional_usd):
    """VWAP de llenar `notional_usd` recorriendo niveles [precio, contratos, ...].
    Devuelve (vwap, filled_ok). filled_ok=0 si el libro no da para tanto."""
    got_usd = 0.0
    cost = 0.0
    got_base = 0.0
    for lv in levels:
        px = float(lv[0]); contracts = float(lv[1])
        lvl_base = contracts * contract_size
        lvl_usd = lvl_base * px
        take_usd = min(lvl_usd, notional_usd - got_usd)
        if take_usd <= 0:
            break
        take_base = take_usd / px
        cost += take_base * px
        got_base += take_base
        got_usd += take_usd
        if got_usd >= notional_usd - 1e-9:
            break
    if got_base <= 0:
        return None, 0
    vwap = cost / got_base
    return vwap, int(got_usd >= notional_usd - 1e-6)


def probe(sym, notionals=None, ex=None):
    """Sondea un símbolo. Devuelve dict con half-spread e impacto por notional."""
    os.environ.setdefault("INSECURE_SSL", "1")
    from data_fetcher import _get_exchange
    ex = ex or _get_exchange("mexc")
    cs = float(ex.market(sym).get("contractSize") or 1.0)
    ob = ex.fetch_order_book(sym, limit=200)
    bid = float(ob["bids"][0][0]); ask = float(ob["asks"][0][0])
    mid = (bid + ask) / 2
    out = {"symbol": sym, "mid": mid,
           "half_spread_pct": (ask - bid) / 2 / mid * 100, "impact": {}}
    for N in (notionals or NOTIONALS):
        vb, okb = _walk(ob["asks"], cs, N)          # comprar -> subir por asks
        vs, oks = _walk(ob["bids"], cs, N)          # vender  -> bajar por bids
        buy = (vb - mid) / mid * 100 if vb else None
        sell = (mid - vs) / mid * 100 if vs else None
        out["impact"][N] = {"buy": buy, "sell": sell, "ok": okb and oks}
    return out


def record_for_alert(sig):
    """Guarda un sondeo al disparar una alerta F. La llama paper.py fail-silent."""
    try:
        p = probe(sig.symbol, notionals=[DEFAULT_NOTIONAL])
        imp = p["impact"][DEFAULT_NOTIONAL]
        c = _conn()
        c.execute("INSERT INTO probes(ts,symbol,source,direction,mid,half_spread_pct,"
                  "buy_slip_pct,sell_slip_pct,notional,filled_ok) "
                  "VALUES (datetime('now'),?,?,?,?,?,?,?,?,?)",
                  (sig.symbol, "alert", sig.direction, p["mid"], p["half_spread_pct"],
                   imp["buy"], imp["sell"], DEFAULT_NOTIONAL, int(imp["ok"])))
        c.commit(); c.close()
        return True
    except Exception:
        return False


def _snapshot():
    try:
        from scanner_bridge import get_perp_watchlist
        syms = get_perp_watchlist()
    except Exception as e:
        print(f"  no pude leer la watchlist ({e}); usando _universe.txt")
        try:
            syms = [s.strip() for s in open("_universe.txt").read().split(",") if s.strip()]
        except Exception:
            syms = []
    if not syms:
        print("  sin símbolos que sondear."); return
    os.environ.setdefault("INSECURE_SSL", "1")
    from data_fetcher import _get_exchange
    ex = _get_exchange("mexc")
    c = _conn()
    n = 0
    for sym in syms:
        try:
            p = probe(sym, ex=ex)
        except Exception:
            continue
        imp = p["impact"][DEFAULT_NOTIONAL]
        c.execute("INSERT INTO probes(ts,symbol,source,direction,mid,half_spread_pct,"
                  "buy_slip_pct,sell_slip_pct,notional,filled_ok) "
                  "VALUES (datetime('now'),?,?,?,?,?,?,?,?,?)",
                  (sym, "snapshot", None, p["mid"], p["half_spread_pct"],
                   imp["buy"], imp["sell"], DEFAULT_NOTIONAL, int(imp["ok"])))
        n += 1
        print(f"  {sym:20s} half-spread {p['half_spread_pct']:.4f}% | "
              f"impacto {DEFAULT_NOTIONAL}$ compra {imp['buy']:.4f}% venta {imp['sell']:.4f}%"
              f"{'' if imp['ok'] else '  (libro insuficiente)'}")
    c.commit(); c.close()
    print(f"\nsnapshot: {n} monedas sondeadas y guardadas")


def _status():
    c = _conn()
    rows = c.execute("SELECT * FROM probes").fetchall()
    print(f"SLIPPAGE PROBE — supuesto del modelo: {ASSUMED_PER_SIDE:.3f}%/lado, BD {DB}")
    if not rows:
        print("  sin sondeos aún. Corre --snapshot para un primer lote, o espera a")
        print("  que las alertas F vayan capturando el momento exacto.")
        return
    for src in ("alert", "snapshot"):
        g = [r for r in rows if r["source"] == src]
        if not g:
            continue
        hs = np.array([r["half_spread_pct"] for r in g])
        # coste real estimado por lado ~ half-spread + impacto de mercado del lado
        per_side = []
        for r in g:
            legs = [x for x in (r["buy_slip_pct"], r["sell_slip_pct"]) if x is not None]
            if legs:
                per_side.append(max(legs))       # el peor lado (conservador)
        ps = np.array(per_side) if per_side else np.array([np.nan])
        print(f"\n  FUENTE '{src}' (n={len(g)}):")
        print(f"    half-spread %/lado : mediana {np.median(hs):.4f} | "
              f"p90 {np.percentile(hs,90):.4f} | max {hs.max():.4f}")
        print(f"    slippage real/lado ({DEFAULT_NOTIONAL}$, peor lado): "
              f"mediana {np.nanmedian(ps):.4f} | p90 {np.nanpercentile(ps,90):.4f} | "
              f"max {np.nanmax(ps):.4f}")
        peor = np.nanmedian(ps)
        veredicto = ("el supuesto SE QUEDA CORTO" if peor > ASSUMED_PER_SIDE
                     else "el supuesto es SUFICIENTE o holgado")
        print(f"    -> mediana {np.nanmedian(ps):.4f}% vs supuesto {ASSUMED_PER_SIDE:.3f}%/lado: {veredicto}")
        insuf = sum(1 for r in g if not r["filled_ok"])
        if insuf:
            print(f"    (ojo: en {insuf}/{len(g)} el libro no daba para {DEFAULT_NOTIONAL}$ -> "
                  f"slippage real AÚN MAYOR)")
    c.close()


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    if args[0] == "--status":
        _status()
    elif args[0] == "--snapshot":
        _snapshot()
    else:
        p = probe(args[0])
        print(f"{p['symbol']}  mid {p['mid']:.6g}  half-spread {p['half_spread_pct']:.4f}%/lado")
        for N, d in p["impact"].items():
            b = f"{d['buy']:.4f}" if d['buy'] is not None else "?"
            s = f"{d['sell']:.4f}" if d['sell'] is not None else "?"
            print(f"  {N:5d}$: compra {b}%  venta {s}%  {'ok' if d['ok'] else 'LIBRO INSUFICIENTE'}")


if __name__ == "__main__":
    main()
