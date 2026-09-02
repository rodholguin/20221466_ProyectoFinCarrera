"""¿Se complementan los modelos? Ensemble sobre la decisión de RELEVANCIA.

Motivación: los modelos evaluados fallan en direcciones OPUESTAS —gemma3:4b es
sobre-inclusivo (recall alto, precisión baja) y gemma3:12b / qwen2.5:14b son
sobre-excluyentes (precisión alta, recall bajo). Si sus errores no están
correlacionados, combinarlos puede superar a cualquiera por separado.

Ahora que la velocidad no es restricción (0.8-1.6 s/artículo en el servidor),
correr dos modelos sobre el corpus completo es viable: ~2.4 s/artículo = 7.6 h.

Reglas evaluadas:
  UNIÓN         relevante si CUALQUIERA lo dice   -> maximiza recall
  INTERSECCIÓN  relevante si AMBOS lo dicen       -> maximiza precisión
  MAYORÍA       (con 3+ modelos) voto mayoritario
"""
from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.sentiment.taxonomia import ERROR, es_relevante

INTERIM = ROOT / "data" / "interim"

# Una corrida por modelo (se omite el duplicado CPU/GPU de gemma3:4b v2.1)
CORRIDAS = {
    "gemma3:4b":   "piloto_r5_gemma3_4b_v21_gpu.csv",
    "gemma3:12b":  "piloto_r5_gemma3_12b_v21.csv",
    "gemma3:27b":  "piloto_r5_gemma3_27b_v21.csv",
    "qwen2.5:14b": "piloto_r5_qwen25_14b_v21.csv",
    "qwen2.5:32b": "piloto_r5_qwen25_32b_v21.csv",
}


def carga(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    d = pd.read_csv(path)
    d = d[d["rel_humana"].notna()].copy()
    d["rel_humana"] = d["rel_humana"].astype(int)
    d["ok"] = d.categoria.notna() & (d.categoria != ERROR)
    d["rel"] = d["categoria"].map(lambda c: int(es_relevante(c)) if isinstance(c, str) else 0)
    return d[["n", "ticker", "title", "rel_humana", "rel", "ok"]]


def met(pred: pd.Series, real: pd.Series) -> dict:
    vp = int(((pred == 1) & (real == 1)).sum())
    fp = int(((pred == 1) & (real == 0)).sum())
    fn = int(((pred == 0) & (real == 1)).sum())
    vn = int(((pred == 0) & (real == 0)).sum())
    p = vp / max(vp + fp, 1)
    r = vp / max(vp + fn, 1)
    return {"exact": (vp + vn) / len(pred), "prec": p, "rec": r,
            "f1": 2 * p * r / max(p + r, 1e-9), "VP": vp, "FP": fp, "FN": fn}


datos = {}
for nombre, arch in CORRIDAS.items():
    d = carga(INTERIM / arch)
    if d is not None:
        datos[nombre] = d.set_index("n")

if len(datos) < 2:
    print("Hacen falta al menos 2 corridas.")
    sys.exit(0)

print(f"Modelos disponibles: {', '.join(datos)}\n")

# Base común: noticias que TODOS clasificaron sin error
base = None
for d in datos.values():
    idx = set(d[d.ok].index)
    base = idx if base is None else (base & idx)
base = sorted(base)
real = datos[next(iter(datos))].loc[base, "rel_humana"]
print(f"Base común (todos sin error de parseo): {len(base)} noticias, "
      f"{real.mean():.1%} relevantes\n")

print("=" * 78)
print("1. INDIVIDUALES sobre la base común")
print("=" * 78)
print(f"  {'modelo':<14} {'exact':>6} {'prec':>6} {'recall':>7} {'F1':>6}")
print("-" * 44)
for nombre, d in datos.items():
    m = met(d.loc[base, "rel"], real)
    print(f"  {nombre:<14} {m['exact']:>6.1%} {m['prec']:>6.1%} "
          f"{m['rec']:>7.1%} {m['f1']:>6.1%}")

print()
print("=" * 78)
print("2. ACUERDO ENTRE PARES (¿son redundantes o complementarios?)")
print("=" * 78)
print(f"  {'par':<30} {'acuerdo':>8} {'kappa':>7}")
print("-" * 48)
for a, b in itertools.combinations(datos, 2):
    ra, rb = datos[a].loc[base, "rel"], datos[b].loc[base, "rel"]
    ac = (ra == rb).mean()
    # kappa de Cohen
    pa, pb = ra.mean(), rb.mean()
    pe = pa * pb + (1 - pa) * (1 - pb)
    kappa = (ac - pe) / (1 - pe) if pe < 1 else float("nan")
    print(f"  {a + ' vs ' + b:<30} {ac:>8.1%} {kappa:>7.2f}")
print("\n  Acuerdo bajo = errores poco correlacionados = el ensemble puede ayudar.")

print()
print("=" * 78)
print("3. ENSEMBLES DE DOS (unión e intersección)")
print("=" * 78)
print(f"  {'combinación':<34} {'regla':<7} {'exact':>6} {'prec':>6} {'recall':>7} {'F1':>6}")
print("-" * 72)
mejores = []
for a, b in itertools.combinations(datos, 2):
    ra, rb = datos[a].loc[base, "rel"], datos[b].loc[base, "rel"]
    for regla, pred in (("unión", ((ra + rb) > 0).astype(int)),
                        ("inters.", ((ra + rb) == 2).astype(int))):
        m = met(pred, real)
        mejores.append((m["f1"], m["prec"], f"{a} + {b}", regla, m))
        print(f"  {a + ' + ' + b:<34} {regla:<7} {m['exact']:>6.1%} {m['prec']:>6.1%} "
              f"{m['rec']:>7.1%} {m['f1']:>6.1%}")

if len(datos) >= 3:
    print()
    print("=" * 78)
    print("4. VOTO MAYORITARIO (todos los modelos)")
    print("=" * 78)
    votos = sum(d.loc[base, "rel"] for d in datos.values())
    pred = (votos > len(datos) / 2).astype(int)
    m = met(pred, real)
    print(f"  mayoría de {len(datos)}: exact {m['exact']:.1%} | prec {m['prec']:.1%} | "
          f"recall {m['rec']:.1%} | F1 {m['f1']:.1%}")

print()
print("=" * 78)
print("5. MEJORES COMBINACIONES por F1 y por PRECISIÓN")
print("=" * 78)
por_f1 = sorted(mejores, key=lambda x: -x[0])[:3]
por_prec = sorted(mejores, key=lambda x: -x[1])[:3]
print("  Por F1:")
for f1, pr, comb, regla, m in por_f1:
    print(f"    {comb} ({regla}): F1 {f1:.1%}, prec {pr:.1%}, recall {m['rec']:.1%}")
print("  Por precisión (criterio principal de seleccion_modelo_R5.txt §2):")
for f1, pr, comb, regla, m in por_prec:
    print(f"    {comb} ({regla}): prec {pr:.1%}, recall {m['rec']:.1%}, F1 {f1:.1%}")
