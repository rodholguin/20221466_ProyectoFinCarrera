---
name: project-d19-novedad-eco
description: "D19 (abierta, diferida a R8): la taxonomía es muda sobre si un evento es NUEVO; las EWMA ya lo cargan implícitamente; propuesta barata = dias_desde_ultimo_evento_misma_categoria"
metadata: 
  node_type: memory
  type: project
  originSessionId: e9a825e5-240a-47f4-9395-4b226c9107f0
  modified: 2026-09-01T02:23:24.366Z
---

**D19 ABIERTA**, planteada por el autor el 2026-08-31: *"una noticia de anuncio de una
compra no es igual que una noticia de la compra; para el momento de la compra el impacto
ya pasó"*. Registro: `docs/decisiones_pendientes_OE1.txt` → D19. **NO bloquea la corrida.**

**El problema, medido en el arco de Luz del Sur:** 7 titulares entre ene y oct 2019, TODOS
`A_ma_reestructuracion`, TODOS magnitud 1.0.
```
  2019-02-25  "Sempra iniciará proceso de venta"   <- +43% viene después
  2019-10-15  "CTG oficializa compra"              <- 10 sesiones tarde
```

**La taxonomía no está mal: está MUDA.** Contesta "¿de qué tipo es?", nunca prometió
"¿esto es nuevo?". La separación fue deliberada en D11. **La novedad no es propiedad del
tipo de evento sino de la historia de la serie**, por eso no cabe en el esquema.

**Lo que ya funciona, y hay que ver antes de inventar:** las EWMA de 3 escalas **ya cargan
la novedad implícitamente** — un evento nuevo llega sobre base baja, un eco sobre base
alta. La red ve el evento Y el nivel previo, así que en principio puede distinguirlos. El
costo real no es error de etiquetado: es **ruido en régimen de pocos datos** (0.9–14
eventos por activo-año). Caro, no fatal.

**Propuesta (barata, determinista, en R6, sin LLM):** columna
`dias_desde_ultimo_evento_misma_categoria` por activo. Hace explícito lo implícito. Entra
como brazo de ablación en R8, igual que D17 y las 18 columnas de D15.

**NO hacer:** pedirle la ETAPA al LLM (rumor/anuncio/confirmación/cierre). Es el campo
condicional que D16 probó dos veces y falló las dos, con deriva verificada sobre 456
titulares held-out. Camino cerrado. Ver [[project-r5-d16-piloto-rol]].

Se decide **después** de la corrida, con el panel en la mano. Ver [[project-d18-hechos-no-adoptados]].
