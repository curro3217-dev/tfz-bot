# Plantilla: backtestear cualquier estrategia en ~20 minutos

Adaptación del bucle de la chuleta **"The Backtest Machine"** (Miles Deutscher) a las
herramientas de la casa. El bucle es siempre el mismo: **articular → codificar →
correr → leer**. Vale para estrategias de un libro, un vídeo de YouTube o de tu cabeza.

Hay dos caminos; los prompts de abajo sirven para los dos.

## Camino A — Con el bot (recomendado: datos MEXC reales, comparaciones limpias)

1. Copia `plantilla_backtest.py` a `bt_<nombre>.py` (el prefijo `bt_` no se sube al repo
   si añades la regla; los `_*.py` ya están ignorados).
2. Pídele a Claude que rellene el bloque ESTRATEGIA con los prompts de abajo.
3. `INSECURE_SSL=1 python bt_<nombre>.py` — saca meseta, IS/OOS y buy&hold de una vez.

## Camino B — Con TradingView (visual, sin tocar el bot)

Igual que el vídeo: prompt 2 pide Pine Script v6, pegar en el Pine Editor,
Strategy Tester, y el resumen de resultados de vuelta a Claude (prompt 3).

## Los 4 prompts (copiar y pegar, editar los corchetes)

**1 — ARTICULAR** (una idea difusa debe volverse reglas objetivas):

> Coge [describe tu estrategia en una frase] y conviértela en reglas 100% objetivas
> para [ACTIVO] en el marco temporal de [TIMEFRAME]. Dame: regla exacta de entrada,
> regla exacta de salida, lógica de stop y tamaño de posición. Sin discreción:
> toda regla tiene que ser computable.

**2 — CODIFICAR** (mismo chat, un mensaje más):

> Camino A: "Ahora escribe esto como función `position(df)` para mi
> plantilla_backtest.py (posición deseada tras cada cierre: +1/0/-1, solo
> información causal), con un PARAM_GRID de parámetros vecinos para la meseta."
>
> Camino B: "Ahora escríbelo como estrategia en Pine Script v6 para TradingView.
> Incluye comisión del 0,1% por lado, fills en la apertura de la vela siguiente y
> 100.000$ de capital inicial. Listo para pegar en el Pine Editor."

**3 — LEER EL VEREDICTO**:

> Aquí están los resultados del backtest: [pega el resumen]. Explícame qué dicen
> el win rate, el profit factor y el max drawdown, y dame un veredicto honesto:
> ¿esta estrategia es para operarla, para arreglarla o para la basura?

**4 — MEJORAR (con honestidad)**:

> Sugiere la mejora más prometedora para esta estrategia, pruébala y dime
> honestamente si de verdad mejoró los resultados.

## La batería de la casa (lo que un backtest tiene que pasar ANTES de creérselo)

Lecciones de la chuleta + las nuestras (ver `programa-investigacion-edges`):

1. **n ≥ 20 trades** o es una anécdota, no evidencia.
2. **Meseta, no pico**: los parámetros vecinos tienen que dar parecido (la plantilla
   lo hace sola con PARAM_GRID). Si solo funciona 9/21 y fallan 8/20 y 10/22, es
   sobreajuste.
3. **IS vs OOS**: si solo gana en uno de los dos periodos, es régimen, no edge
   (la plantilla parte el último año como OOS).
4. **Activo y timeframe importan**: la misma regla ganó en BTC y perdió contra el
   buy&hold en el Nasdaq; Supertrend perdía en el diario y ganaba en el semanal.
   Nunca heredar un backtest de otro mercado/timeframe.
5. **Costes y funding**: la plantilla mete 0,09% ida+vuelta (modelo MEXC); el
   funding de perps NO está modelado — con holds largos puede pesar.
6. **Deriva incondicional**: comparar siempre contra buy&hold del mismo rango
   (la plantilla lo imprime); ganar menos que no hacer nada no es edge.
7. **El veredicto final es el forward test** (paper primero). Un backtest es un
   veredicto sobre el pasado, no una promesa sobre el futuro.

## Si sobrevive a todo

El siguiente paso es una medición forward tipo `weekend_paper.py` /
`ema_cross_paper.py`: BD propia, pre-registro sellado, forward-only, idempotente,
cuenta doble PC + GitHub. Y solo mucho después: testnet → real pequeño, con clave
API solo-trading y tope de capital (escalera del PDF: paper → testnet → live).
