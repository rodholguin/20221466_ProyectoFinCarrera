---
name: project-bloomberg-extraccion
description: "Estado de la extracción Bloomberg (05, 07, 16 y 19-sep-2026): P0 cerrado; A1 (fechas de anuncio) CERRADO vía EVTS; faltan el par OR/MR con Dts=S, el índice TR y LQA."
metadata: 
  node_type: memory
  type: project
  originSessionId: 81b0ed4e-b520-46f7-8270-b9d21c8b235d
  modified: 2026-09-19T22:49:14.119Z
---

**Estado real: `docs/estado_extraccion_bloomberg.txt`** (el RESULTADO), §7 es la
sesión del 19-sep. El plan original sigue en `docs/plan_extraccion_bloomberg.txt`.
Checklist operativo: `docs/checklist_bloomberg_20260919.txt`.

**Encuadre del acta §E, no se negocia:** volcado ÚNICO a parquet con fecha,
NUNCA una dependencia viva. El cierre autoritativo sigue siendo la BVL;
Bloomberg es capa de validación y enriquecimiento.

### Las dos reglas que ya se pagaron caro
- **`Dts=S` en CADA bloque de BDH.** Con `Dts=H` hay una sola columna de fechas
  compartida y los demás bloques la ASUMEN. Ya causó DOS desalineaciones.
- **`Fill=#N/A`, nunca `Fill=P`** (142 días fantasma en el grid del 05-sep).
- Pegar como VALORES antes de salir: los archivos guardados NO tienen fórmulas,
  así que una fórmula que funcionó no se puede recuperar después.

### Ya bajado — NO repetir
`data/raw/bloomberg/` (ignorado en git):
- `grid_ul1wocu2.xlsx` (05-sep): **P0 COMPLETO**. Puntas, volumen, turnover,
  OHLC de los 7 **2011→2026 al 100%**, flotante diario, EQY_SH_OUT, NUM_TRADES
  (solo desde 2014-10).
- `fundamentales.xlsx` (07-sep): era la versión MR. Su bloque "CPACASC1" NO era
  Pacasmayo — descartado.
- `fundamentales_or_mr_indice_20260916.xlsx`: par OR/MR x7 + **SPBLPGPT diario
  2011→2025-08-29**. OJO: **las DOS hojas usaron `Dts=H`**; solo LUSURC1 quedó
  desalineado (22/62 trimestres casan corridos) pero los otros 6 salieron bien
  POR SUERTE.
- **`ern_evts_20260919.xlsx`** (19-sep): ERN + EVTS de los 7. **A1 CERRADO.**
- **`eco_calendario_macro_20260919.xlsx`**: calendario macro con sorpresas.
- **`pantallas_cdr_hds_msci_20260919.docx`**: 10 capturas (CDR 2026, HDS x7,
  buscador MSCI).

### A1 CERRADO (19-sep) — la fecha de anuncio
- **NO sale por Excel**: `ANNOUNCEMENT_DT` (BDP y BDH) y
  `EARN_ANN_DT_TIME_HIST_WITH_EPS` (BDS) dan los tres `#N/A Review`. Bloomberg
  no cubre esos campos para la BVL. **No volver a intentarlo.**
- **SALE POR `EVTS <GO>`**: 428 earnings release de los 7, 2011-2026.
  Cobertura efectivamente completa — EVTS llega a 2011 y ERN (que solo cubre
  desde 2015-Q3) tapa exactamente sus huecos. De regalo: 214 earnings calls,
  76 ex-dividendo, 61 juntas, **5 operaciones de M&A** (alimentan R5).
- **EVTS es pantalla de EMPRESA, no de valor**: escribir CPACASC1 devuelve
  CPACASI1 y está bien — mismo emisor, mismos EEFF, mismo hecho.

### LAS HORAS DE EVTS NO SE USAN — medido contra el registerDate de la BVL
  2011-2016  redondas y repetidas (11:00, 12:00, 17:00) = RELLENO, no dato
  2018-2020  reales y EN HORA DE LIMA (coinciden a ±18 min en 5 de 6)
  2021-2025  hora en que BLOOMBERG CAPTURÓ, 5-34 h DESPUÉS del hecho; al caer
             de madrugada CORRE LA FECHA uno o dos días
>> El `known_date` se queda con la BVL. EVTS sirve para CONFIRMAR que el
   anuncio ocurrió (62-96% coinciden a ≤1 día), no para fecharlo.
>> **ECO SÍ está en hora de Lima**: las tasas del BCRP figuran a las 18:00.

### FREE FLOAT: la tesis lo cita mal (ver ejecutabilidad_y_costos_OE1 §6.1)
**El 2.66% del BCP es el valor del 2011-01-03**, el primer día de la serie. Hoy
2.26%, rango histórico 1.93%–21.70%. Y no es estático en ninguno: **LUSURC1 cae
de 25.99% a 2.86%** con la OPA de 2019. El cuadro de capacidad usa valor fijo y
hay que rehacerlo por tramo. Además el flotante NOMINAL sobreestima al EFECTIVO
(~14% de Pacasmayo está en AFPs que no rotan).
**Dato que dimensiona todo: Luz del Sur negoció el 18-sep S/13,830 EN TODO EL
DÍA; la posición 1/7 de la cartera son S/257k = 18 días de volumen.**

### Pendiente para la próxima visita
1. **OR/MR con `Dts=S`, LOS 7, en AMBAS hojas** — una fórmula por ticker.
   Control: 62 trimestres y CADA BLOQUE CON SU COLUMNA DE FECHAS.
2. **A3 índice**: `SPBLPGPT` + `TOT_RETURN_INDEX_GROSS_DVDS`, y **`M7PE Index`**
   (MSCI Peru Net PEN, en soles, otro proveedor). Si M7PE coincide con SPBLPGPT
   en 2011-2015, el empalme del IGBVL es de retorno total.
3. **MEMB de verdad**, sobre `MXPE Index` (lo del 19-sep fue el buscador).
4. **LQA** — parámetros en estado_extraccion §7.7: CREDITC1 45,918 acc,
   horizonte **1 día**, confianza 95%, volumen/vol/spread en DEFAULT.
   Referencia: el simulador cobra hoy 134 pbs de ida en CREDITC1.
5. `CDR PE` salió solo 2026 → probablemente no vale otra visita.

### Si el add-in de Excel se cae (pasó el 19-sep)
`=BDP("ALICORC1 PE Equity","NAME")` es el test de 5 segundos. Si falla:
revisar que el **TERMINAL siga logueado** (se desloguea por inactividad), luego
`DAPI <GO>` que gobierna el add-in y permite repararlo.

**Why:** el tiempo de terminal es escaso y la tentación es rebajar lo que suena
importante en vez de lo irreemplazable; sin registro de lo conseguido, la
próxima visita se gasta repitiendo el P0.
**How to apply:** antes de agregar cualquier índice o factor al panel, pasarlo
por `probe_macro_exposicion.py` sobre el universo vigente — el mismo tamiz que
eliminó el oro y rechazó el estaño. Ver [[project-macro-factores-validacion]] y
[[project-capacidad-liquidez-oe1]].

## SESIÓN 26-sep — LQA CERRADO; OR/MR BLOQUEADO; FALTA DOCUMENTAR (§8 de estado_extraccion)
- **Excel da `#N/A Review` en TODO, hasta `=BDP(...,"NAME")`** → límite/bloqueo de la cuenta de la sala;
  FA tampoco deja exportar; HELP HELP solo muestra contactos (se abrió BHRQ). OR/MR SIGUE PENDIENTE.
  OJO: el "#N/A Review" del 19-sep en ANNOUNCEMENT_DT pudo ser ESTO y no "BVL no cubierta".
- **LQA: "Volumen de liq (MM)" = MILLONES DE SOLES** (la ayuda dice "monto absoluto"; 45918 saturó a
  10000 pbs/252 días). Horizonte 252 = artefacto de "Coste obj" ~0; LEER SOLO EL COSTO.
  Costo LQA = desviación vs precio medio, SIN comisión → comparar con NUESTRO MEDIO SPREAD.
  LQA no cubre 2018; sí 2020-12-31.
      LUSURC1 S/20k  2026   118.6 / 327.2 (95%)   vs medio spread 110 → coincide
      LUSURC1 S/260k 2026   340.3 / 897.1         ADV ~2,306 acc
      LUSURC1 S/260k 2022   934.8 / 2400.2        ADV ~1,570 acc
      LUSURC1 S/260k 2020-12 193.6 / 628.4        ADV ~169k acc (volumen de la OPA)
      CREDITC1 S/260k 2026   57.6 / 168.2  · S/1.8MM 2026  125.0 / 337.6
- **HALLAZGO: costs.py usa spread CONSTANTE (snapshot 2026-07-27) e impacto = 0.** La serie P0 muestra
  LUSURC1 monto diario S/240-270k (2012-14) → S/13-15k (2024-26), spread 70-105 → 345-500 pbs
  ("Luz del Sur se muere", post-OPA); CREDITC1 al revés (hoy la más líquida). Hace falta: serie de
  puntas (5.3, ahora NECESARIO) + TÉRMINO DE IMPACTO ∝ σ·√(Q/ADV) calibrado con los 6 puntos LQA.
  Top of book LUSURC1 hoy: "1000 x 100" (100 acc en el ask).
- Capturas en la RAÍZ del repo como "WhatsApp Image 2026-09-26 at 3.xx.xx PM.jpeg" (3.17.23 CREDITC1
  0.26 · 3.17.43 CREDITC1 1.80 · 3.18.12 LUSURC1 0.26 · 3.26.01 LUSURC1 2022 · 3.29.05 LUSURC1 2020):
  renombrar y mover a data/raw/bloomberg/.
