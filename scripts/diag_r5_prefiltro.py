"""¿Es seguro un prefiltro regex si la query se amplía (sin ancla _FINANCIAL)?

Mide el prefiltro contra la ANOTACIÓN MANUAL de julio (180 noticias con
`rel_humana` 0/1), que es ground truth real y ya existe. Responde:

  - ¿Cuánto volumen quita el prefiltro?            -> ahorro de LLM
  - ¿Cuántas noticias RELEVANTES mata por error?   -> el costo que importa
  - ¿Cuántas irrelevantes deja pasar?              -> lo cubre la taxonomía

ASIMETRÍA DE DISEÑO: un falso positivo del prefiltro descarta una noticia real
SIN APELACIÓN; un falso negativo solo cuesta una llamada al LLM (~12 s). Por eso
el prefiltro debe ser CONSERVADOR y solo atrapar lo inequívoco.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
ANOTADA = INTERIM / "r5_validacion_anotada.csv"


def _norm(s: str) -> str:
    s = str(s).lower()
    for a, b in zip("áéíóúñ", "aeioun"):
        s = s.replace(a, b)
    return s


# ── Prefiltro A: crónica de índice bursátil ──────────────────────────────
IDX = [
    r"\bbvl\b.*\b(cierr|sub|baj|retroced|avanz|gan|pierd|opera|abr|cae|cay)",
    r"\b(indice|indices)\b.*\bbvl\b",
    r"bolsa de valores de lima",
    r"bolsa (limena|limeña)",
    r"bolsa de lima",
    r"\bindice (general|selectivo|referencial)\b",
    r"s&p/?bvl",
    r"papeles lideres",
]

# ── Prefiltro B: patrocinio / RSE / deporte / promoción ──────────────────
# CONSERVADOR a propósito: solo patrones inequívocos. Se evita "campaña" suelta
# (captura "campaña navideña: venta de panetones", que es OPERACIONAL real).
PAT = [
    r"\bpatrocin",
    r"\bauspici",
    r"\bteleton\b",
    r"\bdona(cion|ciones|ra|ron|do)\b",
    r"\bvoluntariado\b",
    r"responsabilidad social",
    r"\b(copa|torneo|campeonato|maraton|mundial) ",
    r"\bseleccion peruana\b",
    r"\bnavidena? escolar\b",
    r"utiles escolares",
]

IDX_RE = re.compile("|".join(IDX))
PAT_RE = re.compile("|".join(PAT))


def marca(title: str) -> str:
    t = _norm(title)
    if IDX_RE.search(t):
        return "indice"
    if PAT_RE.search(t):
        return "patrocinio"
    return "pasa"


# ─────────────────────────────────────────────────────────────────────────
print("=" * 78)
print("1. LA ANOTACIÓN MANUAL DISPONIBLE")
print("=" * 78)
an = pd.read_csv(ANOTADA)
print(f"  filas: {len(an)}")
print(f"  columnas: {list(an.columns)}")
if "rel_humana" in an.columns:
    an = an[an["rel_humana"].notna()].copy()
    an["rel_humana"] = an["rel_humana"].astype(int)
    print(f"  relevantes: {an.rel_humana.sum()}/{len(an)} ({an.rel_humana.mean():.1%})")
    print("  por activo:")
    for t, g in an.groupby("ticker"):
        print(f"    {t:<10} {int(g.rel_humana.sum()):>3}/{len(g):<3} ({g.rel_humana.mean():>5.1%})")

print()
print("=" * 78)
print("2. EL PREFILTRO CONTRA LA ANOTACIÓN HUMANA  (lo que de verdad importa)")
print("=" * 78)
an["marca"] = an["title"].apply(marca)
tab = pd.crosstab(an["marca"], an["rel_humana"])
tab.columns = [f"humano_rel={c}" for c in tab.columns]
print(tab.to_string())

descartadas = an[an.marca != "pasa"]
print()
print(f"  Descartadas por el prefiltro : {len(descartadas)}/{len(an)} ({len(descartadas)/len(an):.1%})")
if len(descartadas):
    fp = int(descartadas.rel_humana.sum())
    print(f"  De ellas, RELEVANTES (error) : {fp}  -> tasa de error {fp/len(descartadas):.1%}")
    print(f"  Relevantes perdidas del total: {fp}/{int(an.rel_humana.sum())} "
          f"({fp/max(an.rel_humana.sum(),1):.1%} de todas las relevantes)")
pasan = an[an.marca == "pasa"]
print(f"  Sobreviven al prefiltro      : {len(pasan)} | relevancia entre ellas "
      f"{pasan.rel_humana.mean():.1%} (era {an.rel_humana.mean():.1%})")

print()
print("  --- Noticias RELEVANTES que el prefiltro mataría (revisar una a una) ---")
err = descartadas[descartadas.rel_humana == 1]
if err.empty:
    print("    (ninguna)")
for _, r in err.iterrows():
    print(f"    [{r['marca']}] {r['ticker']}: {str(r['title'])[:100]}")

print()
print("=" * 78)
print("3. VOLUMEN QUE AHORRARÍA SOBRE EL CORPUS COMPLETO")
print("=" * 78)
tot = []
for p in sorted(RAW.glob("news_*.parquet")):
    d = pd.read_parquet(p)
    if d.empty:
        continue
    d = d[["title"]].copy()
    d["ticker"] = p.stem.replace("news_", "")
    tot.append(d)
allt = pd.concat(tot, ignore_index=True)
allt["marca"] = allt["title"].apply(marca)

print(f"  {'Activo':<12} {'total':>7} {'índice':>8} {'patroc.':>8} {'pasa':>7} {'ahorro':>8}")
print("-" * 54)
for tk, g in allt.groupby("ticker"):
    n = len(g)
    i = int((g.marca == "indice").sum())
    pt = int((g.marca == "patrocinio").sum())
    ps = int((g.marca == "pasa").sum())
    print(f"  {tk:<12} {n:>7} {i:>8} {pt:>8} {ps:>7} {(n-ps)/n:>7.1%}")
n = len(allt)
ps = int((allt.marca == "pasa").sum())
print("-" * 54)
print(f"  {'TOTAL':<12} {n:>7} {int((allt.marca=='indice').sum()):>8} "
      f"{int((allt.marca=='patrocinio').sum()):>8} {ps:>7} {(n-ps)/n:>7.1%}")
print(f"\n  Horas de LLM ahorradas a 12 s/artículo: {(n-ps)*12/3600:.1f} h de {n*12/3600:.1f} h")

print()
print("  --- 20 titulares marcados como PATROCINIO (verificar que sean ruido) ---")
for t in allt.loc[allt.marca == "patrocinio", "title"].drop_duplicates().head(20):
    print(f"    X {t[:105]}")
