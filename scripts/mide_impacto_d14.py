"""Mide el impacto de D14 (eje `alcance`) SIN re-correr el LLM.

Pregunta que contesta: el eje `alcance` compra suficiente para justificar
reescribir el prompt y re-correr los 6 pilotos?

Insumos (todos ya existen):
  - data/interim/validacion_humana/muestra_r5_anotar.xlsx   (550 anotadas)
  - data/interim/validacion_humana/clave_muestra_r5.csv     (bloque y peso)
  - data/interim/validacion_humana/clasif_alcance_d14.csv        (113 sector_macro)
  - data/interim/validacion_humana/clasif_alcance_relevantes.csv (54 relevantes)

Los dos ultimos son juicio del asistente sobre los titulares, marcados fila a
fila con su razon para que el autor los audite y corrija. La lectura ESTRICTA
usa solo `sector_fuerte`; la AMPLIA suma `sector_debil`. Se reportan las dos
porque la conclusion no debe depender de los casos de borde.

Poblacion: SOLO bloque B, reponderado (Hajek). El bloque A esta estratificado
por la etiqueta del modelo v1 y sesgaria cualquier tasa.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.sentiment.taxonomia import TAXONOMIA  # noqa: E402

VH = ROOT / "data" / "interim" / "validacion_humana"

# Factores de D14. `sector` es el numero en discusion -> se barre aparte.
FACTOR = {"unidad": 0.3, "empresa": 1.0, "sector": 0.3, "mercado": 0.0}


def base(tipo: str) -> float:
    return TAXONOMIA.get(tipo, (0.0, ""))[0]


def hajek(y: pd.Series, w: pd.Series) -> tuple[float, float, float]:
    w = w.astype(float)
    p = float((w * y).sum() / w.sum())
    n_eff = float(w.sum() ** 2 / (w ** 2).sum())
    h = 1.96 * math.sqrt(max(p * (1 - p), 1e-9) / n_eff)
    return p, h, n_eff


def carga() -> pd.DataFrame:
    df = pd.ExcelFile(VH / "muestra_r5_anotar.xlsx").parse("Anotacion")
    clave = pd.read_csv(VH / "clave_muestra_r5.csv")
    df = df.merge(clave[["n", "ticker", "bloque", "peso"]], on="n", how="left")

    sm = pd.read_csv(VH / "clasif_alcance_d14.csv")
    rel = pd.read_csv(VH / "clasif_alcance_relevantes.csv")
    df = df.merge(sm[["n", "clase", "tipo_d14"]], on="n", how="left")
    df = df.merge(rel[["n", "alcance"]], on="n", how="left")

    # tipo actual: el codigo de la anotacion sin el prefijo A_/B_/C_/Z_
    df["tipo_hoy"] = df["categoria"].astype(str).str.replace(
        r"^[ABCZ]_", "", regex=True)
    df["mag_hoy"] = df["tipo_hoy"].map(base).fillna(0.0)
    df["rel_hoy"] = df["mag_hoy"] > 0
    return df


def magnitud_d14(r, f_sector: float, lectura: str):
    """Devuelve (magnitud, tipo, alcance) de la fila bajo D14."""
    fac = dict(FACTOR, sector=f_sector)
    if r["rel_hoy"]:                                   # ya era relevante
        alc = r["alcance"] if isinstance(r["alcance"], str) else "empresa"
        return base(r["tipo_hoy"]) * fac[alc], r["tipo_hoy"], alc
    clase = r["clase"] if isinstance(r["clase"], str) else None
    admitidas = {"sector_fuerte"} if lectura == "estricta" else {
        "sector_fuerte", "sector_debil"}
    if clase in admitidas:
        return base(r["tipo_d14"]) * fac["sector"], r["tipo_d14"], "sector"
    return 0.0, r["tipo_hoy"], "mercado"


def main() -> None:
    df = carga()

    print("=" * 74)
    print("IMPACTO DE D14 - medido sobre las 550 anotaciones del autor")
    print("=" * 74)

    sm = df[df.categoria == "Z_sector_macro"]
    print("\n[1] LOS 113 Z_sector_macro, POR A QUE NIVEL APUNTAN")
    print(sm.clase.value_counts().to_string())
    print("\n  Solo `sector_*` cambia de estado con D14. `mercado` (factor 0.0)")
    print("  sigue en cero por diseno, y `otra_empresa` es un hecho de un")
    print("  tercero: D14 no lo rescata (haria falta otra decision).")
    print("\n  desglose por activo (todas las filas, bloques A y B):")
    print(pd.crosstab(sm.ticker, sm.clase).to_string())

    for lectura in ("estricta", "amplia"):
        print("\n" + "=" * 74)
        print(f"LECTURA {lectura.upper()}", end="")
        print("  (solo sector_fuerte)" if lectura == "estricta"
              else "  (sector_fuerte + sector_debil)")
        print("=" * 74)

        f = 0.3
        df["mag_d14"] = [magnitud_d14(r, f, lectura)[0] for _, r in df.iterrows()]
        df["rel_d14"] = df["mag_d14"] > 0
        b = df[df.bloque == "B"].copy()

        print(f"\n[2] CONTEO EN LA MUESTRA (n=550)   factor sector = {f}")
        print(f"  relevantes  hoy: {int(df.rel_hoy.sum()):3d}"
              f"   ->  D14: {int(df.rel_d14.sum()):3d}"
              f"   ({df.rel_d14.sum() / df.rel_hoy.sum():.2f}x)")
        print(f"  masa magnitud hoy: {df.mag_hoy.sum():6.2f}"
              f"   ->  D14: {df.mag_d14.sum():6.2f}"
              f"   ({df.mag_d14.sum() / df.mag_hoy.sum():.2f}x)")

        sube = df[(~df.rel_hoy) & df.rel_d14]
        baja = df[df.rel_hoy & (df.mag_d14 < df.mag_hoy)]
        print(f"    entran (0 -> >0)            : {len(sube):3d} filas,"
              f" +{sube.mag_d14.sum():.2f} de masa")
        print(f"    se DEGRADAN (unidad/sector) : {len(baja):3d} filas,"
              f" {(baja.mag_d14 - baja.mag_hoy).sum():+.2f} de masa")

        print("\n[3] RELEVANCIA POBLACIONAL (bloque B reponderado, n=430)")
        p0, h0, ne = hajek(b.rel_hoy, b.peso)
        p1, h1, _ = hajek(b.rel_d14, b.peso)
        print(f"  hoy : {p0:6.2%} +-{h0 * 100:4.1f}pp   (n_eff={ne:.0f})")
        print(f"  D14 : {p1:6.2%} +-{h1 * 100:4.1f}pp   ({p1 / p0:.2f}x)")

        print("\n  por activo (relevancia poblacional):")
        print(f"  {'ticker':<10} {'hoy':>8} {'D14':>8} {'x':>6}"
              f"   {'eventos 2012-2025 (cota)':>26}")
        tot0 = tot1 = 0.0
        for t, g in b.groupby("ticker"):
            q0, _, _ = hajek(g.rel_hoy, g.peso)
            q1, _, _ = hajek(g.rel_d14, g.peso)
            n_art = float(g.peso.sum())
            e0, e1 = q0 * n_art, q1 * n_art
            tot0 += e0
            tot1 += e1
            print(f"  {t:<10} {q0:8.1%} {q1:8.1%} {q1 / max(q0, 1e-9):6.2f}"
                  f"   {e0:10.0f} -> {e1:8.0f}")
        print(f"  {'TOTAL':<10} {'':8} {'':8} {'':6}   {tot0:10.0f} -> {tot1:8.0f}"
              f"   ({tot1 / tot0:.2f}x)")

    print("\n" + "=" * 74)
    print("[4] SENSIBILIDAD AL FACTOR `sector` (el numero en discusion)")
    print("=" * 74)
    print(f"  {'factor':>7} {'lectura':>9} {'relev.':>7} {'masa':>8} {'masa x':>7}"
          f" {'% masa que es sector':>21}")
    for lectura in ("estricta", "amplia"):
        for f in (0.1, 0.2, 0.3, 0.5, 1.0):
            m = [magnitud_d14(r, f, lectura) for _, r in df.iterrows()]
            mag = pd.Series([x[0] for x in m])
            alc = pd.Series([x[2] for x in m])
            masa_sec = mag[(alc == "sector") & (mag > 0)].sum()
            print(f"  {f:7.1f} {lectura:>9} {int((mag > 0).sum()):7d}"
                  f" {mag.sum():8.2f} {mag.sum() / df.mag_hoy.sum():7.2f}"
                  f" {masa_sec / mag.sum():20.1%}")

    print("\n" + "=" * 74)
    print("[5] EL PROBLEMA DEL `neutral` - se arregla SIN tocar el LLM")
    print("=" * 74)
    r = df[df.rel_hoy]
    print("  masa de magnitud actual por polaridad (las 6 columnas de D11 solo")
    print("  ven positivo y negativo):")
    for pol, g in r.groupby(r.polaridad.fillna("(vacio)")):
        print(f"    {pol:<10} {len(g):3d} eventos  masa {g.mag_hoy.sum():6.2f}"
              f"  ({g.mag_hoy.sum() / r.mag_hoy.sum():5.1%})")
    inv = r[r.polaridad == "neutral"]
    print(f"\n  INVISIBLE hoy en sent_pos/neg_ewma: {len(inv)} eventos,"
          f" {inv.mag_hoy.sum() / r.mag_hoy.sum():.1%} de la masa.")
    ma = r[r.tipo_hoy == "ma_reestructuracion"]
    print(f"  de los cuales M&A: {len(ma)} eventos, masa {ma.mag_hoy.sum():.2f}"
          f" ({ma.mag_hoy.sum() / r.mag_hoy.sum():.1%} de la masa total).")




def extra() -> None:
    """[6] Heterogeneidad entre activos y densidad del canal.

    D11 fija que la red es UNA SOLA con pesos COMPARTIDOS entre los 7 activos, y
    marca la dispersion de cobertura como el riesgo del canal. Si D14 ensancha esa
    dispersion en vez de cerrarla, empeora justo lo que D11 tuvo que mitigar.
    """
    df = carga()
    b = df[df.bloque == "B"].copy()
    ANIOS = 14.0  # 2012-2025

    print("\n" + "=" * 74)
    print("[6] HETEROGENEIDAD ENTRE ACTIVOS (el riesgo que D11 tuvo que mitigar)")
    print("=" * 74)
    for lectura in ("estricta", "amplia"):
        df["mag_d14"] = [magnitud_d14(r, 0.3, lectura)[0] for _, r in df.iterrows()]
        df["rel_d14"] = df["mag_d14"] > 0
        b = df[df.bloque == "B"].copy()
        ev0, ev1 = {}, {}
        for t, g in b.groupby("ticker"):
            n_art = float(g.peso.sum())
            ev0[t] = hajek(g.rel_hoy, g.peso)[0] * n_art / ANIOS
            ev1[t] = hajek(g.rel_d14, g.peso)[0] * n_art / ANIOS
        print(f"\n  lectura {lectura} - eventos relevantes POR ANIO y activo:")
        print(f"  {'ticker':<10} {'hoy':>8} {'D14':>8}")
        for t in sorted(ev0, key=lambda k: -ev0[k]):
            print(f"  {t:<10} {ev0[t]:8.1f} {ev1[t]:8.1f}")
        r0 = max(ev0.values()) / min(ev0.values())
        r1 = max(ev1.values()) / min(ev1.values())
        print(f"  razon max/min:  hoy {r0:5.1f}x   ->  D14 {r1:5.1f}x"
              f"   ({'EMPEORA' if r1 > r0 else 'mejora'})")


if __name__ == "__main__":
    main()
    extra()
