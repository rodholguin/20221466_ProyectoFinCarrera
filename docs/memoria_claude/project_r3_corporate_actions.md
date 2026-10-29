---
name: project-r3-corporate-actions
description: "Cierre de R3 — capa de ajuste por acciones corporativas, fix del merge BVL/Yahoo, horizonte de mercado reducido a 2012-2025"
metadata: 
  node_type: memory
  type: project
  originSessionId: fc61a441-3c31-4ddc-a094-c09f8e0eaee6
---

## ACTUALIZACIÓN jul-2026: fuente de acciones corporativas migrada yfinance→BVL

La sección de abajo (jun-2026) quedó SUPERSEDIDA en la parte de fuentes. Ya NO
se usa yfinance para splits/dividendos: fetch_actions() usa la BVL nativa
(/v1/issuers/{cc}/value) para los 5 activos. Ahora los 5 están ajustados
(BUENAVC1: dividendos US$→PEN con TC BCRP, src/market/fx.py; SAGAC1/CORAREC1:
antes sin fuente, ahora sí). Se corrigieron 2 bugs de dividendos que traía
yfinance: CREDITC1 subestimado (dividendos ya split-ajustados y re-ajustados) y
ALICORC1 sobreestimado (dividendos inflados por reverse-splits 2025-26 fuera de
horizonte). Nueva align_splits_to_price() elimina el residuo del desfase
dateCut→ex-date (el "1-2 días" de abajo YA NO deja residuo en CREDITC1). yfinance
queda solo como enriquecimiento OHLC de CREDITC1/ALICORC1 (irrelevante: el agente
no usa OHLCV). Ver [[project-bvl-dataondemand]] y
docs/hallazgos_dividendos_acciones_bvl.txt §0. **How to apply:** al tocar
src/market/, recordar que la fuente de acciones corporativas es la BVL (campo
bvl_company_code en config), NO yfinance, y filtrar beneficios por nemónico.

## R3 cerrado (jun-2026): acciones corporativas + fix de merge BVL/Yahoo

**Decisión clave del usuario:** la data de mercado debe ser un flujo "sano y
original" de BVL/SMV antes que de fuentes externas como Yahoo. Por eso el
horizonte EFECTIVO del dataset de mercado es **2012-2025** (no 2005-2025):
se descartó por completo el período 2008-2011 (CREDITC1/ALICORC1) y
2005-2011 (BUENAVC1) en el que Yahoo era la única fuente. Yahoo pasó a ser
estrictamente un enriquecimiento puntual de open/high/low/volumen en fechas
donde la BVL YA tiene un registro — nunca una fuente de cobertura de
respaldo. Fundamentales (R4/SMV) sigue cubriendo 2005-2025 completo; no
confundir los dos horizontes.

**Hallazgo de raíz (válido para entender cualquier análisis futuro de estos
datos):** el `close` de Yahoo (`Ticker.history(auto_adjust=False)`) para
CREDITC1.LM, un ticker de muy baja liquidez (~33k acciones/día), viene
*ya ajustado por splits a la fecha de descarga*, no a la fecha cotizada —
a pesar del flag `auto_adjust=False`. Esto se confirmó porque el producto
acumulado de los ratios de `.splits` de yfinance entre dos fechas reproduce
con <0.1% de error el desfase de escala observado entre el close de Yahoo y
el de la BVL en ese mismo tramo. El bug original de merge (`_merge_bvl_yahoo`
insertaba el close de Yahoo en huecos de la BVL, y mezclaba BVN-USD con
BUENAVC1-PEN) producía saltos diarios de hasta +421%/+397% que NO eran
acciones corporativas reales sino un artefacto de mezclar fuentes en
escalas distintas. Se corrigió restringiendo Yahoo a enriquecimiento OHLC
puntual (nunca close, nunca cobertura de respaldo) y reescalando el
open/high/low de Yahoo por el factor de split antes de fusionarlo.

**Módulo nuevo:** `src/market/corporate_actions.py`. Agrega a cada
`data/interim/market_{TICKER}.parquet`: `close_raw`, `close_split_adj`,
`close_total_return` (ajuste CRSP hacia atrás) + flags `is_split_adjusted`/
`is_div_adjusted`. Fuentes por ticker:
- CREDITC1, ALICORC1: yfinance `.splits`/`.dividends` (validado para CREDITC1).
- BUENAVC1: sin ajuste (BVN es ADR USD, no se puede confirmar splits/dividendos
  en PEN sin acceso a "hechos de importancia" BVL/SMV, que no existe como
  endpoint automatizado — ver [[project-bvl-dataondemand]]).
- SAGAC1, CORAREC1: sin ajuste (sin cobertura Yahoo); `detect_split_candidates()`
  detecta saltos >40% para revisión manual, sin confirmación automática.

`technical_indicators.add_indicators` ahora calcula los indicadores sobre
`close_total_return` (no sobre `close`); se conserva `ret_1d_raw` sobre
`close_raw`.

**Limitaciones conocidas documentadas en `docs/pipeline_extraccion_datos.txt`
sección 2.7:** desfase de 1-2 días entre la ex-date de yfinance y el ajuste
real en la BVL (residuo de hasta ~28% en un solo día por split, no llega al
umbral de 100%); un salto no confirmado de +46.9% en BUENAVC1 el 2020-09-21
sin poder confirmar/descartar como acción corporativa.

**Bug encontrado y corregido (jun-2026, post-cierre):** `market_client.fetch_market()`
pasaba `actions["splits"]` SIN recortar por `end` a `_merge_bvl_yahoo()` (a
diferencia de `build_adjusted_prices()`, que sí recortaba). El único split de
ALICORC1 en yfinance (2026-03-23) cae fuera del horizonte 2012-2025, pero se
filtraba igual como factor constante 0.9222 al reescalar el OHLC de Yahoo →
open/high/low de ALICORC1 quedaban subestimados 7.78% en TODOS los días del
histórico (detectado porque `|open-close|/close` daba una mediana constante
de 7.78% en 13 años, imposible para dinámica de mercado real). Fix: nueva
`filter_actions_by_cutoff()` en `corporate_actions.py`, aplicada en ambos
puntos de uso. Tras regenerar: mediana baja a 0.09%. CREDITC1 no se vio
afectado (sus 15 splits caen dentro del horizonte). Detalle completo en
`docs/pipeline_extraccion_datos.txt` sección 2.7.

**Why:** Indicación directa del usuario (cierre de R3) — la BVL/SMV deben
mandar sobre Yahoo, y los datos deben estar libres de saltos artificiales
antes de pasar a R4 nota/R6.
**How to apply:** Si se vuelve a tocar `src/market/`, recordar que el
horizonte de mercado es 2012-2025 (no 2005-2025) y que `close` ya no debe
usarse directamente para retornos/indicadores — usar `close_total_return`.
Ver también [[project-overview]].
