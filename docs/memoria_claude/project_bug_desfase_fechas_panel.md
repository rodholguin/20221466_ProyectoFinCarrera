---
name: project-bug-desfase-fechas-panel
description: "RESUELTO (2026-09-12): el endpoint share-values de la BVL etiquetaba cada cierre con el SIGUIENTE dia habil. Corregido en la ingesta, panel regenerado y revalidado contra Bloomberg (7/7). Deja una regla metodologica reutilizable."
metadata:
  node_type: memory
  type: project
  originSessionId: 81b0ed4e-b520-46f7-8270-b9d21c8b235d
  modified: 2026-09-12T20:26:04.363Z
---

## RESUELTO el 2026-09-12 — causa raiz aislada y corregida

**La causa NO era nuestra.** El endpoint
`/v1/stock-quote/share-values` de la BVL **etiqueta cada cierre con el
SIGUIENTE dia de negociacion**. Se confirmo consultando la API en crudo: devuelve
cadenas ISO sin ambiguedad, o sea no habia nada que malinterpretar.

    2a vuelta 2021 — Alicorp, mismo precio, etiqueta distinta
      Bloomberg     2021-06-04  6.82     2021-06-07  5.79  (-15.1%)
      share-values  2021-06-07  6.82     2021-06-08  5.79

**Corregido** en `corrige_etiqueta_bvl` (src/market/market_client.py): la fecha
verdadera de la fila i es la etiqueta de la fila i-1. `fetch_bvl` pide un colchon
de 10 dias hacia atras y recorta DESPUES de corregir.

**R3 y R6 regenerados.** R4 y R5 NO se tocaron: el etiquetado LLM de sentimiento
no depende de la fecha de la BVL, asi que lo caro no hubo que rehacerlo.

**Revalidado**, criterio pre-registrado corr(retornos) > 0.85: **7/7 PASAN**
(de 0.02-0.13 a 0.885-0.986). Prueba de evento: el desplome de la 2a vuelta cae
ahora el LUNES 2021-06-07 en Alicorp (-15.1%), BCP (-9.8%) y Ferreycorp (-15.3%).

## Efecto: el agente MEJORO

El panel iba RANCIO (no era look-ahead: era lo contrario), asi que el agente
resolvia un problema mas dificil que el real. Al corregir, accion relativa:
retorno -2.2% -> **+2.6%**, sharpe -0.53 -> **+0.18**, maxDD -7.0% -> **-4.2%**
(el mejor de la tabla). La accion absoluta casi no se movio. **Las conclusiones
cualitativas sobrevivieron todas**; solo cambiaron las cifras.

## La regla que deja, y es lo reutilizable

Sobrevivio a R3-R6 completos porque **todas las validaciones eran INTERNAS**
(rectangularidad, huecos, continuidad, reconciliacion BVL/Yahoo) y **un panel
corrido un dia es perfectamente consistente consigo mismo**.

> Toda serie temporal que entre al panel desde una API sin documentacion de su
> convencion de fechas se contrasta contra una SEGUNDA FUENTE por **correlacion
> de RETORNOS** y con una **prueba de evento** (una fecha donde se sabe que paso
> algo grande), no solo por niveles.

## Lo que sigue abierto

- [ ] **RE-MEDIR "la BVL reacciona con un dia de rezago"**
      ([[project-macro-factores-validacion]]). Se midio sobre el panel rancio,
      asi que pudo ser CONTEMPORANEO. D13 no se reabre (su argumento principal es
      la ejecutabilidad) pero pierde ese respaldo hasta re-medirlo.
- [ ] FERREYC1 2012-2013 da baja coincidencia incluso corrigiendo: es OTRO
      problema, probablemente el ajuste por acciones liberadas.

**Why:** fue el caso mas grave de [[feedback-deriva-decidido-implementado]] y la
regla de contraste externo es el antidoto concreto que dejo.
**How to apply:** las 16 corridas previas al 2026-09-12 estan en CUARENTENA; el
registro de configuraciones las distingue con el campo `panel` dentro de
`resultado`. Detalle completo en docs/hallazgos_desfase_fecha_bvl.txt.
Ver [[project-bloomberg-extraccion]].
