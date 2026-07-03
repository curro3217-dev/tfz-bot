"""
EXPLORACIÓN #13: ANATOMÍA del momentum viernes->sábado (2026-07-03).

DESCRIPTIVO: la regla medida en weekend_paper está SELLADA y aquí no se cambia nada.
Esto es entender el fenómeno y su riesgo para el día que se opere:
  1. PERFIL HORARIO: ¿en qué tramo del sábado se acumula la continuación?
     (retorno acumulado medio, en la dirección del viernes, hora a hora)
  2. ¿DEPENDE DEL TAMAÑO del movimiento del viernes? (quintiles de |ret. viernes|)
  3. RIESGO SEMANAL de la cartera (media de los 42 símbolos por sábado):
     peor semana, racha de semanas perdedoras más larga, drawdown del acumulado.
CUALQUIER regla nueva que salga de aquí (p.ej. "salir a las 12h") necesitaría su
propia validación fuera de universo + pre-registro nuevo. Sin eso, es minería.

Solo lectura. Uso: python explore_friday_anatomy.py
"""
import os
os.environ.setdefault("INSECURE_SSL", "1")

import numpy as np
import pandas as pd
from config import TFZConfig, config_for_timeframe
from data_fetcher import fetch_ohlcv_cached

COST = (0.02 + 0.025) * 2
SYMS = ["AAVE","ADA","ATOM","AVAX","DOT","INJ","NEAR","OP","UNI","SOL",
        "LINK","SUI","SEI","TIA","ENA","ONDO","FET","RENDER","CRV","XLM",
        "DOGE","LTC","BCH","ETC","FIL","APT","ARB","WLD","TON","TRX",
        "1000PEPE","HBAR","ALGO","VET","ICP","GALA","SAND","KAVA",
        "BTC","ETH","BNB","XRP"]


def main():
    cfg = config_for_timeframe(TFZConfig(), "1h")
    perfil = {}      # sabado -> {h: [cum_dir por simbolo]}
    trades = []      # dicts: sabado, sym, fri_abs, pnl (24h, neto)
    for s in SYMS:
        try:
            d = fetch_ohlcv_cached(f"{s}/USDT:USDT", "1h", limit=20000, config=cfg)
        except Exception:
            continue
        d = d.set_index("timestamp")
        daily = d["close"].resample("1D").last().dropna()
        ret = daily.pct_change()
        for t in daily.index:
            if t.weekday() != 5:
                continue
            t_fri = t - pd.Timedelta(days=1)
            t_sun = t + pd.Timedelta(days=1)
            if t_fri not in ret.index or t_sun not in daily.index or pd.isna(ret.get(t)):
                continue
            fr = ret[t_fri]
            if pd.isna(fr) or fr == 0:
                continue
            sgn = np.sign(fr)
            entry = daily[t_fri]                       # cierre del viernes = entrada
            horas = d.loc[t:t + pd.Timedelta(hours=23, minutes=59), "close"]
            if len(horas) < 20:
                continue
            for h_idx, (ht, px) in enumerate(horas.items(), start=1):
                cum = sgn * (px - entry) / entry * 100
                perfil.setdefault(t, {}).setdefault(h_idx, []).append(cum)
            pnl24 = sgn * ret[t] * 100 - COST
            trades.append({"sabado": t, "fri_abs": abs(fr) * 100, "pnl": pnl24})

    tr = pd.DataFrame(trades)

    # 1. perfil horario (medias de medias por sábado)
    print("=== 1. PERFIL HORARIO del sábado (retorno acumulado BRUTO medio, dir. viernes) ===")
    horas_ref = [3, 6, 9, 12, 15, 18, 21, 24]
    serie_h = {}
    for h in range(1, 25):
        vals = [np.mean(v[h]) for t, v in perfil.items() if h in v]
        serie_h[h] = np.mean(vals) if vals else np.nan
    for h in horas_ref:
        print(f"  hora {h:2d}: {serie_h[h]:+.3f}%")
    mejor = max(serie_h, key=lambda k: serie_h[k] if not np.isnan(serie_h[k]) else -9)
    print(f"  (máximo del perfil medio: hora {mejor} con {serie_h[mejor]:+.3f}%)")

    # 2. quintiles del tamaño del viernes
    print("\n=== 2. PnL 24h NETO por quintil de |movimiento del viernes| ===")
    tr["q"] = pd.qcut(tr["fri_abs"], 5, labels=False, duplicates="drop")
    for q, g in tr.groupby("q"):
        p = g["pnl"].values
        se = p.std(ddof=1) / np.sqrt(len(p))
        print(f"  Q{int(q)+1} (|vie| {g['fri_abs'].min():.1f}-{g['fri_abs'].max():.1f}%): "
              f"n {len(p):4d} | exp {p.mean():+.3f}% [{p.mean()-1.96*se:+.3f},"
              f"{p.mean()+1.96*se:+.3f}]")

    # 3. riesgo de la serie semanal (cartera = media por sábado)
    print("\n=== 3. RIESGO de la cartera semanal (media de símbolos por sábado, neto) ===")
    wk = tr.groupby("sabado")["pnl"].mean().sort_index()
    cum = wk.cumsum()
    dd = (cum - cum.cummax())
    racha, peor_racha = 0, 0
    for v in wk.values:
        racha = racha + 1 if v < 0 else 0
        peor_racha = max(peor_racha, racha)
    print(f"  sábados: {len(wk)} | media {wk.mean():+.3f}%/sem | mediana {wk.median():+.3f}%")
    print(f"  peor semana: {wk.min():+.2f}% ({wk.idxmin().date()}) | mejor: {wk.max():+.2f}%")
    print(f"  semanas negativas: {(wk<0).mean()*100:.0f}% | peor racha perdedora: "
          f"{peor_racha} semanas")
    print(f"  drawdown máximo del acumulado: {dd.min():+.2f}% "
          f"(suma acumulada 3 años: {cum.iloc[-1]:+.1f}%)")


if __name__ == "__main__":
    main()
