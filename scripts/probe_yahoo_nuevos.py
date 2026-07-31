"""Prueba si existen tickers Yahoo (.LM = Bolsa de Valores de Lima) para los 5
activos NUEVOS del universo, que hoy tienen `yahoo: null` en config.yaml.

Motivo: la BVL (share-values) NO entrega volumen negociado (volume=NaN, ver
market_client.fetch_bvl). Yahoo es la unica fuente potencial de volumen, y sin
volumen el tope de capacidad de OE1 queda como supuesto declarado en vez de
acotado con datos.

Para cada candidato reporta: si devuelve filas, rango de fechas, moneda, cuantas
filas traen volumen > 0 y el volumen mediano en soles (mediana de close*volume).
"""
from __future__ import annotations

import yfinance as yf

# Candidatos: nemonico BVL -> tickers Yahoo plausibles.
# .LM es el sufijo de la Bolsa de Valores de Lima en Yahoo.
CANDIDATOS = {
    "MINSURI1": ["MINSURI1.LM", "MINSURI1", "MINSUR.LM"],
    "INRETC1":  ["INRETC1.LM", "INRETC1", "INRETC1.PE"],
    "CPACASC1": ["CPACASC1.LM", "CPACASC1", "CPAC"],   # CPAC = ADR NYSE de Pacasmayo
    "FERREYC1": ["FERREYC1.LM", "FERREYC1"],
    "LUSURC1":  ["LUSURC1.LM", "LUSURC1"],
    # Controles: los 2 que YA funcionan hoy en config.yaml.
    "ALICORC1": ["ALICORC1.LM"],
    "CREDITC1": ["CREDITC1.LM"],
}

START, END = "2012-01-01", "2025-12-31"


def probe(tk: str) -> None:
    try:
        raw = yf.Ticker(tk).history(start=START, end=END, auto_adjust=False)
    except Exception as exc:
        print(f"    {tk:16s} ERROR: {type(exc).__name__}: {exc}")
        return

    if raw is None or raw.empty:
        print(f"    {tk:16s} sin datos")
        return

    n = len(raw)
    d0, d1 = raw.index.min().date(), raw.index.max().date()
    vol = raw["Volume"] if "Volume" in raw.columns else None
    n_vol = int((vol > 0).sum()) if vol is not None else 0
    pct_vol = 100.0 * n_vol / n if n else 0.0

    moneda = "?"
    try:
        moneda = (yf.Ticker(tk).fast_info.get("currency") or "?")
    except Exception:
        pass

    if n_vol:
        traded = (raw["Close"] * raw["Volume"])
        med = float(traded[raw["Volume"] > 0].median())
        med_txt = f"  monto mediano/dia={med:,.0f} {moneda}"
    else:
        med_txt = "  (volumen todo 0/NaN)"

    print(f"    {tk:16s} n={n:5d}  {d0}..{d1}  moneda={moneda:4s}"
          f"  dias con volumen={n_vol:5d} ({pct_vol:5.1f}%){med_txt}")


def main() -> None:
    print(f"Sondeo Yahoo {START}..{END}\n")
    for bvl, tickers in CANDIDATOS.items():
        print(f"  {bvl}")
        for tk in tickers:
            probe(tk)
        print()


if __name__ == "__main__":
    main()
