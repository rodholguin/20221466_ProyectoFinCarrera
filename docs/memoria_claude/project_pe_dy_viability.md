---
name: project-pe-dy-viability
description: "Decisión sobre viabilidad de P/E y Dividend Yield en fundamentales (R4) — no implementados, documentado en docs/pipeline_extraccion_datos.txt §3.10.1"
metadata: 
  node_type: memory
  type: project
  originSessionId: fc61a441-3c31-4ddc-a094-c09f8e0eaee6
  modified: 2026-07-30T04:47:07.596Z
---

## P/E y DY: evaluados y descartados (jun-2026), con una excepción acotada

El usuario propuso derivar P/E vía valor nominal SMV o memorias anuales,
validando contra BAP (BCP) / BVN (Buenaventura). Se investigó (sin
implementar) y se concluyó **viabilidad baja** para los 5 activos:

- Valor nominal no está en el WSDL SMV (solo el monto de Capital Emitido,
  no el número de acciones); requeriría investigación externa por empresa
  y puede cambiar en el horizonte.
- Memorias anuales viven en un portal/sistema distinto al WSDL — sería un
  sub-proyecto nuevo (descubrir endpoint + parsear ~70 PDFs), no un
  complemento de R4.
- `obtener_CambiosPatrimonio` (operación SMV no explorada) no respondió en
  una prueba en vivo tras >10 min — no se pudo evaluar ni confiar en ella.
- `yfinance.get_shares_full()` (probado): cobertura parcial (desde
  2016-2019, no 2012-2025 completo) y valores duplicados/inconsistentes en
  la misma fecha — no es una serie limpia.
- BAP es el holding Credicorp (BCP + Pacífico + Mibanco + Prima AFP), no
  BCP solo — cross-check débil, solo orden de magnitud. BVN sí es la misma
  entidad que Buenaventura (cross-check más sólido), pero igual sin fuente
  de acciones confiable. ALICORC1/SAGAC1/CORAREC1 no tienen ningún proxy.

**Camino acotado SÍ viable (no implementado):** para CREDITC1 se podría
reconstruir acciones en circulación históricas dividiendo un ancla actual
por el factor de split YA VALIDADO en `corporate_actions.py` (R3) — más
barato que valor nominal/memorias, pero solo cubre 1 de 5 activos.

**DY es distinto:** ya casi disponible para CREDITC1/ALICORC1 sin tocar SMV,
porque `corporate_actions.py` (R3) ya descarga dividendos por acción en PEN.
No implementado todavía, pero de esfuerzo bajo (a diferencia de P/E).

**Decisión final:** no se implementa P/E ni DY para ninguno de los 5
activos por ahora. Documentado en `docs/pipeline_extraccion_datos.txt`
sección 3.10.1 con el detalle completo del análisis.

## ACTUALIZACIÓN jul-2026: sí hay fuente de acciones (revierte lo anterior)

Se re-sondeó la BVL y se VALIDÓ el ancla de acciones (usuario pidió validar
antes de implementar). Resultado que revierte la conclusión de arriba:

1. La BVL SÍ expone acciones en circulación (`quantity`) en
   /v1/issuers/{cc}/value → listStock (snapshot semanal). Ver
   [[project-bvl-dataondemand]] y scripts/probe_bvl_capital.py.
2. El ancla ACTUAL coincide AL DÍGITO entre BVL, SMV (Capital Emitido÷nominal)
   y yfinance para 4/5 (CREDITC1 triple-match 12,973,174,634). BUENAVC1 no
   (SMV lo reporta en USD; ahí el ancla es la BVL 274.89M).
3. **La serie histórica correcta es SMV Capital Emitido ÷ nominal** (cuenta
   1D0701; BCP usa 1F3301 "Capital social"), ya descargada 2005-2025 trimestral
   en data/raw/smv_cache. Captura splits Y aumentos/reducciones de capital.
4. **El "camino acotado" por factor de splits de arriba QUEDA INVALIDADO**: la
   validación (scripts/validate_shares_anchor.py) mostró que reconstruir por
   splits erra 33-75% históricamente porque estas empresas tuvieron cambios de
   capital ≠ acciones liberadas (ALICORC1 redujo 847M→569M en 2024; CREDITC1
   creció por capitalizaciones; SAGAC1 subió y bajó no-monótono).

Con esto P/E y DY son IMPLEMENTABLES para los 5 sin EODHD (BUENAVC1 con ancla
BVL en vez de SMV). No implementado aún; pendiente decisión del usuario sobre
implementar y/o corregir docs (hallazgos_fundamentales_R4 §5.8, pipeline §3.10.1).

## Variabilidad del conteo 2012-2025 y resolución de BUENAVC1 (SEC 20-F)

Medido (scripts, cache SMV, cuenta capital ÷ nominal), variación del conteo de
acciones DENTRO del horizonte de mercado 2012-2025:
- CREDITC1 +318% (3.10bn→12.97bn, 13 niveles) — capitalizaciones sucesivas
- ALICORC1 +48.7% (847M→569M, 5 niveles) — reducción de capital 2024
- SAGAC1   +59.5% (250M→156.7M, 2 niveles)
- CORAREC1 +5.7%  (897M→890M, pico 941M, 3 niveles) — casi plano
- BUENAVC1 +8.3% en el capital USD, PERO ese vaivén NO es emisión de acciones.

→ Constante sería un error grave para los 3 primeros; por eso la serie SMV
trimestral es imprescindible para ellos.

**BUENAVC1 resuelto con rigor vía SEC (20-F, EDGAR CIK 1013131):** el conteo de
acciones comunes fue PLANO en todo 2012-2025 —emitidas 274,889,924, tesorería
21,174,734, en circulación 253,715,190— idéntico en los 20-F de 2013, 2014,
2015, 2020, 2021, 2022, y el quantity BVL 2026 sigue siendo 274,889,924. El
capital SMV en USD (813→750 miles) se mueve solo por traducción a moneda
funcional USD (adoptada ~2011-2012), no por acciones. Por tanto el ancla
constante de BVN es un HECHO auditado, no un supuesto. Emitidas 274.89M
(consistente con la base "emitidas"=Capital Emitido del SMV de los otros 4) o
en circulación 253.72M (neto de tesorería, correcto para market cap/P/E).
BVN además reporta utilidad en USD y cotiza en PEN (§5.3): su P/E necesita
homogeneizar moneda (usar close en PEN × acciones vs utilidad convertida, o
todo en USD). Fuentes: SEC EDGAR 20-F FY2013/2015/2021 de Buenaventura.

## IMPLEMENTADO end-to-end (jul-2026)

Código: `fundamentals_client.compute_shares_earnings(fund, asset)` → shares_outstanding,
net_income_ttm (PEN), eps_ttm; `compute_ratios(fund, asset=...)` las anexa (asset
opcional, retrocompatible con test_ratios). Utilidad TTM desde la serie **YTD**
(cuenta 2D07ST no-banco / 2F1901 banco SBS, detectada por match con INFO_UtilidadNeta),
NO desde Monto1 (tiene inconsistencias por reexpresión: ALICORC1 2023Q3 Monto1=76,669
vs YTD-diff=26,942). BVN: utilidad USD→PEN por trimestre (TC BCRP) antes de sumar TTM;
rótulo USD espurio de reportante-PEN se ignora por moneda modal.
`build_dataset.build_unified(..., dividends=...)`: pe=close_raw/eps_ttm (NaN si TTM<=0),
dy=div_TTM_por_acción/close_raw, diarios. `run_r6_integration` arma dividendos vía
corporate_actions. Config: `nominal_value` por activo + `shares_outstanding_override`
(BVN=253715190) en Asset/config.yaml. Panel dataset_unificado.parquet: columnas pe, dy
(+ shares_outstanding, net_income_ttm, eps_ttm) en vistas mercado_fundamentales/completa.
Cobertura P/E ~93-96% (no-mineros), 55% BVN (NaN en pérdidas). Notebook §5b ejecutado.
P/E usa close_raw (market cap), NO close_split_adj (evita sesgo por split). Verificado:
CREDITC1 P/E med 13.4, CORAREC1 7.0, BVN 23.7. Scripts test previos siguen OK.

## Base = EN CIRCULACIÓN; tesorería de ALICORC1 resuelta desde SMV (jul-2026)

Base decidida = acciones EN CIRCULACIÓN (neto tesorería), no emitidas. Fórmula
(no bancos): en_circulación = (Capital Emitido 1D0701 − |Acciones en Cartera
1D0711|) / nominal. Tesorería = 0 en el horizonte para CREDITC1, SAGAC1,
CORAREC1 (circulación=emitidas). ALICORC1 SÍ tuvo tesorería MATERIAL (no ~1.4%
como se estimó primero, sino hasta 10%): programas de recompra 84,719,000 acc
(2022-2023, =10%), 76,246,294 al 30-jun-2024 (=10%), amortizadas por etapas
2024-2025. El conteo de tesorería de ALICORC1 SÍ sale del SMV (la registra a
valor nominal S/1 → monto en soles = conteo), validado al 0.0004% contra notas
a los EEFF auditadas. Serie en circulación ALICORC1: 847.19M (2005-2021) →
762.47M (2022-2023) → 617.62M (2024) → 556.08M (2025). BUENAVC1: su SMV
individual NO refleja tesorería (=0); su neto 253.72M viene de la SEC. Scripts:
probe_bvl_capital.py, validate_shares_anchor.py. Docs: pipeline §3.10.2 (g),
hallazgos R4 §5.9.

## Tercera vía: conteo por TRAMOS (jul-2026, nuevo universo)

A las dos fuentes de conteo (capital/nominal y `shares_outstanding_override`
constante) se sumó `Asset.shares_outstanding_schedule` = ((fecha_desde, conteo),...),
con **precedencia schedule > override > capital/nominal** en
`compute_shares_earnings` (helper `_shares_from_schedule`, escalonado por
searchsorted). Es para el activo cuyo conteo CAMBIÓ y no se puede derivar del
capital/nominal: INRETC1 (holding panameño SIN valor nominal) tuvo un único
follow-on en 2022-Q2 → 2012-01-01: 100,556,000 (reconstruido por razón de Capital
Emitido SMV, real en [100.6M, 102.9M], error ≤2%) y 2022-06-30: 108,746,887
(snapshot BVL exacto). Reemplaza al override único, que sobrestimaba el P/E
pre-2022Q2 ~8%. Regresión: CREDITC1/ALICORC1 sin cambio (Δ=0). Ver
[[project-universe-decision]].

**Why:** Evitar que una sesión futura reabra esta investigación desde cero;
la decisión ya tiene un análisis exhaustivo documentado.
**How to apply:** Si se retoma P/E o DY, leer primero §3.10.1 del pipeline
doc y [[project-r3-corporate-actions]] (de donde viene el factor de split
validado y los dividendos ya descargados).
