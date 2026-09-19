"""OE1 — vistas de señales y normalización causal (D5, D6, R8).

FRONTERA CON R6 (ver hallazgos_integracion_R6.txt): R6 entrega el panel limpio,
causal y alineado; OE1 le DA FORMA. Acá vive esa forma: qué columnas entran, qué
transformaciones se aplican y cómo se normalizan. R6 no se re-reconcilia.

D6 — NORMALIZACIÓN CAUSAL, decidida el 2026-09-03:
  * media y desviación EXPANDING, calculadas POR ACTIVO, solo con información
    hasta t. Es causal aunque se aplique dentro del tramo de prueba: nunca mira
    hacia adelante. Lo prohibido es el z-score sobre toda la muestra.
  * winsorización a ±5σ, para que un salto único no domine la escala.
  * calentamiento de 250 días antes de emitir observaciones.
  * los acotados por construcción (rsi_14) NO se estandarizan: se escalan.
  * log1p(days_since_news), ya decidido conceptualmente en R6.

POR ACTIVO Y NO GLOBAL: es el mecanismo 1 de D11, el de costo cero. Convierte
"intensidad absoluta" en "intensidad relativa a la propia historia del activo" y
resuelve el grueso de la heterogeneidad de cobertura entre BCP (577 eventos) y
Minsur (~74) con una sola red de pesos compartidos.

ESCALABILIDAD (por la reunión del 2026-09-02): las vistas se componen de GRUPOS
de columnas, y los grupos se resuelven por prefijo o por lista. Cuando lleguen
las columnas nuevas —sorpresa de fundamentales, P/B, índices externos como
`macro_spx`, features de ADR— basta agregarlas al grupo; ningún consumidor
cambia.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .fundamental_shape import agrega_forma_fundamental

# --------------------------------------------------------------------------
# Grupos de columnas. Un grupo es una lista de nombres exactos y/o prefijos.
# --------------------------------------------------------------------------

#: Derivadas que calcula OE1 a partir del panel. Se definen acá y no en R6
#: porque son "forma", no dato: el nivel de precio es no estacionario y
#: estandarizarlo con estadísticas expanding produce una feature con tendencia.
#: Las razones precio/media móvil sí son estacionarias.
DERIVED: dict[str, tuple[str, str]] = {
    "dist_sma_20": ("close_total_return", "sma_20"),
    "dist_sma_50": ("close_total_return", "sma_50"),
    "dist_ema_12": ("close_total_return", "ema_12"),
    "dist_ema_26": ("close_total_return", "ema_26"),
}

GROUPS: dict[str, list[str]] = {
    "mercado": [
        "ret_1d",
        "dist_sma_20",
        "dist_sma_50",
        "dist_ema_12",
        "dist_ema_26",
        "macd",
        "macd_signal",
        "rsi_14",
        "volatility_20",
        "is_no_trade",
        "is_stale",
    ],
    # Prefijo: cuando entren S&P 500, MSCI EM o China (reunión 2026-09-02, B2)
    # llegan como macro_* y quedan incluidos sin tocar este archivo.
    "macro": ["macro_"],
    # CANAL PRIMARIO — las 9 columnas de D15(b), ni una más: 3 polaridades
    # (pos/neu/neg) x 3 escalas (5/20/60), más 4 columnas de contexto. La
    # magnitud NO multiplica (D15(a)): sobrevive solo como puerta de relevancia.
    "sentimiento": [
        "has_news",
        "days_since_news",
        "n_articles",
        "n_relevantes",
        "sent_pos_ewma_",
        "sent_neu_ewma_",
        "sent_neg_ewma_",
    ],
    # BRAZO CONDICIONAL DE D15(c) — 18 columnas: 2 tramos (ALTO vs RESTO) x 3
    # polaridades x 3 escalas. El panel YA las trae; se declaran acá para que
    # correr el brazo sea cambiar un string.
    # NO SE CORRE POR DEFECTO: D15(c) dice que esta resolución "se compra SOLO
    # si el canal de 9 muestra señal primero". Duplicar el canal sin señal en el
    # canal simple es gastar dimensión y una configuración del contador de D10.
    "sentimiento_18": [
        "has_news",
        "days_since_news",
        "n_articles",
        "n_relevantes",
        "sent_alto_pos_ewma_",
        "sent_alto_neu_ewma_",
        "sent_alto_neg_ewma_",
        "sent_resto_pos_ewma_",
        "sent_resto_neu_ewma_",
        "sent_resto_neg_ewma_",
    ],
    # NIVELES + FORMA. Los niveles entran como escalón arrastrado de ~90 días;
    # la forma (sorpresa y distancia a la media móvil) la agrega
    # `fundamental_shape.agrega_forma_fundamental` y entra por prefijo, así que
    # sumar una columna nueva no obliga a tocar este archivo. Acta §B3/B4.
    "fundamentales": [
        "roe",
        "roa",
        "net_margin",
        "debt_equity",
        "debt_ratio",
        "pe",
        "dy",
        "pe_reliable",
        "known_date_real",
        "pb",
        "es_financiero",
        # --- forma (B3): sorpresa, pico fechado y distancia a la media móvil ---
        "sue_",
        "pico_sue_",
        "fund_dist_ma",
        "sue_valido",
        "dias_desde_resultado",
        "surprise_",  # nombre alternativo, por si R6 las provee algún día
    ],
}

#: Vistas de la ablación de R8.
#:
#: CORREGIDO EL 2026-09-12 — ERA UN DEFECTO QUE INVALIDABA LA ABLACIÓN.
#: Hasta hoy `mercado_sentimiento` y `mercado_fundamentales` incluían `macro`
#: adentro. Con eso, comparar `mercado_sentimiento` contra `solo_mercado` medía
#: el aporte de SENTIMIENTO **MÁS MACRO** y lo atribuía entero al sentimiento:
#: la ablación habría sido INATRIBUIBLE. Ver la entrada #3 de
#: docs/inconsistencias_documento_vs_implementacion.txt.
#:
#: AHORA CADA VISTA AÑADE UN SOLO CANAL SOBRE LA MISMA BASE, y el aporte de cada
#: uno es la diferencia contra `solo_mercado`. Las vistas combinadas se conservan
#: aparte para poder medir interacción (si `completa` supera a la suma de los
#: aportes individuales, los canales se complementan).
VIEWS: dict[str, list[str]] = {
    # --- base y brazos LIMPIOS de la ablación: un canal cada uno ---
    "solo_mercado": ["mercado"],
    "mercado_macro": ["mercado", "macro"],
    "mercado_sentimiento": ["mercado", "sentimiento"],
    "mercado_fundamentales": ["mercado", "fundamentales"],
    # --- combinadas: para interacción, NO para atribuir a un canal ---
    "mercado_macro_sentimiento": ["mercado", "macro", "sentimiento"],
    "mercado_macro_fundamentales": ["mercado", "macro", "fundamentales"],
    "completa": ["mercado", "macro", "sentimiento", "fundamentales"],
    # --- brazo condicional de D15(c), ver GROUPS["sentimiento_18"] ---
    "mercado_sentimiento_18": ["mercado", "sentimiento_18"],
}

#: Brazos que la ablación de R8 compara contra `solo_mercado` para ATRIBUIR el
#: aporte de un canal. Se declara acá para que el consumidor no tenga que
#: acordarse de cuáles son limpias y cuáles no.
VISTAS_ABLACION: tuple[str, ...] = (
    "solo_mercado", "mercado_macro", "mercado_sentimiento", "mercado_fundamentales",
)

#: Columnas 0/1 o ya acotadas: no se estandarizan.
PASSTHROUGH = {
    "is_no_trade",
    "is_stale",
    "has_news",
    "pe_reliable",
    "known_date_real",
    "is_split_adjusted",
    "is_div_adjusted",
    "es_financiero",
    # La sorpresa YA viene estandarizada por su propia sigma (es un z-score por
    # construcción). Volver a estandarizarla con estadísticas expanding la
    # aplastaría y le quitaría justo lo que la hace informativa: la magnitud.
    "sue_valido",
}

#: Prefijos que tampoco se re-estandarizan, por la misma razón que `sue_`.
PASSTHROUGH_PREFIJOS = ("sue_", "pico_sue_")

#: Columnas acotadas que solo se reescalan a [0, 1].
BOUNDED: dict[str, float] = {"rsi_14": 100.0}

#: Columnas a las que se aplica log1p antes de normalizar (colas muy largas).
LOG1P = {"days_since_news", "n_articles", "n_relevantes"}

WINSOR_SIGMA = 5.0
WARMUP_DEFAULT = 250


def resolve_columns(groups: list[str], available: list[str]) -> list[str]:
    """Expande grupos a nombres de columna concretos, en orden estable."""
    out: list[str] = []
    for g in groups:
        if g not in GROUPS:
            raise KeyError(f"grupo desconocido: {g!r}. Opciones: {sorted(GROUPS)}")
        for spec in GROUPS[g]:
            if spec in available:
                if spec not in out:
                    out.append(spec)
            else:  # prefijo
                for col in available:
                    if col.startswith(spec) and col not in out:
                        out.append(col)
    return out


def _expanding_z(x: np.ndarray, warmup: int) -> np.ndarray:
    """Z-score expanding a lo largo del eje 0 (tiempo), columna por columna.

    Usa sumas acumuladas: la estadística en t incluye a t y nada posterior, que
    es exactamente la definición causal de D6. Los NaN se tratan como faltantes
    y no contaminan la media (se cuentan aparte).
    """
    x = np.asarray(x, dtype=float)
    valid = np.isfinite(x)
    filled = np.where(valid, x, 0.0)

    n = np.cumsum(valid, axis=0)
    s1 = np.cumsum(filled, axis=0)
    s2 = np.cumsum(filled * filled, axis=0)

    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(n > 0, s1 / np.maximum(n, 1), 0.0)
        var = np.where(n > 1, s2 / np.maximum(n, 1) - mean * mean, 0.0)
        std = np.sqrt(np.maximum(var, 0.0))
        z = np.where(std > 1e-12, (x - mean) / np.where(std > 1e-12, std, 1.0), 0.0)

    z = np.clip(z, -WINSOR_SIGMA, WINSOR_SIGMA)
    z = np.where(valid, z, 0.0)
    if warmup > 0:
        z[:warmup] = 0.0
    return z


@dataclass
class FeatureTensor:
    """Salida de `build_features`: listo para el entorno, sin pandas adentro."""

    values: np.ndarray  # (T, n_activos, n_features), float32
    columns: list[str]
    tickers: list[str]
    warmup: int

    @property
    def n_features(self) -> int:
        return self.values.shape[2]

    def flat_dim(self) -> int:
        return self.values.shape[1] * self.values.shape[2]


def build_features(
    panel: pd.DataFrame,
    tickers: list[str],
    view: str = "completa",
    warmup: int = WARMUP_DEFAULT,
) -> FeatureTensor:
    """Construye el tensor de features normalizadas para una vista.

    Args:
        panel: panel largo de R6 (una fila por ticker-fecha), ya ordenado.
        tickers: orden canónico de activos.
        view: nombre en `VIEWS`.
        warmup: días iniciales con observación puesta a cero (D6).
    """
    if view not in VIEWS:
        raise KeyError(f"vista desconocida: {view!r}. Opciones: {sorted(VIEWS)}")

    df = panel.copy()
    # Derivadas de OE1 (razones precio/media móvil), antes de resolver columnas.
    for name, (num, den) in DERIVED.items():
        if num in df.columns and den in df.columns:
            df[name] = df[num] / df[den].replace(0.0, np.nan) - 1.0

    # Forma de la señal fundamental (acta §B3): sorpresa, pico fechado en
    # known_date y distancia a la media móvil. Solo si la vista los pide: en
    # `solo_mercado` calcularlos sería trabajo tirado.
    if "fundamentales" in VIEWS[view]:
        df = agrega_forma_fundamental(df)

    cols = resolve_columns(VIEWS[view], list(df.columns))
    if not cols:
        raise ValueError(f"la vista {view!r} no resolvió ninguna columna")

    dates = np.sort(df["date"].unique())
    n_t, n_a = len(dates), len(tickers)
    out = np.zeros((n_t, n_a, len(cols)), dtype=np.float32)

    for j, col in enumerate(cols):
        wide = (
            df.pivot(index="date", columns="ticker", values=col)
            .reindex(index=dates, columns=tickers)
            .to_numpy(dtype=float)
        )
        if col in PASSTHROUGH or col.startswith(PASSTHROUGH_PREFIJOS):
            # NO re-estandarizar y NO winsorizar son DOS decisiones distintas, y
            # hasta el 2026-09-18 este `if` las trataba como una sola. La
            # sorpresa ya viene estandarizada por su propia sigma, así que
            # volver a pasarle un z-score expanding la aplastaría — ese era y
            # sigue siendo el argumento. Pero de ahí no se sigue que deba entrar
            # SIN ACOTAR: `sue_roe` llegaba a -22.46, o sea cuatro veces el
            # rango de TODAS las demás features, y el canal fundamental era el
            # único que escapaba al ±5σ de D6.
            #
            # POR QUÉ IMPORTA PARA R8 Y NO ES COSMÉTICA: si el brazo
            # `mercado_fundamentales` entrenara peor por escala, no habría forma
            # de distinguir "los fundamentales no aportan" de "el brazo tenía
            # las features mal escaladas". Y el criterio de abandono de D11 dice
            # que si el canal no supera al baseline, EL CANAL NO SE TOMA: una
            # ablación sesgada en contra mata un canal que sí servía.
            #
            # El recorte preserva la intención (la magnitud sigue siendo
            # informativa DENTRO del rango) y alinea el canal con el resto. Las
            # columnas binarias de PASSTHROUGH viven en [0, 1], así que para
            # ellas esto es la identidad. Ver D6 (enmendada) y D27.
            block = np.clip(np.nan_to_num(wide, nan=0.0), -WINSOR_SIGMA, WINSOR_SIGMA)
        elif col in BOUNDED:
            block = np.nan_to_num(wide, nan=0.0) / BOUNDED[col]
        else:
            if col in LOG1P:
                wide = np.log1p(np.clip(wide, 0.0, None))
            block = _expanding_z(wide, warmup)
        out[:, :, j] = block.astype(np.float32)

    if not np.all(np.isfinite(out)):
        raise ValueError("quedaron valores no finitos en el tensor de features")

    return FeatureTensor(values=out, columns=cols, tickers=list(tickers), warmup=warmup)
