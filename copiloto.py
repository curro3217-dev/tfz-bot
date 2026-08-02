"""
COPILOTO de ejecucion (sistema Krasnov). NO elige moneda (eso no se detecta bien; lo hace
el humano). Dado moneda + lado + nivel objetivo, devuelve el PLAN de trade mecanico:
  - entrada  = ruptura de la consolidacion reciente (o el nivel que le pases)
  - stop     = estructura (extremo opuesto de la consolidacion), avisando si el riesgo > 2%
  - TP       = el nivel objetivo que le pasas (o sugerencia de baja confianza si no)
  - R:R y veredicto TRADEABLE (>=3:1) / DESCARTAR
Tambien evalua un plan sobre datos historicos (WIN/LOSS/SCRATCH) para comprobar resultados.

ALCANCE (leccion 12): la EJECUCION esta encodeada y probada sobre las calls de Krasnov
(acierto estricto 56%, esperanza +0.17R/trade; el viejo "81%" contaba breakevens como wins).
El copiloto NO valida la SELECCION (que moneda) — eso lo aporta el humano. Los resultados
medidos usan objetivos dados por el humano; NO prueban que tus picks igualen a los de Mark.
"""
import os
import sys
import json
import datetime
import numpy as np

os.environ.setdefault("INSECURE_SSL", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
JOURNAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "copiloto_journal.json")

CONSOL_LB = 12       # velas de consolidacion reciente (3h en 15m)
STRUCT_LB = 12       # velas para el stop de estructura
BUFFER = 0.001       # colchon del stop (0.1%)
RISK_CAP = 0.02      # stop <= 2% (regla de Krasnov)
RR_MIN = 3.0         # R:R minimo (1:3)
COST_R = 0.0         # coste por viaje en R (se puede pasar en el check)


def _fetch(coin, timeframe, since=None, limit=220):
    from data_fetcher import fetch_ohlcv
    from config import TFZConfig, config_for_timeframe
    cfg = config_for_timeframe(TFZConfig(), timeframe)
    sym = coin if "/" in coin else coin + "/USDT:USDT"
    try:
        return fetch_ohlcv(sym, timeframe, limit=limit, since=since, config=cfg)
    except Exception:
        return None       # simbolo inexistente/delistado o error de red -> sin datos


def build_plan(coin, side="long", target=None, asof=None, timeframe="15m"):
    """Devuelve el plan de trade mecanico. side: 'long'|'short'. target: nivel de TP (opcional)."""
    side = side.lower()
    since = None
    if asof is not None:
        adt = asof if isinstance(asof, datetime.datetime) else datetime.datetime.fromisoformat(asof)
        since = int((adt - datetime.timedelta(hours=60)).timestamp() * 1000)
    df = _fetch(coin, timeframe, since=since)
    if df is None or len(df) < CONSOL_LB + 5:
        return {"coin": coin, "error": "sin datos suficientes"}
    H = df["high"].values.astype(float); L = df["low"].values.astype(float); C = df["close"].values.astype(float)
    i = len(df) - 1
    price = C[i]
    hi = H[i - CONSOL_LB:i + 1].max()      # techo de la consolidacion
    lo = L[i - CONSOL_LB:i + 1].min()      # suelo de la consolidacion

    if side == "long":
        entry = hi                          # ruptura al alza
        stop = lo * (1 - BUFFER)            # estructura debajo
    else:
        entry = lo                          # ruptura a la baja
        stop = hi * (1 + BUFFER)            # estructura encima

    risk = abs(entry - stop) / entry
    # TP: el que te da el humano; si no, sugerencia = siguiente swing high/low (baja confianza)
    tp_src = "humano"
    if target is None:
        tp, tp_src = _suggest_target(H, L, i, price, side), "sugerido(baja confianza)"
    else:
        tp = float(target)

    plan = {"coin": coin, "side": side, "price": round(price, 8), "entry": round(entry, 8),
            "stop": round(stop, 8), "risk_pct": round(risk * 100, 2), "tp_src": tp_src}
    if tp is None:
        plan.update({"tp": None, "rr": None, "veredicto": "SIN OBJETIVO CLARO -> no operar"})
        return plan
    reward = (tp - entry) if side == "long" else (entry - tp)
    rr = reward / abs(entry - stop) if reward > 0 else 0.0
    plan["tp"] = round(tp, 8)
    plan["rr"] = round(rr, 2)
    reasons = []
    if risk > RISK_CAP:
        reasons.append(f"stop ancho ({risk*100:.1f}%>2%)")
    if rr < RR_MIN:
        reasons.append(f"R:R {rr:.1f}<3")
    if reward <= 0:
        reasons.append("objetivo mal puesto (no da beneficio)")
    plan["veredicto"] = "TRADEABLE" if not reasons else "DESCARTAR: " + ", ".join(reasons)
    return plan


def _suggest_target(H, L, i, price, side, K=3, lookback=70):
    """Sugerencia tosca de nivel (swing high/low mas cercano en la direccion). BAJA CONFIANZA."""
    lo = max(K, i - lookback)
    if side == "long":
        cand = [H[j] for j in range(lo, i - K + 1) if H[j] == H[j - K:j + K + 1].max() and H[j] > price]
        return min(cand) if cand else None
    cand = [L[j] for j in range(lo, i - K + 1) if L[j] == L[j - K:j + K + 1].min() and L[j] < price]
    return max(cand) if cand else None


def evaluate(coin, side, entry, tp, since_dt, timeframe="5m", struct_lb=STRUCT_LB, cost_r=COST_R):
    """Replica OHLCV desde since_dt y resuelve el trade con stop de estructura + breakeven.
    Devuelve (resultado, R_realizado). R incluye coste por viaje si cost_r>0."""
    since = int(since_dt.timestamp() * 1000)
    df = _fetch(coin, timeframe, since=since, limit=800)
    if df is None or len(df) < 20:
        return "NO_DATA", None
    O = df["open"].values.astype(float); H = df["high"].values.astype(float)
    L = df["low"].values.astype(float); C = df["close"].values.astype(float)
    side = side.lower()
    win_bars = 288  # 24h de 5m para la ruptura confirmada
    if side == "long":
        brk = next((k for k in range(min(win_bars, len(C))) if C[k] >= entry), None)
    else:
        brk = next((k for k in range(min(win_bars, len(C))) if C[k] <= entry), None)
    if brk is None:
        return "NO_ENTRY", None
    if side == "long":
        stop = L[max(0, brk - struct_lb):brk + 1].min() * (1 - BUFFER)
        if stop >= entry:
            return "PARSE?", None
        R = entry - stop
    else:
        stop = H[max(0, brk - struct_lb):brk + 1].max() * (1 + BUFFER)
        if stop <= entry:
            return "PARSE?", None
        R = stop - entry
    be_trigger = entry + R if side == "long" else entry - R
    be = False
    for j in range(brk, len(C)):
        if side == "long":
            if not be and H[j] >= be_trigger:
                be = True
            cur_stop = entry if be else stop
            if L[j] <= cur_stop:
                return ("SCRATCH", 0.0 - cost_r) if be else ("LOSS", -1.0 - cost_r)
            if H[j] >= tp:
                return "WIN", (tp - entry) / R - cost_r
        else:
            if not be and L[j] <= be_trigger:
                be = True
            cur_stop = entry if be else stop
            if H[j] >= cur_stop:
                return ("SCRATCH", 0.0 - cost_r) if be else ("LOSS", -1.0 - cost_r)
            if L[j] <= tp:
                return "WIN", (entry - tp) / R - cost_r
    return "OPEN", None


def _fmt(plan):
    if "error" in plan:
        return f"{plan['coin']}: {plan['error']}"
    lines = [f"  {plan['coin']} {plan['side'].upper()}  (precio {plan['price']})",
             f"  entrada  {plan['entry']}   (ruptura de la consolidacion)",
             f"  stop     {plan['stop']}   (estructura, riesgo {plan['risk_pct']}%)"]
    if plan.get("tp") is not None:
        lines.append(f"  TP       {plan['tp']}   (fuente: {plan['tp_src']})   R:R = {plan['rr']}")
    lines.append(f"  >> {plan['veredicto']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DIARIO HACIA ADELANTE: apuntas cada trade que entra y `status` lo resuelve solo
# contra el precio real de MEXC segun van cerrando. Medicion forward, no backtest.
# ---------------------------------------------------------------------------
def _load():
    if os.path.exists(JOURNAL):
        with open(JOURNAL, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save(rows):
    with open(JOURNAL, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def add_trade(coin, side, entry, stop, tp, source="propio"):
    """Apunta un trade REAL que acabas de tomar (con tus precios reales)."""
    side = side.lower()
    entry, stop, tp = float(entry), float(stop), float(tp)
    R = abs(entry - stop)
    reward = (tp - entry) if side == "long" else (entry - tp)
    now = datetime.datetime.now()
    row = {"id": len(_load()) + 1, "added_local": now.strftime("%Y-%m-%d %H:%M"),
           "epoch_ms": int(now.timestamp() * 1000), "coin": coin.upper(), "side": side,
           "entry": entry, "stop": stop, "tp": tp,
           "rr": round(reward / R, 2) if R > 0 and reward > 0 else 0.0,
           "risk_pct": round(R / entry * 100, 2), "source": source,
           "status": "open", "result": None, "R": None, "closed_local": None}
    rows = _load()
    rows.append(row)
    _save(rows)
    return row


def _walk(side, entry, stop, tp, H, L):
    """Gestiona el trade ya DENTRO (entrada llena): breakeven a +1R, WIN/LOSS/SCRATCH/OPEN."""
    R = abs(entry - stop)
    if R <= 0:
        return "PARSE?", None
    be_trigger = entry + R if side == "long" else entry - R
    be = False
    for j in range(len(H)):
        if side == "long":
            if not be and H[j] >= be_trigger:
                be = True
            cur_stop = entry if be else stop
            if L[j] <= cur_stop:
                return ("SCRATCH", 0.0) if be else ("LOSS", -1.0)
            if H[j] >= tp:
                return "WIN", (tp - entry) / R
        else:
            if not be and L[j] <= be_trigger:
                be = True
            cur_stop = entry if be else stop
            if H[j] >= cur_stop:
                return ("SCRATCH", 0.0) if be else ("LOSS", -1.0)
            if L[j] <= tp:
                return "WIN", (entry - tp) / R
    return "OPEN", None


def resolve_open():
    """Recorre los trades abiertos y los cierra si el precio real ya toco TP o stop."""
    rows = _load()
    changed = 0
    for r in rows:
        if r["status"] != "open":
            continue
        df = _fetch(r["coin"], "5m", since=r["epoch_ms"], limit=1000)
        if df is None or len(df) < 3:
            continue
        H = df["high"].values.astype(float); L = df["low"].values.astype(float)
        res, R = _walk(r["side"], r["entry"], r["stop"], r["tp"], H, L)
        if res in ("WIN", "LOSS", "SCRATCH"):
            r["status"] = "closed"; r["result"] = res; r["R"] = round(R, 2)
            r["closed_local"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            changed += 1
    if changed:
        _save(rows)
    return rows, changed


def cmd_status():
    rows, changed = resolve_open()
    if not rows:
        print("Diario vacio. Apunta trades con:  python copiloto.py add COIN long|short ENTRY STOP TP [fuente]")
        return
    print(f"=== DIARIO COPILOTO ({len(rows)} trades; {changed} cerrados ahora) ===")
    for r in rows:
        tag = r["result"] or "OPEN"
        rr = f"{r['R']:+.2f}R" if r["R"] is not None else f"(R:R {r['rr']})"
        print(f"  #{r['id']:>2} {r['added_local']} {r['coin']:9} {r['side']:5} {tag:8} {rr}  [{r['source']}]")
    closed = [r for r in rows if r["status"] == "closed"]
    Rs = [r["R"] for r in closed if r["R"] is not None]
    w = sum(1 for r in closed if r["result"] == "WIN")
    l = sum(1 for r in closed if r["result"] == "LOSS")
    sc = sum(1 for r in closed if r["result"] == "SCRATCH")
    print(f"\nAbiertos: {sum(1 for r in rows if r['status']=='open')} | Cerrados: {len(closed)}")
    if w + l:
        print(f"Acierto (win/win+loss): {w}/{w+l} = {w/(w+l)*100:.0f}%  | breakeven(scratch): {sc}")
    if Rs:
        print(f"Esperanza por trade: {np.mean(Rs):+.2f}R  (n={len(Rs)})  | total: {np.sum(Rs):+.1f}R")
    print("\n(Medicion FORWARD sobre TUS trades reales. Compara contra 0 y contra el +0.17R de sus calls.)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "add":
        # python copiloto.py add COIN long|short ENTRY STOP TP [fuente]
        if len(args) < 6:
            print("uso: python copiloto.py add COIN long|short ENTRY STOP TP [fuente]")
            sys.exit(0)
        r = add_trade(args[1], args[2], args[3], args[4], args[5], args[6] if len(args) > 6 else "propio")
        print(f"Apuntado #{r['id']}: {r['coin']} {r['side'].upper()} entry {r['entry']} stop {r['stop']} "
              f"tp {r['tp']}  R:R {r['rr']}  riesgo {r['risk_pct']}%  [{r['source']}]")
    elif args and args[0] == "status":
        cmd_status()
    elif args and args[0] == "plan":
        # python copiloto.py plan COIN [long|short] [target]
        coin = args[1].upper()
        side = args[2] if len(args) > 2 else "long"
        target = float(args[3]) if len(args) > 3 else None
        print(_fmt(build_plan(coin, side, target)))
    elif args:
        # atajo: python copiloto.py COIN [long|short] [target]  (plan en vivo)
        coin = args[0].upper()
        side = args[1] if len(args) > 1 else "long"
        target = float(args[2]) if len(args) > 2 else None
        print(_fmt(build_plan(coin, side, target)))
    else:
        print("uso:")
        print("  python copiloto.py plan COIN long|short [target]      -> plan en vivo (entrada/stop/RR)")
        print("  python copiloto.py add COIN long|short ENTRY STOP TP [fuente]  -> apunta un trade")
        print("  python copiloto.py status                              -> resuelve y muestra el acumulado")
