---
name: project-oe1-estado-20260912
description: "Estado de OE1 al 19-sep-2026: R7 y R8 ACREDITADOS (completa corrida: los canales SE ESTORBAN), D25 explicada (el DSR no ordena), y el TAMIZ de recompensas reprueba a las tres de D4. 85 tests."
metadata: 
  node_type: memory
  type: project
  originSessionId: 1e055472-6017-497c-a723-0142fff6138f
  modified: 2026-09-19T17:43:50.341Z
---

## Lo ACREDITADO

- **R7 ACREDITADO** (18-sep): curvas + modelos .zip + indicador. 1M pasos x 10
  semillas, 9/10 mesetas (mediana ~750k).
- **R8 ACREDITADO** (19-sep): `completa` corrio (9 corridas, 19 min) y con eso
  estan las CUATRO configuraciones que pide el documento.
- **Entorno**: reloj t+1, mascara dura, caja remunerada, costo por activo.
  **85 tests** en verde (los 70 de antes + 15 nuevos de recompensas).
- **Panel** 24,584 x 120, 2012-01-02 a 2025-12-30, validado 7/7 contra Bloomberg.
- OE1 SI ESTA COMMITEADO desde el 18-sep (b1b6dd9 + 22f9cd1). Lo del 19-sep
  (§7.11-7.15, tamiz, 3 recompensas nuevas, 15 tests, brazos de D4 corridos)
  esta SIN COMMITEAR.

## R8 `completa`: LOS CANALES SE ESTORBAN (19-sep)

    aporte pareado vs solo_mercado    ret    sharpe  sortino  maxDD    rot
    mercado_macro                   +1.4pp   +0.384  +0.415  -1.0pp  -0.39
    mercado_sentimiento             +1.8pp   +0.452  +0.653  -2.0pp  +0.73
    mercado_fundamentales           +0.6pp   +0.136  +0.273  -1.6pp  -0.36
    completa                        -0.1pp   +0.113  +0.019  -2.5pp  -0.15
    suma de los 3                   +3.8pp   +0.972  +1.341  -4.5pp  -0.02
    INTERACCION                     -3.9pp   -0.860  -1.322  +2.0pp  -0.13
    [SUPERADO 2026-10-09 con R4 consolidado: -1.3pp ret, -1.088 Sharpe, -1.122 sortino, +3.0pp maxDD. Macro y sentimiento se reprodujeron exactos; fundamentales empeora DD en 9/9; cae el patron monotono con la dimension. resultados §7.13 al final.]

- `completa` no alcanza ni la cuarta parte de la suma en Sharpe. **Juntar los
  canales DILUYE.** 4/9 celdas positivas en retorno, 5/9 en Sharpe (una moneda),
  pero solo **2/9 en drawdown**: lo empeora en 7 de 9, que es la unica senial
  estable. Le gana a la caja 1 de 3, igual que todos.
- **LA PREDICCION PRE-REGISTRADA FALLO**: se escribio que rotaria MAS y la
  rotacion BAJA (-0.15). El deterioro no viene por ahi. La otra mitad (381 dims
  vs 87) queda como hipotesis para las 10 semillas.
- Las otras dos combinadas ya NO son urgentes: servian para descomponer una
  interaccion positiva y la medida es negativa y grande.

## POR QUE ENTRENAR MAS EMPEORA: MEDIDO, ya no es lectura (§7.11)

Reordenando el DSR: `r ∝ (R−A) − (A/2B)·(R²−B)`. **El precio de la varianza es
A/(2B), proporcional a la media movil del retorno.**

- El termino de riesgo pesa **7-10%** de la senial. El DSR es ~90% retorno puro.
- En **44% de los dias de train** el coeficiente sale NEGATIVO: el DSR **PAGA**
  por dispersion. 2013-2018 es plano (1/N +2.4% vs caja +2.6%).
- **EL DSR NO ORDENA**: rho de Spearman +0.11 (train) / +0.36 (val) contra el
  Sharpe del periodo, sobre 18 estrategias reales. En train le paga **5.7x mas
  a Markowitz, que PIERDE plata, que al 1/N, que gana**. En val ordena bien.
  >> El objetivo es fiel cuando hay tendencia y deja de serlo cuando el mercado
     es plano — y el tramo de entrenamiento es el plano. ESO cierra D25.
- **El docstring de rewards.py decia que "sumar los incrementos aproxima el
  Sharpe del periodo" y es FALSO.** Corregido en el codigo.
- NEGATIVO honesto: con los momentos de D25 pareados, el DSR SI prefiere al
  agente de 150k (67% de las muestras). El fallo no esta en los momentos.

## EL TAMIZ (§7.12) — se elige recompensa SIN entrenar y SIN gastar el contador

`scripts/d4_tamiz_recompensas.py`. 18 estrategias reales x 2 tramos, 0 corridas.
Criterio pre-registrado: T1 orden (rho>=0.50), T2 no paga por ruido, T3 el
riesgo pesa (>=20%), T4 ve el peaje (>=1%/bp).

    recompensa    rho tr   rho val  ruido PAGA  peso riesgo  peaje   PASA
    dsr            +0.11    +0.36     44%/36       29.9%    2.03%     no
    ddr            -0.63    -0.38     83%/36       48.2%   -4.69%     no
    logret         +0.98    +0.99      0%/36        0.0%   22.42%     no
    mv             +0.46    +0.23      0%/36       28.5%   27.24%     no
    logret_dd      +0.39    +0.86      0%/36       28.8%    7.99%     no
    dsr_rot        +0.24    -0.52     86%/36       41.0%    0.09%     no

- **CORREGIDO 26-sep: `logret_dd` con λ ∈ [0.63, 0.68] SÍ PASA los 4 criterios**
  en el pliegue 0 (barrido fino; la grilla gruesa saltaba 0.51→1.02). Pliegue 1:
  ventana [0.65, 0.95]; pliegue 2: NINGUNO (T1 val nunca llega a .50). `mv`:
  ninguno. Los brazos de §7.15 usaron λ=1.02 (reprueba T1): el tamiz NO se ha
  contrastado con un brazo que lo pase. Nueva opción (a') en D4, sin mover
  umbrales. Lo de abajo ("no existe λ") queda SUPERADO.
- Antes decía: **NINGUNA PASA** y **no existe λ que cumpla T1 y T3
  a la vez** (barrido completo en §7.12). A frecuencia diaria y sin deriva,
  "ordenar como el Sharpe" y "que el riesgo pese" estan en conflicto directo.
- **LA DDR (V1 de D4) NO DEBE CORRERSE**: ordena AL REVES, paga por ruido en 83%
  y un lastre de costo le SUBE la recompensa. Es la unica recomendacion
  inequivoca. Ahorra 30 corridas del contador.
- **`dsr_rot` no funciona**: se vuelve ciego al costo real. **D7 se sostiene**,
  ahora con medicion.
- **Lo mas cerca: `logret_dd` con λ=0.51** — T1 0.74/0.93 holgado, T3 16.8% vs
  umbral 20%. Su fidelidad contra el DRAWDOWN es +0.82/+0.78 ESTABLE en todo el
  barrido, y §7.7 dice que el drawdown es la ventaja medida del agente.

## LOS BRAZOS CORRIDOS (19-sep): EL TAMIZ **NO** PREDICE

18 corridas, `mv` λ=16.29 y `logret_dd` λ=1.02. Diferencia PAREADA vs dsr:

    brazo         ret    sharpe   maxDD     rot    signos+ (ret)
    mv          -0.2pp   -0.194  +1.2pp   -0.225       4/9
    logret_dd   -2.2pp   +0.038  -3.0pp   +0.124       4/9

- **LAS DOS CONDICIONES DE FALSACION SE CUMPLIERON**: `logret_dd` rota MAS
  que el DSR y su drawdown sale PEOR (-3.0pp, mejor en solo 4/9). Se reporta el
  tamiz como FALLIDO para predecir; no se le busca lectura que lo salve.
- SOBREVIVE el tamiz como CARACTERIZACION de la recompensa (que la DDR ordene
  al reves es propiedad de la FUNCION). Sirve para DESCARTAR una rota, no para
  ELEGIR entre sanas.
- **le gana a la caja: dsr 1/3 · mv 0/3 · logret_dd 0/3. CAMBIAR LA RECOMPENSA
  NO MUEVE LA VARA.**

## LAS TRES VIAS DE MEJORA, LAS TRES MEDIDAS Y LAS TRES NEGATIVAS

    computo      §7.9   entrenar mas EMPEORA
    recompensa   §7.15  las tres formas dan lo mismo
    señal        §7.13  los canales se ESTORBAN, ninguno mueve D9

>> El problema no esta en el objetivo, ni en el presupuesto, ni en que falten
   canales: FALTA SEÑAL EXPLOTABLE, O EL PEAJE SE LA COME. Es consistente con
   lo que enseño Markowitz (§4.1): genera bruto y el costo se lo lleva entero.
   ESO YA NO ES UN DEFECTO DEL METODO, ES EL RESULTADO DE LA TESIS.
   (3 semillas: nada es hallazgo hasta las 10 de D10. Lo establecido es lo
   NEGATIVO: no hay motivo para gastar el contador en mas brazos de D4.)

## LO QUE HAY QUE DECIDIR (enmienda a D4, es del autor)

(a) Bajar T3 a 15% y adoptar `logret_dd` λ=0.51 — mover un umbral despues de
    ver. (b) Medir T1 contra el drawdown. (c) Quedarse con el DSR y REPORTAR EL
    TAMIZ COMO RESULTADO NEGATIVO (lo mas honesto y probablemente lo mas
    publicable). (d) Correr `mv` y `logret_dd` 18 corridas ~45 min para ver si
    el tamiz PREDICE el desempeño — eso valida el METODO, que vale mas.

## Codigo nuevo del 19-sep

- `src/env/rewards.py`: +3 recompensas (`mv`, `logret_dd`, `dsr_rot`), interfaz
  `step(net_return, turnover=0.0)`, λ/κ SIN defecto (guarda que falla temprano).
- `scripts/d4_diagnostico_recompensas.py` · `scripts/d4_tamiz_recompensas.py`
- `tests/test_rewards_d4.py` (15 tests; clava los hallazgos de 7.11/7.12)
- `scripts/ablacion_r8.py` gano `--out` (antes una corrida parcial pisaba el JSON)

## Cifras VIGENTES del piloto (pliegue 0, val, mediana de 3 semillas)

    accion RELATIVA   ret +2.6%  sharpe +0.18  maxDD -4.2%  rot 1.97  caja 62%
    1/N diario        ret +11.9% sharpe +0.90  maxDD -10.2% rot 1.97
    solo caja         ret +1.9%
    completa          ret +2.8%  sharpe +0.13  maxDD -7.8%  rot 1.78  caja 38%

Registro D10: **134 corridas, 31 configuraciones distintas, con_test = 0.**

## Decisiones ABIERTAS

- **D4 REABIERTA** (ver arriba). **D29 NUEVA**: si el tamiz es vinculante.
- D23 ventana expanding vs rolling · D24 condicion inicial · D25 presupuesto
  (MEDIDA, falta pre-registrar la parada por rotacion, techo 1.97) · D26
  parametros de Markowitz.

## Trampa recurrente SIN RESOLVER

`stale_surcharge_bps` existe en `CostModel` pero **vale 0.0 en todas las
corridas** — `snapshot_cost_model()` se llama sin kwargs. D8 dice que `is_stale`
encarece y en los hechos no encarece nada. Van DOS sesiones con esto anotado.

## Lo que falta

1. Commitear lo del 19-sep.
2. Enganchar las puntas de Bloomberg al CostModel (xlsx->parquet, 142 dias
   fantasma, reconciliacion pre-registrada). Horas de trabajo en casa.
3. Cerrar la enmienda de D4 y correr R8 definitivo (10 semillas).
4. Tarifario primario de la SAB · indice local SPBLPGPT · P/B · SAC y DDPG.

## R7 multi-algoritmo (26-sep) — CÓDIGO LISTO, SIN CORRER

- Inconsistencia #2 RESUELTA por el autor: PPO + SAC + DDPG (manda el documento). D3 enmendada.
- `src/agents/algoritmos.py`: fábrica única; SAC/DDPG pasan por `AccionAcotada`
  (x∈[-1,1] -> artanh(x); biyección, mismo conjunto alcanzable que PPO). La config
  PPO del registro queda con el MISMO hash (test contra el registro real).
- `ablacion_r8.py --algo {ppo,sac,ddpg}`; `--sac-ent-coef` y `--ddpg-sigma` SIN defecto.
- `scripts/calibra_exploracion_r7.py`: criterio D22 (rotación, solo train, sin registro).
  Referencia PPO log_std=-2 en modo delta: 5.99 rot/año (D22 medía 31 en logits).
- VELOCIDAD: SAC ~14 ms/paso en CPU -> ~35 min por corrida de 150k (PPO ~0.6 min).
- FALTA: correr la calibración completa y que el autor fije ent_coef/σ en D3.
- 96 tests. pytest se instaló el 26-sep (no está en requirements.txt).
- CALIBRACIÓN CORRIDA 26-sep (exploracion_r7.json + _fino.json), criterio = PEAJE DEL RUIDO (est − det),
  ref PPO 5.99: **propuesta DDPG σ=0.15 (0.90x) · SAC ent_coef=0.03 (1.07x)** — FALTA que el autor la
  fije en D3. SAC det ya rota 21.7/año a 20k pasos (síntoma D22). SAC 11.5 ms/paso ≈ 29 min/corrida.
- SIN COMMITEAR (26-sep): src/agents/, tests/test_agentes_r7.py, calibra_exploracion_r7.py, ablacion_r8.py,
  train_ppo_oe1.py, decisiones (D3), inconsistencias (#2).
