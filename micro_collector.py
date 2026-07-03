"""
RECOLECTOR DE MICROESTRUCTURA (2026-07-03). MEXC no da histórico de libro de
órdenes ni de OI, así que se recolecta AHORA para poder investigar DESPUÉS
(imbalance del libro -> retorno siguiente, spreads por hora, etc.).

Cada pasada guarda, por símbolo del universo:
  - mid, medio-spread % (coste real de entrar a mercado en ese momento)
  - imbalance del top-5 del libro: (vol bids - vol asks) / (vol bids + vol asks)
  - funding rate actual
BD propia: micro_data.db (gitignored). Pensado para tarea programada cada 15 min
(TFZ_Micro_Collector). Una pasada = ~40 llamadas API suaves. Solo añade filas;
no toca NADA del bot ni de las mediciones.

Uso: python micro_collector.py         (una pasada y termina)
     python micro_collector.py --status (cuántas filas van)
"""
import os
# INSECURE_SSL lo pone el .cmd del PC; aquí no se fuerza.

import sys
import time
import sqlite3
from datetime import datetime, timezone
from data_fetcher import create_exchange

DB = os.environ.get("TFZ_MICRO_DB",
                    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "micro_data.db"))
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]


def _conn():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS micro_snapshots (
        ts TEXT, symbol TEXT, mid REAL, half_spread_pct REAL,
        imb5 REAL, funding_rate REAL,
        PRIMARY KEY (ts, symbol))""")
    c.commit()
    return c


def main():
    conn = _conn()
    if "--status" in sys.argv:
        n, first, last = conn.execute(
            "SELECT COUNT(*), MIN(ts), MAX(ts) FROM micro_snapshots").fetchone()
        print(f"micro_data.db: {n} filas | de {first} a {last}")
        return
    ex = create_exchange("mexc")
    ex.load_markets()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    ok = 0
    for s in SYMS:
        sym = f"{s}/USDT:USDT"
        try:
            ob = ex.fetch_order_book(sym, limit=5)
            bid, ask = ob["bids"][0][0], ob["asks"][0][0]
            mid = (bid + ask) / 2
            hs = (ask - bid) / mid / 2 * 100
            # MEXC devuelve filas de 3 campos (precio, volumen, ordenes) -> indexar
            vb = sum(r[1] for r in ob["bids"][:5])
            va = sum(r[1] for r in ob["asks"][:5])
            imb = (vb - va) / (vb + va) if (vb + va) > 0 else 0.0
            try:
                fr = ex.fetch_funding_rate(sym).get("fundingRate")
            except Exception:
                fr = None
            conn.execute("INSERT OR IGNORE INTO micro_snapshots VALUES (?,?,?,?,?,?)",
                         (ts, s, mid, round(hs, 5), round(imb, 5), fr))
            ok += 1
            time.sleep(ex.rateLimit / 1000)
        except Exception as e:
            print(f"  {s}: {e}")
    conn.commit()
    print(f"{ts} UTC: {ok}/{len(SYMS)} símbolos guardados")


if __name__ == "__main__":
    main()
