---
name: project-yahoo-volumen-confiabilidad
description: "Validación jul-2026 del volumen de Yahoo (.LM): es dato real pero PARCIAL, no reconcilia con la BVL. No usar como cantidad autoritativa ni para is_no_trade. Hallazgo lateral: la BVL sí expone puntas bid/ask."
metadata: 
  node_type: memory
  type: project
  originSessionId: de936975-c40d-400b-833b-b2213753a8d2
  modified: 2026-07-30T19:22:51.288Z
---

## Validación del volumen de Yahoo (.LM) — 2026-07-30

Motivo: la BVL (share-values) NO entrega volumen (`market_client.fetch_bvl` pone
`volume = NaN`). Yahoo era la única fuente candidata para acotar la capacidad de
OE1. Scripts: `probe_yahoo_nuevos.py`, `probe_yahoo_moneda.py`,
`probe_bvl_volumen.py`, `probe_yahoo_confiabilidad.py`, `probe_yahoo_vol_offset.py`,
`probe_yahoo_vol_diagnostico.py`.

### Lo que SÍ quedó confirmado
- **Los 5 tickers nuevos existen**: FERREYC1.LM, CPACASC1.LM, MINSURI1.LM,
  INRETC1.LM, LUSURC1.LM. Cobertura completa 2012-2025 (~3,500 filas).
- **Moneda correcta**: ratio close Yahoo/BVL crudo = 1.0000 en los 7 (482 días
  2024-25). INRETC1.LM viene en US$, igual que la capa cruda BVL → el manejo de
  `fetch_market:205-206` (`_to_pen` sobre bvl Y yah) ya es correcto y `_to_pen`
  no toca `volume`. NO hace falta código nuevo.
- **El volumen NO está inventado**: Benford MAD 0.0045-0.0068 (conformidad
  cercana/aceptable), 1-13% múltiplos de 100, repeticiones consecutivas 1.4-2.0%
  con run máximo 1-3. Sin huella de relleno sintético ni ffill.

### Lo que lo INVALIDA como cantidad autoritativa
1. **Ancla externa fallida.** La BVL sí publica volumen oficial, pero solo del
   ÚLTIMO día: `GET /v1/issuers/{cc}/value` → `listLastValue[].quantityNegotiated`
   y `.amount` (mismo endpoint que ya usamos para dividendos). En 2026-07-27 el
   close coincidió EXACTO en los 7, pero el volumen no, y sin dirección
   consistente: razón Yahoo/BVL = 0.159 (Minsur), 0.171 (InRetail), 0.184
   (Pacasmayo), 1.643 (Ferreycorp), 5.124 (Luz del Sur).
   Descartadas H1 (desfase de fecha: ninguna fecha vecina reproduce el número) y
   H2 (cambio de unidad: la razón no es constante).
2. **Ceros contradictorios.** En 5.1%-15.4% de los días en que el precio BVL
   CAMBIÓ, Yahoo reporta volumen 0. No es ruido de redondeo: el |retorno| mediano
   de esos días (0.77%-1.37%) es igual al del conjunto (0.81%-1.43%). Están
   repartidos en TODOS los años, no solo al inicio; en LUSURC1 empeoran hacia el
   final (2024: 44, 2025: 42). => Yahoo pierde operaciones reales de forma
   sistemática, y un 0 NO significa "no se negoció".
3. **Relación volumen-volatilidad casi ausente.** Spearman(|ret|, volumen)
   = 0.00-0.13 y mediana Q4/Q1 = 1.00 en Minsur, BCP e InRetail (excluyendo
   retornos exactamente 0). En un mercado real la relación es marcadamente
   positiva. Compatible con un feed muestreado/parcial.
4. **Filas fantasma**: ~93-103 filas por ticker en fechas que la BVL no cotizó
   (p.ej. 28-29 jul, Fiestas Patrias, con close arrastrado), de las cuales 6-19
   traen volumen > 0. Inocuas para el panel porque `build_trading_calendar` usa
   la BVL como calendario, pero confirman que el feed no es limpio.

### Decisiones que se derivan
- **NO** usar el volumen de Yahoo como cantidad negociada autoritativa.
- **NO** redefinir `is_no_trade`/`is_stale` sobre volumen (punto 2 lo refuta).
- El tope de capacidad de OE1 SIGUE siendo un supuesto declarado, no un dato.
  Ver [[project-oe1-plan-iliquidez]].
- Fuente correcta pendiente de evaluar: los boletines/informes bursátiles
  mensuales de la BVL (montos negociados oficiales por emisor, histórico).

### HALLAZGO LATERAL VALIOSO — las puntas SÍ son observables
El mismo `listLastValue` trae `buy` y `sell`. El plan de OE1 asumía que el spread
NO era observable ("el endpoint BVL da solo cierre, sin puntas"). Spread relativo
observado el 2026-07-27 (snapshot único, un solo momento):
ALICORC1 0.08%, INRETC1 0.13%, MINSURI1 0.14%, CPACASC1 0.63%, FERREYC1 0.70%,
CREDITC1 1.65%, LUSURC1 2.20%.
=> ida y vuelta ≈ **8 a 220 pbs**. La grilla de break-even planeada (0/25/50/100
pbs) se queda corta: debe llegar a ~250 pbs. Ver [[project-oe1-plan-iliquidez]].
Además `amount/quantityNegotiated` da el VWAP implícito del día.
Limitación: es un snapshot del último día, no una serie histórica. Un colector
diario de este endpoint construiría la serie hacia adelante (volumen + puntas).
