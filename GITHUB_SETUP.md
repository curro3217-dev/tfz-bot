# Montar el bot TFZ en GitHub Actions 24/7

Mismo patrón que tu scanner: **un disparo por hora (cron-job.org)** lanza el workflow,
que **hace un bucle interno (un ciclo de paper cada 5 min, ~50 min)** y **sube el estado**
(la base de datos de trades) al repo después de cada ciclo.

## 1. Crear el repo
- Crea un repo NUEVO en GitHub (p.ej. `tfz-bot`). Puede ser privado o público.
  - Paper trading, sin claves de exchange -> aunque sea público no hay dinero en riesgo.
  - El token de Telegram NO va en el código, va en "Secrets" (paso 3).

## 2. Subir los archivos
Sube TODO el contenido de la carpeta `tfz-bot` MENOS lo que ignora `.gitignore`
(la caché `data_cache/`, los `.csv`, `.log`, `.bak`, y la BD local). Es decir:
los `.py`, `requirements.txt`, `.github/workflows/bot.yml`, `CHANGELOG.md`, este archivo.

## 3. Poner el token de Telegram en Secrets
En el repo: **Settings -> Secrets and variables -> Actions -> New repository secret**.
Crea DOS:
- `TELEGRAM_BOT_TOKEN`  = tu token (el mismo del scanner)
- `TELEGRAM_CHAT_ID`    = tu chat id

## 4. Activar Actions
Pestaña **Actions** del repo -> si pide habilitarlas, dale a "I understand... enable".

## 5. Disparo por hora (cron-job.org) — igual que el scanner
El workflow se dispara con `workflow_dispatch`. Para lanzarlo cada hora:
1. Crea un **Personal Access Token** (PAT) en GitHub:
   Settings (de tu cuenta) -> Developer settings -> Personal access tokens ->
   Fine-grained token, con permiso **Actions: Read and write** sobre el repo del bot.
2. En **cron-job.org**, crea un job cada hora (igual que el del scanner) que haga:
   - **URL:** `https://api.github.com/repos/TU_USUARIO/tfz-bot/actions/workflows/bot.yml/dispatches`
   - **Método:** POST
   - **Cabeceras:**
     - `Authorization: Bearer TU_PAT`
     - `Accept: application/vnd.github+json`
   - **Cuerpo (body):** `{"ref":"main"}`

(El workflow tambien tiene un `schedule` de respaldo cada hora, por si cron-job.org falla;
pero el cron de GitHub puede retrasarse, por eso el disparo externo es el principal.)

## Qué pasa al arrancar
- El bot crea una base de datos NUEVA (arranque limpio, sin los reseteos ni huecos del PC).
- Primer ciclo de cada hora: descarga datos de Binance (~unos minutos); el resto van rápidos.
- Manda alertas de Telegram al abrir/cerrar, igual que en tu PC.
- Sube `tfz_data.db` al repo cada ciclo -> el estado se conserva entre ejecuciones.

## Para ver cómo va
- Las alertas te siguen llegando por Telegram.
- En la pestaña **Actions** ves cada ejecución y su log (los ciclos).
- El archivo `tfz_data.db` en el repo es el estado actual (lo puedes descargar y abrir
  con cualquier visor de SQLite si quieres mirar los trades).
