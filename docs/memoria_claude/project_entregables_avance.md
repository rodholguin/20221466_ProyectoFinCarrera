---
name: project-entregables-avance
description: "Word y PPT de avance OE1-OE3 (presentados 22-sep-2026, buena devolución); sus generadores viven en scripts/entregables/ y la PPT de docs/ está editada a mano"
metadata: 
  node_type: memory
  type: project
  originSessionId: 43a24782-3ace-4495-b4b9-41628b7a23b5
  modified: 2026-09-23T00:59:50.180Z
---

## Entregables de avance (2026-09-22) — PRESENTADOS, devolución positiva

- `docs/informe_avance_OE1_OE3.docx` — 21 páginas, ejecutivo pero con detalle,
  9 figuras. Público: profesores de tesis (no el asesor especializado).
- `docs/avance_tesis_OE1_OE3.pptx` — presentada en 10 minutos.

**Los generadores están en `scripts/entregables/`** (figuras.py, figuras2.py,
figppt.py, informe.js, deck.js, README.md). Antes vivían solo en el scratchpad
de sesión. Verificado que corren desde ahí y reproducen ambos documentos.
`fig/`, `figppt/` y `node_modules/` van al .gitignore.

**LA PPT DE `docs/` ESTÁ EDITADA A MANO POR EL AUTOR**: 17 láminas (+3 de
planteamiento al inicio: árbol de problemas y dos de mapeo IOV/MoV; −1, la de
los dos defectos propios). `deck.js` genera las 15 originales, así que correrlo
contra esa ruta PISA las ediciones.

**Las tablas de texto de informe.js y deck.js tienen cifras escritas a mano.**
Las figuras se regeneran solas desde los artefactos; las tablas no. Al correr
la versión definitiva de 10 semillas hay que actualizarlas.

## Guion de tiempos de la presentación (10 min, 17 láminas)

Apertura 1:30 · OE1 2:30 · OE2 1:45 · OE3 2:40 · cierre 1:05 = 9:30, con 30 s
de colchón. Marcas: minuto 2 entrando a la lámina 5; minuto 4 cerrando OE1;
minuto 6 entrando a OE3. Si va tarde se sacrifica, en orden: las tres vías de
mejora, el protocolo, y los dos mapeos IOV/MoV.

## Dos afirmaciones del proyecto que se corrigieron al verificarlas

1. **"El mejor año de la década" es FALSO.** El pliegue 0 (+14.2% bruto) está
   en el percentil 81 de las ventanas de 252 días 2013-2025; la mejor rinde
   +69.9% y termina en feb-2017. Es "el tramo más favorable de los SEIS de la
   partición". **Corregido en todo el repo el 26-sep** (§6.1 con la tabla
   medida, scripts/caracteriza_pliegues.py). Sin el tramo ciego da
   PERCENTIL 78, no 81 (el 81 incluía el test del pliegue 2).
2. **El barrido de λ era discreto, y el fino (26-sep) lo DESMINTIÓ**:
   `logret_dd` con λ ∈ [0.63, 0.68] pasa los 4 criterios del tamiz en el
   pliegue 0. Ver [[project-oe1-estado-20260912]].

Caracterización MEDIDA de los pliegues (índice equiponderado, bruto):
p0 +14.2% vol 11.1% · p1 −5.8% vol 26.5% maxDD −41.9% · p2 −5.4% vol 9.4%.
Es medida sobre el propio panel, NO tomada de un índice externo (el índice
local de retorno total sigue pendiente).

**Why:** los dos documentos son la cara visible de la tesis y su código estaba
en un directorio temporal.
**How to apply:** ver `docs/pendientes_20260923.txt` para el resto del plan.
Ver [[project-oe1-estado-20260912]].

## Reunión con el asesor 28-sep-2026 — AVANCE VALIDADO
Se presentó `notebooks/avance_semanal_20260928.ipynb` (generador
`scripts/create_avance_semanal_notebook.py`, 12 figuras: R8 completa, D25, tamiz +
barrido fino de λ en 3 pliegues, SAC/DDPG, Bloomberg EVTS/spreads/LQA, hoja de ruta).
Barrido fino guardado en artefactos_oe1/d4_tamiz_barrido_fino_p{0,1,2}.json.
Hallazgo nuevo al armarlo: las puntas bid/ask de Bloomberg P0 están congeladas o
cruzadas en ≥50% de los días en 2015-2018 → la reconciliación es obligatoria.
Notebook, generador y los 3 JSON quedaron SIN COMMITEAR.
