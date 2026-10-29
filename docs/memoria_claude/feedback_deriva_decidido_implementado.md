---
name: feedback-deriva-decidido-implementado
description: "Riesgo recurrente en este proyecto — decisiones bien documentadas que el código nunca aplicó, y constantes calibradas que no se revalidan al cambiar el universo"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e9a825e5-240a-47f4-9395-4b226c9107f0
  modified: 2026-09-01T21:42:58.003Z
---

**Patrón encontrado TRES VECES el mismo día (2026-09-01).** Registrado como riesgo
transversal propio en `docs/riesgos_transversales_datos.txt` §Tier 1 punto 0.

Una decisión se toma, se documenta bien, y **el código sigue haciendo lo de antes**. O una
CONSTANTE se calibra contra el universo del momento y el universo cambia sin que nadie la
revalide. En ninguno de los dos casos falla nada: el pipeline corre, no hay excepción, los
números salen. Por eso es de Tier 1 — no lo atrapa ninguna prueba, solo una revisión
deliberada, y puede meter look-ahead o features muertas en el panel final.

Las tres instancias:
- `_FILING_LAG_DAYS = 40` calibrado contra 5 emisores; **InRetail entró después** y
  presenta a 43-47d → 5-7 días de LOOK-AHEAD por trimestre. Al re-medir: 4/109 → 25/130.
- `macro_oro` seguía entrando al panel pese a "ORO → ELIMINAR" desde ago-2026. Causa de
  fondo: **dos fuentes de verdad** — el listado de `config.yaml` (decorativo, nadie lo lee)
  y el dict `_SERIES` de `macro_client.py` (el que manda). Divergieron un mes.
- `config.yaml: llm_model` seguía en gemma3:4b cuando la selección había elegido
  gemma3:12b.

**Why:** el proyecto acumula constantes calibradas (lags, listas de series, diccionarios
de nombres, tablas de cobertura) que viven lejos de la evidencia que las justifica. Cuando
cambia el universo o se cierra una decisión, es fácil actualizar el documento y olvidar el
código — o al revés. El propio doc del macro ya había diagnosticado el patrón sin darle
nombre: *"cuando el universo cambió, la justificación de al menos un factor dejó de
aplicar y NADIE LO NOTÓ."*

**How to apply:** al tocar el universo o cerrar una decisión con efecto en datos, revisar
la lista explícita de §Tier 1 punto 0: `_calibra_lag` (R4), `_SERIES` en macro_client.py
(R6), `NOMBRES_EMISOR` en emisores.py (R5), `_build_query` en mediacloud_client (R5),
`_PE_ARTIFACT_PERIODS` (R6), y las tablas de eventos de D11 y del expediente de R5.
Preferir **calcular** la constante a fijarla (como `_calibra_lag`, que se autocalibra por
emisor: un activo nuevo se resuelve solo) y poner **guardas que fallen temprano** donde el
artefacto viejo sería indistinguible del vacío. Al revisar código de este proyecto,
sospechar de toda constante que lleve un número calibrado en un comentario.

Ver [[project-d20-known-date-fundamentales]] y [[project-macro-factores-validacion]].
