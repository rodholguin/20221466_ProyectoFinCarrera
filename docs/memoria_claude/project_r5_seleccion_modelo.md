---
name: project-r5-seleccion-modelo
description: "Selección del clasificador de R5 (ago-2026): 5 modelos ANIDADOS e INDISTINGUIBLES a n=180; referencia no-humana + muestra sin potencia. Plan cerrado: refetch → 550 anotaciones del autor"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6a97b3f6-eead-4573-bd12-b3dd14cb518f
  modified: 2026-08-22T00:00:00.000Z
---

## Selección del modelo de R5 — estado al 2026-08-19

**Handoff completo: `docs/PENDIENTES_R5.txt`.** Registro de la decisión:
`docs/seleccion_modelo_R5.txt` (documento vivo; §1B es lo más importante).

### BLOQUEANTE #1 — la "anotación humana" NO es humana
Lo detectó el AUTOR preguntando quién había anotado. Las 180 etiquetas de
`data/interim/r5_validacion_anotada.csv` las produjo **el asistente**, no una
persona. Evidencia triple: el doc de julio lo dice ("un solo anotador
(asistente)"), los timestamps dan **1.55 s/ítem** (4m39s para 180), y las
columnas se llaman `rel_humana`/`sent_humano` — el nombre es la causa del error.

**El asistente afirmó varias veces por escrito que era anotación humana y
construyó sobre eso un argumento circular** ("un humano lo logró desde el
titular, luego falta capacidad"). Corregido en los 4 docs.

- SOBREVIVE (medido contra mercado/estructura, no contra anotaciones): índice
  acierta signo 50.5%; ventana de evento plana T-2..T+2 (D13); duplicados;
  volumen de queries; **el anidamiento** (es propiedad entre modelos, no
  depende del ground truth).
- DEBILITADO: relevancia 26%, kappa 0.32, espuria 49%, y TODAS las métricas de
  comparación de modelos. Ordenan, pero no miden acierto.
- SESGO NUEVO: evaluar modelos comerciales contra referencia hecha por un
  modelo comercial favorece a los que razonan como el anotador.
- FIX: el autor anota 60 a ciegas (~30-45 min) y la decisión final se toma
  sobre su criterio.

### Barrido local TERMINADO — 5 modelos, 2 familias, 4B a 32B
Tabla viva: `python scripts/compara_modelos_r5.py [--md]`
- **qwen2.5:32b** lidera el criterio principal: precisión 82.6%, espuria 18.8%,
  0% parseo. PERO recall 35.2% → Minsur ~26 eventos de train, insuficiente.
- **gemma3:4b** es el opuesto: recall 77.4%, precisión 57.7%.
- gemma3:12b 81.5%/41.5%; gemma3:27b 65.0%/48.1%; qwen2.5:14b 69.6%/29.6%.
- **Escalar NO ayudó**: 27b empeoró respecto de 12b.
- **Solo la familia qwen usa `no_relevante`.** Ningún gemma la usó nunca, con
  ningún prompt — era rasgo de familia, no de capacidad.

### HALLAZGO QUE CIERRA UNA VÍA: los modelos están ANIDADOS
`scripts/analiza_ensemble_r5.py`: unión de dos modelos = el más inclusivo
EXACTO; intersección = el más excluyente EXACTO. Los positivos de uno son
subconjunto estricto de los del otro. **No aportan información distinta: ordenan
igual y solo cambian dónde cortan.** Voto mayoritario de 4 es peor que el mejor
individual. **El ensemble está descartado — no volver sobre él.**

### 2026-08-22 — SEGUNDO problema con la validación: NO HAY POTENCIA
Independiente de quién anotó. Contra la referencia actual (n=180) los IC 95% de
los cinco modelos **se solapan entre sí**: precisión 57.7%±11.5 (4b), 81.5%±14.7
(12b), 65.0%±14.8 (27b), 69.6%±18.8 (14b), 82.6%±15.5 (32b). El 82.6% que
lideraba se estima sobre **23 ítems marcados**. Anotar solo 60 habría dado "no
se puede saber". Por eso la muestra sube a ~550.

### Diseño de la anotación del autor (decidido 2026-08-22)
`scripts/muestra_validacion_humana_r5.py` → Excel con desplegables + CSV de clave
ciega en `data/interim/validacion_humana/`.
- **Bloque A (120 de las 180)**: submuestra respetando los estratos de julio.
  Da el kappa autor-vs-asistente Y re-puntúa las 5 corridas piloto existentes
  contra referencia humana sin gastar un token.
- **Bloque B (430)**: nuevo, ciego al modelo, estratificado por activo
  (piso 40 + resto proporcional).
- Barajados y ciegos; **cualquier prefijo es muestra válida** → el autor puede
  parar donde quiera.
- Se anota **una categoría de la taxonomía de 15** (+ polaridad si magnitud>0).
  La relevancia sale derivada (relevante == magnitud>0): una columna menos.
- Regla: **juzgar solo por el titular**, que es todo lo que ve el modelo.

### EL CORPUS DEBE SER EL NUEVO (decisión del autor, 2026-08-22)
El fetch del universo de 7 **nunca se hizo**: `data/raw/` solo tiene los 5
parquets viejos (14-jun). Respaldo del corpus viejo en
`data/raw/_corpus_viejo_20260622/` antes de correr `--force`.
**Razón fuerte, más allá de que cambiaron las queries**: el prefiltro regex vive
en la fase de CLASIFICACIÓN (`llm_sentiment.classify_dataframe:153`), no en el
fetch. Por eso `news_<T>.parquet` guarda el corpus COMPLETO, **antes** del
prefiltro, y muestrear de ahí permite medir **qué descarta el regex antes de que
el LLM lo vea** — hoy es un punto ciego total.

### FETCH DEL UNIVERSO 7 — HECHO (2026-08-22)
`--fetch-only --force`, 19,528 noticias tras allowlist+dedup:
CREDITC1 10,029 · INRETC1 3,202 · FERREYC1 1,752 · ALICORC1 1,725 ·
LUSURC1 1,056 · MINSURI1 921 · CPACASC1 843.
**OJO — `docs/pendientes_implementacion_universo.txt` estima Pacasmayo ~10.4k y
la realidad son 843** (1,529 crudas). Minsur y Pacasmayo son los dos más flacos.
Eso invalida la aritmética de conteos con que se planteó D12; el número real de
eventos sale de la anotación. Excel de 550 filas ya generado.

### Lo que queda
- Gemini: código LISTO (`src/sentiment/llm_backends.py`, despacho por nombre de
  modelo, schema estricto). Falta `GEMINI_API_KEY`. Endpoint verificado:
  `/v1beta/interactions`, modelo `gemini-3.7-flash`, header `x-goog-api-key`.
  Responde la pregunta del anidamiento, que NO depende de la referencia.
- Claude: $6.7 (Haiku) a $33.5 (Opus) con Batch API. Hay descuentos académicos.
- **55 archivos SIN COMMITEAR** — el autor no autorizó el commit. Ver el
  handoff para el inventario.

**Why:** la sesión produjo hallazgos que son caros de re-derivar y un error
metodológico que no debe repetirse.
**How to apply:** leer `docs/PENDIENTES_R5.txt` antes de tocar R5. Nunca decir
"anotación humana" sobre ese archivo. Ver [[project-r5-sentiment-status]].

---

## 2026-08-26 — ANOTACIÓN DEL AUTOR COMPLETA (550/550). BLOQUEANTE #1 CERRADO

`data/interim/validacion_humana/muestra_r5_anotar.xlsx` lleno.
Medición: `python scripts/evalua_validacion_humana_r5.py`.

- **Prefiltro regex: 0 relevantes matados** de 109 descartes (19.8% del corpus).
  El punto ciego se cierra a favor del prefiltro.
- **Kappa autor-vs-asistente 0.456** (acuerdo 81.7%) en relevancia; 0.618 en
  polaridad. Lo importante no es el kappa: **el desacuerdo es 100%
  unidireccional** (22 casos asistente-relevante/autor-irrelevante, CERO al
  revés) y **enteramente atribuible a dos convenciones**: sector_macro=0 (14 de
  22) y "M&A siempre neutral" (3 de 3 desacuerdos de polaridad). No es ruido:
  es la frontera que la taxonomía v2.1 movió a propósito.
- **Relevancia poblacional 7.3% ±2.8pp** (bloque B reponderado), NO el 10% crudo
  de las 550 — el bloque A está estratificado por etiqueta del modelo v1.
  Por activo: MINSURI1 21.3% · LUSURC1 20.8% · INRETC1 16.9% · CPACASC1 8.7% ·
  ALICORC1 5.7% · **CREDITC1 2.5% · FERREYC1 1.9%**.
- **RANKING DE MODELOS INVERTIDO.** Contra la referencia del autor gana
  **gemma3:12b** (P 75.0% / R 92.3% / F1 82.8%); qwen2.5:32b, que lideraba
  contra la referencia del asistente, cae a F1 66.7%. McNemar: 12b > toda la
  familia 4b (p<0.02); indistinguible de qwen 14b/32b.
- **EVENTOS PROYECTADOS a 2012-2025 (todo el historial, no solo train):**
  INRETC1 ~540 · CREDITC1 ~253 (IC enorme) · LUSURC1 ~218 · MINSURI1 ~193 ·
  ALICORC1 ~96 · CPACASC1 ~72 · **FERREYC1 ~33 (≈2.4/año)**. Gobierna D12.
- **58% de los eventos relevantes son `neutral`** (y 58% de la masa de magnitud).
  Los 13 M&A — la categoría A más frecuente — son todos neutrales por regla, así
  que **no entran a ninguna EWMA pos/neg**: el evento más material del corpus es
  invisible en las 6 columnas de D11(iii). Es un agujero de diseño, no de datos.
- Truncamiento de titulares: **determinista, no aleatorio** — cuerpo cortado a
  exactamente 70 caracteres antes de anteponer el prefijo de sección
  ("Mercados: ", "Economía: "…). 271 filas del corpus (1.26%), detectable con
  regex.
- Contaminación declarable: **7 filas de 550** llevan nota de haber sido
  consultadas con el asistente (5 confirmaciones, 2 reclasificaciones).
