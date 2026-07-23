# TFZ Bot — Registro de cambios (CHANGELOG)

Registro cronológico de TODO lo que se ha tocado, para poder **retroceder** si algo
se rompe. Cada entrada indica QUÉ cambió, en QUÉ archivo y con qué VALORES, más el
porqué. Lo más reciente arriba del todo de cada día. Fechas en formato AAAA-MM-DD.

> Este proyecto NO usa git, así que este archivo es la única "máquina del tiempo".
> Antes de un cambio grande, conviene copiar el archivo afectado a `*.bak`.

---

## 2026-07-23

### Observación (NO cambia nada): el mal sábado del weekend (11-jul) fue MACRO
- **Contexto**: al revisar los 122 trades del `weekend_paper`, el negativo de las 3
  semanas (media −0.32%/semana) lo arrastra **un solo sábado, el 11-jul**
  (−0.880%, 24% aciertos; los otros dos: +0.022% y −0.108%).
- **Dónde falló**: ese sábado, 34 de 41 monedas venían de viernes alcista → 34
  largos; el sábado el mercado se giró y esos largos hicieron −0.91% de media. Los
  8 peores fueron largos que se dieron la vuelta (DOT vie +6.05%→sáb −2.51%,
  1000PEPE +7.42%→−3.22%, GALA +1.89%→−3.39%…): cuanto más fuerte el viernes, más
  brusca la reversión.
- **¿Fue de las alts o macro? → MACRO**. Comprobado en BTC (velas 1h MEXC, retorno
  00:00→24:00 UTC): el mismo patrón en los 3 findes.
  - 03-jul vie +2.37% → sáb 04 +0.36% (siguió; buen sábado)
  - **10-jul vie +1.59% → sáb 11 −0.46% (SE GIRÓ; sábado malo)**
  - 17-jul vie +0.03% → sáb 18 +1.37% (siguió)
  BTC también venía de viernes verde y el sábado se puso rojo. No fue selección de
  monedas: el mercado entero revirtió. Las alts amplificaron (−0.91% vs −0.46% BTC),
  lo normal por su mayor beta.
- **Lado**: todo el negativo es del lado LARGO (96 largos, media −0.441%, 40%
  aciertos) vs SHORT (26, +0.107%, 50%). Coherente con un julio-2026 bajista:
  "seguir al viernes alcista" mete largo antes de que el finde retome la caída.
- **Conclusión**: NO se toca nada. Es 1 de 3 sábados; que el fallo sea macro
  explica el porqué pero no adelanta el veredicto (criterio sellado: 20 sábados,
  precisamente para que un día así no decida). Registro solo la observación.

## 2026-07-22

### Medición forward PRE-REGISTRADA: las ALERTAS F del asistente
- **Agujero que tapa**: desde que se retiró `micro_pullback` (16-jul) el bot es
  asistente puro y manda alertas F a Telegram, pero **nadie registraba si
  aciertan**. Comprobado: `paper_trades` no tiene ni una fila posterior al
  2026-07-16. El 35.2% de acierto del panel es del `micro_pullback` MUERTO, no de
  lo que llega hoy al Telegram. Detectado al revisar 3 alertas de ENA del 22-jul.
- **Qué**: `f_alerts_paper.py` (NUEVO) + BD propia `f_alerts_paper.db`
  (env `TFZ_FALERTS_DB`). No toca nada existente ni filtra ninguna señal.
- **Grabación**: `paper.py::_alert_once` llama a `record_alert()` **fail-silent**
  justo tras enviar la alerta (si falla, la alerta sale igual). Clave idéntica al
  dedup del bot → idempotente.
- **Resolución**: se recorren velas del mismo TF ESTRICTAMENTE posteriores a la de
  la señal; gana el primer toque de SL o TP. Si una MISMA vela toca los dos →
  se cuenta **SL** (pesimista: dentro de la vela no se sabe el orden). Timeout a
  `TIMEOUT_BARS=96` velas → salida a cierre. Costes `(0.02+0.025)*2 = 0.09%` i/v
  (estándar de la casa). **Funding NO modelado.**
- **START_TS = 2026-07-22 19:30 UTC** (21:30 Madrid). Sellado **después** de haber
  mirado el desenlace de las 3 alertas de ENA de esa mañana (SL tocado a las 10:30
  Madrid) → esas quedan FUERA a propósito: su resultado ya se conocía y meterlas
  contaminaría la muestra.
- **CRITERIO PRE-REGISTRADO** (sellado antes de la primera alerta medida):
  - **PRIMARIO**: a **≥100 EPISODIOS** resueltos, hay edge si la media neta por
    episodio es **> +0.20%** con IC95 excluyendo cero. Si no → se archiva.
  - **EPISODIO**: alertas consecutivas del mismo símbolo/TF/dirección/formación
    separadas por menos de `EPISODE_GAP=4` velas cuentan como UNA (la primera).
    Motivo: el dedup del bot es por VELA, así que un mismo setup dispara varias
    alertas seguidas — el 22-jul ENA disparó **3 en 27 min** con el mismo SL/TP.
    Contarlas por separado inflaría n con datos casi idénticos. Mismo principio
    que `weekend_paper` promediando por sábado.
  - **SECUNDARIO** (descriptivo, NO decide): media sobre TODAS las alertas y
    desglose por formación. Se miran para entender, no para buscar un ganador.
  - Prohibido tocar definiciones/umbrales una vez haya el primer dato.
- **Validación del motor** (antes de sellar, en BD desechable y ya borrada): se
  reprodujeron las 3 alertas de ENA del 22-jul. Resultado del motor: `sl_hit` en
  la vela `2026-07-22 08:30 UTC` (=10:30 Madrid) y −1.38/−1.36/−1.46% netos; el
  agrupado dio **3 alertas → 1 episodio**. Coincide con la comprobación
  independiente de precios MEXC. La BD real quedó en 0 filas.
- **Enganche**: paso nuevo en el bucle de `.github/workflows/bot.yml` tras
  `postpump_paper`. `TFZ_FALERTS_DB` va en el **env del BUCLE**, no solo en ese
  paso, porque la GRABACIÓN ocurre dentro de `main.py paper` — si estuviera solo
  en el paso que resuelve, se escribiría fuera de `github_state/` y se perdería
  al acabar el run.
- **Panel**: `estado.py` lo lista como bloque nuevo (antes del asistente).
- **Pendiente conocido**: `postpump_paper.py` sigue SIN aparecer en `estado.py`
  (no tiene `--status`); hay que consultarlo a mano.

### Medición forward PRE-REGISTRADA: sizing GARCH vs 1x sobre los cruces EMA
- **Qué**: `garch_sizing_paper.py` (NUEVO) compara, sobre los MISMOS cruces del
  EMA paper (lee `ema_cross_paper.db` en SOLO-LECTURA, `mode=ro` — imposible
  tocar la medición congelada), dos tamaños: fijo 1x vs GARCH
  (`mult = 35 / vol_prevista`, recortado [0.25x, 2.0x], mult congelado al fill).
- **Target pre-registrado**: 35% anual, risk-matched (vol realizada de la
  estrategia a 1x en la réplica MEXC 2020→2026: 33.7%). En esa réplica SIN
  costes el vol-targeting dio CAGR 12.3 vs 10.7, Sharpe 0.63 vs 0.47, maxDD
  −38.6 vs −60.2 — es backtest, NO veredicto.
- **Criterio sellado**: se reportan ambas equities y drawdowns; sin veredicto
  hasta ≥20 trades cerrados (~3 años, mismo criterio que el EMA paper).
  Salvedad fija: funding no modelado en ninguna variante.
- **Sin lookahead aunque corra tarde**: el walk-forward asigna a cada fecha un
  forecast hecho solo con datos anteriores → backfillear da el mismo número.
- **Dónde corre**: PC (`run_ema_paper.cmd` a las 03:05, misma tarea que el EMA
  paper) y GitHub (paso nuevo en `bot.yml`, BD en
  `github_state/garch_sizing_paper.db`). `estado.py` lo lista (6 bloques ya).

### Línea GARCH (vol + tamaño sugerido) en las alertas F del asistente
- **Qué**: cada alerta F de Telegram lleva ahora una línea informativa tipo
  `GARCH: vol 42% anual ⛅NORMAL p35 | tamaño 0.36x (target 15%)` — volatilidad
  prevista para mañana (GARCH(1,1) walk-forward sobre velas DIARIAS cerradas de
  MEXC), percentil vs último año, régimen (calm/normal/storm) y multiplicador de
  tamaño `target_vol / forecast_vol` recortado a [0.25x, 2.0x].
- **Archivos**: `garch_sizing.py` (NUEVO — walk-forward copiado tal cual de
  github.com/milesdeutscher/garchmethod, MIT, auditado sin lookahead el 22-jul;
  caché diaria por símbolo en `garch_cache.json`), `paper.py` (`_alert_once`:
  añade la línea al contexto, fail-silent), `requirements.txt` (+`arch>=6.0`).
- **Valores**: MIN_TRAIN 500 días, refit cada 21, percentil sobre 365 días,
  target vol 15% anual (cambiable con env `TFZ_GARCH_TARGET`).
- **Qué NO toca**: nada. No filtra señales, no altera paper congelado ni
  mediciones forward. Si el símbolo no tiene ≥510 días de historia diaria en
  MEXC o algo falla, la alerta sale igual que antes (sin la línea).
- **Porqué**: sizing por volatilidad (vol targeting) del método GARCH del curso;
  el asistente sigue decidiendo el humano, esto solo añade el dato de "cuánto".

## 2026-07-19

### Revisión dominical (2ª semana) — solo lectura, sin cambios de reglas
- `estado.py`: EMA y Ichimoku siguen sin cruces/cambios medibles (normal, sellados
  hace 4-5 días). Prima Coinbase sin episodios abiertos/cerrados (BTC/ETH 0/30).
  Finde: 3 sábados (04, 11, 18-jul), 122 trades, PRIMARIO −0.322% [IC95 −0.874,
  +0.230], SECUNDARIO +0.350% [IC95 −0.775,+1.475] — ninguno de los dos criterios
  se evalúa aún (hace falta ≥20 sábados). Asistente: 165 cerrados, WR 35.2%,
  expectancy −0.623%/trade (solo alertas F, sin acción — como desde el 16-jul).
- Tarea Windows `TFZ_Weekend_Paper` corrió con `LastTaskResult 0` (éxito) pero
  TARDE: programada 03:15, ejecutada 10:45 (el PC estaba apagado/dormido a esa
  hora; Task Scheduler la lanzó al arrancar). Sin acción: el dato del sábado quedó
  registrado igual, solo con retraso. Vigilar si se repite.
- Contraste PC vs GitHub (`github_state/weekend_paper.db`): coinciden en los 3
  sábados EXCEPTO `FIL/USDT:USDT`, ausente en la copia de GitHub las 3 semanas
  (40/40/39 trades en GitHub vs 41/41/40 en PC). Un solo símbolo de 42, no cambia
  las medias de forma relevante; parece fallo de fetch específico de GitHub
  Actions para ese par en MEXC (misma causa que otros geo-bloqueos ya vistos, o
  delisting regional). No se ha tocado el universo (sellado 2026-07-03) — queda
  anotado para investigar si persiste, no es urgente con la muestra actual.
- Workflow "TFZ Bot Paper" en GitHub Actions: activo y corriendo (commits
  automáticos "estado paper ciclo N" cada ~15-20 min, último `ciclo 52` a las
  10:39). Sin anomalías de infraestructura que arreglar.
- `LECCIONES.md`: sin lección nueva. Con solo 3 sábados de finde y 0 eventos de
  EMA/Ichimoku/prima, no hay evidencia suficiente para ninguna lección (añadir
  una ahora sería justo el error que advierte la lección 2 de muestras pequeñas).

## 2026-07-18

### Arreglados los enlaces de TradingView de las alertas (pendiente del 16-jul)
- `notify.tv_link` enlazaba siempre `BYBIT:{base}USDT.P`, pero el bot opera MEXC
  y varias monedas del scanner no existen en Bybit (SYN…) ni todas en MEXC
  (AIGENSYN…) → "símbolo no existe" al abrir la alerta.
- Nuevo `notify._tv_feed`: pregunta al buscador público de TradingView qué
  exchanges tienen `{base}USDT.P` y elige por preferencia MEXC → Binance → Bybit
  → Bitget → Gate → OKX (MEXC primero: mismos precios que opera el bot). Caché
  por proceso, timeout 8s, fail-open a MEXC sin red. Tokens 1000X se reintentan
  sin prefijo. Cobertura verificada con 16 símbolos reales (Binance 15/16, MEXC
  14/16, ningún exchange lo tiene todo → por eso la elección es por moneda).
- Verificado en navegador: MEXC:SYNUSDT.P carga el gráfico del perpetuo con
  precio vivo. Ejemplos del arreglo: SYN→MEXC, AIGENSYN→BINANCE,
  1000PEPE→BINANCE (1000PEPEUSDT.P existe allí), BTC→MEXC.

### Aplicado el artículo "TradingBotV2" (Miles Deutscher): memoria + reflexión + panel
- Gap-analysis contra lo ya montado: cerebro/paper/backtests/seguridad ya cubiertos
  (y con más rigor: pre-registro, meseta, IS/OOS, cuentas dobles). Se aplicaron las
  3 piezas que faltaban:
- **Nuevo `LECCIONES.md`**: archivo de lecciones aprendidas (el "learnings.md" del
  artículo), sembrado SOLO con lecciones reales ya respaldadas por datos (11, con
  fecha y evidencia; detalle en este changelog). Regla: nada inventado, y las
  mediciones selladas no se adaptan con lecciones hasta su veredicto.
- **Nuevo `estado.py`**: panel de estado en un comando (la versión austera del
  "dashboard"): corre los --status canónicos de las 4 mediciones + asistente.
- **Revisión dominical ampliada**: la tarea programada de los domingos pasa de
  vigilar solo el finde a las 4 mediciones + contraste PC/GitHub + mantenimiento
  de LECCIONES.md (reflexión semanal solo con evidencia real).
- NO aplicado, con motivo: TradingView MCP (redundante: los backtests de casa usan
  datos reales de exchange; el MCP comunitario requiere revisión de código y la app
  de escritorio), ejecución real con claves API (regla del usuario: nada de dinero
  real sin veredicto forward; llegado el día, subcuenta con clave solo-trading), y
  el "filtro adaptativo" sobre mediciones selladas (adaptarlas en marcha las
  contamina — lección 3).

## 2026-07-16

### VEREDICTO de la medición congelada: micro_pullback RETIRADO
- Muestra final: **n=384 trades** (PC 162 + GitHub 222, solo micro_pullback 15m/1h, medición
  limpia post-fixes). Expectancy **−0.405%/trade, IC95 [−0.62%, −0.19%]** — negativo con
  certeza estadística. Ambas cuentas y ambas TFs negativas (PC 15m −0.50 / 1h −0.89;
  GitHub 15m −0.20 / 1h −0.43). La "brasa" del 1h (56% win con n=16) NO sobrevivió a la
  muestra grande: espejismo de muestra pequeña, como advirtió el auditor.
- Criterio pre-registrado (2026-07-03) era > +0.3% con IC95 excluyendo cero → **NO CUMPLE →
  se retira según protocolo** (sin re-barrer parámetros, sin "aflojar para tener señales").
- Cambios: `config.enable_micro_pullback=False` (gate nuevo, como round_fade) y
  `paper.run_cycle` ya no lo escanea. El paper TFZ queda como **ASISTENTE puro** (solo
  alertas F2/F3/F4 a Telegram; 8 enviadas hasta hoy). Las posiciones abiertas restantes se
  cierran solas por SL/TP/stale con el update normal. Los otros experimentos (Ichimoku,
  weekend_paper, EMA…) van en BDs/procesos separados y no se tocan.
- Cuentas al cierre de la medición: PC $38.99, GitHub $39.33 (de $50). El experimento costó
  ~$22 simulados y compró la respuesta definitiva: este setup, tal como está, no tiene edge.

## 2026-07-15

### Paso 4 del PDF + tanda de 6 clásicas + nuevo paper forward Ichimoku
- **Paso 4 ("mejorar") del EMA 9/21, veredicto honesto: nada mejora lo que importa.**
  Anatomía de perdedoras (ganadoras duran ~51 días, perdedoras ~9 = amagos; años
  malos 2022 y 2025-26). 4 mejoras probadas en la misma tanda (SMA200, confirmación
  2 días, separación EMAs, combinada): en el último año (jul-25→hoy) TODAS siguen
  perdiendo (−12..−16%); en el total ganan menos que la base. La estrategia necesita
  tendencias largas, no tiene un fallo parcheable.
- **Tanda de 6 clásicas** (Binance 1d, 0.1%/lado, fill apertura siguiente,
  2020→hoy; B&H BTC +834% maxDD −77%): Supertrend semanal +890% (n=3, anécdota),
  cruce dorado 50/200 +326%, MACD +658%, Donchian 20/10 +758% — esas 3 pierden
  contra B&H. EMA 9/21 en ETH +1745% (vs B&H ETH +1387%). **Ichimoku (cierre sobre
  la nube 9/26/52 d26) +1218% con maxDD −35.9%** (la mitad que el resto). ÚLTIMO
  AÑO: pierden TODAS (confirma: sin tendencia no hay familia que gane).
- **Batería al Ichimoku: meseta OK** (7 configs vecinas +900..+1400%), IS +1393%
  / OOS (jul-25→hoy) −10.2% con 0/5 ganadoras. Año a año su edge es DEFENSIVO:
  2022 −22% vs −64% B&H, 2026 −1% vs −26%; en años alcistas gana MENOS que
  aguantar (2024 +48% vs +121%). Es un paracaídas, no un cohete.
- **Nuevo `ichimoku_paper.py`** (gemelo de ema_cross_paper.py): BD propia
  (`ichimoku_paper.db`, env `TFZ_ICHI_DB`), pre-registro 2026-07-15 forward-only,
  idempotente, regla congelada (largo si cierre > máx(senkouA,B) estándar 9/26/52
  d26; fill apertura siguiente; costes MEXC 0.09% i/v; funding no modelado).
  Verificado contra la batería (transiciones del último año coinciden). Estado al
  sellar: BAJO la nube (65015 < techo 70964) → plano; no cuenta.
- Despliegue doble: tarea Windows `TFZ_Ichimoku_Paper` diaria 03:07
  (`C:\Users\jarta\run_ichimoku_paper.cmd`, log `ichimoku_log.txt`) + paso nuevo en
  `bot.yml` (`TFZ_ICHI_DB=github_state/ichimoku_paper.db`). `.gitignore`: añadidos
  `ichimoku_paper.db` e `ichimoku_log.txt`.
- Validación TradingView del EMA 9/21 por el usuario (BTCUSD 1D, 2020→2026):
  fechas de trades ~1:1 con la réplica; +1097% vs +788% B&H, maxDD −53.6%. Ojo
  lectores de TV: micro-trades residuales del simulador (20 de 64) hunden el win
  rate aparente (28% vs ~41% real) y su PF es en dólares compuestos (no comparable
  al PF por % de trade).

---

## 2026-07-14

### Nuevo paper forward: cruce EMA 9/21 diario en BTC (ema_cross_paper.py)
- Origen: chuleta "The Backtest Machine" (Miles Deutscher). Réplica verificada con
  datos MEXC BTC/USDT 1d, jul-2023→hoy, comisión 0.1%/lado, fill apertura siguiente:
  23 trades, WR 34.8%, PF 3.11, +159.8% vs +104.1% buy&hold, maxDD −27.3% vs −53.0%.
  Meseta OK (8/20 +166%, 10/22 +193%, 12/26 +152%). PERO ojo al IS/OOS de la
  plantilla: último año (jul-25→hoy) **−16.4%, PF 0.28, 7 trades** — todo el edge
  vino de 2023-2024. Por eso se mide forward en vez de creérselo.
- **Nuevo `ema_cross_paper.py`**: BD propia (`ema_cross_paper.db`, env `TFZ_EMA_DB`),
  forward-only (pre-registro 2026-07-14; el cruce alcista del 07-10, ya abierto al
  sellar, NO cuenta), idempotente (reconstruye desde velas cerradas, INSERT OR
  IGNORE). Regla congelada: EMA9>EMA21 al cierre diario → largo; < → plano; solo
  largos; fill = apertura siguiente; costes MEXC 0.09% i/v; funding NO modelado
  (salvedad anotada). Verificado que sus cruces coinciden 1:1 con la réplica.
  Aviso Telegram de cruce nuevo solo donde TFZ_TELEGRAM=1 (patrón premium_paper).
- Despliegue doble como weekend/premium: tarea Windows `TFZ_EMA_Paper` (diaria
  03:05 local, `C:\Users\jarta\run_ema_paper.cmd`, log `ema_log.txt`) + paso nuevo
  en `.github/workflows/bot.yml` con `TFZ_EMA_DB=github_state/ema_cross_paper.db`.
- `.gitignore`: añadidos `ema_cross_paper.db` y `ema_log.txt` (la cuenta del PC no
  se sube; la de GitHub va con `-f` en `github_state/` como las demás).

### Arreglo bot.yml: los push de estado del run de GitHub fallaban en silencio
- Detectado en el run 170 (2026-07-14): 3h de bucle SIN subir ni un commit de
  estado. Causa: el cron fija el checkout al commit del momento de encolar, pero
  con la concurrency el run arranca más tarde y el run anterior ha subido estado
  entre medias → `git pull --rebase` choca en las BDs binarias de `github_state/`,
  el rebase queda atascado y todos los push del run fallan (los `|| true` lo
  tragaban). El estado medido en runs así se PERDÍA (afecta a weekend/premium
  de ese run; las mediciones son idempotentes y se reconstruyen, pero los ciclos
  de paper de ese run no se suben).
- Arreglo doble en `.github/workflows/bot.yml`: (1) paso nuevo tras el checkout
  que hace `git fetch` + `reset --hard origin/main` (arrancar siempre desde la
  punta real de la rama, el pin obsoleto deja de importar); (2) en el bucle de
  push, `git rebase --abort` antes de cada reintento para no quedar atascado.

### Arreglo git: tfz_data.db fuera del índice
- `git rm --cached tfz_data.db`: la BD viva del PC estaba trackeada pese al
  .gitignore y su bloqueo (el bot la tiene abierta) rompía cualquier
  pull/rebase ("unable to unlink"). El archivo sigue en disco intacto; solo
  deja de estar en git. La cuenta de GitHub usa `github_state/tfz_data.db`,
  que no se toca. Pull en este repo: mejor `--no-rebase` (merge, el patrón
  de los commits previos).

### Plantilla de backtest rápido (plantilla_backtest.py + PLANTILLA_BACKTEST.md)
- **Nuevo `plantilla_backtest.py`** (solo lectura): harness genérico para probar
  cualquier estrategia editando solo `position(df)` y `PARAM_GRID`. Fijo para
  todas las pruebas: datos vía `data_fetcher` (MEXC), señal en vela cerrada, fill
  apertura siguiente, costes 0.09% i/v, meseta automática, split IS/OOS (último
  año) y buy&hold como listón. Comparaciones limpias entre estrategias.
- **Nuevo `PLANTILLA_BACKTEST.md`**: los 4 prompts del PDF (articular → codificar →
  correr → leer) adaptados a los dos caminos (plantilla del bot o TradingView/Pine)
  + la batería de la casa (n≥20, meseta, IS/OOS, deriva, costes, forward).

---

## 2026-07-10

### RONDA 24b: variante intradía 2h de la #40 (explore_sr_volume_intraday.py) — nada validado
- **Nuevo `explore_sr_volume_intraday.py` (EXPLORACIÓN #41),** solo lectura. Restricción
  del usuario: operar solo ~2h/día y cerrar todo antes de acabar la ventana. Mismos
  niveles causales que la #40; ventana elegida por VOLUMEN (no por retornos): las 2h
  con más volumen mediano = 14-16 UTC (16-18 Madrid verano). Entradas al cierre de la
  vela 13h o 14h UTC, salida forzosa al cierre de 15h UTC. Filtro de volumen ajustado
  por hora del día (>2x media de la misma hora, 20d, desplazada). 42 símbolos,
  1h 2024-03→2026-07, costes MEXC, IS 24-25 / OOS 2026.
- **Resultado: NINGUNA de las 8 familias da positivo.** Todas con IC95 incluyendo 0
  o con n<30, salvo rebote long sin volumen que pierde CON significancia (−0.16%
  total, −0.23% IS). Los costes (0.09%/trade) superan el movimiento típico de una
  sesión de 2h (deriva incondicional ±0.02-0.05%). Con velas 1h la caché solo
  permite 1-2 entradas/día; la caché 15m solo guarda ~20 días (insuficiente).
- Tabla de volumen por hora impresa por el script (pico diario 14 UTC = 16 Madrid);
  la constante `WINDOW_START_UTC` permite re-probar otra ventana sin tocar nada más.

### RONDA 24: soportes/resistencias horizontales + volumen (explore_sr_volume.py) — nada validado
- **Nuevo `explore_sr_volume.py` (EXPLORACIÓN #40),** solo lectura. Estrategia pedida por
  el usuario: SOLO soportes, resistencias y volumen. Niveles causales (swings diarios
  k=3 confirmados con retardo, clúster 0.5%, mín 2 toques, ventana 90d), 8 familias
  (ruptura/rebote x long/short x con/sin filtro volumen >2x media 20d), hold 3d,
  costes MEXC, 40 símbolos, IS 24-25 / OOS 2026, con línea de deriva incondicional.
- **Resultado: ninguna celda pasa la batería de la casa.**
  - Ruptura SHORT sin volumen: la única celda OOS significativa (+2.44% n=163,
    IC95 excluye 0) pero en IS era −0.33% y la deriva 2026 es bajista (−0.67%/3d
    long) → nace del régimen 2026, no consistente. No se abre nada con esto.
  - Rebote LONG + volumen: +3.84% total IC95 excluye 0 pero n=37 (subperiodos
    "pocos") → sin masa estadística.
  - El filtro de volumen NO mejora de forma consistente: en rupturas recorta n
    (54 vs 307) y empeora el short (−8.1% IS); en rebotes long parece ayudar
    (+3.8% vs −0.8%) pero con n=37 no es concluyente.
  - Rebote LONG sin volumen: pierde con significancia en total (−0.81%) — comprar
    "porque tocó el soporte" fue negativo en este periodo.
- Regla del proyecto respetada: parámetros pre-especificados en el docstring antes
  de mirar resultados; no se ha re-optimizado nada después de verlos.

## 2026-07-06

### Supervisión semanal weekend_paper: 1er sábado registrado, tarea Windows no disparó
- **Anomalía detectada:** la tarea programada `TFZ_Weekend_Paper` (domingos 03:15) NO
  se había ejecutado ni una vez desde su creación (2026-07-03): `weekend_log.txt` ni
  existía, `LastRunTime` marcaba el centinela "nunca ejecutada". Causa: la sesión de
  usuario (`jarta`) no estaba iniciada el domingo 2026-07-05 a esa hora — la sesión
  actual arrancó el 2026-07-06 06:35, y la tarea usa LogonType=Interactive (necesita
  sesión activa). `StartWhenAvailable=True` no la recuperó igualmente.
  - **Arreglo aplicado (reversible):** se lanzó manualmente
    `python weekend_paper.py` en el PC (INSECURE_SSL=1) -> registró el sábado
    2026-07-04 pendiente (41/42 símbolos; TON sin señal real esa semana, ver abajo).
  - **Pendiente (necesita permisos de admin, denegado en esta sesión):** cambiar el
    `Principal` de la tarea a `LogonType S4U` para que corra sin sesión interactiva
    activa. Alternativa más simple: dejar la sesión de Windows iniciada los sábados
    por la noche.
- **Comparación PC vs GitHub (cuenta redundante, `github_state/weekend_paper.db`):**
  ambas cuentas coinciden en 40/41 símbolos del sábado 2026-07-04. Diferencias:
  - `TON`: ausente en LAS DOS cuentas — no es fallo, MEXC devolvió precio congelado
    (misma vela repetida, volumen 0) esa semana -> retorno del viernes exactamente 0
    -> excluido por diseño (`fri_ret == 0` se descarta en `weekend_paper.py:93`).
  - `FIL`: registrado en el PC (+4.27% viernes -> -1.33% pnl) pero AUSENTE en GitHub
    pese a docenas de re-ejecuciones del workflow desde entonces (dato real, no
    congelado). Parece un fallo de red puntual del runner de GitHub hacia MEXC
    específico de ese símbolo/momento. Impacto en el criterio: mínimo (1 símbolo de
    42, 1 semana de las >=20 necesarias) — se deja documentado, no se fuerza nada.
  - Workflow "TFZ Bot Paper" en GitHub: ACTIVO (runs in_progress/cancelled normales
    por el ciclo de ~5h40m, nada anómalo).
- **Estado del criterio (informativo, aún NO evaluable):** 1 de los >=20 sábados
  necesarios. Media pnl de los 41 trades de esta semana (no es aún la métrica del
  criterio, que promedia por semana): +0.02%. Regla y parámetros SIN TOCAR.

## 2026-07-06

### RONDA 23: Smart Money Concepts (FVG) — el evangelio pierde; enterrado
- **Librería smartmoneyconcepts (1.8k*) AUDITADA:** los swings (y BOS/CHoCH/OB/
  liquidity que dependen de ellos) usan velas futuras (before AND after) ->
  inutilizables sin re-ingeniería de retardos. El FVG marca t usando t+1 ->
  corregido con +1 día de retardo.
- **explore_smc.py — FVG con lectura clásica: PIERDE con significancia en IS y
  OOS** (alcista->long: -0.49%/-1.06%; bajista->short: -1.25% IS, +0.90% OOS =
  deriva corta 2026). La INVERSA del alcista (short tras FVG alcista) brillaba,
  pero el control de deriva sin solapar la tumba: exceso -0.34% en 2024 (pierde),
  +1.63% en 2025, +0.56% en 2026 -> inconsistente + nacida de invertir una
  hipótesis fallida = minería. Enterrada. Nota estratégica del día: MEXC no tiene
  API oficial de órdenes en futuros -> la ejecución del día de graduación será
  otro venue o manual (1 orden/semana para el vie->sáb).

### RONDA 22: cosecha GitHub del usuario — vectorbt IN, patrones chartistas OUT
- **vectorbt 1.1.0 instalado y verificado** (release de hace 2 días; numba con ruedas
  para Python 3.14) -> acelerador para futuras baterías de exploración.
- **TradingPatternScanner (pip tradingpattern 0.0.5):** roto con pandas 4 (texto sobre
  float64) y con LOOK-AHEAD de serie (shift(-1): la marca del día t usa t+1).
  Replicados sus 3 detectores parcheados en explore_patterns.py con la señal
  retrasada +1 día (corrección honesta).
- **explore_patterns.py — los 6 patrones clásicos, enterrados:** dobles techos/suelos
  nulos; H&S incoherente; H&S invertido PIERDE (otra vez el manual al revés en
  cripto); cuñas incoherentes... salvo "Wedge Up->short" que brillaba (IS y OOS
  signif.) — **analyze_wedge.py lo desmonta**: sin solapar y contra deriva corta,
  exceso +0.96/+0.38/+0.09% por año (2026 ≈ CERO: era la caída del mercado) y
  trimestres de +8.5% a -2.6% según régimen -> proxy de beta bajista, no edge.
- Diagnóstico Telegram del día: el silencio desde el sáb 04:17 era el commit
  98de744 del usuario (silenciar aperturas/cierres del paper) + ausencia de setups
  F1-F4 nuevos; canal verificado vivo con 2 mensajes de prueba desde el PC.

## 2026-07-04

### RONDA 21: macro (SPX/DXY) nulo-refutado + kimchi aparcado
- **explore_macro.py:** H1 S&P risk-on semanal -> BTC: NULO. H2 "DXY sube -> cripto
  baja" (folclore): REFUTADO — pierde -1.04%/sem significativo tal como se predica.
  H3 kimchi premium (Upbit/KRW, FX de Yahoo): IS +3.63%/sem (IC95 excluye 0, 69%
  win) pero Upbit solo da 616 días con huecos y OOS n=9 -> APARCADO (como Trends);
  reintentar con historia más profunda de Upbit si algún día hace falta.
- Nota técnica: yfinance necesita sesión curl_cffi con verify=False en este PC.

### RONDA 20: aviso Telegram de episodios de prima + amplitud y volumen nulos
- **premium_paper.py + bot.yml:** al abrirse un episodio de prima (BTC o ETH) se envía
  aviso informativo a Telegram (fail-silent, solo GitHub con TFZ_TELEGRAM=1, mismo
  patrón que las alertas F1-F4). "No es orden de operar" en el propio mensaje.
- **explore_breadth.py:** (1) amplitud alt-season (% de alts ganando a BTC 30d,
  régimen >60/<40 -> spread alts-BTC semanal): NULO en todo periodo. (2) volumen
  creciente (ranking 7d/30d, L-S semanal): NULO. Familias 38 y 39 enterradas.

### RONDA 19: cola larga de MEXC (3ª réplica del vie->sáb) + efecto estreno (lotería)
- **explore_friday_universe.py:** vie->sáb en 120 perps de MEXC NUNCA usados (9.202
  trades): +0.297% [+0.151,+0.443] excluye 0; 2024 +0.73*, 2025 +0.27*, 2026 plano
  (cola larga floja este año + spreads peores) -> tercera réplica independiente;
  el universo sellado NO se toca. Efecto estreno (81 listados desde 2024-07):
  +11.8% medio días 2-7 pero IC [-1,+25] y win 46% -> lotería de colas, no operable.

### RONDA 18: FOMC — la última familia pública, y el patrón se cumple hasta el final
- **explore_fomc.py (44 reuniones 2021-2026, fechas verificadas en federalreserve.gov):**
  BTC: nulo en todas las ventanas. Cesta de alts, deriva pre-FOMC (día antes + día
  del anuncio): IS 2021-24 +2.92% por evento (IC95 excluye 0) -> OOS 2025-26 -0.40%
  (n=12, ruido). Muerta post-institucionalización, como F&G/expiry/TOM/52s/shocks.
- Con esto: ~41 estrategias/familias examinadas. El catálogo público de datos
  accesibles (velas 8 años, derivados, flujos, sentimiento, on-chain, calendario,
  factores, eventos macro) queda barrido COMPLETO. Sobreviven: vie->sáb + filtro,
  prima BTC/ETH (candidatas), micro_pullback (en examen). Nuevas fronteras = datos
  nuevos: microestructura propia (en fabricación) y los veredictos forward.

### RONDA 17: factores académicos (MAX, low-vol, Amihud) — muertos, con lección
- **explore_factors.py (semanal XS, Binance 2018-26, 42 símbolos):** MAX/lotería
  (short alto): PIERDE -0.76%/sem signif. en IS -> el factor está INVERTIDO en
  cripto. Low-vol/BAB: pierde en IS, plano OOS -> cripto PAGA la volatilidad.
  Amihud (long ilíquido): IS +0.78* -> OOS -0.13 ruido -> muerto post-2024.
- **Lección meta:** los premios de riesgo cripto van al revés que en bolsa (la
  volatilidad extrema se paga). Ya lo capturamos de forma validada con el filtro
  |vie|>=3%; invertir el MAX post-hoc sería minería de un test fallido -> no.

### RONDA 16: seis familias clásicas más, probadas y enterradas
- **explore_breakouts.py (42 símbolos, 1h, 2024-26):** vol-breakout ATR (Larry
  Williams): PIERDE en OOS (-0.19% signif.). NR7: OOS +0.23* pero IS en ruido ->
  no pasa el listón (significancia solo-OOS sin IS = espejo del espejismo). Pico de
  volumen 3x: nulo.
- **explore_52whigh.py (Binance diario 2018-26, George-Hwang):** long cerca del
  máx-52s: IS +2.29%/sem signif. -> OOS 24-26 +0.29 ruido. Muerta post-ETF, mismo
  patrón que F&G/expiry/TOM/shocks.
- **explore_streaks_shocks.py:** rachas (seguir 3/4/5d): negativo e incoherente
  entre k (su inversa también incoherente -> ruido). Shocks ±7% (seguir 1-2d):
  IS positivo signif., OOS girado -> muerto. Reversión ETH/BTC (z90, 2 patas):
  -2.4%/trade -> muerta.
- **NOTA pairs:** ya estaban probados (explore_pairs 15m: -0.33%/trade en 32k
  trades); ni con costes MEXC saldría de negativo. No se repite.
- Con esto: ~37 estrategias/familias examinadas desde el 2026-07-03. Sobreviven
  las mismas: vie->sáb (+filtro), prima BTC/ETH, micro_pullback en examen.

### RONDA 15: ENSAYO GENERAL de la maquinaria forward (QA pre-primer-sábado)
- **weekend_paper probado END-TO-END contra el sábado real 27-jun** (BD desechable,
  START retrasado solo en el ensayo): registró 39/42 símbolos; BTC y DOGE contrastados
  a mano contra los cierres -> EXACTOS. Los 3 que faltan (CRV/OP/TON) son viernes con
  cierre idéntico al jueves (tick grueso -> retorno 0 -> sin dirección -> no hay trade),
  misma regla que el backtest -> sin sesgo, por diseño. La BD real no se tocó.
- **GitHub verificado por API:** run viejo acaba ~22:00 UTC; el siguiente de la cola ya
  lleva los medidores y para el domingo el run activo tendrá el código completo (las
  BDs weekend/premium/micro aparecerán en github_state cuando corran sus pasos).
- Con esto, el primer dato del domingo queda asegurado por cuatro vías: tarea PC
  (03:15 + catch-up), GitHub (código en camino), ensayo E2E exacto, y mi revisión
  programada de las 09:30 que detectaría cualquier fallo.

### RONDA 14: las OTRAS palancas — ejecución (+0.045% real), sizing (nulo), Monte Carlo
- **explore_execution.py (velas 5m MEXC, 233 trades de 2026):** la orden LIMIT al
  cierre del viernes TOCA el precio el 100% de las veces en la 1ª hora del sábado ->
  sin selección adversa en esta construcción; ahorro +0.045%/trade solo en la entrada
  (~+9% relativo; el doble si la salida también es maker). Aplicable el día que se
  opere en real; el paper sigue con taker (conservador). Aproximación toque=llenado.
- **explore_sizing_mc.py:** (1) sizing por riesgo igual (1/vol30) es PEOR que pesos
  iguales (ratio 1.33 vs 1.45): el edge vive en las monedas volátiles -> pesos
  iguales se quedan. (2) Monte Carlo de la cartera combinada (bloques de 4 semanas,
  3 años, 10k caminos): 1x mediana x3.54 [p5 x1.76, p95 x8.07], P(DD>30%)=0.3%;
  2x mediana x10.8 pero P(DD>30%)=15.8%. Foto de riesgo remuestreando 2024-26
  (in-sample parcial); si el régimen cambia, no aplica.

### RONDA 13: compuesta nula, horizonte confirmado, y el PLANO DE CARTERA
- **explore_premium_composite.py:** (1) exigir confirmación de Bitstamp NO añade nada
  (idéntico +2.46%: ambos venues son la misma señal) -> se queda solo Coinbase.
  (2) Barrido de horizonte: el edge se concentra en los 3 primeros días (+0.42%/día);
  los días 8-14 no aportan -> el hold de 7d sellado captura casi todo. Descriptivo.
- **explore_portfolio.py — simulación 2024-2026 de las 3 mangas selladas (1/3 capital
  cada una, semanas sin señal = capital parado):** vie->sáb ~+24%/año (ratio 1.45),
  prima BTC ~+41% (1.36), prima ETH ~+77% (1.67); **COMBINADA ~+47%/año con MENOS
  drawdown que cualquier pata (-13.6% vs -18..-23%) y ratio 1.93** — la diversificación
  funciona (fri↔primas corr ~0; BTC↔ETH primas 0.71, cuentan casi como una).
  ADVERTENCIAS: periodo parcialmente in-sample para las primas (descubiertas en estos
  datos), sin componer, y NADA de esto es promesa: mandan las mediciones forward.

### RONDA 12: bootstrap por clústeres (recalibración honesta) + USDT peg y SOL nulos
- **explore_friday_bootstrap.py (10.000 remuestreos de SÁBADOS enteros — la estadística
  correcta contra la correlación entre símbolos):** la regla base agrupada SOBREVIVE:
  +0.508% IC95-cluster [+0.100,+0.958]; el filtro >=3% también: +0.901% [+0.204,+1.666].
  **PERO los años sueltos ya NO son significativos por separado** (26-52 sábados/año):
  el "significativo cada año" de rondas anteriores usaba IC inflados por trade. La
  magnitud anual es clavada (+0.50/+0.51/+0.52). El criterio pre-registrado del
  weekend_paper ya usaba medias semanales -> el diseño forward era correcto.
- **explore_usdt_peg.py (USDT/USD Bitfinex 2018-2026, 2.776 días):** prima/descuento
  del peg -> NULO con historia profunda (el +1.58% "sugerente" con los 721 días de
  Kraken era ruido de muestra pequeña). Enterrado.
- **Prima de SOL (scratchpad, CB SOL/USD desde 2021):** +1.85%/7d total pero IC95
  incluye 0 siempre y el OOS no supera la deriva -> NO validada. La familia de la
  prima queda en BTC + ETH.

### RONDA 11: prima de ETH (2ª regla sellada) + streams independientes + Trends escaso
- **explore_premium_family.py:** (1) la PRIMA DE ETH propia es aún más fuerte que la
  de BTC: +3.24% IS / **+3.62% OOS 2024-26 (IC95 excluye 0 ambos)**, n=178, exceso
  +2.4% sobre deriva; por años 8/9 positivos (2022 y 2025 flojos, patrón familiar).
  (2) señal de prima BTC -> cesta de alts: +1.44% de exceso pero ns -> no concluyente.
  (3) **corr(vie->sáb, prima) = +0.08 -> streams prácticamente independientes**:
  diversificación real de cartera cuando ambos midan positivo.
- **premium_paper.py AMPLIADO a 2 reglas selladas** (antes de dato alguno): BTC
  (listón +1.0%/7d) y ETH (listón +1.5%/7d), tabla con columna symbol, cada una a
  30 episodios. BD local vacía recreada (0 filas, esquema viejo).
- **explore_trends.py (Google Trends 'bitcoin', 5 años semanales):** H1 atención
  z>=1 -> semana siguiente: IS +10.4% (n=8, 88% win, excluye 0) pero OOS n=5 y
  total n=13 -> DEMASIADO ESCASO para afirmar nada. Aparcado, no enterrado.

### RONDA 10: PRIMA DE COINBASE (candidato serio, en medición) + on-chain nulo
- **explore_premium.py (prima BTC Coinbase-USD vs Binance-USDT, 2018-2026, episodios
  no solapados z90d solo-pasado):** H1 prima alta (z>=+1) -> long 7d: **+2.67%/7d IS
  y +1.97% OOS 2024-26, ambos IC95 excluyendo 0** (n=176, win 65%). H2 (descuento ->
  short): no validada. **analyze_premium.py (controles del caso funding):** sobrevive
  la deriva (exceso +1.67% sobre +0.79% base), dosis-respuesta razonable, transfiere
  a ETH (+3.0% exceso). **ARRUGA honesta: 2025 fue negativo (-0.45%, ns)** -> 8/9 años
  positivos pero el último completo flojea; NO alcanza el listón 6/6 del vie-sáb.
  Veredicto: candidato a medición forward, no edge validado.
- **NUEVO premium_paper.py (forward, sellado 2026-07-03):** pata MEXC en vez de
  Binance (geo-bloqueo en GitHub; correlación de primas 0.992, diff media 0.005pp),
  última vela diaria descartada (puede estar en formación). Criterio: a >=30
  episodios, media > +1.0%/7d con IC95 excluyendo 0; si no, se retira (~1.5 años al
  ritmo histórico). En bot.yml (github_state/premium_paper.db, gitignored local).
- **explore_onchain.py (blockchain.com 2017-2026, direcciones activas y tx/día):**
  NULO con el mismo esqueleto (aceleración no predice; frenazo->short funcionó IS
  pero muere OOS). Enterrado.

### RONDA 9: el test del mecanismo FALLA — retractación de la narrativa institucional
- **explore_holidays.py (momentum en festivos NYSE, 24 festivos 2024-26, 42 símbolos):**
  la hipótesis "sin instituciones -> continuación como el sábado" predecía positivo;
  salió NEGATIVO (-0.47% significativo; festivos-lunes -0.93%, solapa con el patrón
  dom->lun ya conocido; festivos puros entre semana -0.20% ruido con n pequeño).
- **RETRACTACIÓN:** la historia de la ronda 8 ("el edge vive donde no hay
  instituciones") NO se sostiene como mecanismo general. El vie->sáb queda sostenido
  por sus réplicas empíricas (5 años, 3 universos, dosis-respuesta), con mecanismo
  DESCONOCIDO -> más razón para vigilarlo con el criterio pre-registrado, no menos.
  No perseguir la inversa en festivos: sería minar un test fallido (y el dom(-) ya
  murió en la ronda 5).

### RONDA 8: el folclore famoso está MUERTO en OOS (F&G, expiry, turn-of-month)
- **explore_feargreed.py (índice Fear&Greed 2018-2026, episodios no solapados, hold 7d):**
  "comprar el miedo extremo" funcionó 2018-23 (BTC +2.26%/7d, IC95 excluye 0) y desde
  2024 está INVERTIDO (BTC -2.65%, ETH -4.66% significativo). "Vender la codicia": nulo
  siempre. **explore_month_calendar.py:** rally post-vencimiento (ETH +0.82%/día IS,
  significativo) y turn-of-month (BTC/ETH significativos IS) -> ambos DESAPARECIDOS o
  negativos en 2024-26. Las tres anomalías murieron A LA VEZ (~ETFs enero 2024:
  arbitraje institucional entre semana). Coherente con que el vie->sáb (nacido 2022)
  viva justo donde las instituciones no operan: el fin de semana.
- Lección operativa: anomalías públicas de días laborables = presumir muertas post-2024
  salvo prueba OOS reciente; el hueco está en horario sin instituciones.

### RONDA 7: profundidad histórica 2018-2026 — el vie->sáb es un RÉGIMEN nacido en 2022
- **explore_friday_history.py (Binance SPOT diario desde el PC, 42 símbolos, hasta
  8.5 años):** 2018-2021 el efecto NO existía (2020: -0.60% SIGNIFICATIVAMENTE
  NEGATIVO — los sábados revertían). **2022/23/24/25/26: positivo con IC95
  excluyendo 0 los CINCO años** (+0.40/+0.21/+0.64/+0.49/+0.55). Con filtro >=3%:
  mismo patrón, 2024 hasta +1.56%. Conclusión: anomalía DE RÉGIMEN, 5 años estable,
  no eterna -> puede morir como nació; el criterio pre-registrado del weekend_paper
  es el kill-switch. Nota: Binance spot accesible desde el PC (el geo-bloqueo era
  solo de los runners de GitHub).
- Verificado en la API de GitHub: run 36 in_progress con código de la ronda 2; los
  siguientes de la cadena ya cogen el código con weekend_paper y micro_collector
  (margen de sobra para el primer sábado).

### RONDA 6: anatomía del vie->sáb + FILTRO DE MAGNITUD validado 6/6 + DVOL nulo
- **explore_friday_anatomy.py (descriptivo, la regla sellada NO cambia):**
  (1) la continuación se acumula durante TODO el sábado (máximo en la hora 24 ->
  el hold de 24h ya es correcto); (2) DOSIS-RESPUESTA limpia por |ret. viernes|:
  Q1 (<0.9%) +0.02% ... Q5 (>5.8%) +1.16%/trade; (3) riesgo de la cartera semanal
  (42 símbolos, 118 sábados): media +0.50%/sem, 47% semanas negativas, peor -4.6%,
  racha máx 4 perdedoras, drawdown máx -18.6%, acumulado 3 años +59.5%.
- **explore_friday_filter.py — filtro |viernes| >= 3% (umbral FIJO pre-especificado)
  pasa 6/6 celdas** (3 años × 2 universos, todas con IC95 excluyendo 0): +0.49..+1.46%
  por trade con ~40-50% de cobertura. **Pre-registrado como CRITERIO SECUNDARIO en
  weekend_paper** (mismos datos, fri_ret ya se guarda por trade; evaluación del
  subconjunto |vie|>=3% con listón > +0.25%). Sellado junto al primario; --status
  ya muestra los dos.
- **explore_dvol.py — DVOL de Deribit (901 días, endpoint crudo; ccxt ignora los
  parámetros y solo da 16 días):** H1 (vol alta predice retorno siguiente) NULA.
  H2 (efecto viernes más fuerte con vol alta) RECHAZADA: funciona en ambos regímenes
  (+0.43% alta / +0.66% baja, ambos significativos) -> el efecto NO depende del
  régimen de volatilidad global. Robustez adicional.

### RONDA 5: matriz calendario completa — SOLO el viernes pasa el listón
- **explore_calendar_oou.py:** los 7 días × 3 años × 2 universos (los 20 de siempre +
  22 nuevos con majors), con 4 candidatos pre-especificados. Resultado:
  **vie(+): 6/6 celdas positivas y significativas — ÚNICO superviviente.**
  mie(+) muere (2024 nuevo universo negativo); dom(-) muere (2025 se gira);
  lun(-) muere (2024 nuevo universo +0.90% momentum, lo contrario).
- Consecuencia: weekend_paper se queda SOLO con el viernes (42 símbolos) y el
  pre-registro queda SELLADO. Los demás días quedan enterrados con evidencia.

### EL PC YA NO ES NECESARIO: recolector también en GitHub
- A petición (el PC no puede estar siempre encendido): micro_collector acepta
  `TFZ_MICRO_DB` y bot.yml lo ejecuta cada 3 ciclos (~15 min) con cuenta propia
  (github_state/micro_data.db). Estado de dependencias del PC: bot paper = dual
  (GitHub solo se basta), weekend_paper = dual (GitHub solo se basta), recolector =
  dual desde ahora. El PC, cuando esté encendido, SUMA cobertura; si está apagado,
  no se pierde nada esencial. Verificado en la API de GitHub que los runs "cancelled"
  son el reemplazo normal de la cola (concurrency) y hay run activo.

### RONDA 4: vie->sáb REPLICA FUERA DE UNIVERSO (el hallazgo del día) + OI nulo + recolector
- **explore_weekend_oou.py — REPLICACIÓN INDEPENDIENTE del momentum vie->sáb:** la misma
  regla, sin tocar nada, en monedas JAMÁS usadas por nosotros: 18 alts nuevas (DOGE, LTC,
  BCH, ETC, FIL, APT, ARB, WLD, TON, TRX, PEPE, HBAR, ALGO, VET, ICP, GALA, SAND, KAVA):
  **+0.493%/trade con IC95 excluyendo 0 EN CADA AÑO (2024/25/26: +0.50/+0.48/+0.52),
  16/18 positivas**. Majors (BTC/ETH/BNB/XRP): +0.285%, IC95 excluye 0 en total, 4/4
  positivos. Conclusión: es propiedad del mercado cripto, no del universo elegido.
- **weekend_paper AMPLIADO a 42 símbolos** (los 20 + las 18 replicadas + 4 majors),
  hecho ANTES del primer sábado medido, como permitía explícitamente el pre-registro
  (a partir de ahora ya NO se toca). Más datos por sábado -> veredicto antes.
- **explore_oi.py — open interest (Bybit, ~800 días) NULO:** los 4 cuadrantes clásicos
  precio×OI (dinero nuevo/cierres) no predicen el día siguiente (signos incoherentes
  IS/OOS, todo dentro del ruido). El ratio long/short en extremos (contrarian): tilt
  positivo pero IC95 incluye 0 siempre y el crowd_short se gira en OOS. Enterrado.
- **NUEVO micro_collector.py + tarea TFZ_Micro_Collector (PC, cada 15 min):** MEXC no da
  histórico de libro/OI -> se recolecta desde YA (mid, medio-spread, imbalance top-5,
  funding) en micro_data.db (gitignored) para investigar dentro de unas semanas.
  Fix al vuelo: el libro de MEXC trae 3 campos por nivel, no 2.

### RONDA 3: medición weekend blindada + slippage verificado + 2 nulos más (trend, BTC-lead)
- **weekend_paper blindado:** (1) tarea del PC con StartWhenAvailable=True (si el PC está
  apagado el domingo 03:15, corre al encender); (2) paso nuevo en bot.yml -> GitHub lleva
  una cuenta REDUNDANTE (github_state/weekend_paper.db, TFZ_WKND_DB), 1 vez por run;
  idempotente y forward-only, así que PC y GitHub deben registrar trades IDÉNTICOS
  (cross-check gratis). (3) Quitado el os.environ.setdefault de INSECURE_SSL del script:
  en GitHub el SSL va verificado; en el PC lo pone run_weekend_paper.cmd.
- **Slippage VERIFICADO contra el libro de órdenes de MEXC (foto 2026-07-03):** medio-
  spread del universo: mediana 0.014%/lado, media 0.021%, peor OP 0.095%. El supuesto
  del bot (slippage_pct=0.025) es realista/ligeramente conservador -> NO se toca.
- **explore_trend.py (Donchian D20/10 y D55/20, LS y long-only, diario):** NULO en las
  cuatro variantes (LS pierde; long-only +5-8% anualizado en IS se gira a -11/-33% en
  OOS 2026). El trend-following clásico no da en este universo/periodo.
- **explore_btclead.py (¿BTC manda sobre las alts al día siguiente?):** NULO (IS -27%
  anualizado, OOS +69%, ambos con IC95 incluyendo 0 -> ruido con cambio de signo).
  Control (momentum propio de las alts): positivo leve pero no significativo, coherente
  con que la única rebanada válida del momentum diario es la del vie->sáb.

### RONDA 2: dos nulos limpios (xsmom, hora-del-día) + tarea programada del weekend paper
- **explore_xsmom.py (momentum cross-sectional semanal, top-3/bottom-3 de 20):** L-S
  positivo en IS (2024-25) y OOS (2026) pero MUY lejos de significativo (n=117 semanas,
  IC95 [-0.7,+1.0]); long-only NEGATIVO en OOS (-1.6%/sem). Veredicto: nada operable.
- **explore_hourday.py (estacionalidad por hora UTC y sesiones de 8h):** ninguna hora
  supera el listón de costes (0.09%) con consistencia IS->OOS. Caso ejemplar: hora 22
  UTC era la única significativa en IS (+0.10%) y SE GIRA en OOS (-0.03%) -> espejismo
  de multiple-testing cazado por la disciplina descubrir/validar. Sesiones: nada.
- **Tarea programada TFZ_Weekend_Paper (PC):** domingos 03:15 hora local ejecuta
  C:\Users\jarta\run_weekend_paper.cmd -> weekend_paper.py (log en weekend_log.txt).
  Primer disparo: 2026-07-05 (primer sábado pre-registrado: 2026-07-04).
- **NOTA (verificado, sin tocar):** run_paper.cmd del repo es un lanzador VIEJO
  (5m,15m) que ya NO usa la tarea real del PC (\TFZ_Paper -> run_tfz_paper_hidden.vbs
  -> C:\Users\jarta\run_tfz_paper.cmd con 15m,1h correctos). La BD confirma solo
  trades 15m/1h de micro_pullback. Ojo con relanzarlo por error.
- **NOTA reversión a la media:** ya explorada antes (meanrev -0.207%/trade, residual
  BTC-neutral -0.192%); ni con costes MEXC (~+0.11 de mejora) saldría de negativo.

### INVESTIGACIÓN NOCTURNA: funding contrarian INVALIDADO; momentum vie->sáb SOBREVIVE
- **Funding contrarian (batería en explore_funding_deep.py + analyze_funding_deep.py):**
  con el fix de timestamps, el test que siempre decía "sin señales" por fin corrió de
  verdad (~9.000 señales, 400 días de funding Bybit, costes MEXC). Prometía: exp +0.33%
  con IC95 excluyendo 0 TAMBIÉN en OOS, 17/18 símbolos, sobrevivía sin crédito de funding
  y sin solapar. **PERO era artefacto:** el 88% de señales eran shorts y el 67% ni eran
  extremos (funding clavado en el baseline +0.01% -> el percentil 95 degenera en "short
  siempre"); el "edge" (+0.33%) ≈ la caída media del mercado en esas ventanas (-0.42%).
  Los extremos DE VERDAD (|funding|>=0.03%/8h, n=445): negativos o ruido en TODOS los
  trimestres, 7/18 símbolos. El OOS "pasaba" porque la deriva bajista siguió en ese tramo
  (el OOS no protege de un factor de confusión). **Retirado ANTES de medirlo en vivo**:
  funding_paper.py se creó y se BORRÓ (su primer ciclo abrió 14 shorts, todos baseline —
  eso destapó el sesgo). Tercer artefacto cazado por el método (look-ahead, timestamps,
  deriva). Lección para futuros umbrales por percentil: comprobar la masa en el baseline.
- **Efecto día-de-semana (explore_weekend.py, universo propio, 18 símbolos, ~2.9 años):**
  momentum diario (señal = retorno del día D, mantener el día D+1, neto costes MEXC).
  OJO etiquetas: "viernes" = señal del viernes OPERADA EL SÁBADO. El agregado L-V vs S-D
  NO es estable por años (2025 lo contradice) -> descartado. **Lo que sobrevive: señal del
  VIERNES mantenida el SÁBADO**: +0.55/+0.60/+0.56% por año (2024/25/26), IC95 excluyendo
  0 los 3 años; longs +0.87% y shorts +0.27% (ambos >0 -> no es sesgo de deriva); 17/18
  símbolos; sin los top-5 sábados queda +0.18% [+0.02,+0.34] (cola gorda: pocos días
  grandes ponen la carne); mediana +0.14%. Cautelas: salió de comparar 7 días (multiple
  testing) y los 18 símbolos comparten sábado (correlación -> IC real más ancho).
- **NUEVO weekend_paper.py (medición forward pre-registrada, BD propia weekend_paper.db,
  gitignored):** regla exacta = sábado 00:00 UTC entrar en la dirección del retorno del
  viernes, salir domingo 00:00 UTC, universo de 20, costes MEXC. FORWARD-ONLY (solo
  sábados >= 2026-07-03; rellenar el pasado sería otro backtest). CRITERIO PRE-REGISTRADO
  (propuesta ajustable antes del primer sábado): a >=20 sábados, media de las medias
  SEMANALES > +0.15% con IC95 excluyendo 0; si no, se retira. Semántica de etiquetas
  verificada con test sintético. Correr tras el domingo 01:00 UTC (p.ej. domingo/lunes).
  NO toca la medición congelada de micro_pullback (proceso y BD separados).

### COSTES corregidos a MEXC real (contabilidad, NO estrategia) + doble contabilidad
- **Hallazgo (verificado contra la API de MEXC con ccxt, no contra marketing):** el bot se
  cobraba comisiones de otro exchange. `config.commission_pct` era 0.075%/lado (comentario
  original: "bybit/binance") pero MEXC USDT-M cobra **taker 0.02%** (BTC/ETH; varios pares
  0%/0% por promo, no se cuenta con ella) y **maker 0%**. Además `funding_pct_per_8h=0`:
  no se cobraba funding pese a operar perps (BTC verificado: 0.01%/8h).
- **Cambio en config.py:** `commission_pct 0.075 -> 0.02`, `funding_pct_per_8h 0 -> 0.01`
  (baseline estándar, conservador para longs), `slippage_pct 0.025` sin tocar (estimación).
  Ida y vuelta: antes 0.2%, ahora ~0.09% + funding por horas. **Es corrección de
  CONTABILIDAD al venue real, no aflojar parámetros**: el umbral pre-registrado (+0.3%/trade)
  no se toca. Se hace HOY porque las cuentas se resetearon hoy mismo (10 trades PC / 1 GitHub
  cerrados con el modelo viejo; ver recalc_costs.py para unificar al evaluar).
- **NUEVO recalc_costs.py (solo lectura):** reconstruye el PnL BRUTO desde los precios
  guardados y reporta expectancy bajo AMBOS modelos (antiguo y MEXC), con control de
  coincidencia contra el pnl_pct guardado. Verificado: 10/10 trades del PC coinciden
  exactamente con el modelo antiguo -> la reconstrucción es fiel. Uso: `python
  recalc_costs.py` (PC) o con `TFZ_DB=<ruta>` (GitHub). El día de los ~200 trades, evaluar
  el criterio con el modelo MEXC sobre TODOS los trades (unifica los cerrados pre-cambio).
- **explore_funding.py migrado a MEXC + BUG de timestamps arreglado:** funding del venue
  real (antes Bybit) vía `create_exchange` de data_fetcher (SSL centralizado); el contrarian
  (#2) reporta el neto con los DOS costes en la misma tanda (mismas señales, solo cambia el
  coste). `FUND_EX=bybit` reproduce lo viejo. **BUG:** la columna timestamp llega como
  datetime64[ms] y el `astype("int64")//10**6` la dejaba 1000x pequeña -> searchsorted nunca
  casaba -> el test #2 decía "sin señales" SIEMPRE. O sea: el "sin señales" del log viejo de
  Bybit era el bug, no el mercado (el #3 carry no estaba afectado). Grep: el patrón solo
  existía en este script, el núcleo del bot está limpio. Resultados nuevos: funding_mexc.log.
  Limitación conocida: MEXC solo devuelve ~200 eventos de funding (~66 días) por símbolo.

### Alertas F1-F4 (asistente) con contexto de indicadores — idea de CryptoSignal (GitHub)
- **Qué:** la alerta de Telegram del MODO ASISTENTE ahora incluye una línea de contexto
  objetivo: `RSI14 | RVOL (vol última vela cerrada / media 20) | lado y distancia a EMA200`.
  Patrón tomado de github.com/CryptoSignal/Crypto-Signal (5.6k★): alertar con varios
  indicadores y que decida el humano. Investigación previa verificó que NINGÚN repo público
  (Freqtrade 25k★, CryptoSignal, intelligent-trading-bot) demuestra rentabilidad real.
- **Dónde:** `paper._alert_context(df)` (nueva), `paper._alert_once(..., df)` (pasa el df),
  `notify.alert_entry(sig, prob, context=None)` (param opcional, retrocompatible: los otros
  2 call-sites siguen igual).
- **Garantías:** solo velas CERRADAS (`df.iloc[:-1]`, la última puede estar en formación);
  RSI con la misma fórmula que `explore_meanrev.rsi`; es SOLO informativo — no filtra ni
  altera señales, ni toca micro_pullback ni ningún parámetro congelado (permitido: es capa
  asistente/infraestructura). Test sintético OK incl. verificación anti-look-ahead
  (modificar la vela en formación no cambia el contexto). Fail-safe: ante cualquier error
  devuelve "" y la alerta sale como antes.
- **OJO:** las alertas solo salen desde GitHub (`TFZ_TELEGRAM=1`); para que se note hay que
  commitear y subir este cambio al repo.

### PIVOTE tras auditoría externa: MODO ASISTENTE + medición congelada de micro_pullback
- **Contexto:** auditoría externa (dossier) señaló look-ahead como causa probable de la brecha
  backtest(+2.7%/trade) vs vivo(negativo). VERIFICADO en código: (1) los niveles de una señal en
  la vela T usaban swings de hasta 150 velas DESPUÉS de T (ventana completa); (2) las formaciones
  se validaban con el precio del FINAL de la ventana; (3) la tendencia también se medía al final.
  TEST FORENSE A/B (explore_forensic.py, misma tanda, FREEZE_CACHE): modo A (con look-ahead)
  ~plano; modo B (solo pasado, como el vivo) NEGATIVO en 1h/15m/5m. Tres evidencias convergen
  (vivo 63 trades negativo + mecanismo en código + A/B) -> VEREDICTO FIRME: el edge del backtest
  de F1-F4 era artefacto; el sistema TFZ automático no tiene edge real tal como está.
- **Decisión (opciones 1+2 del auditor):**
  (1) **MODO ASISTENTE:** `config.trade_formations=False` -> las señales F1-F4 ya NO abren
  trades; envían ALERTA a Telegram (una sola vez por setup, tabla `sent_alerts` con dedup) y
  decide el humano. Alertas SOLO desde GitHub (`TFZ_TELEGRAM=1` en bot.yml; el PC queda mudo,
  `notify.ALERTS_PAUSED=True` sigue) para no duplicar avisos.
  (2) **MEDICIÓN CONGELADA de micro_pullback:** único setup que sigue operando en paper, SOLO
  15m/1h (5m eliminado: 16% win en vivo). `--timeframe 15m,1h` en bot.yml y en el .cmd del PC.
  Cuentas reseteadas a cero (PC y GitHub).
- **CRITERIO DE ÉXITO PRE-REGISTRADO (no se toca hasta ~200 trades cerrados):** micro_pullback
  15m/1h se considera CON edge si expectancy neta > +0.3%/trade con IC95% excluyendo cero; si
  no, se retira. Durante la medición NO se cambia ningún parámetro de la estrategia (los
  arreglos de infraestructura sí están permitidos). Si surge la tentación de "aflojar para
  tener más señales": eso es el fracaso del sistema, no del mercado (auditor, Fase 3).
- Backup pre-reset: tfz_data.db.bak4_*.

## 2026-06-30

### GitHub corre continuo SIN token (runs largos)
- El auto-relanzado con PAT no funcionó fiable y el usuario no quiere depender de un token.
  Nuevo enfoque (repos publicos = Actions gratis e ILIMITADOS, runs hasta 6h): cada run dura
  ~5h40m (`END=SECONDS+20400`, `timeout-minutes: 350`), un ciclo cada 5 min. Cron cada 30 min
  en `:17,:47` (minutos "tranquilos" para esquivar la saturacion de GitHub a en punto). Con
  `concurrency` (cancel-in-progress:false), si el cron salta durante un run queda en cola y
  arranca al acabar -> cobertura casi continua, sin PAT. Quitado el paso de auto-relanzado por
  PAT. Logs del runner ahora en hora local (TZ=Europe/Madrid). El secret GH_PAT ya no se usa.

### FIX duplicados + auto-relanzado de GitHub
- **DUPLICADOS (grave, inflaba el PnL):** `_scan_setup` (micro_pullback/round_fade) abria la señal
  fechada en la vela del TRIGGER (pasada) y la reabria CADA ciclo mientras siguiera "fresca" ->
  la misma señal contada hasta 15 veces (TAC ×15, +125% falso). Demostrado con datos crudos. Fix:
  (1) `database.open_paper_trade` ahora DEDUPLICA (mismo símbolo+TF+entry_ts+dir+formación -> no
  reabre) y devuelve bool; (2) `_scan_setup` reancla precio y entry_ts a la vela ACTUAL (igual que
  el path principal) y descarta si el precio ya se salió de [SL,TP] ("moved-skip") -> mata el
  backdating y los TP/SL instantáneos. Verificado: test unitario (1ª abre, 2ª/3ª rechazadas) y los
  dos call-sites respetan el retorno. NOTA: el path principal (F-formaciones) YA tenía el reanclaje;
  solo _scan_setup faltaba. Reset limpio de PC y GitHub tras el fix.
- **GitHub no saltaba solo:** verificado que el cron de GitHub no disparó (sin runs a las 13/14/15:05
  pese a estar `active`). El cron de GitHub es poco fiable. Fix en bot.yml: paso final que
  AUTO-RELANZA el siguiente run via `workflow_dispatch` con un PAT (`secrets.GH_PAT`) al acabar cada
  run (~cada hora), sin depender del cron. Requiere que el usuario añada el secret GH_PAT (PAT
  fine-grained con Actions: Read&Write). Sin él, cae al cron de GitHub (respaldo poco fiable).

### Avisos de Telegram PAUSADOS (PC y GitHub)
- A petición: no recibir avisos de ninguno de los dos bots de momento. `notify.ALERTS_PAUSED=True`
  -> `send_telegram` corta el envío de raíz (entradas y cierres). REVERSIBLE: poner False. Escape:
  env `TFZ_TELEGRAM=1` lo fuerza activo en un sitio concreto si algún día se quiere.

### Arranque desde CERO + igualar estrategia (PC y GitHub idénticos para comparar)
- A petición: las dos cuentas paper empiezan de cero. PC: borrado paper_trades (274) + trade_review
  (272) + portfolio_state.json (backup en *.bak_*). GitHub: arrancaba fresco solo (github_state no
  existía; verificado: 0 runs del bot). Los dos parten de $50, sin historial.
- IGUALADA la estrategia: el PC corría CON ML y GitHub con --no-ml (el modelo estaba gitignorado).
  Elegido "los dos CON ML": `ml_model.joblib` subido al repo (force-add), quitado --no-ml de bot.yml
  (ahora el comando es idéntico al del PC), y `scikit-learn==1.9.0` fijado en requirements para que
  el modelo cargue igual que en el PC. Resultado: misma estrategia + misma fuente (MEXC) + mismo
  arranque -> comparación limpia (solo difiere la cadencia: GitHub ~cada hora, PC cada 5 min).

### DESPLIEGUE DUAL: PC y GitHub en paralelo (cuentas paper SEPARADAS para comparar)
- A petición: correr el bot en el PC Y en GitHub a la vez para comparar cuál va mejor.
- Para que NO se pisen: `database.DB_PATH` y `portfolio.PORTF_FILE` ahora aceptan override por
  env `TFZ_DB` / `TFZ_PORTF`. El PC usa los de siempre (tfz_data.db); GitHub (bot.yml) usa
  `github_state/tfz_data.db` y `github_state/portfolio_state.json` (carpeta propia, commiteada al
  repo cada ciclo). Así el PC puede hacer `git pull` sin sobrescribir su cuenta.
- Selftest CONFIRMADO idéntico: hash PC == hash GitHub (1bd9e6bf90d2ce5e), 7 señales iguales ->
  con MEXC el bot opera EXACTAMENTE igual en ambos sitios.
- PENDIENTE (acción del usuario): el workflow "TFZ Bot Paper" está `disabled_manually` en GitHub;
  hay que darle a "Enable workflow" en la pestaña Actions (no se puede por API sin token).
- NOTAS de comparación honesta: (1) la cuenta de GitHub arranca FRESCA en $50; la del PC arrastra
  su historial (~$39) -> comparar expectancy de aquí en adelante, no el equity absoluto. (2) GitHub
  corre ~cada hora (50 min de ciclos cada 5 min + hueco); el PC cada 5 min continuo -> cadencia
  parecida pero no exacta. (3) el bot.yml usa flags 1m,5m,15m/F1/profit; si la tarea del PC usa
  otros, la comparación no es 100% limpia (alinear si se quiere rigor).

### TEST DE VPN en GitHub (idea del usuario): inconcluso, VPN gratis no conecta
- Probado de verdad (no descartado de palabra): vpn_pick.py baja config de VPN Gate (servidores
  gratis, Japón) -> OK genera vpn.ovpn. Pero el túnel openvpn NO sube en el runner (2 intentos, con
  arreglo de cifrados BF-CBC): las configs gratis usan opciones legacy (comp-lzo/cifrados viejos)
  que OpenVPN 2.6 rechaza, y los servidores son flojos. IP de salida seguía siendo US -> 451/403.
  CONCLUSIÓN: el principio es válido (salir por país no bloqueado esquivaría el bloqueo), pero una
  VPN gratis fiable en CI no se sostiene; haría falta una de PAGO (config limpia) -> cuesta dinero
  y su IP podría estar también en lista negra. MEXC sigue siendo mejor (gratis, ya verificado).

### MIGRACIÓN A MEXC (reversible) — para correr 24/7 en GitHub
- **Por qué:** Binance(451) y Bybit(403) geo-bloquean a GitHub. Verificado a fondo: 3 librerías
  (ccxt, connector oficial, python-binance) chocan igual (es por IP, no por librería); 11 endpoints
  probados DESDE el runner (diag_regions.py): los 8 dominios de Bybit (com, bytick.com, .eu, .nl,
  -tr.com, .kz, global) dan 403 CloudFront; fapi.binance 451; solo data-api.binance.vision SPOT
  responde (no sirve, es spot). MEXC es el ÚNICO con futuros en vivo NO bloqueado (diag_mexc.py
  desde GitHub: 814 perp, 29/30 monedas, 85.619 velas OK). Velas idénticas a Binance (<=0.014%).
- **Cambios:** `config.default_exchange="mexc"`, `fallback_exchange="binance"` (REVERSIBLE: volver a
  "binance" deshace todo, no se quitó nada de Binance). `data_fetcher.create_exchange`: mexc->swap.
  Nuevo `data_fetcher._resolve_symbol`: traduce el símbolo interno del bot al de MEXC (acciones
  con sufijo STOCK: MSTR->MSTRSTOCK, MU->MUSTOCK, QQQ->QQQSTOCK, CRCL->CRCLSTOCK; memes sin 1000:
  1000PEPE->PEPE, misma %). fetch_ohlcv usa el símbolo traducido. Solo CL (crudo) no existe en MEXC
  (en el PC cae a Binance por el fallback; en GitHub se pierde 1 moneda).
- Verificado en el PC: ciclo completo `main.py paper` corre OK con MEXC, abre/cierra normal, los 6
  trades abiertos resuelven a MEXC sin problema de escala (no había 1000PEPE abierto).
- Cache se separa por exchange -> no mezcla con la de Binance/Bybit.

### ARREGLO A: resolución INTRAVELA (cierres más realistas)
- `paper._check_exit`: cuando UNA sola vela contiene a la vez el SL y el TP, antes se asumía SL
  (pesimista) -> falseaba muchos cierres, sobre todo en 1h. Ahora, en ese caso ambiguo, mira las
  velas de 1m DENTRO (`_intrabar_first`) para saber cuál se tocó primero. Si no hay datos de 1m,
  mantiene el pesimismo como respaldo seguro. Motivado por C (medido): los trades cierran en
  mediana 1 vela de su TF; en 1h el 83% entra con la señal ya 2-3 velas vieja.

### MEJORA B: stop ENSANCHADO en micro-pullback (x2) — valida y aplicado
- `micro_pullback.MPB_SL_MULT=2.0`: el SL se aleja x2 la distancia a la pausa (TP sobre el riesgo
  original). Validado en la MISMA tanda (2281 señales), por TF y OOS: win 32->44%, expectancy
  +0.131->+0.320% (OOS +0.29->+0.62%); además los trades RESPIRAN más (mediana 2->4 velas; cierres
  en 1 vela 41->21%). El TRAILING se probó y se DESCARTÓ (empeora: corta ganadores). Nota: el
  micro-pullback en 5m es flojo/negativo incluso ensanchado; el edge vive en 1h/15m. REVERSIBLE:
  MPB_SL_MULT=1.0 vuelve al stop ceñido.

### Pendiente detectado (no aplicado): entradas tardías (raíz de "se cierra al instante")
- C confirmó que en 1h/15m el bot entra con la señal vieja (1h: mediana 3 velas tarde, 83% >2
  velas) -> entra a un precio ya pasado -> cierre casi inmediato. Propuesta a validar: GUARD de
  "precio de entrada cerca del precio actual" (no entrar si el mercado ya se fue del nivel).

## 2026-06-29

### FADE-SHORT pausado + tope de tendencia (sangraba en régimen de pumps)
- En vivo el fade-short se hundió (win 44% vs 66-76% validado, sum -26%): regimen reciente de pumps fuertes ->
  los numeros redondos ROMPEN en vez de rechazar (RAVE rompio 0.4->0.45, CBRS 200->219). El fade se salta el gate
  de tendencia (por diseño) -> shortea subidas fuertes. NOTA: NO era bug; los SL cierran a -1.2% (los -10% eran
  marcador en vivo; RAVE/CBRS cerraron a -1.20% al correr el ciclo). Cartera cayo a ~$39.66 (-20%, throttle activo).
- Medido por fuerza de tendencia: el fade pierde en trend 3-10% (la zona donde rompen); cap a <=3% (subidas suaves)
  recupera a +0.154% win 64% (vs +0.037% sin tope, ya con los pumps en los datos). `config.round_fade_trend_max=3`
  aplicado en detect_round_fade. `config.enable_round_fade=False` -> PAUSADO; el micro-pullback (long, a favor de
  tendencia) sigue activo (es el bueno para regimen alcista; sus runners TAC/SYN abiertos en verde).
- TAMBIEN: FADE_TOL 0.6%->1.0% (el coste ~0.2% se comia 1/3 del objetivo de 0.6% -> siempre +0.40/-0.80; a 1.0%
  pesa 1/5 y la expectancy validada sube +0.15->+0.21%).

### MEJORA F3: umbral de score propio (>=80 en vez de 60)
- F3 (cascada) era la formacion mas floja (+0.85%/trade). Análisis: el F3 con score>=80 da +1.30% (OOS +1.23%,
  win 44%) vs el de 60-80 que arrastra (+0.55%). Validado limpio sobre el conjunto: pedir F3>=80 sube el TODO
  de +2.313% a +2.454%/trade (OOS +2.074->+2.227), robusto a umbrales cercanos (75/80/85 suben suave; >=85 ya
  deja 4 trades = sobreajuste, 80 es el punto). `config.f3_min_score=80`; aplicado en `fresh_accepted_signals`
  (eff_min = 80 solo si formation_type=='F3'; las demas siguen en 60). Live: ciclo limpio.

### AÑADIDO throttle de drawdown ("Trader Rehab", Warrior Trading) en la cartera
- `portfolio.DD_THROTTLE`: si el equity cae >=10% del pico -> riesgo a 1/2; >=20% -> 1/4; vuelve a normal al
  recuperar pico. Reduce la profundidad del bache (preserva capital) a cambio de recuperar mas despacio. Es
  RIESGO, no edge (no cambia expectancy/trade). Track de "peak" en el estado.

### AÑADIDO setup MICRO-PULLBACK (Warrior Trading), LONG de continuación — 5m/15m/1h
- Nuevo `micro_pullback.py`: en tendencia, pausa de 1 vela (maximo mas bajo) sobre la 9 EMA, entrada al romper el
  maximo de la pausa; stop=minimo pausa; TP=RR3. VALIDADO fuerte: +0.23-0.28%/trade, OOS +0.37-0.41%, y el
  CONTROL (long aleatorio en tendencia) es NEGATIVO -> el patron aporta. Por TF: 1h +0.51% (mejor), 15m +0.13%,
  5m marginal pero OOS+. 3451 trades. Integrado via `paper._scan_setup` (generico) -> scan_micro_pullback, fuera
  del filtro rr>=6. Smoke test: abrio TAC/GWEI/RE long.

### AÑADIDO setup FADE-SHORT en resistencia de número redondo (1h/15m)
- Nuevo `round_fade.py`: detect_round_fade replica el setup validado (en tendencia alcista, precio 0.3-1.2% bajo
  un entero -> lo TOCA -> short al nivel, TP/SL +/-0.6%). Validado: 1h win 66% exp +0.076% OOS +0.047%; 15m leve
  +0.031%/+0.042%; 5m negativo (no se usa). Modesto pero real, OOS, control plano.
- Integrado en `paper.scan_round_fade` (1h+15m), llamado desde run_cycle. Va por su PROPIO camino: NO pasa el
  filtro score>=60 & rr>=6 (es high-winrate/RR~1) ni el gate de tendencia (es fade counter-trend validado);
  solo guards basicos (1-por-moneda, cap correlacion, cooldown). Smoke test: abrio ENA short en 0.08 y SUI en 0.7.

### AÑADIDO filtro RVOL (volumen relativo, idea de Warrior Trading) — por temporalidad
- Investigado Warrior Trading; el RVOL (vol vela / media 20 velas) resultó el candidato top. Test 1: post-hoc
  sobre CSV salió ENGAÑOSO (solo 172/1709 trades por límite de caché) -> parecía no aportar. Test 2 BIEN HECHO:
  RVOL calculado DENTRO del backtest (columna 'rvol' en ml_dataset, los 1825 trades). Resultado MONÓTONO: a más
  RVOL, más expectancy y mejor OOS. Confirmado POR TEMPORALIDAD: el edge está concentrado en 1m (RVOL>=2 casi
  DOBLA: +2.74->+4.38%/trade, winrate 53->62%, OOS +4.44%), leve en 15m (>=1.5), NULO en 5m.
- Implementado: `config.rvol_min` por TF en TIMEFRAME_PARAMS (1m:2.0, 15m:1.5, 5m/1h:0=off). Filtro en
  `signals.generate_signals`: descarta la señal si rvol(trigger) < rvol_min. Mismo sitio -> backtest y vivo igual.
- Lección (otra vez): el test rápido decía "no sirve"; el bien hecho (muestra completa + por TF) dice "sí, en 1m".
  Verificar a fondo antes de un veredicto. La mejora de winrate (1m 62%) ataca justo la preocupación del usuario.

### GitHub Actions DESCARTADO: runners geo-bloqueados por Binance(451)/Bybit(403)
- Tras montarlo y subirlo (repo curro3217-dev/tfz-bot), prueba de reproducibilidad (selftest.py, idea del
  usuario) cazó que en GitHub salían 0 señales: TODOS los símbolos daban "Could not connect to any exchange".
- diag_net.py confirmó: desde el runner, Binance HTTP 451 (geo) y Bybit HTTP 403 en todos los endpoints (incl.
  fapi.binance.com/ticker, el del scanner). El bot no puede bajar datos en GitHub -> no opera.
- Acciones: workflow del bot DESACTIVADO en GitHub (repo queda como backup de código, antes no había git).
  Bot del PC REACTIVADO como stopgap (Binance sí funciona desde la red de casa). 24/7 real -> Oracle Cloud en
  región permitida (Frankfurt) o VPS. Ver memoria github-actions-geobloqueo.

### Preparado para correr 24/7 en GitHub Actions (como el scanner del usuario)
- Motivo: el bot solo corría ~48% del tiempo (PC apagado ~178h de 340h; ~7h cada noche). Sin 24/7 la muestra
  en vivo no vale (nos perdemos la mitad de señales y la gestión nocturna). Oracle Cloud quedó bloqueado en el
  registro -> se va a GitHub Actions, copiando el patrón YA probado del scanner del usuario (repo zct-scanner):
  disparo horario externo (cron-job.org via workflow_dispatch) + bucle interno cada 5 min + estado subido al repo.
- Archivos nuevos: `requirements.txt` (añadido requests/urllib3), `.gitignore` (excluye caché/csv/logs/bak y la
  BD local), `.github/workflows/bot.yml` (bucle ~50 min, commitea tfz_data.db cada ciclo, secrets de Telegram),
  `GITHUB_SETUP.md` (guía paso a paso). El bot corre con --no-ml (filtro profit no usa ML -> sin dependencia del
  modelo .joblib). scanner_bridge ya es portable (scanner de respaldo integrado). Arranca con BD nueva (limpio).
- NOTA de proceso: yo había descartado GitHub Actions como "mala idea" siendo demasiado tajante; el usuario ya lo
  tenía funcionando con el scanner. Rectificado. (memoria no-descartar-tajante)

## 2026-06-21

### F1 con ENTRADA EN RETEST — ¡la flipa a POSITIVO! (estrategia real de Mark, por fin con edge)
- **Idea:** el cuello de F1 era el winrate bajo (~17%, falsos breakouts). En vez de entrar en la vela de RUPTURA,
  esperar al **retest que aguanta**: el precio rompe, vuelve a tocar el nivel y CIERRA por encima (lo defiende).
  Los falsos breakouts no aguantan el retest → se filtran solos y sube el winrate.
- **Cambios:**
  - `config.py`: `f1_retest_entry: bool = False`, `f1_retest_window: int = 8`, `f1_retest_tol: float = 0.003` (0.3%).
  - `signals.py` `_find_trigger`: para F1 (si `f1_retest_entry`), tras el breakout busca en las siguientes
    `f1_retest_window` velas la que toca el nivel (low<=rh*(1+tol)) y cierra por encima → entra ahí. Si cierra de
    vuelta dentro del rango antes → falso breakout, descartado. (Añadidos `highs`/`lows` a la función.) Short en espejo.
  - `ml_dataset.py`: flag `--f1-retest`.
- **Build:** `ml_dataset_f1retest.csv` (mismo set de 20 que f1mark, perp+funding).
- **Resultado F1 (todos):** ruptura 13.2% win / −256% → **retest 19.0% win / −92%** (expectancy −0.27→−0.077%/trade).
- **Con filtro de PRODUCCIÓN (score>=60 & rr>=6, el mismo que F4):** **102 trades, 32.4% win, +105% sumPnL,
  +1.03%/trade.** POSITIVO.
- **Robustez:** 10 monedas positivas vs 9 negativas (repartido); quitando los 3 mejores trades sigue +41%
  (no son outliers); ambos TF positivos (5m +88%, 15m +17%); perfil asimétrico igual que F4 (mediana −0.20%,
  pocos ganadores grandes). Es un edge real.
- **Pendiente decisión usuario:** activar F1+retest en vivo junto a F4 (ambos bajo filtro profit) o solo como alertas.

## 2026-06-22

### PROBADO y RECHAZADO: BE-lock por runup (+3R -> breakeven)
- Motivado por el patrón "corre +X R y se gira" (en vivo, 6/6 corredores >=2R acabaron en pérdida). Idea: mover
  SL a breakeven tras +3R y dejarlo (NO trailing). Implementado: config.be_lock_runup_r + backtester + flag --be-lock.
- 1er intento de comparación CONTAMINADO (nº trades 1872 vs 1698: la caché Binance cambió entre los 2 builds).
  Detectado por el invariante (al ser solo de salida, el conteo DEBE ser idéntico). Añadido FREEZE_CACHE=1 en
  data_fetcher (lee caché tal cual, sin pedir velas) para A/B 100% limpio. Rebuild congelado: 1698 == 1698 OK.
- Resultado LIMPIO (60/6): baseline exp +2.399% (OOS +2.233%) vs BE-lock +2.315% (OOS +2.131%). EMPEORA.
  Mató 16 ganadores grandes (>+3%) por 472->456. Misma lección que trailing/parcial: proteger corredores cuesta
  más de lo que salva. be_lock_runup_r se queda en 0 (desactivado).

### CAMBIO fuente de datos a BINANCE + multi-activo + arreglos operativos
- Decisión usuario: usar volumen/datos de BINANCE (más fiable) y operar MULTI-ACTIVO (cripto + acciones +
  materias primas tokenizadas), no solo cripto Bybit. "Una estrategia buena debería funcionar en varios activos".
- `config.default_exchange` bybit->binance (fallback bybit). `data_fetcher.create_exchange` ahora fija
  defaultType 'future' para binance / 'swap' para bybit (sin eso binance carga SPOT y los perp no resuelven).
  La caché parquet se separa por exchange -> no se mezcla con la vieja de Bybit. Verificado: DOGE y NVDA (acción,
  $193) llegan rápido de Binance.
- `liquid_watchlist` ahora mide volumen de BINANCE >=85M (igual que el scanner) en vez de Bybit >=50M; devuelve
  BASE/USDT:USDT; incluye acciones/materias (NVDA, QQQ, SOXL, oro...). Excluye solo BTC/ETH (gate).
- PROBLEMA operativo detectado: con caché vacía, el primer ciclo descarga ~42 símbolos x 3 TF de golpe (>5 min);
  el paper cada 5 min se SOLAPABA consigo mismo y saturaba la máquina (todo colgado). ARREGLOS: tarea con
  MultipleInstances=IgnoreNew (no solapar) + ExecutionTimeLimit=PT10M; y se PRE-CARGA la caché con un ciclo
  manual antes de reactivar el 5-min.
- PENDIENTE: re-validar el edge con datos de Binance (todo lo validado era Bybit-cripto). CAVEAT acciones: no
  cotizan 24/7 -> huecos en velas -> posibles barridos/stops falsos; vigilar en los datos.

### CAMBIO brújula de tendencia: regresión 4h (antes 2-puntos 24h)
- Queja del usuario (con razón): el bot longueó IP estando en clara caída, porque la tendencia era un 2-PUNTOS
  (precio ahora vs hace ~24h). IP venía de 0.35 -> pico 0.42 -> caída a 0.37: el 2-puntos daba +6.65% "alcista"
  porque el inicio estaba bajo, ignorando la caída reciente. En 1m la ventana de 24h además se capaba a ~10h (600 velas).
- FIX en `swings.compute_trend_strength`: ahora PENDIENTE DE REGRESIÓN LINEAL sobre la ventana (capta la forma/
  dirección real, no 2 puntos sueltos) + ventana por defecto 4h (reciente). `config.trend_lookback_hours` 24->4
  para que ml_dataset (validación) mida IGUAL que el vivo. Verificado: IP ahora -8.6% (BAJA), se bloquearía el largo.
- El usuario fue tajante: si él ve bajista, el bot también; no vale "ya lo probamos". Es un cambio del MEDIDOR
  (no solo la ventana, que sí se probó antes). Re-validación en marcha (ml_dataset_trendfix.csv) para el número honesto.

### FIX guard de datos frescos (no operar con velas caducadas)
- Detectado (usuario hizo revisar): DOT/JUP abrieron con velas de 6h de antigüedad -> entrada/salida basura sobre
  datos muertos (entry_ts 25-jun 22:42 vs apertura real 26-jun 04:41). El feed/caché devolvía velas viejas para
  algunas monedas en ciertos ciclos. El fix de entry_ts no ayuda si el dato YA viene viejo.
- FIX en `fresh_accepted_signals`: tras fetch, si la última vela es más vieja que el máximo por TF
  (1m:5min, 5m:20, 15m:60, 1h:180) -> [stale-data] y no opera esa moneda ese ciclo. Verificado en vivo: cazó
  XPL 5m con velas de 665 min y lo saltó. Borrados los 2 trades basura (DOT/JUP) + autopsias; cartera reset a $50.

### Autopsia post-trade (trade_review.py) + campos de contexto
- Nuevo `trade_review.py`: tras cada cierre (enganchado en `update_open_trades`) calcula factores DETERMINISTAS
  (no narrativa): outcome, tendencia en entrada (canónica) + contra/a-favor, runup/drawdown máx en R, velas,
  movimiento de BTC durante el trade, score, y AÑADIDO: hora, día de semana, volatilidad (ATR%), volumen relativo.
  Se guarda en tabla `trade_review`. `print_reviews` muestra autopsia + comparación ganadoras-vs-perdedoras +
  desglose por día/hora. Aplicado retro a los trades de hoy. Objetivo: que el patrón de pérdidas emerja de DATOS.
- Nota: con muestra pequeña la comparación aún no concluye nada; es infraestructura para cuando haya volumen.

### FIX bug de anclaje de salida (exit_ts imposible + bucle de re-entradas) + cooldown
- Síntoma 1: exit_ts de trades marcaba hora ANTERIOR a opened_at (ej. OP: abrió 14:30 local/12:30 UTC, exit_ts
  12:30 UTC con trigger 12:25). Síntoma 2: OP se shorteó 3 veces en 10 min (todas SL), re-entrando el mismo setup.
- Causa ÚNICA: `_check_exit` anclaba el escaneo de salidas a `entry_ts` = vela TRIGGER (anterior a la apertura
  real). Con el fix de fidelidad (precio = apertura), el trade "detectaba" su SL en velas PREVIAS a existir ->
  cierre instantáneo falso -> liberaba el guard 1-por-moneda -> el ciclo siguiente reabría el mismo trigger (bucle).
- FIX en `paper.scan_new_signals`: `entry_ts = df["timestamp"].iloc[-1]` (vela de apertura, casa con el precio
  reanclado). _check_exit ahora escanea salidas SOLO desde que el trade existe. Arregla AMBOS síntomas de raíz.
- Mejora colateral: la duración (para funding) y el conteo de stale ahora cuentan desde la apertura real, no el trigger.
- AÑADIDO cooldown anti-re-entrada (`config.reentry_cooldown_min=30`): tras SL/breakeven en una moneda+dirección,
  no reabrir esa combinación durante 30 min ([cooldown-skip]). Seguro de comportamiento EN VIVO (NO medible en
  backtest: el bucle de re-entrada es artefacto del ciclo de 5 min, no existe en histórico). Aplica a trades nuevos.

### Universo "fijo" DINÁMICO por liquidez (sustituye la lista estática ilíquida)
- Problema: de las 30 veteranas estáticas, solo 4 llegaban a 100M vol 24h; 25 estaban por debajo (ATOM 7.9M,
  ALGO 7M, PENDLE 6.3M...) -> fills reales con más slippage que el backtest. Y FET ya no existe en Bybit.
- Realidad medida (597 perps Bybit): solo 14 pasan 100M, solo 2 pasan 100M+mov10%. El umbral 100M es irreal en
  Bybit (el volumen se concentra en Binance). El scanner externo NO mide volumen de Bybit perp (pasa coins <100M).
- Decisión del usuario: umbral >=50M vol 24h (~30 coins). Nueva `paper.liquid_watchlist()`: escanea TODOS los
  perps USDT de Bybit, devuelve los >=50M, EXCLUYE metales tokenizados (XAU/XAG/XAUT) y BTC/ETH (drivers+gate).
  Cacheado 20 min, fail-safe a PERSISTENT_WATCHLIST si el escaneo falla. `resolve_watchlist` la usa en vez de la
  estática -> cada ciclo re-evalúa liquidez; una moneda que cae <50M sale sola y entra otra que ahora cumple.
- Resultado: ~25 líquidas dinámicas (todas operables) + movers del scanner. Las ilíquidas/muertas salen solas.
- CAVEAT honesto: ~la mitad de las líquidas son cripto nuevas sin medir (HYPE, XRP, BNB, LAB, SLX, SPCX, MU,
  1000PEPE, O, FARTCOIN, M, SOL). El edge se validó OOS por METODOLOGÍA, no por moneda concreta; el vivo dirá.

### Cap de correlación: máx 3 posiciones abiertas por dirección
- Visto en vivo: clusters de 6-7 longs que se iban TODOS al stop juntos cuando BTC/mercado caía (los alts van
  casi todos correlados). FIX: `config.max_open_per_dir=3` + chequeo en `paper.scan_new_signals` -> si ya hay 3
  abiertos en una dirección, los nuevos de esa dirección se saltan ([corr-skip]). Limita el riesgo de cola
  correlado y hace realista el margen de una cuenta pequeña ($50 no aguanta 7 posiciones apalancadas).
- Es decisión de RIESGO, no de edge: reduce nº de trades (salta +EV) a cambio de menos varianza/drawdown. NO
  mejora expectancy/trade. El backtest (posiciones ilimitadas, sin margen) no la valida como edge; su valor está
  en reducir el drawdown correlado en vivo.

### FIX fidelidad de entrada: reanclar al precio ACTUAL al abrir (no a la vela trigger)
- BUG detectado por el usuario (UNI short 1m): el bot guardaba el entry = cierre de la vela TRIGGER, pero abre el
  trade en el ciclo siguiente (cada 5 min). En 1m, entre el trigger (12:32, 2.943) y la apertura (12:35, ~2.911)
  el precio se desplomó 1.1% → entry registrado OPTIMISTA (irreal). Infla resultados del paper, peor en 1m por el
  desfase de 5 min vs señales de segundos.
- FIX en `paper.fresh_accepted_signals`: al aceptar, se reancla `entry_price` al precio ACTUAL y se recomputan
  risk_pct/rr_ratio con el MISMO SL/TP estructural. Si el precio ya salió de [SL,TP] o el riesgo supera max_risk
  → `[moved-skip]`. Si el RR reanclado cae < min_rr (el movimiento ya pasó) → lo descarta el filtro 60/6. El UNI
  ejemplo: reanclado a 2.911 da RR 0.24 → se habría descartado. Mejora la fidelidad en TODOS los TF, crítico en 1m.
- NOTA: las entradas previas (incl. la UNI abierta a 2.943) quedaron con precio optimista; el fix solo afecta a
  aperturas nuevas. El edge real del 1m en vivo será menor que el backtest (que asumía entrada instantánea).

### 1m AÑADIDO al paper (validado OOS) + ventana del trend gate / patrón HEI rechazados
- **1m activado:** launcher `run_tfz_paper.cmd` `--timeframe 5m,15m -> 1m,5m,15m`. El 1m valida OOS positivo
  (+1.86%/trade OOS+IS, robusto), aunque secundario al 5m (+2.99%). Ciclo con 3 TF corre en ~1.5 min (cache). Flag
  `--timeframes` en ml_dataset para builds.
- **Ventana del trend gate (24h vs 12h/6h) — RECHAZADO:** acortar la ventana EMPEORA mucho (24h +3.32%/trade, 1302 tr
  vs 12h +1.89%, solo 267 tr). Ventana corta = ruidosa, marca casi todo como "en tendencia" y sobre-bloquea. Se queda
  24h. `compute_trend_strength` ahora acepta `hours` (param) + config `trend_lookback_hours`; flag `--trend-hours`.
- **Patrón HEI (short de coin pumpeada que se gira) — NO es edge:** build sin gate (`--trend-block 999`), aislado el
  patrón (trend_strength>=5 & trend_intraday<=-2 & short): solo **1 trade** en 40 monedas/meses (ultra-raro). Shorts
  pumpeados en general (15 tr) rinden +1.26% vs +2.77% los normales (533 tr). El gate hace bien bloqueándolos. HEI
  fue un caso aislado real, medido, no un edge sistemático.

### Stale 30 -> 80 APLICADO (test LIMPIO + validado OOS)
- El primer barrido del stale estaba CONTAMINADO (comparé f4tag/stale30 construido horas antes vs stale50/80
  nuevos -> trades distintos por crecimiento del cache; el conteo distinto era la pista, ver memoria
  comparaciones-limpias). Rebuild LIMPIO en misma tanda (st30/st80/st120, conteos ~iguales 1410/1382/1407).
- **Resultado robusto en AMBAS mitades:** stale 30 OOS +2.157% / IS +2.724%; stale 80 OOS +2.705% / IS +3.818%;
  stale 120 OOS +2.779% / IS +4.126%. El salto real es 30->80 (OOS +0.55pp); 80->120 casi no aporta OOS (+0.07pp)
  y ata el capital (30h en 15m). APLICADO `config.stale_candles 30 -> 80` (punto óptimo: captura la mejora robusta
  con holds razonables). Afecta a backtest y vivo (_check_exit usa cfg.stale_candles). Primer cambio del día que
  pasa la validación OOS limpia. CORRIGE la conclusión previa errónea ("stale no validaba OOS", que era el artefacto).

### Cartera simulada $50 (riesgo 1%/trade, tope 10x)
- `portfolio.py` + comando `python main.py portfolio`: cartera de $50 que cuenta los trades cerrados DESDE su init
  (abiertos al momento + futuros; excluye los ya cerrados). Sizing riesgo 1%/equity por trade, lev=min(1/stop%,10),
  compone. Se actualiza en cada ciclo del paper (run_cycle). Estado en portfolio_state.json.

### Stale (primer barrido, CONTAMINADO - ver entrada de arriba)
- A raíz de la intuición del usuario ("GALA cerró demasiado pronto"), barrido de `stale_candles` (30/50/80) sobre
  40 monedas (60/6, todas formaciones). Flag `--stale` en ml_dataset.
- **Resultado MONOTÓNICO: cuanto más largo, mejor.** stale 30 (actual): 47.1% win, +2.672%/trade, +3546%.
  stale 50: 44.6% win, +2.932%, +3774%. stale 80: 42.3% win, +3.190%, +3997%. El winrate baja pero la
  expectancy y el PnL total suben: dar más aire deja que trades lentos lleguen a su TP grande en vez de cortarlos
  planos. Es el PRIMER cambio probado que mejora (trailing/parcial/intradía/consolidación/reversión todos empeoraban).
- PENDIENTE: validar OOS (split temporal, como con sl_offset) antes de aplicar; y probar el pico (100/120) por si
  sigue subiendo. Considerar trade-off en vivo: stale más largo = holds más largos = menos huecos libres para nuevas
  entradas (en backtest no hay límite de posiciones; en vivo sí con 1-por-moneda). NO aplicado aún.

### Estado de abiertas con PnL direccion-aware (herramienta canónica)
- `paper.open_position_state(trade)`: PnL no realizado + distancias a SL/TP de una posición abierta, calculados
  SEGÚN la dirección (long/short). `print_status` ahora muestra por cada abierta: precio actual, PnL correcto y
  margen a TP/SL, más el PnL no realizado total. Motivo: se reportó FIL (short) como long con PnL invertido al
  recalcular la fórmula a mano en un script ad-hoc. Norma: usar `python main.py paper --status` para reportar
  estado, nunca reinventar el cálculo. (Memoria: no-recalcular-a-mano.)

### Criterio de Mark "consolidación antes del sweep" para F4 — PROBADO, NO mejora (lo empeora)
- Mark explicó (Telegram, RE) su filtro exacto: un barrido solo es entrada válida si el precio CONSOLIDÓ en la
  zona clave ANTES; "no consolidation, no entry". El F4 del bot NO lo exigía (solo sweep+continuación+reclaim+score≥60).
- Implementado: `formations._has_preceding_consol` (¿consolidación que terminó <=f4_consol_window velas antes del
  sweep y cerca del nivel?), tag `f4_has_consol` propagado a Formation→Signal→dataset, flag `--f4-consol` y config
  `f4_require_consol`/`f4_consol_window`. Build `ml_dataset_f4tag.csv` con TODOS los F4 etiquetados.
- **Resultado (F4, 60/6): los "directo-a-barrer" (que Mark se salta) son MÁS rentables.** F4 con consolidación
  previa: 124 tr, 50.8% win, +3.137%/trade. F4 directo-a-barrer: 736 tr, 54.1% win, +3.449%/trade. Aplicar el
  filtro de Mark al conjunto completo: expectancy +2.672%→+1.704%, sumPnL +3546%→+1007% (−71%, elimina 736 trades
  rentables). DECISIÓN: NO exigir consolidación en F4 (`f4_require_consol`=False).
- Razón en los datos: el F4 del bot ya filtra por continuación/reclaim/score; los straight-to-sweep que pasan ya
  son de calidad. El detector de consolidación (compresión ATR) es más estricto que el "a ojo" de Mark. Mismo
  patrón que trailing/parcial/reversión: mecanizar la discreción de Mark rinde peor que las reglas del bot.

### Toma de beneficios PARCIAL (método de Mark) — PROBADO y RECHAZADO con datos
- Mark toma parciales en sus ganadores (banca ~6% y deja correr el resto hasta el TP). Implementado: parcial
  configurable (`config.partial_enabled/partial_frac/partial_size`; backtester _simulate_trade: al alcanzar
  partial_frac del camino al TP cierra partial_size y mueve el resto a breakeven; flag `--partial frac,size`).
- **Resultado (60/6, 40 monedas): el parcial RECORTA el edge** (igual que el trailing). Sin parcial +2.722%/trade
  (+3516%). 0.6/0.5 (banca 50% al 60% del camino) +2.207%. 0.4/0.5 +1.848%. Winrate sube (47%->48-50%) pero
  sumPnL y expectancy bajan: bancar cierra los ganadores grandes a media subida, que son los que sostienen el
  edge asimétrico. Cuanto antes/más se banca, peor. DECISIÓN: NO añadir parcial. partial_enabled queda en False.
- Nota: Mark sí gana con parciales porque su gestión es DISCRECIONAL (decide cuándo según la estructura en vivo);
  un parcial MECÁNICO a fracción fija del TP no captura eso y resulta negativo, como el trailing y la reversión.

### Acelerar muestreo en vivo: watchlist 14->30 veteranas + fresh 2->3
- Para que el paper acumule trades más rápido (era ~1/día). PERSISTENT_WATCHLIST ampliada de 14 a 30 veteranas
  (las 16 nuevas son TODAS del universo ya validado OOS: LINK, SUI, SEI, TIA, ENA, ONDO, PENDLE, FET, RENDER, JUP,
  WIF, LDO, CRV, GALA, XLM, ALGO). Watchlist total ahora ~39 (movers + 30). Launcher `run_tfz_paper.cmd`: `--fresh
  2 -> 3` (captura setups que se quedaban stale por 1 vela; entrada un pelín más tarde). La validación de fondo
  sigue siendo el backtest (OOS/MC); esto solo acelera el chequeo forward.

### Filtro de calidad en movers — PROBADO, NO es el cuello (rechaza solo 2 trades a 60/6)
- Duda: ¿el filtro de calidad (check_chart_quality) deja escapar movers buenos? Test: build sobre 19 volátiles
  (movers actuales + jóvenes de la validación) con `--no-quality` (bypass) etiquetando cada trade `quality_pass`
  1/0. Flag `--no-quality` y columna en ml_dataset.
- **Resultado (60/6, todas formaciones): de 652 trades, 650 PASAN calidad (+2.69%/trade) y solo 2 son rechazados.**
  O sea: el filtro de calidad NO está costando trades buenos — el filtro de SCORE (≥60) ya descarta las ventanas
  caóticas (estructura sucia → score bajo). A nivel de producción el quality filter es casi redundante. Relajarlo
  no ganaría nada (2 trades). DECISIÓN: dejarlo como está.
- **Conclusión movers:** NO están infra-operados. En estas 19 volátiles hay 650 trades a +2.69%/trade (mismo edge
  que el global +2.72%). Lo que parecía "los movers no se operan" era un artefacto de SNAPSHOT: un mover recién
  pumpeado está en su fase más violenta (ventana falla calidad + sin setup fresco), pero según forma estructura SÍ
  se opera (SYN hoy). El sistema ya caza movers bien.

### Trailing stop (chandelier) — PROBADO y RECHAZADO con datos (recorta los ganadores)
- Tras los casos SYN (+18%→+1.19%) e INJ (+2.4%→+0.65%), se implementó trailing chandelier configurable
  (`config.trail_enabled/trail_atr_mult/trail_activate_r`; backtester `_simulate_trade` sube el SL a k×ATR del
  máximo tras +1R; flag `--trail K` en ml_dataset). Builds k=3/5/8 sobre 40 monedas (60/6, todas formaciones).
- **Resultado: el trailing EMPEORA en todas las variantes.** Sin trailing +2.72%/trade (+3516%). k=3 +1.10%
  (−60%), k=5 +1.95%, k=8 +2.38% (−13%, el menos malo pero aún peor). El winrate sube (47→49%) pero el RR
  realizado y el PnL total BAJAN: el trailing recorta los ganadores grandes (los RR 15 que necesitan espacio para
  llegar al TP), que son los que sostienen el edge asimétrico. Cuanto más ceñido, peor; NINGÚN trailing supera al
  baseline. DECISIÓN: NO añadir trailing. `trail_enabled` queda en False (el código del backtester se queda, off).
  El giveback tipo SYN es el precio de dejar correr a TP los OTROS ganadores grandes; intentar salvarlo cuesta más.

### Umbral del trend gate 1d — PROBADO, SIN CAMBIO (apretar no compensa)
- Barrido del umbral de bloqueo contra-tendencia 1d (5%→0%) por post-filtrado de sl0.5.csv (60/6, todas formas).
  Contra-tendencia rinde MENOS pero NO pierde: a-favor +3.01%/trade (48.8% win) vs contra +0.96%/trade (36.6% win).
  Robusto OOS (contra positivo en ambas mitades: OOS +1.28%, IS +0.48%). Apretar a 0% sube expectancy +2.72→+3.01%
  y win 47→49% PERO baja PnL total 3516→3341% (quita 183 trades positivos, +175%). Mismo patrón que el filtro
  intradía: quitar ganadores flojos sube la media y baja el total. DECISIÓN: dejar trend_block_pct=5% (bloquear
  solo lo claramente contra-tendencia). El INJ 5m lo ilustra: era contra-1d (−2.76%) y ganó (+0.65%).

### Guard 1-posición-por-moneda (evitar doblar exposición)
- El bot abrió 2 longs de INJ a la vez (5m F3 + 15m F2) porque escanea cada TF por separado → exposición doble al
  mismo activo (riesgo combinado 0.55%+1.65%=2.2% en una moneda). No era bug (la validación contó los TF por
  separado) pero sí concentración de riesgo. FIX en `paper.scan_new_signals`: si una moneda ya tiene posición
  abierta (cualquier TF/dirección), no se abre otra → `[dup-skip]`. Cubre también doble apertura en el mismo ciclo.
  Los 2 INJ ya abiertos se mantienen (el guard solo afecta a aperturas nuevas). PENDIENTE: replicar el mismo guard
  en execution.py si se activa trading real (ahora mismo solo corre paper).

### Colchón del stop 0.1 -> 0.5 x ATR (barrido validado OOS, mejora la expectancy)
- Barrido del `sl_atr_offset_mult` (0.1/0.25/0.5/0.75) sobre 40 monedas (ml_dataset_sl*.csv), filtro 60/6, todas
  las formaciones. Al ensanchar el stop: winrate sube (40%->47%->51%), RR baja pero sigue alto (14.7->12.1->11.3,
  >>6), expectancy/trade SUBE (+2.06%->+2.72%->+3.06%), nº de trades baja (1897->1292->1011), PnL total casi igual
  (0.5 = +3516% vs 0.1 = +3904%, -10%). El SL ceñido NO era "la fuente del edge" como se creía: ensanchar mejora
  el resultado por trade sin cargarse el RR.
- **Validación OOS (split temporal): 0.5 gana a 0.1 en AMBAS mitades** — OOS +2.04% vs +1.76%/trade (win 38% vs 34%),
  IS +3.38% vs +2.35% (win 55% vs 45%). No es sobreajuste (el efecto es mecánico: stop ancho -> menos stop-outs).
- **APLICADO:** `config.py sl_atr_offset_mult 0.1 -> 0.5`. Afecta solo a señales NUEVAS (el INJ abierto mantiene su
  SL de 0.1 ya guardado en la BD). Elegido 0.5 (no 0.75) por equilibrio: mejor expectancy/winrate que 0.1 pero
  conserva ~1300 señales (0.75 daba más expectancy pero solo 1011 y menos PnL total).

### Comprobación puntual: el bot "ve" el gráfico real (visor descartado)
- Se montó un visor temporal (chart.py con plotly) que dibujaba las velas 5m/48h con los niveles, rangos, sweeps,
  tendencia y entry/SL/TP que detecta el bot, para contrastar con TradingView. RESULTADO: confirmado, el bot lee
  el mismo gráfico (misma estructura de precio que TradingView/OKX desde Bybit; precios casi idénticos; niveles,
  rangos y sweeps bien detectados). Única diferencia: el eje iba en UTC vs UTC+2 de TradingView (cosmético).
- Era solo para verificar → ELIMINADO (chart.py, run_tfz_chart.cmd, chart_*.html). No se tocó ningún archivo del
  bot; el visor era autónomo. Si en el futuro se quiere, se reconstruye con plotly + el pipeline existente.

### Filtro de tendencia INTRADÍA — PROBADO y RECHAZADO con datos (no mejora el edge)
- A raíz del trade ATOM (short contra un uptrend de 5m), se midió si los perdedores son contra-tendencia intradía
  (trend_intraday = % en ~4h). Conjunto validado: 1897 trades (filtro 60/6, todas las formaciones, intra1+intra2).
- **Resultado: NO hay sesgo.** Perdedores contra-intradía 33.2% vs ganadores contra-intradía 32.6% → prácticamente
  igual. Ser contra-intradía NO predice perder. El ATOM fue varianza normal (un perdedor pequeño, ~60% esperados).
- **Barrido de umbral de bloqueo (0.0–3.0%): ningún umbral mejora el edge.** Bloquear contra-intradía corta
  ganadores y perdedores por igual → baja el PnL total siempre (thr 0.0: +3904%→+2211%, mata 248 ganadores) y la
  expectancy no sube (se queda ~+2.0%). DECISIÓN: NO añadir el filtro intradía. (La columna trend_intraday se queda
  en el dataset por si sirve a futuro, pero no se usa como gate.)

### AUDITORÍA de consistencia validación↔vivo + 2 fixes (costes y huérfanos)
- Auditado todo el sistema buscando discrepancias entre lo VALIDADO (backtester) y lo que corre en VIVO (paper).
  La generación de señales (niveles→formaciones→trend gate→filtro profit→gate BTC) es consistente. Hallazgos:
- **[ALTA, ARREGLADO] El paper guardaba PnL BRUTO; la validación es NETA.** `_check_exit`/`close_paper_trade` no
  restaban costes, mientras `run_backtest` resta `(comisión+slippage)*2 = 0.2%` + funding. El STATUS se veía
  ~0.2%/trade mejor que la realidad (el ATOM −0.474% bruto = −0.676% neto). FIX: en `update_open_trades` se resta
  el MISMO coste que el backtester (commission+slippage ida/vuelta + funding por horas). Y en `main.py` el cfg del
  paper ahora pone `funding_pct_per_8h = 0.01` (igual que la validación; el usuario opera perps).
- **[MEDIA, ARREGLADO] Riesgo de trade huérfano.** `update_open_trades` bajaba 300 velas; si la entrada quedaba
  fuera de esa ventana (PC apagado mucho: >25h en 5m), `_check_exit` no la encontraba y el trade no cerraba nunca.
  FIX: limit 300→1000 (~3.5d en 5m, ~10d en 15m).
- **[BAJA, pendientes/anotados]** F1-mgmt solo está en `_simulate_trade` (no en `_check_exit`; ambos off ahora);
  sin timeout de 200 velas en vivo (el stale a 30 cierra antes); "win" se cuenta pnl>0 en validación vs pnl>0.05
  en STATUS (diferencia ínfima); defaults de min_rr dispersos (config 3 / main 8 / launcher 6). Raíz estructural:
  hay DOS motores de salida duplicados (_simulate_trade y _check_exit) que conviene unificar a futuro.

### opened_at del paper ahora en HORA LOCAL (era UTC, +2h de desfase confuso)
- `database.py open_paper_trade`: `datetime('now')` → `datetime('now','localtime')`. El campo `opened_at` se
  guardaba en UTC, así que un trade abierto a las 10:00 (hora ES / aviso Telegram) figuraba como 08:00 en la BD.
  Ahora coincide con el reloj del usuario y con la hora del Telegram. La tabla estaba vacía → sin mezcla UTC/local.
- `entry_ts`/`exit_ts` se DEJAN en UTC a propósito: son timestamps de VELA (datos de mercado) y `entry_ts` se usa
  como clave para localizar la vela de entrada en `_check_exit` (línea 56); cambiarlos rompería el emparejamiento.
  El STATUS solo muestra `opened_at`, así que de cara al usuario todo queda en hora local.

### Feature trend_intraday añadida al dataset (para medir contra-tendencia intradía)
- `ml_dataset.py`: nueva columna `trend_intraday` = % de movimiento en ~4h en el TF del trade (48 velas en 5m,
  16 en 15m), calculada en la vela de entrada (trigger_idx). Para analizar si los perdedores son contra la
  tendencia intradía y si filtrarlos mejora el edge. Builds `ml_dataset_intra1.csv` (set 20) / `intra2.csv` (20 OOS).

### Historial de paper viejo borrado (empezar limpio con F1+F4)
- Borrados los 13 trades cerrados (16–19 jun, todos F4, etapa contaminada por el crash del paper) de
  `paper_trades` para que el STATUS refleje solo la etapa nueva (F1+retest + F4). Backup previo de la BD en
  `tfz_data.db.bak-20260622-preclean`. STATUS verificado: 0 abiertos / 0 cerrados.

---

### BUG CRÍTICO: el paper en vivo llevaba 78 ciclos CRASHEANDO (UnicodeEncodeError) — ARREGLADO
- Al hacer smoke test antes de activar F1 se descubrió que `paper.py` petaba en cada ciclo: dos prints con
  caracteres no-ASCII (`≥` en el gate BTC línea 410, `válida` en stale-skip línea 212) revientan con la
  codificación cp1252 de Windows al redirigir stdout a `paper_log.txt` (UnicodeEncodeError '≥').
- **Impacto:** el crash ocurría DESPUÉS de "Updating open trades" pero ANTES de `scan_new_signals` → desde que se
  añadió el gate BTC, el paper gestionaba posiciones abiertas pero **NUNCA escaneaba ni abría señales nuevas**.
  78 crashes acumulados en paper_log.txt. El registro de paper (13 trades, 15.4% win) es de ANTES y está obsoleto.
- **Fix:** `≥`→`>=` y `válida`→`valida` en los prints de paper.py; `set PYTHONIOENCODING=utf-8` en
  `run_tfz_paper.cmd` (arregla TODO print unicode de raíz). Smoke test: ciclo completo pasa, escanea y abre.

### F1+retest VALIDADO OOS y ACTIVADO en vivo junto a F4
- **Validación 1 (split temporal):** F1+retest filtro 60/6, mitad antigua (OOS) +14% / 21.1% win / +0.25%/trade;
  mitad reciente +91% / 46.7% win. Ambas positivas.
- **Validación 2 (20 monedas NUEVAS, `ml_dataset_f1retest_oos.csv`, nunca usadas para F1):** filtro 60/6 →
  128 trades, 33.6% win, +106.5% sumPnL, +0.83%/trade. 12 monedas + vs 7 −; sin top3 aún +56%; ambos TF +.
  → NO sobreajustado. F1 (estrategia real de Mark) tiene edge real.
- **Activación en vivo:** flags `--enable-f1 --f1-retest` en `main.py` (comando paper, construye cfg y lo pasa a
  run_cycle); launcher `run_tfz_paper.cmd` actualizado. Ahora el paper opera F1+retest Y F4, ambos bajo el filtro
  profit (score>=60 & rr>=6). Verificado: F1 genera señales y el gate las filtra correctamente.

## 2026-06-18

### F1 + gestión estilo Mark (breakeven temprano) — no la flipa; el cuello es el WINRATE
- Implementada gestión de Mark en backtester (`f1_mgmt`/`f1_be_candles`/`f1_be_min_runup`): si el breakout no
  funciona en N velas, salir a ~breakeven en vez de esperar el stop. Build `ml_dataset_f1mgmt.csv`.
- **Resultado:** la gestión SÍ encogió la pérdida media (−0.60→−0.41%) PERO bajó el winrate (22→16%, cortó
  ganadoras) → sigue break-even/negativo (ret −34% vs −25%). No la flipa.
- **Hallazgo clave:** las pérdidas de F1 YA eran pequeñas (la salida stale las corta). El problema de F1 NO son las
  pérdidas grandes — es el WINRATE BAJO (~17%, mayoría de breakouts falsos). Achicar pérdidas no arregla eso.
- **Siguiente palanca (no probada):** CONFIRMACIÓN del breakout — entrar en el RETEST que aguanta (el PDF lo dice),
  no en la vela de ruptura. Los falsos breakouts no aguantan el retest → se filtran, subiendo el winrate (la raíz).

### F1 (estrategia REAL de Mark, Anexo 2 del PDF) re-testeada con filtro de fuerza — CERRADO
- Releído el PDF a fondo: el setup PRINCIPAL de Mark (Anexo 2, "Setup con 80% probabilidad") = F1 (2 niveles
  arriba + consolidación + breakout, TP tras barrer la liquidez de arriba). El sweep es el OBJETIVO, no requisito.
  Nuestro bot corre F4 (manipulación = Anexo 1, secundario) y teníamos F1 DESACTIVADO → desviados del método.
- Verificado: nuestra F1 SÍ seguía el checklist (stop bajo consolidación, entrada en breakout, TP en liquidez
  arriba). No era bug. Añadida feature `trigger_body_atr` (cuerpo de la vela de entrada / ATR = fuerza del breakout)
  en signals.py + ml_dataset. Build `ml_dataset_f1mark.csv` (--enable-f1, 18.024 trades).
- **VEREDICTO (definitivo):** F1 NO funciona mecánicamente, ni filtrando por fuerza del breakout. Winrate 11-22%
  en todos los buckets; F1 sin filtro 17% win/−285%; F1+rr≥6+fuerza≥0.6 19.7%/−15%; el único positivo (fuerza≥1.5)
  son 14 trades (ruido). vs F4 actual: 39% win, +1937%. **El 80% de Mark es su OJO + gestión + 1m, no las reglas.**
- **Conclusión:** la estrategia de Mark (F1) no es auto-operable rentablemente. Camino honesto = bot ASISTENTE
  (detecta F1 → alerta → el usuario aplica criterio/gestión). `enable_f1` sigue OFF en vivo. PENDIENTE decisión
  usuario: F1 como alertas (asistente) / solo F4 auto / ambos.

### Features nuevas testeadas: volumen del sweep (NO) + fuerza del reclaim (SÍ)
- Añadidas a `sweep.py`/`signals.py`/`ml_dataset.py`: `sweep_vol_ratio` (vol vela sweep / media 30) y
  `reclaim_body_atr` (cuerpo de la vela de reclaim / ATR). Build `ml_dataset_feat.csv` (20 coins, 17.101 trades).
- **sweep_vol_ratio (volumen): SIN edge.** corr con pnl +0.006, sin patrón monótono → descartado (como el F1).
- **reclaim_body_atr (fuerza reclaim): CON edge.** Reclaim fuerte (cuerpo 1-2 ATR) → 47.8% winrate vs 28.7% los
  flojos; corr +0.093. Predice calidad → candidato a meter al score / filtro suave. Features quedan en el código.

### Filtro de correlación con BTC (a raíz de la crítica de un experto) — validado
- **Crítica experta:** un F4 long perfecto en una alt falla si BTC se desploma → añadir correlación BTC.
- **Validado con datos** (cruzando cada señal con el movimiento de BTC en 3h, filtro live score≥60 & rr≥6):
  los trades CONTRA-BTC tienen ~22% winrate (vs 34-43% alineados/neutral). Y los contra-BTC con BTC FUERTE
  (|≥1% en 3h|) son los peores: veteranas **0% winrate**, movers negativos.
- **Implementado (bloqueo suave):** no se abre una señal contra-BTC si |BTC 3h| ≥ `cfg.btc_block_pct` (1.0%).
  `config.py`: `btc_block_pct=1.0`. `paper.py`: `btc_recent_move()` (BTC 1h cacheado, % en 3h, fail-open), gate en
  `fresh_accepted_signals` (`[btc-skip]`), cableado por `scan_new_signals`/`run_cycle` (se calcula 1× por ciclo).
- **Efecto:** quita solo ~3% de trades (los peores, contra-BTC fuerte) → en veteranas el retorno SUBE (+644 vs +612),
  en movers ~igual (+1535 vs +1550). Mejora calidad/riesgo con coste mínimo de avisos. En vigor próximo ciclo.
- **Honesto:** confirma al experto en el SENTIDO (contra-BTC es malo) pero su "RR≥6 es demasiado" lo DESMINTIERON
  los datos (nuestro winrate nunca llega al 55%; bajar RR empeora). **Rollback:** `btc_block_pct=0`.

### Watchlist permanente de veteranas (mata la "lateness") — más trades frescos
- **Problema (lateness):** el scanner solo pasa coins DESPUÉS de mover ≥10% → sus mejores setups ya dispararon
  (los `[stale-skip]` lo confirmaron: HOME/UNI con RR 31-61 pero trigger hace 65-184 velas, imposible entrar a tiempo).
  A los movers no hay solución (son tarde por diseño; scanner intocable).
- **Fix:** vigilar continuamente un set fijo de veteranas validadas → el bot está mirándolas ANTES de que se muevan
  → caza sus setups FRESCOS, sin lateness. `paper.py`: `PERSISTENT_WATCHLIST` (14 veteranas top por edge OOS: DOT,
  APT, ADA, AAVE, DOGE, ARB, NEAR, OP, FIL, UNI, ATOM, AVAX, INJ, SOL) se SUMAN a los movers del scanner en
  `resolve_watchlist` (dedup). El scanner NO se toca.
- **Efecto esperado:** más trades/avisos FRESCOS con edge validado (+600% OOS en veteranas). Coste: veteranas son
  menos volátiles (edge/trade menor que movers) pero SIN el problema de llegar tarde. Watchlist ~5 movers + 14 vet = ~19.
- En vigor en el próximo ciclo. **Rollback:** vaciar `PERSISTENT_WATCHLIST` o volver a devolver solo `movers`.

### Cross-validación del motor de backtest (test diferencial) — 100% correcto
- Pregunta: ¿nuestros números de backtest son fiables o el motor casero tiene bug? (en vez de portar a Freqtrade/
  Jesse, que sería un port aproximado por el desajuste vectorizado-vs-ventanas → no validaría limpio).
- **Test diferencial:** re-implementé la lógica de salida (SL/TP/breakeven/stale/timeout) en código INDEPENDIENTE
  y la comparé trade-a-trade con `backtester._simulate_trade` sobre 138 señales reales (5 coins × 2 TF).
- **Resultado: 138/138 coinciden (100%), max discrepancia 0.0000%.** El motor NO tiene bug de implementación.
- Valida el MOTOR (salidas+PnL); no la generación de señales (=estrategia) ni look-ahead (=walk-forward, aparte).
- El motor queda validado por 4 vías: test diferencial + paper que lo replica + walk-forward + Monte Carlo.

### Caché de datos (idea de Freqtrade/Jesse) — adiós a los rate-limits de Bybit
- **Problema:** cada build/ciclo re-descargaba miles de velas → Bybit 10006 (Too many visits) → cuelgues (vet2/MKR).
- **Solución (`data_fetcher.py`):**
  1. `fetch_ohlcv_cached()`: cachea velas a disco (`data_cache/*.parquet`) y en llamadas repetidas solo trae el
     DELTA (velas nuevas desde la última) + overlap para refrescar la última. Velas cerradas = inmutables, seguro.
  2. `_get_exchange()`: reutiliza la instancia del exchange con `load_markets()` cargado UNA vez por proceso
     (antes se llamaba en cada fetch → 40 llamadas API en un build de 40 jobs; ahora 1).
- **Medido:** fetches en caliente **~5× más rápidos** (0.9s/0.5s vs 4.4s/2.6s) y muchísimas menos llamadas API.
- **Cableado:** `ml_dataset.py` (builds) usa la caché por defecto (`--no-cache` para desactivar). `paper.py` también
  (alias `fetch_ohlcv_cached as fetch_ohlcv` → menos rate-limits en las actualizaciones en vivo). `since` explícito
  bypassa la caché (rango puntual). Smoke test OK (paper devuelve velas frescas).
- **Rollback:** en paper.py volver a `from data_fetcher import fetch_ohlcv`; en ml_dataset usar `--no-cache`.

### Robustez Monte Carlo (idea de Jesse) — el edge NO es un espejismo
- Nuevo `montecarlo_robustness.py`: bootstrap (10k resamples) de los trades de la config en vivo (score≥60 & rr≥6
  + tendencia) en los 4 universos. Mide % escenarios positivos, percentiles de retorno, max drawdown y concentración.
- **Resultado:** **100% de los 10.000 escenarios acaban positivos** en los 4 universos. P5 (pesimista) sigue muy
  positivo (+291% a +1102%). → el edge NO depende de la ordenación ni de pocos trades, es REAL y robusto.
- **Caveat de riesgo:** drawdowns altos (DD medio 38-59%, P95 hasta 100% en puntos de retorno acumulado, no ruina)
  + concentración ~50% en el top-5% de trades. Es asimétrica + apalancada → sube mucho con vaivenes profundos.
- Uso: `python montecarlo_robustness.py [--sims N] [--score S] [--rr R]`. (RR del paper se queda en 6 por decisión.)

### Optimización robusta de umbrales con Optuna (anti-sobreajuste) — herramienta nueva
- Instalado `optuna` (4.9.0, vía pip --trusted-host). Nuevo `optimize_thresholds.py`: busca (min_score, min_rr)
  que funcionan en los 4 universos A LA VEZ (movers, veteranas-1/2, jóvenes-8), exigiendo POSITIVO + volumen en
  cada uno → impide el sobreajuste que nos llevó al score-50.
- **Resultado (objetivo robusto = max retorno del peor universo):** óptimo en **score≥60 & rr≥8** — prácticamente
  nuestra config. CONFIRMA que el ajuste a mano era correcto; NO hay config mágica mejor. El RR 6 vs 8 es un dial
  menor: 8 = un pelín más robusto/calidad (veteranas +647 vs +612), 6 = más volumen/avisos. Ambos robustos.
- (Objetivo quality = max net-por-trade → score≥62 & rr≥14: máxima calidad por trade pero mucho menos volumen/total.)
- **Valor real:** herramienta reutilizable para tunear con rigor (no a mano) cada vez que cambie algo. Uso:
  `python optimize_thresholds.py [--objective robust|quality] [--trials N]`.

### F1 re-testeado BIEN (a raíz del ejemplo de Mark) — sigue sin edge, CERRADO
- Mark compartió un trade real (VELVET 1m): Formación 1 pura (2 niveles + consolidación + breakout, SIN sweep),
  ganadora +6.88%. Reabrió la pregunta: ¿el F1 perdía por la estrategia o por mala implementación?
- Re-test riguroso: flag `enable_f1` (config, default False) → crea F1 (2+ niveles + consolidación, sin sweep) en
  `formations.py`. Build sobre 12 movers con tendencia obligatoria. Resultado:
  - **F1 (score≥60 & rr≥6 + tendencia): 29 tr, win 31%, +0.97%/tr, ret −3%** (break-even en el mejor caso).
  - Sweep (F2/F3/F4) mismo filtro: 313 tr, +2.99%/tr, **+1128%**. RR medio F1 4.3 vs sweep 11.3.
  - Sin filtro RR, F1 claramente negativo (win 12-20%, ret −63% a −213%).
- **VEREDICTO: el F1 NO tiene edge mecánico, ni con tendencia + niveles fuertes. El sweep obligatorio era correcto.**
  Mark gana con F1 por CRITERIO discrecional (scalping 1m, lectura de momentum), no por la estructura → no codificable.
- El flag `enable_f1` queda en código APAGADO por defecto (live no afectado). Pregunta del F1 CERRADA con datos.

### Investigación ZEC (fuga de setups) + logging [stale-skip]
- **Caso ZEC:** el scan mostró una ZEC 15m short (RR 16) "abierta" que el paper NO tomó. Investigado: ZEC 15m tiene
  4 shorts score 71, RR 12.7-29.8, TODAS pasan score≥60&rr≥6 y alineadas con tendencia (-10.4%) — setups
  excelentes. Pero ninguna era FRESCA al evaluarse (la más reciente disparó hace 16 velas/4h).
- **Causa raíz (estructural, no bug):** el bot solo vigila monedas DESPUÉS de que han movido ≥10% (criterio del
  scanner, intocable). ZEC formó sus setups MIENTRAS caía; cuando entró en la watchlist (ya −10%), sus setups eran
  viejos (>fresh). Ensanchar `--fresh` NO se hace: entraría a precios de hace horas que ya no existen (falsearía
  resultados). Es la lateness intrínseca de perseguir movers — Mark no la tiene porque vigila coins ANTES de explotar.
- **Logging añadido (`paper.py`):** nuevo `[stale-skip]` — cuando se descarta una señal que SÍ pasaría el filtro
  (score+rr+tendencia) solo por no ser fresca, se loguea con cuántas velas hace que disparó. Da visibilidad en vivo
  de cuántos setups buenos se escapan por llegar tarde. Verificado que importa.
- **Rollback:** quitar el bloque `[stale-skip]` en `fresh_accepted_signals`.

### Score revertido a 60 (decisión del usuario, por robustez)
- El score-50 demostró ser FRÁGIL (solo positivo en movers originales, negativo en vet1/vet2/jóvenes-8). Vuelta a
  **score≥60** (robusto en los 4 universos). Launcher `run_tfz_paper.cmd`: `--min-score 60` (era 50).
- Config LIVE final del paper: **filtro profit, score≥60, RR≥6, tendencia obligatoria, detección de sweeps aflojada
  (6 velas/3%)**. Todo validado. RR≥6 y sweeps-aflojados son las mejoras robustas que SÍ mantenemos del proceso.
- Rollback: `--min-score 50` (no recomendado).

### Detección de sweeps aflojada (validado: más entradas Y mejor calidad)
- **Investigación contrastada (fuentes externas):** el breakout puro (F1) en 5m/15m falla 55-80% (estudio 50k ORB +
  consenso SMC/ICT) → NO recuperar F1, sería re-añadir perdedores. El edge está en el SWEEP (entrar tras el fakeout).
  Fuentes también dicen que un sweep real puede ser más profundo y durar varias velas (no solo 1-3) → la detección
  del bot (3 velas / 1.5%) podía ser demasiado estricta.
- **Test controlado (misma data, 12 movers, tight vs loose, ambos con tendencia):**
  - TIGHT (3 velas/1.5%): 298 tr, win 32.2%, +2.50%/tr, +991%.
  - **LOOSE (6 velas/3%): 310 tr, win 37.1%, +3.03%/tr, +1196%** → gana en TODO (más señales +10%, más acierto,
    más pnl/tr, más retorno). La detección estricta SÍ se perdía sweeps válidos y buenos.
- **Cambio (`config.py`):** `max_sweep_candles` 3→6, `reclaim_window` 3→6, `max_sweep_depth` 1.5→3.0 (base y en
  TIMEFRAME_PARAMS 5m/15m). Verificado que importa. En vigor en el próximo ciclo del paper.
- **Honesto:** es una mejora REAL y validada (no una apuesta como el score-50), pero el aumento de frecuencia es
  MODESTO (+10% señales) — no lleva solo a las 3-4/día de Mark. La baja frecuencia es en gran parte intrínseca
  (sistema mecánico riguroso + watchlist de ~10 monedas + PC apagado de noche).
- **Rollback:** `max_sweep_candles`/`reclaim_window` a 3, `max_sweep_depth` a 1.5 (base + TIMEFRAME_PARAMS 5m/15m).

### Jóvenes-8 + HALLAZGO CRÍTICO: el score-50 NO generaliza (bandera roja)
- Build `ml_dataset_new8.csv` sobre 8 monedas jóvenes nuevas (PYTH, ENA, TAO, HYPE, STRK, ETHFI, ZRO, EIGEN),
  11 meses (ago-2025→jun-2026), 11.309 trades. Sin cuelgues.
- **Filtro estricto (score≥60 & rr≥8):** 346 tr, win 40.2%, +2.32%/tr, **+1153%** → el edge se confirma en el
  4º universo. Resumen estricto: Movers +1515% / Vet1 +647% / Vet2 +636% / Jóvenes-8 +1153%. MUY robusto.
- **PERO el score-50 (config que se puso en vivo) NO generaliza:** score≥50 & rr≥6 → Movers +1398% ✅, Vet1 −8122%,
  Vet2 negativo, **Jóvenes-8 −2307%** ❌. SOLO fue positivo en el set original de movers → probablemente
  SOBREAJUSTADO a esas monedas. Edge neto de slippage demasiado fino (+0.16%/tr en jóvenes, ~0 en veteranas) vs
  movers (+0.57%). **El score-50 es FRÁGIL.** Recomendación: volver a score 60 (robusto en los 4 universos) aunque
  baje la frecuencia. PENDIENTE decisión del usuario (revertir a 60 o mantener 50 como apuesta).
- Paper REACTIVADO (score 50 de momento, a la espera de la decisión). Monitoreo del build (cada 7 min) finalizado.

### Veteranas-2 (otro set de 20 establecidas) — el edge se CONFIRMA de nuevo
- Build `ml_dataset_older2.csv` sobre TRX, XLM, ETC, BCH, ALGO, HBAR, VET, MANA, SAND, AXS, GALA, CHZ, THETA, RUNE,
  GRT, CRV (16 monedas; EOS sin perp, MKR/SNX/COMP se cayeron por un cuelgue de rate-limit de Bybit, maté el proceso
  y usé el parcial: 16.967 trades). ~7 meses, perps, con fix de tendencia.
- **score≥60 & rr≥8:** 307 tr, win 42%, +1.75%/tr, **+636%** creíble → casi idéntico a vet1 (+647%). DOS sets
  independientes de veteranas ~+640% → consistencia muy fuerte, el edge generaliza.
- **HALLAZGO IMPORTANTE:** con la config LIVE actual (score≥50 & rr≥6) estas veteranas dan **−8122%** (negativo):
  su +0.51%/trade está por DEBAJO del slippage 0.5% → se lo come. **Confirma que el score-50 SOLO vale en movers
  volátiles** (donde da +1398%), NO en monedas tranquilas. El paper en vivo usa movers, así que el score-50 sigue
  bien, pero ese aflojado es específico de alta volatilidad, no universal.
- Lanzado a continuación un 3er build sobre 8 monedas jóvenes nuevas (PYTH, ENA, TAO, HYPE, STRK, ETHFI, ZRO,
  EIGEN), 10 meses (`--candles 30000`), `ml_dataset_new8.csv`.

## 2026-06-17

### Aflojado el score del paper: 60 → 50 (movers sobre-filtrados)
- **Hallazgo:** el filtro score≥60 corta el 92% de las señales y, en MOVERS (universo del paper), corta entradas
  RENTABLES. Datos (RR≥6 + tendencia, retorno creíble apuesta fija 10x −0.5%/tr):
  - Movers score≥60: 453 tr / +2.90%/tr / +1550%. score≥50: 4.125 tr (~9×) / +1.07%/tr / +1398% (sigue rentable).
    score≥45: +2088%, score≥40: +2500%. En movers el listón 60 es DEMASIADO alto.
  - OJO: en VETERANAS bajar el score NO funciona (movimientos pequeños → el slippage se los come, retorno negativo
    por debajo de 60). El 50 vale para movers (volátiles), no para monedas tranquilas.
- **Motivo práctico:** el paper daba ~1 trade/día (Mark da 3-4/día con el mismo método) → score 50 da ~9× más
  señales en los movers → frecuencia tipo Mark + datos en vivo mucho más rápidos.
- **Cambio:** `run_tfz_paper.cmd` ahora `--min-score 50` (antes 60). RR≥6 y tendencia se mantienen. Aplica cuando se
  reactive el paper (estaba pausado por un build pesado de veteranas-2).
- **⚠️ Backtest, no confirmado en vivo** (paper iba 0W/9L). Más trades = sabremos antes si el edge es real en vivo.
- **Rollback:** volver a `--min-score 60`.

### Aflojado el filtro: RR mínimo 8 → 6 (más datos en vivo sin perder edge)
- **Motivo:** el paper post-fix daba ~1 trade/10h (funnel demasiado estrecho) → validación en vivo lentísima.
- **Decidido con datos** (movers + veteranas, score≥60 + tendencia OK, retorno creíble apuesta fija 10x −0.5%/tr):
  - RR≥8: movers 323 tr/+1515%, veteranas 329 tr/+647%.
  - **RR≥6 (elegido):** movers 453 tr (+40%)/+1550%, veteranas 542 tr (+65%)/+612% — más volumen, edge intacto.
  - RR≥5: ya erosiona (veteranas +528%, −18%); descartado.
- **Cambio:** `C:\Users\jarta\run_tfz_paper.cmd` ahora pasa `--min-rr 6` (antes 8). El resto igual (filtro profit,
  score≥60, tendencia). En vigor en el próximo ciclo del paper.
- **Rollback:** volver a `--min-rr 8` en el launcher.

### Validación OOS sobre monedas VETERANAS — el edge GENERALIZA
- Backtest nuevo sobre 20 monedas establecidas y activas (BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, LTC,
  ATOM, NEAR, UNI, AAVE, FIL, APT, ARB, OP, INJ, DOGE), perps, ~7 meses, CON el fix de tendencia.
  Dataset `ml_dataset_older.csv` (22.095 trades). Mismos parámetros del filtro profit (score≥60 & rr≥8), SIN retocar.
- **Resultado:** 329 trades, win 39.5%, +1.71%/trade, retorno creíble **+647%** (−0.5%/tr) / +826% (−0.3%) / +1095%.
  **7/7 meses positivos**, **19/20 monedas positivas** (solo LTC neg con 2 trades).
- **Comparación con movers:** veteranas +1.71%/tr (39.5% win) vs movers +3.63%/tr (35.3% win). Menos edge por trade
  (menos volatilidad) pero más fiable. **El edge NO es solo de los movers** → es real y general, sin sobreajuste
  (parámetros de los movers aplicados a universo nuevo y aguanta). El fix de tendencia también queda validado aquí.

### FIX CLAVE: F4 ya respeta la tendencia (se quita la exención contra-tendencia)
- **Problema (detectado por el usuario):** el bot dio un LONG en BEAT en plena CAÍDA (entry 2.604, precio se fue a
  1.88) — contra-tendencia, violando la regla base de la metodología (tendencia alcista→long, bajista→short).
  Causa: habíamos dado a **F4_manipulation una EXENCIÓN** de la alineación con tendencia (la tratábamos como
  reversión). NO era un cambio de estrategia arreglarlo — era un BUG: la estrategia siempre fue seguir tendencia.
- **Validado con datos (ml_dataset_7m, movers):** bajo el filtro profit, F4 alineadas 36.5% win / +3.69%/trade vs
  contra-tendencia 19.6% win / +0.49%. El bucket contra-tendencia PIERDE en conjunto (−102% retorno creíble).
  Regla nueva (bloquear contra-tend si |trend|≥5%): **495→323 trades, +1413%→+1515%**, win 35.3%, +3.63%/trade
  (más retorno, menos trades, menos slippage). Probablemente explica la racha 0W/8L del paper (eran contra-tend).
- **Cambios de código:**
  - `config.py`: nuevo `trend_block_pct: float = 5.0` (umbral de tendencia "clara").
  - `signals.py` `generate_signals`: BLOQUEO DURO — si `|trend_strength| >= trend_block_pct` y la señal es
    contra-tendencia (long con trend<0 o short con trend>0), se descarta. Aplica a TODAS las formaciones, incl. F4.
    Mercado lateral (|trend|<5) permite ambas direcciones.
  - `signals.py` `_compute_score`: quitada la rama especial de F4; ahora TODAS las formaciones puntúan tendencia
    igual (aligned→magnitud, counter≥5→0, lateral→5).
- **Efecto:** entra en vigor en el próximo ciclo del paper (la tarea importa fresco). El filtro profit sigue igual
  (score≥60 & rr≥8) pero ahora con la puerta de tendencia delante.
- **Rollback:** quitar el bloque "Trend gate" en `generate_signals`, restaurar la rama `if formation.type ==
  "F4_manipulation": trend_score = _magnitude_score(abs_trend)` en `_compute_score`, y borrar `trend_block_pct`.
### TP investigado — RESUELTO sin cambios (NO es un problema)
- Sospecha: el TP sin tope (`_compute_tp` coge el nivel más lejano) daba RR "fantasía" (BEAT a +62%) → pensábamos
  que inflaba el RR sin que las ganadoras llegaran al objetivo.
- **Datos lo desmienten** (filtro profit + nueva regla de tendencia, n=323): distancia TP mediana **+11.3%** (el +62%
  de BEAT era el MÁXIMO, un outlier). Las ganadoras **capturan el 77% del TP** y el **70% casi llegan (≥90%)** → el
  TP SÍ se cumple en monedas volátiles, no es fantasía. RR alto = más pnl: RR 40+ da **+9.52%/trade** (el mejor
  bucket). Correlación rr↔pnl +0.22. **Capar el TP cortaría las mejores → haría daño.**
- **DECISIÓN: no tocar el TP.** El problema del BEAT era TENDENCIA (ya arreglado), no el TP. Hilo cerrado.

## 2026-06-16

### Migración a GitHub Actions 24/7 — EXPLORADA y DESCARTADA (código revertido)
- Objetivo: correr el paper 24/7 sin el PC encendido. GitHub Actions es la única opción gratis sin tarjeta.
- Se adaptó la capa de datos (env vars `TFZ_DATA_EXCHANGE=mexc`, `TFZ_TICKER_URL`, `TFZ_MOVERS_SOURCE=mexc`,
  `TFZ_MIN_VOLUME_USD`) porque los runners de GitHub (EE.UU.) geo-bloquean Bybit y Binance fapi.
- **Velas vía MEXC:** ✅ funciona. **Scan de movers:** el problema. El espejo Binance spot solo da 1 mover
  (muchas monedas son nuevas/solo-futuros); el endpoint crudo de MEXC (`contract.mexc.com/.../contract/ticker`)
  sí da datos completos PERO MEXC mueve mucho menos volumen → su universo de movers es **distinto y más fino**
  que el de Binance (umbral ~3M vs 100M, ~6 movers vs 11, monedas diferentes, mucha menos liquidez).
- **DECISIÓN del usuario (2026-06-16):** NO migrar — no compensa que el bot de GitHub analice un universo MEXC
  distinto del Binance validado. Seguir en el PC. **Todos los cambios de código revertidos** (`data_fetcher.py`,
  `scanner_bridge.py` restaurados a su estado previo; verificado que importan y mantienen Binance fapi + 100M).

### Bybit testnet elegido como venue de VALIDACIÓN (no-KYC, cobertura total)
- Binance testnet descartado: desde ago-2025 el testnet web (login GitHub, sin-KYC) fue retirado; ahora sacar
  claves de testnet pasa por cuenta Binance con KYC. El usuario NO quiere KYC (no operará en Binance, era solo testnet).
- **Bybit testnet VERIFICADO:** alcanzable desde el PC (el bloqueo 10024 era cuenta real/mainnet, el testnet es otro
  sistema), 680 perps, **11/11 movers del scanner listados** (cobertura total), ccxt sandbox ✅, SIN KYC (registro
  aparte en testnet.bybit.com con email). Además bybit ya es el exchange por defecto del bot y el formato de SL/TP
  actual es el nativo de Bybit → probablemente sin fixes de plumbing.
- Variables que necesita el usuario: `BYBIT_TESTNET_API_KEY`, `BYBIT_TESTNET_API_SECRET`.
- **BLOQUEADO (2026-06-16):** aunque la API del testnet es alcanzable y la cuenta testnet se crea, Bybit **NO deja
  crear claves API de trading** desde la región del usuario ("Creating an API Key for this purpose is not supported
  on the current site"), ni con No-IP ni con IP fija. Es la MISMA restricción regional que el 10024 de mainnet.
  → Bybit descartado por completo (mainnet y testnet).
- **CONCLUSIÓN del rastreo de venues:** no existe un testnet con (a) los movers pequeños del scanner + (b) sin KYC +
  (c) accesible desde la región del usuario. Los movers viven en CEX grandes (Binance/Bybit/MEXC: KYC o bloqueo
  regional); los venues no-KYC (Hyperliquid y demás DEX) solo listan majors. Lo ya validado: mecánica de ejecución
  en Hyperliquid + estrategia en paper. Para ejecutar los movers en real haría falta KYC en un CEX que acepte la
  región (NO Bybit). Decisión aparcada; de momento la validación se apoya en el paper trading.

### Preparación Binance Futures testnet (terreno listo, falta claves del usuario)
- **FIX (`execution.py` `exchange()`):** cuando `exchange=="binance"` se usa la clase ccxt **`binanceusdm`**
  (USD-M futuros), no `ccxt.binance` (que va a spot y mis-rutea el testnet de futuros). El nombre de cara al
  usuario y las env vars siguen siendo "BINANCE".
- **Variables de entorno que necesita el usuario (testnet):** `BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_API_SECRET`
  (se crean en testnet.binancefuture.com, login GitHub/Google, SIN KYC).
- **Dry-run validado SIN claves:** `trade --exchange binance --filter profit` → construyó binanceusdm sandbox,
  escaneó movers, simuló 3 órdenes (EVAA short, BEAT long, SOXL short) con sizing + SL/TP correctos.
- **PENDIENTE (requiere claves testnet):** `--check` (leer equity) y primer envío real a testnet; probablemente
  haya que ajustar el plumbing de SL/TP específico de Binance (como pasó con Hyperliquid).
- **Nota:** los datos OHLCV aún vienen de Bybit (data_fetcher por defecto); el venue de ejecución es Binance.
  Opcional a futuro: leer datos de Binance para coherencia total.
- **Rollback:** revertir el mapeo `binanceusdm` en `exchange()` (volver a `getattr(ccxt, self.cfg.exchange)`).

### Investigación de venues de ejecución (sin cambios de código)
- Comparativa verificada de cobertura de los movers del scanner y disponibilidad de testnet:
  - **Hyperliquid:** 225 perps, testnet API ✅, pero solo 1/10 movers (WLD) tanto en testnet como mainnet.
  - **MEXC:** 897 perps, 9/10 movers en mainnet, ccxt `createOrder:True` PERO **NO hay testnet de API**
    (el demo es solo web) y requiere KYC; API de futuros nueva (31-mar-2026), soporte ccxt menos probado.
  - **Binance Futures (ccxt `binanceusdm`):** 788 perps mainnet (10/10 movers), **701 perps testnet (9/10
    movers, falta SOXL)**, testnet API ✅ sin KYC, ccxt maduro. Es la fuente del scanner → cobertura total.
    Conexión OK desde el PC del usuario con el parche `verify=False` (el 451 previo era solo runners EE.UU.).
- **DECISIÓN propuesta:** Binance Futures testnet es el mejor escalón de validación (dinero falso + cobertura
  real de monedas + ccxt estable). MEXC queda como posible venue de mainnet real más adelante. PENDIENTE OK usuario.

### Mecánica de ejecución VALIDADA en Hyperliquid testnet (+ 2 bugs corregidos)
- Test directo (script temporal, ya borrado): construir señal WLD → `place()` → verificar posición + SL/TP → cerrar.
- **RESULTADO: round-trip completo OK** — entrada market colocada (order id real), posición abierta (WLD long
  508 contratos, ~333 notional), **SL y TP adjuntos correctamente** (trigger 0.6357 / 0.7209, reduceOnly), y cierre/flatten OK. Equity 999→999.37, 0 posiciones al final.
- **BUG 1 corregido (`execution.py` `place()`):** ccxt hyperliquid exige `price` en órdenes market (limit-marketable,
  para el bound de slippage). Bybit lo ignora. FIX: `price_arg = signal.entry_price if self._is_hl() else None`,
  pasado como 5º posicional a `create_order`.
- **BUG 2 corregido (`execution.py` `place()`):** el formato Bybit de SL/TP (`stopLoss`/`takeProfit` = float) revienta
  en hyperliquid (lo trata como limit sin precio → `price_to_precision(None)`). FIX: para hyperliquid pasar dicts
  `{"triggerPrice": x, "type": "market"}`; para bybit, el float de antes (rama por `self._is_hl()`).
- **Limitación conocida (no bloqueante):** el executor no tiene método de cierre/flatten propio; el bot sale por
  los SL/TP adjuntos (estáticos, los gestiona el exchange). Un cierre market manual en hyperliquid también
  necesitaría el `price` arg. `cancelAllOrders` no está soportado por ccxt hyperliquid (usar `cancel_order` por id;
  además al cerrar la posición los SL/TP reduceOnly se auto-cancelan).
- **Rollback de los fixes:** revertir las dos ramas `self._is_hl()` en `place()` (volver a `create_order(..., params={stopLoss:float, takeProfit:float})` sin price). Romperá hyperliquid pero restaura el comportamiento Bybit exacto.

### Ejecución en Hyperliquid testnet — conexión establecida
- **Variables de entorno (usuario, vía `setx`):**
  - `HYPERLIQUID_WALLET_ADDRESS` = dirección de la cuenta principal (la de los ~1000 USDC de testnet).
  - `HYPERLIQUID_PRIVATE_KEY` = clave privada de la **agent/API wallet** (solo opera, no retira).
- **Verificado:** `python main.py trade --exchange hyperliquid --check` → `TESTNET (sandbox) OK - equity 999 USDC, 0 posiciones`.
- Código de Hyperliquid en `execution.py` (ya existente de 2026-06-15): `_is_hl()`, `_keys()`,
  `exchange()` (ccxt.hyperliquid con walletAddress+privateKey, `set_sandbox_mode(True)`),
  `to_venue_symbol()` (BASE/USDT:USDT → BASE/USDC:USDC), `get_equity()` lee USDC.
- **Profit filter cableado en ejecución (hecho):** `execution.py` → `run_execution_cycle(...)` nuevos
  params `filter_mode/min_score/min_rr` (pasados a `fresh_accepted_signals`); imprime el filtro activo.
  `main.py` comando `trade`: flags `--filter {ml,profit}` (default ml), `--min-score` (60), `--min-rr` (8).
- **Dry-run verificado:** `python main.py trade --exchange hyperliquid --filter profit --min-score 60 --min-rr 8`
  → DRY-RUN OK, encontró SOXL short, mapeo `/USDT:USDT`→`/USDC:USDC`, sizing 1% riesgo correcto, NO envió nada.
- **Primer envío a testnet probado (2026-06-16):** `--live-testnet --filter profit --leverage 10` →
  conectó OK, encontró señal SOXL, pero la rechazó correctamente: `SOXL/USDC:USDC no cotiza en hyperliquid`.
- **HALLAZGO estratégico:** Hyperliquid testnet lista solo **225 perps** (majors: SOL/BTC/ETH/BNB/AVAX/OP/DYDX...);
  de los 9 movers del scanner SOLO **WLD** está listado (BSB/EVAA/BEAT/VELVET/LAB/SPCX/SOXL y hasta UNI fuera).
  El edge de la estrategia está en movers pequeños que viven en Binance/Bybit/MEXC, NO en Hyperliquid →
  Hyperliquid puede NO ser el venue adecuado para esta estrategia. PENDIENTE DE DECISIÓN del usuario.
- **Rollback:** quitar `--filter profit ...` (default vuelve a ML); borrar las dos variables de entorno.

### Filtro de aceptación: ML → PROFIT-ALIGNED (cambio importante)
- **Motivo:** investigación sobre `ml_dataset_7m.csv` demostró que el ML (clasificador de
  `win`=pnl>0, o sea TASA DE ACIERTO) **tira las señales más rentables**. La estrategia gana por
  ASIMETRÍA (pocas ganadoras enormes, RR alto), no por acierto. Los F4-short de RR≥12 ganan solo
  28% de las veces pero son el bucket MÁS rentable (+1.10%/trade). Filtrar por P(win) elimina el edge.
- **Cifras creíbles (apuesta fija 1%, tope 10x, neto −0.5%/tr slippage, 6 meses):**
  ML 0.50 → +801% | ML 0.40 → +1445% | **score≥50 & RR≥8 → +2050%** | score≥60 & RR≥8 → +1413% (solo 495 trades, +2.55%/tr, el más eficiente).
- **Cambios de código:**
  - `paper.py` → `fresh_accepted_signals(...)`: nuevos params `filter_mode="ml"`, `min_score=60.0`, `min_rr=8.0`.
    En modo `"profit"` la entrada se acepta si `total_score >= min_score AND rr_ratio >= min_rr`.
    El ML se sigue calculando y registrando en `live_log.csv` pero NO decide.
  - `paper.py` → `scan_new_signals(...)` y `run_cycle(...)`: propagan `filter_mode/min_score/min_rr`.
    `run_cycle` imprime `PROFIT gate score>=X & rr>=Y` cuando aplica.
  - `main.py` → comando `paper`: nuevos flags `--filter {ml,profit}` (default `ml`), `--min-score` (60), `--min-rr` (8); pasados a `run_cycle`.
  - `C:\Users\jarta\run_tfz_paper.cmd` (launcher de la tarea programada): ahora usa
    `--filter profit --min-score 60 --min-rr 8` en vez de `--ml-cutoff`.
- **Verificado:** ciclo real con `PROFIT gate score>=60 & rr>=8`, corre limpio.
- **⚠️ Aviso de honestidad:** el filtro score+RR se eligió viendo ya los resultados (riesgo de
  sobreajuste, NO validado rolling/OOS como sí el ML). Su credibilidad viene de la lógica causal,
  hay que CONFIRMARLO forward en paper. Mejora futura: reentrenar el ML como REGRESOR de pnl esperado.
- **Rollback:** en el launcher, volver a `--ml-cutoff 0.55` (o 0.50) y quitar `--filter profit ...`.
  El código nuevo es retrocompatible (default `filter_mode="ml"`).

### Gate ML del paper: 0.50 → 0.40 (revertido luego por el cambio anterior)
- Bajado en el launcher para intentar que el paper abriera trades (con 0.50 llevaba 2 días en 0).
- Sustituido el mismo día por el filtro profit (arriba), porque las señales en vivo puntuaban ML <0.30 y ni a 0.40 entraban.

### Análisis (sin cambios de código)
- Walk-forward rolling limpio (`walkforward_rolling.py`) reproducido: 6 meses todos positivos,
  802 trades a ML 0.50 (47.9% WR, +1.59%/tr), cifra creíble +801% a +1366%.
- Investigación del sesgo del ML (ver "Filtro PROFIT" arriba).

---

## 2026-06-15

### Avisos Telegram (configurado y verificado)
- `notify.py`: `send_telegram`/`alert_entry` (urllib + INSECURE_SSL, lee `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, fail-silent).
- Cableado en `paper.scan_new_signals`: al abrir trade fresco aprobado, manda alerta con entry/SL/TP.
- Credenciales por `setx` (variables permanentes de usuario); la tarea programada las hereda.

### Tarea programada Windows `TFZ_Paper`
- Lanzador en ruta SIN espacios: `C:\Users\jarta\run_tfz_paper.cmd` (las espacios en "Krasnov Trading Course" rompían el Programador → error 0x80070002).
- Frecuencia: cada 5 min (antes 15). Necesita PC encendido + sesión iniciada.
- GOTCHA: desactivar `TFZ_Paper` (`schtasks /Change /TN TFZ_Paper /DISABLE`) antes de runs pesados de datos; reactivar después.

### Adaptación de `execution.py` a Hyperliquid
- Soporte multi-exchange en la capa de ejecución (bybit/binance/hyperliquid) — ver detalle en la entrada de 2026-06-16.

### Despliegue 24/7 — DECISIÓN: seguir en el PC
- GitHub Actions DESCARTADO (runners EE.UU.: Bybit 403, Binance 451 geo-bloqueo). MEXC y otros SÍ funcionan desde allí, pero el usuario no quiere pagar VPS ni dejar el 24/7 hasta automatizar ejecución real.

---

## 2026-06-14

### Fase 2 — Filtro ML de calidad de señal (COMPLETADA)
- `ml_dataset.py` (genera dataset etiquetado), `ml_train.py` (split temporal, guarda `ml_model.joblib`),
  `ml_filter.py` (puntúa señales en vivo, fail-open).
- Integrado en `paper.py` (flags `--ml-cutoff`, `--no-ml`). Config producción de entonces: `score≥60 & p≥0.55`.
- NOTA: este filtro es el que el 2026-06-16 se descubrió desalineado con el beneficio y se sustituyó por el profit-aligned en el paper.

### Integración con el scanner del usuario
- `scanner_bridge.py`: importa la lógica del selector externo (`C:\Users\jarta\Desktop\binance-volume-scanner\scanner.py`)
  o usa copia interna; convierte movers a perps ccxt (`BASEUSDT` → `BASE/USDT:USDT`).
- El paper usa el scanner como watchlist por defecto (`run_cycle(watchlist_source="scanner")`, flag `--watchlist`).

### Capa de ejecución (MVP testnet-first)
- `execution.py` (`Executor` + `run_execution_cycle`) y comando `python main.py trade`.
- SEGURO POR DEFECTO: `testnet=True`, `dry_run=True`. Reutiliza `paper.fresh_accepted_signals`.
- Sizing por riesgo (% equity / distancia SL) capado al poder de compra. Coloca entry market + SL/TP.
- Kill-switch de pérdida diaria (equity-based, persiste en `execution_state.json`, límite 5%).

### Tendencia real + recalibración de umbral
- `compute_trend_strength` (swings.py): % de movimiento con signo sobre ~1 día (antes era 10 hardcodeado).
- Scoring de tendencia direccional en `signals.py` (continuaciones solo a favor; F4 exento).
- `config.py`: `score_minimo` 70→**60**, `bear_score_minimo` 75→**65** (pico de expectancy OOS+IS en 60).

### Confirmación final del motor
- Run de 87 símbolos a umbral 60: expectancy neta OOS +0.858% / IS +0.791%, WR ~39.5%, 91.5% símbolos rentables OOS.
- Fase motor+validación CERRADA: edge real, robusto OOS, neto de costes.

---

## 2026-06-13

### Bug crítico del fetcher (corregido)
- `data_fetcher.fetch_ohlcv` paginaba hacia atrás y abortaba con `len(candles) < batch_size`
  (bybit devuelve 999 → abortaba en la 1ª iteración). TODOS los backtests previos corrieron sobre ~999 velas, no 10k.
- Reescrito a paginación hacia adelante con terminación por timestamp. Timeout 10s/20s por request.

### Tuning de formaciones — sweep obligatorio
- Se exige sweep para TODA formación F1/F2/F3 (antes solo F4). Sin sweep daban WR ~10% y PnL negativo.
  F3 pasó de −18% a +20%. Consecuencia: la F1 "pura" del PDF (sin sweep) ya no genera trade.

### Validación out-of-sample
- `validate_oos.py`: parte 20k velas/símbolo en mitad antigua (OOS) vs reciente (IS). Edge real, no sobreajustado.
- Costes en `backtester.run_backtest`: 0.20% ida y vuelta (`commission_pct` 0.075 + `slippage_pct` 0.025).

---

## Origen del proyecto

Bot de señales y backtesting TFZ v1 en `Downloads/Krasnov Trading Course/tfz-bot/`, motor
determinista basado en la metodología del PDF "Trading From Zero" (Krasnov). Especificación
completa en `TFZ_SPEC_v1.md`. Usa CCXT (Bybit por defecto), requiere `INSECURE_SSL=1` en este PC.
BD SQLite en `tfz_data.db`. La SELECCIÓN de monedas la hace un bot scanner externo; el motor TFZ
solo CONSUME esa lista y aplica la metodología.
