"""Volcado de liquidez de Bloomberg -> parquet: spread intradía y monto negociado diario.

Genera data/interim/liquidez_bloomberg.parquet con una fila por (fecha, ticker):

    spread_bps     spread COTIZADO promedio del día, ida y vuelta, en pbs:
                   AVERAGE_BID_ASK_SPREAD / PX_LAST. NaN donde no hay dato.
    monto_pen      monto negociado del día (TURNOVER), en soles. InRetail cotiza
                   en US$ y se convierte con el TC del BCRP.
    volumen        acciones negociadas (PX_VOLUME).
    relleno        True si la fila es un día de relleno de Bloomberg (Fill=P).

POR QUÉ ESTOS CAMPOS Y NO OTROS (medido el 2026-10-29, ver
docs/resultados_entorno_OE1.txt §8.3):
  * AVERAGE_BID_ASK_SPREAD viene en UNIDADES DE PRECIO (dividido por el precio
    da 25-200 pbs, coherente con el tick de S/0.01); no en %.
  * PX_BID/PX_ASK son las puntas al CIERRE, el libro residual tras la subasta:
    dan hasta 3,999 pbs en 2015-2017. No se usan.
  * La hoja BASE usó una sola columna de fechas (Dts=H). Se verificó que NO
    corrió nada: la correlación de retornos PX_LAST vs el cierre BVL tiene su
    pico en desfase 0 en los 7 (0.85-0.99). El script lo vuelve a comprobar y
    se cae si deja de ser así.
  * El grid se bajó con Fill=P: los días sin dato repiten el anterior. Se
    marcan como `relleno` (volumen Y monto idénticos al día previo) y su spread
    y monto quedan en NaN; NO se inventa liquidez.

Encuadre del acta §E: Bloomberg es un volcado ÚNICO a parquet con fecha, nunca
una dependencia viva. El xlsx crudo no va a git (licencia).

Uso:
    python scripts/gen_liquidez_bloomberg.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CRUDO = Path("data/raw/bloomberg/grid_ul1wocu2.xlsx")
SALIDA = Path("data/interim/liquidez_bloomberg.parquet")
PANEL = Path("data/processed/dataset_unificado.parquet")
FX = Path("data/interim/fx_usdpen_bcrp.parquet")
EN_DOLARES = {"INRETC1"}
CORR_MINIMA = 0.80  # retornos PX_LAST vs cierre BVL en desfase 0


def lee_base(ruta: Path) -> pd.DataFrame:
    """Hoja BASE -> columnas MultiIndex (ticker, campo), índice de fechas."""
    import openpyxl

    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    filas = list(wb["BASE"].iter_rows(values_only=True))
    tickers, campos, datos = filas[0], filas[2], filas[3:]
    fechas = pd.to_datetime([r[0] for r in datos], unit="D", origin="1899-12-30")
    columnas, ticker = {}, None
    for j in range(1, len(campos)):
        if tickers[j]:
            ticker = tickers[j].split()[0]
        valores = [r[j] if isinstance(r[j], (int, float)) else np.nan for r in datos]
        columnas[(ticker, campos[j])] = valores
    df = pd.DataFrame(columnas, index=fechas)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


def verifica_alineacion(bb: pd.DataFrame, panel: pd.DataFrame) -> dict[str, float]:
    """Correlación de retornos contra la BVL; se cae si un bloque quedó corrido."""
    cierre = panel.pivot(index="date", columns="ticker", values="close_raw")
    cierre.index = pd.to_datetime(cierre.index)
    out = {}
    for t in sorted(bb.columns.get_level_values(0).unique()):
        j = pd.concat([bb[(t, "PX_LAST")].rename("bb"), cierre[t].rename("bvl")],
                      axis=1, join="inner").dropna()
        rb, rv = np.log(j.bb).diff(), np.log(j.bvl).diff()
        c = {k: rb.corr(rv.shift(k)) for k in (-1, 0, 1)}
        if c[0] < CORR_MINIMA or c[0] < max(c[-1], c[1]):
            raise ValueError(f"{t}: el bloque de Bloomberg parece desalineado con la BVL {c}")
        out[t] = round(float(c[0]), 3)
    return out


def construye(bb: pd.DataFrame, fx: pd.Series) -> pd.DataFrame:
    partes = []
    for t in sorted(bb.columns.get_level_values(0).unique()):
        d = bb[t]
        relleno = (d.PX_VOLUME.diff() == 0) & (d.TURNOVER.diff() == 0)
        spread = (d.AVERAGE_BID_ASK_SPREAD / d.PX_LAST * 1e4).where(~relleno & (d.PX_LAST > 0))
        monto = d.TURNOVER.where(~relleno)
        if t in EN_DOLARES:
            monto = monto * fx.reindex(monto.index, method="ffill")
        partes.append(pd.DataFrame({
            "date": d.index, "ticker": t,
            "spread_bps": spread.to_numpy(),
            "monto_pen": monto.to_numpy(),
            "volumen": d.PX_VOLUME.where(~relleno).to_numpy(),
            "relleno": relleno.to_numpy(),
        }))
    return pd.concat(partes, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crudo", default=str(CRUDO))
    ap.add_argument("--out", default=str(SALIDA))
    args = ap.parse_args()

    bb = lee_base(Path(args.crudo))
    corr = verifica_alineacion(bb, pd.read_parquet(PANEL))
    print("alineación con la BVL (corr. de retornos, desfase 0):", corr)
    fx = pd.read_parquet(FX)["usdpen"]
    fx.index = pd.to_datetime(fx.index)
    df = construye(bb, fx)

    print(f"\n{len(df):,} filas · {df.date.min().date()} a {df.date.max().date()}")
    print("días de relleno descartados:", df.groupby("ticker").relleno.mean().round(3).to_dict())
    print("spread ida y vuelta (pbs), mediana por año:")
    anual = df.assign(anio=df.date.dt.year).pivot_table(index="anio", columns="ticker",
                                                        values="spread_bps", aggfunc="median")
    print(anual.round(0).to_string())
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
