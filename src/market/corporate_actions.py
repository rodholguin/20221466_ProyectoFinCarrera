"""R3 — Capa de ajuste por acciones corporativas (splits y dividendos).

Produce, a partir de close_raw (precio efectivamente negociado), dos series
derivadas en convención de ajuste hacia atrás (CRSP):

  close_split_adj    — ajustado por splits / acciones liberadas (base de un
                        P/E consistente con el EPS).
  close_total_return — ajustado por splits y dividendos reinvertidos (señal
                        de aprendizaje del agente DRL).

Fuente (única, autoritativa BVL) para los 5 activos del universo:
  dataondemand.bvl.com.pe  GET /v1/issuers/{companyCode}/value
                           -> listValue[].listBenefit[]  (nativo BVL, en PEN o
                           US$ según el emisor). Reemplaza a yfinance como fuente
                           de acciones corporativas (yfinance era un espejo de
                           esta misma fuente; validado en CREDITC1: sus 13
                           acciones liberadas BVL reproducen exactamente los
                           "splits" de yfinance). Ver docs/hallazgos_dividendos_
                           acciones_bvl.txt y scripts/probe_bvl_benefits.py.

Cada beneficio (listBenefit) tiene:
  benefitType : "DE" = Dividendo en Efectivo | "AL" = Acciones Liberadas
  benefitValue: DE -> monto por acción (en `coin`); AL -> % de acciones nuevas
                -> ratio de split = 1 + benefitValue/100
  coin        : "S/." (PEN) | "US$" (USD)
  dateCut     : fecha de corte (~ ex-date); es la fecha del ajuste CRSP.

Moneda: el close de mercado de la BVL de estos activos está en PEN. Los
dividendos que la BVL declara en US$ (BUENAVC1 completo; CORAREC1 parcial) se
convierten a PEN con el tipo de cambio del BCRP a la fecha de corte (ver
src/market/fx.py) para que el factor de reinversión sea homogéneo en soles. Las
acciones liberadas (AL) son adimensionales (un ratio), no requieren conversión.
"""
from __future__ import annotations

import pandas as pd

from src.market import fx
from src.universe import Asset

_SPLIT_CANDIDATE_THRESHOLD = 0.40
# Días de tolerancia al cruzar un salto contra las acciones corporativas de la
# BVL. La BVL fecha por `dateCut`, que puede adelantarse unos días al ajuste real
# del precio (mismo motivo que align_splits_to_price).
_VENTANA_CONFIRMACION = 5

_BVL_DOD = "https://dataondemand.bvl.com.pe"
_BVL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/",
    "Accept": "application/json, text/plain, */*",
}


def fetch_actions(asset: Asset) -> dict[str, pd.Series]:
    """Devuelve {"splits": Series[ratio], "dividends": Series[monto PEN]}
    indexadas por fecha de corte (DatetimeIndex normalizado, tz-naive), desde la
    fuente autoritativa de la BVL. Series vacías si el activo no tiene
    bvl_company_code o si la descarga falla.
    """
    if asset.bvl_company_code:
        return _fetch_bvl_actions(asset)

    print(f"[corporate_actions] {asset.bvl}: sin bvl_company_code en config -> "
          f"sin ajuste por acciones corporativas (close_total_return = close_raw).")
    return _empty_actions()


def _empty_actions() -> dict[str, pd.Series]:
    empty = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    return {"splits": empty, "dividends": empty.copy()}


def fetch_bvl_benefits(company_code: str, nemonico: str | None = None) -> list[dict]:
    """Lista de beneficios (dividendos + acciones liberadas) de un emisor desde
    /v1/issuers/{companyCode}/value.

    IMPORTANTE: /value devuelve UNA entrada listValue por cada valor/clase
    inscrita del emisor (p.ej. BUENAVC1 acción común, BUENAVI1 acción de
    inversión y BVN el ADR), y CADA UNA repite la MISMA lista de beneficios. Si
    se da `nemonico`, se toman solo los beneficios de esa clase; de lo contrario
    se aplanan todas (útil solo para conteos de cobertura, NO para montos: sumar
    todas duplicaría cada dividendo por el número de clases)."""
    import requests

    resp = requests.get(f"{_BVL_DOD}/v1/issuers/{company_code}/value",
                        headers=_BVL_HEADERS, timeout=40)
    resp.raise_for_status()
    value = resp.json()
    benefits: list[dict] = []
    for v in (value or []):
        if nemonico is not None and v.get("nemonico") != nemonico:
            continue
        benefits += v.get("listBenefit") or []
    return benefits


def _fetch_bvl_actions(asset: Asset) -> dict[str, pd.Series]:
    """Descarga los beneficios BVL del emisor y los mapea a las series de splits
    (eventos AL) y dividendos en PEN (eventos DE; USD convertido con TC BCRP).
    Varios eventos en una misma fecha se combinan (splits: producto de ratios;
    dividendos: suma de montos)."""
    try:
        benefits = fetch_bvl_benefits(asset.bvl_company_code, nemonico=asset.bvl)
    except Exception as exc:
        print(f"[corporate_actions] {asset.bvl}: fallo al descargar beneficios BVL "
              f"({exc}) -> sin ajuste.")
        return _empty_actions()

    split_by_date: dict[pd.Timestamp, float] = {}
    div_by_date: dict[pd.Timestamp, float] = {}
    n_de = n_al = n_usd = n_skip = 0

    for b in benefits:
        btype = b.get("benefitType")
        cut = b.get("dateCut")
        raw = b.get("benefitValue")
        if not cut or raw in (None, ""):
            n_skip += 1
            continue
        try:
            val = float(str(raw).replace(",", ""))
        except (TypeError, ValueError):
            n_skip += 1
            continue
        date = pd.Timestamp(cut).normalize()

        if btype == "AL":
            ratio = 1.0 + val / 100.0
            split_by_date[date] = split_by_date.get(date, 1.0) * ratio
            n_al += 1
        elif btype == "DE":
            coin = b.get("coin")
            if fx.is_usd(coin):
                rate = fx.rate_asof([date]).iloc[0]
                if pd.isna(rate):
                    print(f"[corporate_actions] {asset.bvl}: dividendo US$ en {date.date()} "
                          f"sin TC BCRP disponible -> omitido.")
                    n_skip += 1
                    continue
                amount = val * float(rate)
                n_usd += 1
            elif fx.is_pen(coin):
                amount = val
            else:
                print(f"[corporate_actions] {asset.bvl}: dividendo en {date.date()} con "
                      f"moneda desconocida '{coin}' -> se asume PEN.")
                amount = val
            div_by_date[date] = div_by_date.get(date, 0.0) + amount
            n_de += 1
        # otros benefitType (si los hubiera) se ignoran: no afectan el precio.

    splits = _series_from_dict(split_by_date)
    dividends = _series_from_dict(div_by_date)
    print(f"[corporate_actions] {asset.bvl}: BVL cc={asset.bvl_company_code} -> "
          f"{n_al} acciones liberadas, {n_de} dividendos ({n_usd} en US$->PEN), "
          f"{n_skip} omitidos.")
    return {"splits": splits, "dividends": dividends}


def _series_from_dict(d: dict[pd.Timestamp, float]) -> pd.Series:
    if not d:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    s = pd.Series(d).sort_index()
    s.index = _to_ns(pd.DatetimeIndex(s.index))
    return s


def _to_ns(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Normaliza la unidad interna a datetime64[ns]. pandas >= 2.2 preserva
    distintas resoluciones (s/us/ns) según el origen del dato, y merge_asof
    exige que ambos lados de la llave coincidan exactamente en unidad."""
    return pd.DatetimeIndex(idx).astype("datetime64[ns]")


def detect_split_candidates(close_raw: pd.Series,
                            threshold: float = _SPLIT_CANDIDATE_THRESHOLD) -> pd.Series:
    """Retornos diarios |ret| > threshold: saltos overnight anómalos.

    Detección PURA, sin interpretar: la lectura (¿acción corporativa o noticia?)
    la hace `clasificar_saltos`, que además cruza contra los eventos ya
    descargados de la BVL.
    """
    ret = close_raw.sort_index().pct_change()
    return ret[ret.abs() > threshold]


def clasificar_saltos(candidatos: pd.Series, splits: pd.Series,
                      dividends: pd.Series,
                      ventana_dias: int = _VENTANA_CONFIRMACION) -> pd.DataFrame:
    """Separa los saltos por SIGNO y los cruza con las acciones corporativas.

    POR QUÉ EL SIGNO IMPORTA. Un split o una acción liberada aumentan el número
    de acciones y por lo tanto HACEN CAER el precio: el salto es NEGATIVO. Lo
    mismo un dividendo grande en su ex-date. Un salto grande y POSITIVO casi
    nunca es una acción corporativa —salvo un contrasplit, raro en la BVL— y
    típicamente es una NOTICIA, sobre todo una compra o fusión.

    Tratarlos por igual producía falsos positivos caros. En la corrida del
    2026-08-22 los dos únicos avisos del universo eran anuncios de M&A reales:
    CPACASC1 +61.1% (Holcim, US$1,500M) y LUSURC1 +41.1% (Sempra -> China
    Yangtze Power, US$3,590M). Ninguno requería ajuste. Ver
    docs/hallazgos_mercado_R3.txt 5.8.

    POR QUÉ SE CRUZA CON LOS EVENTOS. `fetch_actions` ya trajo de la BVL las
    acciones liberadas y los dividendos del emisor; si hay uno a pocos días del
    salto, el salto queda explicado y no hay nada que revisar a mano. La ventana
    existe porque la BVL fecha por `dateCut`, que puede adelantarse unos días al
    ajuste real de precio (mismo motivo que `align_splits_to_price`).

    Devuelve un DataFrame indexado por fecha con `ret`, `evento` y `veredicto`.
    """
    cols = ["ret", "evento", "veredicto"]
    if candidatos.empty:
        return pd.DataFrame(columns=cols)

    tol = pd.Timedelta(days=ventana_dias)
    eventos: list[tuple[pd.Timestamp, str]] = []
    for serie, nombre in ((splits, "acción liberada/split"),
                          (dividends, "dividendo")):
        if serie is not None and not serie.empty:
            eventos += [(pd.Timestamp(d), nombre) for d in serie.index]

    filas = []
    for fecha, ret in candidatos.items():
        fecha = pd.Timestamp(fecha)
        cerca = [n for d, n in eventos if abs(d - fecha) <= tol]
        if cerca:
            filas.append({"ret": ret, "evento": cerca[0],
                          "veredicto": "explicado por acción corporativa"})
        elif ret < 0:
            filas.append({"ret": ret, "evento": "",
                          "veredicto": "REVISAR: caída sin acción corporativa"})
        else:
            filas.append({"ret": ret, "evento": "",
                          "veredicto": "alza: probable noticia, NO ajustar"})
    return pd.DataFrame(filas, index=pd.DatetimeIndex(candidatos.index))[cols]


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


def filter_actions_by_cutoff(actions: dict[str, pd.Series], end: str | None,
                             fallback_dates: pd.Series | pd.DatetimeIndex,
                             ) -> dict[str, pd.Series]:
    """Recorta splits/dividendos posteriores a `end` (ISO 8601): evita que una
    acción corporativa fuera del horizonte de estudio (p.ej. detectada por
    yfinance después del cierre del dataset) se filtre a la serie histórica.

    Debe aplicarse ANTES de usar `actions["splits"]` en cualquier reescalado
    (tanto el ajuste de close en build_adjusted_prices como el reescalado de
    OHLC de Yahoo en market_client._merge_bvl_yahoo) -- de lo contrario un
    split posterior a `end` se cuela como factor constante en todo el
    histórico (caso real: ALICORC1, split 2026-03-23 fuera de horizonte
    aplicado por error al OHLC 2012-2025 antes de este fix)."""
    cutoff = pd.Timestamp(end) if end else pd.Timestamp(pd.Series(fallback_dates).max())
    splits, dividends = actions["splits"], actions["dividends"]
    return {
        "splits": splits[splits.index <= cutoff],
        "dividends": dividends[dividends.index <= cutoff],
    }


def align_splits_to_price(close_raw: pd.Series, splits: pd.Series,
                          window_before: int = 1, window_after: int = 5,
                          min_frac: float = 0.5) -> pd.Series:
    """Alinea cada split/acción liberada a la fecha REAL del ajuste de precio
    (ex-date efectiva) observada en close_raw.

    La BVL fecha los splits por `dateCut` (corte/registro), que puede adelantarse
    1-3 días hábiles al día en que el precio efectivamente cae (ex-date; se
    confirmó también que la ex-date de yfinance para CREDITC1 iba 1-2 días
    DESPUÉS del dateCut de la BVL). Si el factor CRSP hacia atrás cambia en
    `dateCut` cuando el precio todavía no cayó, se inyecta un salto artificial
    (caso real: CORAREC1 dateCut 2012-06-12, AL 1.4001, con la caída de -28.8%
    recién el 2012-06-14 -> sin alinear aparece un +40% ficticio el 06-12).

    Para cada split (fecha d, ratio r>1) se busca, en la ventana de días de
    cotización [d-window_before, d+window_after], el día cuyo retorno overnight
    más se acerca a la caída esperada (1/r - 1). Se exige que la caída sea al
    menos `min_frac` de la esperada para aceptarla; si no hay ninguna caída
    consistente (p.ej. split anterior al inicio de la serie, o no reflejado en
    el precio) se conserva `dateCut`. Splits que caen a la misma fecha alineada
    se combinan (producto de ratios)."""
    if splits.empty:
        return splits
    close = close_raw.sort_index()
    ret = close.pct_change()
    remapped: dict[pd.Timestamp, float] = {}
    for d, r in splits.sort_index().items():
        expected = 1.0 / r - 1.0  # r=1.4001 -> -0.2857
        lo = d - pd.Timedelta(days=window_before)
        hi = d + pd.Timedelta(days=window_after)
        cand = ret[(ret.index >= lo) & (ret.index <= hi)]
        cand = cand[cand <= expected * min_frac]   # caídas suficientemente grandes
        target = (cand - expected).abs().idxmin() if not cand.empty else d
        target = pd.Timestamp(target).normalize()
        remapped[target] = remapped.get(target, 1.0) * r
    out = pd.Series(remapped).sort_index()
    out.index = _to_ns(pd.DatetimeIndex(out.index))
    return out


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
    actions = filter_actions_by_cutoff(actions, end, close_raw.index)
    # Alinear los splits al día real de la caída de precio (ex-date efectiva)
    # antes de ajustar: la BVL los fecha por dateCut, que puede adelantarse unos
    # días al ajuste real y, si no se corrige, inyecta un salto artificial.
    splits = align_splits_to_price(close_raw, actions["splits"])
    dividends = actions["dividends"]

    candidates = detect_split_candidates(close_raw)
    # El aviso se emite por SALTO y con su veredicto, no en bloque: antes solo
    # aparecía si la serie no tenía NINGÚN split (`splits.empty`), así que un
    # emisor con splits se quedaba sin revisar sus saltos anómalos, y a la vez
    # las alzas por noticia se reportaban como si hubiera un dato que corregir.
    saltos = clasificar_saltos(candidates, splits, dividends)
    for fecha, r in saltos.iterrows():
        detalle = f" [{r['evento']}]" if r["evento"] else ""
        print(f"[corporate_actions] {asset.bvl}: salto overnight "
              f"{r['ret']:+.1%} el {fecha:%Y-%m-%d} -> {r['veredicto']}{detalle}")
    revisar = int((saltos["veredicto"].str.startswith("REVISAR")).sum()) if len(saltos) else 0
    if revisar:
        print(f"[corporate_actions] {asset.bvl}: {revisar} salto(s) requieren "
              f"revisión manual contra avisos BVL/SMV.")

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
