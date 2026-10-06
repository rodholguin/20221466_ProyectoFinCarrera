"""Validación del etiquetado de sentimiento de R5 contra un anotador de referencia.

El clasificador de R5 (gemma3:4b vía Ollama, zero-shot) etiqueta cada noticia como
positivo/negativo/neutral usando SOLO EL TÍTULO (MediaCloud story_list no devuelve
el cuerpo). Este script no evalúa nada por sí mismo: prepara el material para una
anotación ciega y luego calcula el acuerdo.

Uso en dos pasos:
  1. --muestra  -> escribe data/interim/r5_validacion_muestra.csv con la muestra
                   estratificada (ticker x etiqueta), en orden aleatorio y SIN la
                   etiqueta del modelo, para anotarla a ciegas.
  2. --evalua   -> lee data/interim/r5_validacion_anotada.csv (mismo archivo con
                   las columnas `rel_humana` y `sent_humano` completadas) y reporta
                   relevancia, precisión por clase y exactitud reponderada.

La muestra se estratifica por etiqueta PREDICHA porque la población está
desbalanceada y lo que interesa es la precisión de las clases informativas
(positivo/negativo), no solo la exactitud global. Para volver a la población se
repondera cada estrato por su peso real (ver _reponderada).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

RAW = Path("data/raw")
INTERIM = Path("data/interim")
MUESTRA = INTERIM / "r5_validacion_muestra.csv"
ANOTADA = INTERIM / "r5_validacion_anotada.csv"

SEMILLA = 20221466          # código del proyecto, para que la muestra sea reproducible
POR_ESTRATO = 12            # noticias por (ticker x etiqueta)
ETIQUETAS = ["positivo", "neutral", "negativo"]


def _cargar(ticker: str) -> pd.DataFrame:
    """Noticias de un activo con la etiqueta del modelo pegada desde su caché."""
    news = pd.read_parquet(RAW / f"news_{ticker}.parquet")
    cache = json.loads((INTERIM / "sentiment_cache" / f"cache_{ticker}.json")
                       .read_text(encoding="utf-8"))
    clave = news["id"].astype(str) if "id" in news.columns else news["url"].astype(str)
    news["clave"] = clave
    news["lab_modelo"] = clave.map(lambda k: cache.get(k, {}).get("sentiment"))
    news["conf_modelo"] = clave.map(lambda k: cache.get(k, {}).get("confidence"))
    return news[news["lab_modelo"].notna()]


def construir_muestra(tickers: list[str]) -> pd.DataFrame:
    partes, poblacion = [], []
    for t in tickers:
        df = _cargar(t)
        vc = df["lab_modelo"].value_counts()
        for lab in ETIQUETAS:
            sub = df[df["lab_modelo"] == lab]
            poblacion.append({"ticker": t, "lab_modelo": lab, "n_poblacion": len(sub)})
            if sub.empty:
                continue
            partes.append(sub.sample(min(POR_ESTRATO, len(sub)), random_state=SEMILLA))
        print(f"  {t}: {len(df)} noticias clasificadas {dict(vc)}")

    muestra = pd.concat(partes, ignore_index=True)
    # Orden aleatorio: el anotador no debe poder inferir el estrato por la posición.
    muestra = muestra.sample(frac=1.0, random_state=SEMILLA).reset_index(drop=True)
    muestra.insert(0, "n", range(1, len(muestra) + 1))
    pd.DataFrame(poblacion).to_csv(INTERIM / "r5_validacion_poblacion.csv", index=False)
    return muestra


def _reponderada(anot: pd.DataFrame, col_acierto: str) -> float:
    """Exactitud a nivel POBLACIÓN a partir de una muestra estratificada.

    La muestra sobre-representa las clases raras a propósito, así que el promedio
    simple no es el de la población: cada estrato (ticker x etiqueta) se pondera
    por su frecuencia real.
    """
    pob = pd.read_csv(INTERIM / "r5_validacion_poblacion.csv")
    peso = pob.set_index(["ticker", "lab_modelo"])["n_poblacion"]
    por_estrato = anot.groupby(["ticker", "lab_modelo"])[col_acierto].mean()
    w = peso.reindex(por_estrato.index).astype(float)
    return float((por_estrato * w).sum() / w.sum())


def evaluar() -> None:
    anot = pd.read_csv(ANOTADA)
    faltan = anot["sent_humano"].isna() | anot["rel_humana"].isna()
    if faltan.any():
        raise SystemExit(f"Faltan {int(faltan.sum())} filas por anotar en {ANOTADA}")

    anot["rel_humana"] = anot["rel_humana"].astype(int)
    anot["acierto"] = (anot["lab_modelo"] == anot["sent_humano"]).astype(int)

    print(f"\nMuestra anotada: {len(anot)} noticias\n")

    print("=== 1. RELEVANCIA (¿la noticia habla de la empresa?) ===")
    rel = anot.groupby("ticker")["rel_humana"].agg(["mean", "size"])
    for t, r in rel.iterrows():
        print(f"  {t}: {r['mean']:.1%} relevantes  (n={int(r['size'])})")
    print(f"  GLOBAL en la muestra: {anot['rel_humana'].mean():.1%} | "
          f"reponderada a población: {_reponderada(anot, 'rel_humana'):.1%}")

    print("\n=== 2. ACUERDO DE SENTIMIENTO ===")
    print(f"  Toda la muestra:        {anot['acierto'].mean():.1%}")
    rel_only = anot[anot["rel_humana"] == 1]
    if len(rel_only):
        print(f"  Solo noticias relevantes: {rel_only['acierto'].mean():.1%} "
              f"(n={len(rel_only)})")
    print(f"  Reponderado a población:  {_reponderada(anot, 'acierto'):.1%}")

    print("\n=== 3. PRECISIÓN POR CLASE PREDICHA ===")
    for lab in ETIQUETAS:
        sub = anot[anot["lab_modelo"] == lab]
        if sub.empty:
            continue
        print(f"  predicho {lab:9s}: {sub['acierto'].mean():5.1%} correcto "
              f"(n={len(sub)}) | relevantes {sub['rel_humana'].mean():.0%}")

    print("\n=== 4. MATRIZ DE CONFUSIÓN (filas = modelo, columnas = humano) ===")
    print(pd.crosstab(anot["lab_modelo"], anot["sent_humano"]).to_string())

    print("\n=== 5. ¿LA CONFIANZA DEL MODELO DISCRIMINA? ===")
    print(anot.groupby("acierto")["conf_modelo"].describe()[["count", "mean", "50%"]]
          .to_string())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--muestra", action="store_true", help="genera la muestra ciega")
    ap.add_argument("--evalua", action="store_true", help="evalúa la muestra anotada")
    ap.add_argument("--tickers", nargs="+",
                    default=["CREDITC1", "ALICORC1", "BUENAVC1", "SAGAC1", "CORAREC1"])
    args = ap.parse_args()

    if args.muestra:
        m = construir_muestra(args.tickers)
        # El archivo del anotador NO lleva la etiqueta del modelo (anotación ciega).
        ciego = m[["n", "ticker", "publish_date", "media_name", "title"]].copy()
        ciego["rel_humana"] = ""     # 1 = habla de la empresa, 0 = no
        ciego["sent_humano"] = ""    # positivo | neutral | negativo
        ciego.to_csv(MUESTRA, index=False, encoding="utf-8")
        # Las etiquetas del modelo se guardan aparte, para unirlas recién al evaluar.
        m[["n", "clave", "lab_modelo", "conf_modelo"]].to_csv(
            INTERIM / "r5_validacion_claves.csv", index=False, encoding="utf-8")
        print(f"\nMuestra de {len(m)} noticias -> {MUESTRA}")
        print("Anotar rel_humana y sent_humano, guardar como "
              f"{ANOTADA.name} y correr con --evalua")
    elif args.evalua:
        evaluar()
    else:
        ap.error("indica --muestra o --evalua")


if __name__ == "__main__":
    main()
