---
name: project-d11-representacion-sentimiento
description: "D11 (representación del sentimiento) CERRADA el 2026-08-18: polaridad categórica + magnitud por taxonomía ex-ante + decaimiento por EWMAs pos/neg x 3 escalas. D1 cerrada (portafolio). D12 abierta (magnitud fija vs aprendida por tramo)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6a97b3f6-eead-4573-bd12-b3dd14cb518f
  modified: 2026-08-18T16:33:44.050Z
---

## D11 — CERRADA por el autor el 2026-08-18 (ya NO está en deliberación)

Registro completo: `docs/decisiones_pendientes_OE1.txt` → D11.
Taxonomía y tratamiento de la relevancia: **`docs/taxonomia_eventos_R5.txt`**
(creado 2026-08-18). D11 fija el MECANISMO; ese doc fija el CONTENIDO.

### Lo decidido
- **(i) polaridad categórica** {pos, neutral, neg} — adoptada. Fuera el score continuo.
- **(ii) magnitud por TAXONOMÍA de eventos ex-ante** — adoptada. 14 categorías en
  4 tramos (1.0 / 0.6 / 0.3 / 0.0). El LLM clasifica el TIPO (tarea objetiva); la
  magnitud la fija el autor. Las categorías de magnitud 0 SON el filtro de
  relevancia y la abstención.
- **(iii) decaimiento por k EWMAs ponderadas** (opción C), NO τ libre. Razón doble:
  los pesos entran linealmente (bien condicionado) **y** una mezcla de 3
  exponenciales representa MÁS formas que una sola (p. ej. caída rápida con cola
  larga). C domina a A en las dos dimensiones — no es premio de consuelo.

### Forma del feature (fusiona i+ii+iii)
`sent_pos_ewma_{5,20,60}` y `sent_neg_ewma_{5,20,60}` = **6 columnas**. Pos y neg
SEPARADOS: una serie firmada colapsa (buena+mala = 0 = "no pasó nada") y prohíbe la
reacción asimétrica. Se calcula en **R6/build_dataset**, no en R5 → recalibrar
vidas medias o magnitudes NO exige re-pagar el LLM. Se conservan las 4 columnas
crudas actuales.

### Dos decisiones estructurales que matan el error dominante
La polaridad **solo se pide si la categoría tiene magnitud > 0**, y se fuerza en
código (categoría cero → polaridad null, diga lo que diga el modelo). Esto elimina
por construcción la polaridad espuria (49% de las etiquetas con signo). Ver
[[project-r5-sentiment-status]].

### D1 también quedó CERRADA (2026-08-18): agente de PORTAFOLIO
Es el eje central de la tesis (diversificación), por encima de la conveniencia
estadística. Cascadea: D2 → vector de pesos continuo; D3 → PPO/SAC/TD3.
CONSECUENCIA: la red es una sola y comparte pesos entre 7 activos muy heterogéneos
en prensa (BCP 577 eventos vs Minsur ~74). Mitigación decidida: (1) normalización
causal **por activo** — coste cero, ya la exige D6 — (2) feature de régimen de
cobertura, (3) embedding por activo solo como último recurso (sobreajusta).
**Criterio de abandono fijado por el autor: si el canal no supera al baseline en
la ablación de R8, no se toma.**

### La tabla de eventos del universo viejo estaba obsoleta
BUENAVC1 (69), SAGAC1 (41) y CORAREC1 (33) SALIERON del universo — los tres peores.
Medidos quedan solo CREDITC1 577 y ALICORC1 131. Para los 5 nuevos **no hay corpus
descargado**: los 4 probes de MediaCloud usan `story_count` (devuelve un entero),
ninguno llama a `story_list`. Extrapolación optimista (regla de tres con Alicorp):
CPACASC1 ~480, INRETC1 ~400, FERREYC1 ~170, LUSURC1 ~95, MINSURI1 ~74 — optimista
porque son conteos CRUDOS de queries sueltas ("Pacasmayo" matchea la provincia).

### D12 — ABIERTA (diferida a datos, no bloquea R5)
¿Etiquetar solo el TRAMO y que el agente aprenda el peso, en vez de magnitud fija?
Es coherente (mismo principio que (iii)) y **D1=portafolio la vuelve viable**: los
pesos se estiman con los 7 activos agrupados (~950 eventos post-limpieza / 6 celdas
≈ 160 por celda, para un peso lineal). Costo: partición vs agrupación, y 18 columnas
por activo en vez de 6. Se decide con los conteos reales y se compara como brazo de
ablación en R8. Default = magnitud fija.

**Why:** el autor cerró D11 tras discutir el mecanismo; retomar no debe re-litigar
lo decidido, solo ejecutar y resolver D12 con datos.
**How to apply:** implementar la taxonomía y el prompt v2 según
`docs/taxonomia_eventos_R5.txt`; medir los conteos SIN LLM antes de clasificar.
