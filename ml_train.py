"""
Train and evaluate the ML signal-quality filter.

Loads ml_dataset.csv, splits TEMPORALLY (train on older, test on newer -- no
lookahead), trains a gradient-boosting classifier to predict win probability,
and answers the business question: at matched selectivity, does the ML filter
pick better trades than the rule-based score>=60 threshold?

Usage: python -u ml_train.py
Saves: ml_model.joblib  (model + feature list + recommended probability cutoff)
"""

import os
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from ml_dataset import FEATURES

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "ml_dataset.csv")
MODEL = os.path.join(HERE, "ml_model.joblib")


def expectancy(df):
    return df["pnl_pct"].mean() if len(df) else 0.0


def main():
    df = pd.read_csv(DATA)
    df = df.sort_values("entry_ts").reset_index(drop=True)
    print(f"Dataset: {len(df)} trades | win rate {df['win'].mean()*100:.1f}% | "
          f"mean pnl {df['pnl_pct'].mean():+.3f}%")

    # Temporal split: oldest 70% train, newest 30% test
    cut = int(len(df) * 0.70)
    train, test = df.iloc[:cut], df.iloc[cut:]
    print(f"Train: {len(train)} (<= {train['entry_ts'].iloc[-1]}) | "
          f"Test: {len(test)} (>= {test['entry_ts'].iloc[0]})")

    Xtr, ytr = train[FEATURES].values, train["win"].values
    Xte, yte = test[FEATURES].values, test["win"].values

    model = GradientBoostingClassifier(
        n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8,
        random_state=42,
    )
    model.fit(Xtr, ytr)

    proba = model.predict_proba(Xte)[:, 1]
    auc = roc_auc_score(yte, proba)
    print(f"\nTest AUC: {auc:.3f}  (0.5 = no skill, >0.55 = useful)")

    test = test.copy()
    test["prob"] = proba

    # Baseline: the current rule (score>=60) on the test set
    base = test[test["total_score"] >= 60]
    base_n, base_exp = len(base), expectancy(base)
    base_wr = base["win"].mean() * 100 if base_n else 0
    print(f"\nBaseline rule (score>=60):  {base_n} trades | "
          f"WR {base_wr:.1f}% | expectancy {base_exp:+.3f}%")

    # ML filter at matched volume: pick the prob cutoff giving ~same #trades
    if base_n:
        cutoff_matched = np.quantile(proba, 1 - base_n / len(test))
        ml_matched = test[test["prob"] >= cutoff_matched]
        print(f"ML filter (matched vol):   {len(ml_matched)} trades | "
              f"WR {ml_matched['win'].mean()*100:.1f}% | "
              f"expectancy {expectancy(ml_matched):+.3f}% | cutoff p>={cutoff_matched:.3f}")

    # Full probability sweep on the test set
    print(f"\n  prob>=   trades   WR      expectancy")
    print(f"  ------   ------   -----   ----------")
    best = (None, -1e9, 0)
    for p in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]:
        sub = test[test["prob"] >= p]
        if len(sub) < 20:
            print(f"  {p:.2f}     {len(sub):5d}    (too few)")
            continue
        e = expectancy(sub)
        print(f"  {p:.2f}     {len(sub):5d}   {sub['win'].mean()*100:4.1f}%   {e:+.3f}%")
        # prefer best expectancy while keeping >=25% of baseline volume
        if e > best[1] and len(sub) >= max(50, base_n * 0.25):
            best = (p, e, len(sub))

    rec_cutoff = best[0] if best[0] is not None else 0.55
    print(f"\nRecommended cutoff: p>={rec_cutoff:.2f} "
          f"(expectancy {best[1]:+.3f}% on {best[2]} test trades)")

    # Production candidates: a score sanity-floor combined with the ML gate
    print(f"\nCombined gates (production candidates):")
    for sfloor in (50, 60):
        for pcut in (0.55, 0.60):
            sub = test[(test["total_score"] >= sfloor) & (test["prob"] >= pcut)]
            if len(sub) >= 20:
                print(f"  score>={sfloor} & p>={pcut}: {len(sub):5d} trades | "
                      f"WR {sub['win'].mean()*100:4.1f}% | exp {expectancy(sub):+.3f}%")

    # Feature importances
    imp = sorted(zip(FEATURES, model.feature_importances_), key=lambda x: -x[1])
    print(f"\nTop 10 features:")
    for name, w in imp[:10]:
        print(f"  {name:22s} {w:.3f}")

    # Retrain on ALL data for production, save with metadata
    model_full = GradientBoostingClassifier(
        n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8,
        random_state=42,
    )
    model_full.fit(df[FEATURES].values, df["win"].values)
    joblib.dump({"model": model_full, "features": FEATURES,
                 "cutoff": float(rec_cutoff), "test_auc": float(auc)}, MODEL)
    print(f"\nSaved production model -> {MODEL}")


if __name__ == "__main__":
    main()
