"""Genera el informe en Word para la reunión con el especialista.

Convierte docs/resumen_para_especialista_20260902.txt a un .docx presentable:
encabezados jerárquicos, tablas de verdad, cajas de resumen y las preguntas en
una hoja aparte al final.

Uso:  python scripts/gen_informe_especialista.py
Salida: docs/Informe_BVL_DRL_para_especialista.docx
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "Informe_BVL_DRL_para_especialista.docx"

AZUL = RGBColor(0x1F, 0x3A, 0x5F)      # títulos
GRIS = RGBColor(0x59, 0x59, 0x59)      # texto secundario
ACENTO = RGBColor(0x8C, 0x1D, 0x18)    # advertencias / preguntas
HEX_CAB = "1F3A5F"                     # fondo de cabecera de tabla
HEX_CAJA = "EEF2F7"                    # fondo de caja destacada
HEX_PREG = "FBF0EF"                    # fondo de caja de pregunta


# ── utilidades de formato ────────────────────────────────────────────────────
def _sombrear(celda, hexcolor: str) -> None:
    tc = celda._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), hexcolor)
    tc.append(shd)


def _bordes_tabla(tabla) -> None:
    tblPr = tabla._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for lado in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{lado}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), "BFC9D4")
        borders.append(el)
    tblPr.append(borders)


def titulo(doc, texto, nivel=1):
    h = doc.add_heading(texto, level=nivel)
    for r in h.runs:
        r.font.color.rgb = AZUL
        r.font.name = "Calibri"
    return h


def parrafo(doc, texto, cursiva=False, color=None, size=10.5, space_after=6):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run(texto)
    r.font.size = Pt(size)
    r.italic = cursiva
    if color is not None:
        r.font.color.rgb = color
    return p


def rico(doc, partes, size=10.5, space_after=6):
    """partes = [(texto, negrita), ...] — para resaltar dentro de un párrafo."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for texto, negrita in partes:
        r = p.add_run(texto)
        r.font.size = Pt(size)
        r.bold = negrita
    return p


def vinneta(doc, texto, size=10.5):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(texto)
    r.font.size = Pt(size)
    return p


def caja(doc, titulo_caja, cuerpo, fondo=HEX_CAJA, color_titulo=AZUL):
    """Caja de una celda para destacar un mensaje."""
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.cell(0, 0)
    _sombrear(c, fondo)
    _bordes_tabla(t)
    c.paragraphs[0].text = ""
    p1 = c.paragraphs[0]
    r1 = p1.add_run(titulo_caja)
    r1.bold = True
    r1.font.size = Pt(10.5)
    r1.font.color.rgb = color_titulo
    p2 = c.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r2 = p2.add_run(cuerpo)
    r2.font.size = Pt(10)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return t


def tabla(doc, cabeceras, filas, anchos=None, size=9.5):
    """cabeceras=None -> tabla sin banda de encabezado (fichas, portada)."""
    con_cab = cabeceras is not None
    n_cols = len(cabeceras) if con_cab else len(filas[0])
    t = doc.add_table(rows=1 if con_cab else 0, cols=n_cols)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _bordes_tabla(t)
    if con_cab:
        hdr = t.rows[0].cells
        for i, h in enumerate(cabeceras):
            _sombrear(hdr[i], HEX_CAB)
            hdr[i].text = ""
            p = hdr[i].paragraphs[0]
            r = p.add_run(h)
            r.bold = True
            r.font.size = Pt(size)
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    for f in filas:
        celdas = t.add_row().cells
        for i, v in enumerate(f):
            celdas[i].text = ""
            p = celdas[i].paragraphs[0]
            r = p.add_run(str(v))
            r.font.size = Pt(size)
            if i == 0:
                r.bold = True
    if anchos:
        for i, w in enumerate(anchos):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return t


def salto_pagina(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ── documento ────────────────────────────────────────────────────────────────
def main() -> None:
    doc = Document()

    est = doc.styles["Normal"]
    est.font.name = "Calibri"
    est.font.size = Pt(10.5)

    for s in doc.sections:
        s.top_margin = Cm(2.2)
        s.bottom_margin = Cm(2.0)
        s.left_margin = Cm(2.4)
        s.right_margin = Cm(2.4)

    # ── PORTADA ──────────────────────────────────────────────────────────────
    for _ in range(4):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Aprendizaje por refuerzo profundo\naplicado a la Bolsa de Valores de Lima")
    r.bold = True
    r.font.size = Pt(24)
    r.font.color.rgb = AZUL

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Resumen del trabajo para revisión de especialista")
    r.font.size = Pt(13)
    r.font.color.rgb = GRIS

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Estado: base de datos construida, clasificada y auditada · agente aún no entrenado")
    r.italic = True
    r.font.size = Pt(11)
    r.font.color.rgb = ACENTO

    for _ in range(6):
        doc.add_paragraph()
    tabla(doc,
          None,
          [["Autor", "Rodrigo Holguín"],
           ["Asesor", "Dr. Edwin Villanueva"],
           ["Fecha", "2 de septiembre de 2026"],
           ["Horizonte de datos", "2 de enero de 2012 – 31 de diciembre de 2025"],
           ["Universo", "7 acciones de la BVL"]],
          anchos=[5.0, 9.5], size=10.5)

    salto_pagina(doc)

    # ── CÓMO LEER ────────────────────────────────────────────────────────────
    titulo(doc, "Cómo leer este documento", 1)
    parrafo(doc, "El informe tiene dos mitades con propósitos distintos.")
    tabla(doc,
          ["Parte", "Contenido", "Qué se le pide"],
          [["Secciones 1–7\nLo construido",
            "Qué datos se reunieron, con qué criterios y qué limitaciones tienen.",
            "Detectar supuestos que un practicante del mercado peruano sabría que no se sostienen."],
           ["Secciones 8–9\nLo abierto",
            "Siete decisiones de diseño del agente que aún NO se han tomado: función objetivo, "
            "costos, capacidad, benchmarks y protocolo de evaluación.",
            "Opinar sobre criterio de inversión. Es donde su experiencia vale más."],
           ["Hoja final\nPreguntas",
            "Diez preguntas concretas, ordenadas por impacto.",
            "Responderlas, aunque sea parcialmente."]],
          anchos=[3.3, 6.6, 4.6])

    caja(doc, "Por qué no hay resultados de desempeño todavía",
         "Es deliberado. El protocolo de evaluación se fija ANTES de entrenar, para no "
         "elegir la métrica después de ver los resultados. Esa decisión sigue abierta y es "
         "una de las que se consultan en la sección 8.")

    parrafo(doc, "Se omite todo detalle de implementación. Donde una decisión técnica "
                 "tiene consecuencia económica, se explica la consecuencia, no el mecanismo.",
            cursiva=True, color=GRIS, size=10)

    salto_pagina(doc)

    # ── 1. LA TESIS ──────────────────────────────────────────────────────────
    titulo(doc, "1. La tesis en una página", 1)

    titulo(doc, "La pregunta", 2)
    parrafo(doc, "¿Puede un agente de aprendizaje por refuerzo profundo construir y "
                 "rebalancear un portafolio de acciones de la BVL que supere, fuera de "
                 "muestra y de forma robusta, a estrategias de referencia pasivas y clásicas?")

    titulo(doc, "Qué es un agente de este tipo, en términos de portafolio", 2)
    parrafo(doc, "Es una función que observa un vector de estado del mercado en la fecha t "
                 "y devuelve un vector de pesos del portafolio para t+1. La diferencia con "
                 "una optimización de media-varianza es que los pesos no salen de resolver "
                 "un problema sobre momentos estimados, sino de una política aprendida por "
                 "prueba y error sobre la serie histórica, maximizando una recompensa "
                 "acumulada. No estima retornos esperados ni la matriz de covarianzas de "
                 "forma explícita.")

    titulo(doc, "Por qué la BVL y no un mercado desarrollado", 2)
    parrafo(doc, "Porque es donde la pregunta no está contestada. La literatura de esta "
                 "familia de métodos trabaja casi siempre sobre S&P 500, cripto o futuros: "
                 "mercados profundos, con datos abundantes y costos bajos. La BVL es lo "
                 "contrario — pocos emisores líquidos, sesiones sin negociación, spreads "
                 "amplios y cobertura informativa desigual. La tesis toma esas fricciones "
                 "como objeto de estudio, no como estorbo.")

    caja(doc, "El criterio de éxito, fijado de antemano",
         "El objetivo mínimo defendible NO es «ganar dinero»: es superar de forma robusta y "
         "fuera de muestra a los baselines, con un estudio de ablación limpio que muestre "
         "qué canal de información aporta. Está escrito que si el canal de sentimiento no "
         "supera al baseline, el canal no se usa. Lo mismo para fundamentales y macro.")

    parrafo(doc, "Aporte metodológico, más allá del resultado: buena parte del trabajo "
                 "hecho es la construcción de un panel diario point-in-time para la BVL que "
                 "reúne mercado, fundamentales, prensa y macro sobre 14 años. Ese panel y "
                 "las decisiones documentadas para armarlo son reutilizables con "
                 "independencia de si el agente gana o pierde.")

    salto_pagina(doc)

    # ── 2. UNIVERSO ──────────────────────────────────────────────────────────
    titulo(doc, "2. El universo: siete acciones, y por qué esas", 1)
    tabla(doc,
          ["Ticker", "Emisor", "Sector"],
          [["CREDITC1", "Banco de Crédito del Perú", "Banca"],
           ["ALICORC1", "Alicorp", "Consumo masivo"],
           ["INRETC1", "InRetail Perú", "Retail: supermercados, farmacias, centros comerciales"],
           ["CPACASC1", "Cementos Pacasmayo", "Cemento"],
           ["FERREYC1", "Ferreycorp", "Bienes de capital (Caterpillar)"],
           ["MINSURI1", "Minsur (acción de inversión)", "Minería: estaño, cobre"],
           ["LUSURC1", "Luz del Sur", "Distribución eléctrica"]],
          anchos=[2.6, 5.4, 6.5])

    titulo(doc, "La métrica de liquidez que se usó, y por qué esa", 2)
    parrafo(doc, "En lugar del volumen reportado —que se verificó poco confiable para "
                 "tickers de Lima— se usó el porcentaje de sesiones con precio distinto al "
                 "de la sesión hábil anterior. Un precio que no se movió porque nadie "
                 "transó no es información: es el precio anterior arrastrado.")

    tabla(doc,
          ["Emisor", "% sesiones con precio nuevo", "Situación"],
          [["ALICORC1", "75.9 %", "Sigue"],
           ["FERREYC1", "73.5 %", "Entró en jul-2026"],
           ["CPACASC1", "72.1 %", "Entró en jul-2026"],
           ["MINSURI1", "64.9 %", "Entró en jul-2026"],
           ["CREDITC1", "58.6 %", "Sigue"],
           ["LUSURC1", "56.5 %", "Entró en jul-2026"],
           ["INRETC1", "97.5 %", "Entró en jul-2026 (cotiza en USD)"],
           ["SAGAC1", "4.1 %", "SALIÓ del universo"],
           ["CORAREC1", "20.8 %", "SALIÓ del universo"],
           ["BUENAVC1", "23.7 %", "SALIÓ del universo"]],
          anchos=[3.4, 5.6, 5.5])

    caja(doc, "Límite que se declara",
         "El piso del universo subió de 4.1 % a 56.5 %, pero ninguno de los siete es líquido "
         "en el sentido de un mercado desarrollado: el techo observado para un nombre "
         "BVL-nativo es ~75 %. Uno de cada tres o cuatro días, el precio de cierre de la "
         "mitad de la cartera no refleja una transacción de ese día.")

    titulo(doc, "Dos exclusiones deliberadas que conviene discutir", 2)
    vinneta(doc, "Se evaluó y descartó reemplazar BCP por Credicorp (BAP en NYSE). BAP "
                 "negocia ~1,200 veces lo que CREDITC1 en Lima, pero forma su precio en "
                 "Nueva York: incluirlo rompería la premisa del trabajo. Además son valores "
                 "distintos — Credicorp incluye Pacífico, Prima AFP y Mibanco.")
    vinneta(doc, "Pacasmayo tiene ADR en NYSE, pero está prácticamente muerto: US$ 47 mil "
                 "al día contra ~US$ 235 mil en Lima. El 82 % se transa localmente.")

    salto_pagina(doc)

    # ── 3. FUENTES ───────────────────────────────────────────────────────────
    titulo(doc, "3. Las cuatro fuentes de información", 1)
    parrafo(doc, "El agente observa cuatro bloques. Cada uno se construyó por separado, se "
                 "auditó por separado, y en la evaluación final se prueba por separado.")

    titulo(doc, "3.1 Mercado", 2)
    parrafo(doc, "Fuente primaria: la propia BVL. Yahoo Finance se usó solo como validación "
                 "cruzada, nunca como reemplazo — su volumen para tickers de Lima no "
                 "reconcilia con el oficial.")
    parrafo(doc, "Se construyeron tres series de precio, separadas a propósito:")
    tabla(doc,
          ["Serie", "Para qué se usa"],
          [["Precio crudo", "El efectivamente negociado. Valoriza posiciones y da ratios "
                            "contemporáneos como el P/E."],
           ["Ajustado por splits", "Continuidad de las series técnicas."],
           ["Retorno total", "Reinvirtiendo dividendos. Es el que mide desempeño."]],
          anchos=[4.5, 10.0])
    parrafo(doc, "Dividendos y acciones liberadas provienen del registro oficial de la BVL, "
                 "no de un proveedor externo. Los importes en dólares se convierten a soles "
                 "con el tipo de cambio del BCRP a la fecha de corte. Indicadores incluidos: "
                 "medias móviles de 20 y 50 días, MACD, RSI de 14 días, volatilidad de 20 "
                 "días y retorno diario.")
    caja(doc, "Dos banderas que acompañan cada fila, y que importan para la evaluación",
         "SIN NEGOCIACIÓN: la sesión existe en el calendario pero el papel no operó. "
         "PRECIO ARRASTRADO: el cierre es idéntico al de la sesión anterior — conjunto más "
         "amplio, captura los tramos estancados. Se guardan como señal cruda; qué hace el "
         "agente con ellas es una decisión abierta.")

    salto_pagina(doc)

    titulo(doc, "3.2 Fundamentales", 2)
    parrafo(doc, "Estados financieros trimestrales de la SMV, 2012–2025, para los siete "
                 "emisores. De ahí se derivan ROE, ROA, margen neto, deuda/patrimonio y "
                 "deuda/activos; y con el precio diario, P/E y dividend yield.")

    tabla(doc,
          ["Decisión", "Qué se hizo y por qué"],
          [["P/E",
            "Con utilidad de doce meses móviles, reconstruida desde la serie acumulada del "
            "ejercicio para ser robusta a reexpresiones. No se reporta cuando la utilidad "
            "es negativa: en pérdidas el múltiplo no es informativo."],
           ["Acciones en circulación",
            "Conteo híbrido: acciones emitidas y listadas del registro BVL (que tiene la "
            "fecha correcta) menos tesorería reportada a la SMV (que la BVL no descuenta). "
            "La tesorería llegó a 10 % en un emisor: no netearla habría distorsionado la "
            "capitalización."],
           ["InRetail",
            "Se consume consolidado y no individual, porque es un holding cuyo estado "
            "individual reporta pérdida."]],
          anchos=[4.2, 10.3])

    titulo(doc, "El punto de la fecha de conocimiento — lo más importante de esta sección", 3)
    parrafo(doc, "Un estado financiero del cierre de junio no es información pública el 30 "
                 "de junio. Si el agente lo «ve» en la fecha del período, opera con "
                 "información que el mercado no tenía: sesgo de anticipación, y el backtest "
                 "queda inflado.")
    vinneta(doc, "CUANDO EXISTE, se usa la fecha real de presentación, tomada del hecho de "
                 "importancia que el emisor registra en la BVL. Si el registro es después "
                 "de las 15:00 de Lima, se considera conocida al día siguiente: no era "
                 "operable en el cierre del propio día.")
    vinneta(doc, "CUANDO NO EXISTE, se aplica un rezago estimado. La cobertura de fecha real "
                 "empieza hacia 2018, así que el rezago aplica sobre todo a 2012–2017.")

    tabla(doc,
          ["Tramo del panel", "Observaciones con fecha real"],
          [["2005 – 2017", "0 %"],
           ["2019 – 2024", "~96 %"],
           ["Entrenamiento", "31.9 %"],
           ["Validación", "100 %"],
           ["Prueba", "100 %"]],
          anchos=[6.0, 8.5])

    caja(doc, "Esto no es un faltante aleatorio: es un cambio de régimen alineado con la partición",
         "La variable significa una cosa en entrenamiento y otra en prueba. Es exactamente "
         "el punto que planteó el asesor.", fondo=HEX_PREG, color_titulo=ACENTO)

    titulo(doc, "Qué se hizo con eso", 3)
    parrafo(doc, "El asesor planteó una alternativa razonable: si buena parte de los datos "
                 "tiene la fecha estimada, quizá convenga eliminar la señal ahí en vez de "
                 "darla con un rezago que puede ser ruido y hacer que el agente descarte "
                 "los fundamentales en general. Se midió y se resolvió así:")
    tabla(doc,
          ["Hallazgo", "Consecuencia"],
          [["El rezago mediano es de 10 días",
            "Los fundamentales entran como NIVEL que se arrastra hasta el trimestre "
            "siguiente, no como sorpresa en el anuncio. Un corrimiento de 10 días sobre un "
            "escalón de ~90 deja ~11 % de los días con el valor previo. Diluye, no destruye."],
           ["Eliminar vaciaría el entrenamiento, no la prueba",
            "Pasaría de 231 a 75 observaciones trimestrales. Se entrenaría un agente que "
            "casi no vio fundamentales y se lo evaluaría donde sí están y están bien "
            "fechados. El remedio sería peor."],
           ["Se optó por MARCAR",
            "Cada observación lleva una bandera que indica si la fecha es real o estimada. "
            "El agente puede condicionar, y la propuesta de eliminar queda registrada como "
            "un brazo del estudio de ablación: se decide con evidencia, no a priori."]],
          anchos=[5.0, 9.5])

    caja(doc, "Un hallazgo colateral que sí era un error",
         "El rezago estimado estaba calibrado contra el universo ANTERIOR. InRetail entró "
         "después y presenta sus estados entre 43 y 47 días del cierre, cuando el resto lo "
         "hace hacia los 30. El rezago genérico le ADELANTABA la información entre cinco y "
         "siete días en cada trimestre del tramo estimado — sesgo de anticipación real. Se "
         "corrigió calibrando el rezago por emisor con su propia distribución histórica: el "
         "sesgo pasó de 12.6 % a 1.9 % de los períodos, y lo que queda son las prórrogas de "
         "emergencia por COVID, documentadas.", fondo=HEX_PREG, color_titulo=ACENTO)

    salto_pagina(doc)

    titulo(doc, "3.3 Sentimiento de prensa", 2)
    parrafo(doc, "Es el canal más laborioso y el más incierto. Se explica con algo de "
                 "detalle porque es donde la tesis se juega su componente de inteligencia "
                 "artificial.")
    parrafo(doc, "Se recolectaron 19,528 titulares de prensa peruana (Gestión, El Comercio, "
                 "La República) entre 2012 y 2025, para los siete emisores. Un modelo de "
                 "lenguaje de código abierto, ejecutado localmente, clasifica cada titular "
                 "en una de quince categorías de evento y, solo si la categoría es un hecho "
                 "de la empresa, indica la polaridad esperada sobre el valor de la acción.")

    caja(doc, "La decisión de diseño central",
         "Al modelo se le pide una tarea OBJETIVA (¿de qué tipo es este evento?) y NO una "
         "tarea de juicio (¿qué tan importante es?). La importancia la fija el autor por "
         "adelantado, asignando cada categoría a un tramo de relevancia. Razones: la "
         "clasificación de tipo es auditable en la sustentación y un juicio de importancia "
         "emitido por un modelo no lo es; se midió que la autoevaluación del modelo no "
         "discrimina —su «confianza» es casi igual en aciertos que en errores—; y "
         "recalibrar la relevancia después no obliga a reprocesar el corpus.")

    parrafo(doc, "Las categorías de relevancia cero son el filtro: en vez de un «no sé», "
                 "las categorías que no son hechos de la empresa (mención incidental, "
                 "crónica de bolsa, publicidad, nota sectorial) tienen relevancia cero por "
                 "construcción, y se les fuerza polaridad nula aunque el modelo opine otra "
                 "cosa. Esto eliminó por diseño el error dominante de la primera versión: "
                 "49 % de las etiquetas con signo venían de noticias que no hablaban de la "
                 "empresa.")

    titulo(doc, "Cuánto de ese corpus es realmente información", 3)
    tabla(doc,
          ["Medición", "Resultado"],
          [["Titulares recolectados", "19,528 (2012–2025, siete emisores)"],
           ["Son un hecho concreto del emisor",
            "7.2 % ± 2.8 pp — sobre muestra de 550 titulares anotada a mano por el autor, a ciegas"],
           ["Titulares que nombran a la empresa", "16 % del corpus"],
           ["Relevancia en ese estrato", "63.8 %, contra 2.1 % en el resto"]],
          anchos=[6.0, 8.5])

    titulo(doc, "Resultado de la clasificación completa", 3)
    parrafo(doc, "La corrida sobre los 19,513 titulares terminó el 1 de septiembre de "
                 "2026. El modelo etiqueta 2,237 como hecho de la empresa: 11.5 % del "
                 "corpus. Ese número está por encima del 7.2 % porque el modelo "
                 "sobre-declara relevancia — su precisión en esa tarea se midió en 59.3 %. "
                 "Corrigiendo por ella, las dos vías de estimación convergen.")
    tabla(doc,
          ["Vía de estimación", "Cálculo", "Eventos verdaderos"],
          [["Por el clasificador", "2,237 × 0.593", "1,327"],
           ["Por la anotación humana", "19,513 × 0.072", "1,405"],
           ["Diferencia", "", "6 %"]],
          anchos=[5.2, 4.3, 5.0])
    caja(doc, "Por qué esta coincidencia importa",
         "Dos caminos independientes —uno estadístico sobre una muestra anotada a mano, "
         "otro por conteo directo del clasificador corregido por su precisión— dan el mismo "
         "orden de magnitud. Es la validación más fuerte que tiene el canal hoy.")

    tabla(doc,
          ["Emisor", "Artículos", "Eventos", "Eventos/año", "Días con evento"],
          [["CREDITC1", "10,025", "889", "63.5", "631"],
           ["INRETC1", "3,199", "499", "35.7", "363"],
           ["ALICORC1", "1,719", "258", "18.4", "205"],
           ["LUSURC1", "1,055", "217", "15.5", "184"],
           ["MINSURI1", "920", "154", "11.0", "141"],
           ["FERREYC1", "1,752", "123", "8.8", "116"],
           ["CPACASC1", "843", "97", "6.9", "89"],
           ["TOTAL", "19,513", "2,237", "159.8", "—"]],
          anchos=[2.9, 2.9, 2.6, 3.0, 3.1])
    parrafo(doc, "Reparto de polaridad de esos 2,237 eventos: 46.0 % positivo, 34.9 % "
                 "negativo, 19.2 % neutro. Los neutros son eventos que en el diseño "
                 "anterior no entraban a ninguna columna y se perdían.")
    parrafo(doc, "La búsqueda opera sobre el cuerpo del artículo, así que entra todo el que "
                 "mencione al emisor en cualquier parte: como fuente, como dato, como "
                 "ejemplo. Decisión: se marca ese estrato pero no se descarta, y qué hacer "
                 "con él se decide en la ablación.")

    titulo(doc, "Cómo entra la temporalidad", 3)
    parrafo(doc, "Un evento no vale lo mismo el día que ocurre que tres semanas después, "
                 "pero tampoco desaparece de un día para otro. El tratamiento es:")
    tabla(doc,
          ["Mecanismo", "Por qué"],
          [["Decaimiento exponencial en tres escalas simultáneas: vidas medias de 5, 20 y "
            "60 días hábiles",
            "El agente recibe las tres y aprende cuánto pesa cada una. Una mezcla de "
            "exponenciales representa más formas de decaimiento que una sola —por ejemplo, "
            "caída rápida con cola larga— y los pesos entran de forma lineal, que está "
            "mucho mejor condicionado que estimar una constante de decaimiento libre."],
           ["Positivo, neutro y negativo en canales separados",
            "Una serie con signo colapsa: una buena y una mala el mismo día se cancelan y "
            "dan cero, indistinguible de «no pasó nada». Separadas permiten además reacción "
            "asimétrica, que es un hecho estilizado establecido."],
           ["Las noticias de día no hábil se trasladan al siguiente día de negociación",
            "Nunca al anterior."],
           ["No se re-fecha ninguna noticia",
            "Si un medio publicó tarde, se registra tarde. Mover una noticia al momento "
            "«real» del evento sería introducir información que el lector no tenía."]],
          anchos=[5.2, 9.3])

    caja(doc, "Una limitación reconocida y no resuelta",
         "La clasificación identifica el TIPO de evento pero es muda sobre si el evento es "
         "NUEVO. La prensa cubre el mismo hecho varias veces —anuncio, avance, cierre— y "
         "las tres se clasifican igual. Caso medido: la venta de Luz del Sur en 2019 "
         "aparece en siete titulares entre enero y octubre, todos «fusiones y "
         "adquisiciones», todos con la misma relevancia; pero el precio subió 43 % ANTES "
         "del anuncio oficial, y el titular que confirma la operación llegó diez sesiones "
         "DESPUÉS del salto de 41 % en un día.", fondo=HEX_PREG, color_titulo=ACENTO)

    salto_pagina(doc)

    titulo(doc, "3.4 Factores macroeconómicos", 2)
    parrafo(doc, "Cinco series del BCRP, iguales para los siete activos en cada fecha: "
                 "precio del cobre, tipo de cambio USD/PEN, EMBI+ Perú, tasa de referencia "
                 "e inflación (IPC Lima).")
    caja(doc, "El criterio de inclusión cambió a mitad del trabajo, y es un resultado en sí mismo",
         "Originalmente los factores se eligieron por argumento económico y literatura. "
         "Luego se midió su efecto sobre los siete activos vigentes con una regresión "
         "multifactor con errores estándar de Newey-West, y con los factores rezagados un "
         "día —que es la especificación relevante si se opera al día siguiente.")
    tabla(doc,
          ["Factor", "Decisión", "Evidencia"],
          [["Oro", "ELIMINADO",
            "Estaba justificado por Buenaventura, que salió del universo. Ninguno de los "
            "siete produce oro y no tiene efecto propio en ninguno (0 de 7). Control de que "
            "el método funciona: sobre Buenaventura sale con t = +5.57."],
           ["Estaño", "RECHAZADO",
            "Minsur es el 2º productor mundial, así que la hipótesis era natural. Pero a "
            "Minsur lo mueve el COBRE (t = +5.62). El resultado correcto no es «el estaño no "
            "importa»: es que el BCRP solo lo publica como promedio mensual, y una escalera "
            "de doce peldaños al año no explica retornos diarios."],
           ["Cobre, TC y EMBI", "SE QUEDAN",
            "Hallazgo de fondo: el esqueleto macro de la BVL no son los commodities sino EL "
            "TIPO DE CAMBIO Y EL RIESGO PAÍS. El cobre tiene efecto propio solo en 4 de 7; "
            "en los demás lo absorben el TC y el EMBI. Coherente con el mecanismo conocido: "
            "el cobre mueve al sol y el sol mueve a la bolsa."],
           ["Petróleo", "EN EVALUACIÓN",
            "Aparece en Minsur y Ferreycorp, que son los dos que uno predeciría. Pero 2 de 8 "
            "al 5 % es lo esperable por azar con ~48 pruebas. Se probará como brazo de "
            "ablación, no se da por bueno."]],
          anchos=[2.8, 2.6, 9.1])
    parrafo(doc, "Se descartó un feed de noticias geopolíticas: el canal ya llega por "
                 "precio. Una guerra o una crisis política se refleja en el EMBI, el tipo "
                 "de cambio y el cobre antes de que se pueda clasificar la noticia.")

    salto_pagina(doc)

    # ── 4. PANEL ─────────────────────────────────────────────────────────────
    titulo(doc, "4. El panel: lo que el agente ve", 1)
    tabla(doc,
          ["Dimensión", "Valor"],
          [["Filas", "24,591 (7 emisores × 3,513 sesiones)"],
           ["Estado", "Construido y verificado. Insumo cerrado para el agente."],
           ["Columnas", "118"],
           ["Horizonte", "2 de enero de 2012 – 31 de diciembre de 2025"]],
          anchos=[4.5, 10.0])
    parrafo(doc, "Las columnas se agrupan en conjuntos de señales que se prueban por "
                 "separado. Esa es la estructura del estudio de ablación, que es la forma de "
                 "responder «¿qué canal aporta y cuál no?» en vez de entrenar con todo y no "
                 "saber por qué funciona.")
    tabla(doc,
          ["Conjunto de señales", "Contenido"],
          [["Solo mercado", "Precio, técnicos, banderas de liquidez"],
           ["Mercado + sentimiento", "+ los nueve canales de prensa"],
           ["Mercado + fundamentales", "+ ratios, P/E, DY, bandera de fecha"],
           ["Mercado + macro", "+ las cinco series del BCRP"],
           ["Completa", "Todo"],
           ["Sentimiento por tramo", "Variante: desagregado por magnitud del evento"],
           ["Sentimiento restringido", "Variante: solo titulares que nombran a la empresa"],
           ["Fundamentales con fecha real", "Variante: la propuesta de eliminar en vez de marcar"]],
          anchos=[5.5, 9.0])
    caja(doc, "Por qué importa que las variantes estén pre-registradas",
         "Están definidas ANTES de ver resultados. Eso evita elegir después la "
         "especificación que mejor se ve.")

    # ── 5. CAUSALIDAD ────────────────────────────────────────────────────────
    titulo(doc, "5. Disciplina causal: lo que más puede invalidar el trabajo", 1)
    parrafo(doc, "Un backtest de aprendizaje automático es fácil de inflar sin darse "
                 "cuenta. Las reglas que se fijaron:")
    tabla(doc,
          ["Regla", "Detalle"],
          [["Información en su fecha de conocimiento público",
            "No en la fecha a la que se refiere. Aplica a fundamentales y a prensa."],
           ["Ejecución al día siguiente",
            "Lo que se observa al cierre de t se opera en t+1. Nada se decide y ejecuta el "
            "mismo día."],
           ["Ninguna transformación mira hacia adelante",
            "Las normalizaciones se calculan solo con información hasta la fecha, nunca con "
            "la media de toda la muestra."],
           ["Partición temporal y sin barajar",
            "Entrenamiento, validación y prueba en orden cronológico."]],
          anchos=[5.2, 9.3])
    caja(doc, "Verificación hecha sobre el panel final",
         "Ninguna fila tiene un dato fundamental cuya fecha de conocimiento sea posterior a "
         "la fecha de la fila. Durante la auditoría aparecieron tres casos de «decisión "
         "tomada, código no actualizado» —entre ellos el rezago de InRetail, que era sesgo "
         "de anticipación real—. Están corregidos y registrados como riesgo de proceso, "
         "porque ninguno hacía fallar nada: el pipeline corría y los números salían.")

    salto_pagina(doc)

    # ── 6. DESCARTES ─────────────────────────────────────────────────────────
    titulo(doc, "6. Lo que se midió y se descartó", 1)
    parrafo(doc, "Se incluye porque el criterio de descarte dice más del rigor del trabajo "
                 "que los resultados positivos, y porque son lugares donde usted puede "
                 "decir «midieron lo que no era».")
    tabla(doc,
          ["Propuesta", "Resultado", "Detalle"],
          [["Agregar un eje de «alcance» a la clasificación de noticias", "DESCARTADA",
            "No aumentaba la información del canal y empeoraba la desigualdad de cobertura "
            "entre emisores."],
           ["Deducir la polaridad de una fusión según el papel de la empresa (comprada, "
            "compradora, vendedora)", "DESCARTADA en su forma automática",
            "La REGLA es buena: asignando el papel a mano, el acierto direccional duplica al "
            "del método actual. Pero el modelo no logra identificar el papel — en la compra "
            "de Pacasmayo por Holcim lo clasificó mal en las dos formulaciones probadas. "
            "Queda la opción de asignarlo a mano sobre ~130 artículos."],
           ["Incorporar los Hechos de Importancia de la BVL como segunda fuente",
            "NO ADOPTADA",
            "La hipótesis era que la divulgación obligatoria corregiría la desigualdad de "
            "cobertura. Se anotaron a mano 140 hechos contra un criterio fijado de antemano."]],
          anchos=[4.0, 3.0, 7.5])

    parrafo(doc, "El detalle del tercer caso merece su propia tabla, porque es el más "
                 "interesante para discutir:")
    tabla(doc,
          ["Dimensión", "Resultado"],
          [["Calidad de la fuente",
            "BUENA: 53.4 % de los hechos son materiales, contra 7.2 % de la prensa. Siete "
            "veces más densa en señal."],
           ["Lo que se le pidió",
            "NO LO RESUELVE: la desigualdad entre emisores baja de 16.8 a 6.4 veces, no por "
            "debajo de 6 como se había fijado. Pacasmayo no triplica sus eventos bajo ningún "
            "criterio razonable."],
           ["Legibilidad",
            "El 14 % de los hechos es texto administrativo sin contenido («Acuerdos de "
            "sesión de directorio del 18 de abril»), y eso es ADEMÁS de 2,007 hechos ya "
            "excluidos por venir vacíos."],
           ["Dónde sí son superiores",
            "En la FECHA, que es justo lo que el criterio no midió: son point-in-time por "
            "construcción. Queda anotado como propuesta reducida para después."]],
          anchos=[4.2, 10.3])

    # ── 7. LIMITACIONES ──────────────────────────────────────────────────────
    salto_pagina(doc)
    titulo(doc, "7. Limitaciones sin solución dentro del alcance", 1)
    parrafo(doc, "Van al capítulo de limitaciones tal cual.")
    tabla(doc,
          ["Limitación", "Detalle"],
          [["La cobertura de prensa es muy desigual entre emisores",
            "Medido sobre la clasificación completa: BCP produce 63.5 eventos por año y "
            "Pacasmayo 6.9 — una razón de 9.2 veces. No existe fuente disponible que lo "
            "resuelva: es una propiedad de la prensa peruana, no del método (se probó y "
            "descartó una segunda fuente). Es lo que puede hacer que el canal no pase la "
            "ablación, y por eso el criterio de abandono está fijado de antemano. MATIZ: la "
            "desigualdad medida (9.2x) resultó bastante menor que la estimada antes de "
            "correr (16.8x), y el volumen total casi cuadruplicó el presupuesto previsto. El "
            "canal tiene más masa de la que se temía; lo que sigue sin resolverse es el "
            "reparto."],
           ["El mercado anticipa lo que ninguna fuente pública muestra",
            "Luz del Sur subió 43 % antes del hecho de importancia que anunció su venta. "
            "Ninguna señal construida sobre información pública captura eso."],
           ["Se clasifica sobre titulares, sin el cuerpo del artículo",
            "El proveedor de prensa no entrega el texto completo. La anotación humana de "
            "referencia se hizo con la misma información, así que la tarea es alcanzable, "
            "pero el techo es el titular."],
           ["El volumen negociado no es confiable a nivel diario",
            "Para tickers de Lima. Se usó la frecuencia de negociación oficial de los "
            "informes bursátiles mensuales de la BVL como sustituto para medir capacidad."],
           ["La muestra es chica para aprendizaje profundo",
            "~3,500 días por siete activos. Es el argumento principal para favorecer "
            "arquitecturas simples y regularización fuerte, y para desconfiar de cualquier "
            "resultado que dependa de una sola corrida."]],
          anchos=[4.6, 9.9])

    # ── 8. ABIERTO ───────────────────────────────────────────────────────────
    salto_pagina(doc)
    titulo(doc, "8. Lo que está abierto — donde su opinión vale más", 1)
    parrafo(doc, "Siete decisiones del entorno y el agente no se han tomado. Están "
                 "deliberadamente abiertas porque son juicios de inversión antes que de "
                 "programación.")
    tabla(doc,
          ["#", "Decisión", "Estado y opciones"],
          [["1", "Función objetivo",
            "¿Qué maximiza el agente? Retorno acumulado simple, Sharpe, Sortino, retorno "
            "penalizado por drawdown, o retorno en exceso sobre un benchmark. Cada una "
            "produce un comportamiento distinto y ninguna es obviamente correcta."],
           ["2", "Costos de transacción y slippage",
            "Se observaron spreads de compra-venta entre 8 y 220 puntos básicos de ida y "
            "vuelta según el papel. Cruzar el spread de Luz del Sur una vez cuesta ~110 pbs. "
            "Con esos números la frecuencia de rebalanceo deja de ser un detalle y pasa a "
            "ser la decisión central."],
           ["3", "Capacidad del portafolio",
            "Con la liquidez observada, el tamaño realista está en el orden de S/ 1.8 "
            "millones, y el activo que lo limita es BCP."],
           ["4", "Qué hacer en días sin negociación",
            "¿Se le impide al agente operar ese activo ese día, o se le permite y se le "
            "penaliza el intento?"],
           ["5", "Tasa libre de riesgo y benchmark",
            "Si la recompensa usa Sharpe o exceso de retorno hace falta una tasa libre de "
            "riesgo, y hoy no está en el panel."],
           ["6", "Normalización de las señales",
            "Debe ser causal (solo datos hasta la fecha) y probablemente por activo, dado "
            "que los siete tienen escalas muy distintas. Falta fijar la ventana."],
           ["7", "Protocolo de evaluación",
            "A fijar ANTES de entrenar. Baselines previstos: comprar y mantener, "
            "equiponderado 1/N, momentum y media-varianza. Métricas: retorno acumulado, "
            "Sharpe, Sortino, máximo drawdown, rotación. Múltiples semillas y una medida de "
            "significancia, para no concluir sobre una corrida afortunada."]],
          anchos=[1.0, 3.6, 9.9])

    # ── 9. PREGUNTAS — HOJA APARTE ───────────────────────────────────────────
    salto_pagina(doc)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("PREGUNTAS PARA LA REUNIÓN")
    r.bold = True
    r.font.size = Pt(20)
    r.font.color.rgb = AZUL
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Ordenadas por lo que más cambiaría el trabajo si la respuesta es inesperada")
    r.italic = True
    r.font.size = Pt(11)
    r.font.color.rgb = GRIS
    doc.add_paragraph()

    tabla(doc,
          ["#", "Pregunta", "Por qué importa"],
          [["P1", "Frecuencia de rebalanceo. Con spreads de 8 a 220 pbs, ¿a qué frecuencia "
                  "tiene sentido rebalancear una cartera de siete nombres de la BVL? ¿Diaria "
                  "es directamente inviable? ¿Semanal, mensual?",
            "Puede invalidar el diseño entero del entorno."],
           ["P2", "Función objetivo. ¿Qué optimiza realmente un director de portafolios en "
                  "un mercado como este? ¿Sharpe, drawdown, tracking error? ¿Tiene sentido "
                  "que un agente maximice Sharpe diario?",
            "Define la recompensa del agente: es la decisión más determinante."],
           ["P3", "Benchmark justo. ¿Los cuatro baselines previstos son los que un "
                  "profesional exigiría? ¿Contra qué índice se compara honestamente una "
                  "cartera de siete acciones peruanas?",
            "Sin el benchmark correcto, cualquier resultado es discutible."],
           ["P4", "Restricciones realistas. Se asume solo posiciones largas, sin "
                  "apalancamiento. ¿Es lo correcto para la BVL? ¿Hay límites de "
                  "concentración por emisor que un mandato real impondría?",
            "Cambia el espacio de acción del agente."],
           ["P5", "Sentimiento de prensa. ¿La prensa local anticipa o registra? ¿Vale la "
                  "pena el canal, o el flujo de no residentes y el cobre explican casi todo?",
            "Si solo registra, el canal tiene un techo bajo por construcción."],
           ["P6", "Fundamentales y tiempo. ¿Un rezago mediano de 10 días en un indicador "
                  "trimestral cambia una decisión de portafolio, o es irrelevante en la "
                  "práctica?",
            "Decide si vale la pena el trabajo de fechado point-in-time."],
           ["P7", "Quiebres de régimen. El horizonte 2012–2025 incluye el ciclo de "
                  "commodities, la crisis política 2016–2023, la pandemia y el gobierno de "
                  "Castillo. ¿Hay subperíodos que excluiría o trataría aparte?",
            "Afecta la partición y la interpretación de los resultados."],
           ["P8", "El universo. ¿Siete nombres alcanzan? ¿Agregaría efectivo remunerado o "
                  "renta fija como activo, para que el agente pueda «salirse» del mercado?",
            "Cambia la naturaleza del problema de asignación."],
           ["P9", "Capacidad. ¿S/ 1.8 millones es un tamaño con el que un resultado sería "
                  "creíble, o es tan pequeño que el ejercicio pierde interés práctico?",
            "Determina si el trabajo tiene relevancia aplicada."],
           ["P10", "Lo que no estamos viendo. Con lo descrito acá, ¿qué supuesto le parece "
                   "más frágil?",
            "Es la pregunta más valiosa de la lista."]],
          anchos=[1.0, 8.5, 5.0])

    caja(doc, "Si el tiempo se acorta",
         "Priorizar P1 (frecuencia de rebalanceo), P2 (función objetivo) y P5 (si la prensa "
         "anticipa o registra). Las tres pueden cambiar el diseño, y las tres son cosas que "
         "un practicante sabe y nosotros no podemos medir.", fondo=HEX_PREG,
         color_titulo=ACENTO)

    # ── ANEXO ────────────────────────────────────────────────────────────────
    salto_pagina(doc)
    titulo(doc, "Anexo — Glosario", 1)
    tabla(doc,
          ["Término", "Definición"],
          [["Aprendizaje por refuerzo profundo",
            "Familia de métodos donde un agente aprende una política —una regla que mapea "
            "estado a acción— maximizando una recompensa acumulada, sin que se le den "
            "ejemplos de la acción correcta."],
           ["Ablación",
            "Entrenar el mismo modelo quitando un bloque de información por vez, para "
            "atribuir el desempeño a un canal concreto en vez de al conjunto."],
           ["Point-in-time",
            "Disciplina de reconstruir, para cada fecha, solo la información que era pública "
            "en esa fecha."],
           ["Sesgo de anticipación (look-ahead)",
            "Usar en una decisión histórica información que en ese momento no existía. Infla "
            "el backtest y lo invalida."],
           ["Vida media",
            "En un decaimiento exponencial, número de días tras el cual el peso de un evento "
            "pasado se reduce a la mitad."],
           ["Fuera de muestra",
            "Evaluado sobre datos que no se usaron para ajustar el modelo."],
           ["Partición walk-forward",
            "División temporal en entrenamiento, validación y prueba, respetando el orden "
            "cronológico y sin barajar."]],
          anchos=[4.2, 10.3])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    print(f"Generado: {OUT}")
    print(f"Tamaño: {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
