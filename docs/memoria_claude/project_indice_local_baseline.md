---
name: project-indice-local-baseline
description: "El índice local de D10 es SPBLPGPT (S&P/BVL Peru General Total Return PEN); MSCI reemplazó a S&P el 1-sep-2025 y los índices nuam NO tienen historia."
metadata: 
  node_type: memory
  type: project
  originSessionId: 272f238a-320e-4ecd-91d0-d2d9e9a05591
  modified: 2026-09-09T00:48:27.597Z
---

Cierra el baseline "índice local" de **D10** (ver
[[project-oe1-decisiones-cerradas]]). Detalle en
`docs/estado_extraccion_bloomberg.txt` §3.

**EL TICKER ES `SPBLPGPT Index`** — S&P/BVL Peru General **Total Return PEN**,
sucesor del IGBVL. Retorno total y en soles, que es justo lo que se necesita:
el panel usa `close_total_return`, y comparar contra un índice de PRECIO le
quita al baseline sus dividendos y sesga la comparación A FAVOR del agente.

### Por qué no aparecía buscando "Peru" en el terminal
**La BVL cambió de proveedor de índices: MSCI reemplazó a S&P el 1-sep-2025**
(el Selectivo, el 27-ago-2025). Los nuevos son *MSCI nuam Peru General* y
*MSCI nuam Peru Select Capped 15%*.

**`MXNUPESE Index` (MSCI nuam Peru Select) está DESCARTADO**: se bajó y su
primer dato es **2025-08-27**, 275 filas, nada antes. No hay historia ni real
ni reconstruida. La discontinuación de S&P cae al FINAL de la muestra, así que
SPBLPGPT debería cubrir 2012 → ago-2025.

**Verificar igual con `HP` desde 1/1/2010**: S&P tomó el cálculo del IGBVL
alrededor de 2015 y la versión TR podría tener historia reconstruida. Regla
suficiente, sin buscar disclaimers: *todo dato anterior a la fecha de
lanzamiento es back-calculado por definición* — se puede usar, pero se DECLARA.

### Truco útil, sirve para cualquier índice
`TOT_RETURN_INDEX_GROSS_DVDS` lo **calcula Bloomberg** sobre cualquier índice
del que tenga dividendos, sin depender de que el proveedor publique variante TR.
Pedirlo junto a `PX_LAST`: si salen iguales el índice ya es TR; si va por
encima, la brecha anualizada debe rondar el dividend yield (3-4%).

### Otros candidatos, medidos
- **`ETFPERUD`** (VanEck El Dorado Peru ETF, BVL, marzo 2021, USD): replica al
  S&P/BVL Perú Select. Muy corto para el horizonte, pero como baseline
  invertible del tramo final es **más honesto que EPU** — es local y no tiene
  ni el quiebre metodológico del 10-abr-2023 ni el ~66% de tenencias pure-play.
- **`^SPBLPGPT` figura en Yahoo Finance**: si tiene historia, el índice local
  sale GRATIS. Probar con `yfinance`, que ya está en el proyecto.

**Why:** se perdió tiempo de terminal buscando un índice que ya no existe con
ese nombre, y el reemplazo no sirve para 2012-2025.
**How to apply:** como BASELINE, cualquier índice Select está perfecto. Como
REGRESOR sería parcialmente circular por solaparse con los 7 activos — el mismo
reparo que el plan §7.1 ya le puso a EPU. Ver
[[project-bloomberg-extraccion]] y [[project-universe-decision]].
