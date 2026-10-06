"""R6 — Integración temporal y dataset unificado.

Une mercado+técnicos (diario) ⨝ sentimiento (diario) ⨝ fundamentales
(trimestral, propagados desde la fecha en que se conocieron) sobre el
calendario de días hábiles de la BVL.

Las 4 "vistas" de señales que pide R8 (solo mercado; +sentimiento;
+fundamentales; completa) NO son datasets separados: son selecciones de
columnas sobre este panel único.

Decisiones de diseño (sesión 2026-06-23, ver memoria del proyecto):
  * El calendario bursátil se construye AQUÍ (unión de fechas con cotización
    de cualquiera de los 5 activos), no en el entorno DRL (OE1). El entorno
    solo consume el índice de fechas ya resuelto.
  * Sentimiento: SIN decaimiento precalculado (lo aprende el agente). Se
    guardan 4 columnas crudas: `sentiment_score_last`, `days_since_news`,
    `has_news`, `n_articles`.
  * Noticias publicadas en días NO bursátiles (fin de semana, feriado BVL)
    se "roll-forward" al siguiente día hábil antes de agregarlas (evita
    look-ahead: una noticia del sábado no pudo afectar el cierre del
    viernes). Si ese día hábil ya tenía noticias propias, se reagregan con
    media ponderada por número de artículos (consistente con
    `daily_aggregation: mean` de R5).
  * `days_since_news` usa un ancla sintética en la primera fila del panel de
    cada activo (equivalente a asumir un evento neutral en día 0), así no
    hay NaN antes de la primera noticia histórica real.
  * Fundamentales: `pd.merge_asof(..., direction="backward")` sobre
    `known_date` — propagación sin look-ahead, ya validada (sin huecos de
    NaN en el horizonte de mercado 2012-2025 porque el primer `known_date`
    de los 5 activos es 2005-05-15).
  * Macro (jul-2026): las 6 series del BCRP entran como columnas GLOBALES
    `macro_*` (mismo valor para todos los activos en una fecha), en NIVELES
    CRUDOS y ya alineadas point-in-time por `src.macro.macro_client`. El
    builder no las descarga: las recibe ya resueltas (`macro=`), igual que
    los dividendos, para no meter red/caché en la construcción del panel.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.market.technical_indicators import add_indicators
from src.sentiment.llm_sentiment import TRAMOS
from src.universe import SENTIMENT_COUNT_COLS, SENTIMENT_HALFLIVES

_PRICE_COLS = ["close", "close_raw", "close_split_adj", "close_total_return"]
_INDICATOR_COLS = ["ret_1d", "ret_1d_raw", "sma_20", "sma_50", "ema_12", "ema_26",
                    "macd", "macd_signal", "rsi_14", "volatility_20"]

# Periodos donde el P/E no es confiable por un ARTEFACTO de acción corporativa
# (además de los NaN por pérdidas, que ya marca eps<=0). Solo señalizamos: la
# política de enmascarado/normalización es de OE1 (ver docs/riesgos R3/R4).
#   SAGAC1: escisión de Inmobiliaria SIC (JGA 28-nov-2019, 2019Q4) redujo las
#   acciones ~37% a media ventana TTM -> eps_ttm mezcla base de acciones pre/post
#   en 2019Q4..2020Q2 (P/E distorsionado ~37%); además el precio quedó estancado
#   en el evento, así que no hay repreciado real que ajustar (fix "fino"
#   descartado con evidencia).
_PE_ARTIFACT_PERIODS: dict[str, set[str]] = {
    "SAGAC1": {"2019-12-31", "2020-03-31", "2020-06-30"},
}

# Prefijo de las columnas macro globales (BCRP). Ver src/macro/macro_client.py.
_MACRO_PREFIX = "macro_"


def _fill_no_trade_days(panel: pd.DataFrame) -> pd.DataFrame:
    """Arrastra el precio en días sin cotización real de un activo.

    BUENAVC1/SAGAC1/CORAREC1 (y en menor medida CREDITC1/ALICORC1) no
    operan todos los días bursátiles -> al reindexar sobre el calendario
    común (`build_trading_calendar`) esas filas llegan sin cotización. Se
    arrastra el último `close_total_return`/`close_raw` conocido ("stale
    price", sin operación real) y se RECALCULAN los indicadores técnicos
    sobre la serie ya completa con `technical_indicators.add_indicators`
    (todos derivan solo de close_total_return/close_raw, ver
    docs/justificacion_cierre_vs_ohlcv.txt) en vez de arrastrar a ciegas
    los valores de los indicadores -- así ret_1d=0 y volatility_20 decae
    correctamente durante el tramo sin operación, y el salto real se
    refleja íntegro el día en que se retoma la negociación.

    `is_no_trade` marca estas filas para que el entorno (OE1) pueda
    modelar el costo de iliquidez en vez de tratarlas como una sesión real
    (ver nota sobre CREDITC1 en config.yaml). No se completa open/high/
    low/volumen: esa decisión ya se descartó explícitamente (el agente
    solo usa close_total_return, ver justificacion_cierre_vs_ohlcv.txt).
    """
    panel = panel.sort_values("date").copy()
    panel["is_no_trade"] = panel["close_total_return"].isna().astype(int)
    panel[_PRICE_COLS] = panel[_PRICE_COLS].ffill()
    for flag in ("is_split_adjusted", "is_div_adjusted"):
        if flag in panel.columns:
            panel[flag] = panel[flag].ffill()
    panel = panel.drop(columns=[c for c in _INDICATOR_COLS if c in panel.columns])
    return add_indicators(panel)


def build_trading_calendar(market: pd.DataFrame) -> pd.DatetimeIndex:
    """Calendario bursátil = unión de fechas con cotización de CUALQUIER
    activo del universo (BVL-wide), no el calendario de un solo activo.

    Cada activo individual puede tener menos filas (iliquidez, suspensión),
    eso se refleja como NaN en sus columnas de mercado al reindexar sobre
    este calendario común, no como un calendario más corto.
    """
    dates = pd.to_datetime(market["date"]).unique()
    return pd.DatetimeIndex(sorted(dates))


def _roll_forward_dates(dates: pd.Series, calendar: pd.DatetimeIndex) -> np.ndarray:
    """Mapea cada fecha al primer día del calendario >= esa fecha.

    Fechas que ya son día hábil quedan sin cambio. Fechas fuera del rango del
    calendario se recortan al extremo más cercano (no debería ocurrir con
    datos dentro del horizonte del proyecto).
    """
    pos = calendar.searchsorted(dates.to_numpy(), side="left")
    pos = np.clip(pos, 0, len(calendar) - 1)
    return calendar.to_numpy()[pos]


def _align_sentiment_to_calendar(sentiment_ticker: pd.DataFrame,
                                  calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """Lleva el sentimiento diario de un activo al calendario bursátil.

    Reasigna noticias de días no bursátiles al siguiente día hábil y reagrega si
    ese día ya tenía noticias propias. `sentiment_ticker` debe venir ya filtrado
    a un solo ticker.

    CÓMO SE REAGREGA, Y POR QUÉ NO ES LO MISMO PARA TODAS LAS COLUMNAS:
      - `sentiment_score` es una MEDIA de polaridad, así que al fusionar dos días
        se combina como media ponderada por `n_articles`.
      - LAS COLUMNAS DE CONTEO SE SUMAN. Un sábado con 2 eventos que cae sobre un
        lunes con 1 tiene 3 eventos, no 1.5.
    FIX DE UN BUG LATENTE (2026-09-01): la versión anterior promediaba TODO por
    n_articles porque solo existían `sentiment_score` y `n_articles`. Al
    implementar D15 eso habría dividido los conteos de eventos entre el número de
    días fusionados, EN SILENCIO y solo en fines de semana y feriados — o sea un
    sesgo sistemático contra los eventos divulgados en día no hábil, que son
    justamente los que el emisor publica fuera de sesión.
    """
    s = sentiment_ticker.copy()
    s["date"] = pd.to_datetime(s["date"])
    s["date"] = _roll_forward_dates(s["date"], calendar)

    conteos = [c for c in SENTIMENT_COUNT_COLS if c in s.columns]
    weighted = s["sentiment_score"] * s["n_articles"]
    agg = (s.assign(_weighted=weighted)
            .groupby("date", as_index=False)
            .agg(_weighted_sum=("_weighted", "sum"),
                 **{c: (c, "sum") for c in conteos}))
    # n_articles ya viene sumado por el bloque de arriba (está en SENTIMENT_COUNT_COLS).
    agg["sentiment_score"] = agg["_weighted_sum"] / agg["n_articles"].replace(0, np.nan)
    agg["sentiment_score"] = agg["sentiment_score"].fillna(0.0)
    return agg.drop(columns="_weighted_sum")


def _sentiment_ewmas(panel: pd.DataFrame) -> pd.DataFrame:
    """Construye las columnas EWMA del canal de sentimiento (D15, D17).

    De los conteos diarios salen TRES familias, todas con las mismas vidas
    medias (SENTIMENT_HALFLIVES = 5, 20, 60):
      sent_{pos,neu,neg}_ewma_{h}        9 columnas — EL CANAL BASE de D15
      sent_{alto,resto}_{pos,neu,neg}_ewma_{h}  18 — brazo de ablación por tramo
      sent_{pos,neu,neg}_nom_ewma_{h}     9 — brazo RESTRINGIDO de D17

    POR QUÉ AQUÍ Y NO EN R5. Recalibrar vidas medias o cambiar de brazo NO exige
    re-pagar el LLM (D11). Los conteos por artículo son la fuente de verdad; esto
    es aritmética sobre ellos.

    CAUSALIDAD. `ewm(...).mean()` en t usa información hasta t inclusive, y D13
    fija ejecución en t+1: el evento de hoy se opera mañana. No hay look-ahead.
    `adjust=False` da la forma recursiva, que es causal por construcción y no
    re-pondera el pasado al llegar cada observación nueva.

    `neutral` ENTRA. Es el cambio central de D15: antes la polaridad neutra no
    aparecía en ninguna columna y se perdía el 23.3% de la masa relevante.
    """
    out = panel.copy()
    for tr in TRAMOS:
        for pol in ("pos", "neu", "neg"):
            for suf in ("", "_nom"):
                col = f"n_{tr}_{pol}{suf}"
                if col not in out.columns:
                    out[col] = 0
                out[col] = out[col].fillna(0.0)
    for pol in ("pos", "neu", "neg"):
        for suf in ("", "_nom"):
            # El brazo base agrega los tramos; el de ablación los deja separados.
            total = sum(out[f"n_{tr}_{pol}{suf}"] for tr in TRAMOS)
            for h in SENTIMENT_HALFLIVES:
                out[f"sent_{pol}{suf}_ewma_{h}"] = (
                    total.ewm(halflife=h, adjust=False).mean())
                for tr in TRAMOS:
                    out[f"sent_{tr}_{pol}{suf}_ewma_{h}"] = (
                        out[f"n_{tr}_{pol}{suf}"].ewm(halflife=h,
                                                      adjust=False).mean())
    return out


def _days_since_news(has_news: np.ndarray) -> np.ndarray:
    """Días hábiles desde la última noticia (0 el día de la noticia).

    Ancla sintética: si la primera fila no tiene noticia, se trata como si
    hubiera un evento neutral en el día 0 (consistente con
    `sentiment_score_last = 0` antes de la primera noticia real) — evita
    NaN sin inventar un segundo valor sentinela arbitrario.
    """
    idx = np.arange(len(has_news), dtype=float)
    last_news_idx = np.where(has_news == 1, idx, np.nan)
    if np.isnan(last_news_idx[0]):
        last_news_idx[0] = 0.0
    last_news_idx = pd.Series(last_news_idx).ffill().to_numpy()
    return (idx - last_news_idx).astype(int)


def _dividend_ttm(dates, ex_dates, amounts, window_days: int = 365) -> np.ndarray:
    """Suma de dividendos por acción con fecha-ex en (t - window_days, t] para
    cada t en `dates`. O(n log n) vía sumas acumuladas + búsqueda binaria."""
    dates = pd.DatetimeIndex(dates)
    ex_dates = pd.DatetimeIndex(ex_dates)
    if len(ex_dates) == 0:
        return np.zeros(len(dates))
    order = np.argsort(ex_dates.values)
    ex = ex_dates.values[order]
    amt = np.asarray(amounts, dtype=float)[order]
    cum = np.concatenate([[0.0], np.cumsum(amt)])
    upper = np.searchsorted(ex, dates.values, side="right")
    lower = np.searchsorted(ex, (dates - pd.Timedelta(days=window_days)).values,
                            side="right")
    return cum[upper] - cum[lower]


def _merge_macro(unified: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    """Une las columnas macro GLOBALES (mismo valor para todos los activos en una
    fecha) al panel, por 'date'.

    `macro` puede venir indexado por fecha (salida directa de
    `macro_client.macro_features`) o con una columna 'date'. Se hace después del
    concat justamente porque son globales: un solo join en vez de uno por activo,
    y queda explícito que no dependen del ticker.
    """
    m = macro.copy()
    if "date" not in m.columns:
        m = m.rename_axis("date").reset_index()
    m["date"] = pd.to_datetime(m["date"])
    cols = [c for c in m.columns if c != "date"]
    if not cols:
        return unified

    choque = [c for c in cols if c in unified.columns]
    if choque:
        raise ValueError(f"columnas macro que ya existen en el panel: {choque}")

    m = m.drop_duplicates("date")
    out = unified.merge(m[["date"] + cols], on="date", how="left")

    faltan = {c: int(out[c].isna().sum()) for c in cols if out[c].isna().any()}
    if faltan:
        print(f"  AVISO macro: NaN tras el join (fechas del panel sin dato macro): {faltan}")
    return out


def build_unified(market: pd.DataFrame, sentiment: pd.DataFrame,
                  fundamentals_ratios: pd.DataFrame,
                  dividends: pd.DataFrame | None = None,
                  trading_calendar: pd.DatetimeIndex | None = None,
                  macro: pd.DataFrame | None = None) -> pd.DataFrame:
    """Construye el panel (ticker, date) x features.

    Parameters
    ----------
    market : con OHLCV + indicadores técnicos (diario), 1+ tickers
    sentiment : sentiment_score/n_articles diario por activo (esquema R5,
                SIN alinear al calendario bursátil todavía)
    fundamentals_ratios : ratios por (ticker, known_date) trimestral, salida
                de `fundamentals_client.compute_ratios`
    trading_calendar : opcional, para pruebas. Por defecto se deriva de
                `market` con `build_trading_calendar`.
    macro : opcional, features macro GLOBALES ya alineados point-in-time
                (`macro_client.macro_features(calendario)`), indexados por fecha
                o con columna 'date'. Si es None el panel sale sin columnas macro.
    """
    if trading_calendar is None:
        trading_calendar = build_trading_calendar(market)

    panels = []
    for ticker, mkt in market.groupby("ticker"):
        idx = pd.MultiIndex.from_product(
            [[ticker], trading_calendar], names=["ticker", "date"])
        base = pd.DataFrame(index=idx).reset_index()

        mkt = mkt.copy()
        mkt["date"] = pd.to_datetime(mkt["date"])
        panel = base.merge(mkt, on=["ticker", "date"], how="left")
        panel = _fill_no_trade_days(panel)

        # Iliquidez: precio sin cambio vs día hábil previo (superset de
        # is_no_trade; captura el float diminuto de CREDITC1 ~41% de días y
        # cualquier tramo estancado). Señal cruda; OE1 modela costo/operabilidad.
        panel["is_stale"] = (
            panel["close_raw"] == panel["close_raw"].shift(1)).astype(int)

        # Sentimiento: alinear al calendario (roll-forward + reagregación),
        # luego forward-fill crudo del último score conocido.
        sen = sentiment[sentiment["ticker"] == ticker]
        if not sen.empty:
            aligned = _align_sentiment_to_calendar(sen, trading_calendar)
            panel = panel.merge(aligned, on="date", how="left")
        if "sentiment_score" not in panel.columns:
            panel["sentiment_score"] = np.nan
        if "n_articles" not in panel.columns:
            panel["n_articles"] = np.nan

        panel["has_news"] = panel["n_articles"].notna().astype(int)
        panel["n_articles"] = panel["n_articles"].fillna(0).astype(int)
        panel["sentiment_score_last"] = panel["sentiment_score"].ffill().fillna(0.0)
        panel["days_since_news"] = _days_since_news(panel["has_news"].to_numpy())
        panel = panel.drop(columns=["sentiment_score"])

        # D15/D17 — las EWMAs del canal. Van DESPUÉS del reindexado al calendario
        # completo: un día sin noticias es un 0 real (el evento decae), no un
        # hueco. Si se calcularan sobre las filas con noticia el decaimiento
        # dependería de cuándo hubo prensa, que es exactamente lo que no se
        # quiere. El orden por fecha ya lo garantiza `base`, construido desde
        # `trading_calendar`.
        panel = _sentiment_ewmas(panel)

        # Fundamentales: forward-fill desde known_date (evita look-ahead)
        fnd = fundamentals_ratios[fundamentals_ratios["ticker"] == ticker].copy()
        if not fnd.empty:
            fnd["known_date"] = pd.to_datetime(fnd["known_date"])
            fnd = fnd.sort_values("known_date")
            panel = pd.merge_asof(
                panel.sort_values("date"), fnd.sort_values("known_date"),
                left_on="date", right_on="known_date", by="ticker",
                direction="backward")

        # P/E diario = capitalización / utilidad TTM = close_raw / eps_ttm.
        # Se usa close_raw (precio efectivamente negociado) y NO close_split_adj:
        # ambos, eps_ttm y close_raw, están en la base de acciones del momento, así
        # el P/E es contemporáneo y robusto a splits (ver docs §3.10.2). Sin P/E
        # cuando la utilidad TTM es <=0 (pérdidas: P/E no informativo).
        if "eps_ttm" in panel.columns:
            eps = panel["eps_ttm"].to_numpy()
            panel["pe"] = np.where(eps > 0, panel["close_raw"].to_numpy() / eps, np.nan)
            # Confiabilidad del P/E: False donde es NaN (pérdidas) o donde un
            # artefacto de acción corporativa lo distorsiona (escisión SAGA).
            # No se enmascara el P/E de CREDITC1 pese al float diminuto: su nivel
            # se neutraliza con la normalización causal por-activo de OE1 (queda
            # como feature de baja información, no engañosa). Ver docs/riesgos R3.
            reliable = pd.Series(np.isfinite(panel["pe"].to_numpy()), index=panel.index)
            bad = _PE_ARTIFACT_PERIODS.get(ticker)
            if bad and "period" in panel.columns:
                reliable &= ~panel["period"].astype(str).isin(bad)
            panel["pe_reliable"] = reliable.astype(int)

        # Dividend yield = dividendos por acción TTM (PEN) / close_raw.
        if dividends is not None:
            dv = dividends[dividends["ticker"] == ticker]
            if not dv.empty:
                div_ttm = _dividend_ttm(panel["date"], dv["date"], dv["dividend"])
                with np.errstate(divide="ignore", invalid="ignore"):
                    panel["dy"] = div_ttm / panel["close_raw"].to_numpy()

        panels.append(panel)

    unified = pd.concat(panels, ignore_index=True)
    if macro is not None and not macro.empty:
        unified = _merge_macro(unified, macro)
    return unified.sort_values(["ticker", "date"]).reset_index(drop=True)


def feature_views(unified: pd.DataFrame) -> dict[str, list[str]]:
    """Devuelve las columnas de cada configuración de señales de R8.

    A las 4 vistas originales se añade `mercado_macro` (ablación del canal macro,
    análoga a `mercado_sentimiento`); las columnas macro también entran en
    `completa`. Las vistas de sentimiento/fundamentales NO llevan macro, para que
    cada canal siga siendo aislable.

    BRAZOS PRE-REGISTRADOS DEL CANAL DE SENTIMIENTO. Se exponen como vistas para
    que R8 los compare sin re-armar nada. Todos comparten las mismas vidas medias
    y se calculan de los mismos conteos, así que la única diferencia entre ellos
    es la que se quiere medir:
      `mercado_sentimiento`      BASE (D15): 9 columnas pos/neu/neg x 5/20/60.
      `..._tramos`               ABLACIÓN (D15): 18 columnas, alto vs resto
                                 separados. Responde si el tramo de magnitud
                                 aporta sobre la polaridad sola.
      `..._restringido`          ABLACIÓN (D17): las 9 del base pero contando
                                 solo artículos cuyo TITULAR nombra a la empresa.
                                 Responde si vale más 88.6% de precisión que
                                 19.6% más de eventos.
    Las 4 columnas crudas (`sentiment_score_last`, `days_since_news`, `has_news`,
    `n_articles`) van en TODOS los brazos: se conservan por D11 y no son lo que
    se está comparando.
    """
    technical = [c for c in unified.columns
                 if c in {"open", "high", "low", "close", "volume", "ret_1d",
                          "sma_20", "sma_50", "ema_12", "ema_26", "macd",
                          "macd_signal", "rsi_14", "volatility_20",
                          "is_no_trade", "is_stale"}]
    crudas = [c for c in
              ["sentiment_score_last", "days_since_news", "has_news", "n_articles"]
              if c in unified.columns]

    def _ewmas(prefijos: tuple[str, ...], suf: str) -> list[str]:
        return [c for p in prefijos for h in SENTIMENT_HALFLIVES
                for c in [f"sent_{p}{suf}_ewma_{h}"] if c in unified.columns]

    pols = ("pos", "neu", "neg")
    base = _ewmas(pols, "")
    tramos = _ewmas(tuple(f"{tr}_{p}" for tr in TRAMOS for p in pols), "")
    restringido = _ewmas(pols, "_nom")

    _fundamental_cols = {
        "roe", "roa", "net_margin", "debt_equity", "debt_ratio",  # derivados SMV
        "pe", "dy", "pe_reliable",                                 # P/E y DY (+ flag)
        # D20: ¿la fecha en que el agente "se entera" del EEFF es la REAL o el
        # fallback por lag? No es ruido aleatorio: 0% real hasta 2017 y ~96%
        # desde 2019, así que train queda 32.5% real y test 85.2%. Entra como
        # FEATURE para que el agente pueda condicionar, y como llave del brazo
        # de ablación que propuso el asesor (fundamentales solo donde la fecha
        # es real), que en R8 es un NaN-eo de las demás columnas donde vale 0.
        "known_date_real",
    }
    fundamental = [c for c in unified.columns if c in _fundamental_cols]
    macro = [c for c in unified.columns if c.startswith(_MACRO_PREFIX)]
    sentiment = crudas + base
    return {
        "solo_mercado":                      technical,
        "mercado_sentimiento":               technical + sentiment,
        "mercado_sentimiento_tramos":        technical + crudas + tramos,
        "mercado_sentimiento_restringido":   technical + crudas + restringido,
        "mercado_fundamentales":             technical + fundamental,
        "mercado_macro":                     technical + macro,
        "completa":                          technical + sentiment + fundamental + macro,
    }


def save(unified: pd.DataFrame, processed_dir: str | Path) -> Path:
    out = Path(processed_dir) / "dataset_unificado.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    unified.to_parquet(out)
    return out
