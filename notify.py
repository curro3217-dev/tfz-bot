"""
Telegram alerts for fresh, ML-approved entries.

Reads the bot credentials from the environment (reuse the same Telegram bot the
coin scanner already uses):
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID

Fail-silent: if the vars aren't set, send_telegram() just returns False and the
rest of the bot keeps working. Uses urllib (stdlib) so it needs no extra deps
and handles this PC's INSECURE_SSL quirk on its own.

Test it:  python notify.py
"""

import os
import ssl
import urllib.request
import urllib.parse


def _ctx():
    ctx = ssl.create_default_context()
    if os.environ.get("INSECURE_SSL") == "1":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


# PAUSA de avisos: con True, el bot NO envia NADA a Telegram (ni entradas ni cierres),
# en el PC y en GitHub. Para reactivar los avisos, poner False. (Se puede forzar tambien
# con la env TFZ_TELEGRAM=1, util si algun dia quieres avisos solo en un sitio.)
ALERTS_PAUSED = True


def send_telegram(text: str) -> bool:
    if ALERTS_PAUSED and os.environ.get("TFZ_TELEGRAM") != "1":
        return False
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": "true",
    }).encode()
    try:
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "tfz-bot"})
        with urllib.request.urlopen(req, context=_ctx(), timeout=15) as r:
            return r.status == 200
    except Exception as e:
        print(f"[telegram] error: {e}")
        return False


def tv_link(symbol: str, tf: str = None) -> str:
    """Enlace al gráfico de TradingView del MISMO contrato que opera el bot
    (Bybit USDT perp), p.ej. XLM/USDT:USDT -> BYBIT:XLMUSDT.P."""
    base = symbol.split("/")[0].upper()
    url = f"https://www.tradingview.com/chart/?symbol=BYBIT:{base}USDT.P"
    iv = {"1m": "1", "5m": "5", "15m": "15", "1h": "60"}.get(tf)
    if iv:
        url += f"&interval={iv}"
    return url


def alert_entry(sig, prob, context: str = None) -> bool:
    """Format and send a fresh-entry alert. `context` (opcional) es una linea de
    indicadores objetivos (RSI/RVOL/EMA200, ver paper._alert_context) que se añade
    a la alerta del modo asistente para que el humano decida con mas datos."""
    arrow = "🟢 LONG" if sig.direction == "long" else "🔴 SHORT"
    wp = f"{prob*100:.0f}%" if prob is not None else "-"
    ctx_line = f"{context}\n" if context else ""
    msg = (
        f"<b>⚡ TFZ entrada</b>\n"
        f"<b>{sig.symbol}</b>  {arrow}  ({sig.timeframe})\n"
        f"Entry: <code>{sig.entry_price:.6g}</code>\n"
        f"SL: <code>{sig.stop_loss:.6g}</code>\n"
        f"TP: <code>{sig.take_profit:.6g}</code>\n"
        f"R:R {sig.rr_ratio} | score {sig.total_score:.0f} | win% {wp}\n"
        f"{ctx_line}"
        f"{sig.formation_type}\n"
        f'<a href="{tv_link(sig.symbol, sig.timeframe)}">📈 Ver en TradingView</a>'
    )
    return send_telegram(msg)


def alert_exit(trade: dict, reason: str, exit_price: float, pnl_pct: float) -> bool:
    """Format and send a trade-closed alert."""
    emoji = "✅" if pnl_pct > 0 else ("➖" if abs(pnl_pct) < 0.05 else "❌")
    reason_es = {"tp_hit": "TP", "sl_hit": "Stop", "breakeven": "Breakeven",
                 "stale": "Sin avance (stale)", "timeout": "Timeout",
                 "f1_mgmt": "Gestion F1"}.get(reason, reason)
    arrow = "🟢" if trade.get("direction") == "long" else "🔴"
    msg = (
        f"<b>{emoji} TFZ cierre</b>\n"
        f"<b>{trade['symbol']}</b>  {arrow} {trade.get('formation_type','')}  ({trade['timeframe']})\n"
        f"Salida: <code>{exit_price:.6g}</code> ({reason_es})\n"
        f"PnL: <b>{pnl_pct:+.2f}%</b>"
    )
    return send_telegram(msg)


if __name__ == "__main__":
    ok = send_telegram("✅ TFZ bot conectado a Telegram. Aqui llegaran las entradas frescas.")
    print("Mensaje enviado OK" if ok else
          "No se envio. Revisa TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID.")
