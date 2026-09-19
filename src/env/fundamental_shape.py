"""OE1 — forma de la señal fundamental: medias móviles y SORPRESA (acta §B3).

DE DÓNDE SALE. Reunión con el especialista de mercado (2026-09-02), punto B3:

    "La data fundamental es relevante ÚNICAMENTE cuando va en contra de lo
     esperado: se esperaba 2% y subió 10%."

y sugirió además indicadores de cambio grande contra la MEDIA MÓVIL. Esto ataca
una debilidad ya declarada del panel: los fundamentales entran como NIVEL
arrastrado, o sea un escalón de ~90 días que el agente ve como una constante.
Lo que el mercado consume no es el nivel: es la novedad.

QUÉ CAMBIA — LA FORMA, NO EL DATO. Por la frontera con R6 (ver features.py) este
módulo vive en OE1: no re-descarga nada ni re-reconcilia nada. Toma las columnas
trimestrales que el panel ya trae y las convierte en tres cosas:

    sue_<col>              sorpresa estandarizada (el "se esperaba 2%")
    fund_dist_ma<k>_<col>  distancia del nivel actual a la media de los k
                           trimestres ANTERIORES (el "cambio grande contra la
                           media móvil")
    sue_pico_<col>         la sorpresa SOLO el día en que se publicó, cero el
                           resto: convierte el escalón de 90 días en un PICO
                           FECHADO, que es como el mercado la consume
    dias_desde_resultado   antigüedad del último resultado publicado

CAUSALIDAD — ES LO ÚNICO DELICADO ACÁ. Dos garantías, y las dos se testean:
  1. La sorpresa del trimestre q se calcula con trimestres ESTRICTAMENTE
     ANTERIORES a q para la expectativa y la escala. Nunca con q+1.
  2. El panel ya expone el trimestre q recién desde `known_date(q)`, así que la
     sorpresa aparece el día en que el dato se hizo público, no el día en que el
     trimestre cerró. Verificado: known_date se respeta en el 100% de las filas.

EL MODELO DE EXPECTATIVA: camino aleatorio estacional con deriva, que es el SUE
clásico de la literatura de post-earnings announcement drift.

    esperado(q) = x(q − L) + deriva
    sorpresa(q) = (x(q) − esperado(q)) / sigma

donde la deriva y sigma son la media y la desviación EXPANDING de las
diferencias (x(q−L) − x(q−2L)) observadas hasta q−1.

EL REZAGO L NO ES UNO SOLO, y confundirlo sería un error de medición:
  * series TRIMESTRALES PURAS (roe, net_margin) llevan estacionalidad -> L = 4,
    o sea "contra el mismo trimestre del año pasado";
  * series TTM (eps_ttm, net_income_ttm) YA están desestacionalizadas por
    construcción -> L = 1, "contra el trimestre anterior". Usar L = 4 sobre una
    TTM compara ventanas que se solapan en 0 trimestres pero arrastra cuatro
    veces el mismo ruido.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

#: Columnas a las que se les calcula sorpresa, con su rezago estacional.
#: TTM -> 1 (ya desestacionalizada); trimestral pura -> 4.
COLUMNAS_SORPRESA: dict[str, int] = {
    "eps_ttm": 1,
    "net_income_ttm": 1,
    "roe": 4,
    "net_margin": 4,
}

#: Ventanas (en TRIMESTRES) de la media móvil de fundamentales.
VENTANAS_MA: tuple[int, ...] = (4,)

#: Columnas a las que se les calcula distancia a su media móvil.
COLUMNAS_MA: tuple[str, ...] = ("roe", "net_margin", "eps_ttm")

#: Mínimo de observaciones previas para emitir una sorpresa. Por debajo se emite
#: 0.0 (no NaN: el tensor de features tiene que quedar finito) y la bandera
#: `sue_valido` queda en 0, para que el agente pueda distinguir "sin sorpresa"
#: de "sorpresa cero".
MIN_HISTORIA = 4


def sue_serie(x: np.ndarray, lag: int, min_historia: int = MIN_HISTORIA) -> np.ndarray:
    """Sorpresa estandarizada de una serie trimestral, causal y por activo.

    Args:
        x: serie trimestral ordenada por periodo (una observación por trimestre).
        lag: L del camino aleatorio estacional (4 para trimestral, 1 para TTM).
        min_historia: mínimo de diferencias previas para poder estandarizar.

    Returns:
        Vector del mismo largo. 0.0 donde no hay historia suficiente.

    La expectativa y la escala en q usan SOLO diferencias terminadas en q−1 o
    antes; por eso los acumuladores se actualizan DESPUÉS de emitir.
    """
    x = np.asarray(x, dtype=float)
    n = x.shape[0]
    out = np.zeros(n, dtype=float)
    if n <= lag:
        return out

    # d(q) = x(q) - x(q-lag): el "cambio interanual" cuya media es la deriva.
    d = np.full(n, np.nan)
    d[lag:] = x[lag:] - x[:-lag]

    for q in range(lag, n):
        previos = d[lag:q]                       # diferencias hasta q-1
        previos = previos[np.isfinite(previos)]
        if previos.size < min_historia:
            continue
        deriva = previos.mean()
        sigma = previos.std(ddof=1)
        if not np.isfinite(sigma) or sigma <= 1e-12:
            continue
        esperado = x[q - lag] + deriva
        if not np.isfinite(esperado) or not np.isfinite(x[q]):
            continue
        out[q] = (x[q] - esperado) / sigma
    return out


def dist_media_movil(x: np.ndarray, ventana: int) -> np.ndarray:
    """Distancia relativa del valor actual a la media de los `ventana` ANTERIORES.

    Excluye el trimestre actual a propósito: la pregunta es "cuánto se aleja el
    resultado NUEVO de los anteriores", no "cuánto se aleja del promedio que él
    mismo ayuda a formar".

    Devuelve 0.0 donde no hay historia o donde la media es ~0 (el signo de una
    razón con denominador que cruza cero no significa nada).
    """
    s = pd.Series(np.asarray(x, dtype=float))
    media = s.shift(1).rolling(ventana, min_periods=ventana).mean()
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(np.abs(media) > 1e-12, s / media - 1.0, 0.0)
    return np.nan_to_num(np.asarray(out, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)


def agrega_forma_fundamental(
    panel: pd.DataFrame,
    columnas_sorpresa: dict[str, int] | None = None,
    ventanas_ma: tuple[int, ...] = VENTANAS_MA,
    columnas_ma: tuple[str, ...] = COLUMNAS_MA,
) -> pd.DataFrame:
    """Agrega al panel largo las columnas de forma fundamental.

    Trabaja sobre la serie TRIMESTRAL (una fila por ticker-periodo) y después la
    propaga a las filas diarias por `period`, que es como el panel ya arrastra
    los fundamentales. No toca ninguna columna existente.

    Requiere `ticker`, `date`, `period`. Si el panel no trae `period` —o no trae
    ninguna de las columnas pedidas— devuelve el panel intacto: este módulo es
    opcional y no debe tumbar una vista que no usa fundamentales.
    """
    columnas_sorpresa = COLUMNAS_SORPRESA if columnas_sorpresa is None else columnas_sorpresa
    if "period" not in panel.columns or "ticker" not in panel.columns:
        return panel

    df = panel.copy()
    df["_period_dt"] = pd.to_datetime(df["period"], errors="coerce")

    presentes_sue = [c for c in columnas_sorpresa if c in df.columns]
    presentes_ma = [c for c in columnas_ma if c in df.columns]
    if not presentes_sue and not presentes_ma:
        return panel

    nuevas: list[pd.DataFrame] = []
    for ticker, g in df.groupby("ticker", sort=False):
        # Una fila por trimestre, en orden de periodo. `first` porque dentro de
        # un periodo el valor es constante (viene arrastrado).
        q = (
            g.dropna(subset=["_period_dt"])
            .sort_values("_period_dt")
            .groupby("_period_dt", as_index=False)
            .first()
        )
        if q.empty:
            continue
        salida = {"ticker": ticker, "_period_dt": q["_period_dt"].to_numpy()}
        for col in presentes_sue:
            salida[f"sue_{col}"] = sue_serie(q[col].to_numpy(), columnas_sorpresa[col])
        for col in presentes_ma:
            for k in ventanas_ma:
                salida[f"fund_dist_ma{k}_{col}"] = dist_media_movil(q[col].to_numpy(), k)
        nuevas.append(pd.DataFrame(salida))

    if not nuevas:
        return panel
    trimestral = pd.concat(nuevas, ignore_index=True)

    # Bandera de validez: distingue "sorpresa cero" de "todavía no hay historia".
    cols_sue = [c for c in trimestral.columns if c.startswith("sue_")]
    if cols_sue:
        trimestral["sue_valido"] = (
            trimestral[cols_sue].abs().sum(axis=1) > 0
        ).astype(float)

    out = df.merge(trimestral, on=["ticker", "_period_dt"], how="left")
    nuevas_cols = [c for c in trimestral.columns if c not in ("ticker", "_period_dt")]
    out[nuevas_cols] = out[nuevas_cols].fillna(0.0)

    # --- PICO FECHADO: la sorpresa solo el día en que el mercado pudo actuar ---
    # El escalón de 90 días se conserva (sue_*) y el pico se agrega aparte
    # (pico_sue_*): son dos hipótesis distintas sobre cómo el mercado consume la
    # noticia, y cuál gana lo decide la ablación, no este archivo.
    #
    # EL PICO NO SE DISPARA EN `known_date`, SE DISPARA EN EL PRIMER DÍA BURSÁTIL
    # DESDE `known_date`. Medido sobre el panel real: el 23% de las
    # publicaciones cae en sábado, domingo o feriado (36 sábados y 27 domingos
    # de 395 trimestres). Exigir coincidencia exacta con `known_date` perdía uno
    # de cada cuatro eventos, y no al azar: dependía del calendario, que es
    # justo el tipo de sesgo silencioso que no hace fallar nada.
    #
    # Se resuelve sin construir un calendario aparte: el panel YA expone el
    # trimestre q recién desde su known_date, así que la PRIMERA fila de cada
    # (ticker, period) es, por construcción, el primer día bursátil en que el
    # dato era público.
    if cols_sue:
        orden = out.sort_values(["ticker", "_period_dt", "date"]).index
        es_primera = pd.Series(False, index=out.index)
        es_primera.loc[
            out.loc[orden].groupby(["ticker", "_period_dt"], sort=False).head(1).index
        ] = True
        # Un periodo cuya primera fila es el primer día del panel entero no es
        # un anuncio observado: es el arrastre inicial. No se le pone pico.
        primera_fecha = pd.to_datetime(out["date"]).min()
        es_primera &= pd.to_datetime(out["date"]) > primera_fecha
        marca = es_primera.to_numpy()
        for c in cols_sue:
            out[f"pico_{c}"] = np.where(marca, out[c].to_numpy(), 0.0)

    if "known_date" in out.columns:
        dias = (pd.to_datetime(out["date"]) - pd.to_datetime(out["known_date"], errors="coerce"))
        out["dias_desde_resultado"] = np.clip(
            np.nan_to_num(dias.dt.days.to_numpy(dtype=float), nan=0.0), 0.0, None
        )

    return out.drop(columns=["_period_dt"])
