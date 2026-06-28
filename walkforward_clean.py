"""
CLEAN walk-forward — no look-ahead.

Uses the already-built ml_dataset.csv. Restricts to mover coins, splits them
TEMPORALLY, trains the ML only on the OLDER half, and evaluates the live config
(score>=60 & ML>=cutoff) ONLY on the NEWER half the model never saw. Reports the
result month by month + equity. This is the honest "months of live trading"
number, with the data-leakage of the previous run removed.
"""

import argparse
import numpy as np
import pandas as pd
from collections import defaultdict
from sklearn.ensemble import GradientBoostingClassifier

from ml_dataset import FEATURES

MOVERS = {"SIREN", "ESPORTS", "COAI", "EVAA", "BEAT", "STG", "H", "MEGA",
          "SOXL", "RIF", "VELVET", "TRUMP", "NEAR", "ADA", "WLD", "ZEC", "JTO"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ml-cutoff", type=float, default=0.50)
    ap.add_argument("--score", type=int, default=60)
    ap.add_argument("--split", type=float, default=0.6, help="fraction used to TRAIN (older)")
    ap.add_argument("--data", default="ml_dataset.csv", help="Dataset CSV to use")
    args = ap.parse_args()

    df = pd.read_csv(args.data)
    df["base"] = df["symbol"].str.split("/").str[0]
    mov = df[df["base"].isin(MOVERS)].sort_values("entry_ts").reset_index(drop=True)
    print(f"Señales de movers en el dataset: {len(mov)}")
    if len(mov) < 500:
        print("Muy pocas para un split fiable."); return

    cut = int(len(mov) * args.split)
    train, test = mov.iloc[:cut], mov.iloc[cut:]
    print(f"Entreno ML: {len(train)} (<= {train['entry_ts'].iloc[-1]})")
    print(f"Prueba (no visto): {len(test)} (>= {test['entry_ts'].iloc[0]})")

    model = GradientBoostingClassifier(n_estimators=300, max_depth=3,
                                       learning_rate=0.05, subsample=0.8,
                                       random_state=42)
    model.fit(train[FEATURES].values, train["win"].values)

    test = test.copy()
    test["prob"] = model.predict_proba(test[FEATURES].values)[:, 1]

    # LIVE config on the unseen half
    live = test[(test["total_score"] >= args.score) & (test["prob"] >= args.ml_cutoff)].copy()
    print(f"\n  Config en vivo: score>={args.score} & ML>={args.ml_cutoff}")
    print(f"  -> {len(live)} trades en la mitad NO vista")
    if len(live) == 0:
        print("  Sin trades en la config en vivo sobre el set limpio."); return

    live["month"] = live["entry_ts"].str[:7]
    print(f"\n  {'mes':<9}{'trades':>8}{'win%':>8}{'PnL%':>10}{'exp/trade':>11}")
    print(f"  {'-'*9}{'-'*8}{'-'*8}{'-'*10}{'-'*11}")
    bym = defaultdict(list)
    for _, r in live.iterrows():
        bym[r["month"]].append(r["pnl_pct"])
    for mes in sorted(bym):
        p = bym[mes]
        wr = sum(1 for x in p if x > 0.05) / len(p) * 100
        print(f"  {mes:<9}{len(p):>8}{wr:>7.1f}%{sum(p):>+9.1f}%{sum(p)/len(p):>+10.3f}%")

    pnls = live["pnl_pct"].tolist()
    wr = sum(1 for x in pnls if x > 0.05) / len(pnls) * 100
    print(f"\n  {'TOTAL':<9}{len(pnls):>8}{wr:>7.1f}%{sum(pnls):>+9.1f}%{sum(pnls)/len(pnls):>+10.3f}%")

    # Equity (sequential, 1% risk)
    eq, peak, maxdd = 1.0, 1.0, 0.0
    for _, r in live.sort_values("entry_ts").iterrows():
        risk = r["risk_pct"] if r["risk_pct"] > 0 else 1.0
        eq *= (1 + 0.01 * (r["pnl_pct"] / risk))
        if eq <= 0:
            eq = 1e-9; break
        peak = max(peak, eq); maxdd = max(maxdd, (peak - eq) / peak * 100)
    print(f"\n  Capital compuesto (1% riesgo/trade): {eq:.2f}x | maxDD {maxdd:.1f}%")
    print("  (LIMPIO: el ML se entreno solo con datos anteriores a la prueba)")


if __name__ == "__main__":
    main()
