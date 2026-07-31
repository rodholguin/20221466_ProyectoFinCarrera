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
    "ticker", "period", "known_date", "account", "value", "currency", "source"
]

# Esquema canónico de sentimiento (diario)
SENTIMENT_SCHEMA = ["ticker", "date", "sentiment_score", "n_articles", "source"]


if __name__ == "__main__":
    cfg = Config.load()
    print(f"Periodo: {cfg.start} -> {cfg.end}")
    for a in cfg.assets:
        print(f"  [{a.sector:11}] {a.name:32} BVL={a.bvl:10} Yahoo={a.yahoo}")
