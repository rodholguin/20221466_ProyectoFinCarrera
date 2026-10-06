"""Muestra titulares reales para (a) calibrar el ancla _FINANCIAL y (b) diseñar
el regex del filtro de índice bursátil (FIX 1).

Experimento natural: CORAREC1 se descargó SIN ancla financiera (su entrada en
_build_query es solo '"Aceros Arequipa"'), mientras que CREDITC1/ALICORC1/
BUENAVC1/SAGAC1 sí llevaban `AND _FINANCIAL`. Comparar sus titulares muestra
qué deja pasar y qué bloquea el ancla.

OJO: MediaCloud aplica la query sobre el TEXTO COMPLETO, no solo el título, así
que simular el ancla sobre títulos es una prueba MÁS ESTRICTA que la real. Sirve
como indicación, no como réplica exacta.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

RAW = ROOT / "data" / "raw"

# Términos del ancla actual (mediacloud_client._FINANCIAL)
FINANCIAL_TERMS = ["accion", "acciones", "bolsa", "bvl", "utilidad", "inversion",
                   "mercado", "empresa", "minera", "produccion", "resultado",
                   "ganancia"]


def _norm(s: str) -> str:
    """Minúsculas sin tildes, para casar términos sin acentos."""
    s = str(s).lower()
    for a, b in zip("áéíóúñ", "aeioun"):
        s = s.replace(a, b)
    return s


def tiene_ancla(title: str) -> bool:
    t = _norm(title)
    return any(re.search(rf"\b{term}", t) for term in FINANCIAL_TERMS)


print("=" * 78)
print("A. TITULARES DE CORAREC1 (descargado SIN ancla financiera)")
print("=" * 78)
p = RAW / "news_CORAREC1.parquet"
df = pd.read_parquet(p)
titles = df["title"].astype(str)
con = titles[titles.apply(tiene_ancla)]
sin = titles[~titles.apply(tiene_ancla)]
print(f"  n={len(titles)}   pasan el ancla (en el TÍTULO): {len(con)} ({len(con)/len(titles):.1%})")
print(f"                     NO pasan el ancla:            {len(sin)} ({len(sin)/len(titles):.1%})")

print("\n  --- 20 que PASAN el ancla ---")
for t in con.drop_duplicates().head(20):
    print(f"    + {t[:110]}")

print("\n  --- 20 que NO pasan el ancla (¿se perdería algo útil?) ---")
for t in sin.drop_duplicates().head(20):
    print(f"    - {t[:110]}")

print()
print("=" * 78)
print("B. TITULARES DE ALICORC1 (descargado CON ancla) — ¿qué se coló igual?")
print("=" * 78)
df2 = pd.read_parquet(RAW / "news_ALICORC1.parquet")
for t in df2["title"].astype(str).drop_duplicates().head(30):
    print(f"    · {t[:110]}")

print()
print("=" * 78)
print("C. CANDIDATOS A REGEX DE ÍNDICE BURSÁTIL (FIX 1)")
print("=" * 78)
PATRONES = {
    "bvl_cierre":    r"\bbvl\b.*\b(cierr|sub|baj|retroced|avanz|gan|pierd|opera|abr)",
    "bolsa_lima":    r"bolsa de valores de lima|bolsa limena|bolsa limeña",
    "indice_gral":   r"\bindice (general|selectivo)\b|s&p/bvl|sp/bvl",
    "jornada":       r"\b(jornada|sesion) (bursatil|de la bolsa)",
    "alza_baja_gen": r"\b(al alza|a la baja)\b.*\bbolsa\b",
    "acciones_pct":  r"\(\s*-?\d+[\.,]\d+\s*%\s*\)",   # "Aceros Arequipa (3.00%)"
}

todos = []
for p in sorted(RAW.glob("news_*.parquet")):
    d = pd.read_parquet(p)
    d = d[["title"]].copy()
    d["ticker"] = p.stem.replace("news_", "")
    todos.append(d)
allt = pd.concat(todos, ignore_index=True)
allt["_n"] = allt["title"].apply(_norm)

marcado = pd.Series(False, index=allt.index)
for nombre, pat in PATRONES.items():
    m = allt["_n"].str.contains(pat, regex=True, na=False)
    marcado |= m
    print(f"  {nombre:<16} captura {int(m.sum()):>5} de {len(allt)} ({m.mean():>5.1%})")
print(f"  {'UNIÓN':<16} captura {int(marcado.sum()):>5} de {len(allt)} ({marcado.mean():>5.1%})")

print("\n  Desglose por activo (qué % del corpus se descartaría):")
for tk, g in allt.assign(_m=marcado).groupby("ticker"):
    print(f"    {tk:<12} {int(g._m.sum()):>5}/{len(g):<6} ({g._m.mean():>5.1%})")

print("\n  --- 25 titulares CAPTURADOS por el regex (verificar que sean ruido) ---")
for t in allt.loc[marcado, "title"].drop_duplicates().head(25):
    print(f"    X {t[:110]}")

print("\n  --- 15 titulares NO capturados (verificar que no sea ruido de índice) ---")
for t in allt.loc[~marcado, "title"].drop_duplicates().head(15):
    print(f"    . {t[:110]}")
