---
name: project-d20-known-date-fundamentales
description: "D20 (2026-09-01): el lag de fallback estaba calibrado contra el universo VIEJO y le metía 5-7d de look-ahead a InRetail; ahora se calibra por activo + bandera known_date_real"
metadata: 
  node_type: memory
  type: project
  originSessionId: e9a825e5-240a-47f4-9395-4b226c9107f0
  modified: 2026-09-01T19:26:59.340Z
---

**D20 CERRADA el 2026-09-01.** Registro: `docs/decisiones_pendientes_OE1.txt` → D20 y
`docs/riesgos_transversales_datos.txt` §3(a). La planteó el ASESOR: ¿no será mejor
eliminar la señal de fundamentales donde no hay fecha real, en vez de darla con semanas
de rezago?

**Lo que apareció al medir: una REGRESIÓN por cambio de universo.** El barrido original de
jul-2026 era correcto — lo reproduje exacto (`4/109`, 3.7%) sobre los 5 emisores con los
que se calibró. Pero **INRETC1 entró después** (reemplazó a SAGAC1) y nunca se revalidó:
```
  universo viejo (n=109):  lag 40d ->  4/109 ( 3.7%) look-ahead
  + INRETC1     (n=130):   lag 40d -> 25/130 (19.2%)
```
21 de los 25 son InRetail, en los 8 años, **no** son prórrogas: presenta a 43-47d cuando
el resto va a ~30d. Le metía 5-7 días de look-ahead cada trimestre de 2012-2017.

**LECCIÓN TRANSVERSAL: toda constante CALIBRADA contra el universo hay que
re-verificarla cuando el universo cambia.** Mismo modo de falla que la tabla de eventos de
D11 y que el `llm_model` del config que seguía en gemma3:4b.

**La cobertura no es aleatoria** — 0% hasta 2017, ~96% desde 2019 → train 32.5% real,
test 85.2%. La variable significa cosas distintas a cada lado del split.
Retraso del fallback: mediana 10d, >14d en 24.6%.

**Decisión (tres piezas):**
- **(a)** lag por activo (`_calibra_lag`): máx normal del propio emisor + 5d, excluyendo
  COVID, nunca por debajo del global. Look-ahead **26/207 (12.6%) → 4/207 (1.9%)**;
  InRetail 22→0. Lags: **INRETC1 52/66**; MINSURI1/ALICORC1/LUSURC1 41/60; el resto 40/60.
- **(b)** bandera `known_date_real` en el esquema, propagada al panel y a la vista
  `mercado_fundamentales`.
- **(c)** NO se elimina la señal; la propuesta del asesor queda como **brazo de ablación**
  (NaN-ear donde `known_date_real==0`).

**Por qué no eliminar:** vaciaría el TRAIN (231 → 75 periodos) y dejaría el test intacto —
un modelo que nunca aprendió a usar el canal, juzgado donde el canal funciona, y la
ablación sesgada en contra por construcción. Y el retraso **diluye pero no destruye**
porque el panel usa los fundamentales como NIVELES (10d sobre un escalón de 90d), no como
sorpresa. El look-ahead sí era otra cosa: por eso (a) no era disyuntiva sino arreglo.

**Fundamentales de los 4 activos nuevos (MINSURI1, CPACASC1, FERREYC1, LUSURC1)
descargados** el 2026-09-01, 84 periodos cada uno. Los 7 regenerados con el código nuevo.

Ver [[project-bvl-hechos-filing-dates]] y [[project-r5-evaluacion-integral]].
