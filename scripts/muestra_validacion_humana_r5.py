"""Muestra para la ANOTACIÓN HUMANA de referencia de R5 (la del autor).

POR QUÉ EXISTE. La referencia que se venía usando
(data/interim/r5_validacion_anotada.csv, 180 notas) NO la produjo una persona:
la produjo el asistente. Sus columnas se llaman `rel_humana`/`sent_humano` y
mienten. Además, aun tomándola por buena, n=180 no alcanza: la precisión de
qwen2.5:32b se estima sobre 23 ítems marcados (82.6% ± 15.5pp) y los intervalos
de los cinco modelos se solapan entre sí. O sea: la tabla ORDENA pero no MIDE, y
no distingue a un modelo de otro. Este script arma la muestra que sí lo hace.

DE QUÉ CORPUS SE MUESTREA. Del NUEVO (7 activos, queries sin ancla `_FINANCIAL`),
no del viejo. Dos razones, y la segunda es la fuerte:
  1. Las queries cambiaron, así que la población cambió.
  2. El PREFILTRO regex también cambió, y vive en la fase de clasificación
     (llm_sentiment.classify_dataframe), NO en el fetch. O sea que
     news_<TICKER>.parquet guarda el corpus COMPLETO, antes del prefiltro, y
     muestrear de ahí permite medir además QUÉ DESCARTA EL REGEX antes de que el
     LLM lo vea. Hoy ese es un punto ciego total: si el prefiltro tira noticias
     relevantes, ningún modelo puede recuperarlas y el error se le achacaría al
     LLM. Validar sobre el corpus viejo mediría un pipeline que ya no existe.

DISEÑO — dos bloques en un solo archivo, mezclados y ciegos:

  BLOQUE A (n=120 por defecto, submuestra de los 180). Ítems que anotó el
    asistente, respetando sus estratos originales. Sirve para dos cosas: (1) mide
    el acuerdo autor-vs-asistente (kappa), que es lo que decide si aquella
    anotación se rescata o se descarta, y (2) vuelve medibles contra referencia
    humana las CINCO corridas piloto ya existentes, sin volver a pagar un solo
    token de LLM. Se reduce de 180 a 120 porque son del corpus VIEJO y 3 de sus 5
    activos ya no están en el universo: 120 alcanza para el kappa y libera cupo
    para el corpus que de verdad se va a usar.

  BLOQUE B (n=430 por defecto). Muestra NUEVA, aleatoria y CIEGA AL MODELO,
    sobre el corpus nuevo, estratificada por activo (piso por activo + resto
    proporcional al tamaño de la población). Es la que da estimaciones insesgadas
    a nivel población: el bloque A está estratificado por la etiqueta del modelo
    v1, así que por sí solo no representa a la población.

Los dos bloques van BARAJADOS en la misma hoja y el autor no sabe cuál es cuál
(si lo supiera, anotaría distinto el bloque A y el kappa quedaría inflado). La
correspondencia fila -> bloque/artículo vive en el archivo de CLAVE, que no se
abre hasta después de anotar.

ORDEN ALEATORIO = SE PUEDE PARAR A MITAD. Como la hoja está barajada, CUALQUIER
PREFIJO es una submuestra válida. Si el autor llega a la fila 300 y se cansa, se
analiza con 300; no se pierde el trabajo ni se sesga el resultado.

TAREA QUE SE PIDE. Una categoría de la taxonomía de 15 (docs/taxonomia_eventos_R5.txt
§4) por titular, más polaridad cuando la categoría no es de magnitud cero. La
relevancia NO se pregunta aparte: la taxonomía la define (relevante == magnitud
> 0), así que sale derivada de la categoría. Es una columna menos que llenar y
una etiqueta más rica.

Requiere el fetch nuevo hecho:
  python scripts/run_r5_news.py --fetch-only --force

Uso:
  python scripts/muestra_validacion_humana_r5.py            # 120 + 430 = 550
  python scripts/muestra_validacion_humana_r5.py --n-nuevas 500 --n-bloque-a 150
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
SALIDA = INTERIM / "validacion_humana"

ANOTADA = INTERIM / "r5_validacion_anotada.csv"
CLAVES = INTERIM / "r5_validacion_claves.csv"

SEMILLA = 20221466          # código del proyecto: muestra reproducible
PISO_POR_ACTIVO = 40        # mínimo de notas nuevas por activo, para que los
                            # activos chicos no queden con 4 filas

# Activos del universo VIEJO que ya no están en config.yaml pero de los que sí
# hay anotación del asistente (bloque A).
NOMBRES_LEGACY = {
    "BUENAVC1": "Compania de Minas Buenaventura",
    "SAGAC1": "Saga Falabella",
    "CORAREC1": "Aceros Arequipa",
}


def _nombres() -> dict[str, str]:
    from src.universe import Config
    cfg = Config.load(ROOT / "config.yaml")
    n = {a.bvl: a.name for a in cfg.assets}
    n.update(NOMBRES_LEGACY)
    return n


def _tickers_universo() -> list[str]:
    from src.universe import Config
    return [a.bvl for a in Config.load(ROOT / "config.yaml").assets]

# La taxonomía NO se duplica aquí: se deriva de src/sentiment/taxonomia.py, que
# es lo que corre el pipeline. Duplicarla ya causó una divergencia real (la doc
# daba sector_macro = 0.3 cuando el código la había bajado a 0.0 el 2026-08-18).
# Además el anotador lee LA MISMA definición que ve el modelo en su prompt: si
# las descripciones difirieran, la comparación humano-vs-modelo sería injusta.
PREFIJO = {1.0: "A", 0.6: "B", 0.3: "C", 0.0: "Z"}


def _taxonomia() -> list[tuple[str, float, str, str]]:
    """(codigo_dropdown, magnitud, nombre_taxonomia, definicion)."""
    from src.sentiment.taxonomia import TAXONOMIA
    return [(f"{PREFIJO[mag]}_{nombre}", mag, nombre, desc)
            for nombre, (mag, desc) in TAXONOMIA.items()]


AZUL = "1F3864"
GRIS = "F2F2F2"
AMARILLO = "FFF2CC"
FUENTE = "Arial"


# ----------------------------------------------------------------------
# Muestreo
# ----------------------------------------------------------------------
def _pool() -> pd.DataFrame:
    """Población: los parquets del universo VIGENTE, sin titulares repetidos.

    Se restringe a los tickers de config.yaml a propósito: si quedaron parquets
    del universo viejo en data/raw (BUENAVC1, SAGAC1, CORAREC1), muestrear de
    ellos metería en la referencia activos que ya no se van a modelar.
    """
    partes, faltan = [], []
    for t in _tickers_universo():
        f = RAW / f"news_{t}.parquet"
        if not f.exists():
            faltan.append(t)
            continue
        d = pd.read_parquet(f)
        d["ticker"] = t
        partes.append(d)
    if faltan:
        sys.exit(f"Falta el fetch de: {', '.join(faltan)}\n"
                 f"Corre primero: python scripts/run_r5_news.py --fetch-only --force")
    pool = pd.concat(partes, ignore_index=True)
    pool = pool[pool["title"].notna() & (pool["title"].str.strip() != "")]
    # Un titular repetido dentro del mismo activo es el mismo evento re-indexado:
    # anotarlo dos veces no aporta informacion y sesga los pesos.
    antes = len(pool)
    pool = pool.drop_duplicates(subset=["ticker", "title"]).reset_index(drop=True)
    print(f"Poblacion: {antes} noticias -> {len(pool)} tras deduplicar titulares")
    return pool


def _asignacion(pool: pd.DataFrame, n_nuevas: int) -> dict[str, int]:
    """Piso por activo + resto proporcional al tamano de cada poblacion."""
    tickers = sorted(pool["ticker"].unique())
    piso = min(PISO_POR_ACTIVO, n_nuevas // len(tickers))
    asign = {t: piso for t in tickers}
    resto = n_nuevas - piso * len(tickers)
    if resto > 0:
        tam = pool["ticker"].value_counts()
        frac = tam / tam.sum()
        extra = (frac * resto).round().astype(int)
        for t in tickers:
            asign[t] += int(extra.get(t, 0))
    # Cuadrar por redondeo contra el activo mas grande.
    dif = n_nuevas - sum(asign.values())
    if dif:
        mayor = pool["ticker"].value_counts().idxmax()
        asign[mayor] += dif
    return asign


def construir(n_nuevas: int, n_bloque_a: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    pool = _pool()

    # --- BLOQUE A: submuestra de los 180 que anoto el asistente ---------
    an = pd.read_csv(ANOTADA)
    claves = pd.read_csv(CLAVES)[["clave", "lab_modelo"]]
    a = an[["clave", "ticker", "publish_date", "media_name", "title"]].copy()
    a = a.merge(claves, on="clave", how="left")
    a["bloque"] = "A"
    # Estrato original del diseno de julio: ticker x etiqueta v1 del modelo.
    a["estrato"] = a["ticker"] + "|" + a["lab_modelo"].fillna("NA")
    a = a.rename(columns={"clave": "id"})
    if n_bloque_a < len(a):
        # Se reduce RESPETANDO los estratos de julio, no al azar sobre el total:
        # de otro modo los pesos del diseno original dejan de aplicar.
        frac = n_bloque_a / len(a)
        a = (a.groupby("estrato", group_keys=False)
              .sample(frac=frac, random_state=SEMILLA)
              .reset_index(drop=True))
    print(f"Bloque A: {len(a)} de 180 anotadas por el asistente "
          f"({a['estrato'].nunique()} estratos)")

    # --- BLOQUE B: muestra nueva, ciega al modelo -----------------------
    libre = pool[~pool["id"].isin(set(a["id"]))]
    asign = _asignacion(libre, n_nuevas)
    partes, pob = [], []
    for t, k in asign.items():
        sub = libre[libre["ticker"] == t]
        k = min(k, len(sub))
        partes.append(sub.sample(k, random_state=SEMILLA))
        pob.append({"ticker": t, "n_pool": len(sub), "n_muestra": k})
    b = pd.concat(partes, ignore_index=True)
    b["bloque"] = "B"
    b["estrato"] = b["ticker"]
    b["lab_modelo"] = pd.NA
    pobdf = pd.DataFrame(pob)
    print("Bloque B (nuevo, ciego al modelo):")
    for r in pobdf.itertuples():
        print(f"  {r.ticker:10s} {r.n_muestra:4d} de {r.n_pool:6d} "
              f"(peso {r.n_pool / r.n_muestra:.1f})")

    cols = ["id", "ticker", "publish_date", "media_name", "title", "url",
            "bloque", "estrato", "lab_modelo"]
    # Un mismo id puede aparecer bajo dos activos (nota que menciona a ambos),
    # asi que el mapa de urls se deduplica antes de indexar.
    urls = pool.drop_duplicates(subset=["id"]).set_index("id")["url"]
    a["url"] = a["id"].map(urls)
    m = pd.concat([a.reindex(columns=cols), b.reindex(columns=cols)],
                  ignore_index=True)

    # --- Peso de muestreo (para reponderar a poblacion) -----------------
    pesoA = _peso_bloque_a(a)
    pesoB = {r.ticker: r.n_pool / r.n_muestra for r in pobdf.itertuples()}
    m["peso"] = [
        pesoA.get(e, float("nan")) if bl == "A" else pesoB.get(e, float("nan"))
        for bl, e in zip(m["bloque"], m["estrato"])
    ]

    # --- Barajado: cualquier PREFIJO es una submuestra valida -----------
    m = m.sample(frac=1.0, random_state=SEMILLA + 1).reset_index(drop=True)
    m.insert(0, "n", range(1, len(m) + 1))
    m["publish_date"] = pd.to_datetime(m["publish_date"]).dt.strftime("%Y-%m-%d")
    m["empresa"] = m["ticker"].map(_nombres()).fillna(m["ticker"])

    hoja = m[["n", "publish_date", "media_name", "empresa", "title", "url"]].copy()
    hoja.columns = ["n", "fecha", "medio", "empresa", "titular", "url"]
    clave = m[["n", "id", "ticker", "bloque", "estrato", "lab_modelo", "peso"]]
    return hoja, clave


def _peso_bloque_a(a: pd.DataFrame) -> dict[str, float]:
    """Pesos del diseno estratificado de julio (ticker x etiqueta v1)."""
    pob = pd.read_csv(INTERIM / "r5_validacion_poblacion.csv")
    pob["estrato"] = pob["ticker"] + "|" + pob["lab_modelo"]
    n_mues = a["estrato"].value_counts()
    return {r.estrato: r.n_poblacion / n_mues.get(r.estrato, 1)
            for r in pob.itertuples() if n_mues.get(r.estrato, 0) > 0}


# ----------------------------------------------------------------------
# Excel
# ----------------------------------------------------------------------
def _titulo(ws, celda: str, texto: str) -> None:
    ws[celda] = texto
    ws[celda].font = Font(name=FUENTE, size=12, bold=True, color=AZUL)


def escribir_excel(hoja: pd.DataFrame, destino: Path) -> None:
    taxonomia = _taxonomia()
    wb = Workbook()

    # ---------------- Instrucciones ----------------
    ins = wb.active
    ins.title = "Instrucciones"
    ins.sheet_view.showGridLines = False
    ins.column_dimensions["A"].width = 4
    ins.column_dimensions["B"].width = 108

    filas = [
        ("t", "Anotacion humana de referencia — R5 (sentimiento)"),
        ("", ""),
        ("p", "Este archivo construye la REFERENCIA con la que se va a medir a los modelos "
              "de lenguaje de R5. Hasta ahora la referencia la habia producido el asistente, "
              "no una persona, asi que la comparacion de modelos ordenaba pero no media."),
        ("", ""),
        ("h", "REGLA DE ORO — juzgar SOLO por el titular"),
        ("p", "El modelo ve unicamente el titular (MediaCloud no devuelve el cuerpo de la nota). "
              "Si usted abre el enlace y decide con informacion que el modelo nunca tuvo, la "
              "referencia mide algo inalcanzable y el modelo sale injustamente mal. Use el "
              "titular. La columna 'url' esta al final solo para casos genuinamente ambiguos: "
              "si la consulta, escriba 'x' en 'duda' y digalo en 'nota'."),
        ("", ""),
        ("h", "QUE se llena (dos columnas amarillas)"),
        ("p", "1) categoria — SIEMPRE. Elija del desplegable la que mejor describa el evento "
              "para LA EMPRESA de esa fila. Es la taxonomia de la hoja 'Taxonomia'."),
        ("p", "2) polaridad — SOLO si la categoria NO empieza con Z. Las Z son de magnitud "
              "cero (o sea, irrelevantes) y no llevan polaridad: dejela vacia."),
        ("p", "La relevancia NO se pregunta aparte. La taxonomia la define: relevante = "
              "categoria A, B o C. Irrelevante = categoria Z. Por eso hay una columna menos."),
        ("", ""),
        ("h", "COMO decidir la polaridad"),
        ("p", "Polaridad = efecto esperado sobre el valor o las perspectivas de la empresa, "
              "NO el tono del titular. 'Utilidad cae 20%' es negativo aunque este redactado "
              "de forma neutra. Si el evento importa pero su signo no se puede saber por el "
              "titular (p. ej. cambio de CEO sin mas contexto), marque 'neutral'."),
        ("", ""),
        ("h", "PUEDE PARAR CUANDO QUIERA"),
        ("p", "Las filas estan en orden ALEATORIO a proposito, asi que cualquier prefijo es una "
              "muestra valida. Si llega a la fila 300 y se cansa, guarde y avise: se analiza "
              "con 300 y no se pierde nada. Lo que NO se puede hacer es saltear filas del "
              "medio ni ORDENAR o FILTRAR la hoja de forma permanente: el orden es la clave "
              "que empareja cada fila con su articulo."),
        ("", ""),
        ("h", "OTRAS COLUMNAS"),
        ("p", "duda — escriba 'x' si dudo o si abrio el enlace. Sirve para medir en que casos "
              "el titular solo no alcanza, que es un resultado reportable por si mismo."),
        ("p", "nota — texto libre, opcional. Util cuando ninguna categoria calza: eso es "
              "evidencia de que la taxonomia necesita un arreglo."),
        ("", ""),
        ("h", "AL TERMINAR"),
        ("p", "Guarde el archivo con el mismo nombre y avise. No hace falta nada mas."),
        ("", ""),
        ("h", "PROGRESO"),
    ]
    r = 1
    for tipo, txt in filas:
        if tipo == "t":
            _titulo(ins, f"B{r}", txt)
            ins[f"B{r}"].font = Font(name=FUENTE, size=15, bold=True, color=AZUL)
        elif tipo == "h":
            ins[f"B{r}"] = txt
            ins[f"B{r}"].font = Font(name=FUENTE, size=11, bold=True, color=AZUL)
        elif tipo == "p":
            ins[f"B{r}"] = txt
            ins[f"B{r}"].font = Font(name=FUENTE, size=10)
            ins[f"B{r}"].alignment = Alignment(wrap_text=True, vertical="top")
            ins.row_dimensions[r].height = 15 * (1 + len(txt) // 105)
        r += 1

    n = len(hoja)
    r0 = r                       # primera fila del bloque de progreso
    prog = [
        ("Filas en total", n),
        ("Anotadas (categoria llena)", f"=COUNTA(Anotacion!$F$2:$F${n + 1})"),
        ("Avance", f"=C{r0 + 1}/C{r0}"),
        ("Relevantes hasta ahora (A/B/C)",
         f'=COUNTA(Anotacion!$F$2:$F${n + 1})'
         f'-COUNTIF(Anotacion!$F$2:$F${n + 1},"Z_*")'),
        ("Marcadas con duda", f'=COUNTIF(Anotacion!$H$2:$H${n + 1},"x")'),
    ]
    for etiqueta, valor in prog:
        ins[f"B{r}"] = etiqueta
        ins[f"C{r}"] = valor
        ins[f"B{r}"].font = Font(name=FUENTE, size=10)
        ins[f"C{r}"].font = Font(name=FUENTE, size=10, bold=True)
        r += 1
    ins.column_dimensions["C"].width = 14
    ins[f"C{r0 + 2}"].number_format = "0.0%"

    # ---------------- Taxonomia ----------------
    tx = wb.create_sheet("Taxonomia")
    tx.sheet_view.showGridLines = False
    cab = ["codigo", "magnitud", "nombre_taxonomia", "definicion"]
    for j, c in enumerate(cab, 1):
        cel = tx.cell(row=1, column=j, value=c)
        cel.font = Font(name=FUENTE, size=10, bold=True, color="FFFFFF")
        cel.fill = PatternFill("solid", start_color=AZUL)
    for i, (cod, mag, nom, defi) in enumerate(taxonomia, start=2):
        tx.cell(row=i, column=1, value=cod).font = Font(name=FUENTE, size=10, bold=True)
        tx.cell(row=i, column=2, value=mag).font = Font(name=FUENTE, size=10)
        tx.cell(row=i, column=2).number_format = "0.0"
        tx.cell(row=i, column=3, value=nom).font = Font(name=FUENTE, size=10)
        c = tx.cell(row=i, column=4, value=defi)
        c.font = Font(name=FUENTE, size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if mag == 0.0:
            for j in range(1, 5):
                tx.cell(row=i, column=j).fill = PatternFill("solid", start_color=GRIS)
    for col, w in zip("ABCD", (26, 10, 24, 78)):
        tx.column_dimensions[col].width = w
    tx.freeze_panes = "A2"
    tx["F1"] = "Las filas grises son de magnitud CERO: son la abstencion (irrelevante)."
    tx["F1"].font = Font(name=FUENTE, size=10, italic=True)

    # ---------------- Anotacion ----------------
    ws = wb.create_sheet("Anotacion")
    cabecera = ["n", "fecha", "medio", "empresa", "titular",
                "categoria", "polaridad", "duda", "nota", "url"]
    anchos = [6, 11, 16, 30, 92, 26, 12, 7, 34, 55]
    for j, (c, w) in enumerate(zip(cabecera, anchos), 1):
        cel = ws.cell(row=1, column=j, value=c)
        cel.font = Font(name=FUENTE, size=10, bold=True, color="FFFFFF")
        cel.fill = PatternFill("solid", start_color=AZUL)
        cel.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.row_dimensions[1].height = 22

    borde = Side(style="thin", color="D9D9D9")
    for i, fila in enumerate(hoja.itertuples(index=False), start=2):
        vals = [fila.n, fila.fecha, fila.medio, fila.empresa, fila.titular,
                None, None, None, None, fila.url]
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=i, column=j, value=v)
            c.font = Font(name=FUENTE, size=10)
            c.border = Border(bottom=borde)
            c.alignment = Alignment(vertical="center",
                                    wrap_text=(j == 5),
                                    horizontal="center" if j in (1, 2, 8) else "left")
            if j in (6, 7, 8, 9):
                c.fill = PatternFill("solid", start_color=AMARILLO)
            if j == 10:
                c.font = Font(name=FUENTE, size=8, color="808080")
        ws.row_dimensions[i].height = 28

    dv_cat = DataValidation(type="list", formula1=f"=Taxonomia!$A$2:$A${len(taxonomia) + 1}",
                            allow_blank=True, showDropDown=False)
    dv_cat.error = "Elija una categoria del desplegable (hoja Taxonomia)."
    dv_cat.errorTitle = "Categoria no valida"
    ws.add_data_validation(dv_cat)
    dv_cat.add(f"F2:F{len(hoja) + 1}")

    dv_pol = DataValidation(type="list", formula1='"positivo,negativo,neutral"',
                            allow_blank=True, showDropDown=False)
    dv_pol.error = "Solo positivo, negativo o neutral. Vacia si la categoria es Z."
    dv_pol.errorTitle = "Polaridad no valida"
    ws.add_data_validation(dv_pol)
    dv_pol.add(f"G2:G{len(hoja) + 1}")

    dv_duda = DataValidation(type="list", formula1='"x"', allow_blank=True,
                             showDropDown=False)
    ws.add_data_validation(dv_duda)
    dv_duda.add(f"H2:H{len(hoja) + 1}")

    ws.freeze_panes = "F2"
    ws.auto_filter.ref = f"A1:J{len(hoja) + 1}"
    ws.sheet_view.zoomScale = 100

    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)


# ----------------------------------------------------------------------
def _potencia(n: int) -> None:
    """Que compra este tamano de muestra, contra lo que habia (n=180)."""
    tasas = {"gemma3:4b (el mas inclusivo)": 0.394,
             "gemma3:27b": 0.222,
             "gemma3:12b": 0.150,
             "qwen2.5:14b / 32b (los mas restrictivos)": 0.128}
    print(f"\nPRECISION DE LA MEDIDA (IC 95% de la precision, supuesta p=0.75)")
    print(f"{'modelo':44s} {'n=180':>12s} {'n=' + str(n):>12s}")
    for m, tasa in tasas.items():
        def h(N):
            k = N * tasa
            return 1.96 * math.sqrt(.75 * .25 / k) * 100 if k >= 1 else float("nan")
        print(f"{m:44s} {'±%.1fpp' % h(180):>12s} {'±%.1fpp' % h(n):>12s}")
    rel = 0.30
    print(f"\nRecall (sobre las ~{rel:.0%} realmente relevantes, supuesto p=0.60):")
    for N in (180, n):
        k = N * rel
        print(f"  n={N:<5d} -> {int(k):3d} relevantes, "
              f"±{1.96 * math.sqrt(.6 * .4 / k) * 100:.1f}pp")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-nuevas", type=int, default=430,
                    help="tamano del bloque B (muestra nueva, ciega al modelo)")
    ap.add_argument("--n-bloque-a", type=int, default=120,
                    help="cuantas de las 180 ya anotadas por el asistente se "
                         "reanotan (para el kappa autor-vs-asistente)")
    ap.add_argument("--salida", default=str(SALIDA / "muestra_r5_anotar.xlsx"))
    args = ap.parse_args()

    if not ANOTADA.exists():
        sys.exit(f"Falta {ANOTADA}")

    hoja, clave = construir(args.n_nuevas, args.n_bloque_a)
    destino = Path(args.salida)
    escribir_excel(hoja, destino)

    clv = destino.parent / "clave_muestra_r5.csv"
    clave.to_csv(clv, index=False, encoding="utf-8")

    print(f"\nExcel   -> {destino}  ({len(hoja)} filas)")
    print(f"Clave   -> {clv}   (NO abrir hasta terminar de anotar)")
    _potencia(len(hoja))


if __name__ == "__main__":
    main()
