"""PILOTO D16 — ¿funciona de verdad el campo condicional `rol` para M&A?

D16 propone añadir al prompt un campo que SOLO se pregunta si la categoría es
`ma_reestructuracion`, y DERIVAR la polaridad de él con una regla ex-ante del
autor (objetivo -> positivo; comprador/vendedor -> neutral; tercero -> el hecho
no es de la empresa). Antes de adoptarla hay que ver si se sostiene. Este script
mide las TRES cosas que pueden hacerla fracasar:

  (A) REGRESIÓN. Un campo más puede degradar la tarea principal en un modelo
      chico. Se corre el MISMO modelo sobre la MISMA muestra anotada con v2.1
      (sin `rol`) y con v2.2 (con `rol`), y se comparan exactitud, precisión y
      recall de relevancia y polaridad espuria. Si v2.2 pierde en la tarea
      principal, D16 no vale lo que cuesta por muy bien que asigne el rol.

  (B) ACIERTO DEL ROL. Contra la asignación manual del autor sobre los 13 M&A
      de la muestra (scripts/valida_polaridad_ma.py). n es minúsculo y así hay
      que reportarlo: lo que se busca no es significancia sino descartar que el
      modelo confunda comprador con objetivo, que es el único error que importa
      (invierte el signo del evento más grande del panel).

  (C) SUPERVIVENCIA DEL ARCO. El caso que sostiene a D16 es la venta de Luz del
      Sur: 7 titulares entre enero y octubre de 2019 con LUSURC1 como objetivo,
      durante los cuales el precio subió +43% ANTES del anuncio. Si el PASO 1
      del prompt manda a `mencion_incidental` los titulares que no nombran a la
      empresa ("Enel considera oferta por activos de Sempra"), el arco se rompe
      y D16 rinde mucho menos de lo que promete. Se mide sobre los titulares
      reales del corpus, no sobre la muestra.

NO TOCA NADA DE PRODUCCIÓN. El prompt v2.2 vive acá dentro; src/sentiment queda
igual hasta que D16 se decida.

ADVERTENCIA METODOLÓGICA: `rol` es una variable LEÍBLE EN EL TITULAR y la regla
de signo es ex-ante. Ningún evento se etiqueta por su retorno realizado — eso
sería look-ahead. Los retornos solo sirvieron para decidir si valía la pena
medir esto, en valida_polaridad_ma.py.

Uso:
  ssh -f -N -L 11435:127.0.0.1:11434 phantom
  OLLAMA_URL=http://127.0.0.1:11435 python scripts/piloto_rol_d16.py --model gemma3:12b
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.sentiment import llm_backends
from src.sentiment.llm_sentiment import _SYSTEM_PROMPT as PROMPT_V21
from src.sentiment.taxonomia import (
    CATEGORIAS, ERROR, PASA, POLARIDADES, TAXONOMIA, bloque_categorias_prompt,
    es_relevante, prefiltro,
)
from src.universe import Config

INTERIM = ROOT / "data" / "interim"
VH = INTERIM / "validacion_humana"
CACHE = INTERIM / "sentiment_cache"

# ─────────────────────────────────────────────────────────────────────────────
# PROMPT v2.2 — v2.1 + un PASO 4 CONDICIONAL.
#
# Se conserva v2.1 palabra por palabra hasta el bloque de REGLAS para que la
# comparación (A) aísle el efecto del campo nuevo y no el de una reescritura.
# El campo es condicional a propósito: no agranda el espacio de decisión de las
# otras 14 categorías, que es exactamente lo que hundió a D14 (`alcance`).
#
# El modelo NO decide el signo: devuelve un ROL (observable) y la regla lo
# traduce. Es el mismo reparto de trabajo que la magnitud por taxonomía — el
# modelo hace la parte objetiva, el autor fija el valor.
# ─────────────────────────────────────────────────────────────────────────────
_PASO4 = (
    "\n\nPASO 4 — SOLO si elegiste ma_reestructuracion. ¿Qué papel juega LA "
    "EMPRESA en la operación?\n"
    "- objetivo: la empresa (o su matriz) es la que se COMPRA, se vende o "
    "recibe una oferta. Alguien quiere quedarse con ella.\n"
    "- comprador: la empresa es la que ADQUIERE o toma control de otra.\n"
    "- vendedor: la empresa VENDE una filial, unidad o participación suya.\n"
    "- interno: reorganización societaria dentro del mismo grupo, sin cambio "
    "de dueño.\n"
    "- tercero: la operación es entre OTRAS empresas y la nuestra solo se ve "
    "afectada como competidor o del sector.\n"
    "Si no elegiste ma_reestructuracion, responde \"no_aplica\".\n"
)

# ─────────────────────────────────────────────────────────────────────────────
# PROMPT v2.3 — desambiguación `objetivo` / `vendedor`.
#
# POR QUÉ. En v2.2 el modelo acertó 8 de 12 roles, pero falló los 2 `objetivo`
# que importan (Luz del Sur 157 y Pacasmayo 468), llamándolos `vendedor` en
# ambos casos, y produjo 1 falso `objetivo` sobre una reorganización interna que
# rindió -3.00% a z=-7.7. El error no es de capacidad: la glosa de v2.2 decía
# "la empresa es la que se COMPRA", que para "Holcim adquiere la participación
# mayoritaria DE Cementos Pacasmayo" es genuinamente ambiguo — quien vende las
# acciones es el accionista controlador, no la empresa.
#
# LA REGLA SE ESCRIBE EN GENERAL, NO COMO LISTA DE LOS CASOS QUE FALLARON: el
# criterio es QUÉ CAMBIA DE DUEÑO. Si lo que cambia de manos es la empresa (sus
# acciones, su control), es `objetivo`, sin importar quién sea el vendedor. Si
# lo que cambia de manos es algo SUYO, es `vendedor`.
#
# ADVERTENCIA: esta variante se escribió DESPUÉS de ver fallar a v2.2 sobre los
# 13 anotados. Su resultado sobre esos 13 es IN-SAMPLE respecto del ajuste y no
# se puede reportar como validación. Por eso se añade el bloque (E), un set
# held-out de titulares de M&A del corpus que nunca entraron ni en la muestra
# anotada ni en el arco.
# ─────────────────────────────────────────────────────────────────────────────
_PASO4_V23 = (
    "\n\nPASO 4 — SOLO si elegiste ma_reestructuracion. La pregunta es QUÉ "
    "CAMBIA DE DUEÑO en la operación:\n"
    "- objetivo: lo que cambia de dueño es LA EMPRESA MISMA — sus acciones, una "
    "participación en ella, o su control. Da igual quién sea el vendedor (su "
    "matriz, un accionista, un fondo): si alguien compra, adquiere o hace una "
    "oferta POR la empresa, la empresa es `objetivo`.\n"
    "- comprador: la empresa es la que ADQUIERE o toma control de otra empresa.\n"
    "- vendedor: lo que cambia de dueño es algo SUYO y distinto de ella misma — "
    "una filial, una unidad de negocio, una planta, o su participación en OTRA "
    "empresa. La empresa sigue existiendo con los mismos dueños.\n"
    "- interno: reorganización societaria dentro del MISMO grupo (fusión de "
    "filiales, concentración de acciones, cambio de razón social). El dueño "
    "final NO cambia y nadie compra nada.\n"
    "- tercero: la operación es entre OTRAS empresas y la nuestra solo se ve "
    "afectada como competidora o por ser del sector.\n"
    "Si no elegiste ma_reestructuracion, responde \"no_aplica\".\n"
)

# Léxico que define el HELD-OUT de (E). Es una COTA SUPERIOR deliberada: deja
# pasar de más y el propio modelo descarta lo que no es M&A. Construir el control
# con un criterio más fino sería filtrarlo con la misma noción que se quiere
# probar.
LEX_MA = (r"adquir|adquisic|compra de|compr[oó] |fusi[oó]n|fusiona|venta de|"
          r"vend[eió]|\bopa\b|oferta p[uú]blica|toma de control|toma el control|"
          r"escisi[oó]n|reestructur|desinversi[oó]n")

ROLES = ("objetivo", "comprador", "vendedor", "interno", "tercero")

# LA REGLA EX-ANTE QUE SE ESTÁ PROBANDO (D16). La fija el autor, no el modelo.
#   objetivo  -> positivo : se paga prima de control
#   comprador -> neutral  : dilución vs. sinergia, ambiguo desde el titular
#   vendedor  -> neutral  : foco y caja vs. pérdida de activo
#   interno   -> neutral  : no cambia el dueño
#   tercero   -> NO es un hecho de la empresa; se degrada a sector_macro
REGLA_SIGNO = {
    "objetivo": "positivo",
    "comprador": "neutral",
    "vendedor": "neutral",
    "interno": "neutral",
}

def _arma_prompt(paso4: str) -> str:
    """v2.1 + un PASO 4, con el esquema JSON ampliado con `rol`.

    Se corta v2.1 por el bloque de REGLAS y se reinyecta intacto para que la
    comparación aísle el efecto del PASO 4 y no el de una reescritura.
    """
    cabeza, reglas = PROMPT_V21.split("\n\nREGLAS:")
    return (cabeza + paso4 + "\n\nREGLAS:" + reglas.replace(
        '{"categoria": "<una de la lista>", "polaridad": '
        '"<positivo|negativo|neutral|no_aplica>"}',
        '{"categoria": "<una de la lista>", "polaridad": '
        '"<positivo|negativo|neutral|no_aplica>", "rol": '
        '"<objetivo|comprador|vendedor|interno|tercero|no_aplica>"}'))


_SYSTEM_V22 = _arma_prompt(_PASO4)
_SYSTEM_V23 = _arma_prompt(_PASO4_V23)
PROMPTS = {"v21": PROMPT_V21, "v22": _SYSTEM_V22, "v23": _SYSTEM_V23}

# `rol` asignado por LECTURA DEL TITULAR por el autor (misma tabla que
# valida_polaridad_ma.py). Es el patrón de oro de la medición (B).
ROL_HUMANO = {
    36: "comprador", 62: "vendedor", 75: "tercero", 153: "vendedor",
    157: "objetivo", 160: "comprador", 174: "interno", 191: "tercero",
    206: "comprador", 215: "comprador", 391: "objetivo", 468: "objetivo",
    495: "comprador",
}

# (C) EL ARCO. Titulares reales del corpus, con el rol que les asignaría el
# autor leyendo solo el titular. Los de 2019 son la venta de Luz del Sur; los
# de dic-2025, la toma de control de Pacasmayo por Holcim.
ARCO = [
    ("LUSURC1", "2019-01-28", "objetivo"),
    ("LUSURC1", "2019-02-25", "objetivo"),
    ("LUSURC1", "2019-02-28", "objetivo"),
    ("LUSURC1", "2019-04-12", "objetivo"),
    ("LUSURC1", "2019-06-21", "objetivo"),
    ("LUSURC1", "2019-06-26", "objetivo"),
    ("LUSURC1", "2019-10-15", "objetivo"),
    ("CPACASC1", "2025-12-16", "objetivo"),
    ("CPACASC1", "2025-12-17", "objetivo"),
]
ARCO_RE = (r"three gorges|sempra|enel|holcim|adquiere|adquirir|"
           r"toma el control|compra de luz del sur")


# ─────────────────────────────────────────────────────────────────────────────
def _parse(raw: str) -> dict:
    """Extrae {categoria, polaridad, rol}. Un fallo NO se degrada a neutral."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"categoria": ERROR, "polaridad": None, "rol": None}
    if not isinstance(data, dict):
        return {"categoria": ERROR, "polaridad": None, "rol": None}
    cat = str(data.get("categoria") or "").strip().lower()
    if cat not in TAXONOMIA:
        return {"categoria": ERROR, "polaridad": None, "rol": None}
    pol = str(data.get("polaridad") or "").strip().lower()
    rol = str(data.get("rol") or "").strip().lower()
    # Mismo principio que taxonomia.normaliza: lo que no aplica se BORRA en
    # código, no se confía en que el modelo obedezca el prompt.
    if not es_relevante(cat):
        return {"categoria": cat, "polaridad": None, "rol": None}
    pol = pol if pol in POLARIDADES else "neutral"
    rol = rol if (rol in ROLES and cat == "ma_reestructuracion") else None
    return {"categoria": cat, "polaridad": pol, "rol": rol}


def _cache_path(model: str, version: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    return CACHE / f"d16_{model.replace(':', '_')}_{version}.json"


def clasifica(items: pd.DataFrame, nombres: dict, model: str, version: str,
              system: str, timeout: int = 180) -> pd.DataFrame:
    """Corre un prompt sobre `items` (id, ticker, title) con caché por versión."""
    path = _cache_path(model, version)
    cache = json.loads(path.read_text("utf-8")) if path.exists() else {}
    filas, n_llm, t0 = [], 0, time.time()
    for i, r in enumerate(items.itertuples(), 1):
        cat_pref = prefiltro(r.title)
        if cat_pref != PASA:
            res, origen = {"categoria": cat_pref, "polaridad": None,
                           "rol": None}, "prefiltro"
        elif r.id in cache:
            res, origen = cache[r.id], "cache"
        else:
            crudo = llm_backends.call(
                system, f"Empresa: {nombres.get(r.ticker, r.ticker)}\n"
                        f"Titular: {r.title}", model, timeout)
            res = _parse(crudo)
            cache[r.id] = res
            origen, n_llm = "llm", n_llm + 1
            if n_llm % 25 == 0:
                path.write_text(json.dumps(cache, ensure_ascii=False), "utf-8")
                print(f"    [{i}/{len(items)}] {version} · llm={n_llm} · "
                      f"{(time.time() - t0) / max(n_llm, 1):.1f} s/art", flush=True)
        filas.append({"n": getattr(r, "n", None), "id": r.id, "ticker": r.ticker,
                      "title": r.title, "categoria": res["categoria"],
                      "polaridad": res["polaridad"], "rol": res.get("rol"),
                      "origen": origen})
    path.write_text(json.dumps(cache, ensure_ascii=False), "utf-8")
    return pd.DataFrame(filas)


def metricas(pred: pd.DataFrame, humano: pd.DataFrame) -> dict:
    """Métricas de la tarea PRINCIPAL, idénticas a las del Piloto A."""
    d = pred.merge(humano, on="n", how="inner")
    n_err = int((d.categoria == ERROR).sum())
    ok = d[d.categoria != ERROR].copy()
    ok["rel_pred"] = ok.categoria.map(lambda c: int(es_relevante(c)))
    vp = int(((ok.rel_pred == 1) & (ok.rel_hum == 1)).sum())
    fp = int(((ok.rel_pred == 1) & (ok.rel_hum == 0)).sum())
    fn = int(((ok.rel_pred == 0) & (ok.rel_hum == 1)).sum())
    vn = int(((ok.rel_pred == 0) & (ok.rel_hum == 0)).sum())
    firmadas = ok[ok.polaridad.isin(["positivo", "negativo"])]
    return {
        "n": len(ok), "errores": n_err,
        "exactitud_rel": (vp + vn) / max(len(ok), 1),
        "precision": vp / max(vp + fp, 1),
        "recall": vp / max(vp + fn, 1),
        "cat_exacta": (ok.categoria == ok.cat_hum).mean(),
        "espuria": (firmadas.rel_hum == 0).mean() if len(firmadas) else float("nan"),
        "vp": vp, "fp": fp, "fn": fn, "vn": vn,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="gemma3:12b")
    ap.add_argument("--versiones", default="v22,v23",
                    help="variantes con `rol` a comparar contra v2.1")
    ap.add_argument("--solo-arco", action="store_true")
    args = ap.parse_args()
    vs = [v.strip() for v in args.versiones.split(",") if v.strip()]
    sufijo = args.model.replace(":", "_")

    cfg = Config.load(ROOT / "config.yaml")
    nombres = {a.bvl: a.name for a in cfg.assets}
    nombres.update({"BUENAVC1": "Compania de Minas Buenaventura",
                    "SAGAC1": "Saga Falabella", "CORAREC1": "Aceros Arequipa"})

    # ── la muestra anotada (550) ────────────────────────────────────────────
    an = pd.ExcelFile(VH / "muestra_r5_anotar.xlsx").parse("Anotacion")
    k = pd.read_csv(VH / "clave_muestra_r5.csv")
    m = an.merge(k[["n", "id", "ticker", "peso"]], on="n", how="left")
    m = m[m.categoria.notna()].copy()
    m["cat_hum"] = m.categoria.str[2:]           # "A_ma_..." -> "ma_..."
    m["rel_hum"] = m.cat_hum.map(lambda c: int(es_relevante(c)))
    m = m.rename(columns={"titular": "title"})
    hum = m[["n", "cat_hum", "rel_hum", "peso"]]
    items = m[["n", "id", "ticker", "title"]]

    # ── (C) el arco: titulares del corpus crudo ─────────────────────────────
    arco = []
    for tk in ("LUSURC1", "CPACASC1"):
        d = pd.read_parquet(ROOT / "data" / "raw" / f"news_{tk}.parquet")
        d["publish_date"] = pd.to_datetime(d.publish_date, errors="coerce", utc=True)
        d["fecha"] = d.publish_date.dt.strftime("%Y-%m-%d")
        for t, f, rol in ARCO:
            if t != tk:
                continue
            g = d[(d.fecha == f) &
                  d.title.astype(str).str.lower().str.contains(ARCO_RE, regex=True)]
            for r in g.itertuples():
                arco.append({"n": None, "id": r.id, "ticker": tk,
                             "title": r.title, "rol_hum": rol, "fecha": f})
    arco = pd.DataFrame(arco).drop_duplicates(subset="id")

    # ── (E) HELD-OUT ────────────────────────────────────────────────────────
    # Titulares con léxico de M&A del corpus de los 7 activos que NO están ni en
    # la muestra anotada ni en el arco. No tienen rol de referencia (asignarlo es
    # trabajo del autor), así que NO se mide acierto: se mide si la
    # desambiguación de v2.3 INFLA la etiqueta `objetivo`, que es el modo de
    # falla que introduce. Es el control que la comparación in-sample no da.
    ya_vistos = set(items.id) | set(arco.id)
    ho = []
    for tk in ("ALICORC1", "CPACASC1", "CREDITC1", "FERREYC1",
               "INRETC1", "LUSURC1", "MINSURI1"):
        d = pd.read_parquet(ROOT / "data" / "raw" / f"news_{tk}.parquet")
        g = d[d.title.astype(str).str.lower().str.contains(LEX_MA, regex=True)
              & ~d.id.isin(ya_vistos)]
        for r in g.itertuples():
            ho.append({"n": None, "id": r.id, "ticker": tk, "title": r.title})
    heldout = pd.DataFrame(ho).drop_duplicates(subset="id")

    print("=" * 78)
    print(f"PILOTO D16 · modelo {args.model} · variantes {', '.join(vs)}")
    print(f"muestra anotada {len(items)} · arco {len(arco)} · held-out {len(heldout)}")
    print("=" * 78)

    corridas = {}
    if not args.solo_arco:
        for v in ["v21"] + vs:
            print(f"\n>>> {v} sobre las 550…", flush=True)
            corridas[v] = clasifica(items, nombres, args.model, v, PROMPTS[v])
            corridas[v].to_csv(INTERIM / f"d16_{v}_{sufijo}.csv", index=False)

        print("\n" + "=" * 78)
        print("(A) REGRESIÓN — ¿el campo daña la tarea principal? (550 anotadas)")
        print("=" * 78)
        mets = {v: metricas(corridas[v], hum) for v in corridas}
        campos = [("exactitud_rel", "exactitud relevancia"),
                  ("precision", "precisión relevancia"),
                  ("recall", "recall relevancia"),
                  ("cat_exacta", "categoría exacta (15)"),
                  ("espuria", "polaridad espuria")]
        cab = "".join(f"{v:>10}" for v in corridas)
        print(f"  {'métrica':<24}{cab}" + "".join(f"{chr(916) + v:>11}" for v in vs))
        for kk, lab in campos:
            fila = "".join(f"{mets[v][kk]:10.1%}" for v in corridas)
            deltas = "".join(
                f"{(mets[v][kk] - mets['v21'][kk]) * 100:+9.1f}pp" for v in vs)
            print(f"  {lab:<24}{fila}{deltas}")
        print(f"  {'errores de parseo':<24}" +
              "".join(f"{mets[v]['errores']:10d}" for v in corridas))

        print("\n" + "=" * 78)
        print("(B) ACIERTO DEL ROL — contra la asignación manual (n=13)")
        print("   OJO: v2.3 se escribió DESPUÉS de ver fallar a v2.2 sobre estos")
        print("   mismos casos. Su cifra acá es IN-SAMPLE. El control es (E).")
        print("=" * 78)
        tabla = corridas["v21"][["n"]].copy()
        tabla = tabla[tabla.n.isin(ROL_HUMANO)].copy()
        tabla["rol_hum"] = tabla.n.map(ROL_HUMANO)
        for v in vs:
            tabla[v] = tabla.n.map(dict(zip(corridas[v].n, corridas[v].rol)))
        tick = dict(zip(items.n, items.ticker))
        print(f"  {'n':>4} {'ticker':<9} {'rol humano':<11}" +
              "".join(f" {v:<14}" for v in vs))
        for x in tabla.sort_values("n").itertuples():
            cel = ""
            for v in vs:
                got = getattr(x, v)
                mark = "OK" if got == x.rol_hum else ("--" if pd.isna(got) else "XX")
                cel += f" {str(got):<11}{mark:<3}"
            print(f"  {x.n:>4} {tick.get(x.n, '?'):<9} {x.rol_hum:<11}{cel}")
        print()
        for v in vs:
            vis = tabla[tabla[v].notna()]
            ac = (vis[v] == vis.rol_hum).mean() if len(vis) else float("nan")
            det = int(((tabla.rol_hum == "objetivo") & (tabla[v] == "objetivo")).sum())
            no_det = int(((tabla.rol_hum == "objetivo") & tabla[v].notna() &
                          (tabla[v] != "objetivo")).sum())
            falso = int(((tabla.rol_hum != "objetivo") & (tabla[v] == "objetivo")).sum())
            print(f"  {v}: acierto global {ac:.0%} "
                  f"({int((vis[v] == vis.rol_hum).sum())}/{len(vis)}) | "
                  f"objetivos detectados {det}/3 · no detectados {no_det} · "
                  f"falsos objetivos {falso}")

        print("\n" + "=" * 78)
        print(f"(E) HELD-OUT — {len(heldout)} titulares de M&A del corpus, fuera de")
        print("    la muestra y del arco. Sin rol de referencia: se mide si la")
        print("    desambiguación INFLA `objetivo` (el riesgo que introduce).")
        print("=" * 78)
        ho_res = {}
        for v in vs:
            print(f"\n>>> {v} sobre el held-out…", flush=True)
            ho_res[v] = clasifica(heldout, nombres, args.model, v, PROMPTS[v])
            ho_res[v].to_csv(INTERIM / f"d16_heldout_{v}_{sufijo}.csv", index=False)
        for v in vs:
            d = ho_res[v]
            ma = d[d.categoria == "ma_reestructuracion"]
            n_obj = int((ma.rol == "objetivo").sum())
            print(f"\n  {v}: {len(ma)}/{len(d)} clasificados M&A · "
                  f"roles {ma.rol.value_counts(dropna=False).to_dict()}")
            print(f"      `objetivo` = {n_obj} "
                  f"({n_obj / max(len(ma), 1):.1%} de los M&A)")
        if len(vs) == 2:
            a, b = ho_res[vs[0]], ho_res[vs[1]]
            j2 = a[["id", "title", "categoria", "rol"]].merge(
                b[["id", "categoria", "rol"]], on="id", suffixes=("_a", "_b"))
            flip = j2[(j2.rol_a != "objetivo") & (j2.rol_b == "objetivo")]
            print(f"\n  titulares que {vs[1]} volvió `objetivo` y {vs[0]} no: "
                  f"{len(flip)}")
            for x in flip.head(25).itertuples():
                print(f"      [{str(x.rol_a):<10} -> objetivo]  {x.title[:62]}")

    # ── (C) el arco ─────────────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("(C) EL ARCO DE LUZ DEL SUR Y PACASMAYO")
    print("=" * 78)
    if arco.empty:
        return
    ar = {v: clasifica(arco, nombres, args.model, v, PROMPTS[v])
          for v in ["v21"] + vs}
    j = arco[["id", "fecha", "rol_hum", "title"]].copy()
    for v in ["v21"] + vs:
        mm = ar[v].set_index("id")
        j[f"cat_{v}"] = j.id.map(mm.categoria)
        j[f"pol_{v}"] = j.id.map(mm.polaridad)
        if v != "v21":
            j[f"rol_{v}"] = j.id.map(mm.rol)
    for x in j.sort_values("fecha").itertuples():
        print(f"\n  {x.fecha}  {x.title[:74]}")
        print(f"      v2.1  {str(getattr(x, 'cat_v21')):<22} "
              f"pol={str(getattr(x, 'pol_v21'))}")
        for v in vs:
            rol = getattr(x, f"rol_{v}")
            print(f"      {v:<5} {str(getattr(x, f'cat_{v}')):<22} "
                  f"pol={str(getattr(x, f'pol_{v}')):<9} rol={str(rol):<10}"
                  f" => D16: {REGLA_SIGNO.get(str(rol), '—')}")
    print("\n" + "-" * 78)
    for v in vs:
        vivos = j[j[f"cat_{v}"] == "ma_reestructuracion"]
        obj = vivos[vivos[f"rol_{v}"] == "objetivo"]
        print(f"  {v}: sobreviven como M&A {len(vivos)}/{len(j)} · "
              f"rol=objetivo {len(obj)}")
    j.to_csv(INTERIM / f"d16_arco_{sufijo}.csv", index=False)


if __name__ == "__main__":
    main()
