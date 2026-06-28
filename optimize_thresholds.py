"""
Optimizador ROBUSTO de umbrales (score, RR) con Optuna — anti-sobreajuste.

En vez de tunear a mano (lo que llevó al error del score-50, que brillaba en
movers pero perdía en otros universos), busca los umbrales que funcionan en los
4 universos A LA VEZ: movers, veteranas-1, veteranas-2, jóvenes-8.

Dos objetivos disponibles:
  --objective robust   (def) -> maximiza el retorno creíble del PEOR universo
  --objective quality        -> maximiza el net-por-trade medio (más selectivo)

Restricciones (robustez): cada universo debe ser POSITIVO y tener >= min-trades.
Tendencia fija en 5 (ya validada; baked-in en 3 de los 4 datasets).

Uso: python optimize_thresholds.py [--objective robust|quality] [--trials 400] [--min-trades 80]
Requiere: ml_dataset_7m.csv, ml_dataset_older.csv, ml_dataset_older2.csv, ml_dataset_new8.csv
"""
import argparse
import numpy as np
import pandas as pd
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

MOV = {"SIREN", "ESPORTS", "COAI", "EVAA", "BEAT", "STG", "H", "MEGA", "SOXL",
       "RIF", "VELVET", "TRUMP", "NEAR", "ADA", "WLD", "ZEC", "JTO"}
TREND_BLOCK = 5.0


def load(path, mov=False):
    d = pd.read_csv(path)
    d["base"] = d["symbol"].str.split("/").str[0]
    if mov:  # ml_dataset_7m no tiene el trend-gate baked-in -> aplicarlo aquí
        d = d[d["base"].isin(MOV)].copy()
        tr = d["trend_strength"]; il = d["direction_long"] == 1
        counter = ((il & (tr < 0)) | (~il & (tr > 0))) & (tr.abs() >= TREND_BLOCK)
        d = d[~counter]
    return d


def evalu(d, smin, rrmin, haircut=0.5, maxlev=10.0):
    f = d[(d.total_score >= smin) & (d.rr_ratio >= rrmin)]
    if len(f) == 0:
        return 0, 0.0, 0.0, 0.0
    rp = f["risk_pct"].where(f["risk_pct"] > 0, 1.0)
    lev = np.minimum(1.0 / rp, maxlev)
    contrib = lev * (f["pnl_pct"] - haircut) / 100.0
    return len(f), float(contrib.mean()), float(contrib.sum() * 100), float((f["win"] == 1).mean() * 100)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--objective", choices=["robust", "quality"], default="robust")
    ap.add_argument("--trials", type=int, default=400)
    ap.add_argument("--min-trades", type=int, default=80)
    args = ap.parse_args()

    univ = {
        "movers": load("ml_dataset_7m.csv", mov=True),
        "veteranas1": load("ml_dataset_older.csv"),
        "veteranas2": load("ml_dataset_older2.csv"),
        "jovenes8": load("ml_dataset_new8.csv"),
    }
    for k, v in univ.items():
        print(f"  {k}: {len(v)} señales")

    def objective(trial):
        smin = trial.suggest_int("min_score", 45, 72)
        rrmin = trial.suggest_float("min_rr", 3.0, 14.0, step=0.5)
        creds, pts = [], []
        for d in univ.values():
            n, pt, cred, _ = evalu(d, smin, rrmin)
            if n < args.min_trades or cred <= 0:
                return -1e6
            creds.append(cred); pts.append(pt)
        return min(creds) if args.objective == "robust" else float(np.mean(pts))

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=args.trials)

    bp = study.best_params
    print(f"\n=== MEJOR combo robusto ({args.objective}) ===")
    print(f"  min_score={bp['min_score']}  min_rr={bp['min_rr']}")
    for label, (s, r) in [("ÓPTIMO", (bp["min_score"], bp["min_rr"])),
                          ("ACTUAL (60/6)", (60, 6))]:
        print(f"\n  --- {label}: score>={s} & rr>={r} ---")
        print(f"  {'universo':<12}{'trades':>8}{'win%':>7}{'net/tr':>9}{'ret creíble':>13}")
        for k, d in univ.items():
            n, pt, cred, win = evalu(d, s, r)
            print(f"  {k:<12}{n:>8}{win:>6.1f}%{pt*100:>+8.3f}%{cred:>+12.0f}%")


if __name__ == "__main__":
    main()
