---
name: project-r5-d14-d15
description: "D14, D15 y D16 CERRADAS (2026-08-29/30); premisa de D15 corregida: masa neutral real 23.3%, no 57.9%"
metadata: 
  node_type: memory
  type: project
  originSessionId: e9a825e5-240a-47f4-9395-4b226c9107f0
  modified: 2026-08-30T19:42:27.239Z
---

Todo en `docs/decisiones_pendientes_OE1.txt`.

**D14 (eje `alcance`) — MEDIDA Y DESCARTADA.** Al factor 0.3 NO aumenta la masa de
magnitud (0.98x estricta / 1.10x amplia): lo que entra (+6.87) se cancela con lo que el
propio eje degrada (−7.56). Y empeora la heterogeneidad entre activos de 16.5x a 30.0x.
Reproducible: `python scripts/mide_impacto_d14.py`. Las filas 247 y 320 se quedan en
`C_analisis_opinion` a 0.3; la regla (iii) de la fila 68 se retiró del texto de anotación.

**D15 — DECIDIDA (viene del ASESOR).** La magnitud deja de ser multiplicador y queda
solo como puerta de relevancia; el canal pasa a 9 columnas `sent_{pos,neu,neg}_ewma_{5,20,60}`.
Brazo de ablación R8: 18 columnas. El sesgo estaba en el COLAPSO, no en los números —
la normalización causal por columna de D6 borra cualquier factor de escala constante.
**D11 enmendada, D12 ABSORBIDA.**

**CORRECCIÓN DE LA PREMISA DE D15 (2026-08-30) — la decisión NO cambia, su tamaño sí.**
El 57.9% de masa `neutral` que justifica D15 está medido sobre la ANOTACIÓN HUMANA, que
aplica la convención del autor "M&A siempre neutral". El pipeline NO hace eso: el prompt
v2.1 pide polaridad libre al GRUPO A y el modelo se moja (7 `positivo` / 4 `neutral` en
los 11 M&A de las 550). Masa ponderada Hájek entre relevantes:
  anotación → neutral 62.0% / negativo 20.9% / positivo 17.1%
  modelo (muestra) → positivo 45.7% / negativo 31.0% / neutral 23.3%
  **CORRIDA COMPLETA (2026-09-01, definitivo)** → positivo 46.0% / negativo 34.9% / **neutral 19.2%**
Al escribir la tesis hay que citar **19.2%** (cifra de la corrida completa), no 57.9% ni 23.3%. D15 no se reabre: 23.3% tirado
sigue siendo mucho, la columna cuesta cero y el argumento del asesor es independiente
del tamaño. Pendiente menor: la tabla de "eventos esperados por celda" (1,387 / 39-407-232)
hereda el mismo problema y hay que rehacerla contra la corrida definitiva.

**D16 (polaridad de M&A por `rol`) — CERRADA 2026-08-30: MEDIDA Y DESCARTADA en su forma
automática.** Ver [[project-r5-d16-piloto-rol]] para la evidencia completa.

Bug latente a arreglar al implementar D15: `_align_sentiment_to_calendar` promedia por
`n_articles` en el roll-forward; las columnas de conteo deben SUMARSE.

Modelo elegido: **gemma3:12b**. Ver [[project-r5-evaluacion-integral]] para lo abierto.
