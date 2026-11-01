---
name: project-smv-wsdl
description: "Contrato real del WSDL SMV confirmado por sondeo — parámetros, RPJ codes, cobertura"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6b3cf012-0289-48a6-859c-e55c8474dca2
---

## Contrato WSDL SMV (confirmado junio 2026)

**URL:** `https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx?WSDL`

**Operaciones disponibles:**
- `obtener_BalanceGeneral` — Balance General (Situación Financiera)
- `obtener_GanciaPerdida` — Estado de Ganancias y Pérdidas
- `obtener_ResultadosIntegrales` — Resultados Integrales
- `obtener_FlujoEfectivo` — Flujo de Efectivo
- `obtener_CambiosPatrimonio` — Cambios en el Patrimonio
- `obtener_InfoFinanciera` — Resumen financiero (ActivoTotal, PatrimonioTotal, UtilidadNeta, etc.)
- `obtener_EFData` — Grid paginado (firma diferente: page/rows/sidx/sord/_search)

**Parámetros (todos los principales):**
- `Ejercicio`: str, año (e.g., "2023")
- `Periodo`: str, trimestre "1"-"4"
- `Tipo`: str, "I" (Individual) o "C" (Consolidada)
- NO hay parámetro empresa/nemonico — devuelve TODAS las empresas (~261)

**Filtro de empresa:**
- Usar campo `RPJ` en la respuesta (código único de registro)
- Fallback: coincidencia parcial en `NombreEmpresa`

**Códigos RPJ del universo:**
| Ticker   | RPJ    | NombreEmpresa SMV                          | Moneda |
|----------|--------|--------------------------------------------|--------|
| CREDITC1 | B80005 | BANCO DE CREDITO DEL PERU                  | PEN    |
| BUENAVC1 | B20003 | COMPAÑIA DE MINAS BUENAVENTURA S.A.A.      | USD    |
| ALICORC1 | B30006 | ALICORP S.A.A.                             | PEN    |
| SAGAC1   | 014313 | SAGA FALABELLA S.A.                        | PEN    |
| CORAREC1 | CI0003 | CORPORACION ACEROS AREQUIPA S.A.           | PEN    |

**Estructura de la respuesta (BalanceGeneral/GanciaPerdida):**
```json
{"RPJ":"B30006","TipoEmpresa":"...","NombreEmpresa":"ALICORP S.A.A.",
 "RUC":"20100055237","Ejercicio":"2023","TipoInformacion":"Trimestral Individual",
 "Trimestre":"4to Trimestre","Moneda":"Soles","Cuenta":"2D01ST",
 "DescripcionCuenta":"Ingresos de Actividades Ordinarias",
 "Monto1":1668693,"Monto2":1906933,"Monto3":6690567,"Monto4":7333173}
```

**Interpretación de Monto para GanciaPerdida:**
- Monto1 = trimestre actual
- Monto2 = mismo trimestre año anterior
- Monto3 = YTD acumulado del ejercicio actual
- Monto4 = YTD año anterior

**Para BalanceGeneral:**
- Monto1 = saldo al cierre del período actual
- Monto2 = saldo al cierre del período anterior

**Cobertura:** 2005-2023 completo sin gaps (confirmado con Alicorp)

**Caché:** cada llamada devuelve ~8MB (261 empresas). Implementado caché en disco en `data/raw/smv_cache/` (archivo JSON por operación+período).

**Why:** Endpoint no documentado públicamente, descubierto por sondeo directo con zeep.
**How to apply:** Usar `fetch_smv()` en `src/fundamentals/fundamentals_client.py` que ya implementa todo esto.
