# TFZ Bot — Registro de cambios (CHANGELOG)

Registro cronológico de TODO lo que se ha tocado, para poder **retroceder** si algo
se rompe. Cada entrada indica QUÉ cambió, en QUÉ archivo y con qué VALORES, más el
porqué. Lo más reciente arriba del todo de cada día. Fechas en formato AAAA-MM-DD.

> Este proyecto NO usa git, así que este archivo es la única "máquina del tiempo".
> Antes de un cambio grande, conviene copiar el archivo afectado a `*.bak`.

---

## 2026-07-03

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
