---
name: project-bvl-dataondemand
description: BVL dataondemand — fundamentales inoperativo, PERO dividendos+acciones liberadas SÍ vía /v1/issuers/{companyCode}/value (jul-2026)
metadata: 
  node_type: memory
  type: project
  originSessionId: 6b3cf012-0289-48a6-859c-e55c8474dca2
---

## BVL dataondemand — Fundamentales (inoperativo)

**Confirmado junio 2026:** Los siguientes endpoints retornan 200 pero `null` (sin datos) para todos los tickers del universo:
- `GET /v1/issuers/financials?nemonico=ALICORC1` → 200 null
- `GET /v1/issuers/eeff?nemonico=ALICORC1` → 200 null
- `GET /v1/issuers/financial-info?nemonico=ALICORC1` → 200 null
- `POST /v1/financialstatements/` → 404

No hay parámetros adicionales que activen los datos (probado con variantes: year, quarter, period, tipo, etc.).

**Conclusión:** La fuente primaria de fundamentales es el SMV WSDL. Ver [[project-smv-wsdl]].

**Why:** Fueron probados exhaustivamente en scripts/probe_fundamentals*.py en junio 2026.
**How to apply:** No intentar recuperar fundamentales de BVL dataondemand; usar únicamente SMV.

## BVL dataondemand — Dividendos y acciones liberadas (IMPLEMENTADO+VALIDADO, jul-2026)

**ESTADO: ya integrado al pipeline** (no solo sondeado). fetch_actions() en
src/market/corporate_actions.py usa la BVL para los 5 activos vía
fetch_bvl_benefits(cc, nemonico). config.yaml tiene `bvl_company_code` por activo.
Dividendos US$→PEN con TC del BCRP (serie PD04640PD; nuevo módulo src/market/fx.py).
OJO doble-conteo: /value trae UNA entrada listValue por CLASE (común+inversión+ADR),
todas repiten los mismos beneficios → SIEMPRE filtrar por nemónico (conteos reales
por instrumento: CREDITC1 13AL+21DE, BUENAVC1 23DE, ALICORC1 17DE, SAGAC1 1AL+25DE,
CORAREC1 3AL+40DE; el doc de hallazgos §4 sobre-contaba ×2-3). Splits se alinean al
día real de la caída (dateCut se adelanta a la ex-date; align_splits_to_price).
Regeneró market_*.parquet + R6 + notebook exploracion_datos_bvl. Ver
[[project-r3-corporate-actions]] y docs/hallazgos_dividendos_acciones_bvl.txt §0.

## BVL dataondemand — Acciones en circulación / capital en circulación (CONFIRMADO jul-2026)

El "Listado de Capital en Circulación" de la BVL SÍ se sirve desde dataondemand,
y NO en un endpoint nuevo: viene embebido en el MISMO `/v1/issuers/{cc}/value`
que ya usamos para acciones corporativas, en el bloque `listStock` (que antes no
leíamos). Endpoints con nombre propio (/shares, /capital, /listed-capital, etc.)
dan 404. `scripts/probe_bvl_capital.py`. listStock es un SNAPSHOT ÚNICO actual
(n=1, date=2026-07-06 ≈ actualización semanal), NO serie histórica.

Campos de listStock por instrumento (clase): `quantity`=acciones en circulación
(el dato que faltaba para P/E y DY), `nominalValue`=valor nominal/acción,
`capital`=**capitalización bursátil** (= close × quantity; confirmado exacto para
CREDITC1: 6.691×12,973,174,634=86,803,511,476), NO el capital social. El capital
social = quantity×nominalValue. Snapshot 2026-07-06 (acciones común C1):
CREDITC1 12,973,174,634 (nom 1); BUENAVC1 274,889,924 (nom 10); ALICORC1
569,573,006 (nom 1); SAGAC1 156,709,425 (nom 1); CORAREC1 890,858,308 (nom 1).
Cada empresa trae también su clase de inversión (I1) y BVN (ADR, listStock vacío).

**Implicación:** ahora hay ancla AUTORITATIVA de acciones para los 5 (antes solo
CREDITC1 tenía camino viable, ver [[project-pe-dy-viability]]). Reconstrucción
histórica = quantity actual ÷ factor acumulado de splits (corporate_actions.py,
ya validado). Caveat: el factor solo captura acciones liberadas (AL), no aumentos
de capital por aportes ni recompras → aproximación, no exacta. Alternativa:
Capital Emitido trimestral del WSDL SMV ÷ nominalValue de la BVL (si nominal es
estable). NO implementado aún; decisión pendiente del usuario. No sustituye EODHD
para serie histórica diaria, pero elimina la necesidad de EODHD para el ancla.

## BVL dataondemand — OHLC/volumen histórico NO existe (confirmado en fuente, jul-2026)

Rol 2 (OHLC nativo BVL / "Opción C") CERRADO por imposibilidad de la fuente, no
por parámetro no descubierto. Se inspeccionó el web component del sitio
(`assets/web-components/issuer-details/main.js`): el gráfico de la ficha de
emisor es una LÍNEA DE CIERRE (el código NO tiene open/high/low), y usa el mismo
`/v1/stock-quote/share-values` que ya consumimos (GET /{nemonico} = fetch_bvl;
POST = solo la variante multi-ticker "Comparar"); ambas devuelven solo cierre.
Sin serie histórica de volumen. `/v1/stock-quote/daily`=intradía sesión actual;
`/v1/traded-amount/daily`=solo último snapshot. Proveedores de pago (Bloomberg,
LSEG/Datastream, S&P CapIQ) sí llevan OHLCV BVL, pero la iliquidez hace el OHLC
degenerado y el volumen no está ni pagando para 3/5. Detalle:
docs/justificacion_cierre_vs_ohlcv.txt (ADENDA). yfinance queda solo como
enriquecimiento OHLC de CREDITC1/ALICORC1 (Opción B). **How to apply:** no
perseguir OHLC/volumen histórico en la BVL; el agente usa solo cierre.

A diferencia de fundamentales, el MISMO endpoint dataondemand SÍ expone el
historial completo de acciones corporativas por emisor (dividendos en efectivo
+ acciones liberadas), nativo de la BVL, sin Apify ni yfinance:

- `GET /v1/issuers/{companyCode}`         → detalle del emisor
- `GET /v1/issuers/{companyCode}/value`   → `listValue[].listBenefit[]`

Identificadores BVL (3 sistemas): nemónico (CREDITC1) → **companyCode numérico**
(12000) → rpjCode (B80005). El endpoint /value usa el **companyCode numérico**.
companyCode resuelto/confirmado: CREDITC1=12000, BUENAVC1=61200, ALICORC1=21400,
SAGAC1=75700, CORAREC1=20601. Se resuelven con `GET /v1/issuers` (341 emisores)
filtrando por companyName y confirmando con el nemónico en listValue.

Campos de cada beneficio: `benefitType` ("DE"=Dividendo Efectivo, "AL"=Acciones
Liberadas), `benefitValue` (DE=monto/acción; **AL=% de acciones nuevas → ratio
split = 1+val/100**), `coin` ("S/."|"US$"), `dateAgreement`/`dateCut`(~ex-date)/
`dateRegistry`/`dateDelivery`.

**Validado (CREDITC1):** las 13 AL de la BVL reproducen EXACTAMENTE los "splits"
de yfinance (2010:14.785→1.14785; 2012:24.63→1.2463; 2013→1.20939; ...).
yfinance es un espejo de esta fuente. Cobertura ~2010→ (cubre el horizonte de
mercado 2012-2025). Esto resuelve las lagunas de R3: SAGAC1/CORAREC1 (antes sin
fuente de ajuste) y BUENAVC1 (antes sin ajuste por ser BVN un ADR USD). Ver
[[project-r3-corporate-actions]]. Script: `scripts/probe_bvl_benefits.py`.

Pendiente: `POST /v1/corporate-actions` ("Hechos de Importancia") no se logró
invocar (500 "Regex string must not be null!" — falta el campo/nombre exacto del
body); pero eso son avisos regulatorios en PDF, no acciones que afecten el
precio. Requeriría capturar el XHR real del sitio (extensión Chrome no conectada
en la sesión del hallazgo).

**Why:** Sondeo por ingeniería inversa del bundle Angular (main.js: mapa de
endpoints `S.importantFact=/v1/corporate-actions`, base `API_URL_2=dataondemand`)
+ actor Apify soyjb/bvl-peru-mcp que documenta las herramientas.
**How to apply:** Para ajuste por acciones corporativas de los 5 activos, usar
/v1/issuers/{companyCode}/value como fuente autoritativa BVL en PEN (o USD para
BUENAVC1 y parte de CORAREC1), en vez de/además de yfinance.
