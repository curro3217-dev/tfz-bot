# LECCIONES.md — lo que los datos nos han enseñado

Archivo de "memoria de aprendizaje" del proyecto (idea del artículo TradingBotV2,
adaptada). Regla de la casa: **aquí solo entran lecciones respaldadas por datos
reales** — nada de intuiciones, nada de lecciones inventadas. Cada una lleva fecha
y de dónde salió (detalle completo en CHANGELOG.md). Leer ANTES de diseñar
cualquier experimento nuevo.

---

1. **Los backtests bonitos se verifican antes de creerlos.** (2026-07-03)
   El primer edge del bot (+0,86%/trade) era un error de "mirar el futuro"
   (look-ahead). Al arreglarlo, desapareció. → Toda cifra buena se audita.

2. **Las muestras pequeñas mienten.** (2026-07-16)
   El micro_pullback en 1h llevaba 56% de aciertos con 16 trades ("la brasa").
   Con 384 trades: pérdida de −0,4%/trade con certeza estadística. Retirado.

3. **El criterio se sella ANTES de medir, y se obedece.** (2026-07-16)
   El kill-switch pre-registrado del micro_pullback funcionó: no cumplió el
   listón → fuera, sin re-ajustar parámetros ni "aflojar para tener señales".

4. **Un régimen no es un edge.** (2026-07-03)
   El momentum de fin de semana nació en 2022 (antes no existía; en 2020 era
   negativo). Puede morir como nació. Lo famoso pre-2024 murió con los ETFs.

5. **Las estrategias de tendencia solo viven si hay tendencia.** (2026-07-15)
   7 clásicas probadas (EMA, Ichimoku, MACD, Donchian, cruce dorado, Supertrend,
   EMA en ETH): en el último año SIN tendencias, pierden TODAS. No es la
   estrategia, es el mercado.

6. **La mayoría de "mejoras" no mejoran.** (2026-07-15)
   4 filtros anti-amago probados sobre el EMA 9/21: ninguno arregla el año malo
   y todos recortan el resultado total. Parchear el pasado no compra el futuro.

7. **Media estrategia famosa ni siquiera bate a no hacer nada.** (2026-07-15)
   Cruce dorado (+326%), MACD (+658%) y Donchian (+758%) quedaron por debajo de
   comprar-y-aguantar (+834%) en 2020→2026.

8. **Los costes se comen lo pequeño.** (2026-07-10)
   Operar ventanas de 2h: el movimiento típico (±0,02-0,05%) es menor que el
   coste del viaje (0,09%). Sin edge grande, la comisión gana siempre.

9. **La unidad estadística es la semana/el día, no el trade.** (2026-07-04)
   42 símbolos el mismo sábado no son 42 datos: se mueven juntos. Medir por
   medias semanales o el intervalo de confianza sale falsamente estrecho.

10. **Los simuladores tienen artefactos.** (2026-07-15)
    El Strategy Tester de TradingView infló 64 "trades" cuando había ~44 reales
    (micro-restos de redondeo) y hundió el win rate aparente (28% vs ~41%).
    Entender la herramienta antes de leer sus números.

11. **El mejor de una lista siempre tiene parte de suerte.** (2026-07-15)
    Ichimoku ganó la tanda de 6, PERO elegir al ganador de una comparación es
    sesgo de selección. Por eso se mide forward antes de creérselo.

---

*Mantenimiento: la revisión de los domingos añade lecciones nuevas SOLO si los
datos de la semana las respaldan. Las mediciones selladas (EMA, Ichimoku,
finde, prima) NO se tocan con estas lecciones hasta su veredicto — adaptar una
medición en marcha la contamina (lección 3).*
