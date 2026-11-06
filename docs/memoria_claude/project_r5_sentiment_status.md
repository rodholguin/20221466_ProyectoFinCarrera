---
name: project-r5-sentiment-status
description: "R5 EN REDISEÑO (ago-2026): v1 invalidado por medición; prompt v2.1 con taxonomía de eventos implementado; Piloto A midió gemma3:4b; corrida grande BLOQUEADA por velocidad (necesita servidor GPU)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6a97b3f6-eead-4573-bd12-b3dd14cb518f
  modified: 2026-08-18T20:34:03.604Z
---

## R5 — estado al 2026-08-18

**v1 está INVALIDADO** (no borrado: los parquets viejos siguen en disco, pero sus
etiquetas no se usan). La validación de julio lo mató: relevancia 26%, kappa 0.32,
49% de las etiquetas con signo sobre noticias que no hablaban de la empresa,
`confidence` que no discrimina. Detalle: `docs/validacion_etiquetado_r5.txt`.

### Lo IMPLEMENTADO en la sesión del 2026-08-18
Especificación viva: **`docs/taxonomia_eventos_R5.txt`** (es el doc de referencia;
§7 es la auditoría completa de R5 con toda la evidencia).
- `src/sentiment/taxonomia.py` (NUEVO): 15 categorías en 4 tramos de magnitud
  ex-ante + prefiltro regex. `normaliza()` fuerza en código que la polaridad solo
  exista si magnitud > 0.
- `llm_sentiment.py`: prompt **v2.1**, `format:json` + `temperature 0` (0% de
  fallos de parseo), caché indexado por (artículo, prompt, modelo), salida en dos
  niveles (por artículo = fuente de verdad, y diaria para R6).
- `mediacloud_client.py`: queries nuevas para los 7 activos SIN ancla financiera,
  dedup con ventana, provenance (query + fecha), fix de `lstrip("www.")`.
- `run_r5_news.py`: `--force`, `--model`, reporte de tasa de error.
- `SENTIMENT_SCHEMA` ampliado (mag_pos/mag_neg + desglose por tramo para D12).

### HALLAZGOS QUE CAMBIARON EL DISEÑO (todos medidos, todos en §7 del doc)
1. **El ancla `_FINANCIAL` era contraproducente** y se ELIMINÓ. Sus términos son
   el vocabulario de las crónicas de índice: admitía el ruido y bloqueaba M&A y
   noticias regulatorias reales.
2. **`_build_query` no tenía entrada para 5 de los 7 activos** — INRETC1 habría
   usado `"InRetail Peru Corp"` (razón social casi ausente en prensa) e invalidado
   el corpus en silencio.
3. **Bumpear PROMPT_VERSION no invalidaba el caché** (la clave era solo el id):
   CREDITC1 y ALICORC1 habrían reusado etiquetas v1 sin aviso. Corregido.
4. **PACASMAYO: su cobertura de prensa cae 85%** (10,390 -> 1,529) al desambiguar
   la provincia/ciudad. Pasa de 2º a ÚLTIMO del universo en prensa. NO sale del
   universo (entró por liquidez 72.1%), pero su canal de sentimiento vale mucho
   menos de lo esperado. Ver [[project-universe-decision]].
5. **t+1 está sostenido con evidencia** — ver [[project-d11-representacion-sentimiento]] (D13).

### PILOTO A (180 noticias anotadas, gemma3:4b, prompt v2)
Banco de pruebas: `data/interim/r5_validacion_anotada.csv` (ground truth humano;
**rel_humana = 1 <=> cat_humana en {empresa, sector}**). Script:
`scripts/piloto_r5_taxonomia.py`; what-if: `scripts/analiza_piloto_whatif.py`.
- v2: exactitud 65.6%, precisión 46.3%, recall 92.6%, espuria 42.7%. **NO pasa.**
- CULPA DEL DISEÑO, NO DEL MODELO: `sector_macro` (magnitud 0.3) fue el basurero —
  55/180 predicciones, 29% relevantes; en CREDITC1, 18 de 19 eran notas de TC.
  `no_relevante` no se usó NUNCA.
- **`sector_macro` -> magnitud 0.0** (aplicado): 78.3% / 64.2% / 63.0% / 32.6%.
- **CORRECCIÓN IMPORTANTE**: era FALSO que la polaridad espuria "desapareciera por
  construcción". Solo desaparece *condicionada a que la categoría sea correcta*.
- Prompt v2.1 (pregunta de filtro binaria primero, regla de duda -> GRUPO B, caso
  del tipo de cambio explícito). Pendiente: re-medir el piloto con v2.1.

### BLOQUEO ACTUAL: velocidad
El prompt v2 es **~27 s/artículo** en CPU local (v1 era 10-13 s) porque el prompt
lleva la taxonomía completa. Volumen real medido con `story_count`:
**39,783 artículos en colección -> ~11,487 a clasificar** tras allowlist y
prefiltro. Eso es **86 h = 3.6 días** en local. INVIABLE.
=> El **servidor académico PUCP con GPU es la ruta crítica**. Llave SSH generada
(`~/.ssh/id_ed25519_pucp`) y `~/.ssh/config` con ProxyJump bridge->phantom listo;
**falta que el autor instale la pública en ambos saltos**. Con GPU: 3-16 h, y
habilita modelos 12B-27B si v2.1 con 4b sigue sin pasar.

### Seguridad — RESUELTO
El token de MediaCloud filtrado en el repo público se ROTÓ el 2026-08-18. El
nuevo NO está en el historial (verificado con `git log -S`); el viejo quedó inerte.

**Why:** la sesión rediseñó R5 de raíz y midió cada decisión; retomar sin esto
llevaría a re-correr v1 o a repetir la auditoría.
**How to apply:** leer `docs/taxonomia_eventos_R5.txt` §7 antes de tocar R5.
Nunca lanzar la corrida completa en CPU local.
