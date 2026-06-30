"""
Setup MICRO-PULLBACK (Warrior Trading), LONG de continuacion de momentum. En tendencia
alcista: una pausa corta (vela con maximo mas bajo) que se mantiene sobre la 9 EMA, y
entrada cuando la vela siguiente ROMPE el maximo de la pausa. Stop = minimo de la pausa,
TP = RR*riesgo. Validado OOS en 5m/15m/1h (mejor en 1h); el control (long aleatorio en
tendencia) es NEGATIVO -> el patron aporta. RR alto (3) -> NO pasa el filtro rr>=6, va aparte.
"""
import uuid
import pandas as pd
from signals import Signal
from swings import compute_trend_strength

MPB_TREND_MIN = 1.0
MPB_RR = 3.0
# Stop ENSANCHADO: el SL se aleja MPB_SL_MULT veces la distancia al minimo de la pausa.
# Validado (mismas 2281 señales, por TF y OOS): x2 sube win 32->44% y expectancy
# +0.131->+0.320% (OOS +0.29->+0.62%), y los trades respiran mas (mediana 2->4 velas,
# cierres en 1 vela 41->21%). El TP se mantiene sobre el riesgo ORIGINAL. Poner 1.0 lo
# revierte al stop ceñido anterior.
MPB_SL_MULT = 2.0

def detect_micro_pullback(df, symbol, tf, cfg):
    n = len(df)
    if n < 40:
        return []
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    ts = df["timestamp"]
    ema9 = pd.Series(close).ewm(span=9, adjust=False).mean().values
    trend = [compute_trend_strength(df, tf, i) for i in range(n)]
    out = []
    i = 30
    while i < n:
        if trend[i] >= MPB_TREND_MIN:
            # i-1 = pausa (maximo mas bajo) que se mantiene sobre la 9EMA;
            # i rompe el maximo de la pausa; hubo subida antes (close[i-2] > close[i-5])
            if (high[i - 1] < high[i - 2] and low[i - 1] >= ema9[i - 1]
                    and high[i] > high[i - 1] and close[i - 2] > close[i - 5]):
                entry = float(high[i - 1])
                pause_low = float(low[i - 1])
                if entry > pause_low:
                    risk0 = entry - pause_low                 # riesgo original (a la pausa)
                    sl = float(entry - MPB_SL_MULT * risk0)   # stop ensanchado
                    tp = float(entry + MPB_RR * risk0)        # TP sobre el riesgo ORIGINAL
                    out.append(Signal(
                        id=str(uuid.uuid4()), timestamp=ts.iloc[i], symbol=symbol, timeframe=tf,
                        direction="long", formation_type="micro_pullback",
                        entry_price=entry, stop_loss=sl, take_profit=tp,
                        risk_pct=round(MPB_SL_MULT * risk0 / entry * 100, 4),
                        rr_ratio=round(MPB_RR / MPB_SL_MULT, 2),
                        total_score=65.0, trigger_idx=i,
                    ))
                    i += 3
                    continue
        i += 1
    return out
