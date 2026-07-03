"""
EXPLORACIÓN #4: FUNDING COMO SEÑAL, batería completa (2026-07-03).

Contexto: el fix de timestamps en explore_funding.py destapó que el test contrarian
NUNCA se había ejecutado de verdad (decía "sin señales" por un bug de escala). Esta
batería lo prueba en serio, con las reglas de comparación limpia: TODAS las variantes
en la MISMA tanda, mismos datos, y solo cambia la variable de cada eje.

Ejes probados (todas las combinaciones):
  - dirección:  contrarian (funding extremo -> apostar giro) vs follow (ir con la masa)
  - hold:       8h vs 24h
  - umbral:     decil (10%/90%) vs percentil 5 (5%/95%)

Datos: funding de BYBIT (~1200 eventos = ~400 días por símbolo; MEXC solo da ~200) +
precios 1h de la cache (MEXC). Los funding rates entre venues van muy pegados (los
arbitrajistas los igualan), pero se anota como aproximación.

Contabilidad del funding en el PnL: hold_h/8 pagos a la tasa del evento (aprox: la
tasa cambia tras la entrada). El contrarian lo COBRA, el follow lo PAGA.

Estadística: n, winrate, expectancy, IC95 de la media, y split temporal 70/30
(IS/OOS): una variante solo "vale" si el IC95 EXCLUYE cero y el OOS aguanta.
Costes: modelo MEXC verificado (0.02+0.025 por lado). Solo lectura, no toca nada.

Uso: python explore_funding_deep.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import time
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached, create_exchange

COST_MEXC = (0.02 + 0.025) * 2   # % ida y vuelta
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM"]
FUND_EX = os.environ.get("FUND_EX", "bybit")   # bybit = ~1200 eventos/simbolo


def funding_hist(ex, sym, pages=6):
    out = []; until = None
    for _ in range(pages):
        try:
            params = {} if until is None else {"until": until}
            h = ex.fetch_funding_rate_history(sym, limit=200, params=params)
        except Exception:
            break
        if not h:
            break
        out = h + out
        until = h[0]["timestamp"] - 1
        if len(h) < 200:
            break
        time.sleep(ex.rateLimit / 1000)
    seen = set(); res = []
    for x in sorted(out, key=lambda z: z["timestamp"]):
        if x["timestamp"] not in seen:
            seen.add(x["timestamp"]); res.append(x)
    return res


def stats_line(p):
    p = np.array(p)
    if len(p) < 2:
        return "n<2"
    m = p.mean(); se = p.std(ddof=1) / np.sqrt(len(p))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    sig = "IC95 EXCLUYE 0" if lo > 0 or hi < 0 else "ic95 incluye 0"
    return (f"n {len(p):5d} | win {(p > 0).mean() * 100:4.1f}% | exp {m:+.3f}% "
            f"[{lo:+.3f},{hi:+.3f}] {sig} | suma {p.sum():+.0f}%")


def main():
    ex = create_exchange(FUND_EX)
    ex.load_markets()
    cfg = config_for_timeframe(TFZConfig(), "1h")

    # trades[(modo, hold, umbral)] = lista de (timestamp, pnl_neto)
    trades = {}
    raw_rows = []   # por-trade con componentes separados -> CSV para robustez
    for s in SYMS:
        sym = f"{s}/USDT:USDT"
        fh = funding_hist(ex, sym)
        if len(fh) < 100:
            print(f"  {s}: funding insuf ({len(fh)})")
            continue
        rates = np.array([x["fundingRate"] for x in fh])
        fts = np.array([x["timestamp"] for x in fh])
        try:
            d = fetch_ohlcv_cached(sym, "1h", limit=20000, config=cfg)
        except Exception as e:
            print(f"  {s}: sin velas ({e})")
            continue
        ts = d["timestamp"].values.astype("datetime64[ms]").astype("int64")
        cl = d["close"].values
        for q in (0.10, 0.05):
            hi_thr = np.quantile(rates, 1 - q); lo_thr = np.quantile(rates, q)
            for hold_h in (8, 24):
                for r, t in zip(rates, fts):
                    if lo_thr < r < hi_thr:
                        continue
                    idx = np.searchsorted(ts, t)
                    if idx <= 0 or idx + hold_h >= len(ts):
                        continue
                    entry = cl[idx]; exit_px = cl[idx + hold_h]
                    up = (exit_px - entry) / entry * 100        # retorno long
                    fund = abs(r) * 100 * (hold_h / 8)           # pagos de funding aprox
                    # contrarian: contra la masa (funding + -> short), COBRA funding
                    pnl_c = (-up if r > 0 else up) + fund - COST_MEXC
                    # follow: con la masa (funding + -> long), PAGA funding
                    pnl_f = (up if r > 0 else -up) - fund - COST_MEXC
                    trades.setdefault(("contrarian", hold_h, q), []).append((t, pnl_c))
                    trades.setdefault(("follow", hold_h, q), []).append((t, pnl_f))
                    raw_rows.append({"symbol": s, "ts": t, "rate": r, "umbral": q,
                                     "hold_h": hold_h, "ret_long": up, "fund": fund})
        print(f"  {s:7} {len(fh)} eventos de funding")

    print(f"\n=== BATERÍA FUNDING ({FUND_EX}, costes MEXC {COST_MEXC:.2f}% i/v) ===")
    for key in sorted(trades):
        modo, hold_h, q = key
        rows = sorted(trades[key])
        pnls = [p for _, p in rows]
        cut = int(len(rows) * 0.7)
        is_p = [p for _, p in rows[:cut]]
        oos_p = [p for _, p in rows[cut:]]
        print(f"\n[{modo:10s} hold {hold_h:2d}h umbral {q:.0%}]")
        print(f"  TOTAL {stats_line(pnls)}")
        print(f"  IS70  {stats_line(is_p)}")
        print(f"  OOS30 {stats_line(oos_p)}")
    if raw_rows:
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "funding_deep_trades.csv")
        pd.DataFrame(raw_rows).to_csv(out, index=False)
        print(f"\nPor-trade con componentes -> {out}")
    print("\nNOTA: señales solapadas entre símbolos (no independientes) -> el IC95 real")
    print("es más ancho que el mostrado. Funding de bybit como proxy del mercado.")


if __name__ == "__main__":
    main()
