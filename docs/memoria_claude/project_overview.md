---
name: project-overview
description: Descripción general del proyecto tesis DRL aplicado a la BVL
metadata: 
  node_type: memory
  type: project
  originSessionId: 6b3cf012-0289-48a6-859c-e55c8474dca2
---

## Tesis: Pipeline de datos OE2 (R3-R6)

**Objetivo:** DRL (Deep Reinforcement Learning) aplicado a la Bolsa de Valores de Lima (BVL).
**Asesor:** Dr. E. Villanueva. **Alumno:** Rodrigo Holguin (raholguinhuari@gmail.com)

**Universo (5 empresas):**
| Sector       | Empresa            | BVL      | Yahoo        |
|--------------|--------------------|----------|--------------|
| Banca        | BCP                | CREDITC1 | CREDITC1.LM  |
| Minería      | Buenaventura       | BUENAVC1 | BVN (NYSE)   |
| Alimentos    | Alicorp            | ALICORC1 | ALICORC1.LM  |
| Retail       | Saga Falabella     | SAGAC1   | SAGAC1.LM    |
| Manufactura  | Aceros Arequipa    | CORAREC1 | CORAREC1.LM  |

**Período:** 2005-01-01 a 2025-12-31 (20 años)

**Pipeline:**
- R3 (mercado): BVL (dataondemand share-values, fuente primaria) + Yahoo (solo
  enriquecimiento OHLC puntual) + capa de acciones corporativas. Cerrado jun-2026.
  Ver [[project-r3-corporate-actions]].
- R4 (fundamentales): SMV WSDL. Implementado — 84 periodos 2005-Q1 a 2025-Q4 para las 5 empresas.
- R5 (sentimiento): Media Cloud API (collection 34412158) + Ollama gemma3:4b local. En progreso.
- R6 (integración): Dataset unificado. Pendiente.

**Estado actual (junio 2026):**
- Mercado: horizonte EFECTIVO 2012-2025 para los 5 activos (no 2005-2025; ver
  [[project-r3-corporate-actions]] sobre por qué se descartó 2008-2011/2005-2011
  de Yahoo). data/raw/market_*_{bvl,yahoo}.parquet + data/interim/market_*.parquet
  (con close_raw/close_split_adj/close_total_return + flags).
- Fundamentales: data/raw/fund_*_smv.parquet (84 trimestres 2005-2025) + data/raw/smv_cache/
  (R4 SÍ cubre 2005-2025 completo, a diferencia de mercado).
- Notebooks: exploracion_datos_bvl.ipynb (mercado + acciones corporativas, sección 9) y
  exploracion_fundamentales_bvl.ipynb (rango completo 2005-2025, 84 trimestres) — ambos al día.
- R5: Peru National collection_id = 34412158; LLM = ollama gemma3:4b; estimacion de volumen en curso

**Why:** Tesis doctoral de Rodrigo Holguin.
**How to apply:** El proyecto sigue la estructura src/{market,fundamentals,sentiment,integration}.
Al hablar de "el horizonte" del proyecto, distinguir mercado (2012-2025) de
fundamentales (2005-2025) — no son el mismo rango.
