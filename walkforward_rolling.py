"""
ROLLING walk-forward — every month is clean out-of-sample.

For each month M: train the ML on ALL signals from months BEFORE M, then predict
on month M and apply the live config (score>=X & ML>=cutoff). The model never
sees the month it's tested on. Walking forward month by month gives a clean
out-of-sample result for (almost) every month, not just the last test split.
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
    ap.add_argument("--data", default="ml_dataset_7m.csv")
    ap.add_argument("--ml-cutoff", type=float, default=0.50)
    ap.add_argument("--score", type=int, default=50)
    ap.add_argument("--min-train", type=int, default=800,
                    help="min training rows before a month can be tested")
    args = ap.parse_args()

    df = pd.read_csv(args.data)
    df["base"] = df["symbol"].str.split("/").str[0]
    df = df[df["base"].isin(MOVERS)].copy()
    df["month"] = df["entry_ts"].str[:7]
    df = df.sort_values("entry_ts").reset_index(drop=True)
    months = sorted(df["month"].unique())
    print(f"Señales: {len(df)} | meses en datos: {months[0]} -> {months[-1]} ({len(months)})")
    print(f"Config: score>={args.score} & ML>={args.ml_cutoff} | rolling (cada mes OOS)\n")

    print(f"  {'mes':<9}{'entrena':>9}{'trades':>8}{'win%':>8}{'PnL%':>10}{'exp/trade':>11}")
    print(f"  {'-'*9}{'-'*9}{'-'*8}{'-'*8}{'-'*10}{'-'*11}")

    all_live = []  # (entry_ts, pnl, risk)
    for m in months:
        train = df[df["month"] < m]
        test = df[df["month"] == m]
        if len(train) < args.min_train or len(test) < 5:
            print(f"  {m:<9}{len(train):>9}{'-':>8}  (entreno/test insuficiente)")
            continue
        model = GradientBoostingClassifier(n_estimators=300, max_depth=3,
                                           learning_rate=0.05, subsample=0.8,
                                           random_state=42)
        model.fit(train[FEATURES].values, train["win"].values)
        t = test.copy()
        t["prob"] = model.predict_proba(t[FEATURES].values)[:, 1]
        live = t[(t["total_score"] >= args.score) & (t["prob"] >= args.ml_cutoff)]
        if len(live) == 0:
            print(f"  {m:<9}{len(train):>9}{0:>8}")
            continue
        p = live["pnl_pct"].tolist()
        wr = sum(1 for x in p if x > 0.05) / len(p) * 100
        print(f"  {m:<9}{len(train):>9}{len(p):>8}{wr:>7.1f}%{sum(p):>+9.1f}%{sum(p)/len(p):>+10.3f}%")
        for _, r in live.iterrows():
            all_live.append((r["entry_ts"], r["pnl_pct"], r["risk_pct"]))

    if not all_live:
        print("\nSin trades."); return
    pnls = [x[1] for x in all_live]
    wr = sum(1 for x in pnls if x > 0.05) / len(pnls) * 100
    print(f"\n  {'TOTAL':<9}{'':>9}{len(pnls):>8}{wr:>7.1f}%{sum(pnls):>+9.1f}%{sum(pnls)/len(pnls):>+10.3f}%")

    eq, peak, maxdd = 1.0, 1.0, 0.0
    for ts, pnl, risk in sorted(all_live):
        risk = risk if risk and risk > 0 else 1.0
        eq *= (1 + 0.01 * (pnl / risk))
        if eq <= 0:
            eq = 1e-9; break
        peak = max(peak, eq); maxdd = max(maxdd, (peak - eq) / peak * 100)
    print(f"\n  Capital compuesto (1% riesgo/trade): {eq:.2f}x | maxDD {maxdd:.1f}%")

    # CREDIBLE figure: fixed stake (NO compounding), risk 1% off constant capital,
    # leverage cap 10x, with an extra slippage haircut for illiquid movers.
    def fixed_stake(haircut):
        tot = 0.0; max_lev = 10.0
        for ts, pnl, risk in sorted(all_live):
            rp = risk if risk and risk > 0 else 1.0
            lev = min(1.0 / rp, max_lev)        # leverage to risk 1% given the stop
            net = pnl - haircut                  # extra slippage per trade (entry+exit)
            tot += lev * net / 100.0
        return tot * 100  # % return on initial capital over the whole period

    print("\n  === CIFRA CREÍBLE (apuesta fija 1%/trade, sin compounding, tope 10x) ===")
    print(f"  Sin recorte extra:           {fixed_stake(0.0):+.0f}% en ~6 meses")
    print(f"  Con slippage extra -0.3%/tr: {fixed_stake(0.3):+.0f}%")
    print(f"  Con slippage extra -0.5%/tr: {fixed_stake(0.5):+.0f}%")
    print("\n  (Los 'capital compuesto Nx' de arriba son FANTASIA por el compounding; ignorar)")
    print("  (ROLLING LIMPIO: cada mes con modelo entrenado solo con meses anteriores)")


if __name__ == "__main__":
    main()
