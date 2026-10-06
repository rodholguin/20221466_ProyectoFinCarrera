const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
  AlignmentType, HeadingLevel, WidthType, ShadingType, BorderStyle, LevelFormat,
  Header, Footer, PageNumber, PageBreak, TabStopType, VerticalAlign,
} = require("docx");

const FIG = path.join(__dirname, "fig");
const OUT = process.argv[2] || path.join(__dirname, "informe.docx");

// ---------------------------------------------------------------- estilo
const FONT = "Calibri";
const AZUL = "1F3A5F";
const AZUL_CLARO = "E8EEF6";
const GRIS_TXT = "52514E";
const GRIS_BORDE = "C9C8C3";
const ANCHO = 9026; // A4 con márgenes de 1"

// **negrita** dentro del texto
function runs(texto, extra = {}) {
  const partes = texto.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return partes.map((p) =>
    p.startsWith("**")
      ? new TextRun({ text: p.slice(2, -2), bold: true, ...extra })
      : new TextRun({ text: p, ...extra })
  );
}
const P = (t, o = {}) => new Paragraph({ children: runs(t, o.run), spacing: { after: 120, line: 276 }, ...o.par });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const B = (t, nivel = 0) => new Paragraph({ numbering: { reference: "vinetas", level: nivel }, children: runs(t), spacing: { after: 80, line: 276 } });
let nListas = 0;
function N(items) {
  const ref = `num${nListas++}`;
  numeraciones.push({
    reference: ref,
    levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 360, hanging: 360 } } } }],
  });
  return items.map((t) => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(t), spacing: { after: 100, line: 276 } }));
}
const numeraciones = [];
const salto = () => new Paragraph({ children: [new PageBreak()] });

const borde = { style: BorderStyle.SINGLE, size: 4, color: GRIS_BORDE };
const bordes = { top: borde, bottom: borde, left: borde, right: borde };

function celda(texto, ancho, o = {}) {
  const parrafos = (Array.isArray(texto) ? texto : [texto]).map(
    (t) => new Paragraph({
      alignment: o.align || AlignmentType.LEFT,
      spacing: { after: 40, line: 252 },
      children: runs(String(t), { size: o.size || 19, bold: o.bold, color: o.color }),
    })
  );
  return new TableCell({
    borders: bordes,
    width: { size: ancho, type: WidthType.DXA },
    shading: o.fill ? { fill: o.fill, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    verticalAlign: VerticalAlign.CENTER,
    children: parrafos,
  });
}

// tabla: cabecera + filas; num = índices de columnas numéricas (alineadas a la derecha)
function tabla(cab, filas, anchos, o = {}) {
  const total = anchos.reduce((a, b) => a + b, 0);
  const num = new Set(o.num || []);
  const resaltar = new Set(o.resaltar || []);
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: anchos,
    rows: [
      new TableRow({
        tableHeader: true,
        children: cab.map((c, i) => celda(c, anchos[i], { bold: true, fill: AZUL, color: "FFFFFF", align: num.has(i) ? AlignmentType.RIGHT : AlignmentType.LEFT })),
      }),
      ...filas.map((f, r) => new TableRow({
        cantSplit: true,
        children: f.map((c, i) => celda(c, anchos[i], {
          align: num.has(i) ? AlignmentType.RIGHT : AlignmentType.LEFT,
          fill: resaltar.has(r) ? "FFF4DC" : (r % 2 ? "F7F7F5" : undefined),
          bold: i === 0 && o.primeraNegrita,
        })),
      })),
    ],
  });
}

// recuadro de mensaje clave
function recuadro(titulo, lineas, color = AZUL) {
  const hijos = [];
  if (titulo) hijos.push(new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text: titulo, bold: true, color, size: 21 })] }));
  for (const l of lineas) hijos.push(new Paragraph({ spacing: { after: 60, line: 264 }, children: runs(l, { size: 20 }) }));
  return new Table({
    width: { size: ANCHO, type: WidthType.DXA },
    columnWidths: [ANCHO],
    rows: [new TableRow({ cantSplit: true, children: [new TableCell({
      width: { size: ANCHO, type: WidthType.DXA },
      shading: { fill: AZUL_CLARO, type: ShadingType.CLEAR, color: "auto" },
      borders: { top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
        right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, left: { style: BorderStyle.SINGLE, size: 24, color } },
      margins: { top: 120, bottom: 120, left: 200, right: 200 },
      children: hijos,
    })] })],
  });
}
const esp = (n = 120) => new Paragraph({ spacing: { after: n }, children: [] });

function figura(archivo, titulo, fuente) {
  const buf = fs.readFileSync(path.join(FIG, archivo));
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  const ancho = 600;
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 },
      children: [new ImageRun({ type: "png", data: buf, transformation: { width: ancho, height: Math.round(ancho * h / w) },
        altText: { title: titulo, description: titulo, name: archivo } })] }),
    new Paragraph({ spacing: { after: 60 }, children: runs(titulo, { size: 19, bold: false, color: AZUL }) }),
    ...(fuente ? [new Paragraph({ spacing: { after: 200 }, children: runs(fuente, { size: 17, italics: true, color: GRIS_TXT }) })] : []),
  ];
}
const nota = (t) => new Paragraph({ spacing: { before: 60, after: 200 }, children: runs(t, { size: 17, italics: true, color: GRIS_TXT }) });

// ================================================================ contenido
const c = [];

// ---------------------------------------------------------------- portada
c.push(
  new Paragraph({ spacing: { before: 1800, after: 120 }, alignment: AlignmentType.LEFT,
    children: [new TextRun({ text: "PONTIFICIA UNIVERSIDAD CATÓLICA DEL PERÚ", bold: true, color: GRIS_TXT, size: 22 })] }),
  new Paragraph({ spacing: { after: 800 }, children: [new TextRun({ text: "Facultad de Ciencias e Ingeniería · Ingeniería Informática", color: GRIS_TXT, size: 20 })] }),
  new Paragraph({ spacing: { after: 240 }, children: [new TextRun({ text: "Informe de avance de tesis", bold: true, color: AZUL, size: 52 })] }),
  new Paragraph({ spacing: { after: 600, line: 300 }, children: [new TextRun({ text: "Desarrollo de agentes de inversión bursátiles mediante aprendizaje por refuerzo y LLM con integración de información de mercado, estados financieros y de noticias en la Bolsa de Valores de Lima", color: "222222", size: 28 })] }),
  new Paragraph({ border: { top: { style: BorderStyle.SINGLE, size: 8, color: AZUL, space: 12 } }, spacing: { after: 80 },
    children: [new TextRun({ text: "Objetivos específicos 1, 2 y 3 — estado, decisiones y hallazgos", bold: true, size: 22 })] }),
  new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "Autor: Rodrigo Alejandro Holguin Huari", size: 21 })] }),
  new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "Asesor: Dr. Edwin Rafael Villanueva Talavera", size: 21 })] }),
  new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "Lima, 21 de septiembre de 2026", size: 21 })] }),
  salto(),
);

// ---------------------------------------------------------------- resumen ejecutivo
c.push(H1("Resumen ejecutivo"));
c.push(P("La tesis busca **generar evidencia sobre si un agente de inteligencia artificial puede gestionar un portafolio de acciones de la Bolsa de Valores de Lima (BVL) mejor que las reglas clásicas de inversión**, cuando se le cobra lo que de verdad cuesta operar en un mercado pequeño y poco líquido. El agente aprende por prueba y error (aprendizaje por refuerzo) y observa cuatro tipos de información: precios, estados financieros, noticias procesadas con un modelo de lenguaje y variables macroeconómicas."));
c.push(P("El trabajo se organiza en tres objetivos específicos (OE). Su estado al 21 de septiembre es el siguiente:"));
c.push(tabla(
  ["Objetivo", "Qué entrega", "Estado"],
  [
    ["**OE1** · Entorno de simulación de la BVL", "R1 Informe CRISP-DM · R2 Simulador que cobra costos reales, respeta los días sin negociación y remunera la caja", "**Cerrado**"],
    ["**OE2** · Dataset unificado", "R3 Mercado · R4 Fundamentales · R5 Sentimiento de noticias · R6 Integración en un solo panel diario", "**Cerrado** (ajustes finos con Bloomberg)"],
    ["**OE3** · Agentes y estudio comparativo", "R7 Agentes entrenados · R8 Comparación contra estrategias de referencia bajo cuatro configuraciones de señales", "**En curso**: PPO entrenado y evaluado; SAC y DDPG en implementación y pruebas"],
  ],
  [2500, 4526, 2000],
));
c.push(esp());
c.push(recuadro("Cinco mensajes para llevarse", [
  "**1. Los datos están listos y verificados.** Un panel diario de 7 empresas (2012–2025) con 120 variables, construido sin usar información del futuro y contrastado contra Bloomberg: las 7 series de precios coinciden (correlación de 0.89 a 0.99).",
  "**2. En la BVL, el costo de operar manda.** Una cartera repartida en partes iguales y rebalanceada a diario pierde 24 puntos de rentabilidad en comisiones y spreads; el optimizador clásico de Markowitz paga el equivalente al 65% del capital inicial en 13 años.",
  "**3. La vara real es el banco.** Entre 2013 y 2025, dejar el dinero en caja a la tasa del BCRP rindió 40.5%, más que cualquier estrategia con acciones (la mejor: 31.0%), y sin caídas.",
  "**4. El agente aprende a proteger el capital, todavía no a ganar más.** Su peor caída es la menor entre las estrategias con acciones (−4.2% contra −10.2% del reparto igualitario), pero aún no supera al reparto igualitario en años alcistas ni a la caja de forma consistente. **El canal de noticias es el más prometedor** —llega a +9.7% en el tramo más favorable— y a la vez el más volátil.",
  "**5. Se probaron tres vías de mejora y ninguna funcionó** (entrenar más, cambiar la recompensa, darle más información). La lectura que se desprende: en este mercado hay poca señal aprovechable y el costo de operar se la come. Es un resultado de la tesis, no un defecto del método.",
]));
c.push(esp());
c.push(P("**Una advertencia que acompaña a todas las cifras del agente:** son resultados de la etapa de desarrollo, medidos sobre el tramo de **validación** con 3 repeticiones por configuración. El tramo de **prueba**, que dará el resultado final, **no se ha usado nunca**; se reserva para una sola corrida definitiva con reglas fijadas de antemano. Eso es lo que permite que el resultado final sea creíble.", { run: {} }));
c.push(salto());

// ---------------------------------------------------------------- 1. contexto
c.push(H1("1. El problema y la forma de abordarlo"));
c.push(P("La BVL es un mercado pequeño: pocas empresas negocian todos los días, los spreads (la diferencia entre el precio al que se compra y al que se vende) son amplios y la comisión mínima por orden es alta. La mayoría de estudios de inteligencia artificial para inversión se hacen en mercados grandes y líquidos, donde operar es casi gratis. **La pregunta de la tesis es si un agente aprende algo útil cuando operar sí cuesta.**"));
c.push(P("Los tres objetivos encajan como una cadena: los datos (OE2) alimentan un simulador del mercado (OE1), dentro del cual se entrena y evalúa al agente (OE3)."));
c.push(tabla(
  ["OE2 · Datos", "OE1 · Simulador", "OE3 · Agente y evaluación"],
  [[
    ["Precios, estados financieros, noticias y macro", "→ un panel diario, sin información del futuro"],
    ["Reproduce un día de bolsa: el agente observa, decide pesos, paga costos y gana (o pierde) el retorno del día siguiente"],
    ["El agente aprende dentro del simulador y se compara contra estrategias clásicas bajo las mismas reglas"],
  ]],
  [3008, 3009, 3009],
));
c.push(esp());
c.push(H2("1.1 El universo: siete empresas elegidas por liquidez"));
c.push(P("El proyecto original incluía a Saga Falabella, Aceros Arequipa y Buenaventura. Se reemplazaron porque casi no negocian en Lima (Saga lo hace en 9% de las sesiones). El universo final cubre siete sectores:"));
c.push(tabla(
  ["Empresa", "Nemónico", "Sector", "Sesiones con negociación", "Costo de ida y vuelta"],
  [
    ["Alicorp", "ALICORC1", "Consumo masivo", "100.0%", "1.11%"],
    ["Ferreycorp", "FERREYC1", "Bienes de capital", "100.0%", "1.73%"],
    ["Cementos Pacasmayo", "CPACASC1", "Construcción", "95.5%", "1.66%"],
    ["InRetail", "INRETC1", "Retail", "95.2%", "1.16%"],
    ["Minsur", "MINSURI1", "Minería", "95.0%", "1.17%"],
    ["Credicorp / BCP", "CREDITC1", "Banca", "90.5%", "2.68%"],
    ["Luz del Sur", "LUSURC1", "Electricidad", "90.5%", "3.23%"],
  ],
  [2100, 1400, 1826, 1900, 1800], { num: [3, 4] },
));
c.push(nota("Sesiones con negociación: Informe Bursátil Mensual de la BVL, 2012–2026. Costo de ida y vuelta: comprar y luego vender una orden de S/250 mil (comisión, derechos y spread). Solo en el 10% de los días los siete activos tienen precio propio el mismo día."));
c.push(salto());

// ---------------------------------------------------------------- 2. conceptos
c.push(H1("2. Conceptos para leer este informe"));
c.push(P("Esta sección reúne, en lenguaje llano, los conceptos que aparecen en el resto del documento. Cada uno lleva una línea sobre por qué importa en esta tesis."));
c.push(H2("2.1 Conceptos financieros"));
c.push(tabla(
  ["Concepto", "Qué es y por qué importa aquí"],
  [
    ["Portafolio y pesos", "Cómo se reparte el dinero entre activos. Aquí: 7 acciones más caja, sin endeudamiento ni ventas en corto. El agente decide los pesos cada día."],
    ["Retorno", "Cuánto creció el dinero en un periodo. **Retorno anualizado**: el mismo crecimiento expresado como tasa por año, para comparar periodos de distinto largo."],
    ["Volatilidad", "Cuánto oscila el retorno de un día a otro. Es la medida más usada de riesgo."],
    ["Ratio de Sharpe", "Retorno obtenido **por encima de la tasa libre de riesgo**, dividido entre la volatilidad. Responde a “¿cuánto gano por cada unidad de riesgo que asumo?”. Por encima de 1 es muy bueno; cerca de 0, no compensa el riesgo."],
    ["Ratio de Sortino", "Como el Sharpe, pero solo penaliza las oscilaciones hacia abajo, que son las que preocupan al inversionista."],
    ["Máxima caída (drawdown)", "La mayor pérdida desde un máximo hasta el mínimo siguiente. Un −45% significa que en algún momento la cartera perdió casi la mitad de su valor. Es la métrica que mejor refleja el “susto” del inversionista."],
    ["Rotación", "Cuántas veces al año se da vuelta la cartera completa. Cada vuelta paga costos, así que más rotación significa más peaje."],
    ["Costo de transacción", "Lo que cuesta cada operación: comisión de la sociedad agente de bolsa (0.43%, mínimo S/40), derechos de BVL, Cavali y SMV, y la mitad del spread."],
    ["Spread (bid-ask)", "Diferencia entre el mejor precio de compra y el mejor de venta. En la BVL va de 0.08% (Alicorp) a 2.2% (Luz del Sur): un orden de magnitud entre activos."],
    ["Liquidez", "Facilidad para comprar o vender sin mover el precio. En la BVL es la restricción central: muchos días una acción no negocia y su precio es el del día anterior."],
    ["Tasa libre de riesgo · caja", "Lo que rinde el dinero sin invertir en acciones. Aquí la caja gana la tasa de referencia del BCRP, para que “no invertir” sea una opción real para el agente."],
    ["Puntos básicos (pbs)", "Centésima de punto porcentual: 100 pbs = 1%."],
  ],
  [2300, 6726], { primeraNegrita: true },
));
c.push(esp());
c.push(H3("Estrategias de referencia (baselines)"));
c.push(P("Son las reglas contra las que se mide al agente. Si el agente no les gana, no aporta."));
c.push(tabla(
  ["Estrategia", "Qué hace"],
  [
    ["1/N (reparto igualitario)", "Pone la misma proporción en cada activo y rebalancea con una frecuencia fija (diaria, semanal, mensual o trimestral). La literatura lo considera “casi invencible” cuando operar es gratis."],
    ["Comprar y mantener", "Compra una vez al inicio y no vuelve a operar."],
    ["Markowitz", "El optimizador clásico de media-varianza: con los retornos y riesgos estimados del último año, busca la mezcla con mejor relación retorno/riesgo. Se usan tres variantes: tangencia, tangencia con estimación de riesgo robusta (Ledoit-Wolf) y mínima varianza."],
    ["Solo caja", "Todo el dinero en caja remunerada a la tasa del BCRP."],
    ["Banda nula", "200 carteras al azar con las mismas reglas. Dice cuánto se consigue por pura suerte: si el agente cae dentro de esa banda, no hay hallazgo."],
  ],
  [2300, 6726], { primeraNegrita: true },
));
c.push(esp());
c.push(H2("2.2 Conceptos de inteligencia artificial"));
c.push(tabla(
  ["Concepto", "Qué es y por qué importa aquí"],
  [
    ["Aprendizaje por refuerzo", "Un **agente** aprende a tomar decisiones interactuando con un **entorno**. En cada paso observa un **estado**, elige una **acción** y recibe una **recompensa**. Nadie le dice qué hacer: repite millones de veces y ajusta su conducta hacia lo que más recompensa le dio. Aquí: el estado son los datos del día, la acción son los pesos de la cartera y la recompensa mide la rentabilidad ajustada por riesgo."],
    ["Aprendizaje profundo (deep)", "La conducta del agente está en una red neuronal, que traduce lo que observa en una decisión. Aquí se usa deliberadamente una red pequeña (64×64 neuronas), porque 13 años de historia son pocos datos para una red grande."],
    ["PPO, SAC y DDPG", "Tres algoritmos para entrenar agentes que eligen acciones continuas (como pesos entre 0 y 1). **PPO** es estable y es el algoritmo principal. **SAC** y **DDPG** aprenden reutilizando experiencias pasadas y sirven como contraste."],
    ["Recompensa: Sharpe diferencial", "Una versión del ratio de Sharpe que se puede calcular día a día, de modo que el agente recibe señal en cada paso y no solo al final del periodo."],
    ["Exploración", "Durante el entrenamiento el agente prueba acciones con algo de azar para descubrir qué funciona. Si ese azar es excesivo, en bolsa se traduce en operar de más y pagar costos que no aportan nada."],
    ["Semilla", "El número que fija el azar de una corrida. La misma configuración con semillas distintas da agentes distintos; por eso se entrenan varias y se reporta la **mediana**, nunca la mejor."],
    ["Pasos de entrenamiento", "Cuántas decisiones toma el agente mientras aprende. Cada paso es un día simulado; 150 mil pasos equivalen a recorrer la historia muchas veces."],
    ["Sobreajuste", "Cuando el agente aprende patrones del pasado que no se repiten. Se detecta porque mejora en los datos de entrenamiento y empeora en datos nuevos."],
    ["Modelo de lenguaje (LLM)", "Un modelo de IA que entiende texto. Aquí se usa uno local (gemma3 de 12 mil millones de parámetros) para leer titulares y clasificar de qué tipo de evento se trata y si es bueno o malo para la empresa."],
  ],
  [2300, 6726], { primeraNegrita: true },
));
c.push(esp());
c.push(H2("2.3 Conceptos de método: cómo evitar engañarse"));
c.push(tabla(
  ["Concepto", "Qué es y por qué importa aquí"],
  [
    ["Sesgo de anticipación (look-ahead)", "Usar sin querer información que en la fecha de la decisión aún no se conocía (por ejemplo, un estado financiero antes de que se publique). Es el error más común en estudios de inversión y vuelve irreal cualquier resultado. Todo el panel está construido **point-in-time**: cada dato entra el día en que se hizo público."],
    ["Entrenamiento, validación y prueba", "Se parte la historia en tres tramos. Con el de **entrenamiento** el agente aprende; con el de **validación** se diagnostican y ajustan decisiones de diseño; el de **prueba** se usa una sola vez, al final, para dar el resultado."],
    ["Walk-forward y pliegues", "En lugar de un único corte, la historia se recorre hacia adelante en varios **pliegues**. Cada uno entrena con todo lo anterior y valida y prueba en el tramo siguiente, como se haría en la práctica. Aquí hay 3 pliegues, y cada uno cae en un contexto de mercado distinto (ver sección 5)."],
    ["Embargo", "Un hueco de 20 días entre tramos para que las medias móviles del final del entrenamiento no “vean” el inicio de la validación."],
    ["Estudio de ablación", "Se agrega un tipo de información por vez (macro, noticias, fundamentales) y se mide cuánto cambia el resultado. Así se atribuye el aporte de cada fuente."],
    ["Contador de configuraciones y Sharpe deflactado", "Si se prueban muchas variantes, alguna sale bien por suerte. El **Sharpe deflactado** descuenta ese efecto según cuántas se probaron. Por eso se registra cada corrida desde la primera, sin borrar ninguna: hasta hoy, 134 corridas y ninguna sobre el tramo de prueba."],
    ["Pre-registro", "Escribir la regla de decisión y la predicción **antes** de mirar el resultado. Evita elegir, después de ver los números, la lectura que más conviene."],
  ],
  [2300, 6726], { primeraNegrita: true },
));
c.push(salto());

// ---------------------------------------------------------------- 3. OE1
c.push(H1("3. OE1 — El entorno de simulación de la BVL"));
c.push(recuadro(null, ["**Estado: cerrado.** R1 (informe CRISP-DM) y R2 (entorno implementado y probado). El simulador está programado con la interfaz estándar Gymnasium y verificado con **85 pruebas automáticas**."]));
c.push(esp());
c.push(H2("3.1 Qué hace el simulador"));
c.push(P("Reproduce, día por día, la vida de una cartera de S/1.8 millones invertida en las siete acciones más caja. En cada día el agente recibe los datos disponibles, decide cómo reajustar la cartera, paga los costos de ese reajuste y obtiene el retorno del día siguiente."));
c.push(P("**La regla del reloj** es lo que garantiza el realismo: la decisión se toma con información hasta el cierre del día anterior y se ejecuta al cierre de hoy. Por construcción, ninguna decisión puede usar información de su propio día de ejecución."));
c.push(H2("3.2 Cuatro reglas que lo hacen económicamente honesto"));
c.push(tabla(
  ["Regla", "Qué hace", "Por qué"],
  [
    ["Costo por activo", "Cada acción paga su propio costo: comisión, derechos y la mitad de su spread", "Un costo único escondería que Luz del Sur cuesta tres veces más que Alicorp"],
    ["No se opera sin mercado", "Si una acción no negoció ese día, conserva su peso y el agente solo puede mover el resto", "Recomendación del especialista de mercado consultado: “si nadie quiere jugar, no se juega”"],
    ["La caja rinde", "El dinero no invertido gana la tasa de referencia del BCRP", "Si la caja rindiera cero, el entorno castigaría al agente por protegerse"],
    ["La acción es un ajuste", "El agente mueve los pesos actuales en lugar de proponer una cartera nueva cada día", "Así “no operar” es una opción natural y barata. Sin esto el agente rotaba 9 veces al año; con esto, 2"],
  ],
  [1900, 3700, 3426], { primeraNegrita: true },
));
c.push(esp());
c.push(H2("3.3 El costo es el término dominante"));
c.push(P("El costo por operación se calcula como la comisión de la sociedad agente de bolsa (0.43% con mínimo de S/40, más IGV), los derechos de BVL, Cavali y SMV (0.0076%) y la mitad del spread del activo. La comisión mínima de S/40 hace que las órdenes chicas sean carísimas: debajo de unos S/9,300 el costo fijo domina. De ahí se **deriva** una banda de no-operación, sin elegirla a mano."));
c.push(P("Por liquidez, la cartera que el mercado puede absorber sin mover precios es de unos **S/1.8 millones**, acotada por el BCP, que es el activo con menos dinero negociado por día. La tesis se plantea, por tanto, a escala de inversionista individual o family office, no institucional."));
c.push(H2("3.4 Las estrategias de referencia, dentro del mismo simulador"));
c.push(P("Una decisión de diseño importante: **las estrategias de referencia corren en el mismo simulador que el agente**, con los mismos costos y reglas. Si el simulador tuviera un sesgo, lo tendrían ambos lados, y la comparación es justa por construcción. Además, cada estrategia usa su mejor frecuencia de rebalanceo, para no ganarle a un rival mal implementado."));
c.push(...figura("f1_baselines.png",
  "Figura 1. Estrategias de referencia en todo el horizonte (2 de enero de 2013 a 30 de diciembre de 2025), con cartera inicial de S/1.8 millones y costos reales.",
  "En gris, la misma estrategia 1/N diaria sin cobrarle costos, como referencia. En verde, la caja remunerada."));
c.push(P("**Cuatro lecturas de la Figura 1:**"));
c.push(...N([
  "**El costo se come 24 puntos.** El 1/N diario pasa de 32.8% sin costos a 8.5% con costos: S/355 mil de peaje sobre S/1.8 millones.",
  "**Hay una frecuencia óptima intermedia.** Rebalancear trimestralmente (21.0%) rinde más que hacerlo a diario (8.5%), pero no hacer nada (comprar y mantener, 0.7%) es peor. Sí existe un beneficio en rebalancear, y el costo lo destruye si se hace muy seguido.",
  "**Markowitz genera retorno, pero lo regala en costos.** La variante de tangencia paga S/1.18 millones en comisiones (65% del capital inicial) y tiene la peor caída de la tabla (−55%). Es el argumento central de la tesis, medido sobre un método clásico y no sobre el agente.",
  "**La caja le gana a todo:** 40.5% sin caídas. En estos 13 años, este universo de acciones rindió menos que la tasa de referencia. La vara del agente no es solo el 1/N: es “¿le gana a dejar el dinero en el banco?”.",
]));
c.push(P("La Figura 2 muestra el mismo resultado como recorrido en el tiempo. Las carteras de acciones pierden cerca de 40% entre 2013 y comienzos de 2016 y tardan años en recuperarse. Markowitz más que duplica su valor en 2021 y 2022 y luego devuelve buena parte de esa ganancia: es el camino más volátil. La caja crece de forma continua y termina arriba de todas."));
c.push(...figura("g1_evolucion_baselines.png",
  "Figura 2. Evolución del valor de la cartera, 2013–2025 (inicio = 100), con costos reales.",
  null));
c.push(H2("3.5 Por qué creerle al simulador"));
c.push(P("La contabilidad es donde se esconden los errores silenciosos, así que se verificó con pruebas que tienen respuesta conocida de antemano. Por ejemplo, con costo cero “comprar y no tocar” debe replicar **exactamente** la estrategia de comprar y mantener, y una cartera 100% en caja debe crecer **exactamente** a la tasa del BCRP. Las 85 pruebas pasan."));
c.push(P("**Pendientes declarados:** la tarifa de comisión proviene de la web pública de un bróker, no del tarifario negociado para una cuenta de este tamaño. El spread es una foto de julio de 2026 y la serie histórica ya se descargó de Bloomberg, pero falta conectarla al modelo de costos. El recargo de costo previsto para los días en que una acción no tiene precio propio todavía no está activado."));
c.push(salto());

// ---------------------------------------------------------------- 4. OE2
c.push(H1("4. OE2 — El dataset unificado"));
c.push(recuadro(null, ["**Estado: cerrado.** R3 a R6 implementados y verificados. Resultado: un panel de **24,584 filas × 120 columnas** (7 activos, 2 de enero de 2012 a 30 de diciembre de 2025), sin valores faltantes en las columnas que usa el agente y sin ningún dato fechado antes de haberse hecho público."]));
c.push(esp());
c.push(H2("4.1 Las cuatro fuentes de información"));
c.push(tabla(
  ["Canal", "Fuente", "Qué aporta al agente"],
  [
    ["**Mercado** (R3)", "BVL (fuente oficial) y registro de dividendos y acciones liberadas", "Precio de retorno total (incluye dividendos y splits), indicadores técnicos (medias móviles, RSI, volatilidad) y banderas de días sin negociación"],
    ["**Fundamentales** (R4)", "SMV: estados financieros trimestrales, 2005–2025", "ROE, ROA, margen neto, deuda/patrimonio, deuda/activo, P/E y rendimiento por dividendo, y la “sorpresa” de cada resultado frente a lo esperado. Cada dato entra en la fecha real en que se publicó, tomada de los hechos de importancia de la BVL"],
    ["**Sentimiento** (R5)", "~19,500 noticias de prensa peruana (Media Cloud), clasificadas con un modelo de lenguaje local", "2,237 eventos relevantes clasificados en una taxonomía de tipos de evento (resultados, fusiones, regulación, crisis, etc.), con su polaridad, resumidos en 9 series diarias: positivo, neutro y negativo, cada una a 5, 20 y 60 días"],
    ["**Macro**", "BCRP y mercados internacionales", "Tipo de cambio, riesgo país (EMBI), cobre, petróleo, S&P 500, MSCI Emergentes y tasa de referencia"],
  ],
  [1800, 2700, 4526],
));
c.push(esp());
c.push(H2("4.2 Decisiones y hallazgos destacados"));
c.push(H3("La validación externa encontró un error que las internas no veían"));
c.push(P("Al contrastar los precios contra Bloomberg se descubrió que la API de la BVL **etiqueta cada cierre con la fecha del día hábil siguiente**. El panel iba un día atrasado. Todas las validaciones internas pasaban, porque un panel atrasado un día es perfectamente consistente consigo mismo. Se corrigió en la ingesta y se regeneró todo:"));
c.push(tabla(
  ["", "Correlación de retornos con Bloomberg"],
  [["Antes de la corrección", "−0.02 a 0.13 (sin relación)"], ["Después de la corrección", "**0.885 a 0.986 · los 7 activos pasan el umbral fijado de 0.85**"]],
  [3000, 6026], { primeraNegrita: true },
));
c.push(P("Una prueba de evento lo confirma: la caída tras la segunda vuelta electoral de 2021 (Alicorp −15.1%, BCP −9.8%, Ferreycorp −15.3%) cae ahora en el lunes 7 de junio, la fecha correcta. **Lección metodológica:** toda serie que venga de una fuente sin documentación de sus fechas se contrasta contra una segunda fuente independiente."));
c.push(H3("Elegir el modelo de lenguaje con anotación humana, no por intuición"));
c.push(P("Se compararon cinco modelos de lenguaje locales (de 4 mil a 32 mil millones de parámetros) y se eligió con **550 titulares anotados por el autor**. Tres resultados:"));
c.push(B("**El ranking cambió al usar la anotación humana.** El modelo que lideraba contra una referencia automática cayó al tercer lugar. Evaluar un modelo contra otro modelo favorece a los que “piensan” igual."));
c.push(B("**Más grande no fue mejor.** El modelo de 27 mil millones de parámetros rindió peor que el de 12 mil millones. El elegido, gemma3:12b, alcanza una precisión de 75% y una exhaustividad de 92% para detectar noticias relevantes."));
c.push(B("**La señal tiene contenido económico.** Las noticias que el modelo marca como relevantes coinciden con movimientos grandes de precio el 34.8% de las veces, frente a 18.4% de base (p = 0.006). Las irrelevantes no se distinguen del azar."));
c.push(H3("Las variables macro se midieron antes de incluirlas"));
c.push(P("Cada factor macro entra solo si mueve de forma medible a las empresas del universo. El tipo de cambio es significativo en 7 de 7 y el riesgo país en 6 de 7. **El oro se eliminó** (0 de 7) porque su justificación era Buenaventura, que salió del universo. El estaño no se incluyó pese a que Minsur es un gran productor: a Minsur lo mueve el cobre."));
c.push(H3("La iliquidez se ve como precio repetido, no como ausencia de mercado"));
c.push(P("Solo el 0.8% de los datos son días sin mercado posible, pero entre 24% y 44% de los días (según el activo) el precio es el mismo del día anterior porque no hubo operaciones que lo movieran. Eso hace que el riesgo estimado con estos precios **parezca menor** de lo que es, y justamente en los activos más caros de operar. Se declara como sesgo que afecta a cualquier método, el agente incluido."));
c.push(H2("4.3 Ajustes en curso con Bloomberg"));
c.push(B("Ya se descargaron: fechas de anuncio de resultados (428 eventos 2011–2026), serie histórica de spreads, volumen y precios. Falta conectar los spreads al modelo de costos."));
c.push(B("El free float del BCP que cita el documento de tesis (2.66%) es de 2011; hoy es 2.26%. Luz del Sur cayó de 26% a 2.9% tras la OPA de 2019–2020."));
c.push(B("Pendiente menor: el ratio precio/valor contable (P/B)."));
c.push(salto());

// ---------------------------------------------------------------- 5. OE3
c.push(H1("5. OE3 — Agentes y estudio comparativo"));
c.push(recuadro(null, ["**Estado: en curso.** El agente **PPO** está entrenado y evaluado en la etapa piloto, y ya existen los entregables de R7 (curvas de entrenamiento y modelos guardados) y de R8 (las cuatro configuraciones de señales que pide el documento). **SAC y DDPG están en implementación y pruebas.** Falta la corrida definitiva: 10 semillas, 3 pliegues y el tramo de prueba."]));
c.push(esp());
c.push(H2("5.1 Configuración del piloto"));
c.push(tabla(
  ["Elemento", "Valor"],
  [
    ["Algoritmo", "PPO (SAC y DDPG en pruebas)"],
    ["Red neuronal", "Pequeña, 64×64 neuronas: son solo ~3,300 días de una única historia"],
    ["Qué decide", "Pesos de 7 acciones más caja, como ajuste sobre la cartera actual (hasta 5 puntos por día)"],
    ["Recompensa", "Sharpe diferencial: rentabilidad ajustada por riesgo, día a día"],
    ["Repeticiones", "3 semillas por configuración (10 en la corrida final); se reporta la mediana"],
    ["Evaluación", "Tramo de validación de cada pliegue. El tramo de prueba no se ha tocado"],
    ["Registro", "134 corridas registradas, todas PPO, 0 sobre el tramo de prueba"],
  ],
  [2300, 6726], { primeraNegrita: true },
));
c.push(esp());
c.push(H3("Los tres pliegues caen en mercados muy distintos"));
c.push(tabla(
  ["Pliegue", "Entrena con", "Valida en", "Contexto del tramo de validación", "1/N diario en validación"],
  [
    ["0", "2013 – oct-2018", "nov-2018 – nov-2019", "El tramo más favorable de los seis que produce la partición", "+11.9%"],
    ["1", "2013 – oct-2020", "nov-2020 – nov-2021", "Pandemia y elecciones: volatilidad casi el doble de lo habitual", "−8.7%"],
    ["2", "2013 – oct-2022", "nov-2022 – nov-2023", "Año de caída", "−7.5%"],
  ],
  [900, 1700, 1900, 3026, 1500], { num: [4] },
));
c.push(P("Esto es importante para leer los resultados: **un solo pliegue mide el contexto de mercado, no al agente.** Por eso se reportan los tres."));
c.push(nota("La caracterización de cada tramo está medida sobre el propio universo de 7 activos (índice equiponderado, bruto): pliegue 0 +14.2% con volatilidad de 11.1%; pliegue 1 −5.8% con volatilidad de 26.5% y una caída de −41.9%, el tramo más extremo del periodo; pliegue 2 −5.4% con volatilidad de 9.4%. El tramo del pliegue 0 está en el percentil 81 de todas las ventanas de 252 días entre 2013 y 2025, no es el máximo: la mejor ventana del periodo rinde +69.9% y termina en febrero de 2017."));
c.push(H2("5.2 Dos problemas de diseño que se encontraron y se resolvieron"));
c.push(B("**El azar de exploración hacía operar de más.** Con los parámetros estándar de la librería, un agente sin entrenar rotaba la cartera 206 veces al año solo por el azar de exploración. El agente pagaba un peaje enorme que no venía de sus decisiones y no podía aprender a evitarlo. Se calibró la exploración mirando **cuánto opera** el agente, nunca cuánto gana, para no ajustar el diseño al resultado."));
c.push(B("**“No operar” era casi imposible.** Si el agente propone una cartera nueva cada día, quedarse quieto exige repetir exactamente la decisión anterior. Al cambiar la acción a un **ajuste** sobre los pesos actuales, la rotación bajó de 9.2 a 2.0 veces al año, la misma del 1/N diario."));
c.push(H2("5.3 R7: el agente aprende su objetivo"));
c.push(P("El documento de tesis pide “convergencia estable de las curvas de recompensa en al menos 3 semillas”. Con 10 semillas y un millón de pasos, **9 de 10 curvas se estabilizan** (la mitad antes de los ~750 mil pasos) y la recompensa sube en las diez. El indicador de R7 queda cumplido para PPO."));
c.push(P("La **recompensa por paso** es la “nota” que el agente recibe en cada día simulado según la rentabilidad ajustada por riesgo de su decisión. Que suba significa que el agente aprende a hacer lo que se le pide:"));
c.push(...figura("g2_curva_aprendizaje.png",
  "Figura 3. Curva de aprendizaje: recompensa por paso durante el entrenamiento (10 semillas, un millón de pasos, pliegue 0).",
  "Cada línea clara es una semilla (media móvil de ~50 mil pasos); la línea oscura es la mediana. Las líneas verticales marcan el presupuesto del piloto y el punto donde la mediana se estabiliza."));
c.push(P("Dos semillas encuentran recompensas mucho más altas que el resto. **Que la nota de entrenamiento suba no garantiza que el agente sea mejor en datos nuevos:** la sección 5.6 muestra que ocurre lo contrario."));
c.push(H2("5.4 El agente frente a las estrategias de referencia"));
c.push(P("El agente se entrenó con cinco combinaciones de información. La tabla las muestra todas en la validación del pliegue 0 (noviembre de 2018 a noviembre de 2019), con la mediana de 3 semillas y el rango que abarcan esas semillas:"));
c.push(tabla(
  ["Configuración", "Retorno", "Rango entre semillas", "Sharpe", "Máx. caída", "Rotación/año"],
  [
    ["Agente · solo mercado", "+2.6%", "−0.9 a +5.4", "0.18", "**−4.2%**", "1.97"],
    ["Agente · + macro", "+4.4%", "+1.5 a +6.8", "0.40", "−5.2%", "1.48"],
    ["**Agente · + sentimiento**", "**+9.7%**", "**−2.0 a +22.8**", "**0.74**", "−8.3%", "2.89"],
    ["Agente · + fundamentales", "+5.2%", "+5.2 a +5.6", "0.44", "−7.4%", "1.46"],
    ["Agente · todas las señales", "+2.8%", "−1.2 a +7.2", "0.13", "−7.8%", "1.78"],
    ["1/N diario", "+11.8%", "—", "0.90", "−10.2%", "1.97"],
    ["1/N trimestral", "**+13.1%**", "—", "**0.96**", "−9.7%", "1.19"],
    ["Solo caja", "+1.9%", "—", "0.00", "0.0%", "0.00"],
  ],
  [2526, 1100, 1800, 900, 1300, 1400], { num: [1, 2, 3, 4, 5], resaltar: [2] },
));
c.push(P("**El canal de noticias es el más prometedor y también el más riesgoso.** Es la única configuración cuya suma de los tres pliegues no es negativa (+0.2 puntos, contra −5.6 de solo mercado), y en este año alcanza +9.7%. Pero en el pliegue de la pandemia cae −11.9%, la peor de las cinco, con una máxima caída de −32.7% (el 1/N cayó −42.6% en ese mismo tramo, así que el agente sigue amortiguando, pero mucho menos). Y su rango entre semillas en este pliegue va de −2.0% a +22.8%: **25 puntos de dispersión contra una mejora de 7**. Con 3 semillas no alcanza para declararlo ganador."));
c.push(P("Por eso **la configuración de referencia del informe sigue siendo “solo mercado”**, que es la línea base de la comparación, y la elección definitiva se fijará antes de mirar el tramo de prueba. Elegir ahora la combinación que mejor validó sería quedarse con el mejor de cinco intentos después de ver el resultado."));
c.push(esp(60));
c.push(P("La Figura 4 muestra cómo evoluciona día a día ese año. El agente se mueve cerca de la caja durante los primeros meses y se separa de ella gradualmente. El 1/N, totalmente invertido desde el primer día, sube más pero también cae más."));
c.push(...figura("g3_patrimonio_val.png",
  "Figura 4. Valor de la cartera en la validación del pliegue 0 (inicio = 100): las 3 semillas del agente con solo datos de mercado (la línea más oscura es la mediana), frente al 1/N diario y la caja.",
  null));
c.push(P("La Figura 5 abre la cartera del agente (semilla mediana) para ver **qué decide**. El episodio arranca 100% en caja y el agente solo puede mover 5 puntos por día, así que entra al mercado despacio: termina el año con 24% en caja. Sus posiciones más grandes son InRetail y BCP; a Luz del Sur, la más cara de operar, le da poco peso."));
c.push(...figura("g4_pesos_agente.png",
  "Figura 5. Composición de la cartera del agente día a día (validación del pliegue 0, semilla mediana).",
  "Por eso la “caja media” de 62% mide en buena parte la velocidad de entrada. Si arrancar invertido o medir solo el tramo estable es una decisión de diseño pendiente."));
c.push(P("Por último, la Figura 6 resume el retorno de todas las configuraciones en los tres pliegues. Azul es ganancia y rojo, pérdida:"));
c.push(...figura("g5_mapa_calor_r8.png",
  "Figura 6. Retorno en validación por configuración y pliegue (mediana de 3 semillas).",
  "Encima de la línea, el agente con distinta información; debajo, las dos referencias principales."));
c.push(P("**Lo que muestran la tabla y las Figuras 4 a 6:**"));
c.push(B("**La ventaja del agente es la protección, no la ganancia.** Su peor caída en el pliegue 0 (−4.2%) es menos de la mitad que la del 1/N (−10.2%). En los años de caída pierde menos que el 1/N: −7.3% contra −8.7% en el pliegue 1 y −0.9% contra −7.5% en el pliegue 2."));
c.push(B("**En el año alcista queda muy por detrás del 1/N** (+2.6% contra +11.9%), y **no le gana a la caja en dos de los tres pliegues.** Ninguna configuración del agente supera todavía a la caja de forma consistente."));
c.push(B("**El agente elige quedarse en caja, y para lo que vio en su entrenamiento es la respuesta correcta.** Entre 2013 y 2018 la caja rindió 2.6% anual con caída cero, frente a 1.5% anual del 1/N con una caída de −46%. Que la validación del pliegue 0 sea el tramo más favorable de los seis es una propiedad del corte, no un error del agente."));
c.push(B("**Más información compra retorno y lo paga en riesgo.** Ordenadas por retorno en este pliegue, las cinco configuraciones se ordenan casi igual por máxima caída, pero al revés: la que más gana es la que más cae. El canal de noticias casi duplica la volatilidad del agente (10.8% contra 5.8%, mediana de los tres pliegues) y sube su costo de operación 37%."));
c.push(B("**Una prueba de sensatez propuesta por el especialista de mercado:** Luz del Sur es el activo más caro de operar (3.2% de ida y vuelta). Si el modelo de costos funciona, el agente debería evitarlo. El agente le da 2.0% de peso medio, cuando el reparto igualitario le daría 14.3%."));
c.push(H2("5.5 R8: ¿qué aporta cada tipo de información?"));
c.push(P("Se entrenó al agente con cinco combinaciones de información (solo mercado, más macro, más sentimiento, más fundamentales y todas juntas), en los 3 pliegues y con 3 semillas cada una. La Figura 7 compara la mejora de Sharpe de cada combinación frente al agente con solo datos de mercado:"));
c.push(...figura("f4_canales.png",
  "Figura 7. Mejora del ratio de Sharpe frente al agente con solo datos de mercado (mediana de 9 comparaciones pareadas: 3 pliegues × 3 semillas).",
  "La barra rayada es la suma de los aportes individuales, que es lo que se esperaría si los canales se complementaran."));
c.push(P("**Lecturas:**"));
c.push(B("**Cada canal por separado mejora el Sharpe** (sentimiento +0.45, macro +0.38, fundamentales +0.14), pero **juntos se estorban**: todas las señales combinadas logran +0.11, menos de la cuarta parte de la suma. Una explicación posible, aún por confirmar, es que con todas las señales la observación pasa de 87 a 381 variables para la misma red pequeña y la misma poca historia."));
c.push(B("**Las señales hacen al agente más activo, no más prudente.** Los tres canales empeoran la máxima caída, que era la única ventaja clara del agente. El sentimiento sube la rotación 40% y el costo 37%; el macro es el único que calma al agente."));
c.push(B("**Ninguna combinación convierte al agente en ganador frente a la caja:** todas le ganan en 1 de 3 pliegues."));
c.push(B("**Con 3 semillas, el ruido supera a la señal.** Dentro de una misma configuración, el retorno de las tres semillas va de −2.0% a +22.8%, mientras que la diferencia entre configuraciones es de unos 2 puntos. Por eso ninguna de estas cifras se reporta todavía como hallazgo, y la corrida final usa 10 semillas."));
c.push(H2("5.6 ¿Entrenar más ayuda? No: hace operar más"));
c.push(P("Se entrenaron 10 agentes durante un millón de pasos y se evaluaron en cuatro momentos del entrenamiento. El agente mejora cada vez más en su objetivo, pero en datos nuevos **empeora en 9 de las 10 semillas**:"));
c.push(...figura("f3_presupuesto.png",
  "Figura 8. Efecto de entrenar más (pliegue 0, validación, mediana de 10 semillas).",
  null));
c.push(P("El mecanismo es claro: cuanto más optimiza, más patrones de corto plazo encuentra en 2013–2018, y para aprovecharlos tiene que operar. La rotación casi se triplica (de 1.9 a 5.2 veces al año) y el costo sube 166%. Los patrones no se repiten en el año siguiente, pero el peaje sí se paga. **En este problema el sobreajuste no aparece como una curva que se despega lentamente, sino como rotación.**"));
c.push(H2("5.7 ¿Otra recompensa ayuda? Tampoco"));
c.push(P("Al descomponer la recompensa de Sharpe diferencial se encontró que, en la práctica, es casi pura rentabilidad: el término de riesgo pesa apenas entre 7% y 10% de la señal, y en el 44% de los días del tramo de entrenamiento incluso **premia** la volatilidad. En ese tramo, la recompensa le paga más a Markowitz, que pierde dinero, que al 1/N, que gana."));
c.push(P("Se diseñó entonces un filtro para evaluar recompensas **sin entrenar agentes**, comparando cómo ordena cada una a 18 estrategias reales. Ninguna de las seis candidatas pasó los cuatro criterios fijados de antemano, y el filtro mostró que ordenar como el Sharpe y dar peso al riesgo están en conflicto directo a frecuencia diaria. Se entrenaron agentes con las dos mejores alternativas: **ninguna mejora el resultado** frente a la caja. El filtro sí descartó con claridad una recompensa que estaba prevista (la de semivarianza), porque ordena al revés, y eso ahorró 30 corridas."));
c.push(P("La Figura 9 muestra el conflicto. Cada punto es una forma de recompensa. El eje vertical mide si la recompensa **ordena bien**, es decir, si prefiere las mismas estrategias que prefiere el Sharpe (1 = mismo orden, 0 = azar, negativo = al revés). El eje horizontal mide **cuánto pesa el riesgo** dentro de ella. Se busca la esquina verde: una recompensa que ordene bien y que además tome en cuenta el riesgo."));
c.push(...figura("g6_frontera_recompensa.png",
  "Figura 9. La función de recompensa: fidelidad de orden frente al peso del riesgo, sobre 18 estrategias reales en el tramo de entrenamiento del pliegue 0.",
  "Las dos series de colores barren el parámetro λ, que regula cuánto pesa el riesgo. Las líneas punteadas solo unen los valores probados: entre λ = 0.51 y 1.02 queda un tramo sin probar."));
c.push(P("La recompensa usada, el Sharpe diferencial, ordena casi al azar (0.11), y la de semivarianza ordena al revés (−0.63). Al darle más peso al riesgo, los puntos se desplazan a la derecha pero bajan: se gana atención al riesgo y se pierde fidelidad. **Ninguno de los valores probados cae en la zona buscada.**"));
c.push(recuadro("Síntesis del OE3 hasta hoy", [
  "Las tres vías naturales de mejora se midieron y las tres dieron negativo: **más cómputo** empeora, **otra recompensa** da lo mismo y **más señales** se estorban. El problema no está en el objetivo, en el presupuesto ni en la falta de datos.",
  "La hipótesis que queda en pie es económica: **en la BVL hay poca señal aprovechable, o el costo de operar se la lleva.** Es lo mismo que muestra Markowitz, que genera retorno bruto y lo entrega en comisiones. Si la corrida definitiva lo confirma, es un resultado publicable sobre mercados pequeños e ilíquidos.",
]));
c.push(esp(240));

// ---------------------------------------------------------------- 6. hallazgos
c.push(H1("6. Hallazgos principales"));
c.push(...N([
  "**En la BVL, el costo de transacción es el término dominante.** Rebalancear a diario le cuesta 24 puntos de retorno al 1/N, y Markowitz paga el 65% del capital en comisiones. Cualquier estrategia activa tiene que superar ese peaje antes de aportar.",
  "**La caja remunerada fue la estrategia ganadora en 2013–2025** (40.5% sin caídas). Esto cambia la vara de evaluación: la evaluación tiene que poder premiar al agente que decide no invertir.",
  "**El agente PPO aprende a proteger el capital:** tiene la menor caída entre las estrategias con acciones y pierde menos que el 1/N en los años malos, pero todavía no gana más que el 1/N ni que la caja.",
  "**Agregar información no suma:** cada canal aporta por separado, pero combinados se estorban.",
  "**Entrenar más empeora al agente fuera de muestra**, porque el sobreajuste se manifiesta como rotación y la rotación cuesta.",
  "**Los datos de la BVL necesitan validación externa:** la API oficial fechaba cada cierre un día después, y solo el contraste con Bloomberg lo reveló.",
  "**El modelo de lenguaje debe elegirse con anotación humana:** la referencia automática invertía el ranking de modelos, y un modelo más grande no fue mejor.",
]));
c.push(esp());
c.push(H2("Limitaciones que se declaran"));
c.push(B("Las cifras del agente son de la etapa piloto: validación, 3 semillas y solo PPO. No son todavía resultados de la tesis."));
c.push(B("El costo de comisión viene de una tarifa pública, no del tarifario negociado para una cuenta de S/1.8 millones, y el spread aún es una foto, no una serie histórica."));
c.push(B("Los precios repetidos por falta de negociación hacen que el riesgo estimado parezca menor al real."));
c.push(B("La escala es de inversionista individual (~S/1.8 millones), acotada por la liquidez del BCP."));
c.push(B("Los tres resultados de prueba no son independientes entre sí, porque los pliegues comparten historia de entrenamiento. Los intervalos de confianza se construyen sobre las semillas."));

// ---------------------------------------------------------------- 7. próximos pasos
c.push(salto());
c.push(H1("7. Próximos pasos"));
c.push(tabla(
  ["Paso", "Para qué", "Estado"],
  [
    ["Entrenar y evaluar SAC y DDPG", "Completar los tres algoritmos que compromete R7", "En implementación y pruebas"],
    ["Cerrar las decisiones de diseño pendientes", "Recompensa, condición inicial del episodio, presupuesto de entrenamiento (propuesta: detener cuando la rotación supere la del 1/N) y parámetros de Markowitz", "En decisión"],
    ["Conectar los spreads históricos de Bloomberg al modelo de costos", "Un spread fijo subestima el costo en los periodos de estrés, que es cuando el agente quiere operar", "Datos descargados"],
    ["Pre-registrar la corrida definitiva", "Fijar reglas de lectura y predicciones antes de ver el tramo de prueba", "Pendiente"],
    ["Corrida definitiva", "10 semillas × 3 pliegues × 3 algoritmos × 4 configuraciones, sobre el tramo de prueba, una sola vez", "Pendiente"],
    ["Pruebas estadísticas", "Sharpe deflactado por número de configuraciones probadas, intervalos por semillas y comparación contra la banda nula", "Pendiente"],
    ["Redacción", "Capítulos de resultados de OE1 y OE3, conclusiones y trabajo futuro", "En curso"],
  ],
  [2600, 4426, 2000], { primeraNegrita: true },
));
c.push(salto());

// ---------------------------------------------------------------- anexo
c.push(H1("Anexo. Detalle del estudio por señales (R8)"));
c.push(P("Retorno en validación por pliegue, mediana de 3 semillas, 150 mil pasos de entrenamiento."));
c.push(tabla(
  ["Configuración", "Pliegue 0", "Pliegue 1", "Pliegue 2"],
  [
    ["Solo mercado", "+2.6%", "−7.3%", "−0.9%"],
    ["Mercado + macro", "+4.4%", "−7.6%", "+0.5%"],
    ["Mercado + sentimiento", "+9.7%", "−11.9%", "+2.4%"],
    ["Mercado + fundamentales", "+5.2%", "−6.7%", "−3.4%"],
    ["Todas las señales", "+2.8%", "−8.0%", "−4.1%"],
    ["1/N diario", "+11.8%", "−8.7%", "−7.5%"],
    ["Solo caja", "+1.9%", "+0.3%", "+5.4%"],
  ],
  [3326, 1900, 1900, 1900], { num: [1, 2, 3], primeraNegrita: true },
));
c.push(esp());
c.push(P("Máxima caída en validación por pliegue:"));
c.push(tabla(
  ["Configuración", "Pliegue 0", "Pliegue 1", "Pliegue 2"],
  [
    ["Solo mercado", "−4.2%", "−21.0%", "−7.6%"],
    ["Mercado + macro", "−5.2%", "−23.8%", "−5.4%"],
    ["Mercado + sentimiento", "−8.3%", "−32.7%", "−6.1%"],
    ["Mercado + fundamentales", "−7.4%", "−17.6%", "−9.7%"],
    ["1/N diario", "−10.2%", "−42.6%", "−11.3%"],
  ],
  [3326, 1900, 1900, 1900], { num: [1, 2, 3], primeraNegrita: true },
));
c.push(esp());
c.push(P("Comportamiento medio de cada configuración (mediana sobre los 3 pliegues):"));
c.push(tabla(
  ["Configuración", "Rotación/año", "Caja media", "Volatilidad", "Costo pagado"],
  [
    ["Solo mercado", "1.97", "62.8%", "5.8%", "S/30,859"],
    ["Mercado + macro", "1.50", "58.2%", "6.7%", "S/27,690"],
    ["Mercado + sentimiento", "2.76", "56.2%", "10.8%", "S/42,248"],
    ["Mercado + fundamentales", "1.71", "50.7%", "8.9%", "S/27,023"],
  ],
  [2826, 1550, 1550, 1550, 1550], { num: [1, 2, 3, 4], primeraNegrita: true },
));
c.push(nota("Fuente de todas las cifras: docs/resultados_entorno_OE1.txt, data/interim/registro_configuraciones.jsonl y los artefactos de scripts/ablacion_r8.py y scripts/d25_presupuesto.py del repositorio de la tesis."));

// ================================================================ documento
const doc = new Document({
  creator: "Rodrigo Holguin",
  title: "Informe de avance de tesis — OE1 a OE3",
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: FONT, color: AZUL },
        paragraph: { spacing: { before: 120, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 25, bold: true, font: FONT, color: AZUL },
        paragraph: { spacing: { before: 260, after: 120 }, outlineLevel: 1, keepNext: true } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: FONT, color: "333333" },
        paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: {
    config: [
      { reference: "vinetas", levels: [
        { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 260 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 260 } } } },
      ] },
      ...numeraciones,
    ],
  },
  sections: [{
    properties: {
      page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1300, left: 1440 } },
      titlePage: true,
    },
    headers: {
      default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
        children: [new TextRun({ text: "Informe de avance · OE1–OE3 · DRL en la BVL", size: 16, color: GRIS_TXT })] })] }),
      first: new Header({ children: [new Paragraph({ children: [] })] }),
    },
    footers: {
      default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: [PageNumber.CURRENT], size: 17, color: GRIS_TXT })] })] }),
      first: new Footer({ children: [new Paragraph({ children: [] })] }),
    },
    children: c,
  }],
});

Packer.toBuffer(doc).then((b) => { fs.writeFileSync(OUT, b); console.log("escrito", OUT, b.length); });
