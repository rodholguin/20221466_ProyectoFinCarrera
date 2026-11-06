---
name: project-d18-hechos-no-adoptados
description: "D18 (2026-08-31): los Hechos de Importancia NO entran como 2da fuente — criterio pre-registrado falla los 3 puntos; la fuente es buena (53.4% materialidad) pero no arregla la heterogeneidad"
metadata: 
  node_type: memory
  type: project
  originSessionId: e9a825e5-240a-47f4-9395-4b226c9107f0
  modified: 2026-09-01T02:23:10.954Z
---

**D18 CERRADA el 2026-08-31.** Expediente completo: `docs/materialidad_hechos_R5.txt`.
Registro: `docs/decisiones_pendientes_OE1.txt` → D18.
Reproducible: `python scripts/evalua_materialidad_hechos.py`.

El autor anotó los 140/140 a ciegas. **El criterio pre-registrado dice NO ADOPTAR:**
```
  (1) heterogeneidad < 6.0x            :   6.4x   NO
  (2) FERREYC1 triplica                :   2.9x   NO
  (2) CPACASC1 triplica                :   2.1x   NO
  (3) filtro de rutina sin materiales  :    15    NO
```

**No es que la fuente sea mala:** materialidad poblacional **53.4% ±10.2pp** contra
**7.2%** de la prensa — siete veces más densa en señal. Lo que no hace es arreglar la
heterogeneidad, que es para lo que se propuso.

**La estimación previa erraba por más del doble:** decía 2.9x de heterogeneidad y
Pacasmayo 26.8 hechos/año (7.9x); lo medido es 6.4x y 4.3/año (2.1x). **La
pre-registración hizo su trabajo** — es la práctica que hay que conservar.

**Dos problemas del criterio, declarados sin usarlos para rescatar nada:**
- **(3) está mal especificado**: 14 de los 15 "materiales perdidos" son `A_resultados`
  (EEFF), y el mismo doc ya decía antes de anotar que los EEFF son doble conteo con R4 y
  hay que excluirlos. Choque entre dos reglas del mismo día. Da igual: (1) y (2) fallan solos.
- **No es robusto**: dos filas marcadas con `duda` (las escrituras públicas) voltean dos
  de los tres umbrales (6.4→5.7x, FERREYC1 2.9→3.3x). Y **premia el etiquetado
  incorrecto**. Lo robusto: CPACASC1 no triplica bajo ningún etiquetado (2.1x–2.5x).

**Lo que nunca se midió y es donde los hechos SÍ sirven: la FECHA.** Tras la anotación,
de las tres ventajas declaradas solo sobrevive el `registerDate` point-in-time (el código
oficial resultó poco fiable — fila 107, L21 "Emisiones" para un reporte de tenedores de
ADRs; y 14% de los hechos es texto mudo). **Propuesta reducida y diferida:** usar los
hechos como **ancla de fecha**, no como fuente de eventos. Se mide después del panel.

**Las 5 observaciones del anotador se verificaron una por una** (§5 del doc). La
reutilizable: *materialidad antes que palabra clave* — un acto notarial no es el evento, y
fecharlo ahí sitúa la señal meses después de que el mercado se enteró.

**Limitaciones que van a la tesis y NO tienen arreglo** (§7): hechos mudos (14% + 2,007
ya excluidos); clasificación por titular sin cuerpo; **la cobertura de Pacasmayo y
Ferreycorp (8.2 y 6.8 eventos/año) — ninguna fuente disponible la arregla**; y la
anticipación del mercado (LdS subió +43% antes del hecho).

Ver [[project-d19-novedad-eco]] y [[project-r5-d16-piloto-rol]].
