"""
Cartera simulada de $50 'como en un exchange real'.

Sizing por RIESGO 1% por trade (modelo validado): en cada trade el apalancamiento
se ajusta al stop para arriesgar el 1% del capital actual, con TOPE 10x. El P&L en
dólares de cada trade cerrado actualiza el equity (compone).

Cuenta SOLO los trades cerrados DESPUÉS de inicializar (los abiertos ahora cuando
cierren + los futuros). Los ya cerrados antes de arrancar quedan excluidos.

Estado en portfolio_state.json. Ver: python main.py portfolio
"""
import json
import os

PORTF_FILE = os.path.join(os.path.dirname(__file__), "portfolio_state.json")
START = 50.0
MAX_LEV = 10.0
RISK_PCT = 1.0   # % del equity arriesgado por trade


def _load():
    if os.path.exists(PORTF_FILE):
        try:
            with open(PORTF_FILE) as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _save(st):
    with open(PORTF_FILE, "w") as f:
        json.dump(st, f, indent=2)


def init_portfolio(conn, start=START):
    """Crea la cartera si no existe, excluyendo los trades YA cerrados al arrancar."""
    st = _load()
    if st:
        return st
    cur = conn.execute("SELECT id FROM paper_trades WHERE status='closed'")
    excluded = [r[0] for r in cur.fetchall()]
    st = {"equity": start, "start_equity": start, "excluded": excluded,
          "counted": [], "history": []}
    _save(st)
    return st


def update_portfolio(conn):
    """Procesa los trades recién cerrados (no excluidos, no contados) y actualiza el
    equity con el modelo de riesgo 1% / tope 10x. Devuelve (nuevos, estado)."""
    st = _load()
    if st is None:
        st = init_portfolio(conn)
    excl = set(st["excluded"]); cnt = set(st["counted"])
    cur = conn.execute(
        "SELECT id,symbol,direction,risk_pct,pnl_pct,exit_reason,opened_at "
        "FROM paper_trades WHERE status='closed' ORDER BY exit_ts")
    new = []
    for tid, sym, dr, rp, pnl, er, oa in cur.fetchall():
        if tid in excl or tid in cnt or pnl is None:
            continue
        rp = rp if (rp and rp > 0) else 1.0
        lev = min(RISK_PCT / rp, MAX_LEV)        # apalancamiento para arriesgar 1% dado el stop
        dollar = st["equity"] * lev * (pnl / 100.0)
        st["equity"] += dollar
        st["counted"].append(tid); cnt.add(tid)
        rec = {"id": tid, "symbol": sym, "dir": dr, "pnl_pct": round(pnl, 3),
               "lev": round(lev, 2), "dollar": round(dollar, 4),
               "equity": round(st["equity"], 4), "reason": er, "opened_at": oa}
        st["history"].append(rec)
        new.append(rec)
    _save(st)
    return new, st


def print_portfolio():
    st = _load()
    print(f"\n{'='*60}")
    print(f"  CARTERA SIMULADA  (riesgo 1%/trade, tope 10x)")
    print(f"{'='*60}")
    if st is None:
        print("  (sin inicializar; se crea en el próximo ciclo del paper)")
        print(f"{'='*60}\n"); return
    n = len(st["history"])
    ret = (st["equity"] / st["start_equity"] - 1) * 100
    print(f"  Capital inicial: ${st['start_equity']:.2f}")
    print(f"  Capital actual:  ${st['equity']:.2f}  ({ret:+.1f}%)")
    print(f"  Trades contados: {n}")
    if n:
        wins = sum(1 for h in st["history"] if h["dollar"] > 0)
        print(f"  Aciertos:        {wins}/{n} ({wins/n*100:.0f}%)")
        print(f"\n  Últimos trades:")
        for h in st["history"][-12:]:
            print(f"    {h['symbol'][:14]:14} {h['dir']:5} {h['reason'] or '':9} "
                  f"{h['pnl_pct']:+6.2f}% x{h['lev']:.1f} -> ${h['dollar']:+.3f} "
                  f"| equity ${h['equity']:.2f}")
    print(f"{'='*60}\n")
