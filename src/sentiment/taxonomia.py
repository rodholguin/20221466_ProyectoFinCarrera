"""Taxonomía de eventos y prefiltro de relevancia para R5 (prompt v2).

Especificación completa y evidencia: docs/taxonomia_eventos_R5.txt
Decisión que lo ordena: D11 en docs/decisiones_pendientes_OE1.txt

DOS DECISIONES ESTRUCTURALES QUE IMPLEMENTA ESTE MÓDULO:
  (A) La polaridad SOLO aplica a categorías de magnitud > 0. Se fuerza en código
      (`normaliza`), no se confía en que el modelo obedezca el prompt. Esto elimina
      por construcción el error dominante medido en julio: 49% de las etiquetas
      con signo venían de noticias que no hablaban de la empresa.
  (B) Las categorías de magnitud CERO SON la abstención. No hace falta un "no sé"
      separado: preguntar "¿de qué tipo es?" es más fácil y objetivo para un
      modelo chico que pedirle que se autoevalúe (su `confidence` está medido y
      no discrimina: 0.750 en errores vs 0.730 en aciertos).
"""
from __future__ import annotations

import re
import unicodedata

# ── Taxonomía: categoría -> (magnitud ex-ante, glosa para el prompt) ─────────
# La magnitud la fija el AUTOR, no el LLM. Es auditable en la sustentación y se
# recalibra sin re-pagar el LLM (se aplica río abajo, en R6).
TAXONOMIA: dict[str, tuple[float, str]] = {
    # ── magnitud ALTA ────────────────────────────────────────────────────────
    "resultados": (
        1.0, "utilidad, ingresos, ventas, márgenes, estados financieros, balance"),
    "ma_reestructuracion": (
        1.0, "compra o venta de empresas, fusión, adquisición, escisión"),
    "crisis_evento_adverso": (
        1.0, "accidente, derrame, fraude, investigación, sanción, huelga, conflicto"),
    "regulatorio_material": (
        1.0, "norma, tarifa, arancel, antidumping o fallo que afecta al negocio"),
    # ── magnitud MEDIA ───────────────────────────────────────────────────────
    "estrategia_inversion": (
        0.6, "inversión, nueva planta, tienda o mina, expansión, entrada a un mercado"),
    "dividendo_capital": (
        0.6, "dividendo, recompra, emisión de acciones o bonos, deuda, financiamiento"),
    "operacional": (
        0.6, "producción, volúmenes, despachos, contratos ganados, operación diaria"),
    "gobierno_corporativo": (
        0.6, "cambio de gerente general, directorio, renuncia o nombramiento"),
    # ── magnitud BAJA ────────────────────────────────────────────────────────
    "analisis_opinion": (
        0.3, "recomendación de analista, precio objetivo, calificación de riesgo"),
    # ── magnitud CERO — esto es el filtro de relevancia ───────────────────────
    # sector_macro BAJÓ de 0.3 a 0.0 el 2026-08-18 tras el Piloto A. Dos razones:
    # (1) redundancia con las 6 features macro del panel, ya anotada en el diseño;
    # (2) LA DECISIVA — se volvió el BASURERO del modelo: 55 de 180 predicciones
    #     (30.6%) y solo 29.1% de ellas relevantes de verdad. En CREDITC1, 18 de
    #     sus 19 `sector_macro` eran notas de tipo de cambio.
    # Efecto medido del cambio: exactitud 65.6% -> 78.3%, precisión 46.3% -> 64.2%,
    # polaridad espuria 42.7% -> 32.6%. Ver docs/taxonomia_eventos_R5.txt §7.9.
    "sector_macro": (
        0.0, "habla del sector o del precio del metal/insumo SIN mencionar un "
             "hecho concreto de la empresa"),
    "indice_bursatil": (
        0.0, "crónica de la sesión de la BVL, índices, lista de ganadores y perdedores"),
    "patrocinio_rse": (
        0.0, "auspicio, donación, responsabilidad social, deporte, evento benéfico"),
    "marketing_promocion": (
        0.0, "oferta, promoción, lanzamiento de producto, apertura de local"),
    "mencion_incidental": (
        0.0, "la empresa aparece solo como dato, fuente o ejemplo, y la noticia "
             "trata de otro tema (tipo de cambio, política, otra empresa)"),
    "no_relevante": (
        0.0, "el titular no trata de esta empresa en absoluto"),
}

CATEGORIAS = tuple(TAXONOMIA)
CON_POLARIDAD = tuple(c for c, (m, _) in TAXONOMIA.items() if m > 0)
SIN_POLARIDAD = tuple(c for c, (m, _) in TAXONOMIA.items() if m == 0)
POLARIDADES = ("positivo", "negativo", "neutral")

# Categoría sentinela: el modelo devolvió algo no parseable o inválido. NO es una
# clasificación — se cuenta aparte y no entra en las features. Distinguirla de un
# "neutral" legítimo es justo lo que v1 no hacía (mapeaba el fallo a neutral).
ERROR = "_error_parseo"


def magnitud(categoria: str) -> float:
    """Magnitud ex-ante de una categoría. Desconocida o error -> 0.0."""
    return TAXONOMIA.get(categoria, (0.0, ""))[0]


def es_relevante(categoria: str) -> bool:
    """Relevante == magnitud > 0. Es la definición operativa del canal."""
    return magnitud(categoria) > 0.0


def normaliza(categoria: str | None, polaridad: str | None) -> tuple[str, str | None]:
    """Aplica la decisión (A): la polaridad solo sobrevive si la magnitud es > 0.

    Se fuerza SIEMPRE, diga lo que diga el modelo. Una categoría desconocida se
    marca como ERROR en vez de degradarse a una etiqueta plausible.
    """
    cat = (categoria or "").strip().lower()
    if cat not in TAXONOMIA:
        return ERROR, None
    if not es_relevante(cat):
        return cat, None                      # abstención estructural
    pol = (polaridad or "").strip().lower()
    return cat, (pol if pol in POLARIDADES else "neutral")


# ─────────────────────────────────────────────────────────────────────────────
# PREFILTRO REGEX (FIX 1) — optimizador de COSTO, no mecanismo de corrección.
#
# ASIMETRÍA DELIBERADA: un falso positivo descarta una noticia real SIN
# APELACIÓN; un falso negativo solo cuesta una llamada al LLM (~12 s). Por eso
# solo se atrapa lo INEQUÍVOCO y ante la duda se deja pasar: lo que se escape lo
# recoge la categoría correspondiente de la taxonomía.
#
# Medido contra las 180 noticias anotadas a mano (docs/taxonomia_eventos_R5.txt
# §7.5): descarta 25.6% con CERO noticias relevantes perdidas, y sube la
# relevancia del corpus de 30.0% a 40.3%.
# ─────────────────────────────────────────────────────────────────────────────

_INDICE = [
    r"\bbvl\b.*\b(cierr|sub|baj|retroced|avanz|gan|pierd|opera|abr|cae|cay)",
    r"\b(indice|indices)\b.*\bbvl\b",
    r"bolsa de valores de lima",
    r"bolsa (limena|limeña)",
    r"bolsa de lima",
    r"\bindice (general|selectivo|referencial)\b",
    r"s&p/?bvl",
    r"papeles lideres",
]

# OJO: NO incluir "mundial". Captura "potencia mundial", "líder mundial",
# "precio mundial", "Banco Mundial" — vocabulario CENTRAL de minería y
# commodities. Con MINSURI1 en el universo ("segundo productor mundial de
# estaño") mataría noticias reales. Riesgo detectado y corregido el 2026-08-18.
_PATROCINIO = [
    r"\bpatrocin",
    r"\bauspici",
    r"\bteleton\b",
    r"\bdona(cion|ciones|ra|ron|do)\b",
    r"\bvoluntariado\b",
    r"responsabilidad social",
    r"\b(copa|torneo|campeonato|maraton) ",
    r"\bseleccion peruana\b",
    r"utiles escolares",
]

_RE_INDICE = re.compile("|".join(_INDICE))
_RE_PATROCINIO = re.compile("|".join(_PATROCINIO))

PASA = "pasa"


def _sin_tildes(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def prefiltro(titulo: str) -> str:
    """Clasificación barata previa al LLM.

    Devuelve la CATEGORÍA de la taxonomía si el titular es inequívocamente ruido
    (`indice_bursatil` o `patrocinio_rse`), o PASA si hay que consultar al LLM.
    Devolver la categoría —y no un booleano— hace que el prefiltro y el LLM
    alimenten exactamente el mismo esquema, sin ramas especiales río abajo.
    """
    t = _sin_tildes(titulo)
    if _RE_INDICE.search(t):
        return "indice_bursatil"
    if _RE_PATROCINIO.search(t):
        return "patrocinio_rse"
    return PASA


def bloque_categorias_prompt() -> str:
    """Renderiza la taxonomía para el prompt, AGRUPADA por si lleva polaridad.

    Agrupar ayuda a un modelo chico a razonar por eliminación (y es la mitigación
    registrada para el riesgo de que 14 categorías sean demasiadas para gemma3:4b).
    """
    con = "\n".join(f"- {c}: {TAXONOMIA[c][1]}" for c in CON_POLARIDAD)
    sin = "\n".join(f"- {c}: {TAXONOMIA[c][1]}" for c in SIN_POLARIDAD)
    return (
        "GRUPO A — hechos de la empresa (requieren polaridad):\n" + con +
        "\n\nGRUPO B — NO son hechos de la empresa (sin polaridad):\n" + sin
    )
