"""GARCH(1,1) walk-forward: forecast de volatilidad + multiplicador de tamaño.

Linea INFORMATIVA para las alertas del modo asistente (igual que _alert_context
de paper.py): NO filtra, NO altera señales ni el paper congelado. Dice "cuanto",
nunca "hacia donde" (GARCH predice magnitud, no direccion).

El walk-forward esta copiado tal cual de milesdeutscher/garchmethod (MIT,
(c) 2026 Miles Deutscher, scripts/garch_forecast.py + vol_target.py), auditado
el 2026-07-22: cada forecast del dia t+1 usa SOLO datos hasta el cierre de t
(refit cada 21 dias sobre ventana expansiva; entre refits la recursion avanza
con params ya estimados). Sin lookahead.

Sizing: mult = target_vol / forecast_vol, recortado a [0.25x, 2.0x].
Target por defecto 15% anual (desks institucionales); TFZ_GARCH_TARGET lo cambia.

Cache diario por simbolo en garch_cache.json: el forecast solo cambia cuando
cierra la vela diaria, y el walk-forward completo (~80 refits) tarda segundos.
"""

import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

MIN_TRAIN = 500          # dias de historia antes del primer forecast (canonico del repo)
REFIT_EVERY = 21         # re-estimar params cada N dias
REGIME_LOOKBACK = 365    # ventana para percentil / regimen
PERIODS_PER_YEAR = 365   # cripto opera todos los dias
MAX_LEVERAGE = 2.0
MIN_SIZE = 0.25

CACHE_PATH = Path(__file__).parent / "garch_cache.json"


def _target_vol() -> float:
    try:
        return float(os.environ.get("TFZ_GARCH_TARGET", "15"))
    except ValueError:
        return 15.0


def _walkforward_garch(closes: np.ndarray) -> pd.DataFrame | None:
    """Copiado de garchmethod/scripts/garch_forecast.py (walkforward_garch),
    sobre un array de cierres diarios YA CERRADOS. None si falta historia."""
    from arch import arch_model

    rets = 100.0 * np.diff(closes) / closes[:-1]
    n = len(rets)
    if n < MIN_TRAIN + 10:
        return None

    fcast_var = np.full(n, np.nan)
    omega = alpha = beta = mu = None
    sigma2 = None

    for t in range(MIN_TRAIN, n):
        if (t - MIN_TRAIN) % REFIT_EVERY == 0:
            am = arch_model(rets[:t], vol="GARCH", p=1, q=1, mean="Constant", dist="t")
            res = am.fit(disp="off", show_warning=False)
            p = res.params
            mu, omega, alpha, beta = p["mu"], p["omega"], p["alpha[1]"], p["beta[1]"]
            sigma2 = float(res.conditional_volatility[-1] ** 2)
        eps = rets[t] - mu
        sigma2 = omega + alpha * eps ** 2 + beta * sigma2
        fcast_var[t] = sigma2

    out = pd.DataFrame({"fcast_vol": np.sqrt(fcast_var)})
    pct = out["fcast_vol"].rolling(REGIME_LOOKBACK, min_periods=90).apply(
        lambda w: (w.iloc[:-1] < w.iloc[-1]).mean() * 100 if len(w) > 1 else np.nan,
        raw=False)
    out["vol_pctile"] = pct
    return out


def size_from_vol(forecast_vol_ann: float, target_vol_ann: float) -> float:
    """Copiado de garchmethod/scripts/vol_target.py."""
    if forecast_vol_ann is None or forecast_vol_ann <= 0 or np.isnan(forecast_vol_ann):
        return MIN_SIZE
    return float(np.clip(target_vol_ann / forecast_vol_ann, MIN_SIZE, MAX_LEVERAGE))


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text())
    except Exception:
        return {}


def _save_cache(cache: dict):
    try:
        CACHE_PATH.write_text(json.dumps(cache, indent=1))
    except Exception:
        pass


def garch_snapshot(symbol: str) -> dict | None:
    """Forecast de vol para `symbol` con velas diarias CERRADAS de MEXC (mismo
    data_fetcher del bot). Devuelve dict con vol anualizada, percentil 1a,
    regimen y multiplicador — o None si no hay historia (>=510 dias) o falla."""
    try:
        from data_fetcher import fetch_ohlcv

        df = fetch_ohlcv(symbol, timeframe="1d", limit=3000)
        if df is None or len(df) < MIN_TRAIN + 11:
            return None
        d = df.iloc[:-1]                       # solo velas cerradas
        as_of = str(pd.to_datetime(d["timestamp"].iloc[-1]).date())

        cache = _load_cache()
        hit = cache.get(symbol)
        if hit and hit.get("as_of") == as_of:
            return hit

        wf = _walkforward_garch(d["close"].to_numpy(dtype=float))
        if wf is None:
            return None
        last = wf.dropna(subset=["fcast_vol"]).iloc[-1]
        vol_ann = float(last["fcast_vol"]) * np.sqrt(PERIODS_PER_YEAR)
        pctile = float(last["vol_pctile"]) if pd.notna(last["vol_pctile"]) else None
        regime = (None if pctile is None else
                  "calm" if pctile <= 33 else "normal" if pctile <= 67 else "storm")
        target = _target_vol()
        snap = {
            "as_of": as_of,
            "vol_ann_pct": round(vol_ann, 1),
            "pctile_1y": round(pctile, 0) if pctile is not None else None,
            "regime": regime,
            "target_vol_pct": target,
            "size_mult": round(size_from_vol(vol_ann, target), 2),
            "computed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        cache[symbol] = snap
        _save_cache(cache)
        return snap
    except Exception:
        return None


def garch_context_line(symbol: str) -> str:
    """Linea para la alerta de Telegram. Vacia si no se puede calcular
    (fail-silent, mismo contrato que _alert_context)."""
    s = garch_snapshot(symbol)
    if not s:
        return ""
    emoji = {"calm": "🌤", "normal": "⛅", "storm": "⛈"}.get(s["regime"], "")
    reg = f" {emoji}{s['regime'].upper()} p{s['pctile_1y']:.0f}" if s["regime"] else ""
    return (f"GARCH: vol {s['vol_ann_pct']:.0f}% anual{reg} | "
            f"tamaño {s['size_mult']:.2f}x (target {s['target_vol_pct']:.0f}%)")


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT:USDT"
    print(garch_context_line(sym) or f"(sin datos suficientes para {sym})")
