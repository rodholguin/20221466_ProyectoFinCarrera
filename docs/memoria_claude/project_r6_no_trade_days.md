---
name: project-r6-no-trade-days
description: "R6: política para días sin cotización real de un activo (BVL abrió pero el activo no operó) — precio stale + indicadores recalculados + flag is_no_trade. Incluye fix de rsi_14 NaN (preexistente de R3, ya corregido)."
metadata:
  node_type: memory
  type: project
  originSessionId: fc61a441-3c31-4ddc-a094-c09f8e0eaee6
---

## R6 — días sin cotización ("no-trade"): decidido e implementado (2026-06-23)

Al reindexar el panel sobre el calendario bursátil único (ver
[[project-r6-integration]]), quedaron expuestos huecos donde un activo
específico no cotizó aunque la BVL sí abrió: SAGAC1 192 días (9 episodios,
el mayor de 41 sesiones consecutivas, 2012-09 a 2015-04), BUENAVC1 14 días
(un solo episodio, nov-dic 2014), CREDITC1 2 días. ALICORC1/CORAREC1 sin
huecos.

**Decisión:** se arrastra el último `close_total_return`/`close_raw`
conocido (precio "stale", sin operación real) y se RECALCULAN los
indicadores técnicos (`technical_indicators.add_indicators`) sobre la
serie ya completa, en vez de arrastrar a ciegas los valores de los
indicadores ya calculados. NO se completa open/high/low/volumen — esa
ruta ya se descartó explícitamente en
`docs/justificacion_cierre_vs_ohlcv.txt` (el agente solo usa
`close_total_return`, ningún indicador usa OHLCV). Una columna
`is_no_trade` (0/1) marca estas filas para que el entorno (OE1) pueda
modelar el costo de iliquidez en vez de tratarlas como una sesión real
(ver nota sobre CREDITC1 en `config.yaml`: "limpiar huecos/cierres
estancados y modelar el costo de iliquidez en el entorno").

**Why:** Es la misma asimetría de iliquidez ya documentada para 3/5
activos (volumen permanentemente NaN: BUENAVC1/SAGAC1/CORAREC1).
Forward-fill + recálculo de indicadores es el tratamiento estándar para
"stale price" en mercados emergentes/activos ilíquidos: `ret_1d=0` y
`volatility_20` decaen correctamente durante el tramo sin operación,
mientras el salto real al reanudar la negociación se refleja íntegro ese
día (verificado con SAGAC1 2012-09-10: -3.4% tras 4 sesiones
`is_no_trade`).

**Implementado en** `src/integration/build_dataset.py::_fill_no_trade_days`,
llamado desde `build_unified()` justo después del merge de mercado, antes
del bloque de sentimiento.

## Hallazgo de `rsi_14` NaN: diagnosticado y CORREGIDO (2026-06-23)

Al validar se encontró que `rsi_14` ya tenía **27.5% de NaN en los
parquets originales de R3** (antes de la decisión de no-trade), muy
desigual por activo: SAGAC1 79.4%, CORAREC1 26.6%, BUENAVC1 31.2%,
CREDITC1 2.4%, ALICORC1 0.7%. Causa: `_rsi()` en
`src/market/technical_indicators.py` hacía `loss.replace(0, np.nan)` —
cuando una ventana de 14 días no tenía NINGUNA pérdida, el RSI quedaba
indefinido en vez de calcularse.

**Diagnóstico cuantitativo de las dos causas distintas del NaN** (sobre
los parquets originales, antes de la corrección):
- 1,690 filas (36%): pérdida=0 PERO ganancia>0 (ventana sin pérdidas en
  absoluto). NO es ambiguo — RS=ganancia/0→∞→RSI=100 es el límite exacto
  de la fórmula de Wilder, igual que TA-Lib/pandas-ta. Esto era un bug,
  no una decisión de modelado.
- 3,009 filas (64%, concentrado en SAGAC1 con 2,153): pérdida=0 Y
  ganancia=0 (ventana totalmente plana, 0/0 verdaderamente indefinido,
  coincide con tramos de iliquidez/`is_no_trade`). Esto sí requería una
  convención explícita.

**Decisión (no es imputación — los datos de precio nunca faltaron, solo
el resultado de la fórmula en un caso límite):**
- pérdida=0, ganancia>0 → RSI=100 (corrección de fórmula, sin ambigüedad).
- pérdida=0, ganancia=0 → RSI=50 (convención "sin señal de momentum",
  no 100, porque ahí no hubo movimiento real que justifique fuerza
  alcista — coherente con que esos tramos ya están marcados `is_no_trade`).

**Implementado en** `src/market/technical_indicators.py::_rsi` (no en
R6) para que se mantenga consistente si se regenera `market_*.parquet`
directamente. Se recalcularon los 5 `data/interim/market_*.parquet`
existentes (sin volver a llamar a las APIs de BVL/Yahoo, solo
recomputando indicadores sobre el close ya descargado) y se regeneró
`dataset_unificado.parquet`. Resultado: NaN de `rsi_14` bajó de 27.5% a
solo el warm-up de las primeras 14 filas por activo (70 de 17,565,
0.4%) — el mínimo irreducible (no hay suficiente historia para una
ventana de 14 días en los primeros 14 días de cada serie).

**How to apply:** Esto ya está resuelto, no reabrir. Si una sesión
futura toca `_rsi()` de nuevo, mantener la distinción entre los dos
casos (no colapsarlos ambos a 100, que sería la convención más común
pero engañosa para los tramos `is_no_trade`).
