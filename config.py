from dataclasses import dataclass, field
from typing import Dict


@dataclass
class TFZConfig:
    # --- Swing detection (spec §2) ---
    swing_order: int = 3
    min_swing_separation: int = 5
    noise_threshold_mult: float = 0.3
    atr_period: int = 14

    # --- Horizontal levels (spec §3) ---
    cluster_tol: float = 0.0020  # 0.20%
    min_touches: int = 2
    min_level_age: int = 10  # candles
    equal_hl_tol: float = 0.0010  # 0.10%
    equal_hl_bonus: int = 15

    # --- Diagonal levels (spec §4) ---
    tol_diagonal: float = 0.0020  # 0.20%
    max_slope_pct: float = 5.0

    # --- Consolidation (spec §5) ---
    atr_fast_period: int = 5
    atr_slow_period: int = 20
    compression_threshold: float = 0.75
    compression_exit: float = 0.90
    consolidation_min_duration: int = 6  # candles
    consolidation_max_range: float = 4.0  # %
    consolidation_min_range: float = 0.2  # %

    # --- Liquidity sweep (spec §6) ---
    max_sweep_candles: int = 6  # was 3; loosened (validated: catches more valid sweeps)
    max_sweep_depth: float = 3.0  # % (was 1.5)
    reclaim_window: int = 6  # candles (was 3)
    continuation_window: int = 10  # candles

    # --- Distance between levels (spec §14.2) ---
    dist_max_altcoin: float = 3.0  # %
    dist_max_topcoin: float = 2.0  # %
    top_coins: list = field(default_factory=lambda: [
        "BTC", "ETH", "SOL", "BNB", "XRP",
    ])

    # --- Pullback (spec §14.3) ---
    pullback_max: float = 15.0  # %

    # --- Single level target (spec §14.4) ---
    single_level_pump_min: float = 30.0  # %

    # --- Risk management (spec §10-11) ---
    max_risk_pct: float = 2.0
    min_rr: float = 3.0
    # 0.1 -> 0.5 (2026-06-22): barrido del colchón del stop validado OOS. Un stop
    # más ancho (0.5xATR pasado la estructura) aguanta el ruido: winrate 40%->47%
    # y expectancy +2.06%->+2.72%/trade, con RR aún ~12 (no se carga el RR). La
    # mejora por trade se mantiene en la mitad OOS (no sobreajuste). Ver CHANGELOG.
    sl_atr_offset_mult: float = 0.5

    # --- Trailing stop (chandelier) ---
    # Una vez el trade va a favor (>= trail_activate_r en R), el stop se sube a
    # trail_atr_mult x ATR por debajo del MÁXIMO alcanzado (long) y solo sube,
    # nunca baja. Bloquea parte del runup en lugar de devolverlo (casos SYN/INJ
    # que llegaron a +18%/+2.4% y cerraron en +1%). Desactivado por defecto hasta
    # validar con datos qué k mejora el neto sin recortar los ganadores grandes.
    trail_enabled: bool = False
    trail_atr_mult: float = 3.0
    trail_activate_r: float = 1.0  # activar tras +1R de beneficio

    # BE-lock por runup: tras +N R a favor, mover el SL a la entrada (sin pérdida) y
    # dejarlo (NO trailing). Protege a los corredores probados sin tocar el techo.
    # 0 = desactivado. En prueba (patrón "corre +3R y se gira").
    be_lock_runup_r: float = 0.0
    be_lock_to_r: float = 0.0  # a dónde mover el SL al activar: 0=entrada (sin pérdida), 3=asegura +3R

    # TP en numero redondo: si el objetivo cae a <=round_tp_tol de un numero redondo
    # (multiplo de 10^floor(log10)), salir en el redondo (resistencia validada). En prueba.
    round_tp_snap: bool = False
    round_tp_tol: float = 0.01

    # Filtro de volumen relativo (RVOL = vol vela / media 20 velas). Se setea por TF
    # en TIMEFRAME_PARAMS (1m:2.0, 15m:1.5, 5m/1h:0=off). 0 = sin filtro.
    rvol_min: float = 0.0

    # F3 (cascada) es la formacion mas floja: exige mas score que las demas (validado:
    # F3>=80 sube de +0.85% a +1.30%/trade y el conjunto +2.31->+2.45%). Las otras en 60.
    f3_min_score: float = 80.0

    # MODO ASISTENTE (2026-07-03, tras auditoria externa + test forense): el test A/B
    # confirmo que el edge del backtest de F1-F4 era LOOK-AHEAD (sin futuro: negativo en
    # todas las TFs). Decision: las formaciones F1-F4 ya NO abren trades; solo ALERTAN
    # por Telegram (decide el humano). El paper sigue midiendo micro_pullback (15m/1h)
    # congelado. Poner True para volver a operar formaciones automaticamente.
    trade_formations: bool = False

    # Fade-short en numero redondo: PAUSADO (sangraba en regimen de pumps fuertes, los
    # redondos rompen en vez de rechazar). Se reactiva con tope de tendencia si valida.
    enable_round_fade: bool = False
    # Tope de tendencia para el fade: no fadear si la subida es mas fuerte que esto (en
    # subidas moderadas-fuertes el redondo ROMPE). Validado: cap <=3% recupera a +0.15%
    # win 64% (vs +0.037% sin tope). 0 = sin tope.
    round_fade_trend_max: float = 3.0

    # --- Toma de beneficios PARCIAL (método de Mark) ---
    # Al alcanzar partial_frac del camino al TP, cerrar partial_size de la posición
    # y mover el stop del resto a breakeven; el resto sigue hasta el TP/stale.
    # Banca parte del runup en vez de devolverlo (casos SYN/INJ). Desactivado por
    # defecto hasta validar qué combinación mejora el neto.
    partial_enabled: bool = False
    partial_frac: float = 0.5   # fracción del camino entry->TP donde se toma parcial
    partial_size: float = 0.5   # fracción de la posición que se cierra en el parcial

    # --- F4: exigir consolidación previa (criterio de Mark: "no consolidation,
    # no entry") --- el precio debe haber consolidado cerca del nivel ANTES del
    # barrido. Si va directo a barrer sin consolidar, no es entrada válida.
    # Off por defecto; la medición usa el tag f4_has_consol sin filtrar.
    f4_require_consol: bool = False
    f4_consol_window: int = 20  # velas máx entre fin de consolidación y el sweep

    # --- Trading costs (commissions + slippage) ---
    commission_pct: float = 0.075  # taker fee per side, % (bybit/binance spot ~0.075-0.1)
    slippage_pct: float = 0.025    # estimated slippage per side, %
    funding_pct_per_8h: float = 0.0  # perp funding rate per 8h, %; 0 = spot (no funding)

    # --- Scoring (spec §13) ---
    # Recalibrated 70 -> 60 after fixing trend scoring: an OOS/IS threshold sweep
    # showed expectancy peaks at 60 in BOTH halves (OOS +0.62%, IS +0.65%) with
    # ~512 trades; 70 was discarding good F4 trades that no longer reach it now
    # that trend points aren't uniformly inflated.
    score_minimo: int = 60

    # --- Chart quality filters (spec §14.1) ---
    wick_ratio_max: float = 0.70
    gap_threshold: float = 1.0  # %
    max_gap_count: int = 5
    min_swings_required: int = 3
    filter_lookback: int = 50  # candles

    # --- Trade management (spec §12) ---
    # 30 -> 80 (2026-06-24): barrido LIMPIO (mismos trades) + validado OOS. Dar más
    # aire antes de cortar por "sin avance" sube la expectancy de forma robusta:
    # OOS +2.157%->+2.705%/trade (30->80). El 120 ya casi no aporta OOS (+2.779%) y
    # ata el capital demasiado (30h en 15m). 80 = punto óptimo. Ver CHANGELOG.
    stale_candles: int = 80
    weakness_atr_mult: float = 0.5
    weakness_window: int = 10  # candles
    retest_atr_mult: float = 0.2

    # --- Bear market (spec §16) ---
    bear_tp_distance: float = 5.0  # %
    bear_tp_factor: float = 0.8
    bear_max_risk_pct: float = 1.5
    bear_score_minimo: int = 65  # was 75; kept 5pts above score_minimo (60) for bear strictness

    # --- Cap de correlación / exposición (riesgo) ---
    # Máx posiciones abiertas EN LA MISMA DIRECCIÓN a la vez. En cripto los alts van
    # casi todos correlados con BTC, así que N longs = una sola apuesta grande; un
    # volcón los tira a todos juntos (visto en vivo). Limita el riesgo de cola y hace
    # realista el margen de una cuenta pequeña. 0 = sin límite.
    max_open_per_dir: int = 3

    # Cooldown anti-re-entrada: tras un SL/breakeven en una moneda+dirección, no
    # reabrir esa misma combinación durante N minutos (evita que el bot se deje
    # "picar" varias veces seguidas en el mismo chop). 0 = desactivado. Es un
    # seguro de comportamiento EN VIVO (no medible en backtest).
    reentry_cooldown_min: float = 30.0

    # --- Multi-timeframe (spec §15) ---
    mtf_bonus: int = 10  # bonus for levels appearing on multiple TFs

    # --- Trend gate (spec §9.2/§13): never trade against a CLEAR trend ---
    # When |1d trend| >= this %, counter-trend signals are blocked outright for
    # ALL formations (incl. F4). Below it the market is treated as ranging and
    # either direction is allowed. (Removed the old F4 counter-trend exemption,
    # which was taking long-in-downtrend / short-in-uptrend losers.)
    trend_block_pct: float = 5.0
    # Ventana (horas) para medir la tendencia del gate, ahora por REGRESIÓN (ver
    # swings.compute_trend_strength). 4h = tendencia RECIENTE visible: el bot "ve" la
    # caída/subida que ve el ojo en el gráfico, no el neto de hace un día. Antes 24h
    # con 2-puntos hacía que una moneda en caída saliera "alcista".
    trend_lookback_hours: float = 4.0

    # --- F1 (dos niveles + consolidación SIN sweep, spec §7.1) ---
    # Desactivado por defecto (mecánicamente perdía en el test viejo). Flag para
    # re-testearlo BIEN: con tendencia obligatoria (ya en generate_signals) + 2+
    # niveles fuertes + consolidación, que son las condiciones reales del método.
    enable_f1: bool = False
    # Gestión estilo Mark para F1: si el breakout no funciona en f1_be_candles velas
    # (max_runup < f1_be_min_runup %), salir al precio actual (~breakeven) en vez de
    # esperar el stop completo. Es la "mitad del método" que el PDF enfatiza.
    f1_mgmt: bool = False
    f1_be_candles: int = 3
    f1_be_min_runup: float = 0.5  # %
    # F1: entrar en el RETEST que aguanta (no en la vela de ruptura). Filtra falsos
    # breakouts (los que no aguantan el retest se descartan) -> sube el winrate.
    f1_retest_entry: bool = False
    f1_retest_window: int = 8     # velas tras el breakout para buscar el retest
    f1_retest_tol: float = 0.003  # tolerancia para "tocar" el nivel (0.3%)

    # --- Filtro de correlación con BTC ---
    # No abrir una señal que vaya en contra de un movimiento FUERTE de BTC:
    # si |BTC en 3h| >= este %, se bloquea long-cuando-BTC-cae / short-cuando-sube.
    # Validado: los contra-BTC con BTC fuerte tienen ~0-20% de acierto. 0 = desactivado.
    btc_block_pct: float = 1.0

    # --- Data ---
    # MEXC como fuente principal: es el UNICO exchange con futuros en vivo que NO
    # geo-bloquea a GitHub (Binance da 451 y Bybit 403 desde los runners de EEUU;
    # verificado contra 11 endpoints). Asi el bot puede correr 24/7 en GitHub igual
    # que en el PC (misma fuente -> selftest identico). Cobertura ~29/30 monedas; velas
    # identicas a Binance (<=0.014% dif). Binance queda de respaldo (solo funciona desde
    # el PC). REVERSIBLE: para volver a Binance, poner default_exchange="binance".
    # La cache se separa por exchange, asi que no se mezcla con la de Binance/Bybit.
    default_exchange: str = "mexc"
    fallback_exchange: str = "binance"
    default_timeframes: list = field(default_factory=lambda: ["5m", "15m"])

    def get_dist_max(self, symbol: str) -> float:
        base = symbol.split("/")[0].upper()
        if base in self.top_coins:
            return self.dist_max_topcoin
        return self.dist_max_altcoin


TIMEFRAME_PARAMS: Dict[str, dict] = {
    "1m": {
        "swing_order": 2,
        "cluster_tol": 0.0010,
        "consolidation_min_duration": 10,
        "consolidation_max_range": 2.0,
        "max_sweep_depth": 1.0,
        "noise_threshold_mult": 0.2,
        "rvol_min": 2.0,   # filtro volumen relativo (Warrior Trading): casi DOBLA expectancy en 1m
    },
    "5m": {
        "swing_order": 3,
        "cluster_tol": 0.0015,
        "consolidation_min_duration": 6,
        "consolidation_max_range": 4.0,
        "max_sweep_depth": 3.0,
        "noise_threshold_mult": 0.3,
    },
    "15m": {
        "swing_order": 3,
        "cluster_tol": 0.0020,
        "consolidation_min_duration": 6,
        "consolidation_max_range": 4.0,
        "max_sweep_depth": 3.0,
        "noise_threshold_mult": 0.3,
        "rvol_min": 1.5,   # filtro volumen relativo: mejora leve en 15m
    },
    "1h": {
        "swing_order": 5,
        "cluster_tol": 0.0030,
        "consolidation_min_duration": 6,
        "consolidation_max_range": 4.0,
        "max_sweep_depth": 2.0,
        "noise_threshold_mult": 0.4,
    },
}


def config_for_timeframe(base: TFZConfig, tf: str) -> TFZConfig:
    import copy
    cfg = copy.deepcopy(base)
    if tf in TIMEFRAME_PARAMS:
        for k, v in TIMEFRAME_PARAMS[tf].items():
            setattr(cfg, k, v)
    return cfg
