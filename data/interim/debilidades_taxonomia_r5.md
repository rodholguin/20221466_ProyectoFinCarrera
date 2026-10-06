# Debilidades de la taxonomía y del muestreo — R5

Documento de trabajo a partir de la anotación completa de las 550 filas de `muestra_r5_anotar.xlsx`.
No propone cambios para esta entrega: recoge lo que apareció al anotar, para resolverlo en la siguiente fase.

Resultado de referencia: **55 relevantes (10%) y 495 irrelevantes (90%)**. Toda observación de abajo hay que leerla contra ese desbalance.

---

## 1. Distribución: la taxonomía está desbalanceada al revés de como fue diseñada

| Bloque | Categoría | Filas |
|---|---|---|
| A (magnitud 1) | ma_reestructuracion | 13 |
| | crisis_evento_adverso | 7 |
| | regulatorio_material | 5 |
| | resultados | 4 |
| B (0.6) | estrategia_inversion | 11 |
| | operacional | 4 |
| | dividendo_capital | 2 |
| | **gobierno_corporativo** | **0** |
| C (0.3) | analisis_opinion | 9 |
| Z (0) | no_relevante | 151 |
| | indice_bursatil | 123 |
| | sector_macro | 114 |
| | mencion_incidental | 88 |
| | patrocinio_rse | 11 |
| | marketing_promocion | 9 |

La taxonomía dedica 9 de sus 15 códigos a lo relevante (55 filas) y 6 a lo irrelevante (495). El detalle fino está donde casi no hay datos y el grueso del corpus se comprime en cuatro casillas.

**Consecuencias medibles:**

- `B_gobierno_corporativo` no tiene ninguna fila. En macro-F1 su F1 es indefinido: hay que decidir *antes* de correr los modelos si se excluye del promedio o se cuenta como cero, porque la diferencia entre ambas opciones es de varios puntos.
- `A_resultados` (4) y `B_dividendo_capital` (2) no tienen soporte para reportar precisión por clase.
- Que `A_resultados` sea la categoría más escasa es contraintuitivo: los resultados trimestrales son el hecho más relevante para un inversionista. La causa es la fuente — prensa generalista (Gestión, El Comercio, La República) cubre resultados de forma esporádica. Si el objetivo del clasificador es señal financiera, el corpus está mal elegido antes que la taxonomía.

**Línea a explorar:** invertir la granularidad. Un solo código de abstención con subtipo opcional, y en cambio abrir A/B/C por materialidad (ver §6).

---

## 2. Etiqueta empresa–noticia: no es *data leakage*, es el criterio de asociación de MediaCloud

La sospecha es correcta en el síntoma y equivocada en el diagnóstico. *Data leakage* es contaminación entre entrenamiento y evaluación; aquí no hay entrenamiento. Lo que ocurre es que **MediaCloud asocia la nota a la empresa por el cuerpo del artículo, no por el titular**, y la muestra solo trae el titular. De ahí que el 88% de los titulares no nombre a la empresa.

Hay dos fenómenos distintos que conviene no mezclar:

**(a) Asociación legítima, invisible en el titular.** El cuerpo sí menciona a la empresa.
- Fila 9 y otras 35: notas de tipo de cambio, asociadas al BCP porque citan su cotización.
- Fila 154: "Credicorp incluyó acciones de InRetail y Ferreycorp para julio", en una fila de Alicorp — probablemente Alicorp figura en la lista completa.

**(b) Falsos positivos de coincidencia de cadena.** Aquí la etiqueta simplemente está mal.
- Fila 437: "Violeta Ferreyros sobre parodia a Trampolín a la fama" → homonimia con el apellido, nada que ver con Ferreycorp.
- Fila 50: "Accidente en mina Cobriza" en una fila de Buenaventura. Cobriza es de Doe Run.
- Filas 145, 244, 179, 345: el titular es de **otra** empresa del listado (Alicorp en fila de Pacasmayo, Pacasmayo en fila de Ferreycorp, Plaza Vea en fila de Saga, Tottus en fila de Ferreycorp).

**Riesgo concreto para la evaluación:** la fila 50 es la trampa más informativa de la muestra. Un modelo que no sepa quién opera Cobriza la clasificará como `A_crisis_evento_adverso` y estará equivocado por falta de conocimiento del mundo, no por fallo de criterio. Vale la pena reportar aparte cuántos errores son de ese tipo.

**Decisión pendiente:** si el pipeline final le entrega al modelo el cuerpo del artículo y no solo el titular, estas etiquetas cambian de significado y la referencia deja de ser válida. Hay que fijar la unidad de entrada antes de anotar de nuevo.

---

## 3. Duplicados: la unidad es el par (empresa, noticia), no la noticia

Seis titulares aparecen exactos en dos filas distintas, doce filas en total. Casi siempre con **empresas diferentes**:

- Filas 6 y 161: misma crónica de la BVL, una en Pacasmayo y otra en Luz del Sur.
- Filas 101 y 155: "El futuro TEC de las 10 Empresas Más Admiradas del 2023", en Alicorp y en BCP.
- Filas 350 y 534: mismo titular, **misma** empresa (Buenaventura) — esa sí es duplicación pura.

A esto se suman los casi-duplicados: las filas 75 y 191 cuentan la compra de Maestro por Sodimac con dos redacciones distintas.

**Implicación:** el acuerdo entre anotadores y las métricas se inflan levemente porque hay ítems que no son independientes. Es menor con 12 filas, pero si se amplía la muestra hay que deduplicar por hash del titular y decidir explícitamente si el par (empresa, noticia) o la noticia es la unidad de análisis.

---

## 4. Regulación general: el hueco más grande de la taxonomía

`A_regulatorio_material` exige una norma "que afecta **al negocio**". Eso deja sin casilla propia a toda la regulación sectorial, que hoy cae a `Z_sector_macro` con magnitud **cero** — es decir, se trata igual que una nota de farándula.

Ejemplos que quedaron en 0 y que un analista sí miraría:

- Fila 13: nuevas opciones de inversión para las AFP (sistema previsional).
- Fila 332: Perú fijará niveles mínimos de transgénicos en alimentos procesados.
- Fila 460: Indecopi fiscaliza call centers con IA (alcanza a todo el retail).
- Fila 541: condiciones de la suspensión perfecta de labores.
- Fila 24: la BVL rebaja 90% las tarifas de negociación del Índice de Buen Gobierno Corporativo.

El caso 24 muestra además que "afecta al negocio" y "afecta a la acción" son cosas distintas que la definición no separa: la rebaja abarata negociar el papel de Ferreycorp sin tocar su negocio de maquinaria.

En el otro extremo, la regulación sí entró como A cuando la empresa era el objeto identificable de la norma: filas 70, 214 y 499 (el conflicto tarifario Luz del Sur–Osinergmin–COES) y fila 340 (el Senace aprueba el EIA de San Rafael, mina de Minsur).

**Línea a explorar:** desdoblar en `regulatorio_sectorial` (magnitud baja, ~0.3) y `regulatorio_material` (1), o añadir un campo de **alcance**: empresa / sector / economía. El criterio que usé provisionalmente — "¿la norma nombra o singulariza a la empresa como destinatario?" — funciona, pero es una convención mía que no está escrita en ningún lado.

---

## 5. Polaridad de fusiones y adquisiciones: el problema no es el signo, es el rol

Las 13 filas de `A_ma_reestructuracion` quedaron todas en `neutral`. Eso no es una evasiva: **la evidencia empírica de estudios de evento dice que el retorno anormal del comprador es cercano a cero en promedio, mientras que el de la empresa adquirida es claramente positivo por la prima de control.** Adivinar el signo desde el titular no es posible; distinguir el rol, sí.

La taxonomía no registra si la empresa es compradora, comprada o vendedora, y esos tres casos tienen signos esperados distintos:

- Fila 468 — "Holcim adquirirá participación mayoritaria en Cementos Pacasmayo": Pacasmayo es **adquirida**, hay prima de control, signo esperado positivo.
- Fila 206 — "Alicorp adquiere la brasileña Pastificio Santa Amália": Alicorp es **compradora**, signo indeterminado.
- Fila 62 — "Minsur acuerda la venta de su operación minera en Brasil": Minsur es **vendedora**, el signo depende de si desinvierte un activo problemático o uno rentable, cosa que el titular no dice.

**Línea a explorar:** un campo `rol` (comprador / objetivo / vendedor / no aplica) permitiría derivar la polaridad por regla en vez de pedírsela al anotador, y de paso da una hipótesis contrastable contra datos de mercado.

---

## 6. Tipo de evento y materialidad están colapsados en un solo eje

Esta es la observación más fuerte de todas y el caso 478 la ilustra perfectamente.

Fila 478: "Callao: roban equipos electrónicos en Plaza Vea de Bellavista". Es un hecho concreto de la empresa y encaja en la definición de `A_crisis_evento_adverso` ("accidente, derrame, fraude, investigación, sanción"). Pero recibe **magnitud 1, la misma que una toma de control**. Un robo de unos miles de soles en una tienda no mueve el valor de InRetail. Lo mismo con la fila 482 (robo en una botica del grupo).

Compárese dentro de la misma categoría A:

| Fila | Hecho | Magnitud asignada | Materialidad real |
|---|---|---|---|
| 478 | Robo en una tienda | 1 | despreciable |
| 76 | Orden de compensar a clientes por precios mal publicados | 1 | baja |
| 382 | Denuncia de daño ambiental contra Pucamarca | 1 | media-alta |
| 391 | China Three Gorges compra Luz del Sur | 1 | máxima |

La taxonomía actual pregunta *qué tipo de hecho es* y usa la respuesta como proxy de *cuánto importa*. Son dos preguntas distintas y el proxy falla en las colas.

**Línea a explorar:** dos ejes independientes.

1. **Relevancia** (binaria o de tres niveles): ¿el titular reporta un hecho cuyo sujeto es la empresa?
2. **Tipo de evento**: resultados, M&A, regulatorio, operacional, capital, gobierno, crisis, análisis.
3. **Materialidad** (alta / media / baja): magnitud esperada del efecto.

Anotar tres campos simples es más rápido y más confiable que elegir entre 15 códigos, y además permite calcular métricas por eje: un modelo puede acertar la relevancia y fallar la materialidad, y hoy eso es invisible.

---

## 7. Categorías cuya frontera tuve que fijar por convención

Ninguna de estas reglas se deduce del texto de la hoja `Taxonomia`. Las apliqué de forma consistente, pero **si no entran al prompt como codebook, el modelo será penalizado por no adivinarlas**, y eso no es clasificación sino telepatía. Afectan a unas 150 filas.

| Frontera | Regla aplicada | Filas afectadas |
|---|---|---|
| Tipo de cambio | `Z_mencion_incidental`: el BCP es fuente de la cotización | ~36 |
| Mercado en bloque vs. la acción propia | Valorizaciones y rankings del conjunto → `Z_indice_bursatil`; juicio sobre la acción de **esa** empresa → `C_analisis_opinion` (contraste: fila 68 vs fila 227) | ~15 |
| Estudios firmados por la empresa | `Z_mencion_incidental`: la empresa es autor, no objeto (filas 103, 140, 251, 509, 510) | ~8 |
| Instructivos de producto | `Z_marketing_promocion` (filas 156, 201, 269, 514, sobre Yape) | ~6 |
| Avisos de servicio eléctrico | Corte programado → `Z_mencion_incidental`; apagón imprevisto → `A_crisis_evento_adverso` (fila 318) | ~5 |
| M&A vs. inversión | Suma capacidad al propio negocio → B; cambia el perímetro del grupo → A (fila 476 vs fila 62) | ~14 |
| Polaridad de M&A | Siempre `neutral` | 13 |

---

## 8. Calidad del texto de entrada

- **Cinco titulares cortados a media palabra**: filas 110, 250, 372, 418 y 531. Ejemplo, la 531: "Tiendas Paris: ¿Por qué Cencosud decidió cerrar su operación en Perú y" — la información que decide la clasificación puede estar justo después del corte.
- **Trece titulares con cadenas SEO** separadas por pipes, que mezclan tags de sección con el titular real. Ejemplo, la fila 1: "Gratificación | cuentas CTS | depósito a plazo fijo | ... | TU-DINERO". Aquí el ruido no impide clasificar, pero sí infla la longitud y puede desviar a modelos pequeños.
- **46 filas sin URL** (8%), lo que impide verificar el titular contra la fuente si aparece una duda.
- La longitud va de 23 a 218 caracteres sin ningún tope sistemático, así que **el truncamiento no viene de un límite de campo** sino de la extracción. Vale revisar el scraper antes de ampliar la muestra.

Sobre "no delimitar tanto": ampliar la ventana de texto sí resolvería los cortes, pero cambia la tarea. Con titular solo, se mide clasificación con información escasa y las etiquetas de §2 son coherentes. Con titular + bajada, o con el cuerpo, muchas de las filas hoy clasificadas como `Z_mencion_incidental` pasarían a ser relevantes, y **la referencia entera habría que rehacerla**. Es una decisión de diseño, no una corrección.

---

## 9. Cosas a fijar antes de correr los modelos

1. Decidir el tratamiento de `B_gobierno_corporativo` (categoría vacía) en el macro-F1.
2. Publicar los baselines triviales junto a los resultados: responder siempre "irrelevante" acierta **90%** en relevancia; responder siempre `Z_no_relevante` acierta **27.5%** en las 15 categorías.
3. Decidir si las reglas de §7 entran al prompt como codebook (se mide clasificación) o no (se mide adivinanza de convenciones, y hay que declararlo).
4. Correr las métricas con y sin las 106 filas marcadas con `duda`: la diferencia estima cuánto se degrada la tarea cuando el titular solo no alcanza.
5. Reportar aparte la tasa de salidas inválidas de los modelos locales (categorías inventadas, nombre en vez de código)
