---
name: project-riesgos-datos-pendientes
description: Registro de riesgos/puntos frágiles transversales de datos (R3-R6) para continuar — en docs/riesgos_transversales_datos.txt
metadata: 
  node_type: memory
  type: project
  originSessionId: b669a5ee-2c73-42c3-aeb4-8ff73952051e
  modified: 2026-07-30T05:35:11.622Z
---

Revisión transversal de puntos frágiles/riesgo de datos (mercado R3, fundamentales
R4, sentimiento R5, integración R6), generada jul-2026 para continuar la próxima
sesión. Documento completo: **docs/riesgos_transversales_datos.txt**.

Convención acordada: cada punto débil que se resuelva se anota y se modifica
docs/riesgos_transversales_datos.txt (marcar [RESUELTO]).

ILIQUIDEZ (hallazgo jul-2026, ahora el riesgo #1): medida con flag `is_stale`
(close==día previo) sobre crudos BVL, la iliquidez es universal y severa —
precios distintos en 13 años: SAGA 2.2%, CORAREC 5.5%, CREDITC1 13%, BVN 15.9%,
ALICORP 16.7% (stale 24-96%). `is_no_trade` (0-5%) la SUBCUENTA (la BVL arrastra
precio de referencia sin marcarlo). Dos fenómenos distintos: staleness (universal)
vs distorsión de nivel por free-float (solo BCP). PENDIENTE: decisión de universo
— reemplazar SAGA/CORAREC (<10% distintos) por INRETC1/CASAGRC1 (retail) y
CPACASC1/LUSURC1 (construcción/utilities); BVL-nativos topan ~20-25%, los líquidos
(BAP/SCCO) son NYSE (fuera de premisa). Banderas `is_stale` y `pe_reliable`
agregadas al panel (build_dataset). SAGA 2019Q4 = escisión Inmob. SIC (no AL),
P/E marcado pe_reliable=0. BCP: P/E NO enmascarado (normalización por-activo OE1
disuelve el nivel). Doc riesgos R3/R4 actualizado.

Prioridades:
1. [HECHO jul-2026] Verificado el lag de known_date vs plazos regulatorios SMV
   (RSMV 016-2015): Q1<=30abr, Q2<=31jul, Q3<=31oct, Q4<=15feb local / 60 días
   para emisores en el extranjero (BVN/NYSE). El +45d fijo introducía look-ahead
   en Q4 (~15 días para BVN). Corregido: _FILING_LAG_DAYS={1:45,2:45,3:45,4:60}
   en fundamentals_client. Parquets fund + dataset_unificado + ambos notebooks
   regenerados/re-ejecutados (0 errores). Docs pipeline §3.5, hallazgos R4 y
   riesgos actualizados. Siguiente look-ahead abierto: reexpresado vs point-in-time.
2. Modelado de costos/iliquidez en OE1 (crítico para credibilidad del trading).
3. Declarar en limitaciones: selección/supervivencia, techo de la señal de
   sentimiento. NOTA: el riesgo "reexpresado vs point-in-time" fue REEVALUADO
   jul-2026 y es de BAJO impacto: el servicio SMV preserva cada filing original
   y el pipeline lee columnas propias (no comparativas), así que el panel ya es
   point-in-time (verificado: fund_BUENAVC1 2013 patrimonio = original 2,613,666,
   no el reexpresado 3,547,114). Empíricamente ~82% de cifras no cambian; swings
   de ROE/ROA/margen solo en casos raros (BVN 2013 utilidad +37k→−107k, cambia de
   signo). Apalancamiento (D/E,D/A) robusto. Residual: acciones/dividendos/splits
   sí son snapshot actual de BVL. Ver [[project-bvl-hechos-filing-dates]] y doc
   riesgos §3b.
   DECISIÓN jul-2026 (modelo temporal): panel de fundamentales "first-reported,
   INMUTABLE (mono-vintage)" — cada trimestre entra una vez con su valor original
   en su known_date y nunca se revisa. Causalmente seguro y simple; costo =
   imperfección de completitud (tras una reexpresión el feature histórico no la
   refleja), impacto ~nulo porque ese trimestre ya salió de la ventana/TTM.
   TRABAJO FUTURO: panel BITEMPORAL (point-in-time por vintage). Documentado en
   riesgos §3(b).
4. Barato: ancla financiera para CORAREC1 en el query de MediaCloud (peor ruido
   temático, R5 §5.3); congelar parquet crudos con fecha de extracción.
5. Considerar feature de antigüedad de fundamentales (análoga a days_since_news).

## Actualización jul-2026 (sesión de implementación del nuevo universo)

CRITERIO DE REGISTRO (indicación del usuario): cuando un riesgo deja de aplicar, NO
se borra el item — se ANOTA QUÉ MITIGACIÓN se aplicó, qué parte queda abierta y cuál
es el límite de la mitigación. Ver [[feedback-registro-mitigacion-riesgos]].

- **Riesgo #1 ILIQUIDEZ — mitigación 2 aplicada (selección de universo)**: se
  reemplazaron los 3 activos que lo hacían inmanejable. % de días con precio distinto
  (=1−is_stale, 2012-2025): SALEN SAGAC1 4.1%, CORAREC1 20.8%, BUENAVC1 23.7%;
  ENTRAN FERREYC1 73.5%, CPACASC1 72.1%, MINSURI1 64.9%, INRETC1 63.1%, LUSURC1
  56.5%; SIGUEN ALICORC1 75.9%, CREDITC1 58.6%. **El piso del universo subió de 4.1%
  a 56.5%.** Mitigación 1 (previa) = banderas is_no_trade e is_stale. LÍMITE: ningún
  BVL-nativo pasa de ~74%. SIGUE ABIERTO y es lo crítico: costo/impacto/slippage en
  OE1 (prioridad 2 de arriba) — el cambio de universo mejora el insumo, no sustituye
  el modelado.
- **Ruido temático R5 — mitigación PARCIAL y colateral**: CORAREC1, el peor caso y el
  único sin ancla financiera, salió del universo, así que ese query ya no alimenta el
  panel. NO cierra el riesgo: el mecanismo (resúmenes de índice, homonimia) sigue
  vigente y los 5 queries NUEVOS están sin auditar. Al correr R5 hay que medirles el
  ruido con el criterio de R5 §5.3 y, si aparece, aplicar la mitigación pendiente
  (ancla financiera / filtro de relevancia con el LLM).
- **Artefactos de conteo de acciones (`pe_reliable`) — mecanismo conservado**: los
  casos concretos de SAGAC1/CORAREC salieron del panel, pero `_PE_ARTIFACT_PERIODS`
  sigue en build_dataset como guarda para eventos societarios no-AL futuros. Los dos
  casos nuevos se resolvieron por CONFIGURACIÓN y no con la bandera: INRETC1 conteo
  por tramos (error del P/E pre-2022Q2 de ~8% → ≤2%; el escalón del EPS en 2022Q2 NO
  se marca porque un follow-on diluye el P/E trailing por definición, a diferencia de
  una escisión) y MINSURI1 override con el total económico. PENDIENTE al correr R4:
  verificar que CPACASC1/FERREYC1/LUSURC1/MINSURI1 no traigan eventos no-AL nuevos.
- **NUEVO riesgo detectado Y cerrado — §3(a.4) look-ahead por tipo de EEFF**: el
  known_date real salía del hecho "Intermedia Individual" aunque INRETC1 consume el
  CONSOLIDADO, que se divulga 9-19 d después (mediana 14) en 30/30 trimestres.
  Mitigación: patrón por tipo (`_EEFF_OBS_RE` mapa I/C) y `_load_filing_dates(tipo=)`.
  Se descartó además la hipótesis de que la individual adelantara la información
  (R² de cambios = 0.007; 14/53 trimestres con signo opuesto).
  Evidencia: scripts/probe_inretail_i_vs_c.py.
- **Riesgo NUEVO declarado**: el tramo pre-2022Q2 de acciones de INRETC1 es
  RECONSTRUIDO por razón de Capital Emitido (real en [100.6M, 102.9M]) → error del
  P/E ≤2%, no cero. Ver [[project-pe-dy-viability]].

Aclaración registrada (el usuario lo preguntó): el ancla SEC constante de BVN NO
se eliminó; lo invalidado fue la reconstrucción por factor de splits (método
distinto). Ver [[project-pe-dy-viability]] y el encabezado del txt.
