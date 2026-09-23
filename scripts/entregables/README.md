# Generadores de los entregables de avance

Código que produce los dos documentos de avance de la tesis a partir de los
artefactos ya calculados. **No entrena ni recalcula nada**: lee
`data/interim/artefactos_oe1/` y dibuja.

| Archivo | Qué produce |
|---|---|
| `figuras.py` | 4 figuras para el Word, en `fig/` |
| `figuras2.py` | 6 figuras más (curva de aprendizaje, patrimonio, pesos, mapa de calor, frontera de recompensas), en `fig/` |
| `figppt.py` | Re-ejecuta las dos anteriores con tipografía grande, en `figppt/`, para proyectar |
| `informe.js` | `docs/informe_avance_OE1_OE3.docx` (21 páginas), usa `fig/` |
| `deck.js` | `docs/avance_tesis_OE1_OE3.pptx` (15 láminas), usa `figppt/` |

## Cómo regenerar

> **CUIDADO CON LA PPT.** `docs/avance_tesis_OE1_OE3.pptx` es la versión que se
> presentó el 2026-09-22 y fue **editada a mano por el autor**: tiene 17
> láminas (se agregaron 3 de planteamiento al inicio y se quitó la de los dos
> defectos propios). `deck.js` genera las 15 originales, así que **correrlo
> contra esa ruta pisa esas ediciones**. Si hay que regenerar, sacar la salida
> a otro nombre y reaplicar los cambios a mano, o editar el .pptx directamente.

```bash
# 1. dependencias (una sola vez, en esta carpeta)
npm install docx pptxgenjs

# 2. figuras
python scripts/entregables/figuras.py
python scripts/entregables/figuras2.py
python scripts/entregables/figppt.py

# 3. documentos
node scripts/entregables/informe.js  C:/tesis/docs/informe_avance_OE1_OE3.docx
node scripts/entregables/deck.js     C:/tesis/docs/avance_tesis_OE1_OE3.pptx
```

`fig/`, `figppt/` y `node_modules/` no se versionan: son regenerables.

## Requisitos

- Los artefactos de OE1 en disco. Si faltan:
  `python scripts/genera_artefactos_oe1.py` (~10 min).
- Python con matplotlib y pandas; Node con `docx` y `pptxgenjs`.
- Las figuras usan la tipografía **Segoe UI** y los documentos **Calibri** y
  **Cambria**.

## Convenciones que conviene no romper

- **La paleta está validada para daltonismo** y es la misma en los dos
  documentos: azul `#2a78d6`, naranja `#eb6834`, verde agua `#1baf7a`,
  amarillo `#eda100`. El acento de las láminas (`EB6834`) es el mismo naranja
  de los gráficos, a propósito.
- `figppt.py` no duplica el código de las figuras: reejecuta los otros dos
  scripts sustituyendo tamaños de fuente y acortando las etiquetas que no
  entran al agrandarlas. Si se agrega una figura nueva, revisar que sus
  etiquetas quepan en la versión grande.
- **Toda cifra de estos documentos sale de los artefactos**, no está escrita a
  mano en el generador, salvo las tablas de texto (que sí están en línea y hay
  que actualizar a mano cuando cambien las corridas).

## OJO — las tablas escritas a mano

`informe.js` y `deck.js` llevan cifras en línea dentro de sus tablas y
recuadros (los resultados por pliegue, los costos por activo, las métricas de
R5). Cuando se corra la versión definitiva con 10 semillas, **hay que
actualizarlas a mano**; no se leen de los JSON. Las figuras sí se regeneran
solas.
