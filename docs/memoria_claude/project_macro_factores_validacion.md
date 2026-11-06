---
name: project-macro-factores-validacion
description: "Validación empírica de los factores macro (ago-2026): oro se ELIMINA (0 de 7 activos), estaño RECHAZADO, TC+EMBI son el esqueleto; columnas globales le ganan a por-activo"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8f76166a-8158-4363-a0c7-c6a6c927dc95
  modified: 2026-08-22T17:51:29.975Z
---

## Factores macro: medidos, no supuestos (2026-08-22)

Doc completo: `docs/fundamento_macro_riesgo_politico.txt` §4 (método, resultados,
decisiones y limitaciones). Script: `scripts/probe_macro_exposicion.py`.
Log: `data/interim/probe_macro_exposicion.log`.

**Cambio de criterio**: un factor entra si tiene EFECTO MEDIDO en el universo
vigente, no si tiene una historia económica plausible. La sección 1 del doc los
había elegido por argumento, y al cambiar el universo la justificación del oro
quedó huérfana sin que nadie lo notara.

### Resultados (regresión multifactor rezagada 1 día, Newey-West)
| factor | significativo en |
|---|---|
| TC USD/PEN | **7 de 7** |
| EMBI Perú | 6 de 7 |
| cobre | 4 de 7 |
| petróleo WTI | 2 de 7 (Minsur, Ferreycorp) |
| **oro** | **0 de 7** |
| **estaño** | **0 de 7** |

### Decisiones
- **ORO -> ELIMINAR.** Su activo justificante (BUENAVC1) salió del universo y no
  tiene efecto en ninguno de los 7. Control de que el método sirve: sobre BVN el
  oro sale t=+5.57 y el cobre pierde significancia.
- **ESTAÑO -> NO agregar**, pese a que Minsur es #2 mundial. A Minsur lo mueve el
  COBRE (t=+5.62; Mina Justa). Matiz que importa: el BCRP solo publica estaño
  MENSUAL (PN01653XM), y eso no puede explicar retornos diarios -> el resultado
  es "esta serie no sirve", no "el estaño no importa".
- **PETRÓLEO -> en evaluación** (brazo de ablación R8). 2 de 8 al 5% es lo
  esperable por azar, aunque son justo los dos predecibles ex ante.
- **COLUMNAS GLOBALES ganan** a "una por activo": el único factor específico de
  un activo era oro/BVN y ya no está. Ver [[project-d11-representacion-sentimiento]].

### Dos hallazgos colaterales que importan
1. **La BVL reacciona con UN DÍA de retraso** y no es precio rancio (se verificó
   exigiendo que t-1 haya transado). Coincide con el horizonte de D13 (ejecutar
   en t+1). Falta ver si sobrevive a costos -> [[project-oe1-plan-iliquidez]].
2. **INRETC1 cotiza en US$** y se convierte con el TC del mismo día, así que
   `ret_PEN = ret_USD + ret_TC` POR CONSTRUCCIÓN. Su correlación positiva con el
   TC es aritmética, no económica. No es look-ahead, pero sí heterogeneidad ante
   una red compartida.

### Trampa técnica reutilizable
`is_stale` es **int64 (0/1), no bool**. `~` sobre entero es bitwise y da -1/-2:
como máscara booleana es una bomba silenciosa. Castear siempre.

**Why:** revierte dos recomendaciones que yo mismo había dado (agregar estaño,
columna por activo) y elimina una columna del panel.
**How to apply:** antes de agregar cualquier feature macro, medirla con
`probe_macro_exposicion.py` sobre el universo vigente.
