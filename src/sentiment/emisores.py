"""¿El TITULAR nombra a la empresa (o a una marca suya)? — bandera de D17.

QUÉ RESUELVE. MediaCloud busca sobre el TEXTO COMPLETO del artículo, así que el
corpus incluye todo el que mencione al emisor en cualquier parte: como fuente,
como dato, como ejemplo. Medido sobre los 7 activos, SOLO EL 16.2% DEL CORPUS
(3,162 de 19,528) nombra a la empresa en el titular — y ese estrato es donde
vive la señal (D17):

    estrato    relevancia humana   ponderada   precisión del LLM (v2.1)
    NOMBRA               63.8%       44.0%              88.6%
    anónimo               2.1%        1.1%              16.7%

El 83% de los falsos positivos y el 83% de la polaridad espuria del canal salen
del estrato anónimo. Es el resto del error que D11 atacó por construcción en
julio (49% de las etiquetas con signo venían de noticias que no hablaban de la
empresa) y que v2.1 redujo sin cerrar.

SE MARCA, NO SE FILTRA. Esta bandera NO descarta artículos: el LLM sigue
corriendo sobre el corpus completo y la decisión de restringir el canal se toma
río abajo, en R6/build_dataset, como brazo pre-registrado de la ablación de R8
(canal completo vs canal restringido). Es el mismo patrón que D11: la decisión
se mueve a donde es barato revertirla, porque restringir conservaría el 80.4% de
los eventos relevantes — y el 19.6% que se pierde NO es basura (el apagón de
Surco/Miraflores, el inicio de la venta de Sempra, el EIA de Senace).

POR QUÉ INCLUYE MARCAS COMERCIALES Y NO SOLO LA RAZÓN SOCIAL. Es donde vive la
noticia: `yape` son 607 titulares —el segundo término más frecuente del corpus
de BCP— y `plaza vea` 162 en el de InRetail. Sin las marcas la bandera mediría
otra cosa.

ES MÁS PERMISIVA QUE LA QUERY, A PROPÓSITO. Opera sobre un corpus YA anclado por
mediacloud_client._build_query, así que puede usar `pacasmayo` a secas donde la
query necesita `(Pacasmayo AND (cemento OR cementera OR planta))`.

LÍMITE DECLARADO: los estratos de la validación son n=58 nombrados y n=420
anónimos (37 y 9 relevantes). El tamaño del efecto es enorme —30x en relevancia,
5x en precisión— y por eso se cree, pero los intervalos son anchos. Marcar en
vez de filtrar es la mitigación de ese límite.

Decisión que lo ordena: D17 en docs/decisiones_pendientes_OE1.txt.
"""
from __future__ import annotations

import re
import unicodedata

# ── Diccionario por emisor: razón social + filiales + MARCAS COMERCIALES ─────
# Los conteos son los titulares del corpus que matchean cada bloque (2026-08-30).
NOMBRES_EMISOR: dict[str, str] = {
    # Perímetro decidido en D17 parte 1: el activo es el BANCO, la ventana de
    # noticias es el GRUPO. `credicorp` se INCLUYE — ahí vive el Helm Bank y la
    # sanción de Indecopi. `prima afp` y `pacifico seguros` son HERMANAS (de
    # Credicorp, no de BCP): se incluyen por consistencia y son 21 titulares.
    "CREDITC1": r"banco de credito|\bbcp\b|credicorp|\byape\b|\bmibanco\b"
                r"|prima afp|\bkrealo\b|pacifico seguros",
    "ALICORC1": r"\balicorp\b|\bprimor\b|\bsapolio\b|don vittorio|blanca flor"
                r"|\bnicolini\b|\bintradevco\b",
    "CPACASC1": r"\bpacasmayo\b|fosfatos del pacifico",
    "FERREYC1": r"\bferreycorp\b|\bferreyros\b|\bunimaq\b|\borvisa\b|\bmotored\b",
    # `intercorp` es la MATRIZ: mismo criterio que `credicorp` para BCP.
    "INRETC1":  r"\binretail\b|supermercados peruanos|plaza vea|\binkafarma\b"
                r"|\bmifarma\b|\bvivanda\b|real plaza|\bmass\b|\bintercorp\b"
                r"|\bquicorp\b|\beconomax\b",
    "LUSURC1":  r"luz del sur|\btecsur\b",
    "MINSURI1": r"\bminsur\b|mina justa|\bmarcobre\b|\bpucamarca\b|\btaboca\b"
                r"|\braura\b",
    # ── Universo VIEJO. Se conservan para poder reprocesar corridas anteriores
    # (misma convención que _build_query). NO están validados contra anotación.
    "BUENAVC1": r"buenaventura|\byanacocha\b|\bcerro verde\b|\bel brocal\b",
    "SAGAC1":   r"saga falabella|\bfalabella\b|\btottus\b|\bsodimac\b",
    "CORAREC1": r"aceros arequipa|\bcorarec\b",
}

# ── Exclusiones: el término existe pero apunta a otra cosa ───────────────────
# `ferreyros` ES UN APELLIDO. De sus 74 titulares cerca de la mitad son personas:
# Ramón Ferreyros (empresario), Andrea Ferreyros (TV) y sobre todo el EX-MINISTRO
# Eduardo Ferreyros (TPP, exportaciones, Dakar). Sin esta regla FERREYC1 pasa de
# 129 a 152 titulares "nombrados", 23 de ellos falsos.
EXCLUSIONES: dict[str, str] = {
    "FERREYC1": r"ministr[oa] ferreyros|ram[oó]n ferreyros|andrea ferreyros"
                r"|eduardo ferreyros",
}

# Si el titular ALSO nombra a la empresa sin ambigüedad, la exclusión no aplica:
# "Ferreycorp: Ramón Ferreyros dice que..." sigue siendo noticia de Ferreycorp.
RESCATES: dict[str, str] = {
    "FERREYC1": r"\bferreycorp\b|\bunimaq\b|\borvisa\b|\bmotored\b",
}

# POR QUÉ `nicolini` SE QUEDA AQUÍ Y NO DEBE IRSE A LA QUERY (medido 2026-08-30).
# En la colección Perú Nacional `"Nicolini"` da 2,114 artículos, y solo el 1.7%
# menciona a Alicorp: es sobre todo el APELLIDO (la familia). Ese número invita a
# quitarlo — sería un error. En el CORPUS YA ANCLADO de ALICORC1 hay 3 titulares
# con `nicolini` y los 3 son la marca de harina ("Regresa el tradicional
# Recetario Nicolini"). Es exactamente la asimetría que justifica que la bandera
# sea más permisiva que la query: el ancla ya hizo el trabajo de desambiguar.
# La lección general: un término se juzga contra el CORPUS del activo, no contra
# la colección. Mismo caso que `pacasmayo` y `mass`.
#
# TÉRMINOS EVALUADOS Y RECHAZADOS (2026-08-30), con el motivo medido:
#   `inland energy`  NO es Luz del Sur: es otra empresa (Majes II, Gobierno
#                    Regional de Arequipa). 4 titulares, los 4 ajenos.
#   `caterpillar`    es la marca que Ferreycorp DISTRIBUYE, no Ferreycorp.
#   `bolivar`, `opal`  0 hits en el corpus.
#   `casino`         2 hits, y es también casa de juego. No paga el riesgo.
# TÉRMINO VERIFICADO Y ACEPTADO: `mass` (InRetail) parecía riesgoso; se
# inspeccionaron los 17 titulares que no nombran otra marca y TODOS son la
# cadena de descuento. El ancla de la query ya acota el corpus.


def _sin_tildes(s: str) -> str:
    """Misma normalización que taxonomia._sin_tildes: el corpus mezcla acentos."""
    s = unicodedata.normalize("NFD", str(s).lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


_RE_NOMBRES = {tk: re.compile(p) for tk, p in NOMBRES_EMISOR.items()}
_RE_EXCL = {tk: re.compile(p) for tk, p in EXCLUSIONES.items()}
_RE_RESC = {tk: re.compile(p) for tk, p in RESCATES.items()}


def nombra_empresa(ticker: str, titulo: str) -> bool:
    """¿El titular nombra al emisor o a una marca suya?

    Un ticker sin diccionario devuelve False y NO revienta: la bandera es
    informativa y no debe tumbar una corrida. Pero eso haría que TODO el activo
    quedara marcado como anónimo, así que `tickers_sin_diccionario` existe para
    detectarlo antes de correr (la lección de _build_query, que antes caía en un
    default silencioso e invalidaba el corpus sin avisar).
    """
    rx = _RE_NOMBRES.get(ticker)
    if rx is None:
        return False
    t = _sin_tildes(titulo)
    if not rx.search(t):
        return False
    excl = _RE_EXCL.get(ticker)
    if excl is not None and excl.search(t):
        resc = _RE_RESC.get(ticker)
        if resc is None or not resc.search(t):
            return False
    return True


def tickers_sin_diccionario(tickers) -> list[str]:
    """Tickers que no tienen entrada. Llamar ANTES de una corrida.

    Un activo sin diccionario saldría 100% anónimo y el brazo restringido de la
    ablación lo dejaría fuera ENTERO, en silencio. Vale más fallar temprano.
    """
    return [t for t in tickers if t not in NOMBRES_EMISOR]
