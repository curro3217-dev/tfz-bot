"""
PANEL DE ESTADO en un comando (2026-07-18, idea del articulo "TradingBotV2":
un dashboard para ver todo de un vistazo, en version austera y honesta).

  python estado.py          # estado de las 4 mediciones forward + el asistente

Solo LEE (ejecuta los --status canonicos de cada modulo, nada de recalcular a
mano). En el PC activa INSECURE_SSL=1 solo si no estaba definido.
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ENV = dict(os.environ)
ENV.setdefault("INSECURE_SSL", "1")
ENV.setdefault("PYTHONIOENCODING", "utf-8")

BLOQUES = [
    ("EMA 9/21 BTC diario (agresiva, sellada 14-jul)",
     ["ema_cross_paper.py", "--status"]),
    ("Ichimoku BTC diario (paracaidas, sellada 15-jul)",
     ["ichimoku_paper.py", "--status"]),
    ("Sizing GARCH vs 1x sobre cruces EMA (sellada 22-jul)",
     ["garch_sizing_paper.py", "--status"]),
    ("Momentum viernes->sabado (sellada 3-jul)",
     ["weekend_paper.py", "--status"]),
    ("Prima de Coinbase (sellada 3-jul)",
     ["premium_paper.py", "--status"]),
    ("Asistente TFZ (micro_pullback RETIRADO 16-jul; solo alertas F)",
     ["main.py", "paper", "--status"]),
]


def main():
    print("=" * 64)
    print("  ESTADO GENERAL — mediciones paper (nada es dinero real)")
    print("=" * 64)
    for titulo, args in BLOQUES:
        print(f"\n### {titulo}")
        try:
            r = subprocess.run([sys.executable, os.path.join(BASE, args[0]), *args[1:]],
                               cwd=BASE, env=ENV, capture_output=True,
                               text=True, encoding="utf-8", timeout=600)
            out = (r.stdout or "").strip()
            print(out if out else f"  (sin salida; codigo {r.returncode})")
            if r.returncode != 0:
                print(f"  [AVISO] termino con error {r.returncode}: "
                      f"{(r.stderr or '').strip().splitlines()[-1] if r.stderr else '?'}")
        except Exception as e:
            print(f"  [ERROR] no se pudo ejecutar: {e}")
    print("\n(Lecciones aprendidas: LECCIONES.md | historial de cambios: CHANGELOG.md)")


if __name__ == "__main__":
    main()
