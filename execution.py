"""
Execution layer for the TFZ engine — TESTNET-FIRST and SAFE BY DEFAULT.

Turns a validated Signal into real exchange orders (entry + stop-loss +
take-profit) with risk-based position sizing. Defaults are deliberately
defensive:

  - testnet = True      -> Bybit sandbox, fake money
  - dry_run = True      -> compute & print the order, DON'T send it
  - confirm_live = False -> a hard wall against trading real money

Going to real money requires ALL of: testnet=False, dry_run=False,
confirm_live=True, and real API keys in the environment. The module refuses
otherwise. Build/test on testnet for weeks before even considering that.

API keys come from the environment, never hardcoded:
  testnet:  BYBIT_TESTNET_API_KEY / BYBIT_TESTNET_API_SECRET
  live:     BYBIT_API_KEY / BYBIT_API_SECRET   (keep withdrawals DISABLED)
"""

import os
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from data_fetcher import _patch_ssl

_STATE_PATH = os.path.join(os.path.dirname(__file__), "execution_state.json")


@dataclass
class ExecutionConfig:
    exchange: str = "bybit"
    testnet: bool = True            # sandbox by default
    dry_run: bool = True            # compute & show, do not send
    confirm_live: bool = False      # extra wall for real money

    risk_per_trade_pct: float = 1.0  # % of equity risked per trade
    leverage: int = 3
    max_open_positions: int = 3
    max_daily_loss_pct: float = 5.0  # kill-switch: stop after this daily loss
    min_notional_usdt: float = 5.0   # skip dust-sized orders
    max_position_pct: float = 40.0   # cap one position to this % of buying power


class ExecutionError(Exception):
    pass


class Executor:
    def __init__(self, cfg: ExecutionConfig = None):
        self.cfg = cfg or ExecutionConfig()
        self._ex = None
        self._guard_live()

    # ---- safety -----------------------------------------------------------
    def _guard_live(self):
        c = self.cfg
        going_live = (not c.testnet) and (not c.dry_run)
        if going_live and not c.confirm_live:
            raise ExecutionError(
                "REFUSED: real-money trading requires confirm_live=True. "
                "Use testnet first."
            )

    @property
    def mode(self) -> str:
        if self.cfg.dry_run:
            return "DRY-RUN (no orders sent)"
        return "TESTNET (sandbox)" if self.cfg.testnet else "LIVE (real money)"

    # ---- exchange ---------------------------------------------------------
    def _is_hl(self):
        return self.cfg.exchange == "hyperliquid"

    def _keys(self):
        # Hyperliquid is a DEX: auth is wallet-based (walletAddress + privateKey
        # of an AGENT wallet that can trade but NOT withdraw). Other exchanges use
        # apiKey/secret (binance futures testnet needs no KYC via GitHub login).
        ex = self.cfg.exchange.upper()
        if self._is_hl():
            return (os.environ.get(f"{ex}_WALLET_ADDRESS"),
                    os.environ.get(f"{ex}_PRIVATE_KEY"))
        suffix = "_TESTNET" if self.cfg.testnet else ""
        return (os.environ.get(f"{ex}{suffix}_API_KEY"),
                os.environ.get(f"{ex}{suffix}_API_SECRET"))

    def exchange(self):
        if self._ex is not None:
            return self._ex
        import ccxt
        _patch_ssl()
        a, b = self._keys()
        if not self.cfg.dry_run and not (a and b):
            kind = "wallet (address+privateKey)" if self._is_hl() else "API keys"
            raise ExecutionError(
                f"Missing {kind} for {self.cfg.exchange} "
                f"{'testnet' if self.cfg.testnet else 'live'}. Set them in the environment.")
        if self._is_hl():
            ex = ccxt.hyperliquid({
                "walletAddress": a, "privateKey": b,
                "enableRateLimit": True, "timeout": 20000,
            })
        else:
            # "binance" futures live on the USD-M class (binanceusdm); plain
            # ccxt.binance defaults to spot and mis-routes the futures testnet.
            ccxt_id = "binanceusdm" if self.cfg.exchange == "binance" else self.cfg.exchange
            ex = getattr(ccxt, ccxt_id)({
                "apiKey": a, "secret": b,
                "enableRateLimit": True, "timeout": 20000,
                "options": {"defaultType": "swap"},
            })
        if self.cfg.testnet:
            ex.set_sandbox_mode(True)
        if os.environ.get("INSECURE_SSL") == "1":
            ex.verify = False
            try:
                ex.session.verify = False
            except Exception:
                pass
        self._ex = ex
        return ex

    def to_venue_symbol(self, symbol: str) -> str:
        """Map a signal symbol (BASE/USDT:USDT) to this venue's format.
        Hyperliquid perps are USDC-settled (BASE/USDC:USDC)."""
        if self._is_hl():
            base = symbol.split("/")[0]
            return f"{base}/USDC:USDC"
        return symbol

    # ---- account ----------------------------------------------------------
    def get_equity(self) -> float:
        """Account equity in the settle currency (USDC on Hyperliquid, else USDT).
        In dry-run with no creds, assume a nominal 1000 for sizing."""
        if self.cfg.dry_run and not all(self._keys()):
            return 1000.0
        bal = self.exchange().fetch_balance()
        ccy = "USDC" if self._is_hl() else "USDT"
        c = bal.get(ccy, {})
        eq = float(c.get("total") or c.get("free") or 0.0)
        if eq == 0.0:  # fallback: any reported total equity
            try:
                eq = float(bal.get("total", {}).get(ccy) or 0.0)
            except Exception:
                pass
        return eq

    def open_positions(self):
        if self.cfg.dry_run and not all(self._keys()):
            return []
        try:
            return [p for p in self.exchange().fetch_positions()
                    if float(p.get("contracts") or 0) != 0]
        except Exception:
            return []

    # ---- daily-loss kill switch ------------------------------------------
    def _day_start_equity(self, current_equity: float) -> float:
        """Equity recorded at the start of today's trading. Resets at date change."""
        today = datetime.now().strftime("%Y-%m-%d")
        state = {}
        if os.path.exists(_STATE_PATH):
            try:
                with open(_STATE_PATH) as f:
                    state = json.load(f)
            except Exception:
                state = {}
        if state.get("date") != today:
            state = {"date": today, "start_equity": current_equity}
            with open(_STATE_PATH, "w") as f:
                json.dump(state, f)
        return float(state.get("start_equity", current_equity))

    def daily_loss_status(self, equity: float):
        """Return (kill_switch_active, drawdown_pct, day_start_equity)."""
        start = self._day_start_equity(equity)
        dd = (start - equity) / start * 100 if start > 0 else 0.0
        return dd >= self.cfg.max_daily_loss_pct, dd, start

    # ---- sizing -----------------------------------------------------------
    def compute_qty(self, signal, equity: float) -> float:
        risk_amt = equity * self.cfg.risk_per_trade_pct / 100.0
        risk_per_unit = abs(signal.entry_price - signal.stop_loss)
        if risk_per_unit <= 0:
            raise ExecutionError("Invalid stop distance (<=0)")
        qty = risk_amt / risk_per_unit
        # Cap to buying power: with very tight stops the risk-based size can
        # demand more margin than the account has. Capping reduces effective
        # risk below target (safer), never above.
        max_notional = equity * self.cfg.leverage * self.cfg.max_position_pct / 100.0
        if qty * signal.entry_price > max_notional:
            qty = max_notional / signal.entry_price
        return qty

    # ---- the gate before any order ---------------------------------------
    def _preflight(self, signal):
        c = self.cfg
        n_open = len(self.open_positions())
        if n_open >= c.max_open_positions:
            raise ExecutionError(f"max_open_positions reached ({n_open}/{c.max_open_positions})")
        equity = self.get_equity()
        if equity <= 0:
            raise ExecutionError("No equity available")
        qty = self.compute_qty(signal, equity)
        notional = qty * signal.entry_price
        if notional < c.min_notional_usdt:
            raise ExecutionError(f"notional {notional:.2f} < min {c.min_notional_usdt}")
        return equity, qty, notional

    # ---- place ------------------------------------------------------------
    def place(self, signal, verbose=True) -> Optional[dict]:
        """Place (or simulate) entry + SL + TP for a signal."""
        equity, qty, notional = self._preflight(signal)
        side = "buy" if signal.direction == "long" else "sell"
        venue_symbol = self.to_venue_symbol(signal.symbol)

        # On a real venue, make sure the coin is actually listed there
        if not self.cfg.dry_run:
            try:
                if venue_symbol not in self.exchange().load_markets():
                    raise ExecutionError(f"{venue_symbol} no cotiza en {self.cfg.exchange}")
            except ExecutionError:
                raise
            except Exception:
                pass

        plan = {
            "symbol": venue_symbol, "side": side, "qty": round(qty, 8),
            "entry": signal.entry_price, "sl": signal.stop_loss,
            "tp": signal.take_profit, "notional": round(notional, 2),
            "leverage": self.cfg.leverage, "risk_pct": self.cfg.risk_per_trade_pct,
            "equity": round(equity, 2), "mode": self.mode,
        }

        if verbose:
            print(f"  [{self.mode}] {venue_symbol} {side.upper()} "
                  f"qty {plan['qty']} (~{plan['notional']} @ {self.cfg.leverage}x) | "
                  f"entry {signal.entry_price:.6g} SL {signal.stop_loss:.6g} "
                  f"TP {signal.take_profit:.6g}")

        if self.cfg.dry_run:
            plan["status"] = "simulated"
            return plan

        ex = self.exchange()
        try:
            ex.set_leverage(self.cfg.leverage, venue_symbol)
        except Exception:
            pass  # some accounts reject re-setting; non-fatal
        # Hyperliquid "market" orders are marketable-limit: ccxt requires a
        # reference price to derive the max-slippage bound. Bybit ignores price
        # on market orders, so only pass it for hyperliquid.
        price_arg = signal.entry_price if self._is_hl() else None
        # SL/TP attach format differs per venue: Bybit takes plain trigger
        # prices; hyperliquid wants dicts with triggerPrice + market type
        # (grouped tp/sl), else ccxt treats them as limit orders with no price.
        if self._is_hl():
            order_params = {
                "stopLoss": {"triggerPrice": signal.stop_loss, "type": "market"},
                "takeProfit": {"triggerPrice": signal.take_profit, "type": "market"},
                "reduceOnly": False,
            }
        else:
            order_params = {
                "stopLoss": signal.stop_loss,
                "takeProfit": signal.take_profit,
                "reduceOnly": False,
            }
        try:
            order = ex.create_order(
                venue_symbol, "market", side, qty, price_arg, params=order_params,
            )
        except Exception as e:
            # An exchange rejection (min size, regulatory, margin, etc.) must not
            # crash the cycle -- surface it and let the caller skip & continue.
            raise ExecutionError(f"order rejected by exchange: {e}")
        plan["status"] = "sent"
        plan["order_id"] = order.get("id")
        if verbose:
            print(f"    -> order {order.get('id')} ({plan['status']})")
        return plan


def run_execution_cycle(symbols=None, timeframes=None, tfz_cfg=None,
                        exec_cfg: ExecutionConfig = None, fresh_lookback=2,
                        ml_cutoff=0.55, use_ml=True, watchlist_source="scanner",
                        verbose=True, filter_mode="ml", min_score=60.0, min_rr=8.0):
    """One execution cycle: scanner watchlist -> fresh accepted signals ->
    place (or simulate) orders. Reuses the exact paper-trading signal logic.
    filter_mode "ml" uses the win-prob gate; "profit" uses score>=min_score & rr>=min_rr
    (the profit-aligned filter the paper trading uses; keeps high-RR asymmetric winners)."""
    from config import TFZConfig
    from paper import fresh_accepted_signals, resolve_watchlist

    tfz_cfg = tfz_cfg or TFZConfig()
    ex = Executor(exec_cfg)
    symbols = resolve_watchlist(symbols, watchlist_source, verbose)
    timeframes = timeframes or ["5m", "15m"]

    print(f"\n[execution cycle @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print(f"  Mode: {ex.mode} | risk {ex.cfg.risk_per_trade_pct}%/trade | "
          f"{ex.cfg.leverage}x | max {ex.cfg.max_open_positions} pos")

    # Daily-loss kill switch: halt new entries if equity fell too far today.
    equity = ex.get_equity()
    killed, dd, day_start = ex.daily_loss_status(equity)
    print(f"  Equity {equity:.2f} | day start {day_start:.2f} | "
          f"daily P&L {-dd:+.2f}% (limit -{ex.cfg.max_daily_loss_pct}%)")
    if killed:
        print(f"  KILL SWITCH ACTIVE: daily loss {dd:.2f}% >= {ex.cfg.max_daily_loss_pct}% "
              f"-> NO new orders today. (Open positions keep their exchange SL/TP.)")
        return 0

    if filter_mode == "profit":
        print(f"  Filter: PROFIT score>={min_score:.0f} & rr>={min_rr:.0f}")
    else:
        print(f"  Filter: ML p>={ml_cutoff:.2f}" if use_ml else "  Filter: none (ML off)")
    print(f"  Watchlist: {len(symbols)} symbols x {len(timeframes)} TF")

    # Dedup against positions already open on the venue (venue-symbol + side)
    open_keys = set()
    for p in ex.open_positions():
        open_keys.add((p.get("symbol"), p.get("side")))

    placed = 0
    for symbol in symbols:
        for tf in timeframes:
            for sig, trend, prob, df in fresh_accepted_signals(
                    symbol, tf, tfz_cfg, fresh_lookback, ml_cutoff, use_ml, verbose=verbose,
                    filter_mode=filter_mode, min_score=min_score, min_rr=min_rr):
                key = (ex.to_venue_symbol(sig.symbol), sig.direction)
                if key in open_keys:
                    continue
                try:
                    ex.place(sig, verbose=verbose)
                    open_keys.add(key)
                    placed += 1
                except ExecutionError as e:
                    if verbose:
                        print(f"  [skip] {sig.symbol} {sig.direction}: {e}")
    print(f"  -> {placed} order(s) {'simulated' if ex.cfg.dry_run else 'sent'}")
    return placed
