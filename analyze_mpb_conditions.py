"""
ANÁLISIS (2026-07-23): ¿el micro_pullback falla UNIFORME o solo en ciertas
condiciones? Decisión detrás: las alertas F que manda el bot hoy son EL MISMO
detector sin auto-trade -> si falla en todo, las F están condenadas.

Lee los 389 trades cerrados (PC + GitHub) en SOLO-LECTURA y trocea el PnL YA
CALCULADO por el bot (no recalcula nada) por: hora local, régimen de BTC (día
alcista/bajista), día de semana y símbolo.

OJO (comparaciones limpias): con ~15 horas + 7 días + símbolos, ALGÚN corte saldrá
positivo por azar. Lo que importa NO es el mejor corte (mirage), sino si hay ALGUNA
condición donde gane de verdad. Spoiler del run: no la hay — pierde incluso en el
régimen favorable (BTC alcista) con IC95 excluyendo 0.
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
import sqlite3
import numpy as np
import pandas as pd
from data_fetcher import fetch_ohlcv
from config import TFZConfig, config_for_timeframe

BASE = os.path.dirname(os.path.abspath(__file__))


def _load(db, src):
    c = sqlite3.connect("file:" + db + "?mode=ro", uri=True)
    cur = c.execute("SELECT symbol,entry_ts,pnl_pct FROM paper_trades WHERE status='closed'")
    return [dict(zip([d[0] for d in cur.description], r), src=src) for r in cur]


def _report(df, col, label, minn=15):
    print(f"\n=== por {label} (grupos con n>={minn}) ===")
    out = []
    for k, sub in df.groupby(col):
        if len(sub) < minn:
            continue
        m = sub.pnl_pct.mean(); se = sub.pnl_pct.std(ddof=1) / np.sqrt(len(sub))
        out.append((k, len(sub), m, (sub.pnl_pct > 0).mean() * 100, m - 1.96 * se, m + 1.96 * se))
    for k, n, m, w, lo, hi in sorted(out, key=lambda x: x[2]):
        flag = " <-- IC95 excluye 0" if (lo > 0 or hi < 0) else ""
        print(f"  {str(k):>8}: n={n:3d} media {m:+.3f}% win {w:4.1f}% IC95[{lo:+.3f},{hi:+.3f}]{flag}")


def main():
    df = pd.DataFrame(_load(os.path.join(BASE, "tfz_data.db"), "PC") +
                      _load(os.path.join(BASE, "github_state/tfz_data.db"), "GH"))
    df["t"] = pd.to_datetime(df.entry_ts)
    df["hora_mad"] = (df.t.dt.hour + 2) % 24
    df["dow"] = df.t.dt.dayofweek
    btc = fetch_ohlcv("BTC/USDT:USDT", "1d", limit=60, config=config_for_timeframe(TFZConfig(), "1d"))
    reg = {pd.to_datetime(r.timestamp).date(): (r.close > r.open) for r in btc.itertuples()}
    df["btc_up"] = df.t.dt.date.map(reg)
    print(f"micro_pullback: {len(df)} trades cerrados | media {df.pnl_pct.mean():+.3f}% | "
          f"win {(df.pnl_pct > 0).mean() * 100:.1f}%")
    _report(df, "hora_mad", "HORA (Madrid)")
    _report(df, "btc_up", "REGIMEN BTC (True=dia alcista)")
    _report(df, "dow", "DIA SEMANA (0=lun)")


if __name__ == "__main__":
    main()
