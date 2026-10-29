---
name: project-oe1-decisiones-cerradas
description: "2026-09-03: tras la reunión con el especialista de mercado, D2-D10 quedaron CERRADAS y arranca el MVP de OE1. Reemplaza cualquier nota que diga que D4-D10 siguen abiertas."
metadata: 
  node_type: memory
  type: project
  originSessionId: a4bf0392-6869-48a5-93a7-71a7e9156ede
  modified: 2026-09-03T22:18:36.781Z
---

Reunión con especialista de mercado el **2026-09-02**. Acta completa y decisiones
en `docs/decisiones_pendientes_OE1.txt` (sección ACTA + entradas D2-D10, D21).
**D1-D9 CERRADAS; D10 y D7 cerradas en forma.** Ya NO bloquea nada para construir
el entorno.

Las decisiones, en una línea cada una:
- **D2** símplex continuo de 8 (7 activos + caja) por softmax; el activo enmascarado
  conserva su peso y se renormaliza sobre el remanente.
- **D3** PPO primario; SAC como UNA verificación de robustez, no brazo de la grilla.
- **D4** **Sharpe diferencial (DSR) de Moody-Saffell**, ENMENDANDO la propuesta del
  02-sep que tenía la DDR (semivarianza) como primaria. El especialista pidió Sharpe;
  su argumento literal ("el Sortino es de fondos apalancados") es incorrecto, pero la
  conclusión se adopta porque **el DSR elimina λ** — el ajuste al riesgo está en la
  forma funcional. Se cambia λ por η (vida media, pre-registrable). Brazos: DSR / DDR / λ=0.
  `A_t` y `B_t` van en la observación (si no, la recompensa no es markoviana).
- **D5** ventana apilada + MLP, sin recurrencia: la memoria ya está en las EWMAs 5/20/60.
- **D6** normalización expanding POR ACTIVO, winsor ±5σ, calentamiento 250 días.
- **D7** costo por activo dentro de V_neto, sin penalizador de rotación extra.
  **Se RETIRÓ la grilla hasta 400 pbs** (estaba mal compuesta: mezclaba el peor spread
  con el portafolio, y costo sobre patrimonio en vez de sobre rotación). Techo real
  ~306 pbs. Se reporta **c\* continuo por bisección**, no una grilla.
  **La banda de no-operación se DERIVA del mínimo de S/40 por orden ≈ 0.52% del
  portafolio**, ya no se elige a mano.
- **D8** máscara dura en `is_no_trade`; `is_stale` es recargo de costo, no prohibición.
- **D9** caja remunerada a `macro_tasa_ref`/365.
- **D10** baselines ampliados (+ índice local, EPU, banda nula Dirichlet), cada baseline
  con su propia frecuencia óptima. **Falta decidir el split**: la recomendación es
  walk-forward de 3-4 pliegues con embargo de 20 días.
- **D21** MVP de extremo a extremo SÍ, pero **el piloto no toca el tramo de prueba**
  (train+val solamente), o las corridas contarían para el Sharpe deflactado.

**MEDIDO el 03-sep, contra la afirmación del especialista:** el factor común de la BVL
para estos 7 activos es **PC1 = 29.7% diario / 35.5% semanal / 45.1% mensual**, NO 70%
(correlación media por pares 0.229). `scripts/mide_comovimiento_oe1.py`. Colateral:
**solo 9.3% de las fechas tienen a los 7 activos transando el mismo día.**

**Tarifario verificado:** el 0.4% del especialista NO era exagerado (Renta 4 publica
0.43% + mínimo S/40); los derechos SMV+BVL+Cavali son ~0.76 pbs, despreciables.
Pendiente de fuente primaria: IGV, si "por operación" es por lado, y si S/1.8 MM
negocia por debajo del retail.

**ENTORNO CONSTRUIDO Y VERIFICADO (2026-09-03)**: paquete `src/env/` (panel, features,
costs, rewards, portfolio_env, policies) + `tests/test_portfolio_env.py` — 12 tests, todos
pasan, incluidos los 4 de conservación (buy&hold exacto, 1/N exacto, caja a rf compuesta,
simplex+mascara). Humo en `scripts/smoke_env_oe1.py`.

**PRIMEROS NUMEROS REALES (baselines, 3,261 dias):** el costo se come 24 puntos (1/N diario
34.4% -> 10.2%, S/368k de peaje); la frecuencia optima es INTERIOR (trimestral 24.9% > mensual
21.3% > semanal 19.3% > diario 10.2%, pero buy&hold 4.9%); **la CAJA gana con 40.5% y drawdown
0% contra -45%** — en 2012-2025 el universo rindio menos que la tasa de referencia, asi que la
vara del agente no es 1/N sino el banco; y el 1/N mensual esta POR DEBAJO de la mediana de la
banda nula (25.6%). Costo ida y vuelta calculado: 111 pbs (Alicorp) a 323 (Luz del Sur).

**PILOTO CERRADO (D21/D22, 03-sep)**: dos bugs de parametrizacion encontrados y corregidos.
(1) exploracion: el defecto de SB3 (log_std_init=0) rota 206 veces/anio sobre un simplex — el
ruido paga el peaje y el gradiente no puede atribuirlo; se calibra por ROTACION, no por
desempenio (log_std=-2, ent_coef=0). gSDE MEDIDO Y DESCARTADO (empeora: 63 vs 31).
(2) **D2 ENMENDADA: accion RELATIVA** (w_obj = normaliza(w_actual + 0.05*tanh(a))) — con la
accion absoluta, no-operar era inalcanzable. Rotacion 9.09 -> 2.01 (1/N: 1.96).

**EL HALLAZGO QUE IMPORTA**: en el pliegue 0 train y val son REGIMENES OPUESTOS —
train 2013-2018 el 1/N da 1.65%/anio con -46.5% de drawdown y la CAJA da 2.63%; val 2018-2019
el 1/N da 11.91%. El agente aprende a quedarse 65% en caja, que es CORRECTO para lo que vio.
Consecuencias: reportar un solo pliegue es enganioso (los 3 de D10 son requisito, no mejora);
D9 queda validada por la via incomoda; y la evaluacion debe poder PREMIAR salirse del mercado.
Costo medido: **1.1% del capital por unidad de rotacion anual**.

**TRAMPA DE REPO**: `.gitignore` tenia `env/` sin anclar y se tragaba `src/env/` entero.
Corregido a `/env/`. Si alguien pega un .gitignore estandar de Python, vuelve a pasar.

Ver [[project-oe1-plan-iliquidez]], [[project-capacidad-liquidez-oe1]],
[[project-r5-evaluacion-integral]] y [[feedback-deriva-decidido-implementado]].
