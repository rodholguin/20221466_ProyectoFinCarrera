---
name: project-ferreycorp-holding-r4
description: "RESUELTO 2026-10-09: R4 pasó a estados CONSOLIDADOS en todos los no bancos (no solo Ferreycorp), con utilidad ATRIBUIBLE para EPS/ROE; BCP queda individual"
metadata:
  node_type: memory
  type: project
  originSessionId: 5234d5da-2ac1-4b45-9361-f0d9fcbfca75
  modified: 2026-10-09T15:27:01.202Z
---

Detectado el 06-oct (margen neto de Ferreycorp 787%). Al medirlo en los 7
activos el 09-oct resultó GENERAL: el individual de una matriz suma la
utilidad de las subsidiarias (método de participación) pero no sus ingresos
ni activos. Ingreso I/C 2023: Ferreycorp 0.01, Minsur 0.37, Alicorp 0.47,
Pacasmayo 0.66, Luz del Sur 0.97. ROE/EPS/P/E estaban bien. Margen, ROA y deuda no.

**Decisión del autor (09-oct): consolidado en TODOS los no bancos.** BCP sigue
individual (taxonomía SBS, sin la cuenta 2D0802) y se declara como limitación.

Lo implementado en fundamentals_client.py:
- **Utilidad atribuible.** EPS, P/E y ROE usan GP_2D0802 y BG_1D0710. La neta
  consolidada (2D07ST/INFO) incluye minoritarios: Minsur +44% en 2023 y
  InRetail ~7% en 2019-20.
- **Piso de fecha.** La fecha real del hecho INDIVIDUAL es el piso del lag de
  respaldo del consolidado (LUSURC1 2020-Q1 tenía 68 días de look-ahead).
- **Tesorería positiva.** Se descarta (CPACASC1 2012-Q1/Q2 daba −28M de acciones).

Tests en tests/test_fundamentales_consolidado.py. R4, R6 y los notebooks
fundamentales/integración quedaron regenerados. Los brazos R8
mercado_fundamentales y completa se re-corrieron (mismo hash, no suman a D10).
Docs actualizados: riesgos R4 (mitigación), insumo C.2.1/K, pipeline §3.

**Why:** "lo que el mercado precia es el grupo". Una regla única es más
defendible que un umbral de materialidad.
**How to apply:** las cifras de P/E y margen anteriores al 09-oct están marcadas
NO CITAR en el insumo. Ver [[project-r6-integration]] y
[[feedback-deriva-decidido-implementado]].
