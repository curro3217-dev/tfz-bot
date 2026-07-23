"""
EL LISTÓN DE COSTE (2026-07-23): ¿qué esperanza/acierto mínimo necesita una idea
para ser rentable en cripto DESPUÉS de la fricción real? Reúne lo aprendido esta
semana: comisión + slippage (diagnóstico slippage_probe) + funding (funding.py).

La idea: la mayoría de estrategias externas mueren no por falta de señal sino porque
el coste se come el edge (ver PO3 #44). Esta herramienta lo cuantifica ANTES de
gastar tiempo midiendo: le das el stop (R), el R:R y el hold, y te dice el acierto
mínimo para empatar con costes reales — y cuánto lo inflan los costes vs el ideal.

Matemática (bracket con objetivo rr·R, stop R, coste total c por trade):
  break-even  p* = (R + c) / (R·(rr+1))      [sin coste: p = 1/(rr+1)]
  El asesino es c/R: si el coste es una fracción grande de R, p* se dispara.

Coste total por trade (ida+vuelta) = 2·comisión + 2·slippage/lado + |funding del hold|.

Uso:
  python cost_bar.py --stop 0.156 --rr 2 --hold 3            # stop en %, hold en horas
  python cost_bar.py --stop 0.5 --rr 3 --hold 168 --symbol BTC --live
Env: INSECURE_SSL=1 para las llamadas --live.
"""
import os
import sys
import argparse

FEE_SIDE = 0.02            # % comisión taker MEXC por lado (verificado)
# slippage/lado por defecto segun liquidez (del diagnostico slippage_probe, 23-jul):
SLIP_DEFAULT = {"major": 0.010, "mover": 0.050}   # % por lado
FUNDING_8H_DEFAULT = 0.006  # % por 8h, |media| tipica MEXC (regimen tranquilo)


def slippage_side(symbol=None, live=False, tier="mover"):
    """% de slippage por lado. Live -> lo mide del order book; si no, por tier."""
    if live and symbol:
        try:
            from slippage_probe import probe
            sym = symbol if "/" in symbol else symbol + "/USDT:USDT"
            p = probe(sym, notionals=[500])
            imp = p["impact"][500]
            legs = [x for x in (imp["buy"], imp["sell"]) if x is not None]
            return max(legs) if legs else SLIP_DEFAULT[tier]
        except Exception:
            pass
    return SLIP_DEFAULT[tier]


def funding_cost(symbol, hold_hours, direction=1, live=False):
    """|coste de funding| del hold (%). Live -> histórico real; si no, estimación."""
    n8 = hold_hours / 8.0
    if live and symbol:
        try:
            import time
            from funding import funding_pct
            now = int(time.time() * 1000)
            f = funding_pct(symbol + "/USDT:USDT" if "/" not in symbol else symbol,
                            now - int(hold_hours * 3600 * 1000), now, direction)
            return abs(f)
        except Exception:
            pass
    return n8 * FUNDING_8H_DEFAULT


def cost_roundtrip(stop_pct, hold_hours, symbol=None, live=False, tier="mover", direction=1):
    slip = slippage_side(symbol, live, tier)
    fees = 2 * FEE_SIDE
    slp = 2 * slip
    fund = funding_cost(symbol, hold_hours, direction, live)
    total = fees + slp + fund
    return {"fees": fees, "slippage": slp, "funding": fund, "total": total,
            "slip_side": slip}


def breakeven_winrate(rr, stop_pct, cost_pct):
    return (stop_pct + cost_pct) / (stop_pct * (rr + 1))


def report(stop_pct, rr, hold_hours, symbol=None, live=False, tier="mover"):
    c = cost_roundtrip(stop_pct, hold_hours, symbol, live, tier)
    p0 = 1.0 / (rr + 1)                                  # break-even IDEAL (sin coste)
    p = breakeven_winrate(rr, stop_pct, c["total"])
    print(f"=== LISTÓN DE COSTE ===")
    quien = f"{symbol} (live)" if (symbol and live) else f"tier {tier}"
    print(f"  stop (R) {stop_pct:.3f}% | R:R 1:{rr:g} | hold {hold_hours:g}h | {quien}")
    print(f"  coste/trade: comision {c['fees']:.3f}% + slippage {c['slippage']:.3f}% "
          f"({c['slip_side']:.3f}%/lado) + funding {c['funding']:.3f}% = "
          f"TOTAL {c['total']:.3f}%")
    print(f"  coste / R = {c['total']/stop_pct:.2f}  (si es alto, el coste manda)")
    print(f"  acierto para EMPATAR: {p*100:.1f}%   (ideal sin coste: {p0*100:.1f}%)")
    print(f"  -> el coste sube el listón {(p-p0)*100:+.1f} puntos de acierto")
    if p >= 0.55:
        print(f"  VEREDICTO: listón >=55% -> muy difícil para una entrada mecánica. Sospechoso.")
    elif p >= p0 + 0.10:
        print(f"  VEREDICTO: el coste sube el listón >10 puntos -> el edge tiene que ser grande.")
    else:
        print(f"  VEREDICTO: el coste no distorsiona mucho -> viable si la señal predice.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", type=float, required=True, help="stop (R) en %% del precio")
    ap.add_argument("--rr", type=float, default=2.0, help="ratio objetivo (rr:1)")
    ap.add_argument("--hold", type=float, default=1.0, help="duracion del hold en horas")
    ap.add_argument("--symbol", default=None, help="p.ej. BTC (para --live)")
    ap.add_argument("--live", action="store_true", help="mide slippage/funding reales")
    ap.add_argument("--tier", default="mover", choices=["major", "mover"])
    a = ap.parse_args()
    report(a.stop, a.rr, a.hold, a.symbol, a.live, a.tier)


if __name__ == "__main__":
    main()
