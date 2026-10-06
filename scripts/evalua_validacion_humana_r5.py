"""Analiza la anotación humana de R5 (la del autor) y mide a los modelos con ella.

Consume el Excel que produjo scripts/muestra_validacion_humana_r5.py, ya llenado,
más su CSV de clave ciega. Se puede correr con la anotación A MEDIO TERMINAR: como
la hoja está barajada, cualquier prefijo es una submuestra válida y el script
simplemente ignora las filas vacías.

QUÉ MIDE, y con qué muestra cada cosa (no son intercambiables):

  1. PREFILTRO REGEX — con TODA la anotación. Es el punto ciego actual: el
     prefiltro descarta titulares ANTES de que el LLM los vea, así que lo que
     mata por error ningún modelo puede recuperarlo. Nunca se había medido.

  2. KAPPA autor-vs-asistente — SOLO bloque A. Decide si las 180 etiquetas de
     julio se rescatan como segundo anotador o se descartan.

  3. TASAS DE POBLACIÓN (% relevante, mezcla de categorías) — SOLO bloque B,
     reponderadas por el peso de muestreo. El bloque A está estratificado por la
     etiqueta del modelo v1, así que meterlo sesgaría la tasa.

  4. COMPARACIÓN DE MODELOS — sobre los ítems anotados que tengan salida de
     modelo. Hoy eso son los pilotos ya corridos (bloque A). Para el bloque B hay
     que correr antes el piloto sobre esos ítems.

Uso:
  python scripts/evalua_validacion_humana_r5.py
  python scripts/evalua_validacion_humana_r5.py --anotado ruta/al.xlsx
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

INTERIM = ROOT / "data" / "interim"
SALIDA = INTERIM / "validacion_humana"
ANOTADA_ASISTENTE = INTERIM / "r5_validacion_anotada.csv"


# ----------------------------------------------------------------------
# Utilidades estadísticas
# ----------------------------------------------------------------------
def ic_prop(k: int, n: int) -> str:
    """Proporción con IC 95% (Wald). Devuelve texto listo para imprimir."""
    if n == 0:
        return "     n=0    "
    p = k / n
    h = 1.96 * math.sqrt(max(p * (1 - p), 1e-9) / n)
    return f"{p:6.1%} ±{h * 100:4.1f}pp (n={n})"


def prop_ponderada(y: pd.Series, w: pd.Series) -> tuple[float, float, float]:
    """Estimador de Hájek + IC por tamaño de muestra efectivo (Kish).

    La muestra sobre-representa a propósito a los activos chicos, así que el
    promedio simple NO es el de la población: cada fila pesa N_estrato/n_estrato.
    El n efectivo castiga la dispersión de pesos, que es lo que de verdad limita
    la precisión de un estimador ponderado.
    """
    w = w.astype(float)
    p = float((w * y).sum() / w.sum())
    n_eff = float(w.sum() ** 2 / (w ** 2).sum())
    h = 1.96 * math.sqrt(max(p * (1 - p), 1e-9) / n_eff)
    return p, h, n_eff


def kappa(a: pd.Series, b: pd.Series) -> tuple[float, float]:
    """Kappa de Cohen y acuerdo observado, para dos anotadores sobre las mismas
    unidades."""
    df = pd.DataFrame({"a": a, "b": b}).dropna()
    if df.empty:
        return float("nan"), float("nan")
    po = float((df["a"] == df["b"]).mean())
    pa = df["a"].value_counts(normalize=True)
    pb = df["b"].value_counts(normalize=True)
    pe = float(sum(pa.get(c, 0) * pb.get(c, 0)
                   for c in set(pa.index) | set(pb.index)))
    k = (po - pe) / (1 - pe) if pe < 1 else float("nan")
    return k, po


def _lee_kappa(k: float) -> str:
    """Escala de Landis & Koch, para no discutir sobre un número desnudo."""
    if k != k:
        return "sin datos"
    for umbral, etiqueta in ((0.81, "casi perfecto"), (0.61, "sustancial"),
                             (0.41, "moderado"), (0.21, "aceptable"),
                             (0.0, "leve")):
        if k >= umbral:
            return etiqueta
    return "peor que el azar"


# ----------------------------------------------------------------------
# Carga
# ----------------------------------------------------------------------
def cargar(anotado: Path, clave: Path) -> pd.DataFrame:
    from src.sentiment.taxonomia import TAXONOMIA

    hoja = pd.read_excel(anotado, sheet_name="Anotacion")
    clv = pd.read_csv(clave)
    df = hoja.merge(clv, on="n", how="left", validate="one_to_one")

    df = df[df["categoria"].notna()].copy()
    if df.empty:
        sys.exit("No hay ninguna fila anotada todavia.")
    df["categoria"] = df["categoria"].astype(str).str.strip()

    # El desplegable trae el prefijo de tramo (A_/B_/C_/Z_); la taxonomia real no.
    df["cat_autor"] = df["categoria"].str.split("_", n=1).str[1]
    desconocidas = set(df["cat_autor"]) - set(TAXONOMIA)
    if desconocidas:
        sys.exit(f"Categorias que no existen en la taxonomia: {desconocidas}")

    df["mag_autor"] = df["cat_autor"].map(lambda c: TAXONOMIA[c][0])
    df["rel_autor"] = (df["mag_autor"] > 0).astype(int)
    df["pol_autor"] = df["polaridad"].astype(str).str.strip().replace("nan", pd.NA)

    n_tot = len(hoja)
    print(f"Anotadas {len(df)} de {n_tot} filas ({len(df) / n_tot:.0%})")
    print(f"  bloque A (re-anotacion del set del asistente): "
          f"{int((df.bloque == 'A').sum())}")
    print(f"  bloque B (muestra nueva, ciega al modelo):     "
          f"{int((df.bloque == 'B').sum())}")
    if "duda" in df:
        n_duda = int(df["duda"].notna().sum())
        print(f"  marcadas con duda: {n_duda} ({n_duda / len(df):.1%})")
    return df


# ----------------------------------------------------------------------
# 1. Prefiltro regex — el punto ciego
# ----------------------------------------------------------------------
def evalua_prefiltro(df: pd.DataFrame) -> None:
    from src.sentiment.taxonomia import PASA, prefiltro

    print("\n" + "=" * 72)
    print("1. PREFILTRO REGEX (corre ANTES del LLM: lo que mata, nadie lo recupera)")
    print("=" * 72)

    df = df.copy()
    df["pref"] = df["titular"].astype(str).map(prefiltro)
    corta = df["pref"] != PASA

    n_corta = int(corta.sum())
    print(f"Descarta {n_corta} de {len(df)} titulares ({n_corta / len(df):.1%}) "
          f"sin consultar al LLM.")

    # Falsos negativos: el regex lo tiro y el autor dice que SI era relevante.
    fn = df[corta & (df["rel_autor"] == 1)]
    print(f"\n  ERROR CARO — descartados que el autor considera RELEVANTES: "
          f"{len(fn)} de {n_corta} ({len(fn) / max(n_corta, 1):.1%})")
    if len(fn):
        print("  (estos ningun modelo puede recuperarlos; el error se le achacaria al LLM)")
        for r in fn.head(12).itertuples():
            print(f"    [{r.pref:16s} <- {r.cat_autor:22s}] {str(r.titular)[:76]}")
        if len(fn) > 12:
            print(f"    ... y {len(fn) - 12} mas")

    # Acierto: de lo que descarta, cuanto era efectivamente de esa categoria.
    ok = df[corta & (df["cat_autor"] == df["pref"])]
    print(f"\n  Acierto de categoria en lo descartado: {len(ok)}/{n_corta} "
          f"({len(ok) / max(n_corta, 1):.1%})")
    print(f"  Ahorro de llamadas al LLM: {n_corta / len(df):.1%} del corpus")


# ----------------------------------------------------------------------
# 2. Kappa autor vs asistente (bloque A)
# ----------------------------------------------------------------------
def evalua_acuerdo(df: pd.DataFrame) -> None:
    print("\n" + "=" * 72)
    print("2. ACUERDO AUTOR vs ASISTENTE (solo bloque A)")
    print("=" * 72)

    a = df[df["bloque"] == "A"]
    if a.empty:
        print("Sin filas del bloque A anotadas todavia.")
        return

    asis = pd.read_csv(ANOTADA_ASISTENTE).rename(columns={"clave": "id"})
    m = a.merge(asis[["id", "rel_humana", "sent_humano"]], on="id", how="left")
    m = m[m["rel_humana"].notna()]
    if m.empty:
        print("Ninguna fila del bloque A cruzo con la anotacion del asistente.")
        return

    k, po = kappa(m["rel_autor"], m["rel_humana"].astype(int))
    print(f"RELEVANCIA  n={len(m)}  acuerdo {po:.1%}  kappa {k:.3f}  ({_lee_kappa(k)})")
    print(f"  autor dice relevante:     {m['rel_autor'].mean():.1%}")
    print(f"  asistente dijo relevante: {m['rel_humana'].mean():.1%}")

    amb = m[(m["rel_autor"] == 1) & (m["rel_humana"] == 1)]
    if len(amb):
        k2, po2 = kappa(amb["pol_autor"], amb["sent_humano"])
        print(f"\nPOLARIDAD   n={len(amb)} (donde ambos dicen relevante)  "
              f"acuerdo {po2:.1%}  kappa {k2:.3f}  ({_lee_kappa(k2)})")

    print("\nLECTURA: kappa alto -> las 180 del asistente se pueden declarar como")
    print("segundo anotador. Kappa bajo -> manda la del autor y la otra se descarta.")


# ----------------------------------------------------------------------
# 3. Tasas de población (bloque B, reponderado)
# ----------------------------------------------------------------------
def tasas_poblacion(df: pd.DataFrame) -> None:
    print("\n" + "=" * 72)
    print("3. POBLACION (solo bloque B, reponderado por peso de muestreo)")
    print("=" * 72)

    b = df[df["bloque"] == "B"]
    if b.empty:
        print("Sin filas del bloque B anotadas todavia.")
        return

    p, h, n_eff = prop_ponderada(b["rel_autor"], b["peso"])
    print(f"RELEVANCIA global: {p:.1%} ±{h * 100:.1f}pp  (n={len(b)}, n_eff={n_eff:.0f})")

    print("\nPor activo (sin reponderar: dentro de un activo el muestreo es uniforme)")
    g = b.groupby("ticker")["rel_autor"].agg(["size", "sum"])
    for t, r in g.iterrows():
        print(f"  {t:10s} {ic_prop(int(r['sum']), int(r['size']))}")

    print("\nMezcla de categorias (reponderada a poblacion):")
    tot = b["peso"].sum()
    mix = (b.groupby("cat_autor")["peso"].sum() / tot).sort_values(ascending=False)
    for c, v in mix.items():
        marca = " " if b.loc[b.cat_autor == c, "mag_autor"].iloc[0] > 0 else "·"
        print(f"  {marca} {c:24s} {v:6.1%}")
    print("  (· = magnitud cero, o sea abstencion)")


# ----------------------------------------------------------------------
# 4. Modelos contra la referencia del autor
# ----------------------------------------------------------------------
def compara_modelos(df: pd.DataFrame) -> None:
    print("\n" + "=" * 72)
    print("4. MODELOS vs LA REFERENCIA DEL AUTOR")
    print("=" * 72)

    pilotos = sorted(INTERIM.glob("piloto_r5_*.csv"))
    if not pilotos:
        print("No hay corridas piloto en data/interim/piloto_r5_*.csv")
        return

    ref = df.set_index("id")[["rel_autor", "cat_autor", "pol_autor"]]
    filas, positivos = [], {}
    for f in pilotos:
        et = f.stem.replace("piloto_r5_", "")
        p = pd.read_csv(f)
        col_id = "id" if "id" in p.columns else "clave"
        p = p[p[col_id].notna()].drop_duplicates(subset=[col_id])
        j = p.set_index(col_id)[["relevante", "categoria"]].join(ref, how="inner")
        j = j[j["rel_autor"].notna()]
        if j.empty:
            continue
        j["relevante"] = j["relevante"].fillna(0).astype(int)
        tp = int(((j.relevante == 1) & (j.rel_autor == 1)).sum())
        fp = int(((j.relevante == 1) & (j.rel_autor == 0)).sum())
        fn = int(((j.relevante == 0) & (j.rel_autor == 1)).sum())
        cat_ok = int((j["categoria"] == j["cat_autor"]).sum())
        filas.append({
            "modelo": et, "n": len(j),
            "precision": ic_prop(tp, tp + fp),
            "recall": ic_prop(tp, tp + fn),
            "f1": f"{2 * tp / max(2 * tp + fp + fn, 1):.1%}",
            "cat_exacta": f"{cat_ok / len(j):.1%}",
        })
        positivos[et] = j["relevante"]

    if not filas:
        print("Ningun piloto cruza con las filas ya anotadas.")
        print("Para el bloque B hay que correr el piloto sobre esos items primero.")
        return

    t = pd.DataFrame(filas).sort_values("modelo")
    print(f"\n{'modelo':22s} {'n':>4s} {'precision':>22s} {'recall':>22s} "
          f"{'F1':>7s} {'cat':>7s}")
    for r in t.itertuples():
        print(f"{r.modelo:22s} {r.n:4d} {r.precision:>22s} {r.recall:>22s} "
              f"{r.f1:>7s} {r.cat_exacta:>7s}")

    print("\nCOMPARACION PAREADA (McNemar sobre discordantes: es lo que de verdad")
    print("separa modelos que se solapan mucho; los IC de arriba se solapan de mas)")
    nombres = sorted(positivos)
    ref_rel = ref["rel_autor"]
    for i, x in enumerate(nombres):
        for y in nombres[i + 1:]:
            comun = positivos[x].index.intersection(positivos[y].index)
            comun = comun.intersection(ref_rel.dropna().index)
            if len(comun) < 10:
                continue
            px, py = positivos[x][comun], positivos[y][comun]
            r = ref_rel[comun].astype(int)
            # Discordantes: uno acierta y el otro no.
            ax, ay = (px == r), (py == r)
            b01 = int((~ax & ay).sum())
            b10 = int((ax & ~ay).sum())
            nd = b01 + b10
            if nd == 0:
                continue
            z = (abs(b10 - b01) - 1) / math.sqrt(nd)
            p_val = math.erfc(z / math.sqrt(2))
            mejor = x if b10 > b01 else y
            sig = "*" if p_val < 0.05 else " "
            print(f"  {x:20s} vs {y:20s} discordantes {nd:3d} "
                  f"({b10:3d}/{b01:3d})  p={p_val:.3f} {sig} -> {mejor}")
    print("  * = diferencia significativa al 5%")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--anotado", default=str(SALIDA / "muestra_r5_anotar.xlsx"))
    ap.add_argument("--clave", default=str(SALIDA / "clave_muestra_r5.csv"))
    args = ap.parse_args()

    anotado, clave = Path(args.anotado), Path(args.clave)
    for p in (anotado, clave):
        if not p.exists():
            sys.exit(f"Falta {p}")

    df = cargar(anotado, clave)
    evalua_prefiltro(df)
    evalua_acuerdo(df)
    tasas_poblacion(df)
    compara_modelos(df)


if __name__ == "__main__":
    main()
