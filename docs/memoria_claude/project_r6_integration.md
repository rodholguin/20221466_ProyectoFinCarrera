---
name: project-r6-integration
description: "R6 (integración): política de huecos de sentimiento decidida — decaimiento aprendido por el agente, no precomputado"
metadata:
  node_type: memory
  type: project
  originSessionId: fc61a441-3c31-4ddc-a094-c09f8e0eaee6
  modified: 2026-07-30T04:24:02.123Z
---

## R6 — decisión tomada: política de huecos de sentimiento (2026-06-22)

Antes de construir el panel unificado de R6, se evaluaron alternativas
para tratar los días de mercado sin noticia en el feature de sentimiento
(ver [[project-r5-sentiment-status]] para los datos de cobertura: 7.7% a
58.3% según el activo, con rachas sin noticia de cola pesada — mediana de
1 a 7 días hábiles, pero máximos de 278 a 404 días hábiles según el
activo).

**Decisión: el decaimiento del sentimiento NO se precalcula en R6 — se
deja como parámetro aprendible dentro del propio agente DRL.**

**Why:** El asesor (Dr. Villanueva) sugirió que la tasa de decaimiento se
aprenda junto con las redes del agente, en vez de fijar un half-life a
mano (que sería un hiperparámetro optimizado sobre una métrica proxy,
no sobre el reward real del agente). Esto también evita el dilema de
"half-life único para los 5 activos vs. calibrado por activo" — la red
puede aprender una tasa distinta implícitamente por activo sin que el
investigador la fije.

**Esquema resultante para el bloque de sentimiento en el panel de R6**
(por `ticker, date`, sin decaer nada):
  - `sentiment_score_last` — último score observado (-1/0/+1), forward-
    fill crudo del valor sin transformar. Antes de la primera noticia
    histórica de un activo: 0 (sin información todavía, no neutral
    observado).
  - `days_since_news` — días hábiles desde esa última noticia. 0 en
    días con noticia.
  - `has_news` — 1 si hubo ≥1 noticia ese día, 0 si no.
  - `n_articles` — conteo de noticias del día; 0 en huecos (sin
    ambigüedad, a diferencia del score).

**Referencia de literatura mencionada (no verificada con cita exacta,
solo como pista a seguir):** redes con decaimiento aprendido sobre series
con datos faltantes/irregulares, ej. GRU-D (Che et al. 2018) — capa de
decaimiento `exp(-softplus(w·Δt))` con `w` entrenable. No se decidió usar
esa arquitectura específica, solo se usó como referencia conceptual de
que `days_since_news` puede alimentar directamente una capa que aprenda
a descontar la señal.

**Pendiente (no bloquea esta decisión, es para cuando se implemente el
agente):** si `days_since_news` se alimenta crudo o transformado (ej.
log) a la red, dado que los máximos observados son de cientos de días.

**How to apply:** Cuando se construya `scripts/run_r6_integration.py` (o
el notebook de R6), el bloque de sentimiento debe escribir estas 4
columnas crudas, NO una columna ya decaída. Si una sesión futura propone
precalcular un sentiment_score_decay con half-life fijo, señalar que ya
se decidió explícitamente lo contrario por sugerencia del asesor.

## Implementado y validado (2026-06-23)

`src/integration/build_dataset.py` se reescribió y `scripts/run_r6_integration.py`
ya genera `data/processed/dataset_unificado.parquet` (17,565 filas = 5
activos x 3,513 días bursátiles, 2012-2025, 36 columnas). Decisiones
adicionales tomadas en esta sesión (no estaban en el cierre anterior):

- **Calendario bursátil se construye en R6** (`build_trading_calendar`:
  unión de fechas con cotización de cualquiera de los 5 activos), NO en
  el entorno DRL (OE1). El entorno solo debe consumir el índice de fechas
  ya resuelto en el panel, sin reconciliar calendarios.
- **Noticias en día no bursátil (fin de semana/feriado BVL) se
  roll-forward** al siguiente día hábil ANTES de aplicar el forward-fill
  de `sentiment_score_last` -- son dos mecanismos distintos y
  compuestos: roll-forward resuelve a qué fila va una noticia sin fila
  propia; forward-fill (ya decidido arriba) es lo que pasa los días
  siguientes sin noticia nueva. Si hay colisión (la noticia rolleada cae
  en un día que ya tenía noticia propia) se reagregan con media
  ponderada por `n_articles` (consistente con `daily_aggregation: mean`
  de R5). Validado con caso real: sábado 2013-07-20 (score 0.0, 2
  artículos) + lunes nativo 2013-07-22 (score 1.0, 1 artículo) -> 0.333,
  n_articles=3.
  Efecto: la cobertura de noticias subió levemente vs. lo reportado en R5
  (ej. SAGAC1 7.7%->9.2%, CREDITC1 58.3%->60.7%) -- se recuperan noticias
  de fin de semana que antes se perdían fuera del calendario.
- **`days_since_news` usa un ancla sintética en la fila 0** de cada
  activo (se trata como si hubiera un evento neutral en día 0) en vez de
  NaN antes de la primera noticia histórica real -- evita inventar un
  segundo valor sentinela arbitrario.
- **`days_since_news` se guarda CRUDO (entero, días hábiles) en el
  parquet.** La transformación `log1p` (acordada con el usuario, no
  `log` puro porque `days_since_news=0` en días con noticia) se aplica en
  OE1 al construir la observación, NO en R6 -- misma lógica de
  separación que el calendario: R6 guarda crudo, OE1 transforma. Esto
  cierra el "pendiente" que quedaba abierto sobre crudo vs. transformado.

Ver también [[project-r6-no-trade-days]] para la decisión paralela sobre
activos que no cotizaron un día bursátil (huecos de mercado, no de
sentimiento).

**How to apply:** Si una sesión futura pregunta dónde vive el calendario
bursátil o por qué `days_since_news` no viene transformado en el
parquet, esto ya está resuelto -- no reabrir la discusión, solo señalar
esta nota.

## Documentación de cierre de R6 (2026-06-23)

R6 quedó documentado con el mismo formato que R3/R4/R5:
`docs/hallazgos_integracion_R6.txt` (narrativa completa de las 8
decisiones de esta sesión + sección dedicada de política de imputación
que distingue explícitamente qué SÍ es imputación de qué no lo es) y
`notebooks/exploracion_integracion_bvl.ipynb` (9 secciones, ejecutado,
generado por `scripts/create_integration_notebook.py`). `docs/
pipeline_extraccion_datos.txt` sección 4 se reescribió completo (estaba
desactualizado, todavía decía "el sentimiento se imputa como 0.0") y el
encabezado del documento ahora referencia también
hallazgos_sentimiento_R5.txt y hallazgos_integracion_R6.txt (R5 nunca
había quedado listado ahí). Ver también [[project-r6-no-trade-days]] para
la decisión paralela documentada en la misma sesión.

## P/E y DY integrados al panel (jul-2026)

El panel pasó de 36 a **41 columnas**: se añadieron pe, dy (+ auxiliares
shares_outstanding, net_income_ttm, eps_ttm). pe y dy se calculan a nivel
DIARIO en build_unified (no se propagan por known_date como ROE/ROA): pe =
close_raw/eps_ttm (NaN si utilidad TTM<=0), dy = dividendos_TTM/close_raw.
feature_views los expone en mercado_fundamentales y completa. run_r6_integration
arma la serie de dividendos vía corporate_actions. Ver [[project-pe-dy-viability]]
para la metodología. Doc R6 actualizado (columnas §2, excepción NaN §5.5, nota de
implementación + caveats P/E/DY en limitaciones, catálogo Sec. 5b en §7). Notebook
exploracion_integracion_bvl.ipynb regenerado con Sec. 5b (P/E/DY diarios + zoom
CREDITC1 P/E-vs-EPS que ilustra la integración precio-diario × fundamental-
trimestral) y ejecutado (0 errores). El generador ahora pasa asset= a
compute_ratios. Notebook de fundamentales también tiene su Sec. 5b.

## Features MACRO integrados al panel (jul-2026) — item (d) del handoff de universo

`build_unified(..., macro=DataFrame|None)` + `_merge_macro`: las 6 series BCRP
entran como columnas **globales** `macro_*` (cobre, oro, embi, tasa_ref, inflacion,
tc_usdpen) con un join por `date` **después** del concat de paneles (son globales;
`ValueError` si alguna columna macro ya existe, aviso si el join deja NaN). El
builder **no descarga nada**: recibe el macro ya resuelto, igual que `dividends` —
`run_r6_integration` hace `macro_features(build_trading_calendar(market))` y, si el
fetch falla, construye el panel sin macro (aviso, no aborta). `feature_views` gana
la vista **`mercado_macro`** (ablación del canal) y suma las 6 a `completa` (34
cols); sentimiento/fundamentales quedan sin macro para poder aislar canales.
Niveles CRUDOS (retorno log / nivel+cambio va en OE1), coherente con R6=crudo.

Ajuste necesario en `macro_client.load_macro(start=)`: 2012-01-01 → **2011-01-01**
(+ caché `data/interim/macro_bcrp.parquet` regenerado). Sin ese colchón el `asof`
de las series MENSUALES deja sin valor todo enero-2012 (21 días hábiles de
macro_tasa_ref, 22 de macro_inflacion). No es look-ahead: solo agrega observaciones
previas al horizonte.

Verificado sobre 3,513 fechas: 0 NaN en las 6 columnas; 1 solo valor distinto por
fecha (globalidad); rangos sensatos; y point-in-time OK — los escalones de
macro_inflacion caen día 1-5 del mes (mediana 1) y los de macro_tasa_ref a
fin/inicio de mes (mediana 30), con **0 escalones a mitad de mes**. Doc R6 y
notebook AÚN NO regenerados (van con la corrida del nuevo universo).
