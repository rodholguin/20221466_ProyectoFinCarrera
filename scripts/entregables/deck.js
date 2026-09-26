const fs = require("fs");
const path = require("path");
const PptxGenJS = require("pptxgenjs");

const FIG = path.join(__dirname, "figppt");
const OUT = process.argv[2] || path.join(__dirname, "avance.pptx");

// ---------------------------------------------------------------- paleta
const NAVY = "1E2761";      // dominante
const NAVY2 = "3B4E85";     // navy claro para texto secundario sobre claro
const ICE = "CADCFC";       // apoyo
const ACC = "EB6834";       // acento
const INK = "1A1A1A";
const MUTE = "5F6470";
const CARD = "F2F5FA";
const WHITE = "FFFFFF";
const VERDE = "0C6B4A";

const HF = "Cambria";   // titulares
const BF = "Calibri";   // cuerpo

const W = 13.33, H = 7.5;
const M = 0.62;                 // margen
const COL = W - 2 * M;          // ancho util

const pres = new PptxGenJS();
pres.layout = "LAYOUT_WIDE";
pres.author = "Rodrigo Holguin";
pres.title = "Avance de tesis — DRL en la BVL";

// ---------------------------------------------------------------- helpers
function slideBase(kicker, titulo, opts = {}) {
  const s = pres.addSlide();
  const oscuro = !!opts.oscuro;
  if (oscuro) s.background = { color: NAVY };
  if (kicker) {
    s.addText(kicker.toUpperCase(), {
      x: M, y: 0.34, w: COL, h: 0.26, isTextBox: true, margin: 0,
      fontFace: BF, fontSize: 11.5, bold: true, charSpacing: 1.6,
      color: oscuro ? ICE : ACC,
    });
  }
  if (titulo) {
    s.addText(titulo, {
      x: M, y: 0.62, w: COL, h: opts.hTitulo || 0.72, isTextBox: true, margin: 0,
      fontFace: HF, fontSize: opts.fsTitulo || 27, bold: true,
      color: oscuro ? WHITE : NAVY, valign: "top",
    });
  }
  return s;
}

function pie(s, texto) {
  s.addText(texto, {
    x: M, y: H - 0.62, w: COL, h: 0.3, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 10.5, italic: true, color: MUTE,
  });
}

// tarjeta con titulo y lineas de texto
function card(s, x, y, w, h, titulo, lineas, o = {}) {
  s.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.06,
    fill: { color: o.fill || CARD },
    line: { color: o.fill || CARD, width: 0 },
    shadow: { type: "outer", angle: 90, blur: 8, offset: 1, color: "9AA3B5", opacity: 0.22 },
  });
  const pad = 0.22;
  let cy = y + pad;
  if (titulo) {
    s.addText(titulo, {
      x: x + pad, y: cy, w: w - 2 * pad, h: 0.3, isTextBox: true, margin: 0,
      fontFace: BF, fontSize: o.fsTitulo || 14, bold: true, color: o.colorTitulo || NAVY,
    });
    cy += o.gapTitulo || 0.38;
  }
  if (lineas && lineas.length) {
    const items = lineas.map((t, i) => ({
      text: typeof t === "string" ? t : t.text,
      options: Object.assign(
        { breakLine: i < lineas.length - 1, bullet: o.vinetas ? { indent: 12 } : false },
        typeof t === "object" ? t.options : {}
      ),
    }));
    s.addText(items, {
      x: x + pad, y: cy, w: w - 2 * pad, h: y + h - cy - pad * 0.6, isTextBox: true, margin: 0,
      fontFace: BF, fontSize: o.fs || 12.5, color: o.color || INK,
      lineSpacingMultiple: 1.12, paraSpaceAfter: o.vinetas ? 5 : 3, valign: "top",
    });
  }
}

// numero grande con etiqueta
function stat(s, x, y, w, numero, etiqueta, o = {}) {
  s.addText(numero, {
    x, y, w, h: 0.82, isTextBox: true, margin: 0,
    fontFace: HF, fontSize: o.fs || 40, bold: true, color: o.color || ACC,
    align: o.align || "left",
  });
  s.addText(etiqueta, {
    x, y: y + (o.fs && o.fs > 44 ? 0.9 : 0.8), w, h: o.hEtq || 0.7, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: o.fsEtq || 12, color: o.colorEtq || INK, align: o.align || "left",
    lineSpacingMultiple: 1.05,
  });
}

// imagen ajustada a una caja, centrada
function img(s, archivo, x, y, w, h, o = {}) {
  const buf = fs.readFileSync(path.join(FIG, archivo));
  const iw = buf.readUInt32BE(16), ih = buf.readUInt32BE(20);
  const esc = Math.min(w / iw, h / ih);
  const fw = iw * esc, fh = ih * esc;
  s.addImage({
    path: path.join(FIG, archivo),
    x: x + (w - fw) / 2, y: y + (o.top ? 0 : (h - fh) / 2), w: fw, h: fh,
  });
  return y + (o.top ? fh : (h - fh) / 2 + fh);
}

function caption(s, x, y, w, texto) {
  s.addText(texto, {
    x, y, w, h: 0.32, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 10.5, color: MUTE, align: "center", italic: true,
  });
}

// franja de conclusion
function remate(s, texto, y) {
  s.addShape(pres.ShapeType.roundRect, {
    x: M, y, w: COL, h: 0.62, rectRadius: 0.05,
    fill: { color: NAVY }, line: { color: NAVY, width: 0 },
  });
  s.addText(texto, {
    x: M + 0.24, y: y + 0.02, w: COL - 0.48, h: 0.58, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 13, color: WHITE, valign: "middle", bold: false,
  });
}

// chip numerado (motivo visual repetido)
function chip(s, x, y, n, texto, w) {
  s.addShape(pres.ShapeType.ellipse, {
    x, y, w: 0.34, h: 0.34, fill: { color: NAVY }, line: { color: NAVY, width: 0 },
  });
  s.addText(String(n), {
    x, y, w: 0.34, h: 0.34, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 12, bold: true, color: WHITE, align: "center", valign: "middle",
  });
  s.addText(texto, {
    x: x + 0.46, y: y - 0.02, w: w - 0.46, h: 0.42, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 12.5, color: INK, valign: "top",
  });
}

// =========================================================== 1 · portada
{
  const s = pres.addSlide();
  s.background = { color: NAVY };
  s.addText("Agentes de inversión que aprenden por refuerzo", {
    x: M, y: 1.75, w: 11.6, h: 1.5, isTextBox: true, margin: 0,
    fontFace: HF, fontSize: 40, bold: true, color: WHITE, lineSpacingMultiple: 1.05,
  });
  s.addText("Mercado, estados financieros y noticias en la Bolsa de Valores de Lima", {
    x: M, y: 3.25, w: 11.2, h: 0.5, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 18, color: ICE,
  });
  s.addText("Avance de los objetivos específicos 1, 2 y 3", {
    x: M, y: 4.25, w: 11.2, h: 0.4, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 14, bold: true, color: ACC, charSpacing: 0.6,
  });
  s.addText([
    { text: "Rodrigo Alejandro Holguin Huari", options: { bold: true, breakLine: true } },
    { text: "Asesor: Dr. Edwin Rafael Villanueva Talavera", options: { breakLine: true } },
    { text: "Facultad de Ciencias e Ingeniería · 22 de septiembre de 2026", options: {} },
  ], {
    x: M, y: 5.5, w: 11.2, h: 1.1, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 13, color: ICE, lineSpacingMultiple: 1.25,
  });
  s.addNotes("Presento el avance de los tres objetivos. OE1 y OE2 están cerrados; OE3 está en curso, con PPO entrenado y evaluado.");
}

// =========================================================== 2 · el problema
{
  const s = slideBase("El problema", "La BVL no es Wall Street: aquí operar cuesta caro");
  s.addText("La mayoría de estudios de IA para inversión se hacen en mercados grandes y líquidos, donde operar es casi gratis. La pregunta de esta tesis es si un agente aprende algo útil cuando cada operación paga peaje.", {
    x: M, y: 1.5, w: 11.5, h: 0.6, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 14, color: INK, lineSpacingMultiple: 1.15,
  });
  const anchoC = 3.85, gap = 0.36;
  const datos = [
    ["10%", "de los días los 7 activos tienen precio propio el mismo día", "El resto arrastra el precio anterior: no hubo operaciones que lo movieran"],
    ["0.08% → 2.2%", "es el rango del spread entre activos", "Lo que se pierde solo por cruzar la punta: Alicorp contra Luz del Sur"],
    ["S/40", "de comisión mínima por orden", "Las órdenes chicas son carísimas: debajo de S/9,300 el costo fijo domina"],
  ];
  datos.forEach((d, i) => {
    const x = M + i * (anchoC + gap);
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 2.45, w: anchoC, h: 2.9, rectRadius: 0.06,
      fill: { color: CARD }, line: { color: CARD, width: 0 },
      shadow: { type: "outer", angle: 90, blur: 8, offset: 1, color: "9AA3B5", opacity: 0.22 },
    });
    s.addText(d[0], {
      x: x + 0.24, y: 2.68, w: anchoC - 0.48, h: 0.8, isTextBox: true, margin: 0,
      fontFace: HF, fontSize: d[0].length > 6 ? 27 : 38, bold: true, color: ACC,
    });
    s.addText(d[1], {
      x: x + 0.24, y: 3.6, w: anchoC - 0.48, h: 0.65, isTextBox: true, margin: 0,
      fontFace: BF, fontSize: 13.5, bold: true, color: NAVY, lineSpacingMultiple: 1.05,
    });
    s.addText(d[2], {
      x: x + 0.24, y: 4.32, w: anchoC - 0.48, h: 0.85, isTextBox: true, margin: 0,
      fontFace: BF, fontSize: 11.5, color: MUTE, lineSpacingMultiple: 1.1,
    });
  });
  remate(s, "Universo: 7 empresas de 7 sectores, 2012–2025, cartera de S/1.8 millones  ·  OE1 entorno: cerrado  ·  OE2 datos: cerrado  ·  OE3 agente: en curso", 5.8);
  pie(s, "Frecuencia de negociación: Informe Bursátil Mensual de la BVL. Spreads: puntas de compra y venta por activo.");
  s.addNotes("El costo de transacción no es un detalle de implementación: es la restricción que define el problema.");
}

// =========================================================== 3 · R1 + R2
{
  const s = slideBase("OE1 · Entorno de simulación", "R1 + R2 · Un simulador que cobra lo que cobra la BVL");
  s.addText("Entorno estilo Gymnasium: en cada paso el agente observa el mercado, decide cómo reajustar la cartera, paga los costos de ese reajuste y recibe el retorno del día siguiente.", {
    x: M, y: 1.5, w: 11.6, h: 0.55, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 14, color: INK, lineSpacingMultiple: 1.15,
  });
  // reloj
  s.addText("EL RELOJ, QUE ES LO QUE GARANTIZA EL REALISMO", {
    x: M, y: 2.15, w: 6, h: 0.28, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 11, bold: true, charSpacing: 1.2, color: MUTE,
  });
  const pasos = [
    ["t − 1", "Observa", "datos hasta el cierre de ayer"],
    ["t", "Ejecuta", "rebalancea y paga costos"],
    ["t + 1", "Cobra", "gana el retorno del día"],
  ];
  const aP = 1.72, gP = 0.42;
  pasos.forEach((p, i) => {
    const x = M + i * (aP + gP);
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 2.5, w: aP, h: 1.6, rectRadius: 0.06,
      fill: { color: i === 1 ? NAVY : CARD }, line: { color: i === 1 ? NAVY : CARD, width: 0 },
    });
    s.addText(p[0], {
      x, y: 2.7, w: aP, h: 0.3, isTextBox: true, margin: 0, align: "center",
      fontFace: BF, fontSize: 11.5, bold: true, color: i === 1 ? ICE : ACC,
    });
    s.addText(p[1], {
      x, y: 3.04, w: aP, h: 0.34, isTextBox: true, margin: 0, align: "center",
      fontFace: HF, fontSize: 16, bold: true, color: i === 1 ? WHITE : NAVY,
    });
    s.addText(p[2], {
      x: x + 0.12, y: 3.44, w: aP - 0.24, h: 0.55, isTextBox: true, margin: 0, align: "center",
      fontFace: BF, fontSize: 10.5, color: i === 1 ? ICE : MUTE, lineSpacingMultiple: 1.05,
    });
    if (i < 2) {
      s.addShape(pres.ShapeType.rightArrow, {
        x: x + aP + 0.09, y: 3.18, w: 0.24, h: 0.24,
        fill: { color: "B9BFCC" }, line: { color: "B9BFCC", width: 0 },
      });
    }
  });
  s.addText("Ninguna decisión puede usar información de su propio día de ejecución.", {
    x: M, y: 4.3, w: 6.1, h: 0.35, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 12, italic: true, color: NAVY2,
  });
  // cuatro reglas
  s.addText("CUATRO REGLAS QUE LO HACEN ECONÓMICAMENTE HONESTO", {
    x: 6.95, y: 2.15, w: 5.8, h: 0.28, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 11, bold: true, charSpacing: 1.2, color: MUTE,
  });
  const reglas = [
    ["Costo por activo", "cada acción paga su propio spread"],
    ["No se opera sin mercado", "si no negoció, conserva su peso"],
    ["La caja rinde", "el dinero sin invertir gana la tasa del BCRP"],
    ["La acción es un ajuste", "mover los pesos, no redefinirlos"],
  ];
  reglas.forEach((r, i) => {
    const x = 6.95 + (i % 2) * 2.98;
    const y = 2.5 + Math.floor(i / 2) * 1.2;
    card(s, x, y, 2.78, 1.05, r[0], [r[1]], { fsTitulo: 12.5, fs: 10.5, gapTitulo: 0.3, color: MUTE });
  });
  remate(s, "85 pruebas automáticas. Con costo cero, «comprar y no tocar» replica exactamente comprar y mantener; una cartera 100% en caja crece exactamente a la tasa del BCRP.", 5.35);
  pie(s, "Decisiones D2, D7, D8, D9 y D13 del registro de decisiones de diseño.");
  s.addNotes("Las pruebas de conservación son la defensa contra errores silenciosos de contabilidad: un bug aquí contamina todos los resultados sin hacer fallar nada.");
}

// =========================================================== 4 · baselines
{
  const s = slideBase("OE1 · Decisión clave", "Las estrategias de referencia corren dentro del mismo simulador");
  card(s, M, 1.55, 4.55, 2.3, "Por qué importa", [
    "Mismos costos, mismas reglas, mismo simulador para el agente y sus rivales: la comparación es justa por construcción, no por revisión.",
  ], { fs: 12.5 });
  card(s, M, 4.05, 4.55, 1.6, "Y cada uno con su mejor frecuencia", [
    "Compararse contra un 1/N rebalanceado a diario sería ganarle a un rival mal implementado.",
  ], { fs: 12.5 });
  stat(s, M, 5.9, 4.55, "−24 puntos", "es lo que el costo le quita al reparto igualitario diario: de +32.8% a +8.5% en 13 años", { fs: 30, hEtq: 0.8, fsEtq: 12 });
  img(s, "f1_baselines.png", 5.45, 1.45, 7.4, 4.8);
  caption(s, 5.45, 6.4, 7.4, "Retorno total y peor caída, 2013–2025, con costos reales. En verde, la caja remunerada.");
  s.addNotes("La barra gris es el mismo 1/N sin cobrarle costos: la diferencia entre gris y azul es el peaje.");
}

// =========================================================== 5 · la caja gana
{
  const s = slideBase("OE1 · Resultado", "El hallazgo incómodo: la caja le ganó a todo");
  img(s, "g1_evolucion_baselines.png", 4.85, 1.45, 8.0, 4.15, { top: true });
  caption(s, 4.85, 5.75, 8.0, "Valor de la cartera, 2013–2025 (inicio = 100), con costos reales.");
  stat(s, M, 1.55, 3.9, "40.5%", "rindió la caja remunerada, contra 31.0% de la mejor estrategia con acciones — y sin ninguna caída", { fs: 46, hEtq: 0.95 });
  card(s, M, 3.75, 3.9, 1.9, "Markowitz: el argumento medido sobre un método clásico", [
    "Paga S/1.18 MM en comisiones, el 65% del capital inicial, y tiene la peor caída de la tabla (−55%).",
  ], { fs: 11.5, fsTitulo: 12.5, gapTitulo: 0.52 });
  remate(s, "Consecuencia de diseño: la vara del agente no es el reparto igualitario, es el banco. Y si la caja no rindiera, el entorno le escondería al agente la estrategia que de hecho ganó.", 6.15);
  s.addNotes("En 2013-2025 este universo de acciones rindió menos que la tasa de referencia. Por eso la evaluación tiene que poder premiar al agente que decide no invertir.");
}

// =========================================================== 6 · el panel
{
  const s = slideBase("OE2 · Datos", "R3 a R6 · Un panel de 24,584 × 120 sin información del futuro");
  const fuentes = [
    ["Mercado (R3)", "BVL, fuente oficial", "Precio de retorno total (con dividendos y splits), indicadores técnicos y banderas de días sin negociación"],
    ["Fundamentales (R4)", "SMV, 2005–2025", "ROE, ROA, margen neto, deuda/patrimonio, P/E y dividendos, más la sorpresa de cada resultado trimestral"],
    ["Noticias (R5)", "Prensa peruana + LLM local", "2,237 eventos relevantes clasificados por tipo y polaridad, resumidos en 9 series diarias"],
    ["Macro", "BCRP y mercados", "Tipo de cambio, riesgo país, cobre, petróleo, S&P 500 y MSCI Emergentes"],
  ];
  const aF = 2.93, gF = 0.18;
  fuentes.forEach((f, i) => {
    const x = M + i * (aF + gF);
    card(s, x, 1.55, aF, 2.6, f[0], [
      { text: f[1], options: { bold: true, color: ACC, breakLine: true } },
      { text: "", options: { breakLine: true, fontSize: 5 } },
      { text: f[2], options: {} },
    ], { fs: 11, fsTitulo: 13 });
    s.addShape(pres.ShapeType.rightArrow, {
      x: x + aF / 2 - 0.14, y: 4.3, w: 0.28, h: 0.28,
      fill: { color: "B9BFCC" }, line: { color: "B9BFCC", width: 0 }, rotate: 90,
    });
  });
  s.addShape(pres.ShapeType.roundRect, {
    x: M, y: 4.75, w: COL, h: 1.0, rectRadius: 0.06,
    fill: { color: NAVY }, line: { color: NAVY, width: 0 },
  });
  s.addText([
    { text: "R6 · Panel unificado    ", options: { bold: true, fontSize: 15, color: WHITE } },
    { text: "24,584 filas × 120 columnas   ·   7 activos   ·   2 de enero de 2012 a 30 de diciembre de 2025   ·   sin valores faltantes", options: { fontSize: 12.5, color: ICE } },
  ], {
    x: M + 0.3, y: 4.75, w: COL - 0.6, h: 1.0, isTextBox: true, margin: 0, valign: "middle",
  });
  card(s, M, 5.95, 6.0, 1.1, "Point-in-time: cada dato entra el día en que se hizo público", [
    "La fecha de los estados financieros es la de su publicación real, tomada de los hechos de importancia de la BVL.",
  ], { fs: 11, fsTitulo: 12.5, gapTitulo: 0.3 });
  card(s, 6.94, 5.95, 5.77, 1.1, "La macro se midió antes de incluirla", [
    "El tipo de cambio afecta a 7 de 7 empresas y el riesgo país a 6 de 7. El oro se eliminó: no afecta a ninguna.",
  ], { fs: 11, fsTitulo: 12.5, gapTitulo: 0.3 });
  s.addNotes("El trabajo difícil no fue extraer los datos sino fecharlos: cualquier dato que entre antes de ser público convierte el resultado en ficción.");
}

// =========================================================== 7 · fechas
{
  const s = slideBase("OE2 · Calidad de datos", "La validación que encontró el error: contrastar contra otra fuente");
  s.addText("La API oficial de la BVL etiqueta cada cierre con la fecha del día hábil siguiente: el panel iba un día atrasado. Todas las validaciones internas pasaban, porque un panel corrido un día es perfectamente consistente consigo mismo.", {
    x: M, y: 1.48, w: 11.6, h: 0.62, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 14, color: INK, lineSpacingMultiple: 1.15,
  });
  // antes / despues
  const aC = 3.5;
  s.addShape(pres.ShapeType.roundRect, {
    x: M, y: 2.45, w: aC, h: 2.15, rectRadius: 0.06,
    fill: { color: "FBECE8" }, line: { color: "FBECE8", width: 0 },
  });
  s.addText("ANTES", { x: M + 0.24, y: 2.62, w: aC - 0.48, h: 0.3, isTextBox: true, margin: 0, fontFace: BF, fontSize: 11, bold: true, charSpacing: 1.2, color: "B23A2E" });
  s.addText("−0.02 a 0.13", { x: M + 0.24, y: 2.94, w: aC - 0.48, h: 0.6, isTextBox: true, margin: 0, fontFace: HF, fontSize: 28, bold: true, color: "B23A2E" });
  s.addText("correlación de retornos contra Bloomberg: ninguna relación", { x: M + 0.24, y: 3.6, w: aC - 0.48, h: 0.8, isTextBox: true, margin: 0, fontFace: BF, fontSize: 11.5, color: INK, lineSpacingMultiple: 1.1 });

  s.addShape(pres.ShapeType.roundRect, {
    x: M + aC + 0.3, y: 2.45, w: aC, h: 2.15, rectRadius: 0.06,
    fill: { color: "E6F4EC" }, line: { color: "E6F4EC", width: 0 },
  });
  s.addText("DESPUÉS", { x: M + aC + 0.54, y: 2.62, w: aC - 0.48, h: 0.3, isTextBox: true, margin: 0, fontFace: BF, fontSize: 11, bold: true, charSpacing: 1.2, color: VERDE });
  s.addText("0.885 a 0.986", { x: M + aC + 0.54, y: 2.94, w: aC - 0.48, h: 0.6, isTextBox: true, margin: 0, fontFace: HF, fontSize: 28, bold: true, color: VERDE });
  s.addText("los 7 activos pasan el umbral fijado de antemano (0.85)", { x: M + aC + 0.54, y: 3.6, w: aC - 0.48, h: 0.8, isTextBox: true, margin: 0, fontFace: BF, fontSize: 11.5, color: INK, lineSpacingMultiple: 1.1 });

  card(s, M + 2 * aC + 0.6, 2.45, 4.61, 2.15, "Prueba de evento", [
    "La caída tras la segunda vuelta electoral de 2021 —Alicorp −15.1%, BCP −9.8%, Ferreycorp −15.3%— cae ahora en el lunes 7 de junio, que es la fecha económicamente correcta.",
  ], { fs: 12, fsTitulo: 13.5 });

  s.addText("QUÉ EFECTO TUVO EN EL AGENTE", {
    x: M, y: 4.85, w: 11.6, h: 0.28, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 11, bold: true, charSpacing: 1.2, color: MUTE,
  });
  s.addText("El panel iba rancio, no adelantado: el agente decidía con información de dos días antes, o sea resolvía un problema más difícil que el real. Al corregirlo, su retorno pasó de −2.2% a +2.6% y su peor caída mejoró de −7.0% a −4.2%.", {
    x: M, y: 5.18, w: 11.6, h: 0.6, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 12.5, color: INK, lineSpacingMultiple: 1.12,
  });
  remate(s, "La regla que deja: toda serie que venga de una fuente sin documentación de sus fechas se contrasta contra una segunda fuente por correlación de RETORNOS, no de niveles.", 5.95);
  s.addNotes("Las conclusiones cualitativas sobrevivieron todas a la corrección; solo cambiaron las cifras.");
}

// =========================================================== 8 · R5
{
  const s = slideBase("OE2 · Noticias", "R5 · Un modelo de lenguaje local etiqueta 19,500 titulares");
  card(s, M, 1.5, 5.6, 2.05, "Cómo funciona", [
    "El LLM clasifica el TIPO de evento —resultados, fusión, regulación, crisis…— sobre una taxonomía de 15 categorías. Es una tarea objetiva.",
    "La magnitud de cada tipo la fija el autor, no el modelo. Las categorías de magnitud cero son el filtro de relevancia.",
  ], { fs: 12, vinetas: true });
  card(s, M, 3.75, 5.6, 1.35, "Qué recibe el agente", [
    "9 series diarias: positivo, neutro y negativo, cada una con memoria de 5, 20 y 60 días.",
  ], { fs: 12 });
  card(s, M, 5.28, 5.6, 1.35, "Validación económica", [
    "Las noticias marcadas como relevantes coinciden con saltos grandes de precio el 34.8% de las veces, contra 18.4% de base (p = 0.006). Las irrelevantes no se distinguen del azar.",
  ], { fs: 11.5, colorTitulo: VERDE });

  s.addText("DOS RESULTADOS QUE INTERESAN A UN INFORMÁTICO", {
    x: 6.6, y: 1.5, w: 6.1, h: 0.28, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 11, bold: true, charSpacing: 1.2, color: MUTE,
  });
  chip(s, 6.6, 1.9, 1, "", 6.1);
  s.addText([
    { text: "El ranking de modelos se invirtió.", options: { bold: true, breakLine: true } },
    { text: "Se eligió con 550 titulares anotados a mano por el autor. El modelo que lideraba contra una referencia hecha por otro modelo cayó al tercer lugar: evaluar un LLM contra otro LLM favorece a los que razonan igual.", options: {} },
  ], {
    x: 7.06, y: 1.88, w: 5.64, h: 1.15, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 12, color: INK, lineSpacingMultiple: 1.12,
  });
  chip(s, 6.6, 3.2, 2, "", 6.1);
  s.addText([
    { text: "Más grande no fue mejor.", options: { bold: true, breakLine: true } },
    { text: "El modelo de 27 mil millones de parámetros rindió peor que el de 12 mil millones. El elegido, gemma3:12b, alcanza 75% de precisión y 92% de exhaustividad detectando noticias relevantes.", options: {} },
  ], {
    x: 7.06, y: 3.18, w: 5.64, h: 1.15, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 12, color: INK, lineSpacingMultiple: 1.12,
  });
  card(s, 6.6, 4.5, 6.11, 2.13, "Por qué importa para la tesis", [
    "El canal de noticias es el único que no se puede comprar hecho: es trabajo propio de extracción, clasificación y validación.",
    "Todo corre en GPU local con un modelo abierto, así que la señal es reproducible y no depende de un proveedor externo ni de su precio.",
  ], { fs: 12, vinetas: true });
  s.addNotes("La anotación humana fue el bloqueante que ordenó la selección de modelo: sin ella el ranking estaba invertido.");
}

// =========================================================== 9 · R7
{
  const s = slideBase("OE3 · Entrenamiento", "R7 · El agente aprende: 9 de 10 semillas llegan a meseta");
  const conf = [
    ["Algoritmo", "PPO · SAC y DDPG en pruebas"],
    ["Red", "64 × 64, pequeña a propósito"],
    ["Qué decide", "pesos de 7 acciones más caja"],
    ["Recompensa", "Sharpe diferencial, día a día"],
    ["Repeticiones", "3 semillas; 10 en la corrida final"],
    ["Evaluación", "validación; el test sigue intacto"],
  ];
  card(s, M, 1.5, 4.1, 3.4, "Configuración del piloto", [], {});
  conf.forEach((c, i) => {
    const y = 2.0 + i * 0.44;
    s.addText(c[0], {
      x: M + 0.22, y, w: 1.35, h: 0.4, isTextBox: true, margin: 0,
      fontFace: BF, fontSize: 11.5, bold: true, color: NAVY,
    });
    s.addText(c[1], {
      x: M + 1.55, y, w: 2.3, h: 0.4, isTextBox: true, margin: 0,
      fontFace: BF, fontSize: 11.5, color: INK,
    });
  });
  card(s, M, 5.05, 4.1, 1.05, "Cómo se lee la curva", [
    "Es la nota que recibe el agente cada día simulado: si sube, aprende lo que se le pide.",
  ], { fs: 11.5, fsTitulo: 12.5, gapTitulo: 0.32 });
  img(s, "g2_curva_aprendizaje.png", 5.0, 1.5, 7.8, 4.0, { top: true });
  caption(s, 5.0, 5.6, 7.8, "Recompensa por paso durante el entrenamiento: 10 semillas, un millón de pasos, pliegue 0.");
  remate(s, "El indicador que pide el documento de tesis —convergencia estable en al menos 3 semillas— queda cumplido para PPO. Pero la sección siguiente muestra que una nota de entrenamiento más alta no significa mejor desempeño fuera de muestra.", 6.25);
  s.addNotes("Las dos semillas que se disparan hacia arriba son las que peor validan: esa es la tensión de la diapositiva de las tres vías.");
}

// =========================================================== 10 · dos bugs
{
  const s = slideBase("OE3 · Lecciones de diseño", "Dos defectos propios que casi se leen como evidencia sobre la BVL");
  const bugs = [
    {
      n: "1", t: "El azar de exploración hacía operar de más",
      antes: "206", antesEtq: "veces al año rotaba la cartera un agente SIN entrenar, solo por el ruido de exploración",
      texto: "En un espacio de acción tipo símplex, el ruido gaussiano con los parámetros por defecto de la librería resortea la cartera entera en cada paso. El agente pagaba un peaje enorme que no venía de sus decisiones, así que no tenía cómo aprender a evitarlo.",
    },
    {
      n: "2", t: "«No operar» era casi inalcanzable",
      antes: "9.2 → 2.0", antesEtq: "veces al año bajó la rotación al cambiar la forma de la acción",
      texto: "Si el agente propone una cartera nueva cada día, quedarse quieto exige reproducir exactamente la decisión anterior: un accidente, no un estado alcanzable. La acción pasó a ser un ajuste sobre los pesos actuales, y no operar quedó gratis.",
    },
  ];
  bugs.forEach((b, i) => {
    const x = M + i * 6.2;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 1.5, w: 5.89, h: 4.0, rectRadius: 0.06,
      fill: { color: CARD }, line: { color: CARD, width: 0 },
      shadow: { type: "outer", angle: 90, blur: 8, offset: 1, color: "9AA3B5", opacity: 0.22 },
    });
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.26, y: 1.74, w: 0.4, h: 0.4, fill: { color: NAVY }, line: { color: NAVY, width: 0 } });
    s.addText(b.n, { x: x + 0.26, y: 1.74, w: 0.4, h: 0.4, isTextBox: true, margin: 0, align: "center", valign: "middle", fontFace: BF, fontSize: 13, bold: true, color: WHITE });
    s.addText(b.t, { x: x + 0.8, y: 1.72, w: 4.85, h: 0.45, isTextBox: true, margin: 0, fontFace: BF, fontSize: 14.5, bold: true, color: NAVY });
    s.addText(b.antes, { x: x + 0.26, y: 2.28, w: 2.3, h: 0.6, isTextBox: true, margin: 0, fontFace: HF, fontSize: b.antes.length > 4 ? 26 : 34, bold: true, color: ACC });
    s.addText(b.antesEtq, { x: x + 2.65, y: 2.3, w: 3.0, h: 0.75, isTextBox: true, margin: 0, fontFace: BF, fontSize: 11, color: MUTE, lineSpacingMultiple: 1.08 });
    s.addText(b.texto, { x: x + 0.26, y: 3.15, w: 5.37, h: 1.75, isTextBox: true, margin: 0, fontFace: BF, fontSize: 12, color: INK, lineSpacingMultiple: 1.15 });
  });
  remate(s, "La regla que queda: la exploración se calibra mirando CUÁNTO OPERA el agente, nunca cuánto gana. Un hiperparámetro elegido mirando el desempeño en validación es selección encubierta.", 5.75);
  pie(s, "Ninguno de los dos resultados era evidencia sobre el mercado peruano: eran parametrización.");
  s.addNotes("Es el tipo de error que se publica como hallazgo si uno no lo persigue: el agente parecía destruir valor y en realidad pagaba el peaje del ruido.");
}

// =========================================================== 11 · R8 resultados
{
  const s = slideBase("OE3 · Resultados", "R8 · El agente protege capital; las noticias prometen más");
  img(s, "g5_mapa_calor_r8.png", 5.45, 1.45, 7.45, 4.15, { top: true });
  caption(s, 5.45, 5.62, 7.45, "Retorno en validación por configuración y pliegue (mediana de 3 semillas). Azul es ganancia; rojo, pérdida.");
  stat(s, M, 1.5, 4.6, "+9.7%", "alcanza el agente con el canal de noticias en el tramo más favorable de la partición, contra +2.6% con solo datos de mercado", { fs: 40, hEtq: 0.85, fsEtq: 12 });
  card(s, M, 3.35, 4.6, 1.25, "Su ventaja clara es otra: la prudencia", [
    "Con solo mercado tiene la menor caída de todas las estrategias con acciones: −4.2% contra −10.2% del reparto igualitario.",
  ], { fs: 11.5, fsTitulo: 12.5, gapTitulo: 0.32 });
  card(s, M, 4.78, 4.6, 1.3, "Y el matiz que hay que decir en voz alta", [
    "El canal de noticias es también el más volátil: en el pliegue de la pandemia cae −11.9%, y entre semillas va de −2.0% a +22.8%.",
  ], { fs: 11.5, fsTitulo: 12.5, gapTitulo: 0.32, colorTitulo: ACC });
  card(s, M, 6.2, 4.6, 0.75, "", [
    "Ninguna configuración le gana a la caja en más de 1 de los 3 pliegues.",
  ], { fs: 11.5, fill: "EDEFF5" });
  s.addNotes("Con 3 semillas no se puede declarar ganador a ningún canal: la dispersión entre semillas es mayor que la diferencia entre configuraciones. Por eso la corrida final usa 10.");
}

// =========================================================== 12 · qué decide
{
  const s = slideBase("OE3 · Comportamiento", "Qué decide el agente, y qué le aportan las señales");
  img(s, "g4_pesos_agente.png", M, 1.45, 6.2, 3.1, { top: true });
  caption(s, M, 4.6, 6.2, "Composición de la cartera día a día, validación del pliegue 0.");
  img(s, "f4_canales.png", 6.95, 1.45, 5.8, 3.1, { top: true });
  caption(s, 6.95, 4.6, 5.8, "Mejora de Sharpe frente al agente con solo datos de mercado.");
  card(s, M, 5.05, 6.2, 1.55, "Elige quedarse fuera del mercado, y tiene razón", [
    "Arranca 100% en caja y entra despacio: termina el año con 24%. En su tramo de entrenamiento la caja rindió 2.6% anual contra 1.5% del reparto igualitario, con caída cero contra −46%.",
  ], { fs: 11.5, fsTitulo: 13, gapTitulo: 0.34 });
  card(s, 6.95, 5.05, 5.76, 1.55, "Los canales se estorban entre sí", [
    "Cada uno aporta por separado, pero las tres señales juntas logran +0.11 de Sharpe: menos de la cuarta parte de la suma de sus aportes individuales (+0.97).",
  ], { fs: 11.5, fsTitulo: 13, gapTitulo: 0.34, colorTitulo: ACC });
  pie(s, "Prueba de sensatez: Luz del Sur es el activo más caro de operar (3.2% ida y vuelta) y el agente le da 2.0% de peso medio, cuando el reparto igualitario le daría 14.3%.");
  s.addNotes("La observación pasa de 87 a 381 variables cuando se juntan los canales, con la misma red pequeña y la misma poca historia: esa es la hipótesis a contrastar con 10 semillas.");
}

// =========================================================== 13 · las tres vías
{
  const s = slideBase("OE3 · Las vías de mejora", "Tres formas de mejorar al agente: medidas, y las tres negativas");
  // via 1
  s.addText("1 · ENTRENAR MÁS", { x: M, y: 1.42, w: 6.0, h: 0.3, isTextBox: true, margin: 0, fontFace: BF, fontSize: 12, bold: true, charSpacing: 1.2, color: ACC });
  img(s, "f3_presupuesto.png", M, 1.75, 6.05, 2.0, { top: true });
  s.addText("La recompensa de entrenamiento sube, pero la validación empeora en 9 de las 10 semillas: la rotación casi se triplica y el costo sube 166%.", {
    x: M, y: 3.85, w: 6.05, h: 0.75, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 12, color: INK, lineSpacingMultiple: 1.12,
  });
  // via 2
  s.addText("2 · CAMBIAR LA RECOMPENSA", { x: 6.95, y: 1.42, w: 5.8, h: 0.3, isTextBox: true, margin: 0, fontFace: BF, fontSize: 12, bold: true, charSpacing: 1.2, color: ACC });
  img(s, "g6_frontera_recompensa.png", 6.95, 1.75, 5.8, 2.0, { top: true });
  s.addText("Ordenar bien las estrategias y darle peso al riesgo están en conflicto directo a frecuencia diaria: ningún valor probado cae en la zona buscada.", {
    x: 6.95, y: 3.85, w: 5.8, h: 0.75, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 12, color: INK, lineSpacingMultiple: 1.12,
  });
  // via 3
  card(s, M, 4.7, 11.6 + 0.5 - 0.5, 1.0, "3 · Agregar más señales", [
    "Medido en la diapositiva anterior: la interacción entre canales es negativa (−3.9 puntos de retorno). Juntar información no suma, diluye.",
  ], { fs: 12, fsTitulo: 13, gapTitulo: 0.32, colorTitulo: ACC });
  remate(s, "El mecanismo es el hallazgo: aquí el sobreajuste no aparece como una curva de validación que se despega despacio, sino como ROTACIÓN. Y la rotación se paga en costos.", 5.95);
  pie(s, "Las tres vías se midieron con el mismo protocolo y el mismo presupuesto, para que sean comparables entre sí.");
  s.addNotes("Esto reorienta la tesis: el problema no está en el objetivo, ni en el presupuesto de cómputo, ni en la falta de datos.");
}

// =========================================================== 14 · protocolo
{
  const s = slideBase("Método", "Cómo evitamos engañarnos");
  const piezas = [
    ["Walk-forward con 3 pliegues", "Cada pliegue entrena con todo lo anterior y valida en el tramo siguiente, como se haría en la práctica. Cada uno cae en un contexto de mercado distinto: año alcista, pandemia y año bajista."],
    ["Embargo de 20 días", "Un hueco entre tramos para que las medias móviles del final del entrenamiento no alcancen a ver el inicio de la validación."],
    ["Banda nula", "200 carteras al azar con las mismas reglas y los mismos costos. Si el agente cae dentro de esa banda, no hay hallazgo."],
    ["Contador de configuraciones", "134 corridas registradas desde la primera, sin borrar ninguna. El Sharpe deflactado descuenta el número de intentos."],
  ];
  piezas.forEach((p, i) => {
    const x = M + (i % 2) * 6.2;
    const y = 1.5 + Math.floor(i / 2) * 2.0;
    card(s, x, y, 5.89, 1.8, p[0], [p[1]], { fs: 12, fsTitulo: 13.5, gapTitulo: 0.38 });
  });
  s.addShape(pres.ShapeType.roundRect, {
    x: M, y: 5.6, w: COL, h: 1.25, rectRadius: 0.06,
    fill: { color: NAVY }, line: { color: NAVY, width: 0 },
  });
  s.addText([
    { text: "El tramo de prueba no se ha tocado nunca.", options: { bold: true, fontSize: 16, color: WHITE, breakLine: true } },
    { text: "Todas las cifras mostradas son de validación. El test se reserva para una sola corrida definitiva, con las reglas congeladas de antemano: eso es lo que permitirá que el número final sea creíble.", options: { fontSize: 12.5, color: ICE } },
  ], {
    x: M + 0.3, y: 5.6, w: COL - 0.6, h: 1.25, isTextBox: true, margin: 0, valign: "middle",
    lineSpacingMultiple: 1.1,
  });
  s.addNotes("Este protocolo se fijó antes de entrenar. Es lo que separa un backtest convincente de uno creíble.");
}

// =========================================================== 15 · cierre
{
  const s = slideBase("Cierre", "Hallazgos y próximos pasos", { oscuro: true });
  s.addText("LO QUE YA SABEMOS", {
    x: M, y: 1.5, w: 6.0, h: 0.3, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 11.5, bold: true, charSpacing: 1.4, color: ACC,
  });
  const hallazgos = [
    "En la BVL el costo de transacción es el término dominante: se come 24 puntos del reparto igualitario y el 65% del capital en Markowitz.",
    "La caja remunerada fue la estrategia ganadora de 2013–2025. La evaluación tiene que poder premiar al agente que decide no invertir.",
    "El agente aprende a proteger capital: la menor caída de todas. Todavía no a ganar más.",
    "Agregar información no suma: cada canal aporta por separado y juntos se estorban.",
    "Los datos de la BVL necesitan validación externa, y el modelo de lenguaje, anotación humana.",
  ];
  hallazgos.forEach((h, i) => {
    s.addShape(pres.ShapeType.ellipse, { x: M, y: 1.95 + i * 0.95, w: 0.3, h: 0.3, fill: { color: ACC }, line: { color: ACC, width: 0 } });
    s.addText(String(i + 1), { x: M, y: 1.95 + i * 0.95, w: 0.3, h: 0.3, isTextBox: true, margin: 0, align: "center", valign: "middle", fontFace: BF, fontSize: 11, bold: true, color: NAVY });
    s.addText(h, {
      x: M + 0.44, y: 1.92 + i * 0.95, w: 5.5, h: 0.88, isTextBox: true, margin: 0,
      fontFace: BF, fontSize: 12, color: WHITE, lineSpacingMultiple: 1.1,
    });
  });
  s.addText("LO QUE VIENE", {
    x: 7.1, y: 1.5, w: 5.6, h: 0.3, isTextBox: true, margin: 0,
    fontFace: BF, fontSize: 11.5, bold: true, charSpacing: 1.4, color: ACC,
  });
  const pasos = [
    ["Completar los tres algoritmos", "SAC y DDPG, en implementación y pruebas"],
    ["Subir a 10 semillas", "la dispersión entre semillas hoy supera a la señal"],
    ["Pre-registrar y correr sobre el test", "reglas congeladas, una sola corrida, los 3 pliegues"],
    ["Pruebas estadísticas", "Sharpe deflactado, intervalos por semillas, banda nula"],
    ["Reforzar el modelo de costos", "spreads históricos de Bloomberg, ya descargados, para estresar el costo en los periodos de tensión"],
  ];
  pasos.forEach((p, i) => {
    const y = 1.92 + i * 0.95;
    s.addShape(pres.ShapeType.roundRect, {
      x: 7.1, y, w: 5.61, h: 0.82, rectRadius: 0.05,
      fill: { color: "2B3A72" }, line: { color: "2B3A72", width: 0 },
    });
    s.addText([
      { text: p[0], options: { bold: true, color: WHITE, breakLine: true } },
      { text: p[1], options: { color: ICE, fontSize: 11 } },
    ], {
      x: 7.3, y: y + 0.04, w: 5.2, h: 0.74, isTextBox: true, margin: 0,
      fontFace: BF, fontSize: 12, valign: "middle", lineSpacingMultiple: 1.06,
    });
  });
  s.addNotes("El resultado negativo ya es un resultado: si la corrida definitiva lo confirma, es publicable como evidencia sobre mercados pequeños e ilíquidos.");
}

pres.writeFile({ fileName: OUT }).then(() => console.log("escrito", OUT));
