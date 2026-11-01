---
name: project-r5-evaluacion-integral
description: LEER PRIMERO — OE2 (R3-R6) CERRADO el 2026-09-01; panel final 24,591x118 construido y verificado; lo que sigue es OE1 (entorno y agente)
metadata:
  node_type: memory
  type: project
---

**OE2 (R3-R6) ESTA CERRADO desde el 2026-09-01.** Handoff vigente:
`docs/PENDIENTES_R5.txt`.

**PANEL FINAL, construido y verificado:**
`data/processed/dataset_unificado.parquet` — 24,591 filas x 118 columnas, 7 activos,
2012-01-02 a 2025-12-31. Cero NaN en las 9 columnas del canal de sentimiento; cero filas
con fecha de conocimiento posterior a la fecha de la fila.

**La corrida de R5 se hizo** (8.5 h de GPU, gemma3:12b via tunel a xwing, 1.59 s/llamada,
error de parseo 0.0-0.3%). Resultado por activo (eventos / por año):
```
  CREDITC1 889/63.5 · INRETC1 499/35.7 · ALICORC1 258/18.4 · LUSURC1 217/15.5
  MINSURI1 154/11.0 · FERREYC1 123/8.8  · CPACASC1  97/6.9
```

**EL NUMERO QUE ORDENABA TODO ESTABA MAL, y para bien.** Se presupuestaba "2.9% del
corpus llega a features, ~564 eventos con signo, Ferreycorp 0.9/año". Lo medido: **2,237
eventos etiquetados**, 1,808 con signo, **Ferreycorp 8.8/año**, y la heterogeneidad
resulto **9.2x** en vez de 16.8x. El canal tiene mucha mas masa de la que se temia.

**VALIDACION CRUZADA que conviene tener a mano:** el modelo etiqueta 11.5% del corpus,
por encima del 7.2% de la anotacion humana, porque sobre-declara relevancia (precision
59.3%). Corrigiendo, las dos vias convergen: 2,237x0.593=1,327 vs 19,513x0.072=1,405
(6% de brecha). **No confundir el 11.5% del modelo con la relevancia real.**

**Polaridad real: 46.0% positivo, 34.9% negativo, 19.2% neutro.** El `neutral` definitivo
es **19.2%** — no el 57.9% de la anotacion ni el 23.3% estimado. D15 sigue justificada.

**SUPERADO EL 2026-09-03**: D2-D10 quedaron CERRADAS tras la reunion con el
especialista. Ver [[project-oe1-decisiones-cerradas]]. Texto original abajo.

**LO QUE SIGUE ES OE1**: entorno de RL y agente. Decisiones abiertas D4-D10 en
`docs/decisiones_pendientes_OE1.txt`, **ninguna bloqueada por datos**: funcion de
recompensa, observacion/ventana, normalizacion causal, costos de transaccion, dias sin
negociacion, tasa libre de riesgo y protocolo de evaluacion. Las tres criticas son D6
(look-ahead), D7 (costos: spreads medidos de 8 a 220 pbs) y D10 (protocolo, a fijar ANTES
de entrenar).

**Nada se ha commiteado todavia** — es todo agosto y el 1-set sin versionar.

Ver [[project-r5-d14-d15]], [[project-d17-perimetro-bcp]], [[project-d18-hechos-no-adoptados]],
[[project-d20-known-date-fundamentales]], [[feedback-deriva-decidido-implementado]].
