---
name: project-universe-decision
description: "Decisión de universo (jul-2026): reemplazar SAGA→InRetail y CORAREC→Pacasmayo, agregar Ferreycorp (6º); minera diferida. Scorecard de candidatos (liquidez+SMV+prensa)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 11430378-f501-4579-83b7-1e1375e7ede2
  modified: 2026-07-30T18:58:04.440Z
---

## Decisión de universo (jul-2026) — tomada por el usuario

Motivada por el riesgo #1 (iliquidez, ver [[project-riesgos-datos-pendientes]]):
SAGA (4.1% días operados) y CORAREC (20.8%) son casi no negociables.

**Confirmado:**
- **SAGA (retail) → InRetail (INRETC1)**
- **Aceros Arequipa (CORAREC1) → Cementos Pacasmayo (CPACASC1)**
- **+ Ferreycorp (FERREYC1)** como 6º activo (sector NUEVO: bienes de capital),
  SIN eliminar la minera.
- **+ Luz del Sur (LUSURC1)** como 7º activo (utilities). SMV RPJ B40008, Soles,
  I y C 2012-2025, utilidad positiva. Liquidez 56.5%, prensa 2.8/sem (ambas OK).
- **Minera: MINSUR (MINSURI1) REEMPLAZA A BUENAVENTURA (BUENAVC1) — DECIDIDO
  y CERRADO por el usuario el 2026-07-30.** BVN sale del universo. La comparación
  que sustentó la decisión se conserva abajo como evidencia.
  Métricas (probe_minsur_vs_bvn.py). Minsur cc BVL=62200, rpj SMV A20032, precio
  PEN (~S/5.3, NO necesita convertir precio, igual que BVN), reporte USD, nominal
  S/1, snapshot 961,000,840, 20 dividendos. BVN cc 61200, precio PEN (~S/90),
  nominal 10, snapshot 274,889,924 (SEC neto 253.7M), 23 dividendos.
  DIFERENCIADOR CLAVE — utilidad neta (9 años SMV consolidado, miles USD):
  BVN positiva solo 2/9 (2022 +69k, 2024 +30k; el resto PÉRDIDAS crónicas por
  impairments/asociadas) → su P/E es NaN casi siempre. Minsur positiva 7/9 (solo
  pérdida 2015 crash −508k y 2017 −9k; 2021-2024 fuerte, +178k..+390k) → P/E
  USABLE. Liquidez Minsur 64.9% vs BVN 23.7%. Prensa BVN 2.6 vs Minsur 2.2.
  Ventajas BVN: ancla SEC 20-F auditada + clase única. Ventajas Minsur: liquidez
  BVL real + P/E usable + estaño(#2 mundial)/cobre(Mina Justa) alineado con macro.
  ITEM (1) RESUELTO (probe_minsur_estabilidad.py): capital Minsur PERFECTAMENTE
  plano 2012-2025 — Capital Emitido común (1D0701)=601,269 y Acciones de Inversión
  (1D0703)=300,634 (miles USD) constantes todos los años, treasury=0. Conteo
  MINSURI1=961,000,840 constante → ancla fija justificada, más limpia que BVN.
  ITEM (2) ABIERTO: MINSURI1 es acción de INVERSIÓN (no votante; la común Breca no
  flota). Su participación en el patrimonio = 300,634/(601,269+300,634)=33.3%. P/E
  a nivel instrumento = precio MINSURI1 / (utilidad×33.3% ÷ 961M acc). Análogo pero
  INVERSO a CORAREC (ahí la común CORAREC1 sí flota y se usa). Ya resuelto en
  config vía override 2,883,002,520 (total económico); NO requiere código nuevo.
  Queda como LIMITACIÓN A DECLARAR en la tesis: el P/E de MINSURI1 es a nivel de
  instrumento (acción de inversión, 33.3% del patrimonio), no de la empresa.

## Scorecard de candidatos (las 3 patas), medido jul-2026

Liquidez = % días con cambio de precio (= 1 − is_stale, coincide EXACTO con el
flag del panel), BVL share-values 2012-2025. Script: `probe_liquidez_candidatos.py`.
SMV RPJ/moneda: `probe_smv_new.py` + `probe_smv_debug.py` (campo NombreEmpresa,
NO RazonSocial). Prensa = art/semana MediaCloud Perú Nacional: `probe_mc_new.py`,
`probe_mc_candidatos.py`.

| Activo | Liquidez | SMV RPJ / moneda | Prensa/sem |
|---|---|---|---|
| Pacasmayo CPACASC1 | 72.1% | CD0005 / Soles | 14.3 |
| Ferreycorp FERREYC1 | 73.5% | B60001 / Soles | 5.0 |
| InRetail INRETC1 | 63.1% | OE5087 / Soles (CONSOLIDADO; individual da pérdida) | 11.8 |
| UNACEM UNACEMC1 | 63.3% | B30121 / Soles | (sin medir) |
| Minsur MINSURI1 | 64.9% | A20032 / **USD** | 2.2 |
| Volcan VOLCABC1 | 80.7% | CM0001 / USD (estrés financiero) | — |
| Casa Grande CASAGRC1 | 66.1% | (Soles) | **0.5 → DESCARTADA (sin prensa)** |
| Aenza AENZAC1 | 64.5% | — | 7.9 (ruido Lava Jato) |
| Luz del Sur LUSURC1 | 56.5% | — | 2.8 |
Incumbentes (base): SAGA 4.1%/2.2sem, CORAREC 20.8%/1.5(piso), ALICORP 75.9%/3.9,
CREDITC 58.6%/36.6, BVN 23.7%/2.6.

**Hallazgo estructural:** casi TODA minera peruana reporta en USD (Buenaventura,
Minsur, Volcan, Nexa, Cerro Verde) → cualquier minera de reemplazo hereda el
P/E bimoneda de BVN (la maquinaria USD→PEN ya existe para BVN). Ferreycorp y
Pacasmayo y UNACEM en Soles.

## Costo de ampliar el universo (verificado en código)

Pipeline parametrizado sobre `config.yaml` → `universe`; `run_r6_integration`
itera `for asset in cfg.assets`. Agregar activo = bloque de config + re-correr,
SIN cambios de código para una BVL-nativa en Soles. Costo marginal: R3 bajo; **R4
casi gratis** (el SMV baja las ~261 empresas por período en 1 llamada cacheada,
solo filtra un RPJ nuevo); **R5 es el cuello de botella** (Ollama gemma3:4b
clasifica cada artículo — Pacasmayo 10,390 arts, InRetail 8,615); R6 bajo.

**Datos por-activo CERRADOS (jul-2026, scripts probe_bvl_company_codes.py +
probe_bvl_nominal.py; el bvl rpjCode == SMV RPJ, cross-validado):**
| Activo | bvl_company_code | nominal | moneda precio | benefit | acciones snapshot |
|---|---|---|---|---|---|
| Pacasmayo CPACASC1 | 23950 | 1.0 | S/. | 18 div | 423,868,449 |
| Ferreycorp FERREYC1 | 73600 | 1.0 | S/. | 26 div + 5 AL | 946,063,288 |
| Luz del Sur LUSURC1 | 70252 | 0.68 | S/. | 55 div | 486,951,371 |
| InRetail INRETC1 | 74222 | 0 (sin par) | **US$** | 10 div | 108,746,887 |
Los 3 primeros LISTOS para config (PEN, nominal claro). Pacasmayo tiene también
CPACASI1 (inversión) — se usa la común CPACASC1.

**InRetail — investigación del ancla (decisión usuario: investigar antes de
integrar). Script probe_smv_inretail_shares.py.** Complicaciones: (1) precio en
US$ (~25) → requiere close US$→PEN con TC BCRP, MÁS que BVN (BVN ya cotizaba PEN);
(2) sin valor nominal (holding Panamá, ISIN PAL...) → NO sirve capital÷nominal;
(3) fundamentales = consolidado (individual da pérdida). PERO acciones ESTABLES:
Capital Emitido SMV individual (1D0701, en S/) plano 2012-2020 (2,739,714) y sube
a 2,962,923 en ~2021-2023 (un solo follow-on, +8%); conteo ~102.9M (IPO 2012) →
108.7M hoy (+5.6%, un escalón). Muy estable vs PEN-nativos. Ancla piecewise de 2 niveles
+ close US$→PEN (extiende maquinaria BVN); documentar como BVN.

CERRADO (jul-2026, probe_inretail_followon.py): el follow-on fue EXACTAMENTE
2022-Q2 (Capital Emitido individual 1D0701 plano en 2,739,714 desde 2012 hasta
2022-Q1, salta a 2,962,923 en 2022-Q2; treasury 1D0711=0 siempre). Ancla final:
- 2022-Q2 → 2025-12-31: 108,746,887 (snapshot BVL, exacto/autoritativo)
- 2012 → 2022-Q1: ~100,556,000 = 108,746,887 × (2,739,714/2,962,923), reconstruido
  por razón de Capital Emitido SMV. El follow-on fue sobre par, así que el
  verdadero pre-conteo está en [100.6M, 102.9M(IPO)]; incertidumbre ≤2%, solo
  afecta P/E pre-2022. DY NO usa conteo (usa div/acción de listBenefit ÷ precio).
Config InRetail: bvl_company_code=74222, smv_rpj=OE5087, precio US$→PEN (TC BCRP),
fundamentales CONSOLIDADO en soles, shares_outstanding por tramo (override 2-niveles).
InRetail = activo más manual del universo, pero cerrado y tratable.

## ESTADO DE IMPLEMENTACIÓN (jul-2026)
HANDOFF completo para retomar: **docs/pendientes_implementacion_universo.txt**
(pasos a-e con archivos/funciones/valores exactos + orden de corrida + verificación).
HECHO: (1) `src/macro/macro_client.py` — fetch BCRP 6 series + alineación
point-in-time `macro_features(dates)`, probado (0 NaN 2013-2025), cache
data/interim/macro_bcrp.parquet. (2) `config.yaml` reescrito: 7 activos (Minsur
override=2,883,002,520; InRetail smv_tipo=C, price_currency=USD, override=108.7M) +
sección sources.macro. (3) `src/universe.py` Asset: campos nuevos price_currency,
smv_tipo. Config.load OK.
HECHO (jul-2026, sesión de implementación): **(a)** `market_client._to_pen` —
consume `price_currency=USD` y convierte open/high/low/close con TC BCRP vigente
(`fx.rate_asof`); se llama en `fetch_market` después de grabar el raw (raw queda
en US$) y antes del merge/acciones corporativas. Probado 2025-H1: US$26-32 →
S/95-120, 0 NaN, ALICORC1 intacto. **(b)** `fetch_smv(tipo=None)` resuelve
`tipo or asset.smv_tipo or "I"` → todos los llamadores correctos por config;
`fetch_fundamentals` expone `tipo` como override. Verificado 2023Q4 INRETC1: C
=+321,717 vs I =−40,729 miles S/ (moneda PEN, caché por tipo ya separada).
`gen_fundamentals.py`: rango 2020-2023 → cfg.start/end, raw_dir de config, `--force`.
**(b.2) FIX de look-ahead** que salió de (b): el known_date real venía del hecho
"Intermedia INDIVIDUAL" aunque INRETC1 consume el CONSOLIDADO, y en INRETC1 la
consolidada se divulga 9-19 d después (mediana 14) en 30/30 trimestres (ALICORC1
0/30, CREDITC1 0/26 → inocuo para tipo "I"). `_EEFF_OBS_RE` pasó a mapa {"I","C"} y
`_load_filing_dates(tipo=)` lo recibe de fetch_smv. Ver riesgos §3(a.4).
**(d) macro en R6**: `build_unified(..., macro=)` + `_merge_macro` (join por date tras
el concat; ValueError si choca una columna); el runner resuelve
`macro_features(build_trading_calendar(market))`; `feature_views` con nueva vista
`mercado_macro` y las 6 en `completa`. `load_macro(start=)` 2012→**2011** (colchón para
el asof de las mensuales; sin él, enero-2012 quedaba sin tasa/inflación) y caché
regenerado. Verificado: 0 NaN, 1 valor por fecha, rangos sensatos, escalones de las
mensuales solo a inicio/fin de mes (0 a mitad de mes → sin look-ahead).
**(c) ancla por TRAMOS**: nuevo campo `Asset.shares_outstanding_schedule` =
((fecha_desde, conteo), ...) normalizado a tupla en `Config.load` (Asset es frozen/
hashable); `_shares_from_schedule` escalonada (searchsorted, avisa en periodos previos
al primer tramo); precedencia en `compute_shares_earnings`: **schedule > override >
capital/nominal**. En config, INRETC1 usa schedule (2012-01-01→100,556,000;
2022-06-30→108,746,887) y ya NO override. Regresión: CREDITC1/ALICORC1 con Δshares y
Δeps_ttm = 0 exactos. Baja el error del P/E pre-2022Q2 de ~8% a ≤2% (el tramo viejo es
reconstruido por razón de Capital Emitido; real en [100.6M, 102.9M]); NO se enmascara
con pe_reliable=0.
End-to-end real (a+b+c): `data/raw/fund_INRETC1_smv.parquet` YA GENERADO
(scripts/gen_fund_inretail.py, 11,602 filas, 54 periodos 2012Q3-2025Q4, PEN,
known_date real en 30/56) → **no re-descargar en la corrida R4**. Tramos exactos
(39 periodos a 100.556M, 15 a 108.747M), escalón el 2022-08-16 = known_date real de
la consolidada 2022Q2. P/E diario 91.7% de cobertura, mediana 25.8; capitalización
mediana S/10,220 MM ≈ los ~US$2.5-3 mil MM reales → escala correcta. OJO DISCO: el
tipo "C" no estaba cacheado y cada archivo del WSDL trae todas las empresas (~5 MB);
`data/raw/smv_cache/` quedó en **2.2 GB**. Se bajó desde 2012 (no 2005) porque el
IPO fue oct-2012.
**NO QUEDA CÓDIGO PENDIENTE** del handoff: solo la corrida R3→R6 + docs/notebooks.
Minsur NO necesita código nuevo (override+USD→PEN de utilidad ya existen).
PENDIENTE corrida: re-correr R3→R6 (R5/LLM es el cuello — clasificar InRetail 8.6k,
Pacasmayo 10.4k, Ferreycorp/LuzSur/Minsur). Scripts nuevos de esta sesión:
probe_liquidez_candidatos, probe_bvl_company_codes, probe_bvl_nominal,
probe_inretail_followon, probe_minsur_vs_bvn, probe_minsur_estabilidad, probe_bcrp_macro.

## Features MACRO — alcance decidido (jul-2026): "hasta inflación"
Duros, globales por fecha, merge_asof con known_date=fecha de anuncio, fuente
BCRP (reusa `src/market/fx.py`, serie TC PD04640PD ya implementada). SEIS series:
cobre, TC (ya está), oro, tasa de referencia BCRP, EMBI+ Perú, inflación IPC.
Precios como retorno log; tasas/EMBI nivel+cambio. NO se incluye Fed/UST, PBI,
VIX/S&P (quedaron fuera del corte).

CÓDIGOS BCRP CONFIRMADOS (validados contra API, cobertura 2012-2025 completa,
script `probe_bcrp_macro.py`):
- TC USD/PEN venta bancario: PD04640PD (diaria) — YA en src/market/fx.py
- Cobre Londres cUS$/lb:      PD04701XD (diaria)
- Oro Londres US$/oz troy:    PD04704XD (diaria)
- EMBIG Perú spread pbs:      PD04709XD (diaria, 3653/3653 sin huecos)
- Tasa de referencia (%):     PD04722MM (mensual, nivel)
- Inflación IPC Lima:         PN01271PM (mensual, var% MENSUAL — NO 12m ni nivel;
  la de 12m es otro código si se quiere la interpretable vs meta 1-3%)
Point-in-time: diarias entran en su fecha; tasa en fecha de reunión BCRP; IPC del
mes M se publica ~1 de M+1 → known_date en M+1 (evitar look-ahead). Endpoint API:
estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json/{start}/{end}.

## Riesgo político/geopolítico → indicadores (documentado)
Doc: **docs/fundamento_macro_riesgo_politico.txt**. NO se agrega feed de noticias
geopolíticas (bajo valor para Perú; redundante). El canal entra por proxies duros:
- Global (guerras) → precios de commodities (cobre/oro). Respaldo: choques de
  términos de intercambio explican ~25.6% de varianza del PBI 2001-2016 (30-60%
  en estudios recientes; IMF Art. IV).
- Político doméstico (vacancias, autogolpe Castillo dic-2022, conflictos) → EMBI/
  precios. Respaldo Perú-específico: Micozzi, Navia, Pinto & Saiegh (2024, JRFM
  17(7):298) — el mercado repreció el autogolpe en minutos (alta frecuencia; en
  DIARIO puede verse "insignificante" → limitación, nuestro panel es diario).
- HALLAZGO clave: existe **EPU-Perú del BCRP** (Doc. Trabajo 002-2026), índice
  news-based 2009-2025 (scraping Gestión/El Comercio/Perú21/RPP) ya validado —
  add-on ideal de bajo costo si se quiere el tono/sorpresa, sin clasificador
  propio. Base metodológica: Baker, Bloom & Davis (2016, QJE 131(4):1593).
Ver [[project-r6-integration]] y [[project-riesgos-datos-pendientes]].
