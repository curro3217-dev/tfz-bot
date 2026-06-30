import ssl
import ccxt
import pandas as pd
import os
import time
from pathlib import Path
from config import TFZConfig

_ssl_patched = False


def _patch_ssl():
    global _ssl_patched
    if _ssl_patched:
        return
    if os.environ.get("INSECURE_SSL") == "1":
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        ssl._create_default_https_context = ssl._create_unverified_context
        import requests.adapters
        _original_send = requests.adapters.HTTPAdapter.send

        def _patched_send(self, request, **kwargs):
            kwargs["verify"] = False
            # Guarantee a hard timeout on every request so a stalled socket can
            # never hang the process indefinitely (connect, read).
            if not kwargs.get("timeout"):
                kwargs["timeout"] = (10, 20)
            return _original_send(self, request, **kwargs)

        requests.adapters.HTTPAdapter.send = _patched_send
        _ssl_patched = True


def create_exchange(name: str) -> ccxt.Exchange:
    _patch_ssl()
    cls = getattr(ccxt, name)
    opts = {
        "enableRateLimit": True,
        "timeout": 20000,  # ms — ccxt-level cap so a request can't hang forever
    }
    # Tipo de mercado por exchange: queremos perps lineales USDT (BASE/USDT:USDT).
    # Binance necesita defaultType 'future'; Bybit 'swap'. Sin esto, Binance carga
    # SPOT y los simbolos perp no resuelven.
    dtype = {"binance": "future", "bybit": "swap", "mexc": "swap"}.get(name)
    if dtype:
        opts["options"] = {"defaultType": dtype}
    exchange = cls(opts)
    if os.environ.get("INSECURE_SSL") == "1":
        exchange.verify = False
        exchange.session.verify = False
    return exchange


_EXCHANGES = {}


def _get_exchange(name: str):
    """Reuse one exchange instance per process with markets loaded ONCE.
    load_markets() is the slow per-fetch call and an API hit -> caching it
    turns N calls (one per fetch in a build) into 1, easing the rate limit."""
    ex = _EXCHANGES.get(name)
    if ex is None:
        ex = create_exchange(name)
        ex.load_markets()
        _EXCHANGES[name] = ex
    return ex


def _resolve_symbol(name: str, exchange, symbol: str) -> str:
    """Traduce el simbolo INTERNO del bot al nombre que usa el exchange. El bot guarda
    todo como BASE/USDT:USDT (estilo Binance); MEXC nombra distinto algunas: acciones
    tokenizadas con sufijo STOCK (MSTR -> MSTRSTOCK) y memes sin el prefijo 1000
    (1000PEPE -> PEPE; misma evolucion en %). Si ya coincide o no es MEXC, no toca nada."""
    if symbol in exchange.markets:
        return symbol
    if name != "mexc":
        return symbol
    base, _, quote = symbol.partition("/")
    rest = "/" + quote
    cands = []
    if base.startswith("1000"):
        cands.append(base[4:] + rest)        # 1000PEPE -> PEPE
    cands.append(base + "STOCK" + rest)      # MSTR -> MSTRSTOCK
    for c in cands:
        if c in exchange.markets:
            return c
    return symbol


def fetch_ohlcv(
    symbol: str,
    timeframe: str = "15m",
    limit: int = 1000,
    since: int = None,
    config: TFZConfig = None,
) -> pd.DataFrame:
    cfg = config or TFZConfig()

    exchange = None
    ex_symbol = symbol
    for name in [cfg.default_exchange, cfg.fallback_exchange]:
        try:
            cand = _get_exchange(name)
            exchange = cand                       # recuerda el ultimo valido como fallback
            s = _resolve_symbol(name, cand, symbol)
            if s in cand.markets:
                exchange = cand
                ex_symbol = s
                break
        except Exception:
            continue

    if exchange is None:
        raise RuntimeError(f"Could not connect to any exchange for {symbol}")

    all_candles = []
    tf_ms = _timeframe_to_ms(timeframe)
    now = int(time.time() * 1000)

    # Start timestamp: explicit `since`, or `limit` bars back from now.
    fetch_since = since if since is not None else now - limit * tf_ms

    # Paginate forward by timestamp. Terminate on: no data, no progress,
    # reaching the present, or hitting the requested limit. We do NOT break on
    # a batch returning fewer than 1000 candles -- exchanges routinely return
    # 999 for a full window, which would otherwise abort after one request.
    last_ts = None
    while True:
        candles = exchange.fetch_ohlcv(ex_symbol, timeframe, since=fetch_since, limit=1000)
        if not candles:
            break
        if all_candles and candles[0][0] <= all_candles[-1][0]:
            candles = [c for c in candles if c[0] > all_candles[-1][0]]
            if not candles:
                break
        all_candles.extend(candles)

        new_last = all_candles[-1][0]
        if new_last == last_ts:  # no forward progress -> reached end of history
            break
        last_ts = new_last
        fetch_since = new_last + 1

        if len(all_candles) >= limit:
            break
        if fetch_since >= now:  # caught up to the present
            break
        time.sleep(exchange.rateLimit / 1000)

    all_candles = all_candles[:limit]

    df = pd.DataFrame(
        all_candles,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    return df


_TF_MAP = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000,
    "4h": 14_400_000, "6h": 21_600_000, "12h": 43_200_000, "1d": 86_400_000,
}


def _timeframe_to_ms(tf: str) -> int:
    return _TF_MAP.get(tf, 900_000)


def save_candles(df: pd.DataFrame, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def load_candles(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)


_CACHE_DIR = Path(__file__).parent / "data_cache"


def fetch_ohlcv_cached(
    symbol: str,
    timeframe: str = "15m",
    limit: int = 1000,
    since: int = None,
    config: TFZConfig = None,
) -> pd.DataFrame:
    """Like fetch_ohlcv but caches candles to disk and only fetches the NEW
    candles on repeat calls (the Freqtrade/Jesse pattern). Closed candles are
    immutable, so this is safe — it just avoids re-downloading thousands of
    candles every build and hammering the exchange rate limit (Bybit 10006).
    If an explicit `since` is given, bypass the cache (it's a one-off range)."""
    if since is not None:
        return fetch_ohlcv(symbol, timeframe, limit=limit, since=since, config=config)
    cfg = config or TFZConfig()
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = symbol.replace("/", "_").replace(":", "_")
    path = _CACHE_DIR / f"{cfg.default_exchange}_{safe}_{timeframe}.parquet"
    tf_ms = _timeframe_to_ms(timeframe)

    # FREEZE_CACHE: usar la cache TAL CUAL, sin pedir velas nuevas. Para comparaciones
    # A/B limpias: garantiza que dos builds lean datos IDENTICOS (mismo set de trades).
    if os.environ.get("FREEZE_CACHE") == "1" and path.exists():
        try:
            return pd.read_parquet(path).tail(limit).reset_index(drop=True)
        except Exception:
            pass

    cached = None
    if path.exists():
        try:
            cached = pd.read_parquet(path)
        except Exception:
            cached = None

    if cached is not None and len(cached) >= limit:
        # Incremental: only fetch candles since the last cached one (+ small
        # overlap to refresh the most recent, possibly-unclosed candle).
        last_ms = int(pd.Timestamp(cached["timestamp"].max()).timestamp() * 1000)
        try:
            delta = fetch_ohlcv(symbol, timeframe, limit=limit,
                                since=last_ms - 2 * tf_ms, config=cfg)
        except Exception:
            delta = None
        merged = pd.concat([cached, delta], ignore_index=True) if delta is not None and len(delta) else cached
    else:
        # First time, or cache smaller than requested -> fetch the full window.
        full = fetch_ohlcv(symbol, timeframe, limit=limit, config=cfg)
        merged = pd.concat([cached, full], ignore_index=True) if cached is not None else full

    merged = (merged.drop_duplicates(subset=["timestamp"])
                    .sort_values("timestamp").reset_index(drop=True))
    try:
        merged.to_parquet(path, index=False)
    except Exception:
        pass
    return merged.tail(limit).reset_index(drop=True)
