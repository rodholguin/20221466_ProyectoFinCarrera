---
name: project-bvl-informe-bursatil
description: "Informe Bursátil Mensual BVL (PDF, 173 informes 2012-2026): fuente OFICIAL de volumen, monto negociado, frecuencia y acciones en circulación por emisor y por mes. Parser por texto validado 7/7 en 2013/2019/2025."
metadata: 
  node_type: memory
  type: project
  originSessionId: de936975-c40d-400b-833b-b2213753a8d2
  modified: 2026-07-30T19:55:23.857Z
---

## Informe Bursátil Mensual de la BVL — evaluado 2026-07-30

Buscado como reemplazo del volumen de Yahoo, que resultó parcial
(ver [[project-yahoo-volumen-confiabilidad]]).

### Acceso
- URL predecible: `https://documents.bvl.com.pe/pubdif/infmen/M{YYYY}_{MM}.pdf`
- **Cobertura verificada por HEAD: 173 informes.** 2012 completo salvo junio;
  2013-2025 los 12 meses de cada año; 2026 hasta junio. Tamaño 0.6-2.4 MB,
  ~54 páginas (2013) a ~64 (2025).
- Índice de publicaciones: `https://documents.bvl.com.pe/merc_publi_boletindiario.html`

### Tabla "Renta Variable — Valores Negociados": 20 columnas POR EMISOR Y POR MES
`acciones_en_circulacion | valor_nominal | capitalizacion_bursatil |
valor_contable | ISIN | nemónico | CANTIDAD NEGOCIADA (acciones) |
MONTO EFECTIVO S/ | MONTO EFECTIVO US$ | % del total | N° de operaciones |
FRECUENCIA (%) | apertura | cierre | máxima | mínima | promedio | C.M.T. |
rotación | rendimiento mensual`

Otras secciones útiles: Ranking de valores (por frecuencia / operaciones / monto /
capitalización), dividendos y fechas (Acciones-Dividendo), clasificación de riesgo
por emisor, tabla de valores referenciales para operaciones de reporte,
indicadores económicos, y un acumulado semestral en el Anexo Estadístico.

### Parseabilidad — RESUELTA
El formato de columnas es IDÉNTICO en 2013, 2019 y 2025. Lo único que cambia es
que los PDF antiguos NO traen líneas de tabla, así que `pdfplumber.extract_tables`
falla en ellos. **Solución: parsear por TEXTO anclando en el ISIN** (regex ISIN
estándar `^[A-Z]{2}[A-Z0-9]{9}\d$` — NO restringir a "PE", InRetail es holding
panameño con ISIN `PA...`). 4-5 tokens antes del ISIN, 14-16 después.
Script validado: `scripts/probe_infmen_parser.py` → **7/7 activos en 2013, 2019 y
2025**. pdfplumber está instalado; no hay poppler (el Read de PDF no funciona).

### Validaciones que ya salieron de las 3 muestras
- Acciones en circulación coinciden EXACTO con el snapshot BVL de `config.yaml`
  en 2025-06: FERREYC1 946,063,288 · CPACASC1 423,868,449 · MINSURI1 961,000,840
  · INRETC1 108,746,887 · LUSURC1 486,951,371.
- **InRetail: el tramo pre-2022 se puede CERRAR.** La BVL reporta 102,807,319
  acciones en jun-2013 y jun-2019. Nuestro config usa 100,556,000 reconstruido por
  razón de Capital Emitido, con error declarado ≤2% y rango real [100.6M, 102.9M].
  El oficial cae dentro de ese rango, en el extremo alto → se puede reemplazar la
  reconstrucción por el dato oficial y ELIMINAR esa limitación.
  Ver [[project-universe-decision]] y [[project-pe-dy-viability]].
- El conteo de acciones NO es constante: ALICORC1 847,191,731 (2013 y 2019) →
  617,618,735 (2025); CREDITC1 3,102,896,755 → 10,217,386,717 → 12,973,174,634;
  FERREYC1 803,234,873 → 975,683,029 → 946,063,288. Sirve de validación cruzada
  independiente del cálculo actual (SMV Capital Emitido ÷ nominal).
- **`FRECUENCIA` es la medida OFICIAL de liquidez** (% de sesiones con negociación)
  y es la métrica correcta, superior a nuestro proxy `1 − is_stale` (que mide
  % de días con precio distinto y por tanto SUBESTIMA la negociación).

### Limitación
Granularidad MENSUAL, no diaria. Para el tope de capacidad de OE1 alcanza (monto
mensual ÷ sesiones = monto diario medio, y `frecuencia` da los días operados).
NO reemplaza una serie diaria de volumen, que sigue sin existir salvo el
`listLastValue` del último día.
