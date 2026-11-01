"""Sólo lectura (2026-10-06): ¿se puede sostener la corrección de fecha de la BVL SIN
Bloomberg? Contraste de retornos del cierre crudo del panel (R3 corregido) contra
el cierre de Yahoo (.LM) para los 2 activos con Yahoo en disco."""
from pathlib import Path
import pandas as pd, numpy as np
ROOT = Path(__file__).resolve().parent.parent
for t in ["ALICORC1","CREDITC1"]:
    m = pd.read_parquet(rf"C:\tesis\data\interim\market_{t}.parquet")[["date","close_raw"]]
    m["date"]=pd.to_datetime(m.date); m=m.set_index("date").close_raw
    y = pd.read_parquet(rf"C:\tesis\data\raw\market_{t}_yahoo.parquet")
    y["date"]=pd.to_datetime(y.date).dt.tz_localize(None).dt.normalize(); y=y.set_index("date").close
    for nombre, serie in [("corregido", m), ("sin corregir (etiqueta +1 dia)", m.shift(-1).dropna().rename(None))]:
        if "sin" in nombre:  # reconstruye la etiqueta original: valor del dia i rotulado en i+1
            serie = pd.Series(m.values[:-1], index=m.index[1:])
        j = pd.concat([serie.rename("bvl"), y.rename("yah")], axis=1, join="inner").loc["2013":"2025"]
        r = np.log(j).diff().dropna()
        r = r[(r.abs()<0.2).all(axis=1)]   # fuera días de split (Yahoo en base de hoy)
        print(f"{t}  {nombre:32s} n={len(r):5d}  corr(ret)={r.bvl.corr(r.yah):+.3f}")
