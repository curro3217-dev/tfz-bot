"""
Robustez Monte Carlo del edge (idea tomada de Jesse).

Coge los trades de la config en vivo (score>=60 & rr>=6 + tendencia) y los
remuestrea miles de veces (bootstrap con reemplazo) para responder:
  - ¿qué % de escenarios acaba en positivo? (¿el edge es real o suerte?)
  - rango realista de retorno (P5/P50/P95) y de max drawdown
  - concentración: ¿cuánto del beneficio depende de unos pocos trades enormes?
    (clave en una estrategia asimétrica como esta)

Uso: python montecarlo_robustness.py [--sims 10000] [--score 60] [--rr 6]
"""
import argparse
import numpy as np
import pandas as pd

MOV = {"SIREN", "ESPORTS", "COAI", "EVAA", "BEAT", "STG", "H", "MEGA", "SOXL",
       "RIF", "VELVET", "TRUMP", "NEAR", "ADA", "WLD", "ZEC", "JTO"}
TREND_BLOCK = 5.0


def load(path, mov=False):
    d = pd.read_csv(path)
    d["base"] = d["symbol"].str.split("/").str[0]
    if mov:
        d = d[d["base"].isin(MOV)].copy()
        tr = d["trend_strength"]; il = d["direction_long"] == 1
        counter = ((il & (tr < 0)) | (~il & (tr > 0))) & (tr.abs() >= TREND_BLOCK)
        d = d[~counter]
    return d


def contributions(d, smin, rrmin, haircut=0.5, maxlev=10.0):
    """Net leveraged contribution per trade (lo que suma al retorno creíble)."""
    f = d[(d.total_score >= smin) & (d.rr_ratio >= rrmin)]
    rp = f["risk_pct"].where(f["risk_pct"] > 0, 1.0)
    lev = np.minimum(1.0 / rp, maxlev)
    return (lev * (f["pnl_pct"] - haircut) / 100.0 * 100).values  # en % de capital


def max_dd(curve):
    peak = np.maximum.accumulate(curve)
    return float(np.max(peak - curve)) if len(curve) else 0.0


def montecarlo(c, sims, rng):
    n = len(c)
    base = c.sum()
    finals = np.empty(sims); dds = np.empty(sims)
    for i in range(sims):
        s = rng.choice(c, size=n, replace=True)
        curve = np.cumsum(s)
        finals[i] = curve[-1]
        dds[i] = max_dd(curve)
    # concentración: cuota del top 5% de trades sobre el total positivo
    pos = c[c > 0]; top5 = np.sort(pos)[::-1][:max(1, int(0.05 * n))]
    conc = (top5.sum() / pos.sum() * 100) if pos.sum() > 0 else 0.0
    return base, finals, dds, conc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=10000)
    ap.add_argument("--score", type=int, default=60)
    ap.add_argument("--rr", type=float, default=6.0)
    args = ap.parse_args()
    rng = np.random.default_rng(42)

    univ = {
        "movers": load("ml_dataset_7m.csv", mov=True),
        "veteranas1": load("ml_dataset_older.csv"),
        "veteranas2": load("ml_dataset_older2.csv"),
        "jovenes8": load("ml_dataset_new8.csv"),
    }
    print(f"Config: score>={args.score} & rr>={args.rr} | {args.sims} simulaciones bootstrap\n")
    print(f"  {'universo':<11}{'n':>5}{'real':>8}{'%posit':>8}{'P5':>8}{'P50':>8}{'P95':>8}{'DD med':>8}{'DD P95':>8}{'top5%':>7}")
    print(f"  {'-'*11}{'-'*5}{'-'*8}{'-'*8}{'-'*8}{'-'*8}{'-'*8}{'-'*8}{'-'*8}{'-'*7}")
    for k, d in univ.items():
        c = contributions(d, args.score, args.rr)
        if len(c) < 20:
            print(f"  {k:<11}{len(c):>5}  (pocos trades)"); continue
        base, finals, dds, conc = montecarlo(c, args.sims, rng)
        pct_pos = (finals > 0).mean() * 100
        p5, p50, p95 = np.percentile(finals, [5, 50, 95])
        print(f"  {k:<11}{len(c):>5}{base:>+7.0f}%{pct_pos:>7.1f}%{p5:>+7.0f}%{p50:>+7.0f}%{p95:>+7.0f}%"
              f"{np.median(dds):>7.0f}%{np.percentile(dds,95):>7.0f}%{conc:>6.0f}%")

    print("\n  %posit = % de escenarios que acaban en positivo | P5/P50/P95 = retorno (percentiles)")
    print("  DD med/P95 = max drawdown típico y pesimista | top5% = cuota del 5% mejores trades sobre el beneficio")


if __name__ == "__main__":
    main()
