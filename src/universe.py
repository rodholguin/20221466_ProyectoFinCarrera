"""Carga del universo y utilidades compartidas.

Define el esquema canónico que TODOS los pipelines deben respetar para que
R6 (dataset unificado) sea un simple join:

  - mercado / sentimiento : clave (ticker, fecha)        -> diario
  - fundamentales         : clave (ticker, periodo)      -> trimestral
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml


@dataclasses.dataclass(frozen=True)
class Asset:
    sector: str
    name: str
    bvl: str
    yahoo: str | None
    smv: str | None
    smv_rpj: str | None = None  # código RPJ del registro SMV (clave de filtro exacta)
    bvl_company_code: str | None = None  # companyCode NUMÉRICO de la BVL (dataondemand
                                         # /v1/issuers/{cc}/value → dividendos + acciones
                                         # liberadas nativas BVL). Ver corporate_actions.
    nominal_value: float | None = None   # valor nominal por acción (S/), de la BVL
                                         # (listStock). Usado para derivar acciones en
                                         # circulación = (Capital Emitido - tesorería) /
                                         # nominal. Ver fundamentals_client + docs §3.10.2.
    shares_outstanding_override: int | None = None  # conteo fijo de acciones en
                                         # circulación cuando el SMV no permite derivarlo
                                         # (MINSURI1: capital USD + acción de inversión,
                                         # override = total económico; BUENAVC1: ancla SEC).
    shares_outstanding_schedule: tuple[tuple[str, int], ...] | None = None
                                         # Igual que el override pero POR TRAMOS, para un
                                         # activo cuyo conteo cambió y no se puede derivar
                                         # del capital/nominal: ((fecha_desde, conteo), ...)
                                         # con fecha_desde ISO = primer periodo en que rige
                                         # ese conteo. Tiene PRECEDENCIA sobre el override.
                                         # INRETC1: follow-on exacto en 2022-Q2. Ver
                                         # fundamentals_client.compute_shares_earnings.
    price_currency: str | None = None    # moneda del close de la BVL. None/"PEN" = ya
                                         # está en soles (default). "USD" (INRETC1) =>
                                         # el close se convierte a PEN con el TC BCRP.
    smv_tipo: str | None = None          # "I" (Individual, default) o "C" (Consolidado).
                                         # INRETC1 usa "C" (holding; su individual da pérdida).
    isin: str | None = None
    notes: str | None = None
    xcheck: str | None = None   # ticker de validación cruzada (p.ej. BAP para BCP)


@dataclasses.dataclass(frozen=True)
class Config:
    start: str
    end: str
    assets: list[Asset]
    raw: dataclasses.InitVar[Path]
    sources: dict
    paths: dict

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> "Config":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        assets = [Asset(**cls._normalize_asset(a)) for a in raw["universe"]]
        return cls(
            start=raw["period"]["start"],
            end=raw["period"]["end"],
            assets=assets,
            raw=Path(raw["paths"]["raw"]),
            sources=raw["sources"],
            paths=raw["paths"],
        )

    @staticmethod
    def _normalize_asset(a: dict) -> dict:
        """Ajusta los tipos que YAML no puede expresar tal cual.

        `shares_outstanding_schedule` llega como lista de listas y se pasa a tupla
        de tuplas: `Asset` es un dataclass frozen (hashable) y una lista lo
        rompería si el activo se usa como clave o en un set.
        """
        sched = a.get("shares_outstanding_schedule")
        if sched:
            a = dict(a)
            a["shares_outstanding_schedule"] = tuple(
                (str(desde), int(conteo)) for desde, conteo in sched)
        return a

    def __post_init__(self, raw):  # noqa: D401
        pass


# Esquema canónico de columnas de mercado (diario)
MARKET_SCHEMA = ["ticker", "date", "open", "high", "low", "close", "volume", "source"]

# Esquema canónico de fundamentales (trimestral)
# 'known_date' = fecha en que el EEFF se hizo público (evita look-ahead bias)
FUNDAMENTALS_SCHEMA = [
    "ticker", "period", "known_date",
    # D20 (2026-09-01): ¿`known_date` es la FECHA REAL de presentación (hecho de
    # importancia de la BVL) o el FALLBACK por lag calibrado? La cobertura de
    # fecha real NO es aleatoria — es 0% hasta 2017 y ~96% desde 2019 — así que
    # el train queda 32.5% real y el test 85.2%: la variable significa cosas
    # distintas a un lado y otro del split. Sin esta bandera ese cambio de
    # régimen es invisible, y no se puede correr la ablación que lo mide.
    "known_date_real",
    "account", "value", "currency", "source"
]

# Esquema canónico de sentimiento (diario). v3 (2026-09-01): implementa D15 y
# D17. Ver docs/taxonomia_eventos_R5.txt y decisiones D15/D17.
#
#   sentiment_score / n_articles   se CONSERVAN (R6 los consume hoy). El score
#       se calcula solo sobre artículos RELEVANTES (magnitud > 0).
#
#   n_{alto,resto}_{pos,neu,neg}   D15: CONTEOS por celda tramo x polaridad, con
#       `neutral` INCLUIDO. La magnitud dejó de ser multiplicador y quedó solo
#       como puerta de relevancia: cada evento relevante pesa 1. Son el insumo de
#       las 9 columnas `sent_{pos,neu,neg}_ewma_{5,20,60}` que R6 construye.
#       DOS tramos, no tres: la celda `alto x positivo` tiene ~39 eventos en 14
#       años y 7 activos, sostenida por n=2 filas de la muestra anotada — no
#       aguanta un peso propio. El brazo base (9 columnas) suma los dos tramos;
#       el brazo de ablación de R8 (18 columnas) los usa separados.
#
#   *_nom                          D17: los mismos conteos restringidos al
#       subconjunto cuyo TITULAR nombra a la empresa. Ese estrato tiene 63.8% de
#       relevancia contra 2.1%, y de él sale solo el 17% de la polaridad espuria.
#       Permiten construir el brazo RESTRINGIDO de la ablación sin volver al
#       nivel de artículo. NO reemplazan a los completos: conviven.
#
# REEMPLAZAN a mag_pos/mag_neg y mag_{alto,medio,bajo}_{pos,neg} de v2, que
# nunca tuvieron consumidor río abajo y que D15 dejó sin sentido (eran conteos
# escalados por un factor constante que la normalización causal de D6 borra).
#
# La fuente de verdad por artículo vive aparte y trae `titular_nombra_empresa`.
SENTIMENT_SCHEMA = [
    "ticker", "date", "sentiment_score", "n_articles", "n_relevantes",
    "n_articles_nom", "n_relevantes_nom",
    "n_alto_pos", "n_alto_pos_nom", "n_alto_neu", "n_alto_neu_nom",
    "n_alto_neg", "n_alto_neg_nom",
    "n_resto_pos", "n_resto_pos_nom", "n_resto_neu", "n_resto_neu_nom",
    "n_resto_neg", "n_resto_neg_nom",
    "source",
]

# Columnas de CONTEO del esquema de sentimiento. Se listan aparte porque el
# roll-forward al calendario bursátil debe SUMARLAS, no promediarlas (era un bug
# latente: `_align_sentiment_to_calendar` promediaba todo por n_articles).
SENTIMENT_COUNT_COLS = [c for c in SENTIMENT_SCHEMA if c.startswith("n_")]

# Vidas medias de las EWMAs del canal de sentimiento (D11-iii: base FIJA, pesos
# aprendidos por la red). Se fijan acá para que R6 y la ablación de R8 usen las
# mismas y no se desincronicen.
SENTIMENT_HALFLIVES = (5, 20, 60)


if __name__ == "__main__":
    cfg = Config.load()
    print(f"Periodo: {cfg.start} -> {cfg.end}")
    for a in cfg.assets:
        print(f"  [{a.sector:11}] {a.name:32} BVL={a.bvl:10} Yahoo={a.yahoo}")
