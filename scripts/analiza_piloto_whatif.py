"""Qué pasa con las métricas del Piloto A si se reasignan magnitudes.

El piloto mostró que `sector_macro` (magnitud 0.3 -> cuenta como RELEVANTE) se
volvió el basurero del modelo: 55 de 180 predicciones. Este script recalcula las
métricas bajo escenarios alternativos SIN volver a llamar al LLM, para separar
"el modelo no sirve" de "la magnitud que yo le asigné a una categoría está mal".
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.sentiment.taxonomia import TAXONOMIA

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--csv", default="piloto_r5_gemma3_4b.csv",
                help="archivo del piloto en data/interim")
args = ap.parse_args()

CSV = ROOT / "data" / "interim" / args.csv
print(f"Archivo: {CSV.name}\n")
res = pd.read_csv(CSV)
res = res[res.categoria.notna() & (res.categoria != "_error_parseo")].copy()
res["rel_humana"] = res["rel_humana"].astype(int)

print(f"Base: {len(res)} noticias | relevantes reales {res.rel_humana.mean():.1%}")
print("Recordatorio: rel_humana = 1  <=>  cat_humana en {empresa, sector}\n")


def metricas(nombre: str, cero_extra: set[str]) -> dict:
    """Relevante == magnitud > 0, con `cero_extra` forzadas a magnitud 0."""
    rel_pred = res["categoria"].map(
        lambda c: 0 if c in cero_extra else int(TAXONOMIA.get(c, (0.0, ""))[0] > 0))
    vp = int(((rel_pred == 1) & (res.rel_humana == 1)).sum())
    fp = int(((rel_pred == 1) & (res.rel_humana == 0)).sum())
    fn = int(((rel_pred == 0) & (res.rel_humana == 1)).sum())
    vn = int(((rel_pred == 0) & (res.rel_humana == 0)).sum())
    prec = vp / max(vp + fp, 1)
    rec = vp / max(vp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    acc = (vp + vn) / len(res)
    # Polaridad espuria: de las etiquetas CON SIGNO que sobreviven, cuántas son
    # sobre noticias irrelevantes.
    con_signo = res[(rel_pred == 1) & res.polaridad.isin(["positivo", "negativo"])]
    esp = (con_signo.rel_humana == 0).mean() if len(con_signo) else 0.0
    return {"escenario": nombre, "exactitud": acc, "precision": prec,
            "recall": rec, "f1": f1, "VP": vp, "FP": fp, "FN": fn,
            "signo": len(con_signo), "espuria": esp}


escenarios = [
    ("A. Actual (sector_macro = 0.3)", set()),
    ("B. sector_macro -> 0", {"sector_macro"}),
    ("C. sector_macro + analisis_opinion -> 0", {"sector_macro", "analisis_opinion"}),
]
filas = [metricas(n, s) for n, s in escenarios]
t = pd.DataFrame(filas)

print(f"{'Escenario':<42} {'exact':>6} {'prec':>6} {'recall':>7} {'F1':>6} "
      f"{'espuria':>8}")
print("-" * 80)
for _, r in t.iterrows():
    print(f"{r.escenario:<42} {r.exactitud:>6.1%} {r.precision:>6.1%} "
          f"{r.recall:>7.1%} {r.f1:>6.1%} {r.espuria:>8.1%}")
print("\n(v1 de referencia: relevancia efectiva 26%, polaridad espuria 49.0%)")

print("\n" + "=" * 80)
print("¿A DÓNDE VAN LAS PREDICCIONES DE sector_macro?")
print("=" * 80)
sm = res[res.categoria == "sector_macro"]
print(f"  {len(sm)} predicciones ({len(sm)/len(res):.1%} de la muestra)")
print(f"  De ellas, relevantes de verdad: {int(sm.rel_humana.sum())} "
      f"({sm.rel_humana.mean():.1%})")
if "cat_humana" in sm.columns:
    print("  Desglose por categoría humana:")
    for k, v in sm["cat_humana"].value_counts().items():
        print(f"    {k:<12} {v:>3}")

print("\n" + "=" * 80)
print("PRECISIÓN POR CATEGORÍA PREDICHA (¿cuáles son de fiar?)")
print("=" * 80)
print(f"  {'categoría':<24} {'mag':>4} {'n':>4} {'% relevante real':>17}")
print("-" * 54)
for cat, g in res.groupby("categoria"):
    mag = TAXONOMIA.get(cat, (0.0, ""))[0]
    marca = "  <-- fuga" if (mag > 0 and g.rel_humana.mean() < 0.5) else ""
    print(f"  {cat:<24} {mag:>4.1f} {len(g):>4} {g.rel_humana.mean():>16.1%}{marca}")

print("\n" + "=" * 80)
print("CREDITC1: el peor activo (38.9%) — ¿por qué?")
print("=" * 80)
bcp = res[res.ticker == "CREDITC1"]
print(pd.crosstab(bcp["categoria"], bcp["rel_humana"]).to_string())
