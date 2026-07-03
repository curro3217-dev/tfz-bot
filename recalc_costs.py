"""
DOBLE CONTABILIDAD de costes (solo lectura, no modifica NADA).

Recalcula la expectancy de los trades paper CERRADOS bajo dos modelos de coste:
  - ANTIGUO (Bybit/Binance): comision 0.075%/lado + slippage 0.025%/lado, funding 0
  - MEXC (verificado contra la API 2026-07-03): taker 0.02%/lado + slippage
    0.025%/lado + funding 0.01%/8h (baseline; long paga funding positivo)

El PnL BRUTO se reconstruye desde los PRECIOS guardados (entry_price/exit_price y
direccion), no desde el pnl_pct neto (que depende del modelo activo cuando cerro el
trade). Como control, tambien reconstruye el neto con cada modelo y lo compara con
el pnl_pct guardado para decir con que modelo se cerro cada trade.

Uso:
  python recalc_costs.py                 # cuenta del PC (tfz_data.db)
  TFZ_DB=github_state/tfz_data.db python recalc_costs.py   # cuenta de GitHub
"""
import os
import sqlite3
import numpy as np
import pandas as pd

DB = os.environ.get("TFZ_DB", os.path.join(os.path.dirname(__file__), "tfz_data.db"))

# (comision %/lado, slippage %/lado, funding %/8h)
MODELS = {
    "ANTIGUO (bybit/binance)": (0.075, 0.025, 0.0),
    "MEXC (verificado)":       (0.02,  0.025, 0.01),
}
THRESHOLD = 0.3   # criterio pre-registrado: expectancy neta > +0.3%/trade


def gross_pnl(row) -> float:
    e, x = row["entry_price"], row["exit_price"]
    if not e or x is None:
        return None
    if row["direction"] == "long":
        return (x - e) / e * 100
    return (e - x) / e * 100


def cost_of(row, commission, slippage, funding_8h) -> float:
    cost = (commission + slippage) * 2
    if funding_8h > 0 and row["entry_ts"] and row["exit_ts"]:
        try:
            hours = max(0.0, (pd.to_datetime(row["exit_ts"]) - pd.to_datetime(row["entry_ts"]))
                        .total_seconds() / 3600.0)
            cost += funding_8h * (hours / 8.0)
        except Exception:
            pass
    return cost


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM paper_trades WHERE status='closed' ORDER BY exit_ts").fetchall()
    print(f"BD: {DB}")
    print(f"Trades cerrados: {len(rows)}")
    if not rows:
        print("Nada que recalcular todavia.")
        return

    usable = [r for r in rows if gross_pnl(r) is not None]
    gross = np.array([gross_pnl(r) for r in usable])
    stored = np.array([r["pnl_pct"] for r in rows if r["pnl_pct"] is not None])
    print(f"\n{'modelo':28} {'expectancy':>12} {'total':>9} {'win%':>6} {'coste medio':>12}")
    for name, (c, s, f) in MODELS.items():
        nets = np.array([g - cost_of(r, c, s, f) for r, g in zip(usable, gross)])
        match = sum(1 for r, net in zip(usable, nets)
                    if r["pnl_pct"] is not None and abs(net - r["pnl_pct"]) < 0.02)
        wr = (nets > 0.05).mean() * 100
        verdict = "PASA" if nets.mean() > THRESHOLD else "no pasa"
        print(f"{name:28} {nets.mean():+11.3f}% {nets.sum():+8.1f}% {wr:5.1f}% "
              f"{gross.mean() - nets.mean():11.3f}%"
              f"   [{verdict} el umbral {THRESHOLD:+.1f}%] (coincide con lo guardado: {match}/{len(nets)})")
    print(f"\n(guardado en BD: expectancy {stored.mean():+.3f}% sobre {len(stored)} trades — "
          f"mezcla del modelo vigente en cada cierre)")
    print("Criterio pre-registrado (2026-07-03): expectancy neta > +0.3%/trade con IC95% "
          "excluyendo cero, a ~200 trades cerrados. Este script NO evalua el IC95%; "
          "para eso, main.py paper --status + validate_oos.py cuando toque.")


if __name__ == "__main__":
    main()
