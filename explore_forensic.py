"""FORENSE DE LOOK-AHEAD (tarea nº1 del auditor).

Pregunta: ¿el edge del backtest desaparece cuando las señales solo pueden usar
informacion disponible en su momento (como el bot en vivo)?

Diseño A/B con la MISMA tanda de datos (FREEZE_CACHE=1):
  MODO A "viejo" : ventana de 400 velas, se aceptan señales con trigger en CUALQUIER
                   punto de la ventana (los niveles/tendencia/validez usan velas
                   posteriores al trigger -> look-ahead). Es lo que hacia validate_oos.
  MODO B "vivo"  : misma ventana deslizante, pero SOLO se aceptan señales cuyo trigger
                   este en las ultimas `FRESH` velas de la ventana (= las señales solo
                   ven pasado, como el paper en vivo con fresh_lookback).

Para que el modo B muestree la historia con densidad, el paso de la ventana en B es
pequeño (STEP_B); en A se usa el paso original (STEP_A=50). Ambos modos deduplican por
(trigger_idx, direction) y simulan salidas con el MISMO run_backtest sobre el df completo.

Salida: por TF y modo -> n señales, win rate, expectancy neta, y por formacion.
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")
os.environ.setdefault("FREEZE_CACHE", "1")

import numpy as np
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached
from swings import detect_swings, compute_trend_strength
from levels import detect_horizontal_levels, detect_diagonal_levels
from consolidation import detect_consolidations
from sweep import detect_sweeps
from formations import detect_formations
from filters import check_chart_quality
from signals import generate_signals
from backtester import run_backtest

UNI = [s.strip() for s in open("_universe.txt").read().split(",") if s.strip()]
TFS = ["1h", "15m", "5m"]
WINDOW = 400
STEP_A = 50      # modo viejo (como validate_oos / main backtest)
STEP_B = 5       # modo vivo: paso fino para muestrear "finales de ventana" densamente
FRESH = 2        # como el paper (fresh_lookback=2): trigger en las ultimas 2 velas
CANDLES = 1500


def collect_signals(df, symbol, tf, tf_cfg, step, fresh_only):
    """Pipeline ventana a ventana. fresh_only: exigir trigger al final de la ventana."""
    out = []
    n = len(df)
    for w_start in range(0, n - WINDOW, step):
        window = df.iloc[w_start:w_start + WINDOW].reset_index(drop=True)
        swings = detect_swings(window, tf_cfg)
        if not check_chart_quality(window, swings, tf_cfg).passed:
            continue
        cp = float(window["close"].iloc[-1])
        cidx = len(window) - 1
        h = detect_horizontal_levels(swings, cp, tf_cfg, total_candles=len(window))
        d = detect_diagonal_levels(swings, cp, tf_cfg)
        consols = detect_consolidations(window, tf_cfg, [l.price for l in h])
        sweeps = detect_sweeps(window, h, tf_cfg)
        forms = detect_formations(h, d, consols, sweeps, cp, cidx, tf_cfg)
        trend = compute_trend_strength(window, tf, cidx, hours=tf_cfg.trend_lookback_hours)
        sigs = generate_signals(window, forms, symbol, tf, tf_cfg,
                                trend_strength=trend, is_bear_market=False)
        for s in sigs:
            if fresh_only and s.trigger_idx < cidx - FRESH:
                continue          # como el vivo: solo triggers recien confirmados
            s.trigger_idx += w_start
            out.append(s)
    # dedup como validate_oos
    seen, uniq = set(), []
    for s in out:
        k = (s.trigger_idx, s.direction)
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    return uniq


def summarize(tag, allres):
    """allres: lista de (pnl, formation)."""
    if not allres:
        print(f"  {tag}: 0 trades")
        return
    a = np.array([r[0] for r in allres])
    print(f"  {tag}: n={len(a):4d} | win {(a > 0.05).mean() * 100:5.1f}% | "
          f"exp {a.mean():+.3f}%/trade | suma {a.sum():+.1f}%")
    from collections import defaultdict
    g = defaultdict(list)
    for p, f in allres:
        g[f].append(p)
    for f, pp in sorted(g.items()):
        pa = np.array(pp)
        print(f"      {f:16s} n={len(pa):4d} win {(pa > 0.05).mean() * 100:5.1f}% "
              f"exp {pa.mean():+.3f}%")


print(f"FORENSE LOOK-AHEAD | universo={len(UNI)} monedas | ventana={WINDOW} | "
      f"A: paso {STEP_A} sin filtro | B: paso {STEP_B} trigger en ultimas {FRESH} velas\n")

for tf in TFS:
    print(f"===== TF {tf} =====")
    res_a, res_b = [], []
    used = 0
    for sym in UNI:
        tf_cfg = config_for_timeframe(TFZConfig(), tf)
        try:
            df = fetch_ohlcv_cached(sym, tf, limit=CANDLES, config=tf_cfg)
        except Exception:
            continue
        if len(df) < WINDOW + 100:
            continue
        used += 1
        for mode, step, fresh, bucket in (("A", STEP_A, False, res_a),
                                          ("B", STEP_B, True, res_b)):
            sigs = collect_signals(df, sym, tf, tf_cfg, step, fresh)
            if not sigs:
                continue
            results, _ = run_backtest(df, sigs, tf_cfg)
            smap = {s.id: s for s in sigs}
            for r in results:
                s = smap.get(r.signal_id)
                bucket.append((r.pnl_pct, s.formation_type if s else "?"))
    print(f"  monedas con datos: {used}")
    summarize("A viejo (con look-ahead)", res_a)
    summarize("B vivo  (solo pasado)   ", res_b)
    print()

print("FIN. Si B << A, el edge del backtest era look-ahead. Lo que quede en B es el edge real.")
