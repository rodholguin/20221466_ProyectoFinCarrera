---
name: project-r5-d16-piloto-rol
description: "D16 cerrada: la regla objetivo→positivo vale (oráculo 62% vs 31%) pero gemma3:12b no extrae el `rol`; producción sigue en v2.1"
metadata: 
  node_type: memory
  type: project
  originSessionId: e9a825e5-240a-47f4-9395-4b226c9107f0
  modified: 2026-08-30T19:42:48.087Z
---

**D16 CERRADA el 2026-08-30 — medida y descartada en su forma automática.**
Evidencia en `docs/decisiones_pendientes_OE1.txt` → D16 §MEDICIÓN.
Reproducible: `python scripts/piloto_rol_d16.py --model gemma3:12b --versiones v22,v23`.

**La regla es buena; la extracción no.** Acierto de dirección sobre los 13 titulares del
arco (r+20d, umbral ±2%):
```
  oráculo (rol a mano)          8/13 = 62%   <- techo de D16
  D16 con v2.2                  4/13 = 31%
  D16 con v2.3                  2/13 = 15%
  polaridad libre de v2.1       4/13 = 31%   <- lo que ya hace el pipeline
  convención "todo neutral"     2/13 = 15%
```
Con el rol correcto la dirección DUPLICA al pipeline. Con el rol que produce
gemma3:12b, D16 empata con no hacer nada — y en Pacasmayo es peor (v2.1 daba
`positivo` solo; v2.2/v2.3 lo bajan a `neutral`).

**Dos formulaciones probadas, dos fracasos en direcciones OPUESTAS.** v2.2 (glosa corta)
no daña la tarea principal (empate; el modo de falla de D14 no se repite) pero detecta
1/3 objetivos. v2.3 (desambiguación "qué cambia de dueño", escrita para arreglar v2.2)
detecta 0/3, rompe 3 casos que v2.2 tenía bien, y sí daña: −9.2pp de precisión de
relevancia y +8.5pp de polaridad espuria. Held-out de 456 titulares confirma que la
deriva es sistemática (`objetivo` 13.3% → 4.2%), no ruido de n=13.
Los dos errores que matan la regla: Pacasmayo (+61%, z=22) sale `vendedor`/`comprador`;
el reordenamiento interno de Luz del Sur (−3.00%, z=−7.7) sale `objetivo` en v2.2.

**Riesgo descartado de paso:** el PASO 1 NO rompe el arco de noticias. v2.2 mantiene
13/13 como M&A y rescata 3 que v2.1 mandaba a `mencion_incidental`.

**Hallazgo colateral que vale por sí solo:** la venta de Luz del Sur es un ARCO de 7
titulares (ene–oct 2019), no un evento puntual; el precio subió +43% ANTES del anuncio y
+128.6% en 2019. El salto de +41.10% fue el 1-oct-2019 con el hecho BVL del 30-set,
mientras el titular de prensa llegó el 15-oct — 10 sesiones tarde. Refuerza el caso de
los Hechos de Importancia.

**Dato de infraestructura verificado:** la corrida definitiva de R5 sobre los 7 activos
(19,528 artículos) NO EXISTE. Los únicos cachés completos son `cache_*.json` del 9-jul,
prompt v1 y universo VIEJO. Todo lo v2.1 son pilotos de 180 ítems.

**Si se quiere recuperar el 62%**, con criterio pre-registrado (3/3 objetivos, 0 falsos):
(1) asignar el rol a mano sobre ~130 artículos, ~1 h, no reproducible sobre datos nuevos;
(2) piloto Gemini, 10 min, falta API key. Ninguno bloquea.
**NO gastar más GPU en prompts locales.** Producción sigue en v2.1; `src/sentiment` nunca
se tocó (v2.2/v2.3 viven dentro del script).

Ver [[project-r5-d14-d15]] (incluye la corrección de la premisa de D15) y
[[project-r5-evaluacion-integral]].
