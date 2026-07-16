"""
Paper trading loop for the TFZ engine.

Runs the validated pipeline forward on live data without risking capital:
  1. update open paper trades against the latest candles (TP/SL/stale/breakeven)
  2. scan the watchlist for FRESH signals and open new paper trades
  3. report open positions and closed performance

Designed to be run periodically (cron or `/loop`):
    python -u main.py paper --once

Exit logic mirrors backtester._simulate_trade so paper results are consistent
with the historical validation.
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import List

from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached as fetch_ohlcv
from swings import detect_swings, compute_atr, compute_trend_strength
from levels import detect_horizontal_levels, detect_diagonal_levels
from consolidation import detect_consolidations
from sweep import detect_sweeps
from filters import check_chart_quality
from formations import detect_formations
from signals import generate_signals
from database import (
    get_connection, init_db, open_paper_trade, get_open_paper_trades,
    close_paper_trade, paper_stats, save_signal,
)
import ml_filter

# Default watchlist: the liquid majors + actives (subset of the backtest universe)
DEFAULT_WATCHLIST = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT",
]


_TF_MIN = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}


def _intrabar_first(symbol, candle_ts, tf, sl, tp, direction, cfg):
    """Resolucion INTRAVELA (arreglo A): cuando una sola vela contiene A LA VEZ el SL y
    el TP, no se sabe cual se toco primero. Antes se asumia SL (pesimista). Aqui miramos
    las velas de 1m DENTRO de esa vela para decidir el orden real. Devuelve 'sl', 'tp' o
    None (sin datos 1m -> el llamador mantiene el pesimismo como respaldo seguro)."""
    try:
        nmin = _TF_MIN.get(tf, 60)
        since = int(pd.to_datetime(candle_ts).timestamp() * 1000)
        end = since + nmin * 60 * 1000
        m1 = fetch_ohlcv(symbol, "1m", limit=nmin + 2, since=since,
                         config=config_for_timeframe(cfg, "1m"))
        if m1 is None or len(m1) == 0:
            return None
        h = m1["high"].values
        l = m1["low"].values
        for k in range(len(m1)):
            t = int(pd.to_datetime(m1["timestamp"].iloc[k]).timestamp() * 1000)
            if t < since or t >= end:
                continue
            if direction == "long":
                hit_sl, hit_tp = l[k] <= sl, h[k] >= tp
            else:
                hit_sl, hit_tp = h[k] >= sl, l[k] <= tp
            if hit_sl:        # SL primero (o ambos en la misma vela de 1m -> pesimista)
                return "sl"
            if hit_tp:
                return "tp"
        return None
    except Exception:
        return None


def _check_exit(trade: dict, df, cfg: TFZConfig):
    """Return (exit_price, exit_reason, exit_ts, pnl_pct) if the trade resolved
    in the candles after entry, else None (still open)."""
    ts = df["timestamp"].astype(str).values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    atr = compute_atr(df, cfg.atr_period)

    # Locate the entry candle by timestamp
    entry_ts = str(trade["entry_ts"])
    entry_idx = None
    for i in range(len(ts)):
        if ts[i] >= entry_ts:
            entry_idx = i
            break
    if entry_idx is None:
        return None

    direction = trade["direction"]
    entry = trade["entry_price"]
    current_sl = trade["stop_loss"]
    tp = trade["take_profit"]
    consol_h = trade["consol_high"]
    consol_l = trade["consol_low"]

    moved_be = False
    max_runup = 0.0
    max_dd = 0.0

    for i in range(entry_idx + 1, len(df)):
        if direction == "long":
            runup = (highs[i] - entry) / entry * 100
            dd = (entry - lows[i]) / entry * 100
        else:
            runup = (entry - lows[i]) / entry * 100
            dd = (highs[i] - entry) / entry * 100
        max_runup = max(max_runup, runup)
        max_dd = max(max_dd, dd)

        # SL / TP — detectar si la vela toca cada nivel
        if direction == "long":
            hit_sl, hit_tp = lows[i] <= current_sl, highs[i] >= tp
        else:
            hit_sl, hit_tp = highs[i] >= current_sl, lows[i] <= tp

        # Vela AMBIGUA (toca ambos): mirar 1m para saber cual fue primero (arreglo A).
        if hit_sl and hit_tp:
            first = _intrabar_first(trade["symbol"], ts[i], trade["timeframe"],
                                    current_sl, tp, direction, cfg)
            if first == "tp":
                hit_sl = False          # el 1m confirma que el TP llego antes
            else:
                hit_tp = False          # 'sl' o sin datos -> pesimista (respaldo seguro)

        if hit_sl:
            pnl = ((current_sl - entry) if direction == "long" else (entry - current_sl)) / entry * 100
            reason = "breakeven" if moved_be and abs(pnl) < 0.05 else "sl_hit"
            return current_sl, reason, ts[i], round(pnl, 4)
        if hit_tp:
            pnl = ((tp - entry) if direction == "long" else (entry - tp)) / entry * 100
            return tp, "tp_hit", ts[i], round(pnl, 4)

        # Move to breakeven on a confirmed retest (spec §10.3)
        if not moved_be and consol_h is not None and consol_l is not None:
            curr_atr = atr[i] if i < len(atr) and not np.isnan(atr[i]) else 0
            if direction == "long":
                if lows[i] <= consol_h + curr_atr * cfg.retest_atr_mult and closes[i] > consol_h and max_runup > 0.3:
                    current_sl = entry
                    moved_be = True
            else:
                if highs[i] >= consol_l - curr_atr * cfg.retest_atr_mult and closes[i] < consol_l and max_runup > 0.3:
                    current_sl = entry
                    moved_be = True

        # Stale exit (spec §12.2)
        candles_in = i - entry_idx
        if candles_in >= cfg.stale_candles and (runup - max_dd) < 1.0:
            px = closes[i]
            pnl = (px - entry) / entry * 100 if direction == "long" else (entry - px) / entry * 100
            return px, "stale", ts[i], round(pnl, 4)

    return None  # unresolved -> still open


def _alert_context(df) -> str:
    """Contexto objetivo para la alerta del modo asistente (patron de CryptoSignal,
    github.com/CryptoSignal/Crypto-Signal: la alerta lleva varios indicadores y decide
    el humano). SOLO velas CERRADAS (la ultima del df puede estar en formacion).
    Es informativo: NO filtra ni altera ninguna señal ni el paper congelado."""
    try:
        d = df.iloc[:-1]
        closes = d["close"].values.astype(float)
        if len(closes) < 30:
            return ""
        # RSI-14 Wilder (misma formula que explore_meanrev.rsi)
        delta = np.diff(closes, prepend=closes[0])
        gain = np.where(delta > 0, delta, 0.0)
        loss = np.where(delta < 0, -delta, 0.0)
        ag = pd.Series(gain).ewm(alpha=1 / 14, adjust=False).mean().values
        al = pd.Series(loss).ewm(alpha=1 / 14, adjust=False).mean().values
        rs = np.divide(ag, al, out=np.zeros_like(ag), where=al != 0)
        rsi = (100 - 100 / (1 + rs))[-1]
        # RVOL: volumen de la ultima vela cerrada vs media de las 20 anteriores
        vols = d["volume"].values.astype(float)
        vol_ma = vols[-21:-1].mean()
        rvol = vols[-1] / vol_ma if vol_ma > 0 else 0.0
        parts = [f"RSI14 {rsi:.0f}", f"RVOL {rvol:.1f}x"]
        # Lado de la EMA200 (tendencia de fondo), solo si hay historia suficiente
        if len(closes) >= 200:
            ema200 = pd.Series(closes).ewm(span=200, adjust=False).mean().values[-1]
            dist = (closes[-1] - ema200) / ema200 * 100
            side = "sobre" if dist >= 0 else "bajo"
            parts.append(f"{side} EMA200 ({dist:+.1f}%)")
        return " | ".join(parts)
    except Exception:
        return ""


def _alert_once(conn, sig, entry_ts, df=None) -> bool:
    """MODO ASISTENTE: envia la alerta de un setup UNA sola vez (dedup por
    simbolo+TF+vela+direccion+formacion, igual que el dedup de trades). Devuelve True
    si se envio (primera vez), False si ya se habia alertado."""
    conn.execute("CREATE TABLE IF NOT EXISTS sent_alerts ("
                 "key TEXT PRIMARY KEY, sent_at TEXT)")
    key = f"{sig.symbol}|{sig.timeframe}|{entry_ts}|{sig.direction}|{sig.formation_type}"
    cur = conn.execute("INSERT OR IGNORE INTO sent_alerts VALUES (?, datetime('now'))", (key,))
    conn.commit()
    if cur.rowcount == 0:
        return False
    try:
        from notify import alert_entry
        ctx = _alert_context(df) if df is not None else ""
        alert_entry(sig, None, context=ctx or None)
    except Exception:
        pass
    return True


def update_open_trades(conn, cfg: TFZConfig, verbose=True) -> int:
    """Re-evaluate every open paper trade against fresh candles. Returns #closed."""
    closed = 0
    for trade in get_open_paper_trades(conn):
        tf_cfg = config_for_timeframe(cfg, trade["timeframe"])
        try:
            # limit 1000 (not 300): _check_exit locates the entry candle by timestamp;
            # if the entry scrolled out of the window (PC off long) the trade would be
            # orphaned (never closes). 1000 velas = ~3.5d en 5m, ~10d en 15m.
            df = fetch_ohlcv(trade["symbol"], trade["timeframe"], limit=1000, config=tf_cfg)
        except Exception as e:
            if verbose:
                print(f"  [update] {trade['symbol']} {trade['timeframe']}: fetch error {e}")
            continue
        res = _check_exit(trade, df, tf_cfg)
        if res:
            exit_price, reason, exit_ts, pnl = res
            # Apply the SAME costs as backtester.run_backtest so the paper PnL is NET
            # (commission+slippage ida y vuelta + funding de perp) y comparable con el
            # edge validado. Sin esto el PnL del paper era BRUTO (~0.2%/trade optimista).
            cost = (tf_cfg.commission_pct + tf_cfg.slippage_pct) * 2
            if tf_cfg.funding_pct_per_8h > 0:
                try:
                    hours = max(0.0, (pd.to_datetime(exit_ts) - pd.to_datetime(trade["entry_ts"])).total_seconds() / 3600.0)
                    cost += tf_cfg.funding_pct_per_8h * (hours / 8.0)
                except Exception:
                    pass
            pnl = round(pnl - cost, 4)
            close_paper_trade(conn, trade["id"], exit_price, reason, exit_ts, pnl)
            closed += 1
            # Autopsia post-trade: factores deterministas (contra-tendencia, BTC,
            # runup en R, velas...) guardados en trade_review. Fail-silent.
            try:
                from trade_review import review_trade
                closed_trade = dict(trade)
                closed_trade.update(status="closed", exit_price=exit_price,
                                    exit_reason=reason, exit_ts=str(exit_ts), pnl_pct=pnl)
                review_trade(conn, closed_trade, cfg)
            except Exception as e:
                if verbose:
                    print(f"  [review] {trade['symbol']}: {e}")
            # SIN aviso a Telegram al cerrar: los trades del paper son la MEDICION
            # silenciosa; el movil solo recibe alertas de setups del asistente.
            if verbose:
                print(f"  [closed] {trade['symbol']:10s} {trade['timeframe']:>3s} "
                      f"{trade['direction']:5s} {trade['formation_type']:16s} "
                      f"{reason:10s} pnl {pnl:+.2f}%")
    return closed


def btc_recent_move(cfg, hours=3):
    """BTC % move over the last `hours` (1h candles), for the BTC-correlation gate.
    Fail-open: returns 0.0 (no block) if BTC data is unavailable."""
    try:
        tf_cfg = config_for_timeframe(cfg, "1h")
        df = fetch_ohlcv("BTC/USDT:USDT", "1h", limit=50, config=tf_cfg)
        if len(df) > hours:
            return float((df["close"].iloc[-1] / df["close"].iloc[-1 - hours] - 1) * 100)
    except Exception:
        pass
    return 0.0


def fresh_accepted_signals(symbol, tf, cfg: TFZConfig, fresh_lookback=2,
                           ml_cutoff=0.55, use_ml=True, candles=600, verbose=True,
                           filter_mode="ml", min_score=60.0, min_rr=8.0, btc_3h=None):
    """Run the full pipeline for one symbol/timeframe and return the freshly
    triggered, accepted signals. Shared by paper trading and execution so
    both act on exactly the same logic. Returns list of (signal, trend, prob, df).

    filter_mode:
      "ml"     -> accept unless ML win-probability < ml_cutoff (classic gate).
      "profit" -> profit-aligned gate: accept iff total_score >= min_score AND
                  rr_ratio >= min_rr. Designed for the asymmetric edge where the
                  win-rate ML filter wrongly discards high-RR winners. The ML
                  probability is still computed/recorded for analysis.
    """
    tf_cfg = config_for_timeframe(cfg, tf)
    try:
        df = fetch_ohlcv(symbol, tf, limit=candles, config=tf_cfg)
    except Exception as e:
        if verbose:
            print(f"  [scan] {symbol} {tf}: fetch error {e}")
        return []
    if len(df) < 200:
        return []
    # GUARD DE DATOS FRESCOS: si la última vela es vieja (feed/caché caducado), NO operar
    # esta moneda este ciclo. Evita abrir trades con precios de hace horas (visto: DOT/JUP
    # con velas de 6h -> entrada y salida basura sobre datos muertos).
    max_age_min = {"1m": 5, "5m": 20, "15m": 60, "1h": 180}.get(tf, 30)
    now_utc = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))
    age_min = (now_utc - pd.to_datetime(df["timestamp"].iloc[-1])).total_seconds() / 60.0
    if age_min > max_age_min:
        if verbose:
            print(f"  [stale-data] {symbol:10s} {tf:>3s} ultima vela hace {age_min:.0f} min "
                  f"(max {max_age_min}) -> datos viejos, no opero")
        return []

    swings = detect_swings(df, tf_cfg)
    if not check_chart_quality(df, swings, tf_cfg).passed:
        return []

    current_price = float(df["close"].iloc[-1])
    current_idx = len(df) - 1
    h_levels = detect_horizontal_levels(swings, current_price, tf_cfg, total_candles=len(df))
    d_levels = detect_diagonal_levels(swings, current_price, tf_cfg)
    level_prices = [l.price for l in h_levels]
    consolidations = detect_consolidations(df, tf_cfg, level_prices)
    sweeps_list = detect_sweeps(df, h_levels, tf_cfg)
    formations = detect_formations(h_levels, d_levels, consolidations,
                                   sweeps_list, current_price, current_idx, tf_cfg)
    trend = compute_trend_strength(df, tf, current_idx)
    signals = generate_signals(df, formations, symbol, tf, tf_cfg,
                               trend_strength=trend, is_bear_market=False)

    accepted = []
    for sig in signals:
        if sig.trigger_idx < current_idx - fresh_lookback:
            # Not fresh enough to enter realistically. If it WOULD have passed the
            # filter, log it -> reveals valid setups missed due to freshness /
            # watchlist timing (the bot only watches coins after they've moved >=10%,
            # so good setups that formed during the move are often already stale).
            if verbose:
                would_pass = ((sig.total_score >= min_score and sig.rr_ratio >= min_rr)
                              if filter_mode == "profit" else True)
                if would_pass:
                    ago = current_idx - sig.trigger_idx
                    print(f"  [stale-skip] {symbol:10s} {tf:>3s} {sig.direction:5s} "
                          f"{sig.formation_type:16s} score {sig.total_score:.0f} "
                          f"rr {sig.rr_ratio:.1f} (valida, trigger hace {ago} velas, no fresca)")
            continue  # not a fresh trigger
        # FIDELIDAD DE ENTRADA: el trade se abre AHORA, al precio ACTUAL, no al cierre
        # de la vela trigger (que puede ser de varias velas atrás -> con ciclo de 5 min
        # y señales de 1m, el precio ya se movió). Reanclamos el entry al precio actual
        # y recomputamos RR/riesgo con el MISMO SL/TP estructural. Si el movimiento ya
        # pasó (precio fuera de [SL,TP] o RR caído por debajo del filtro), se descarta.
        sl, tp = sig.stop_loss, sig.take_profit
        if sig.direction == "long":
            valid_side = sl < current_price < tp
            risk_now = (current_price - sl) / current_price * 100 if current_price > 0 else 999
        else:
            valid_side = tp < current_price < sl
            risk_now = (sl - current_price) / current_price * 100 if current_price > 0 else 999
        denom = abs(current_price - sl)
        rr_now = abs(tp - current_price) / denom if denom > 1e-12 else 0
        if (not valid_side) or risk_now <= 0 or risk_now > cfg.max_risk_pct:
            if verbose:
                print(f"  [moved-skip] {symbol:10s} {tf:>3s} {sig.direction:5s} "
                      f"{sig.formation_type:16s} (precio ya en {current_price:.4g}, "
                      f"entry {sig.entry_price:.4g} caduco)")
            continue
        sig.entry_price = current_price       # precio real de apertura
        sig.risk_pct = round(risk_now, 4)
        sig.rr_ratio = round(rr_now, 2)        # el filtro 60/6 de abajo usa este RR ya reanclado
        # BTC-correlation gate: don't open a trade that fights a STRONG BTC move
        # (long while BTC dumps / short while BTC pumps). Validated: those have
        # ~0-20% win. Fail-open if btc_3h is None (filter off).
        if btc_3h is not None and abs(btc_3h) >= cfg.btc_block_pct:
            counter_btc = ((sig.direction == "long" and btc_3h < 0)
                           or (sig.direction == "short" and btc_3h > 0))
            if counter_btc:
                if verbose:
                    print(f"  [btc-skip] {symbol:10s} {tf:>3s} {sig.direction:5s} "
                          f"{sig.formation_type:16s} (BTC {btc_3h:+.1f}% en 3h, en contra)")
                continue
        prob = ml_filter.predict_win_prob(sig, trend) if use_ml else None
        if filter_mode == "profit":
            # F3 es la formacion mas floja: pedirle MAS score (validado: F3>=80 da +1.30%/
            # OOS +1.23% vs +0.85% a >=60, y sube el conjunto +2.31->+2.45%). Las demas en min_score.
            eff_min = max(min_score, cfg.f3_min_score) if sig.formation_type == "F3" else min_score
            passed = (sig.total_score >= eff_min and sig.rr_ratio >= min_rr)
        else:
            passed = not (prob is not None and prob < ml_cutoff)
        # Record every evaluated setup (live path only, i.e. when ML prob exists)
        if use_ml:
            try:
                from recorder import record_eval
                record_eval(sig, prob, passed, df["timestamp"].iloc[sig.trigger_idx])
            except Exception:
                pass
        if not passed:
            if verbose:
                if filter_mode == "profit":
                    print(f"  [skip] {symbol:10s} {tf:>3s} {sig.direction:5s} "
                          f"{sig.formation_type:16s} score {sig.total_score:.0f} "
                          f"rr {sig.rr_ratio:.1f} (need score>={min_score:.0f} & rr>={min_rr:.0f})")
                else:
                    pstr = f"{prob:.2f}" if prob is not None else "n/a"
                    print(f"  [ml-skip] {symbol:10s} {tf:>3s} {sig.direction:5s} "
                          f"{sig.formation_type:16s} score {sig.total_score:.0f} "
                          f"win_prob {pstr} < {ml_cutoff:.2f}")
            continue
        accepted.append((sig, trend, prob, df))
    return accepted


def collect_setups(symbols, timeframes, cfg: TFZConfig, fresh_lookback=20,
                   ml_cutoff=0.55, verbose=False):
    """Read-only: return current/recent setups across the watchlist with full
    entry details + ML win probability + how each has played out so far
    (TP/SL/open), for manual review. Does NOT trade."""
    from backtester import _simulate_trade
    rows = []
    for symbol in symbols:
        for tf in timeframes:
            tf_cfg = config_for_timeframe(cfg, tf)
            for sig, trend, _p, df in fresh_accepted_signals(
                    symbol, tf, cfg, fresh_lookback, use_ml=False, verbose=verbose):
                prob = ml_filter.predict_win_prob(sig, trend)
                candles_ago = (len(df) - 1) - sig.trigger_idx
                # Auto-check the outcome on the candles since it triggered
                res = _simulate_trade(df, sig, tf_cfg)
                if res is None:
                    outcome, out_pnl = "abierto", None
                else:
                    outcome = {"tp_hit": "TP", "sl_hit": "SL", "breakeven": "BE",
                               "stale": "stale", "timeout": "abierto"}.get(res.exit_reason, res.exit_reason)
                    out_pnl = res.pnl_pct
                ts_utc = df["timestamp"].iloc[sig.trigger_idx]
                # Data is UTC; show Spain time (CEST = UTC+2 in summer)
                ts_local = (ts_utc + pd.Timedelta(hours=2)).strftime("%H:%M")
                rows.append({
                    "symbol": symbol, "tf": tf, "direction": sig.direction,
                    "formation": sig.formation_type, "entry": sig.entry_price,
                    "sl": sig.stop_loss, "tp": sig.take_profit, "rr": sig.rr_ratio,
                    "score": sig.total_score, "win_prob": prob,
                    "candles_ago": candles_ago, "trend": round(trend, 2),
                    "time_es": ts_local, "outcome": outcome, "out_pnl": out_pnl,
                })
    rows.sort(key=lambda r: (r["win_prob"] if r["win_prob"] is not None else -1), reverse=True)
    return rows


def scan_new_signals(conn, symbols, timeframes, cfg: TFZConfig,
                     fresh_lookback=2, candles=600, ml_cutoff=0.55,
                     use_ml=True, verbose=True,
                     filter_mode="ml", min_score=60.0, min_rr=8.0, btc_3h=None) -> int:
    """Scan the watchlist for fresh signals and open paper trades. Returns #opened."""
    opened = 0
    _open = get_open_paper_trades(conn)
    open_keys = {(t["symbol"], t["timeframe"], t["direction"]) for t in _open}
    # Guard 1-posicion-por-moneda: no doblar exposicion al mismo activo (cualquier
    # TF/direccion). Si la moneda ya tiene un trade abierto, se salta ([dup-skip]).
    open_symbols = {t["symbol"] for t in _open}
    # Cap de correlación: nº de abiertas por dirección (limita el cluster correlado).
    dir_count = {"long": 0, "short": 0}
    for t in _open:
        dir_count[t["direction"]] = dir_count.get(t["direction"], 0) + 1
    # Cooldown anti-re-entrada: ultimo SL/breakeven por (symbol, direction) en 24h.
    # exit_ts es UTC, igual que la marca de tiempo de las velas -> comparables.
    recent_stops = {}
    if cfg.reentry_cooldown_min > 0:
        cur = conn.execute(
            "SELECT symbol, direction, MAX(exit_ts) FROM paper_trades "
            "WHERE status='closed' AND exit_reason IN ('sl_hit','breakeven') "
            "AND exit_ts >= datetime('now','-1 day') GROUP BY symbol, direction")
        recent_stops = {(s, d): x for s, d, x in cur.fetchall() if x}

    for symbol in symbols:
        if symbol in open_symbols:
            if verbose:
                print(f"  [dup-skip] {symbol:10s} ya tiene posicion abierta (1 por moneda)")
            continue
        for tf in timeframes:
            if symbol in open_symbols:  # abierta en este mismo ciclo por otro TF
                break
            for sig, trend, prob, df in fresh_accepted_signals(
                    symbol, tf, cfg, fresh_lookback, ml_cutoff, use_ml, candles, verbose,
                    filter_mode=filter_mode, min_score=min_score, min_rr=min_rr, btc_3h=btc_3h):
                key = (symbol, tf, sig.direction)
                if key in open_keys:
                    continue
                # Cap de correlación: máx N abiertas por dirección (0 = sin límite)
                if cfg.max_open_per_dir and dir_count.get(sig.direction, 0) >= cfg.max_open_per_dir:
                    if verbose:
                        print(f"  [corr-skip] {symbol:10s} {tf:>3s} {sig.direction:5s} "
                              f"(ya hay {dir_count[sig.direction]} {sig.direction} abiertos, "
                              f"max {cfg.max_open_per_dir})")
                    continue
                # Cooldown anti-re-entrada: si esta moneda+direccion tuvo un SL hace
                # menos de reentry_cooldown_min, no reabrir (evita el chop repetido)
                last_stop = recent_stops.get((symbol, sig.direction))
                if last_stop:
                    cur_t = str(df["timestamp"].iloc[-1])  # UTC, como exit_ts
                    gap = (pd.to_datetime(cur_t) - pd.to_datetime(last_stop)).total_seconds() / 60.0
                    if 0 <= gap < cfg.reentry_cooldown_min:
                        if verbose:
                            print(f"  [cooldown-skip] {symbol:10s} {tf:>3s} {sig.direction:5s} "
                                  f"(SL hace {gap:.0f} min, cooldown {cfg.reentry_cooldown_min:.0f})")
                        continue
                # entry_ts = vela de APERTURA (la actual), no la del trigger. El precio
                # ya se reancla al precio actual (fix de fidelidad), así que la marca de
                # tiempo debe casar: _check_exit escanea salidas SOLO desde que el trade
                # existe. Anclar al trigger (anterior) provocaba cierres falsos en velas
                # previas a la apertura -> exit_ts imposible + bucle de re-entradas.
                entry_ts = df["timestamp"].iloc[-1]
                # MODO ASISTENTE (auditoria 2026-07-03): las formaciones F1-F4 NO operan
                # (el forense demostro que su edge de backtest era look-ahead). Solo se
                # ALERTA por Telegram y decide el humano. El paper sigue con micro_pullback.
                if not getattr(cfg, "trade_formations", True):
                    if _alert_once(conn, sig, entry_ts, df) and verbose:
                        print(f"  [alerta] {symbol:10s} {tf:>3s} {sig.direction:5s} "
                              f"{sig.formation_type:16s} score {sig.total_score:.0f} "
                              f"rr {sig.rr_ratio:.1f} (asistente, no opera)")
                    continue
                save_signal(conn, sig)
                if not open_paper_trade(conn, sig, entry_ts):
                    continue                            # ANTI-DUPLICADOS: señal ya operada
                open_keys.add(key)
                open_symbols.add(symbol)
                dir_count[sig.direction] = dir_count.get(sig.direction, 0) + 1
                opened += 1
                # Telegram alert for the fresh entry (fail-silent if not configured)
                try:
                    from notify import alert_entry
                    alert_entry(sig, prob)
                except Exception:
                    pass
                if verbose:
                    pstr = f"win_prob {prob:.2f}" if prob is not None else "ml off"
                    print(f"  [opened] {symbol:10s} {tf:>3s} {sig.direction:5s} "
                          f"{sig.formation_type:16s} entry {sig.entry_price:.4g} "
                          f"SL {sig.stop_loss:.4g} TP {sig.take_profit:.4g} "
                          f"score {sig.total_score:.0f} {pstr}")
                break  # 1 por moneda: ya abrimos una, no abrir mas en este TF
    return opened


def open_position_state(trade, cfg: TFZConfig = None) -> dict:
    """PnL no realizado y distancias a SL/TP de una posicion abierta, calculados
    SEGUN SU DIRECCION (long/short). UNICA fuente para reportar estado de abiertas:
    evita recalcular la formula a mano (causa del error FIL-short reportado como long).
    """
    cfg = cfg or TFZConfig()
    tf_cfg = config_for_timeframe(cfg, trade["timeframe"])
    px = float(fetch_ohlcv(trade["symbol"], trade["timeframe"], limit=3, config=tf_cfg)["close"].iloc[-1])
    e, sl, tp = trade["entry_price"], trade["stop_loss"], trade["take_profit"]
    if trade["direction"] == "long":
        pnl = (px - e) / e * 100
        dist_sl = (px - sl) / px * 100   # margen hasta el SL (positivo = aun no tocado)
        dist_tp = (tp - px) / px * 100
    else:  # short
        pnl = (e - px) / e * 100
        dist_sl = (sl - px) / px * 100
        dist_tp = (px - tp) / px * 100
    return {"price": px, "pnl": round(pnl, 3),
            "dist_sl": round(dist_sl, 3), "dist_tp": round(dist_tp, 3)}


def print_status(conn):
    st = paper_stats(conn)
    print(f"\n{'='*64}")
    print(f"  PAPER TRADING STATUS")
    print(f"{'='*64}")
    print(f"  Open positions:  {st['open']}")
    print(f"  Closed trades:   {st['closed']}")
    if st["closed"]:
        print(f"  Win rate:        {st['win_rate']:.1f}% ({st['wins']}W / {st['losses']}L)")
        print(f"  Total PnL:       {st['total_pnl']:+.2f}%")
        print(f"  Expectancy:      {st['expectancy']:+.3f}% / trade")
        print(f"  Best / worst:    {st['best']:+.2f}% / {st['worst']:+.2f}%")

    open_trades = get_open_paper_trades(conn)
    if open_trades:
        print(f"\n  Open positions ({len(open_trades)}):")
        tot = 0.0
        for t in open_trades:
            try:
                s = open_position_state(t)
                tot += s["pnl"]
                print(f"    {t['symbol']:14s} {t['timeframe']:>3s} {t['direction']:5s} "
                      f"{t['formation_type']:16s} | entry {t['entry_price']:.5g} ahora {s['price']:.5g} "
                      f"| PnL {s['pnl']:+.2f}% | al TP {s['dist_tp']:+.1f}% / al SL {s['dist_sl']:+.1f}%")
            except Exception as e:
                print(f"    {t['symbol']:14s} {t['direction']:5s} estado n/d ({e})")
        print(f"  PnL no realizado total: {tot:+.2f}%")
    print(f"{'='*64}\n")


# Veteranas validadas (OOS +600%), vigiladas SIEMPRE -> sin "lateness": el bot
# está mirándolas antes de que se muevan, así que caza sus setups FRESCOS.
# Se SUMAN a los movers del scanner (el scanner NO se toca).
PERSISTENT_WATCHLIST = [
    # 14 originales
    "DOT/USDT:USDT", "APT/USDT:USDT", "ADA/USDT:USDT", "AAVE/USDT:USDT",
    "DOGE/USDT:USDT", "ARB/USDT:USDT", "NEAR/USDT:USDT", "OP/USDT:USDT",
    "FIL/USDT:USDT", "UNI/USDT:USDT", "ATOM/USDT:USDT", "AVAX/USDT:USDT",
    "INJ/USDT:USDT", "SOL/USDT:USDT",
    # +16 (todas del universo ya validado OOS) para más frecuencia de setups
    "LINK/USDT:USDT", "SUI/USDT:USDT", "SEI/USDT:USDT", "TIA/USDT:USDT",
    "ENA/USDT:USDT", "ONDO/USDT:USDT", "PENDLE/USDT:USDT", "FET/USDT:USDT",
    "RENDER/USDT:USDT", "JUP/USDT:USDT", "WIF/USDT:USDT", "LDO/USDT:USDT",
    "CRV/USDT:USDT", "GALA/USDT:USDT", "XLM/USDT:USDT", "ALGO/USDT:USDT",
]


# Excluidas del universo liquido dinamico:
#  - Metales tokenizados (XAU/XAG/XAUT/PAXG/XPT): no son cripto, la metodologia
#    de barridos de liquidez no aplica.
#  - BTC/ETH: drivers del mercado y se usan como gate de correlacion; operar el
#    propio benchmark contra el que filtramos es contradictorio.
WATCHLIST_EXCLUDE = {"XAU", "XAG", "XAUT", "PAXG", "XPT", "BTC", "ETH"}
LIQUID_MIN_VOL = 85e6   # umbral de volumen 24h (USDT) en BINANCE (referencia mas fiable)

_liq_cache = {"ts": 0.0, "list": None}   # cache 20 min para no re-escanear cada ciclo


def liquid_watchlist(min_vol=LIQUID_MIN_VOL, exclude=WATCHLIST_EXCLUDE, verbose=True):
    """Escanea los perps USDT de BINANCE (el volumen mas fiable, igual que el scanner)
    y devuelve los liquidos (>=min_vol de volumen 24h), excluyendo metales tokenizados
    y BTC/ETH, en formato BASE/USDT:USDT. Sustituye a la lista fija: si una moneda baja
    del umbral sale sola y entra otra. El bot trae las velas de Bybit; las que no esten
    en Bybit fallan el fetch y se saltan solas (no operamos aun, no filtramos por Bybit).
    Fail-safe: si el escaneo falla, usa PERSISTENT_WATCHLIST. Cacheado 20 min."""
    import time
    if _liq_cache["list"] is not None and (time.time() - _liq_cache["ts"]) < 1200:
        return _liq_cache["list"]
    try:
        import ccxt
        ex = ccxt.binance({"options": {"defaultType": "future"}})
        if os.environ.get("INSECURE_SSL") == "1":
            ex.verify = False
        ex.load_markets()
        perps = [s for s, m in ex.markets.items()
                 if m.get("swap") and m.get("linear")
                 and m.get("quote") == "USDT" and m.get("active")]
        tk = ex.fetch_tickers(perps)
        liq = [(s.split("/")[0], t.get("quoteVolume") or 0) for s, t in tk.items()
               if (t.get("quoteVolume") or 0) >= min_vol
               and s.split("/")[0] not in exclude]
        liq.sort(key=lambda r: -r[1])
        out = [f"{b}/USDT:USDT" for b, _ in liq]
        if not out:
            raise RuntimeError("0 monedas liquidas (escaneo vacio)")
        _liq_cache.update(ts=time.time(), list=out)
        return out
    except Exception as e:
        if verbose:
            print(f"  liquid_watchlist fallo ({e}); uso lista estatica de respaldo")
        return list(PERSISTENT_WATCHLIST)


def resolve_watchlist(symbols=None, source="scanner", verbose=True):
    """Decide which symbols to scan. The external scanner owns mover selection
    (untouched); we just consume its picks AND add a DYNAMIC set of liquid perps
    (>=50M vol 24h, Bybit) that we watch continuously. La lista liquida se
    re-evalua cada ciclo: cualquier moneda que pierde liquidez es sustituida."""
    if symbols:
        return symbols
    if source == "scanner":
        movers = []
        try:
            from scanner_bridge import get_perp_watchlist
            movers = get_perp_watchlist() or []
        except Exception as e:
            if verbose:
                print(f"  Scanner unavailable ({e})")
        veteranas = liquid_watchlist(verbose=verbose)
        # scanner movers + liquidas dinamicas (dedup, orden estable)
        combined = list(dict.fromkeys(movers + veteranas))
        if verbose:
            print(f"  Watchlist: {len(movers)} movers (scanner) + "
                  f"{len(veteranas)} liquidas (>=85M Binance) = {len(combined)}")
        return combined
    return DEFAULT_WATCHLIST


def _scan_setup(conn, symbols, cfg: TFZConfig, detect_fn, tfs, direction,
                name, candles=600, fresh_lookback=2, verbose=True):
    """Scan genérico para setups APARTE (fade-short, micro-pullback). NO pasan el filtro
    score/rr (RR propio) ni dependen del gate de momentum; solo guards basicos:
    1-por-moneda, cap de correlacion, cooldown, y datos frescos. Devuelve nº abiertas."""
    opened = 0
    _open = get_open_paper_trades(conn)
    open_symbols = {t["symbol"] for t in _open}
    dir_count = {"long": 0, "short": 0}
    for t in _open:
        dir_count[t["direction"]] = dir_count.get(t["direction"], 0) + 1
    recent_stops = {}
    if cfg.reentry_cooldown_min > 0:
        cur = conn.execute("SELECT symbol, direction, MAX(exit_ts) FROM paper_trades "
                           "WHERE status='closed' AND exit_reason IN ('sl_hit','breakeven') "
                           "AND exit_ts >= datetime('now','-1 day') GROUP BY symbol, direction")
        recent_stops = {(s, d): x for s, d, x in cur.fetchall() if x}
    now_utc = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))
    max_age = {"5m": 20, "15m": 60, "1h": 180}

    for symbol in symbols:
        if symbol in open_symbols:
            continue
        for tf in tfs:
            if symbol in open_symbols:
                break
            tf_cfg = config_for_timeframe(cfg, tf)
            try:
                df = fetch_ohlcv(symbol, tf, limit=candles, config=tf_cfg)
            except Exception:
                continue
            if len(df) < 100:
                continue
            age = (now_utc - pd.to_datetime(df["timestamp"].iloc[-1])).total_seconds() / 60.0
            if age > max_age.get(tf, 60):
                continue  # datos viejos
            cur_idx = len(df) - 1
            current_price = float(df["close"].iloc[-1])
            sigs = [s for s in detect_fn(df, symbol, tf, cfg)
                    if s.trigger_idx >= cur_idx - fresh_lookback]
            for sig in sigs:
                if cfg.max_open_per_dir and dir_count.get(direction, 0) >= cfg.max_open_per_dir:
                    break
                last_stop = recent_stops.get((symbol, direction))
                if last_stop:
                    gap = (pd.to_datetime(str(df["timestamp"].iloc[-1]))
                           - pd.to_datetime(last_stop)).total_seconds() / 60.0
                    if 0 <= gap < cfg.reentry_cooldown_min:
                        continue
                # FIDELIDAD (igual que el path principal): abrir AHORA al precio ACTUAL,
                # no a la vela del trigger (que puede ser de varias velas atras). Si el
                # movimiento YA paso (precio fuera de [SL,TP]) se descarta -> esto evita
                # "revivir" una señal vieja y los TP/SL instantaneos que inflaban el conteo
                # (caso TAC: el precio ya estaba por encima del TP -> moved-skip).
                sl, tp = sig.stop_loss, sig.take_profit
                if direction == "long":
                    valid_side = sl < current_price < tp
                    risk_now = (current_price - sl) / current_price * 100 if current_price > 0 else 999
                else:
                    valid_side = tp < current_price < sl
                    risk_now = (sl - current_price) / current_price * 100 if current_price > 0 else 999
                if (not valid_side) or risk_now <= 0:
                    if verbose:
                        print(f"  [moved-skip] {symbol:10s} {tf:>3s} {direction:5s} {name} "
                              f"(precio ya en {current_price:.4g}, entry {sig.entry_price:.4g} caduco)")
                    continue
                denom = abs(current_price - sl)
                sig.entry_price = current_price        # precio real de apertura
                sig.risk_pct = round(risk_now, 4)
                sig.rr_ratio = round(abs(tp - current_price) / denom, 2) if denom > 1e-12 else 0
                entry_ts = df["timestamp"].iloc[-1]    # vela ACTUAL, no la del trigger
                save_signal(conn, sig)
                if not open_paper_trade(conn, sig, entry_ts):
                    continue                            # ANTI-DUPLICADOS: señal ya operada
                open_symbols.add(symbol)
                dir_count[direction] = dir_count.get(direction, 0) + 1
                opened += 1
                # SIN aviso a Telegram: esto es la MEDICION silenciosa (paper), no el
                # asistente. Solo _alert_once (setups F) debe llegar al movil.
                if verbose:
                    print(f"  [opened] {symbol:10s} {tf:>3s} {direction:5s} {name} "
                          f"entry {sig.entry_price:.5g} SL {sig.stop_loss:.5g} TP {sig.take_profit:.5g}")
                break
    return opened


def scan_round_fade(conn, symbols, cfg, **kw):
    from round_fade import detect_round_fade
    return _scan_setup(conn, symbols, cfg, detect_round_fade, ("1h", "15m"), "short", "round_fade", **kw)


def scan_micro_pullback(conn, symbols, cfg, **kw):
    from micro_pullback import detect_micro_pullback
    # Solo 15m/1h (auditoria 2026-07-03): en vivo 5m dio 16% de acierto y exp negativa;
    # la unica señal de vida esta en 1h (56% win) y 15m. Medicion CONGELADA ~200 trades.
    return _scan_setup(conn, symbols, cfg, detect_micro_pullback, ("15m", "1h"), "long", "micro_pullback", **kw)


def run_cycle(symbols=None, timeframes=None, cfg: TFZConfig = None,
              fresh_lookback=2, ml_cutoff=0.55, use_ml=True,
              watchlist_source="scanner", verbose=True,
              filter_mode="ml", min_score=60.0, min_rr=8.0):
    cfg = cfg or TFZConfig()
    symbols = resolve_watchlist(symbols, watchlist_source, verbose)
    timeframes = timeframes or ["5m", "15m"]

    conn = get_connection()
    init_db(conn)

    if filter_mode == "profit":
        gate_state = f"PROFIT gate score>={min_score:.0f} & rr>={min_rr:.0f}"
    else:
        gate_state = f"ML gate p>={ml_cutoff:.2f}" if (use_ml and ml_filter._load()) else "ML off"
    print(f"\n[paper cycle @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print(f"  Watchlist: {len(symbols)} symbols x {len(timeframes)} TF | {gate_state}")

    print("  Updating open trades...")
    n_closed = update_open_trades(conn, cfg, verbose)
    print(f"  -> {n_closed} closed")

    # Cartera simulada $50 (riesgo 1%/trade) -> se actualiza al cerrar trades
    try:
        from portfolio import init_portfolio, update_portfolio
        init_portfolio(conn)
        new_pf, pst = update_portfolio(conn)
        for h in new_pf:
            print(f"  [$] {h['symbol'][:12]:12} {h['pnl_pct']:+.2f}% x{h['lev']:.1f} "
                  f"-> ${h['dollar']:+.3f} | cartera ${pst['equity']:.2f}")
    except Exception as _e:
        if verbose:
            print(f"  [portfolio] {_e}")

    # BTC-correlation gate: compute BTC's recent move ONCE per cycle.
    btc_3h = btc_recent_move(cfg) if cfg.btc_block_pct > 0 else None
    if btc_3h is not None:
        print(f"  BTC 3h: {btc_3h:+.2f}% (bloquea contra-BTC si |>={cfg.btc_block_pct}%|)")

    print("  Scanning for new signals...")
    n_opened = scan_new_signals(conn, symbols, timeframes, cfg,
                                fresh_lookback=fresh_lookback,
                                ml_cutoff=ml_cutoff, use_ml=use_ml, verbose=verbose,
                                filter_mode=filter_mode, min_score=min_score, min_rr=min_rr,
                                btc_3h=btc_3h)
    print(f"  -> {n_opened} opened")

    # Setups APARTE (validados, RR propio, fuera del filtro de momentum):
    # micro_pullback RETIRADO por veredicto pre-registrado (2026-07-07): n=384,
    # exp -0.405%/trade, IC95 todo negativo. Gate por config, igual que round_fade.
    _extra = []
    if getattr(cfg, "enable_micro_pullback", False):
        _extra.append(("micro-pullback", scan_micro_pullback))
    if getattr(cfg, "enable_round_fade", False):
        _extra.insert(0, ("round-fade", scan_round_fade))
    for _name, _fn in _extra:
        try:
            _n = _fn(conn, symbols, cfg, fresh_lookback=fresh_lookback, verbose=verbose)
            if _n:
                print(f"  -> {_n} {_name} opened")
            n_opened += _n
        except Exception as _e:
            if verbose:
                print(f"  [{_name}] {_e}")

    print_status(conn)
    conn.close()
    return n_opened, n_closed
