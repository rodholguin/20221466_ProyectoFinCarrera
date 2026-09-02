"""Tabla comparativa de TODOS los modelos evaluados en el Piloto A.

Lee cada data/interim/piloto_r5_*.csv y calcula las mismas métricas para todos,
contra la misma anotación humana. La tabla se regenera desde los datos, así que
no puede quedar desincronizada del documento.

Uso:
  python scripts/compara_modelos_r5.py            # tabla en consola
  python scripts/compara_modelos_r5.py --md       # markdown para pegar en el doc
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.sentiment.taxonomia import ERROR, TAXONOMIA, es_relevante

INTERIM = ROOT / "data" / "interim"

# Metadatos por corrida: etiqueta -> (modelo, prompt, dónde corrió)
# La etiqueta es el sufijo del archivo piloto_r5_<etiqueta>.csv
META = {
    "gemma3_4b":         ("gemma3:4b",  "v2",   "CPU local"),
    "gemma3_4b_v21":     ("gemma3:4b",  "v2.1", "CPU local"),
    "gemma3_4b_v21_gpu": ("gemma3:4b",  "v2.1", "xwing GPU"),
    "gemma3_12b_v21":    ("gemma3:12b", "v2.1", "xwing GPU"),
    "gemma3_27b_v21":    ("gemma3:27b", "v2.1", "xwing GPU"),
    "qwen25_14b_v21":    ("qwen2.5:14b", "v2.1", "xwing GPU"),
    "qwen25_32b_v21":    ("qwen2.5:32b", "v2.1", "xwing GPU"),
}


def metricas(csv: Path) -> dict | None:
    res = pd.read_csv(csv)
    if "categoria" not in res.columns or "rel_humana" not in res.columns:
        return None
    res = res[res["rel_humana"].notna()].copy()
    res["rel_humana"] = res["rel_humana"].astype(int)

    n_total = len(res)
    n_err = int((res.categoria == ERROR).sum() + res.categoria.isna().sum())
    ok = res[res.categoria.notna() & (res.categoria != ERROR)].copy()
    if ok.empty:
        return None

    ok["rel_pred"] = ok["categoria"].map(lambda c: int(es_relevante(c)))
    vp = int(((ok.rel_pred == 1) & (ok.rel_humana == 1)).sum())
    fp = int(((ok.rel_pred == 1) & (ok.rel_humana == 0)).sum())
    fn = int(((ok.rel_pred == 0) & (ok.rel_humana == 1)).sum())
    vn = int(((ok.rel_pred == 0) & (ok.rel_humana == 0)).sum())
    prec = vp / max(vp + fp, 1)
    rec = vp / max(vp + fn, 1)

    con_signo = ok[ok.polaridad.isin(["positivo", "negativo"])]
    espuria = (con_signo.rel_humana == 0).mean() if len(con_signo) else float("nan")

    usadas = int(ok["categoria"].isin(TAXONOMIA).groupby(ok["categoria"]).any().sum())
    usa_no_rel = "sí" if (ok.categoria == "no_relevante").any() else "NO"

    return {
        "exactitud": (vp + vn) / len(ok),
        "precision": prec,
        "recall": rec,
        "f1": 2 * prec * rec / max(prec + rec, 1e-9),
        "espuria": espuria,
        "err": n_err / max(n_total, 1),
        "cats": usadas,
        "no_relevante": usa_no_rel,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--md", action="store_true", help="salida en markdown")
    args = ap.parse_args()

    filas = []
    for csv in sorted(INTERIM.glob("piloto_r5_*.csv")):
        etiqueta = re.sub(r"^piloto_r5_|\.csv$", "", csv.name)
        m = metricas(csv)
        if m is None:
            continue
        modelo, prompt, donde = META.get(etiqueta, (etiqueta, "?", "?"))
        filas.append({"modelo": modelo, "prompt": prompt, "donde": donde, **m})

    if not filas:
        print("No hay corridas del piloto todavía.")
        return
    t = pd.DataFrame(filas).sort_values(["prompt", "modelo"])

    if args.md:
        print("| Modelo | Prompt | Exact. | Prec. | Recall | F1 | Espuria | Parseo | Cats | `no_relevante` |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for _, r in t.iterrows():
            print(f"| {r.modelo} | {r.prompt} | {r.exactitud:.1%} | {r.precision:.1%} | "
                  f"{r.recall:.1%} | {r.f1:.1%} | {r.espuria:.1%} | {r.err:.1%} | "
                  f"{r.cats}/15 | {r.no_relevante} |")
    else:
        print(f"{'Modelo':<13} {'prompt':<6} {'exact':>6} {'prec':>6} {'recall':>7} "
              f"{'F1':>6} {'espuria':>8} {'parseo':>7} {'cats':>5} {'no_rel':>7}")
        print("-" * 82)
        for _, r in t.iterrows():
            print(f"{r.modelo:<13} {r.prompt:<6} {r.exactitud:>6.1%} {r.precision:>6.1%} "
                  f"{r.recall:>7.1%} {r.f1:>6.1%} {r.espuria:>8.1%} {r.err:>7.1%} "
                  f"{r.cats:>4}/15 {r.no_relevante:>7}")
        print("\nBase: 180 noticias anotadas a ciegas (30.0% relevantes).")
        print("relevante == magnitud > 0. 'espuria' = etiquetas con signo sobre")
        print("noticias irrelevantes (v1 de referencia: 49.0%).")


if __name__ == "__main__":
    main()
