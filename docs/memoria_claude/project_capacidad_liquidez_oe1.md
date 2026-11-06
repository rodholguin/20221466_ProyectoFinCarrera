---
name: project-capacidad-liquidez-oe1
description: "Resultados jul-2026 del panel mensual BVL: frecuencia oficial supera al proxy 1-is_stale en 23-34pp, capacidad del portafolio ~S/1.8MM, y conteo HÍBRIDO de acciones (BVL fecha + SMV tesorería) implementado 31-jul-2026."
metadata: 
  node_type: memory
  type: project
  originSessionId: de936975-c40d-400b-833b-b2213753a8d2
  modified: 2026-07-31T17:18:39.431Z
---

## Resultados del panel mensual oficial BVL — 2026-07-30

Panel: `data/interim/bvl_mensual.parquet`, 42,009 filas, 448 valores, **173 meses**
(2012-01..2026-06). Único hueco: 2016-03 (tabla rasterizada).
Documento completo: **docs/ejecutabilidad_y_costos_OE1.txt**.
Ver [[project-bvl-informe-bursatil]] y [[project-yahoo-volumen-confiabilidad]].

### 1. El proxy de liquidez subestimaba MUCHO (23-34 pp)
Frecuencia oficial (% sesiones con negociación) vs `1 − is_stale`:
ALICORC1 100.0/75.9 · FERREYC1 100.0/73.5 · CPACASC1 95.5/72.1 · INRETC1 95.2/63.1
· MINSURI1 95.0/64.9 · LUSURC1 90.5/56.5 · CREDITC1 90.5/58.6.
**El piso real del universo es 90.5%, no 56.5%.** Prohibir transar en todo día
`is_stale` le quitaría al agente ~1/3 de sus días operables (afecta D8).

**La decisión de universo NO se invalida** (se verificó): el orden se preserva.
Oficial de los descartados: CORAREC1 35.0%, BUENAVC1 25.0%, SAGAC1 9.1% — muy por
debajo de los elegidos, y la brecha es más nítida en dinero (SAGAC1 S/52,212/mes
vs S/2.5-44 MM). Lo que estaba mal era el NIVEL de la métrica, no el ranking.
MATIZ: frecuencia ≠ profundidad. CASAGRC1 tiene 100% de frecuencia con solo
S/1.96 MM/mes.

### 2. Capacidad: el binding constraint es BCP, y la escala es chica
Monto negociado por día operado (mediana): INRETC1 2,175,409 · ALICORC1 2,141,411
· FERREYC1 1,405,830 · CPACASC1 823,902 · MINSURI1 657,179 · LUSURC1 311,757 ·
**CREDITC1 131,322** (el más delgado en DINERO pese a ser el banco más grande;
flotante mínimo, rotación mensual 0.010%).
Con salida en 20 sesiones al 10% de participación: posición tope S/262,644 =>
**~S/1.84 MM de cartera equiponderada**. Declarar como prueba de concepto a
escala de inversionista individual/family office, NO institucional.
OJO METODOLÓGICO: el monto diario acota el TRADE, no el portafolio; el puente
exige un supuesto de salida explícito.

### 3. Conteo de acciones: oficial vs pipeline son DEFINICIONES distintas
Contraste: CREDITC1 |dif| mediana 0.00% (máx 25.85%), ALICORC1 0.00% (máx 10.00%),
INRETC1 2.19%.
- **Tesorería (Alicorp)**: verificado en EEFF — capital 847,192 constante con
  cartera 0 → −84,719 (2022-12), y el capital recién baja a 762,473 en 2024-03.
  El pipeline resta tesorería de inmediato; la BVL cuenta acciones EMITIDAS.
  **Para EPS el pipeline es MEJOR que el oficial.** (Corolario: la
  `capitalizacion` de la BVL sobrestima cuando hay tesorería.)
- **Fecha de reconocimiento (BCP)**: el pipeline usa el capital del balance y la
  BVL lista después → el pipeline se adelanta. Medido: **15 de 54 trimestres
  (28%)**, siempre en la misma dirección, +2.26% a +25.85%; el desfase NO es
  siempre de 1 trimestre (en 2021 duró 3). Sesgo RECURRENTE ANUAL (BCP capitaliza
  cada año) → artefacto con periodicidad que la normalización causal de OE1 NO
  elimina y que un agente DRL podría aprender como estacionalidad real.

  **[C] CONTEO HÍBRIDO IMPLEMENTADO Y VERIFICADO (2026-07-31)**, antes de la
  corrida R3→R6 (después habría obligado a repetir R4-R6). Fórmula:
  `acciones = emitidas_BVL(mes de cierre) − |tesorería SMV 1D0711| / nominal`,
  sustituyendo SOLO la rama capital÷nominal; precedencia schedule (InRetail) >
  override (Minsur) > híbrido, intacta. Código: `fundamentals_client._bvl_mensual`
  + `_shares_listed_bvl` + rama general de `compute_shares_earnings`.
  Regresión: CREDITC1 cambia 16/83 periodos (no 15 — el 16º es 2016-03, el mes del
  PDF rasterizado, que ahora sí tiene valor por ffill); el P/E baja igual en 14
  (2013-06 y 2014-03 ya tenían eps_ttm NaN por un hueco preexistente de la utilidad
  de BCP en 2013). ALICORC1 0 periodos >1%. Criterios de aceptación al dígito.
  **[B] DESCARTADA por innecesaria**: [C] corrige en vez de señalizar, así que
  marcar `pe_reliable=0` perdería P/E válido.
  Residuos: 2005-2011 caen al cálculo del balance (sin efecto: sin precio no hay
  P/E); 2016-03 es ffill (exacto, el conteo es escalonado, pero derivado);
  `bvl_mensual.parquet` es ahora DEPENDENCIA de R4 (si falta, avisa y cae al
  cálculo anterior, no descarga PDF). Detalle: docs/ejecutabilidad_y_costos_OE1.txt
  §8.3; también en pipeline_extraccion_datos.txt §3.10.3 y riesgos §R4.
  El P/E NO exige re-descargar R4: `compute_ratios` se evalúa al construir el panel.
- **REGLA (superada por [C])**: se creía que el oficial servía solo como capa de
  VALIDACIÓN porque reemplazarlo metería el error de tesorería. El híbrido muestra
  que la disyuntiva era falsa: la BVL aporta la FECHA y el SMV el AJUSTE.

### 4. InRetail CORREGIDO en config.yaml
Serie oficial: 2012-09 79,807,319 (pre-IPO) | 2012-10 **102,807,319** (IPO) |
2022-04 108,746,887 (follow-on). Reemplaza la reconstrucción de 100,556,000, que
erraba **−2.19%**, algo POR ENCIMA del "≤2%" declarado. Limitación ELIMINADA.
Propagado ya a riesgos_transversales_datos.txt y
pendientes_implementacion_universo.txt. Ver [[project-pe-dy-viability]].

### 5. Spread observado (corrige un supuesto del plan OE1)
Las puntas SÍ son observables (`buy`/`sell` en listLastValue): ida y vuelta
**8 a 220 pbs**. La grilla de break-even 0/25/50/100 pbs SE QUEDA CORTA → ~250.
Ver [[project-oe1-plan-iliquidez]].
