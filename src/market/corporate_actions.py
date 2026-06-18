"""R3 — Capa de ajuste por acciones corporativas (splits y dividendos).

Produce, a partir de close_raw (precio efectivamente negociado), dos series
derivadas en convención de ajuste hacia atrás (CRSP):

  close_split_adj    — ajustado por splits / acciones liberadas (base de un
                        P/E consistente con el EPS).
  close_total_return — ajustado por splits y dividendos reinvertidos (señal
                        de aprendizaje del agente DRL).

Fuentes por ticker (cobertura heterogénea, ver indicaciones del asesor):
  CREDITC1, ALICORC1 — yfinance .splits / .dividends del ticker .LM.
                       Validado: para CREDITC1, el producto acumulado de los
                       ratios de split (2013-2023) reproduce casi exactamente
                       (4.183 vs 4.18 empírico) el desfase de escala observado
                       entre el close crudo de la BVL y el close de Yahoo en el
                       mismo período -> confirma que los ratios son correctos.
  BUENAVC1           — BVN (Yahoo) es el ADR NYSE en USD; sus splits/dividendos
                       NO corresponden a la acción en PEN. Sin una fuente
                       automatizada de hechos de importancia BVL/SMV en PEN
                       confirmada, se deja sin ajustar (is_split_adjusted=False,
                       is_div_adjusted=False). Los 2 splits de BVN en yfinance
                       (2003, 2008) son anteriores al horizonte efectivo y no se
                       usan en ningún caso.
  SAGAC1, CORAREC1   — sin cobertura Yahoo. detect_split_candidates() señala
                       saltos overnight (|ret_1d| > 0.40) para revisión manual
                       contra avisos de la BVL/SMV; no hay confirmación
                       automatizada, así que por defecto quedan sin ajustar.
"""
from __future__ import annotations

import pandas as pd

from src.universe import Asset

_SPLIT_CANDIDATE_THRESHOLD = 0.40

# Tickers para los que yfinance .splits/.dividends SÍ corresponde a la misma
# acción en PEN que cotiza en la BVL (mismo instrumento, no un ADR).
_YAHOO_ACTIONS_TICKERS = {"CREDITC1", "ALICORC1"}


def fetch_actions(asset: Asset) -> dict[str, pd.Series]:
    """Devuelve {"splits": Series[ratio], "dividends": Series[monto]} indexadas
    por fecha (DatetimeIndex normalizado, tz-naive), según la fuente que
    corresponde al ticker. Series vacías si no hay fuente confirmada.
    """
    if asset.bvl in _YAHOO_ACTIONS_TICKERS:
        return _fetch_yahoo_actions(asset.yahoo)

    if asset.bvl == "BUENAVC1":
        print(f"[corporate_actions] {asset.bvl}: BVN es un ADR USD; sus splits/"
              f"dividendos no se usan sin confirmar contra hechos de importancia "
              f"BVL/SMV en PEN. Sin ajuste (close_total_return = close_split_adj "
              f"= close_raw).")
        return _empty_actions()

    print(f"[corporate_actions] {asset.bvl}: sin fuente automatizada de splits/"
          f"dividendos (sin cobertura Yahoo). Ver detect_split_candidates() para "
          f"candidatos a revisar manualmente contra avisos BVL/SMV.")
    return _empty_actions()


def _empty_actions() -> dict[str, pd.Series]:
    empty = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    return {"splits": empty, "dividends": empty.copy()}


def _fetch_yahoo_actions(yahoo_ticker: str) -> dict[str, pd.Series]:
    import yfinance as yf

    tk = yf.Ticker(yahoo_ticker)

    splits = tk.splits
    splits = pd.Series(splits.to_numpy(dtype=float), index=_normalize_index(splits.index))

    div_raw = tk.dividends
    if isinstance(div_raw, pd.DataFrame):
        div_raw = div_raw.iloc[:, 0]   # columna "Dividends"; "currency" se asume PEN
    dividends = pd.Series(div_raw.to_numpy(dtype=float), index=_normalize_index(div_raw.index))

    return {"splits": splits, "dividends": dividends}


def _normalize_index(idx: pd.Index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(idx)
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    return _to_ns(idx.normalize())


def _to_ns(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Normaliza la unidad interna a datetime64[ns]. pandas >= 2.2 preserva
    distintas resoluciones (s/us/ns) según el origen del dato, y merge_asof
    exige que ambos lados de la llave coincidan exactamente en unidad."""
    return pd.DatetimeIndex(idx).astype("datetime64[ns]")


def detect_split_candidates(close_raw: pd.Series,
                            threshold: float = _SPLIT_CANDIDATE_THRESHOLD) -> pd.Series:
    """Retornos diarios |ret| > threshold: candidatos a split/acción liberada
    NO confirmada. Uso: revisión manual contra avisos BVL/SMV."""
    ret = close_raw.sort_index().pct_change()
    return ret[ret.abs() > threshold]


def _backward_cumulative_factor(dates: pd.DatetimeIndex, events: pd.Series) -> pd.Series:
    """Factor de ajuste hacia atrás (convención CRSP).

    Para cada fecha d en `dates`, devuelve el producto de los ratios de los
    eventos (en `events`, indexados por fecha) cuya fecha es ESTRICTAMENTE
    posterior a d. El propio día del evento ya queda en la base "nueva"
    (post-evento) y no se divide/multiplica por su propio ratio.
    """
    dates = _to_ns(pd.DatetimeIndex(dates))
    if events.empty:
        return pd.Series(1.0, index=dates)

    ev = events.sort_index()
    ev.index = _to_ns(pd.DatetimeIndex(ev.index))
    cum_incl = pd.Series(ev.to_numpy()[::-1], index=ev.index[::-1]).cumprod()[::-1]
    cum_excl = cum_incl.shift(-1).fillna(1.0)

    price_df = pd.DataFrame({"date": dates}).sort_values("date")
    ev_df = cum_excl.rename("factor").rename_axis("date").reset_index().sort_values("date")
    merged = pd.merge_asof(price_df, ev_df, on="date", direction="backward")
    merged["factor"] = merged["factor"].fillna(cum_incl.iloc[0])

    return pd.Series(merged["factor"].to_numpy(), index=merged["date"]).reindex(dates)


def split_factor(dates: pd.DatetimeIndex, splits: pd.Series) -> pd.Series:
    """Factor acumulado de splits (>= 1) vigente en cada fecha de `dates`,
    para reescalar valores que ya vienen en la base de acciones "actual"
    (p.ej. el open/high/low de Yahoo) de vuelta a la base "como cotizó ese
    día": valor_como_cotizó = valor_base_actual * split_factor(fecha)."""
    return _backward_cumulative_factor(dates, splits)


def apply_split_adjustment(close_raw: pd.Series, splits: pd.Series) -> pd.Series:
    """Ajusta close_raw (indexado por fecha) por splits, convención CRSP: cada
    precio histórico se divide por el producto acumulado de los ratios de los
    splits posteriores a esa fecha, dejándolo en la base de acciones actual."""
    factor = _backward_cumulative_factor(close_raw.index, splits)
    return close_raw / factor.reindex(close_raw.index).to_numpy()


def apply_total_return(close_raw: pd.Series, splits: pd.Series,
                       dividends: pd.Series) -> pd.Series:
    """Ajusta close_raw por splits y reinversión de dividendos. En cada
    ex-date, el factor de reinversión es 1 + dividendo_ajustado/precio_ajustado;
    estos factores se acumulan hacia atrás igual que los splits, sobre la base
    ya ajustada por splits (close_split_adj)."""
    split_adj = apply_split_adjustment(close_raw, splits)
    if dividends.empty:
        return split_adj

    dividends = pd.Series(dividends.to_numpy(), index=_to_ns(pd.DatetimeIndex(dividends.index)))

    # Los dividendos están en la base de acciones vigente en su propia fecha;
    # se expresan en la base de acciones actual con el mismo factor de split.
    split_factor_at_div = _backward_cumulative_factor(dividends.index, splits)
    div_split_adj = dividends / split_factor_at_div

    price_df = pd.DataFrame({
        "date": _to_ns(pd.DatetimeIndex(split_adj.index)), "price": split_adj.to_numpy(),
    }).sort_values("date")
    div_df = pd.DataFrame({"date": dividends.index}).sort_values("date")
    price_at_ex = pd.merge_asof(div_df, price_df, on="date", direction="backward")
    price_at_ex = pd.Series(price_at_ex["price"].to_numpy(), index=price_at_ex["date"])

    yield_ratio = 1.0 + (div_split_adj.reindex(price_at_ex.index) / price_at_ex)
    yield_ratio = yield_ratio.dropna()
    if yield_ratio.empty:
        return split_adj

    tr_factor = _backward_cumulative_factor(close_raw.index, yield_ratio)
    return split_adj * tr_factor.reindex(close_raw.index).to_numpy()


def build_adjusted_prices(asset: Asset, close_raw: pd.Series,
                          end: str | None = None,
                          actions: dict[str, pd.Series] | None = None,
                          ) -> tuple[pd.Series, pd.Series, dict]:
    """Orquesta fetch_actions + apply_split_adjustment + apply_total_return
    para un activo. `close_raw` debe estar indexado por fecha.

    `end`: si se da (ISO 8601), recorta splits/dividendos posteriores a esa
    fecha -- evita aplicar acciones corporativas futuras (fuera del horizonte
    de estudio) a la serie histórica.
    `actions`: si ya se descargaron (p.ej. en market_client.fetch_market para
    reescalar el OHLC de Yahoo), se reutilizan en lugar de volver a llamar a
    fetch_actions (evita una segunda llamada de red a yfinance).

    Devuelve (close_split_adj, close_total_return, flags) donde flags =
    {"is_split_adjusted": bool, "is_div_adjusted": bool}.
    """
    if actions is None:
        actions = fetch_actions(asset)
    splits, dividends = actions["splits"], actions["dividends"]

    cutoff = pd.Timestamp(end) if end else close_raw.index.max()
    splits = splits[splits.index <= cutoff]
    dividends = dividends[dividends.index <= cutoff]

    candidates = detect_split_candidates(close_raw)
    if not candidates.empty and splits.empty:
        fechas = ", ".join(d.strftime("%Y-%m-%d") for d in candidates.index)
        print(f"[corporate_actions] {asset.bvl}: {len(candidates)} salto(s) overnight "
              f">{_SPLIT_CANDIDATE_THRESHOLD:.0%} sin split confirmado -> revisar "
              f"avisos BVL/SMV manualmente. Fechas: {fechas}")

    is_split_adjusted = not splits.empty
    is_div_adjusted = not dividends.empty

    if is_split_adjusted:
        close_split_adj = apply_split_adjustment(close_raw, splits)
    else:
        close_split_adj = close_raw.copy()

    if is_split_adjusted or is_div_adjusted:
        close_total_return = apply_total_return(close_raw, splits, dividends)
    else:
        close_total_return = close_split_adj.copy()

    flags = {"is_split_adjusted": is_split_adjusted, "is_div_adjusted": is_div_adjusted}
    return close_split_adj, close_total_return, flags
