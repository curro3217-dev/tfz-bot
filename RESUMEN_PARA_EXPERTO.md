# TFZ Bot — Dossier técnico para evaluación externa

> Documento compilatorio del sistema completo de trading algorítmico "TFZ" (Trading From
> Zero), para que un experto pueda evaluarlo. Incluye metodología, arquitectura, parámetros
> exactos, gestión de riesgo, validación y **rendimiento real en vivo (paper)**.
> Fecha del snapshot: 2026-07-02.

---

## 0. Resumen ejecutivo (TL;DR para el experto)

- **Qué es:** bot determinista que opera **perpetuos cripto (USDT)** en MEXC, basado en la
  metodología "Trading From Zero" (Krasnov): niveles de liquidez + liquidity sweeps +
  consolidaciones. Filosofía: **bajo winrate / RR alto** (pocas ganadoras pero grandes).
- **Estado:** en **paper trading** (dinero simulado, $50 inicial, riesgo 1%/trade). Corre en
  paralelo en el PC del usuario y en GitHub Actions (misma lógica, cuentas separadas, para
  comparar). No opera dinero real.
- **Problema que se quiere evaluar:** en vivo, **está perdiendo dinero**. Sobre la muestra
  mayor (63 trades en GitHub) la expectancy es negativa; solo el timeframe **1h** sale
  positivo. Se busca criterio experto sobre si el edge es real, qué está mal, y qué ajustar.
- **Universo:** el bot NO elige monedas; consume una lista de "movers" (monedas que ya se
  movieron >10%) de un **scanner externo** (intocable). Solo decide entradas/salidas sobre esas.

---

## 1. Metodología base (Trading From Zero / Krasnov)

La lógica de detección está especificada al detalle en el fichero adjunto **`TFZ_SPEC_v1.md`**
(≈1000 líneas, spec matemática completa). Resumen de los conceptos:

1. **Swing points** (SH/SL de orden N): máximos/mínimos locales.
2. **Niveles horizontales de liquidez:** clustering de swings (equal highs/lows, triple
   tops). Donde se acumulan stops.
3. **Niveles diagonales:** trendlines con ≥3 toques.
4. **Consolidaciones:** compresión de volatilidad (ATR_fast/ATR_slow ≤ 0.75) en rango acotado.
5. **Liquidity sweep:** el precio rompe un nivel (barre stops) y recupera rápido → señal de
   manipulación. Es el núcleo del edge.
6. **Formaciones (setups):**
   - **F1:** 2 niveles + consolidación (breakout). *Desactivado por defecto.*
   - **F2:** F1 + sweep previo confirmado.
   - **F3:** 3+ niveles en cascada + consolidación.
   - **F4 (manipulation):** sweep + reclaim del nivel barrido (entrada de cambio de tendencia).
7. **Entrada:** al **cierre** de la vela que confirma el trigger (breakout / rotura de
   trendline / reclaim). Nunca dentro del rango, nunca contra tendencia clara.
8. **Stop:** donde el setup se invalida (debajo/encima de la consolidación + colchón ATR).
   Riesgo máx **2%/trade**.
9. **Take-profit:** el nivel de liquidez objetivo más lejano. **RR mínimo 3.0**.
10. **Scoring 0–100** (trend, niveles, consolidación, sweep, cascada, distancia, RR). Umbral
    de operación **≥60** (recalibrado desde 70 tras corregir el cálculo de tendencia).

**Nota de diseño validada (Anexo Z de la spec):** las formaciones SIN sweep daban winrate
~10% y PnL negativo; se hizo **obligatorio un sweep cercano en TODAS las formaciones**. El F1
"puro" del PDF ya no se genera.

---

## 2. Arquitectura del sistema

```
Scanner externo (intocable)  ──movers (BASE/USDT:USDT)──►  BOT TFZ
                                                            │
   MEXC (velas OHLCV, futuros) ◄───────────────────────────┤ data_fetcher.py
                                                            │
   [por cada moneda y TF (1m,5m,15m,1h)]                    │
     1. Filtros de descarte (wicks, gaps, estructura)       │ filters.py
     2. Swings → niveles → consolidaciones → sweeps         │ swings/levels/consolidation/sweep.py
     3. Formaciones F1–F4                                    │ formations.py
     4. Entry/SL/TP + scoring + filtros                      │ signals.py
     5. Filtro ML (probabilidad de acierto)                 │ ml_filter.py (ml_model.joblib)
     6. Apertura/gestión/cierre de paper trades             │ paper.py
     7. Cartera simulada (riesgo 1%, throttle)              │ portfolio.py
     8. Registro en SQLite + autopsia por trade             │ database.py / trade_review.py
```

**Ficheros clave:** `paper.py` (motor en vivo, 39 KB), `signals.py`, `formations.py`,
`config.py` (todos los parámetros), `backtester.py` (simulación histórica), `validate_oos.py`
(validación fuera de muestra).

**Fuente de datos:** MEXC (perp USDT). Se migró desde Binance/Bybit porque estos geo-bloquean
a los servidores de GitHub (451/403); MEXC no. Velas ≈ idénticas a Binance (≤0.014% dif).

**Ciclo:** cada 5 min: (1) re-evalúa trades abiertos (¿SL/TP?), (2) escanea nuevas entradas,
(3) reporta. En GitHub corre en runs largos (~5h40m) encadenados por cron.

---

## 3. Setups adicionales (fuera de la spec original, añadidos y validados por separado)

Aparte de F1–F4, se añadieron dos setups con lógica propia (no pasan el filtro score/RR
estándar, van por su propio carril `_scan_setup`):

- **`micro_pullback`** (Warrior Trading bull-flag): en tendencia alcista, pausa de 1 vela
  (máximo más bajo) por encima de la 9-EMA; entrada al romper el máximo de la pausa. Stop =
  mínimo de la pausa **×2** (`MPB_SL_MULT=2.0`, ensanchado y validado). TP = 3×riesgo original.
  **Es el setup que MÁS opera en vivo** (53 de 63 trades en GitHub).
- **`round_fade`** (fade-short en número redondo): **PAUSADO** (`enable_round_fade=False`)
  porque sangraba en régimen de pumps (los redondos rompen en vez de rechazar).

---

## 4. Parámetros exactos (config.py actual)

### Detección de estructura
| Parámetro | Valor | | Parámetro | Valor |
|---|---|---|---|---|
| swing_order (N) | 3 (1m:2, 1h:5) | | cluster_tol | 0.20% (varía por TF) |
| min_touches | 2 | | min_level_age | 10 velas |
| equal_hl_tol / bonus | 0.10% / +15 | | max_slope_pct (diag) | 5.0% |
| compression_threshold | 0.75 | | compression_exit | 0.90 |
| consolidation_min_duration | 6 velas | | consolidation_max_range | 4.0% |
| max_sweep_candles | 6 | | max_sweep_depth | 3.0% (1h:2, 1m:1) |
| reclaim_window | 6 | | continuation_window | 10 |

### Riesgo / entrada / salida
| Parámetro | Valor | Nota |
|---|---|---|
| max_risk_pct | **2.0%** | riesgo máx por trade |
| min_rr | **3.0** | RR mínimo |
| sl_atr_offset_mult | **0.5** | colchón del stop (0.1→0.5, validado OOS: WR 40→47%, exp +2.06→+2.72%) |
| stale_candles | **80** | cierre por "sin avance" (30→80, validado OOS +2.16→+2.71%) |
| score_minimo | **60** | (70→60 tras corregir tendencia; pico de expectancy OOS/IS en 60) |
| trend_block_pct | **5.0%** | bloquea contra-tendencia si \|tendencia 1d\| ≥ 5% |
| trend_lookback_hours | **4h** | tendencia por regresión sobre 4h (antes 24h) |
| btc_block_pct | **1.0%** | no abrir contra un movimiento fuerte de BTC en 3h |
| max_open_per_dir | **3** | máx posiciones en la misma dirección (correlación alt/BTC) |
| reentry_cooldown_min | **30 min** | no reabrir moneda+dir tras un SL (evita el "chop") |
| f3_min_score | **80** | F3 (cascada) exige más score (es la formación más floja) |
| rvol_min | 1m:2.0, 15m:1.5 | filtro volumen relativo (Warrior Trading) |

### Costes (netos, se descuentan del PnL)
- commission 0.075%/lado + slippage 0.025%/lado = **0.20% ida y vuelta**. funding perp: 0 (a revisar).

### Desactivados / en prueba (flags off)
trailing stop, BE-lock, toma parcial, round_tp_snap, F1, f1_retest, f4_require_consol.

---

## 5. Gestión de riesgo (portfolio.py)

- Capital inicial **$50**, sizing por **RIESGO 1% del equity por trade** (el apalancamiento se
  ajusta al stop; tope **10×**). El P&L en $ compone.
- **Throttle por drawdown ("Trader Rehab"):** desde −10% de drawdown → riesgo a la mitad;
  desde −20% → a la cuarta parte. Reduce la profundidad del bache a cambio de recuperar más
  despacio.
- Cap de correlación (máx 3 en la misma dirección) porque en cripto los alts van correlados
  con BTC → N longs = una sola apuesta grande.

---

## 6. Filtro ML (fase 2)

- `ml_model.joblib` (sklearn 1.9.0): clasificador entrenado sobre features del setup (score,
  RR, RVOL, tendencia, distancias…) que estima la **probabilidad de acierto**. Trades por
  debajo del corte se descartan. Se puede desactivar (`--no-ml`). Actualmente **activo** en PC
  y GitHub.

---

## 7. Validación hecha hasta ahora

- **Out-of-sample (OOS):** por símbolo, mitad antigua = OOS vs mitad reciente = IS (87
  símbolos, ~20k velas/símbolo). Todos los ajustes clave confirmados fuera de muestra y netos
  de costes (`validate_oos.py`).
- **Walk-forward** (`walkforward*.py`), **Monte Carlo** de robustez (`montecarlo_robustness.py`),
  **barridos de umbral** (`optimize_thresholds.py`).
- **Selftest de reproducibilidad:** hash idéntico PC vs GitHub → misma lógica en ambos.

---

## 8. Bugs encontrados y corregidos (contexto importante para el experto)

Recientemente se detectaron y arreglaron **dos fallos que inflaban falsamente los resultados**
del paper en vivo (no afectaban al backtester, sí al motor en vivo `_scan_setup`):

1. **Backdating de entrada:** los setups `micro_pullback`/`round_fade` abrían el trade fechado
   en la **vela del trigger** (a veces varias velas atrás) y lo evaluaban contra velas **ya
   cerradas** → cierres instantáneos, casi siempre en TP → winrate falso. **Fix:** reanclar
   entrada al **precio y vela ACTUAL** (como ya hacía el path principal de F1–F4), y descartar
   si el precio ya se salió de [SL,TP] ("moved-skip").
2. **Duplicados:** como cerraban en el mismo ciclo, la misma señal se **reabría cada ciclo**
   (una señal de TAC se registró 15 veces). **Fix:** deduplicar por
   símbolo+TF+vela+dirección+formación en `open_paper_trade`.

**Los números de rendimiento de abajo son POST-fix (limpios).**

---

## 9. RENDIMIENTO REAL EN VIVO (paper) — lo que se quiere evaluar

Dos cuentas paper independientes, misma lógica, arrancadas de cero ($50). Snapshot 2026-07-02:

### Cartera
| | PC | GitHub |
|---|---|---|
| Equity | ~$45.9 | **~$39.2 (−21,6%)** |
| Trades cerrados | ~30 | **63** |
| Winrate | ~40% | ~27% |

> La cuenta de **GitHub es la muestra más fiable** (63 trades, corrió sin interrupción). La del
> PC tuvo menos trades (posible tiempo apagado) y está sesgada por 1 outlier de +52%.

### Desglose GitHub (63 cerrados) — por FORMACIÓN
| Setup | n | winrate | expectancy/trade | suma |
|---|---|---|---|---|
| micro_pullback | 53 | 32% | **−0.083%** | −4.4% |
| F4_manipulation | 4 | 0% | −0.582% | −2.3% |
| F3 | 5 | 0% | −0.230% | −1.1% |
| F2 | 1 | 0% | −0.202% | −0.2% |

### Desglose GitHub — por TIMEFRAME (muy revelador)
| TF | n | winrate | expectancy/trade |
|---|---|---|---|
| **1h** | 16 | **56%** | **+0.566%** ✅ |
| 15m | 16 | 25% | −0.386% |
| 5m | 25 | 16% | −0.360% |
| 1m | 6 | 0% | −0.320% |

- Motivos de cierre GitHub: **34 SL / 24 TP / 5 breakeven**.
- Mejor/peor trade GitHub: +4.77% / −2.25%.

**Lectura de los datos (para contrastar con el experto):**
- El único timeframe con edge positivo claro es **1h**. Los intradía rápidos (5m, 1m) son
  claramente negativos.
- Las formaciones "puras" del método (F2/F3/F4) tienen **0% winrate** en esta muestra (aunque
  con n muy pequeño: 1–5 trades cada una).
- El setup que más opera (`micro_pullback`, ajeno a la spec original) es **ligeramente
  negativo** en vivo, pese a validar positivo en backtest OOS.

---

## 10. Preguntas abiertas para el experto

1. ¿El edge del método (sweep + niveles) es real o es sobreajuste del backtest? El backtest OOS
   daba +2.7%/trade; en vivo la expectancy es negativa. ¿Dónde está la fuga (costes, slippage
   real, selección de universo, look-ahead residual)?
2. **1h positivo vs 5m/1m negativo:** ¿conviene operar SOLO 1h/15m y abandonar los rápidos?
3. `micro_pullback` (Warrior Trading) domina las operaciones pero es marginal en vivo. ¿Mantener,
   ajustar (RR, stop, filtro de tendencia) o retirar?
4. El universo viene de un scanner de "movers" (monedas ya +10%). ¿Sesga esto las entradas
   (compramos fuerza ya agotada)? ¿Impacto en el edge?
5. Sizing riesgo 1% + tope 10× + throttle por drawdown: ¿adecuado para esta distribución de
   resultados (cola de pérdidas por correlación con BTC)?
6. ¿Es la muestra (30–63 trades) suficiente para concluir algo, o es ruido?

---

## 11. Cómo reproducir / inspeccionar

```
# Estado del paper:            python main.py paper --status
# Cartera simulada:            python main.py portfolio
# Un ciclo de paper:           python main.py paper --timeframe 1m,5m,15m --fresh 3 \
#                                --filter profit --min-score 60 --min-rr 6 --enable-f1 --f1-retest
# Backtest histórico:          python main.py backtest ...
# Validación OOS:              python validate_oos.py --score-floor 60
```
- Datos: SQLite `tfz_data.db` (tabla `paper_trades`, `trade_review`).
- Config: todo en `config.py` (dataclass `TFZConfig` + `TIMEFRAME_PARAMS`).
- Historial de cambios y su porqué: `CHANGELOG.md`.
- Spec completa de la metodología: **`TFZ_SPEC_v1.md`** (adjuntar junto a este documento).

---

*Adjuntar al experto: este fichero + `TFZ_SPEC_v1.md` + `config.py` + `CHANGELOG.md`. Con eso
tiene la metodología, los parámetros exactos, la evolución y el rendimiento real.*
