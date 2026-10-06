"""¿Cuánto cuesta ejecutar en t+1? Evidencia para defenderlo en la tesis.

PROBLEMA: `publish_date` de MediaCloud es una FECHA SIN HORA (verificado en
scripts/diag_r5_integridad.py: 100% de los artículos en la hora 00). No podemos
saber si una nota salió antes o después del cierre de la BVL (15:00 Lima). Si el
agente pudiera operar el MISMO día T al que se atribuye la noticia, estaría
potencialmente usando información que el mercado ya incorporó -> look-ahead.

FIX PROPUESTO: el agente observa el sentimiento del día T pero solo puede operar
al precio de T+1.

LO QUE ESTE SCRIPT MIDE (y por qué es válido pese a que las etiquetas están mal):
usa solo |retorno| y la BANDERA de si hubo noticia, NO la polaridad. O sea es
INDEPENDIENTE de la calidad del etiquetado, que es justamente lo que está roto.

  1. ¿Se disparan los precios el mismo día T de la noticia? (el costo de t+1)
  2. ¿Y en T+1? (lo que el agente sí puede capturar)
  3. Ventana de evento T-2..T+2.
  4. ¿Qué fracción de los movimientos extremos cae en día con noticia?
  5. TODO LO ANTERIOR, separando las noticias de ÍNDICE BURSÁTIL — que son
     literalmente crónicas del movimiento del mercado y por tanto están
     mecánicamente correlacionadas con días de movimiento grande. Sin esta
     separación, el resultado sale inflado por construcción.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

RAW = ROOT / "data" / "raw"
PANEL = ROOT / "data" / "processed" / "dataset_unificado.parquet"

# Regex de índice bursátil, versión ampliada tras ver titulares reales
IDX_PATTERNS = [
    r"\bbvl\b.*\b(cierr|sub|baj|retroced|avanz|gan|pierd|opera|abr|cae|cay)",
    r"\b(indice|indices)\b.*\bbvl\b",
    r"bolsa de valores de lima",
    r"bolsa (limena|limeña)",
    r"bolsa de lima",
    r"\bindice (general|selectivo|referencial)\b",
    r"s&p/?bvl",
    r"papeles lideres",
]
IDX_RE = re.compile("|".join(IDX_PATTERNS))


def _norm(s: str) -> str:
    s = str(s).lower()
    for a, b in zip("áéíóúñ", "aeioun"):
        s = s.replace(a, b)
    return s


def es_indice(title: str) -> bool:
    return bool(IDX_RE.search(_norm(title)))


# ─────────────────────────────────────────────────────────────────────────
panel = pd.read_parquet(PANEL)
print("=" * 78)
print("PANEL")
print("=" * 78)
print(f"  filas={len(panel)}  columnas={len(panel.columns)}")
cols_ret = [c for c in panel.columns if "ret" in c.lower()]
print(f"  columnas de retorno: {cols_ret}")
RET = "ret_1d" if "ret_1d" in panel.columns else cols_ret[0]
print(f"  usando: {RET}")
panel["date"] = pd.to_datetime(panel["date"])
panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)

# Retornos adelantados/atrasados por activo
g = panel.groupby("ticker")[RET]
for k in (1, 2):
    panel[f"ret_lead{k}"] = g.shift(-k)
    panel[f"ret_lag{k}"] = g.shift(k)

# ─────────────────────────────────────────────────────────────────────────
# Banderas de noticia reconstruidas desde el corpus crudo, separando índice
# ─────────────────────────────────────────────────────────────────────────
flags = []
for p in sorted(RAW.glob("news_*.parquet")):
    tk = p.stem.replace("news_", "")
    d = pd.read_parquet(p)
    if d.empty:
        continue
    d = d[["title", "publish_date"]].copy()
    d["fecha"] = pd.to_datetime(d["publish_date"]).dt.normalize()
    d["idx"] = d["title"].apply(es_indice)
    agg = (d.groupby("fecha")
             .agg(n_tot=("title", "size"), n_idx=("idx", "sum"))
             .reset_index())
    agg["n_real"] = agg["n_tot"] - agg["n_idx"]
    agg["ticker"] = tk
    flags.append(agg)
news = pd.concat(flags, ignore_index=True)

# Roll-forward al siguiente día hábil del panel (igual que R6)
out = []
for tk, gn in news.groupby("ticker"):
    fechas_panel = panel.loc[panel.ticker == tk, "date"].sort_values().unique()
    if len(fechas_panel) == 0:
        continue
    idx = np.searchsorted(fechas_panel, gn["fecha"].values, side="left")
    ok = idx < len(fechas_panel)
    gg = gn[ok].copy()
    gg["date"] = fechas_panel[idx[ok]]
    out.append(gg.groupby(["ticker", "date"], as_index=False)[["n_tot", "n_idx", "n_real"]].sum())
news_al = pd.concat(out, ignore_index=True)

df = panel.merge(news_al, on=["ticker", "date"], how="left")
for c in ("n_tot", "n_idx", "n_real"):
    df[c] = df[c].fillna(0)
df["hay_noticia"] = (df.n_tot > 0).astype(int)
df["hay_real"] = (df.n_real > 0).astype(int)
df["solo_indice"] = ((df.n_idx > 0) & (df.n_real == 0)).astype(int)

# Excluir días sin cotización (precio stale): ahí el retorno es 0 artificial
if "is_no_trade" in df.columns:
    df = df[df.is_no_trade == 0]
    print(f"  (se excluyen días sin cotización; quedan {len(df)} filas)")

df["abs_ret"] = df[RET].abs()

# ─────────────────────────────────────────────────────────────────────────
print()
print("=" * 78)
print("1. |RETORNO| EN DÍA DE NOTICIA vs DÍA SIN NOTICIA  (el costo de t+1)")
print("=" * 78)
print(f"  {'Activo':<10} {'|ret| s/not':>11} {'|ret| c/not':>11} {'razón':>7} "
      f"{'c/ REAL':>9} {'razón':>7} {'solo índice':>12} {'razón':>7}")
print("-" * 84)
for tk, gg in df.groupby("ticker"):
    sin_n = gg.loc[gg.hay_noticia == 0, "abs_ret"].mean()
    con_n = gg.loc[gg.hay_noticia == 1, "abs_ret"].mean()
    con_r = gg.loc[gg.hay_real == 1, "abs_ret"].mean()
    solo_i = gg.loc[gg.solo_indice == 1, "abs_ret"].mean()
    f = lambda x: f"{x:.4f}" if pd.notna(x) else "  n/a"
    r = lambda a, b: f"{a/b:.2f}x" if (pd.notna(a) and pd.notna(b) and b) else "  n/a"
    print(f"  {tk:<10} {f(sin_n):>11} {f(con_n):>11} {r(con_n, sin_n):>7} "
          f"{f(con_r):>9} {r(con_r, sin_n):>7} {f(solo_i):>12} {r(solo_i, sin_n):>7}")

print()
print("=" * 78)
print("2. VENTANA DE EVENTO — |ret| medio alrededor del día de noticia REAL")
print("=" * 78)
print(f"  {'Activo':<10} {'T-2':>9} {'T-1':>9} {'T (día)':>9} {'T+1':>9} {'T+2':>9} {'base':>9}")
print("-" * 70)
for tk, gg in df.groupby("ticker"):
    ev = gg[gg.hay_real == 1]
    base = gg.loc[gg.hay_noticia == 0, "abs_ret"].mean()
    vals = [ev["ret_lag2"].abs().mean(), ev["ret_lag1"].abs().mean(),
            ev["abs_ret"].mean(), ev["ret_lead1"].abs().mean(),
            ev["ret_lead2"].abs().mean()]
    fila = " ".join(f"{v:>9.4f}" if pd.notna(v) else f"{'n/a':>9}" for v in vals)
    print(f"  {tk:<10}{fila} {base:>9.4f}")

print()
print("=" * 78)
print("3. MOVIMIENTOS EXTREMOS (|ret| en el top 5% del activo)")
print("=" * 78)
print(f"  {'Activo':<10} {'% extremos':>11} {'% extremos':>11} {'% días':>9}")
print(f"  {'':<10} {'c/ noticia':>11} {'c/ REAL':>11} {'c/ noticia':>9}")
print("-" * 46)
for tk, gg in df.groupby("ticker"):
    u = gg["abs_ret"].quantile(0.95)
    ext = gg[gg.abs_ret >= u]
    print(f"  {tk:<10} {ext.hay_noticia.mean():>10.1%} {ext.hay_real.mean():>11.1%} "
          f"{gg.hay_noticia.mean():>9.1%}")

print()
print("=" * 78)
print("4. LO QUE EL AGENTE SÍ PUEDE CAPTURAR: |ret| en T+1 tras noticia REAL")
print("=" * 78)
print(f"  {'Activo':<10} {'|ret| T+1 base':>15} {'|ret| T+1 tras not.':>20} {'razón':>7}")
print("-" * 56)
for tk, gg in df.groupby("ticker"):
    base = gg.loc[gg.hay_noticia == 0, "ret_lead1"].abs().mean()
    tras = gg.loc[gg.hay_real == 1, "ret_lead1"].abs().mean()
    rr = f"{tras/base:.2f}x" if (pd.notna(tras) and pd.notna(base) and base) else "n/a"
    print(f"  {tk:<10} {base:>15.4f} {tras:>20.4f} {rr:>7}")

print()
print("=" * 78)
print("5. RESUMEN AGREGADO (todos los activos juntos)")
print("=" * 78)
b = df.loc[df.hay_noticia == 0, "abs_ret"].mean()
n = df.loc[df.hay_noticia == 1, "abs_ret"].mean()
r_ = df.loc[df.hay_real == 1, "abs_ret"].mean()
i_ = df.loc[df.solo_indice == 1, "abs_ret"].mean()
print(f"  |ret| día SIN noticia            : {b:.4f}")
print(f"  |ret| día CON noticia (cualquiera): {n:.4f}  ({n/b:.2f}x)")
print(f"  |ret| día CON noticia REAL        : {r_:.4f}  ({r_/b:.2f}x)")
print(f"  |ret| día SOLO de índice          : {i_:.4f}  ({i_/b:.2f}x)")
print()
print(f"  Días con noticia de índice marcados: {int(df.n_idx.gt(0).sum())}")
print(f"  Días con noticia real marcados    : {int(df.hay_real.sum())}")
