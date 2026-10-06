"""Informe Bursátil Mensual de la BVL — fuente OFICIAL de negociación por emisor.

Por qué existe este módulo
--------------------------
El endpoint primario de la BVL (share-values) entrega SOLO el cierre diario:
`market_client.fetch_bvl` pone `volume = NaN`. Yahoo era la única alternativa y
se descartó como cantidad autoritativa: no reconcilia con el dato oficial de la
BVL (razón Yahoo/oficial entre 0.16x y 5.12x el mismo día), reporta volumen 0 en
5-15% de los días en que el precio SÍ cambió, y su correlación volumen-|retorno|
es casi nula (validación completa en scripts/probe_yahoo_confiabilidad.py).

El Informe Bursátil Mensual es la fuente oficial que sí cierra ese hueco:
publicación de la propia BVL, PDF, URL predecible y cobertura 2012-2026.

  https://documents.bvl.com.pe/pubdif/infmen/M{YYYY}_{MM}.pdf

Tabla "Renta Variable — Valores Negociados", 20 columnas por EMISOR y por MES:
  acciones en circulación | valor nominal | capitalización bursátil |
  valor contable | ISIN | nemónico | CANTIDAD NEGOCIADA | MONTO EFECTIVO S/ |
  MONTO EFECTIVO US$ | % del total | N° de operaciones | FRECUENCIA (%) |
  apertura | cierre | máxima | mínima | promedio | C.M.T. | rotación |
  rendimiento mensual

Parseo
------
El formato de columnas es IDÉNTICO en 2013, 2019 y 2025; lo único que cambia es
que los PDF antiguos NO traen líneas de tabla, así que `extract_tables` falla en
ellos. Por eso se parsea por TEXTO anclando en el ISIN, que parte la línea igual
en ambas épocas. El ISIN se reconoce con el patrón estándar (2 letras de país +
9 alfanuméricos + dígito de control) y NO restringido a "PE": InRetail es un
holding panameño y su ISIN empieza en "PA".

Granularidad: MENSUAL. Sirve para acotar capacidad y para medir liquidez con la
`frecuencia` oficial, pero NO reemplaza una serie diaria de volumen (que no
existe en ninguna fuente disponible salvo el último día vía listLastValue).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

_URL = "https://documents.bvl.com.pe/pubdif/infmen/M{y}_{m:02d}.pdf"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}

_PDF_DIR = Path("data/raw/bvl_infmen")
_CACHE = Path("data/interim/bvl_mensual.parquet")

# ISIN estándar. NO restringir a "PE" (InRetail = PAL1801171A1).
_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
# Nemónico BVL: letras + sufijo de clase/serie. Puede traer notas al pie "(3)".
_NEM = re.compile(r"^([A-Z]{2,10}[A-Z0-9]\d)(\(.*\))?$")
_NOTA = re.compile(r"^\(\d+([,\d]*)\)$")
# El acumulado semestral del Anexo Estadístico es OTRA tabla con las mismas
# columnas: hay que excluirlo o se mezclarían meses con semestres.
_ACUMULADO = re.compile(r"ENERO\s*[-–]\s*\w+", re.I)

# DISCRIMINADOR del acumulado: sus columnas de cotización traen la FECHA en que
# se alcanzó el máximo/mínimo ("1.47 31/03"), cosa que la tabla mensual no hace.
# Es la única marca fiable a nivel de FILA, y hace falta: en algunos informes la
# tabla mensual no tiene capa de texto y, sin este filtro, se colaría el
# acumulado del trimestre haciéndose pasar por un mes.
_FECHA_DM = re.compile(r"^\d{2}/\d{2}$")

# Números tal como salen del PDF: '1,234.56', '-.-', '82.26', '$1,2', '0.77%'.
_NUMERICO = re.compile(r"^[$]?-?[\d,]+\.?\d*[%]?$")

# Algunos informes (2016-2019) embeben la fuente sin ToUnicode y pdfplumber
# devuelve los glifos como '(cid:NN)'. El desplazamiento es constante:
# cid = ASCII - 29 (verificado: '(cid:28)(cid:21)(cid:24)(cid:15)...' -> '925,...').
_CID = re.compile(r"\(cid:(\d+)\)")


def _decid(texto: str) -> str:
    """Recupera el texto de los PDF cuya fuente no trae mapa Unicode."""
    if "(cid:" not in texto:
        return texto
    return _CID.sub(lambda m: chr(int(m.group(1)) + 29), texto)

# Campos posteriores al nemónico, en orden (14 tras normalizar los tokens).
_POST = ["cantidad_negociada", "monto_pen", "monto_usd", "pct_total",
         "n_operaciones", "frecuencia", "apertura", "cierre", "maxima",
         "minima", "promedio", "cmt", "rotacion", "rendim_mensual"]

_NUM_COLS = ["acciones_circulacion", "valor_nominal", "capitalizacion",
             "valor_contable", "cantidad_negociada", "monto_pen", "monto_usd",
             "pct_total", "n_operaciones", "frecuencia", "apertura", "cierre",
             "maxima", "minima", "promedio", "cmt", "rotacion", "rendim_mensual"]


# ── descarga ─────────────────────────────────────────────────────────────────
def informe_path(year: int, month: int, pdf_dir: Path = _PDF_DIR) -> Path:
    return pdf_dir / f"M{year}_{month:02d}.pdf"


def download_informe(year: int, month: int, pdf_dir: Path = _PDF_DIR,
                     force: bool = False) -> Path | None:
    """Descarga un informe mensual (con caché en disco). None si no existe."""
    import requests

    dest = informe_path(year, month, pdf_dir)
    if dest.exists() and not force and dest.stat().st_size > 0:
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(_URL.format(y=year, m=month), headers=_HEADERS, timeout=120)
    except Exception as exc:
        print(f"[infmen] {year}-{month:02d}: fallo de red ({exc})")
        return None
    if r.status_code != 200 or not r.content:
        return None
    dest.write_bytes(r.content)
    return dest


# ── parseo ───────────────────────────────────────────────────────────────────
def _normaliza(tokens: list[str]) -> list[str]:
    """Reune tokens partidos por el extractor de texto.

    En los informes recientes la rotación y el rendimiento salen como
    '0.770' '%' (dos tokens) y el monto en dólares como '$' '6,473,583.47'.
    Tras esta normalización la cola siempre tiene 14 campos, como en 2013.
    """
    out: list[str] = []
    for t in tokens:
        if t == "%" and out:
            out[-1] += "%"
        elif t == "$":
            out.append("$")          # se une con el siguiente en la pasada final
        elif out and out[-1] == "$":
            out[-1] = "$" + t
        else:
            out.append(t)
    return out


def _parse_linea(linea: str) -> dict | None:
    """Convierte una línea de la tabla de renta variable en un registro."""
    tok = linea.split()
    idx = next((i for i, t in enumerate(tok) if _ISIN.match(t)), None)
    if idx is None or idx + 1 >= len(tok):
        return None

    m = _NEM.match(tok[idx + 1])
    if not m:
        return None

    antes = tok[:idx]
    if len(antes) < 3:
        return None          # las tablas de renta FIJA abren con el ISIN

    # Los 3 primeros campos (acciones, nominal, capitalización) son numéricos o
    # '-.-'. Exigirlo descarta otras tablas del informe que también traen ISIN.
    cab = antes[:3]
    if not all(t == "-.-" or _NUMERICO.match(t) for t in cab):
        return None
    if not any(_NUMERICO.match(t) for t in cab):
        return None

    # La cola del bloque previo es un marcador de moneda del valor contable
    # ('M' = moneda nacional, o '-.-'): no es un campo de datos.
    despues = _normaliza([t for t in tok[idx + 2:] if not _NOTA.match(t)])
    if any(_FECHA_DM.match(t) for t in despues):
        return None          # fila del acumulado trimestral/semestral, no mensual

    reg: dict[str, str | None] = {
        "nemonico": m.group(1),
        "isin": tok[idx],
        "acciones_circulacion": antes[0],
        "valor_nominal": antes[1],
        "capitalizacion": antes[2],
        "valor_contable": antes[3] if len(antes) > 3 else None,
    }
    for k, v in zip(_POST, despues):
        reg[k] = v
    for k in _POST:
        reg.setdefault(k, None)
    return reg


def _num(x) -> float:
    """'-.-' -> NaN; '1,234.56' -> 1234.56; '$1,2' y '0.77%' se limpian."""
    if x is None:
        return float("nan")
    s = str(x).strip().replace(",", "").replace("$", "").replace("%", "")
    if s in ("", "-.-", "-", "."):
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def parse_informe(pdf_path: Path) -> pd.DataFrame:
    """Extrae la tabla mensual de renta variable de UN informe.

    Devuelve una fila por valor listado (todos los emisores, no solo el universo)
    con los campos numéricos ya convertidos. `moneda_precio` distingue los
    valores que cotizan en US$ (InRetail): sus cotizaciones vienen con '$'.
    """
    import pdfplumber

    # NO se filtra por el encabezado "RENTA VARIABLE": en varios informes (p.ej.
    # 2021) el título solo aparece en la PRIMERA página de la tabla y las de
    # continuación quedaban fuera (se perdían todos los activos salvo los bancos).
    # En su lugar la fila se identifica sola por su forma, y el orden del
    # documento resuelve el resto: la tabla mensual siempre precede al acumulado
    # del anexo, así que basta con quedarse con la primera aparición.
    filas: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = _decid(page.extract_text() or "")
            for linea in txt.split("\n"):
                reg = _parse_linea(linea)
                if reg:
                    filas.append(reg)

    if not filas:
        return pd.DataFrame()

    df = pd.DataFrame(filas)
    df["moneda_precio"] = df["cierre"].astype(str).str.startswith("$").map(
        {True: "USD", False: "PEN"})
    for c in _NUM_COLS:
        df[c] = df[c].map(_num)

    # Un mismo nemónico puede repetirse si el informe lista el valor en más de
    # una página (continuaciones): se conserva la primera aparición.
    return df.drop_duplicates(subset="nemonico", keep="first").reset_index(drop=True)


# ── orquestación ─────────────────────────────────────────────────────────────
def build_mensual(start_year: int = 2012, end_year: int = 2026,
                  pdf_dir: Path = _PDF_DIR, force_download: bool = False,
                  verbose: bool = True) -> pd.DataFrame:
    """Descarga y parsea todos los informes del rango.

    Devuelve un panel mensual (una fila por nemónico y mes) con `periodo`
    (Period[M]) y `date` = último día del mes del informe.
    """
    partes: list[pd.DataFrame] = []
    for y in range(start_year, end_year + 1):
        for mth in range(1, 13):
            p = download_informe(y, mth, pdf_dir, force=force_download)
            if p is None:
                continue
            try:
                df = parse_informe(p)
            except Exception as exc:
                print(f"[infmen] {y}-{mth:02d}: fallo al parsear ({exc})")
                continue
            if df.empty:
                print(f"[infmen] {y}-{mth:02d}: 0 filas extraídas")
                continue
            df.insert(0, "periodo", pd.Period(year=y, month=mth, freq="M"))
            partes.append(df)
            if verbose:
                print(f"[infmen] {y}-{mth:02d}: {len(df):4d} valores")

    if not partes:
        return pd.DataFrame()

    out = pd.concat(partes, ignore_index=True)
    out["date"] = out["periodo"].dt.to_timestamp(how="end").dt.normalize()
    return out.sort_values(["periodo", "nemonico"]).reset_index(drop=True)


def load_mensual(cache: Path = _CACHE, refresh: bool = False, **kwargs) -> pd.DataFrame:
    """Panel mensual oficial, con caché en parquet."""
    if cache.exists() and not refresh:
        df = pd.read_parquet(cache)
        df["periodo"] = df["periodo"].astype("period[M]")
        return df

    df = build_mensual(**kwargs)
    if df.empty:
        return df
    cache.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["periodo"] = out["periodo"].astype(str)
    out.to_parquet(cache)
    return df


def panel_activo(nemonico: str, df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Serie mensual de un activo, ordenada por periodo."""
    df = load_mensual() if df is None else df
    return df[df["nemonico"] == nemonico].sort_values("periodo").reset_index(drop=True)
