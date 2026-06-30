"""
Setup FADE-SHORT en resistencia de numero redondo (entero). Validado OOS (modesto,
mejor en 1h/15m): en tendencia alcista, cuando el precio TOCA un numero entero por
arriba, vender el rechazo (TP/SL ceñidos ~0.6%). Es high-winrate / RR bajo -> va por su
propio camino (NO pasa el filtro score>=60 & rr>=6 ni el gate de tendencia del momentum).

detect_round_fade(df, symbol, tf, cfg) -> [Signal SHORT, ...] con trigger en el toque.
"""
import math
import uuid
import pandas as pd
from signals import Signal
from swings import compute_trend_strength

# parametros (validados en explore_roundnum5)
FADE_TREND_MIN = 1.0
FADE_TOL = 0.010       # TP/SL a +/-1.0% del nivel. Subido de 0.6% -> 1.0%: el coste
# (~0.2% i/v) pesaba un TERCIO del objetivo de 0.6% (de ahi +0.40/-0.80); a 1.0% pesa un
# quinto y la expectancy validada sube (+0.152 -> +0.212%, OOS +0.224%).
FADE_NEARLO = 0.003    # el precio esta 0.3-1.2% por debajo del nivel
FADE_NEARHI = 0.012
FADE_APPROACH = 60     # velas para que se de el toque tras el acercamiento

def detect_round_fade(df, symbol, tf, cfg):
    """Replica EXACTA del setup validado: en tendencia alcista, cuando el precio esta
    0.3-1.2% por debajo de un numero entero y luego lo TOCA -> short al nivel. Señal en
    la vela del toque."""
    n = len(df)
    if n < 80:
        return []
    closes = df["close"].values
    highs = df["high"].values
    ts = df["timestamp"]
    trend = [compute_trend_strength(df, tf, i) for i in range(n)]
    out = []
    trend_max = getattr(cfg, "round_fade_trend_max", 0.0)
    i = 80
    while i < n - 1:
        # solo fadear en subidas SUAVES: si trend > round_fade_trend_max el redondo
        # tiende a ROMPER (validado: la zona 3-10% pierde; cap a <=3% recupera a +0.15%).
        if trend[i] >= FADE_TREND_MIN and (trend_max <= 0 or trend[i] <= trend_max):
            p = closes[i]
            if p > 0:
                d = 10 ** math.floor(math.log10(p))
                L = (math.floor(p / d) + 1) * d          # entero mas cercano por arriba
                gap = (L - p) / p
                if FADE_NEARLO <= gap <= FADE_NEARHI:     # 0.3-1.2% por debajo
                    tj = None
                    for j in range(i + 1, min(i + FADE_APPROACH, n)):
                        if highs[j] >= L:
                            tj = j
                            break
                    if tj is not None:
                        entry = float(L)
                        sl = float(L * (1 + FADE_TOL))
                        tp = float(L * (1 - FADE_TOL))
                        risk = abs(entry - sl) / entry * 100
                        rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
                        out.append(Signal(
                            id=str(uuid.uuid4()), timestamp=ts.iloc[tj], symbol=symbol, timeframe=tf,
                            direction="short", formation_type="round_fade",
                            entry_price=entry, stop_loss=sl, take_profit=tp,
                            risk_pct=round(risk, 4), rr_ratio=round(rr, 2),
                            total_score=65.0, trigger_idx=tj,
                        ))
                        i = tj + 1
                        continue
        i += 1
    return out


if __name__ == "__main__":
    # Validacion: corre el detector sobre el universo y simula cada señal (TP antes que SL).
    import numpy as np
    from config import TFZConfig, config_for_timeframe
    from data_fetcher import fetch_ohlcv_cached
    UNI = open("_universe.txt").read().split(",")
    POST, COST = 30, 0.12
    for tf in ["1h", "15m", "5m"]:
        trades = []
        for sym in UNI:
            tfc = config_for_timeframe(TFZConfig(), tf)
            try:
                df = fetch_ohlcv_cached(sym, tf, limit=2500, config=tfc)
            except Exception:
                continue
            if len(df) < 300:
                continue
            high = df["high"].values; low = df["low"].values; close = df["close"].values
            ts = df["timestamp"].astype(str).values
            for s in detect_round_fade(df, sym, tf, TFZConfig()):
                i = s.trigger_idx; e = s.entry_price; tp = s.take_profit; sl = s.stop_loss
                end = min(i + POST, len(df)); o = None
                for k in range(i + 1, end):
                    if low[k] <= tp: o = (e - tp) / e * 100 - COST; break
                    if high[k] >= sl: o = (e - sl) / e * 100 - COST; break
                if o is None: o = (e - close[end - 1]) / e * 100 - COST
                trades.append((sym, ts[i], o))
        if trades:
            a = np.array([t[2] for t in trades])
            oos = []
            bysym = {}
            for t in trades: bysym.setdefault(t[0], []).append(t)
            for sy, tt in bysym.items(): tt.sort(key=lambda z: z[1]); oos += tt[:len(tt)//2]
            oe = np.mean([t[2] for t in oos]) if oos else 0
            print(f"{tf:>3s}: {len(a):4d} señales | win {(a>0).mean()*100:.1f}% | exp {a.mean():+.3f}% | OOS {oe:+.3f}%")
        else:
            print(f"{tf:>3s}: 0 señales")
