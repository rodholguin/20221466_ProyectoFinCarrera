"""Diagnóstico de integridad de R5 ANTES de la corrida grande del universo de 7.

Verifica sobre los parquets ya existentes (universo viejo):
  1. Columnas disponibles y si `text` trae cuerpo o viene vacío.
  2. Zona horaria de `publish_date` (¿UTC o local?) y su efecto en el corte diario.
  3. Tasa de duplicados por (título, fecha) — el FIX 3 pendiente.
  4. Dominios presentes (¿el allowlist con lstrip está filtrando bien?).
  5. Estructura del caché de sentimiento (¿guarda versión de prompt/modelo?).
No modifica nada. Solo lee.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"

print("=" * 72)
print("1. COLUMNAS Y CONTENIDO DE TEXTO")
print("=" * 72)
paths = sorted(RAW.glob("news_*.parquet"))
if not paths:
    print("  No hay parquets de noticias.")
    sys.exit(0)

sample = pd.read_parquet(paths[0])
print(f"  Archivo de muestra: {paths[0].name}  ({len(sample)} filas)")
print(f"  Columnas: {list(sample.columns)}")
for col in ("text", "title", "id", "url", "publish_date", "language"):
    if col in sample.columns:
        nn = sample[col].notna().sum()
        print(f"    {col:<14} no-nulos {nn}/{len(sample)}")
    else:
        print(f"    {col:<14} AUSENTE")

print()
print("=" * 72)
print("2. ZONA HORARIA DE publish_date")
print("=" * 72)
pdt = sample["publish_date"]
print(f"  dtype: {pdt.dtype}")
print(f"  tz   : {getattr(pdt.dtype, 'tz', None)}")
print(f"  min  : {pdt.min()}")
print(f"  max  : {pdt.max()}")
hours = pd.to_datetime(pdt).dt.hour
print("  Distribución por hora (si es LOCAL, debe caer de madrugada;")
print("  si es UTC, el pico se corre +5h respecto de la hora peruana):")
vc = hours.value_counts().sort_index()
for h, n in vc.items():
    bar = "#" * int(40 * n / vc.max())
    print(f"    {h:02d}h {n:>6}  {bar}")
madrugada = int(hours.isin([0, 1, 2, 3, 4]).sum())
print(f"  Artículos entre 00-04h: {madrugada} ({madrugada/len(hours):.1%})")
print("  -> Si es alto, `publish_date` está en UTC y esas notas son de la")
print("     TARDE/NOCHE peruana del día ANTERIOR: el corte diario las desplaza.")

print()
print("=" * 72)
print("3. DUPLICADOS (FIX 3 pendiente)")
print("=" * 72)
for p in paths:
    df = pd.read_parquet(p)
    if df.empty or "title" not in df.columns:
        continue
    t = df["title"].astype(str).str.strip().str.lower()
    d = pd.to_datetime(df["publish_date"]).dt.date
    key = pd.Series(list(zip(t, d)))
    dup = int(key.duplicated().sum())
    dup_t = int(t.duplicated().sum())
    print(f"  {p.stem:<22} n={len(df):>6}  dup(titulo,fecha)={dup:>5} ({dup/len(df):>5.1%})"
          f"   dup(solo titulo)={dup_t:>5} ({dup_t/len(df):>5.1%})")

print()
print("=" * 72)
print("4. DOMINIOS (verificación del allowlist / bug de lstrip)")
print("=" * 72)


def _domain_actual(url: str) -> str:
    """Réplica EXACTA de _filter_by_source en mediacloud_client.py."""
    try:
        return urlparse(str(url)).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _domain_correcto(url: str) -> str:
    try:
        net = urlparse(str(url)).netloc.lower()
        return net[4:] if net.startswith("www.") else net
    except Exception:
        return ""


all_urls = []
for p in paths:
    df = pd.read_parquet(p)
    if "url" in df.columns:
        all_urls += df["url"].astype(str).tolist()

dom_act = pd.Series([_domain_actual(u) for u in all_urls])
dom_cor = pd.Series([_domain_correcto(u) for u in all_urls])
difieren = (dom_act != dom_cor).sum()
print(f"  URLs totales: {len(all_urls)}")
print(f"  Dominios donde lstrip('www.') DIFIERE del strip correcto: {difieren}")
if difieren:
    ej = pd.DataFrame({"actual": dom_act, "correcto": dom_cor})
    ej = ej[ej.actual != ej.correcto].drop_duplicates().head(15)
    for _, r in ej.iterrows():
        print(f"    lstrip -> {r.actual!r:<28} correcto -> {r.correcto!r}")
print("  Top dominios presentes (tras el filtro ya aplicado):")
for dom, n in dom_cor.value_counts().head(12).items():
    print(f"    {dom:<28} {n:>6}")

print()
print("=" * 72)
print("5. ESTRUCTURA DEL CACHÉ DE SENTIMIENTO")
print("=" * 72)
cdir = INTERIM / "sentiment_cache"
caches = sorted(cdir.glob("cache_*.json")) if cdir.exists() else []
if not caches:
    print("  No hay cachés.")
else:
    c = json.loads(caches[0].read_text(encoding="utf-8"))
    k = next(iter(c))
    print(f"  Archivo: {caches[0].name}  entradas={len(c)}")
    print(f"  Ejemplo de clave : {k!r}")
    print(f"  Ejemplo de valor : {c[k]!r}")
    campos = set()
    for v in list(c.values())[:500]:
        campos |= set(v.keys())
    print(f"  Campos guardados : {sorted(campos)}")
    print("  -> ¿Incluye versión de prompt o modelo?  "
          f"{'SÍ' if ({'prompt_version', 'model'} & campos) else 'NO'}")
    total = sum(len(json.loads(p.read_text(encoding='utf-8'))) for p in caches)
    print(f"  Entradas cacheadas en TODOS los activos: {total}")

print()
print("=" * 72)
print("6. QUERIES: cobertura del universo VIGENTE en _build_query")
print("=" * 72)
from src.universe import Config
from src.sentiment.mediacloud_client import _build_query

cfg = Config.load(ROOT / "config.yaml")
for a in cfg.assets:
    q = _build_query(a)
    generica = q == f'"{a.name}"'
    marca = "  <-- GENÉRICA (cae al default)" if generica else ""
    print(f"  {a.bvl:<10} {q}{marca}")
