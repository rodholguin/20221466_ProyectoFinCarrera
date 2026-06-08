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
        assets = [Asset(**a) for a in raw["universe"]]
        return cls(
            start=raw["period"]["start"],
            end=raw["period"]["end"],
            assets=assets,
            raw=Path(raw["paths"]["raw"]),
            sources=raw["sources"],
            paths=raw["paths"],
        )

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
