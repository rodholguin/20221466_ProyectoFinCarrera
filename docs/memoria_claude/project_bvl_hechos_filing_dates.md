---
name: project-bvl-hechos-filing-dates
description: BVL POST /v1/corporate-actions INTEGRADO — known_date usa fecha real de presentación de EEFF (registerDate) con fallback al lag fijo
metadata: 
  node_type: memory
  type: project
  originSessionId: 509e4789-5c90-4c84-9c56-2f5ffe2957ed
---

**INTEGRADO jul-2026** en `fundamentals_client` (`_load_filing_dates`,
`_bvl_fetch_hechos`, `_known_date(filing_dates)`, `fetch_smv(use_filing_dates=True)`).
known_date = registerDate real (+1 día si registró >=15:00 Lima; primera
divulgación; descarta lag<0 o >150d) con fallback al lag fijo. Cobertura real
~2018-2025 (27-30/84 períodos por activo); pre-2018 usa lag. Parquets fund_*_smv
y dataset_unificado REGENERADOS (scripts/regen_fund_known_dates.py +
run_r6_integration.py); notebooks re-ejecutados. Verificado en panel:
CREDITC1/CORAREC1 Q4-2023 activan ~5 semanas antes (24-25 ene vs 1 mar); BVN Q4
sin cambio (presenta en deadline). Hechos crudos cacheados en
data/raw/smv_cache/bvl_hechos_{rpj}_2005_2025.json.

**FALLBACK calibrado a {Q1-Q3:40, Q4:60}** (antes 45/60). Barrido empírico de
look-ahead sobre 109 lags reales Q1-Q3: 30d→33% de casos, 35d→4%, 40d→4%, 45d→1%;
máx NORMAL (sin COVID) = 35d, y con >=35d hay 0/95 look-ahead. Se eligió 40
(máx normal 35 + ~5d colchón; recorta warm-up vs 45) uniforme; se DESCARTÓ
esquema por-año (2017). Los únicos violadores son prórrogas de emergencia
documentadas: COVID Res.033-2020-SMV/02 (Q1-2020 30-abr→31-jul, ~+3 meses) y
El Niño Costero Res.014-2017-SMV/01 (confirmada como concordancia oficial en RSMV
016-2015; nº exacto de días no recuperado, queda en SIL SMV/El Peruano).
Deadlines legales base verificados textual (RSMV 016-2015 art.5/11). Justificación
completa en doc riesgos §3(a.1/a.2/a.3).

RESUELTO jul-2026 (sesión de validación). El endpoint POST
`https://dataondemand.bvl.com.pe/v1/corporate-actions` ("Hechos de Importancia")
SÍ funciona y entrega la FECHA REAL de presentación de cada EEFF ante el mercado.

**Payload correcto** (capturado del frontend Angular de bvl.com.pe con Claude in
Chrome — imposible desde Claude dispatch por falta de red):
`{"rpjCode":"B30006","page":1,"size":15,"search":"","startDate":"2026-06-01","endDate":"2026-07-31"}`
- Se identifica por **rpjCode** (no companyCode ni nemónico). startDate/endDate
  OBLIGATORIAS yyyy-MM-dd. El 500 previo ('Regex string must not be null!' / 'text')
  era por payload equivocado (LocalDate.parse(null)).
- Respuesta paginada `{totalElements,totalPages,first,last,content[]}`. Cada item:
  **registerDate** (timestamp real de registro = fecha buscada), sessionDate,
  observation, session, documents[{path->PDF}], codes[{codeHHII,descCodeHHII}].
- Los EEFF se filtran por `observation` (~"Información Financiera Intermedia" /
  "Reporte de Resultados"), no por `codes` (vienen vacíos en muchos).

**Hallazgo clave — VALIDADO en los 5 emisores × 6 trimestres (30 puntos)**, usando
el EEFF intermedio INDIVIDUAL (Tipo=I, el que consume el pipeline). Los 5 usan su
rpjCode de SMV directamente (== BVL): CREDITC1 B80005, BUENAVC1 B20003, ALICORC1
B30006, SAGAC1 014313, CORAREC1 CI0003. El lag fijo actual (45d Q1-Q3 / 60d Q4 en
`fundamentals_client._FILING_LAG_DAYS`) es causalmente seguro: holgura mínima
global = **0 días, NO hay look-ahead en ningún caso**. Pero demora los
fundamentales hasta ~5 semanas y el margen varía mucho por emisor:
- CREDITC1 / CORAREC1: presentan +18..+26d (bancos/mineras, muy temprano) → el lag
  fijo los retrasa +19..+37d.
- ALICORC1 / SAGAC1: +29..+46d → conservador ~2 semanas.
- BUENAVC1: Q4 cae EXACTO en +60d (regla NYSE) → confirma que la corrección Q4→60d
  era imprescindible (un +45 ahí = −14d de look-ahead).

Conclusión: SÍ se puede reemplazar el lag fijo por la fecha de presentación REAL
(registerDate), con fallback al lag fijo cuando falte el hecho. Mejora la
precisión temporal (point-in-time) sin cambiar los valores reexpresados.

Script funcional (los 5 + tabla de holguras): `scripts/probe_bvl_hechos.py`
(`fetch_facts`, `filing_dates((ejercicio,trim)->fecha)`). PENDIENTE de decisión
del usuario: integrar `filing_dates` en `fundamentals_client` para usar
registerDate como known_date. Ver [[project-riesgos-datos-pendientes]] y
[[project-bvl-dataondemand]].
