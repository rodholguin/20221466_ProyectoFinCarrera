---
name: project-oe1-plan-iliquidez
description: "Plan acordado (jul-2026, NO implementado) para tratar el riesgo #1 (iliquidez/ejecutabilidad) al construir el entorno DRL de OE1"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4d8057ad-f771-444f-9148-afcb5500f969
  modified: 2026-07-30T05:41:48.721Z
---

Plan de tratamiento del riesgo #1 (iliquidez y ejecutabilidad) para cuando se
construya OE1. **Nada de esto está en el código todavía.** Redactado completo en
`docs/riesgos_transversales_datos.txt`, Tier 1 #1, sección "PLAN DE TRATAMIENTO EN
OE1" — leerlo ANTES de diseñar el entorno.

**Diagnóstico:** NO es un problema técnicamente difícil. Los mecanismos son estándar
y ninguno exige datos que el proyecto no tenga. Es sobre todo cautela de modelado +
declaración explícita de supuestos.

Los 5 mecanismos, por relación esfuerzo/credibilidad:
1. **Ejecución en t+1** (observa cierre de t, transa al cierre de t+1).
2. **Prohibir transar en días no ejecutables** usando `is_no_trade`/`is_stale` →
   forzar *hold*. Las banderas ya están en el panel R6 justamente para esto; es la
   mitigación con mejor relación esfuerzo/credibilidad.
3. **Costo proporcional**: comisión SAB + tarifas BVL/Cavali/SMV (citar el tarifario
   publicado, no inventar cifras) + **spread como SUPUESTO declarado** — el spread
   domina en un mercado delgado y NO es observable (el endpoint BVL da solo cierre,
   sin puntas).
4. **Tope de posición/capacidad** (portafolio chico declarado; sin volumen no se
   puede calcular participación de mercado).
5. **PIEZA CENTRAL — costo de equilibrio (break-even):** reportar el desempeño sobre
   una grilla de costos (0/25/50/100 pbs ida y vuelta) e informar a qué costo el
   agente deja de superar al buy-and-hold. Convierte un parámetro incierto en un
   umbral de robustez evaluable en la sustentación.

**EL AGUIJÓN (decirlo antes de escribir conclusiones):** el riesgo no es que no se
pueda modelar, es que el tratamiento honesto **puede borrar la ventaja**. Si el edge
solo aparece a costo ~0, el hallazgo pasa a ser "no hay ventaja económicamente
explotable en la BVL con estas señales" — legítimo y reportable, pero cambia la
narrativa de la tesis.

**Sub-tarea barata pendiente (~10 min):** probar si existen los tickers Yahoo de los
5 activos nuevos (FERREYC1.LM, CPACASC1.LM, LUSURC1.LM, MINSURI1.LM, y el de
INRETC1) — hoy `yahoo: null` en config para todos ellos; solo CREDITC1.LM y
ALICORC1.LM están. Si traen volumen, el tope de capacidad pasa de supuesto a acotado
con datos. El close sigue siendo el de la BVL (Yahoo solo enriquece OHLC/volumen
donde ya hay fila BVL, ver `market_client._merge_bvl_yahoo`).

Ver [[project-riesgos-datos-pendientes]] (mitigaciones ya aplicadas al riesgo #1:
banderas + cambio de universo, piso de liquidez 4.1% → 56.5%) y
[[feedback-registro-mitigacion-riesgos]].
