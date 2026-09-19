"""OE1 — modelo de costos de transacción (D7).

El costo NO es un detalle de implementación en la BVL: es el término dominante.
Ver `docs/decisiones_pendientes_OE1.txt` D7 y `docs/ejecutabilidad_y_costos_OE1.txt`.

Estructura del costo, POR ACTIVO (nunca único: el spread va de 8 pbs en Alicorp a
220 pbs en Luz del Sur, un orden de magnitud):

    costo_i = max(min_fee, comision_pct · nocional_i) · (1 + IGV)   <- comisión SAB
            + derechos_pct · nocional_i                             <- BVL+Cavali+SMV
            + medio_spread_i · nocional_i                           <- cruzar el spread
            (+ recargo por is_stale, si se activa)

COSTURA PARA BLOOMBERG (la razón por la que esto es una clase y no una constante):
`half_spread_bps` acepta indistintamente
  * un escalar por activo  -> spread CONSTANTE (lo que tenemos hoy: un snapshot
    del 2026-07-27, declarado como supuesto), o
  * una matriz (T, n_activos) -> SERIE DE TIEMPO del spread.
El segundo caso es el que importa: un spread constante subestima el costo justo
en el estrés (2020, 2021), que es cuando el agente quiere operar. Cuando llegue
la serie histórica de puntas, se cambia el argumento y NADA MÁS.

Lo que NO se modela, y se declara:
  * Impacto de mercado ≈ 0 POR CONSTRUCCIÓN. El tope de capacidad (~S/1.8 MM,
    acotado por BCP) mantiene la participación baja. Es un supuesto declarado,
    no una estimación.
  * No hay penalizador de rotación aparte del costo: sería cobrar dos veces.

CIFRAS POR DEFECTO — PENDIENTES DE FUENTE PRIMARIA (D7). Verificado por búsqueda
web el 2026-09-03, NO por el tarifario oficial:
  * Renta 4 Perú publica 0.43% con mínimo S/40 (mercado local, web).
  * Derechos SMV+BVL+Cavali ≈ 0.00755% por lado.
  * Falta confirmar: si el IGV se suma sobre la comisión, si "por operación" es
    por lado o ida y vuelta, y si una cuenta de S/1.8 MM negocia por debajo del
    retail. Esa última cambia el resultado más que cualquier decisión de
    arquitectura, y no está publicada.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Comisión SAB retail publicada (Renta 4 Perú, mercado local web). PENDIENTE de
# confirmar contra el tarifario primario antes de que entre a la tesis.
COMISION_RETAIL = 0.0043
COMISION_MIN_PEN = 40.0
IGV = 0.18
# SMV 0.00135% + BVL 0.0021% + Cavali 0.004095%. Despreciable, pero se incluye
# para no tener que justificar una omisión.
DERECHOS_MERCADO = 0.0000755

# Spread relativo (sell-buy)/mid observado el 2026-07-27 vía listLastValue.
# Es el COSTO DE IDA Y VUELTA; el modelo cobra la mitad por lado.
SPREAD_SNAPSHOT_BPS: dict[str, float] = {
    "ALICORC1": 8.0,
    "INRETC1": 13.0,
    "MINSURI1": 14.0,
    "CPACASC1": 63.0,
    "FERREYC1": 70.0,
    "CREDITC1": 165.0,
    "LUSURC1": 220.0,
}


@dataclass
class CostModel:
    """Costo de transacción por activo, en unidades de dinero.

    Args:
        tickers: orden canónico de los activos (define el eje de columnas).
        half_spread_bps: medio spread por lado, en puntos básicos. Escalar,
            vector (n_activos,) o matriz (T, n_activos) para la serie temporal.
        commission_rate: comisión SAB proporcional, por lado.
        min_fee: comisión mínima por orden, en la moneda del portafolio.
        igv: impuesto sobre la comisión SAB. 0.0 lo desactiva.
        fees_rate: derechos de mercado (BVL+Cavali+SMV), por lado.
        stale_surcharge_bps: recargo cuando el precio venía arrastrado
            (`is_stale`). Por D8, is_stale NO prohíbe operar: encarece.
        cost_multiplier: escala TODO el costo. Es el eje sobre el que se calcula
            el costo de equilibrio c* por bisección (D7); 1.0 = caso base.
    """

    tickers: list[str]
    half_spread_bps: np.ndarray | float = 0.0
    commission_rate: float = COMISION_RETAIL
    min_fee: float = COMISION_MIN_PEN
    igv: float = IGV
    fees_rate: float = DERECHOS_MERCADO
    stale_surcharge_bps: float = 0.0
    cost_multiplier: float = 1.0

    _spread: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        n = len(self.tickers)
        spread = np.asarray(self.half_spread_bps, dtype=float)
        if spread.ndim == 0:
            spread = np.full(n, float(spread))
        if spread.ndim == 1 and spread.shape[0] != n:
            raise ValueError(
                f"half_spread_bps tiene {spread.shape[0]} valores y hay {n} activos"
            )
        if spread.ndim == 2 and spread.shape[1] != n:
            raise ValueError(
                f"half_spread_bps (T, n) tiene {spread.shape[1]} columnas y hay {n} activos"
            )
        if spread.ndim > 2:
            raise ValueError("half_spread_bps debe ser escalar, (n,) o (T, n)")
        if np.any(spread < 0):
            raise ValueError("half_spread_bps no puede ser negativo")
        self._spread = spread

    # ------------------------------------------------------------------ API
    def spread_at(self, day_idx: int) -> np.ndarray:
        """Medio spread por lado (fracción, no pbs) en la fecha dada."""
        row = self._spread[day_idx] if self._spread.ndim == 2 else self._spread
        return row / 10_000.0

    def cost_of_trades(
        self,
        notionals: np.ndarray,
        day_idx: int,
        is_stale: np.ndarray | None = None,
    ) -> np.ndarray:
        """Costo en dinero de operar `notionals[i]` (valor absoluto) por activo.

        Devuelve un vector del mismo largo que `notionals`; los activos con
        nocional 0 pagan 0 (no hay orden, no hay mínimo).
        """
        notionals = np.abs(np.asarray(notionals, dtype=float))
        trades = notionals > 0.0

        comision = np.where(
            trades,
            np.maximum(self.min_fee, self.commission_rate * notionals) * (1.0 + self.igv),
            0.0,
        )
        derechos = self.fees_rate * notionals
        spread = self.spread_at(day_idx) * notionals

        recargo = 0.0
        if self.stale_surcharge_bps and is_stale is not None:
            recargo = (self.stale_surcharge_bps / 10_000.0) * notionals * np.asarray(is_stale)

        return self.cost_multiplier * (comision + derechos + spread + recargo)

    # --------------------------------------------------- banda de no-operación
    def band_notional(self) -> float:
        """Piso económico por orden, en dinero. NO es un parámetro elegido a mano.

        Debajo de este nocional la comisión mínima domina: se paga una tarifa
        fija que, proporcionalmente, es enorme. Con S/40 y 0.43%, el umbral es
        S/9,302 — mover S/2,000 costaría 200 pbs sobre el monto transado.

        Si no hay mínimo (min_fee=0) no hay piso y devuelve 0.0.
        """
        if self.min_fee <= 0 or self.commission_rate <= 0:
            return 0.0
        return self.min_fee / self.commission_rate

    def roundtrip_bps(self, day_idx: int = 0, notional: float = 1e6) -> np.ndarray:
        """Costo de ida y vuelta en pbs por activo, para reportar y auditar.

        `notional` importa porque el mínimo por orden no es proporcional.
        """
        one_way = self.cost_of_trades(np.full(len(self.tickers), notional), day_idx)
        return 2.0 * one_way / notional * 10_000.0


def snapshot_cost_model(tickers: list[str], **kwargs) -> CostModel:
    """CostModel con el spread del snapshot 2026-07-27 para el universo dado."""
    faltan = [t for t in tickers if t not in SPREAD_SNAPSHOT_BPS]
    if faltan:
        raise KeyError(f"sin spread observado para {faltan}; ver §3 de ejecutabilidad_y_costos_OE1")
    # El snapshot es ida y vuelta -> la mitad por lado.
    half = np.array([SPREAD_SNAPSHOT_BPS[t] / 2.0 for t in tickers], dtype=float)
    return CostModel(tickers=list(tickers), half_spread_bps=half, **kwargs)


def zero_cost_model(tickers: list[str]) -> CostModel:
    """Sin fricción. Es el control del experimento y la base de los tests."""
    return CostModel(
        tickers=list(tickers),
        half_spread_bps=0.0,
        commission_rate=0.0,
        min_fee=0.0,
        igv=0.0,
        fees_rate=0.0,
    )
