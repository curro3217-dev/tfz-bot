"""
LECTOR informativo del impacto del FUNDING en las mediciones multi-día (2026-07-23).

Lee en SOLO-LECTURA las BD de premium/EMA/Ichimoku, reconstruye sus trades CERRADOS
(sin tocar nada), y reporta el PnL SELLADO (como está) junto a un PnL "con funding"
(informativo) usando funding.funding_pct. El primario sellado NO se altera: esto es
una columna paralela, como GARCH lo es del EMA.

Solo importa en holds largos (ver funding.py): intradía es negligible, aquí no.
Sin trades cerrados -> no hace ni una llamada de red (rápido, seguro en el panel).

Uso: python funding_impact.py [--status]
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
import sqlite3
import numpy as np
import pandas as pd
from funding import funding_pct

BASE = os.path.dirname(os.path.abspath(__file__))


def _ms(date_str):
    return int(pd.Timestamp(str(date_str)).value // 1_000_000)   # 00:00 UTC de esa fecha


def _ro(path):
    return sqlite3.connect("file:" + path + "?mode=ro", uri=True)


def _premium():
    """(nombre, lista de (symbol_perp, entry_ms, exit_ms, dir, pnl_sellado))."""
    db = os.environ.get("TFZ_PREM_DB", os.path.join(BASE, "premium_paper.db"))
    out = []
    try:
        c = _ro(db); c.row_factory = sqlite3.Row
        for r in c.execute("SELECT * FROM prem_trades WHERE status='closed'"):
            sym = r["symbol"].split("/")[0] + "/USDT:USDT"    # 'BTC' -> 'BTC/USDT:USDT'
            out.append((sym, _ms(r["entry_date"]), _ms(r["exit_date"]), 1, r["pnl_pct"]))
        c.close()
    except Exception:
        pass
    return "Premium Coinbase (long 7d)", out


def _pairs(db, sym_perp, table):
    """Reconstruye trades up->dn (largo) de ema_events/ichi_events (solo cerrados)."""
    out = []
    try:
        c = _ro(db); c.row_factory = sqlite3.Row
        rows = c.execute(f"SELECT * FROM {table} ORDER BY signal_date").fetchall()
        c.close()
    except Exception:
        return out
    entry = None
    for r in rows:
        if r["direction"] == "up" and entry is None:
            entry = r
        elif r["direction"] == "dn" and entry is not None:
            pnl = (r["fill_px"] / entry["fill_px"] - 1) * 100 - (0.02 + 0.025) * 2
            out.append((sym_perp, _ms(entry["fill_date"]), _ms(r["fill_date"]), 1, pnl))
            entry = None
    return out


def measurements():
    m = [_premium()]
    m.append(("EMA 9/21 BTC (long)",
              _pairs(os.environ.get("TFZ_EMA_DB", os.path.join(BASE, "ema_cross_paper.db")),
                     "BTC/USDT:USDT", "ema_events")))
    m.append(("Ichimoku BTC (long)",
              _pairs(os.environ.get("TFZ_ICHI_DB", os.path.join(BASE, "ichimoku_paper.db")),
                     "BTC/USDT:USDT", "ichi_events")))
    return m


def main():
    print("=== IMPACTO DEL FUNDING (informativo; PnL sellado NO se toca) ===")
    any_trade = False
    for nombre, trades in measurements():
        if not trades:
            print(f"  {nombre}: 0 trades cerrados (sin impacto que medir aún)")
            continue
        any_trade = True
        sellado, confund, fund = [], [], []
        for sym, ent, exi, d, pnl in trades:
            if pnl is None:
                continue
            f = funding_pct(sym, ent, exi, d)
            sellado.append(pnl); fund.append(f); confund.append(pnl + f)
        if not sellado:
            print(f"  {nombre}: sin PnL numérico")
            continue
        s = np.array(sellado); cf = np.array(confund); fn = np.array(fund)
        print(f"  {nombre} (n={len(s)}):")
        print(f"    PnL SELLADO   media {s.mean():+.4f}%")
        print(f"    funding medio       {fn.mean():+.4f}%  (viento {'en contra' if fn.mean()<0 else 'a favor'})")
        print(f"    PnL con funding media {cf.mean():+.4f}%  (informativo)")
    if not any_trade:
        print("  (todas a 0 eventos; el lector está listo para cuando cierren trades)")


if __name__ == "__main__":
    main()
