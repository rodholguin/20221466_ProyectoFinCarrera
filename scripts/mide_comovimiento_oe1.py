# -*- coding: utf-8 -*-
"""Mide la afirmacion del especialista: '~70% del mercado BVL lo explican factores externos'.

Dos pasos separados a proposito:
  PASO 1  co-movimiento: cuanta varianza comun tienen los 7 (PCA). No necesita nada nuevo.
  PASO 2  cuanto de ese factor comun lo explican los factores EXTERNOS que ya tenemos
          (cobre, tipo de cambio, EMBI) vs los domesticos (tasa de referencia, inflacion).
Se reporta contemporaneo (explicacion) y rezagado un dia (lo unico operable).
"""
import numpy as np
import pandas as pd

df = pd.read_parquet("data/processed/dataset_unificado.parquet")
df["date"] = pd.to_datetime(df["date"])

# ---------- panel ancho de retornos ----------
wide = df.pivot(index="date", columns="ticker", values="ret_1d").sort_index()
stale = df.pivot(index="date", columns="ticker", values="is_stale").sort_index()
notrade = df.pivot(index="date", columns="ticker", values="is_no_trade").sort_index()
tickers = list(wide.columns)
print(f"panel: {wide.shape[0]} fechas x {len(tickers)} activos  {tickers}\n")

# retorno "real": NaN donde el precio venia arrastrado (un 0 arrastrado no es informacion)
traded = (stale.fillna(1) == 0) & (notrade.fillna(1) == 0)
wide_tr = wide.where(traded)


def pca_share(X, etiqueta):
    X = X.dropna()
    if X.shape[0] < 50:
        print(f"  {etiqueta}: muestra insuficiente ({X.shape[0]})")
        return
    Z = (X - X.mean()) / X.std(ddof=1)          # correlacion, no covarianza
    ev = np.linalg.eigvalsh(np.cov(Z.values, rowvar=False))[::-1]
    share = ev / ev.sum()
    print(f"  {etiqueta:38s} n={X.shape[0]:5d}  PC1={share[0]:5.1%}  "
          f"PC1+PC2={share[:2].sum():5.1%}  PC1..3={share[:3].sum():5.1%}")
    return share


print("PASO 1 - CO-MOVIMIENTO (varianza comun de los 7)")
pca_share(wide, "diario, todas las filas")
pca_share(wide_tr, "diario, solo dias con transaccion")
# semanal: corrige el sesgo por negociacion no sincronica, que en mercados ralos
# subestima el factor comun
sem = (1 + wide.fillna(0)).resample("W-FRI").prod() - 1
pca_share(sem, "semanal (viernes)")
men = (1 + wide.fillna(0)).resample("ME").prod() - 1
pca_share(men, "mensual")

# correlacion media por pares, como lectura alternativa
c = wide_tr.corr()
iu = np.triu_indices_from(c.values, k=1)
print(f"\n  correlacion media por pares (dias con transaccion): {np.nanmean(c.values[iu]):.3f}")

# ---------- factores macro ----------
macro_cols = ["macro_cobre", "macro_tc_usdpen", "macro_embi",
              "macro_tasa_ref", "macro_inflacion"]
macro = df.groupby("date")[macro_cols].first().sort_index()
F = pd.DataFrame(index=macro.index)
F["cobre"] = np.log(macro["macro_cobre"]).diff()
F["tc"] = np.log(macro["macro_tc_usdpen"]).diff()
F["embi"] = macro["macro_embi"].diff()
F["tasa_ref"] = macro["macro_tasa_ref"].diff()
F["inflacion"] = macro["macro_inflacion"].diff()

EXTERNOS = ["cobre", "tc", "embi"]      # precio de commodity, moneda, riesgo pais
DOMESTICOS = ["tasa_ref", "inflacion"]


def r2(y, X):
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    if len(d) < 100:
        return np.nan, 0
    Y = d["y"].values
    A = np.column_stack([np.ones(len(d)), d[X.columns].values])
    beta, *_ = np.linalg.lstsq(A, Y, rcond=None)
    resid = Y - A @ beta
    ss_tot = ((Y - Y.mean()) ** 2).sum()
    return 1 - (resid ** 2).sum() / ss_tot, len(d)


print("\n\nPASO 2 - R2 CONTRA FACTORES (contemporaneo = explicacion)")
print(f"  {'activo':10s} {'externos':>10s} {'+domesticos':>12s}")
X_ext = F[EXTERNOS]
X_all = F[EXTERNOS + DOMESTICOS]
for t in tickers:
    y = wide_tr[t]
    a, n = r2(y, X_ext)
    b, _ = r2(y, X_all)
    print(f"  {t:10s} {a:9.1%} {b:11.1%}   (n={n})")

# el factor comun mismo
Z = wide.dropna()
Zs = (Z - Z.mean()) / Z.std(ddof=1)
w, V = np.linalg.eigh(np.cov(Zs.values, rowvar=False))
pc1 = pd.Series(Zs.values @ V[:, -1], index=Z.index)
a, n = r2(pc1, X_ext)
b, _ = r2(pc1, X_all)
print(f"  {'PC1':10s} {a:9.1%} {b:11.1%}   (n={n})   <- el factor comun de la BVL")

print("\nPASO 2b - R2 CON FACTORES REZAGADOS UN DIA (lo unico operable)")
X_ext_l = X_ext.shift(1)
X_all_l = X_all.shift(1)
print(f"  {'activo':10s} {'externos':>10s} {'+domesticos':>12s}")
for t in tickers:
    y = wide_tr[t]
    a, _ = r2(y, X_ext_l)
    b, _ = r2(y, X_all_l)
    print(f"  {t:10s} {a:9.1%} {b:11.1%}")
a, _ = r2(pc1, X_ext_l)
b, _ = r2(pc1, X_all_l)
print(f"  {'PC1':10s} {a:9.1%} {b:11.1%}   <- el factor comun de la BVL")
