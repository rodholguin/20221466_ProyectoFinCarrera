"""PILOTO A — ¿sostiene el modelo la taxonomía de eventos? (prompt v2)

Evalúa el prompt v2 contra la ANOTACIÓN MANUAL CIEGA de julio
(data/interim/r5_validacion_anotada.csv, 180 noticias con `rel_humana` y
`categoria` anotadas por humano). No requiere anotar nada nuevo.

MÉTRICA PRINCIPAL — RELEVANCIA. La taxonomía define relevante == magnitud > 0,
así que se compara directamente contra `rel_humana`. Línea base v1: 26% de
relevancia efectiva, kappa 0.32, y 49% de las etiquetas CON SIGNO provenientes de
noticias irrelevantes (el error dominante que v2 debe eliminar por construcción).

Uso:
  python scripts/piloto_r5_taxonomia.py --model gemma3:4b
  python scripts/piloto_r5_taxonomia.py --model gemma3:12b --etiqueta 12b
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.universe import Config
from src.sentiment.llm_sentiment import PROMPT_VERSION, classify_dataframe
from src.sentiment.taxonomia import ERROR, TAXONOMIA, es_relevante

INTERIM = ROOT / "data" / "interim"
ANOTADA = INTERIM / "r5_validacion_anotada.csv"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="gemma3:4b")
    ap.add_argument("--etiqueta", default=None,
                    help="sufijo del archivo de salida (por defecto, el modelo)")
    ap.add_argument("--sin-prefiltro", action="store_true",
                    help="mide al LLM solo, sin la ayuda del prefiltro regex")
    args = ap.parse_args()
    etiqueta = args.etiqueta or args.model.replace(":", "_")

    cfg = Config.load(ROOT / "config.yaml")
    nombres = {a.bvl: a.name for a in cfg.assets}
    # Los activos del universo VIEJO no están en config; se completan a mano
    # porque la muestra anotada es de ellos.
    nombres.update({"BUENAVC1": "Compania de Minas Buenaventura",
                    "SAGAC1": "Saga Falabella",
                    "CORAREC1": "Aceros Arequipa"})

    an = pd.read_csv(ANOTADA)
    an = an[an["rel_humana"].notna()].copy()
    an["rel_humana"] = an["rel_humana"].astype(int)
    print(f"Muestra anotada: {len(an)} noticias | relevantes {an.rel_humana.mean():.1%}")
    print(f"Modelo: {args.model} | prompt {PROMPT_VERSION} | "
          f"prefiltro {'NO' if args.sin_prefiltro else 'sí'}\n")

    # classify_dataframe espera columnas id/title/ticker/publish_date
    news = an.rename(columns={"clave": "id"})[
        ["id", "ticker", "publish_date", "title"]].copy()

    t0 = time.time()
    partes, stats_tot = [], []
    for tk, g in news.groupby("ticker"):
        empresa = nombres.get(tk, tk)
        print(f"  {tk} ({empresa}): {len(g)} noticias")
        art, st = classify_dataframe(
            g, empresa, INTERIM / "sentiment_cache" / f"piloto_{etiqueta}_{tk}.json",
            model=args.model, save_every=20,
            usar_prefiltro=not args.sin_prefiltro)
        partes.append(art)
        st["ticker"] = tk
        stats_tot.append(st)
    dur = time.time() - t0

    art = pd.concat(partes, ignore_index=True)
    # La anotación humana ya trae una columna `categoria` (empresa/sector/
    # mercado/ruido). Se renombra ANTES del merge para que no colisione con la
    # categoría predicha por el modelo.
    an = an.rename(columns={"categoria": "cat_humana"})
    res = an.merge(art[["id", "categoria", "polaridad", "magnitud", "relevante",
                        "origen"]],
                   left_on="clave", right_on="id", how="left")
    salida = INTERIM / f"piloto_r5_{etiqueta}.csv"
    res.to_csv(salida, index=False, encoding="utf-8")

    st = pd.DataFrame(stats_tot)
    n_llm = int(st.llm.sum())
    print(f"\nTiempo total {dur/60:.1f} min | llamadas al LLM {n_llm} | "
          f"{dur/max(n_llm,1):.1f} s por llamada")
    print(f"Prefiltradas sin LLM: {int(st.prefiltro.sum())} | "
          f"errores de parseo: {int(st.errores_parseo.sum())} "
          f"({st.errores_parseo.sum()/len(res):.1%})")

    ok = res[res.categoria != ERROR].copy()
    print("\n" + "=" * 74)
    print("1. RELEVANCIA — lo que decide si el modelo sirve")
    print("=" * 74)
    acc = (ok.relevante == ok.rel_humana).mean()
    vp = int(((ok.relevante == 1) & (ok.rel_humana == 1)).sum())
    fp = int(((ok.relevante == 1) & (ok.rel_humana == 0)).sum())
    fn = int(((ok.relevante == 0) & (ok.rel_humana == 1)).sum())
    vn = int(((ok.relevante == 0) & (ok.rel_humana == 0)).sum())
    prec = vp / max(vp + fp, 1)
    rec = vp / max(vp + fn, 1)
    print(f"  Exactitud            : {acc:.1%}")
    print(f"  Precisión (de las que llama relevantes, cuántas lo son): {prec:.1%}")
    print(f"  Recall   (de las relevantes reales, cuántas encuentra) : {rec:.1%}")
    print(f"  F1                   : {2*prec*rec/max(prec+rec,1e-9):.1%}")
    print(f"  VP={vp}  FP={fp}  FN={fn}  VN={vn}")
    print("\n  Por activo:")
    for tk, g in ok.groupby("ticker"):
        print(f"    {tk:<10} exactitud {(g.relevante==g.rel_humana).mean():>6.1%}  "
              f"(n={len(g)}, relevantes reales {g.rel_humana.mean():.0%})")

    print("\n" + "=" * 74)
    print("2. POLARIDAD ESPURIA — el error dominante de v1 (era 49%)")
    print("=" * 74)
    con_signo = ok[ok.polaridad.isin(["positivo", "negativo"])]
    if len(con_signo):
        esp = (con_signo.rel_humana == 0).mean()
        print(f"  Etiquetas con signo: {len(con_signo)}")
        print(f"  De ellas, sobre noticias IRRELEVANTES: {esp:.1%}   (v1: 49.0%)")
    else:
        print("  El modelo no emitió ninguna polaridad con signo.")

    print("\n" + "=" * 74)
    print("3. CATEGORÍA PREDICHA vs CATEGORÍA HUMANA (empresa/sector/mercado/ruido)")
    print("=" * 74)
    if "cat_humana" in ok.columns:
        print(pd.crosstab(ok["categoria"], ok["cat_humana"]).to_string())

    print("\n" + "=" * 74)
    print("4. DISTRIBUCIÓN DE CATEGORÍAS PREDICHAS (¿usa la taxonomía o colapsa?)")
    print("=" * 74)
    vc = ok["categoria"].value_counts()
    for cat in TAXONOMIA:
        n = int(vc.get(cat, 0))
        marca = "" if n else "   <- nunca usada"
        print(f"  {cat:<24} mag {TAXONOMIA[cat][0]:.1f}  {n:>4}{marca}")
    usadas = int((vc.index.isin(TAXONOMIA)).sum())
    print(f"\n  Categorías usadas: {usadas}/{len(TAXONOMIA)}")
    print(f"\nDetalle por noticia -> {salida.name}")


if __name__ == "__main__":
    main()
