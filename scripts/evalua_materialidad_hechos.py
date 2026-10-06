"""Evalúa la anotación de materialidad de los Hechos de Importancia (BVL).

Consume el Excel que produjo scripts/muestra_materialidad_hechos.py, ya llenado,
más su clave ciega. Funciona con la anotación A MEDIO TERMINAR: la hoja está
barajada, así que cualquier prefijo es una submuestra válida.

CRITERIO DE DECISIÓN — PRE-REGISTRADO ANTES DE VER LOS DATOS (2026-08-29).
Se escribe acá para no moverlo después según convenga, que es el modo de falla
clásico de este tipo de medición. La propuesta de sumar los Hechos como segunda
fuente SE ADOPTA si se cumplen LAS DOS:

  (1) HETEROGENEIDAD. La razón max/min de eventos por año entre los 7 activos,
      contando prensa + hechos materiales, BAJA DE 16.8x A MENOS DE 6x.
      Es la razón de ser de la propuesta: D11 declara esa dispersión como EL
      riesgo del canal con una red de pesos compartidos. Si no la arregla, no
      hay motivo para sumar una fuente.

  (2) LOS ACTIVOS FAMÉLICOS. FERREYC1 y CPACASC1 AL MENOS TRIPLICAN sus eventos
      por año. Hoy están en 2.3 y 3.9; la prensa no los cubre y son la razón por
      la que se buscó otra fuente. Si el feed oficial tampoco los alimenta, la
      propuesta no resuelve el problema que la originó.

SE RECHAZA si falla cualquiera de las dos. Y se rechaza TAMBIÉN, con
independencia de ambas, si la verificación del filtro (abajo) sale mal y no se
puede arreglar: un filtro que descarta material no es un filtro, es un sesgo.

VERIFICACIÓN DEL FILTRO DE RUTINA. El estrato `rutina` no es relleno. Mide si el
filtro determinista está matando eventos materiales, igual que se hizo con el
prefiltro regex de R5 (que descartaba 19.8% con CERO relevantes perdidos). Si
aparecen materiales dentro de la rutina, hay que aflojar el filtro y re-muestrear
ANTES de decidir nada.

Uso:
  python scripts/evalua_materialidad_hechos.py
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.sentiment.taxonomia import TAXONOMIA  # noqa: E402

VH = ROOT / "data" / "interim" / "validacion_humana"
ANIOS = 14.0                      # 2012-2025

# Eventos/año de PRENSA, medidos sobre las 550 anotaciones (bloque B
# reponderado). Fuente: scripts/mide_impacto_d14.py §6.
PRENSA = {"INRETC1": 38.6, "CREDITC1": 18.1, "LUSURC1": 15.6, "MINSURI1": 13.8,
          "ALICORC1": 6.8, "CPACASC1": 3.9, "FERREYC1": 2.3}
UMBRAL_HETEROGENEIDAD = 6.0
FAMELICOS = ("FERREYC1", "CPACASC1")


def hajek(y: pd.Series, w: pd.Series) -> tuple[float, float, float]:
    """Proporción ponderada (Hájek) + IC 95% por tamaño de muestra efectivo."""
    w = w.astype(float)
    if w.sum() == 0:
        return float("nan"), float("nan"), 0.0
    p = float((w * y).sum() / w.sum())
    n_eff = float(w.sum() ** 2 / (w ** 2).sum())
    h = 1.96 * math.sqrt(max(p * (1 - p), 1e-9) / n_eff)
    return p, h, n_eff


def carga() -> pd.DataFrame:
    d = pd.ExcelFile(VH / "muestra_hechos_materialidad.xlsx").parse("Anotacion")
    k = pd.read_csv(VH / "clave_hechos_materialidad.csv")
    d = d.merge(k[["n", "ticker", "capa", "estrato", "peso"]], on="n", how="left")
    d = d[d.categoria.notna()].copy()
    d["tipo"] = d.categoria.astype(str).str.replace(r"^[ABCZ]_", "", regex=True)
    d["mag"] = d.tipo.map(lambda t: TAXONOMIA.get(t, (0.0, ""))[0]).fillna(0.0)
    d["material"] = d.mag > 0
    return d


def main() -> None:
    argparse.ArgumentParser().parse_args()
    d = carga()
    if d.empty:
        print("La anotación está vacía. Llene la columna `categoria` del Excel.")
        return
    print(f"anotadas: {len(d)} de 140  ({d.capa.value_counts().to_dict()})\n")

    # ── 1. Verificación del filtro ───────────────────────────────────────────
    print("=" * 70)
    print("[1] VERIFICACIÓN DEL FILTRO DE RUTINA (va primero: puede invalidar todo)")
    print("=" * 70)
    rut = d[d.capa == "rutina"]
    perdidos = rut[rut.material]
    print(f"  filas de `rutina` anotadas : {len(rut)}")
    print(f"  MATERIALES dentro de rutina: {len(perdidos)}")
    if len(perdidos):
        p, h, _ = hajek(rut.material, rut.peso)
        print(f"  -> tasa poblacional en rutina: {p:.1%} ±{h*100:.1f}pp")
        print("  -> EL FILTRO ESTÁ MATANDO EVENTOS. Aflojarlo y re-muestrear")
        print("     ANTES de decidir. Casos:")
        for r in perdidos.itertuples():
            print(f"       [{r.ticker}] {r.categoria:<24} {str(r.hecho)[:66]}")
    else:
        print("  -> filtro limpio: CERO materiales descartados en la muestra.")

    # ── 2. Tasa de materialidad ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("[2] TASA DE MATERIALIDAD (poblacional, Hájek)")
    print("=" * 70)
    cand = d[d.capa == "candidato"]
    p, h, ne = hajek(cand.material, cand.peso)
    print(f"  dentro de los candidatos : {p:6.1%} ±{h*100:4.1f}pp  (n={len(cand)}, n_eff={ne:.0f})")
    pt, ht, _ = hajek(d.material, d.peso)
    print(f"  sobre TODO lo anotable   : {pt:6.1%} ±{ht*100:4.1f}pp")
    print(f"  (comparación: la prensa rinde 7.2% ±2.8pp)")

    # ── 3. Eventos por año y heterogeneidad ──────────────────────────────────
    print("\n" + "=" * 70)
    print("[3] EVENTOS/AÑO: PRENSA vs HECHOS MATERIALES  — EL CRITERIO (1) Y (2)")
    print("=" * 70)
    print(f"  {'activo':<10}{'prensa':>8}{'hechos':>8}{'suma':>8}{'x':>7}  {'tasa':>7}")
    hh, ok_fam = {}, {}
    for t in sorted(PRENSA, key=lambda k: -PRENSA[k]):
        g = d[d.ticker == t]
        gc = g[g.capa == "candidato"]
        tasa, _, _ = hajek(gc.material, gc.peso) if len(gc) else (float("nan"),) * 3
        # eventos = tasa de materialidad x tamaño del estrato candidato del activo
        n_pool = float(gc.peso.sum()) if len(gc) else 0.0
        ev = (tasa * n_pool / ANIOS) if n_pool else 0.0
        hh[t] = ev
        ok_fam[t] = (PRENSA[t] + ev) / PRENSA[t] >= 3.0
        print(f"  {t:<10}{PRENSA[t]:8.1f}{ev:8.1f}{PRENSA[t]+ev:8.1f}"
              f"{(PRENSA[t]+ev)/PRENSA[t]:7.1f}  {tasa:7.1%}")

    su = {t: PRENSA[t] + hh[t] for t in PRENSA}
    r_prensa = max(PRENSA.values()) / min(PRENSA.values())
    r_suma = max(su.values()) / min(su.values())
    print(f"\n  razón max/min:  prensa {r_prensa:.1f}x  ->  prensa+hechos {r_suma:.1f}x")
    print(f"  total/año:      prensa {sum(PRENSA.values()):.1f}"
          f"  ->  {sum(su.values()):.1f}")

    print("\n" + "=" * 70)
    print("[4] VEREDICTO CONTRA EL CRITERIO PRE-REGISTRADO")
    print("=" * 70)
    c1 = r_suma < UMBRAL_HETEROGENEIDAD
    c2 = all(ok_fam[t] for t in FAMELICOS)
    c3 = len(perdidos) == 0
    print(f"  (1) heterogeneidad < {UMBRAL_HETEROGENEIDAD}x            : "
          f"{r_suma:5.1f}x   {'CUMPLE' if c1 else 'NO CUMPLE'}")
    for t in FAMELICOS:
        print(f"  (2) {t} triplica              : "
              f"{(PRENSA[t]+hh[t])/PRENSA[t]:5.1f}x   {'CUMPLE' if ok_fam[t] else 'NO CUMPLE'}")
    print(f"  (3) filtro sin materiales perdidos : "
          f"{len(perdidos):5d}    {'CUMPLE' if c3 else 'NO CUMPLE'}")
    print(f"\n  >>> {'ADOPTAR' if (c1 and c2 and c3) else 'NO ADOPTAR / REVISAR'}")

    # ── 5. Mezcla que alimentaría D15 ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("[5] MEZCLA DE CATEGORÍAS Y POLARIDAD (lo que entraría a las 9 columnas)")
    print("=" * 70)
    mat = d[d.material]
    if len(mat):
        print(mat.categoria.value_counts().to_string())
        print("\n  polaridad:")
        print(mat.polaridad.fillna("(vacia)").value_counts().to_string())
        tramo = pd.cut(mat.mag, [-.01, .3, .6, 1.0], labels=["bajo", "medio", "alto"])
        print("\n  celdas tramo x polaridad:")
        print(pd.crosstab(tramo.astype(str), mat.polaridad.fillna("(vacia)")).to_string())
    dudas = d[d.duda.astype(str).str.lower().str.strip() == "x"]
    print(f"\n  marcadas con duda: {len(dudas)} ({len(dudas)/len(d):.0%}) — si es alto,"
          f"\n  la taxonomía de prensa no sirve para esta fuente y eso es un resultado.")
    notas = d[d.nota.notna()]
    if len(notas):
        print(f"\n  notas del anotador ({len(notas)}):")
        for r in notas.itertuples():
            print(f"    [{r.ticker}] {str(r.nota)[:80]}")


if __name__ == "__main__":
    main()
