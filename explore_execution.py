"""
EXPLORACIÓN #28: EJECUCIÓN MAKER en el vie->sáb (2026-07-03).

Las reglas pagan taker (0.02% + slippage 0.025% por lado). Una orden LIMIT al precio
de cierre del viernes cobraría maker (0%) y sin spread... si se llena. La trampa
documentada: las limit se llenan MÁS cuando el precio va en contra (selección
adversa). Aquí se mide con velas de 5m de MEXC:
  - tasa de llenado: ¿el precio toca el cierre del viernes en la 1ª hora del sábado?
    (long: low <= entry; short: high >= entry)
  - selección adversa: PnL de los trades LLENADOS vs NO llenados
  - neto de la táctica "limit 1h, si no llena -> market": ¿mejora al taker puro?
Muestra: 10 símbolos líquidos x sábados de 2026 (llamadas 5m acotadas).

Solo lectura. Uso: python explore_execution.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import time
import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached, create_exchange

TAKER, SLIP, MAKER = 0.02, 0.025, 0.0
COST_TAKER_RT = (TAKER + SLIP) * 2
SYMS = ["BTC","ETH","SOL","DOGE","XRP","LINK","AVAX","LTC","ADA","TON"]


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    ex = create_exchange("mexc")
    ex.load_markets()
    rows = []
    for s in SYMS:
        sym = f"{s}/USDT:USDT"
        d = fetch_ohlcv_cached(sym, "1h", limit=20000, config=cfg)
        daily = d.set_index("timestamp")["close"].resample("1D").last().dropna()
        ret = daily.pct_change()
        sabados = [t for t in daily.index
                   if t.weekday() == 5 and t.year == 2026 and t - pd.Timedelta(days=1) in ret.index]
        for t in sabados:
            fr = ret[t - pd.Timedelta(days=1)]
            if pd.isna(fr) or fr == 0 or pd.isna(ret.get(t)):
                continue
            entry = daily[t - pd.Timedelta(days=1)]
            sgn = np.sign(fr)
            since = int(t.timestamp() * 1000)
            try:
                c5 = ex.fetch_ohlcv(sym, "5m", since=since, limit=12)  # 1ª hora
                time.sleep(ex.rateLimit / 1000)
            except Exception:
                continue
            if len(c5) < 6:
                continue
            lows = min(x[3] for x in c5)
            highs = max(x[2] for x in c5)
            filled = (lows <= entry) if sgn > 0 else (highs >= entry)
            pnl_bruto = sgn * ret[t] * 100
            rows.append({"sym": s, "t": t, "filled": bool(filled),
                         "pnl_bruto": float(pnl_bruto)})
    df = pd.DataFrame(rows)
    print(f"muestra: {len(df)} trades ({df['t'].nunique()} sábados de 2026, "
          f"{df['sym'].nunique()} símbolos)")
    fr_ = df["filled"].mean()
    print(f"\n1. TASA DE LLENADO de la limit en la 1ª hora: {fr_*100:.0f}%")
    f_ = df[df.filled]; nf = df[~df.filled]
    print(f"2. SELECCIÓN ADVERSA (PnL bruto medio):")
    print(f"   llenados   n {len(f_):3d}: {f_['pnl_bruto'].mean():+.3f}%")
    print(f"   no llenados n {len(nf):3d}: {nf['pnl_bruto'].mean():+.3f}%")
    # tácticas (por trade, costes por lado: entrada según táctica + salida taker)
    # taker puro: entrada taker+slip, salida taker+slip
    pnl_taker = df["pnl_bruto"] - COST_TAKER_RT
    # limit->market: si llena, entrada maker sin slip; si no, entra a la hora a
    # precio de mercado (aprox: mismo pnl bruto, coste taker) -- aproximación
    # conservadora: el precio de entrada tardía se ignora (sesgo pequeño, 1h de 24)
    cost_entry = np.where(df["filled"], MAKER, TAKER + SLIP)
    pnl_limit = df["pnl_bruto"] - cost_entry - (TAKER + SLIP)
    print(f"\n3. NETO por táctica (misma muestra):")
    print(f"   taker puro      : {pnl_taker.mean():+.3f}%/trade")
    print(f"   limit 1h->market: {pnl_limit.mean():+.3f}%/trade "
          f"(ahorro {pnl_limit.mean()-pnl_taker.mean():+.3f}%)")
    print("\nNOTA: aproximación con velas 5m (toque = llenado, sin cola de libro);")
    print("el ahorro real puede ser algo menor. La selección adversa del punto 2 es")
    print("la cifra clave: si los llenados rinden mucho peor, la limit no compensa.")


if __name__ == "__main__":
    main()
