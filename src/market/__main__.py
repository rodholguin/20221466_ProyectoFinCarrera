"""Punto de entrada del pipeline R3 (mercado + indicadores técnicos).

Ejecutar desde la raíz del proyecto:
    python -m src.market
"""
from pathlib import Path

from src.universe import Config
from src.market.market_client import fetch_market
from src.market.technical_indicators import add_indicators


def main() -> None:
    cfg = Config.load()
    raw_dir = Path(cfg.paths["raw"])
    interim_dir = Path(cfg.paths["interim"])
    interim_dir.mkdir(parents=True, exist_ok=True)

    for a in cfg.assets:
        df = fetch_market(a, cfg.start, cfg.end, raw_dir)
        if df.empty:
            print(f"{a.bvl}: sin datos")
            continue
        df = add_indicators(df)
        out = interim_dir / f"market_{a.bvl}.parquet"
        df.to_parquet(out)
        print(f"{a.bvl}: {len(df)} filas -> {out}")


if __name__ == "__main__":
    main()
