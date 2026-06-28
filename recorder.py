"""
Live evaluation log: records EVERY setup the bot evaluates in a live cycle to a
clean CSV (live_log.csv) for later analysis -- both the ones that pass the ML
gate and the ones rejected. This builds a real dataset of the bot's live
behaviour over time (vs the messy text paper_log).

One row per evaluated fresh signal:
  cycle_ts, symbol, timeframe, direction, formation, entry, sl, tp, rr, score,
  win_prob, passed (1/0 = cleared the ML cutoff), trigger_ts
"""

import os
import csv
from datetime import datetime

_PATH = os.path.join(os.path.dirname(__file__), "live_log.csv")
_COLS = ["cycle_ts", "symbol", "timeframe", "direction", "formation",
         "entry", "sl", "tp", "rr", "score", "win_prob", "passed", "trigger_ts"]


def record_eval(sig, prob, passed, trigger_ts):
    new = not os.path.exists(_PATH)
    try:
        with open(_PATH, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(_COLS)
            w.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                sig.symbol, sig.timeframe, sig.direction, sig.formation_type,
                sig.entry_price, sig.stop_loss, sig.take_profit, sig.rr_ratio,
                round(sig.total_score, 1),
                round(prob, 4) if prob is not None else "",
                int(bool(passed)), str(trigger_ts),
            ])
    except Exception:
        pass  # never let logging break a live cycle
