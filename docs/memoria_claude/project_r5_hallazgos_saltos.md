---
name: project-r5-hallazgos-saltos
description: La taxonomía R5 VALIDADA contra precio (p=0.006); hechos NO reemplazan prensa; Pacasmayo tiene ADR en NYSE sin usar
metadata: 
  node_type: memory
  type: project
  originSessionId: 57b248e7-4256-4f44-b7db-35d8d1f31350
  modified: 2026-08-30T06:21:38.176Z
---

Documento: `docs/hallazgos_saltos_y_fuentes_R5.txt` (2026-08-30). Cinco hallazgos de
la sesión, independientes de la decisión pendiente sobre Hechos de Importancia.

**H1 — el más importante para la tesis.** Primera evidencia dura de que la taxonomía
de R5 funciona: las noticias anotadas como relevantes coinciden con |z|>2 el 34.8%
de las veces contra 18.4% de base (**p=0.006**); las irrelevantes son indistinguibles
del azar (p=0.19). En julio la correlación nula no probaba nada porque el corpus era
74% ruido. **M&A es la categoría más asociada al precio** (60% con |z|>2, p=0.004) — y
es la que va entera a `neutral`. `crisis_evento_adverso` tiene magnitud 1.0 y está
POR DEBAJO de la base: recalibrar el tramo después de la corrida (gratis con D15).

**H2 — NO reemplazar la prensa por los hechos.** Los hechos no explican los saltos
(lift 1.25-1.32) y pierden contra la prensa ETIQUETADA (1.89). Lo valioso de la prensa
es el trabajo del LLM. Sumarlos sigue en pie; reemplazar no. Consideración de tesis a
conversar con el asesor: si el canal pasa a un feed regulatorio con códigos oficiales,
el rol del LLM se reduce.

**H3 — principio point-in-time, planteado por el autor.** NO se re-fechan las noticias
al momento "real" del evento: si salió tarde, salió tarde, y moverla es look-ahead. El
hecho es otra observación con su propia fecha; ambas conviven. Una bandera de novedad
sí es legítima porque mira hacia atrás.

**H4 — los saltos sin fuente son el 4%, no el 25%.** El 61% son movimiento común de
mercado y el 64% tienen precio stale previo. Ex-dividendo y calendario descartados.

**H5 — fuentes no consideradas.** La accionable: **Cementos Pacasmayo cotiza en NYSE
como `CPAC` desde feb-2012** (1 ADS = 5 acciones) y es el activo con más saltos sin
fuente (35). La serie NO está en el repo (`yahoo: null` en config.yaml). Bajarla y
medir es una tarde. Ojo: usar solo el cierre del ADR del día ANTERIOR o es fuga.
También: ventanas de reclasificación MSCI (14-ago-2015 la BVL cayó 5.25%), y retiros
de AFP (Minsur el más golpeado, −2.2%, pero confundido con las elecciones de 2021).

**H6 — el universo es consistente (verificado a pedido del autor).** Objetó que
Pacasmayo cotice en NYSE cuando Buenaventura salió por eso. Medido: el ADR de Pacasmayo
(CPAC) mueve **US$47 mil/día** de mediana contra ~US$235 mil/día en Lima → **82% se
negocia en Lima, el ADR es nominal**. El de Buenaventura (BVN) mueve **335x más**. El
criterio real del universo fue frecuencia BVL (BUENAVC1 25.0% vs CPACASC1 95.5%), no
"tiene ADR". Esto **degradó H5.a**: el ADR es demasiado fino para explicar los 35 saltos
sin fuente de Pacasmayo. Y sobre CREDITC1 (BAP mueve ~1,200x): ya estaba decidido y
documentado en el registro de riesgos — los cross-listed NYSE son "fuera de premisa" y
la delgadez de CREDITC1 ES la premisa de la tesis, no un defecto.

Ver [[project-r5-evaluacion-integral]] (decisión pendiente) y [[project-r5-d14-d15]].
