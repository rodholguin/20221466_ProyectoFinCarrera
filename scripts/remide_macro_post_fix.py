"""Re-medición (sólo lectura, 2026-10-06) del tamiz macro sobre el panel CORREGIDO
(fix de fecha BVL del 2026-09-12). Reusa las funciones de
scripts/probe_macro_exposicion.py sin modificar el repo.
Agrega: rezago 2 (el relevante para el reloj del entorno: obs e-1 -> retorno e->e+1)
y el aporte incremental de macro_spx / macro_msci_em."""
import sys, importlib.util
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("pm", ROOT/"scripts/probe_macro_exposicion.py")
pm = importlib.util.module_from_spec(spec); spec.loader.exec_module(pm)
I = ROOT/"data/interim"
VIG = ["ALICORC1","CPACASC1","CREDITC1","FERREYC1","INRETC1","LUSURC1","MINSURI1"]
panel = pm.cargar_precios(); panel = panel[panel.ticker.isin(VIG + ["BUENAVC1"])]
m = pd.read_parquet(I/"_macro_bcrp_con_oro_20260901.parquet")
ex = pd.read_parquet(I/"macro_extra_probe.parquet"); ix = pd.read_parquet(I/"macro_indices.parquet")
m = m.join(ex, how="outer").join(ix, how="outer").sort_index()
for c in ["macro_estano","macro_tasa_ref","macro_inflacion"]: m[c]=m[c].ffill()
pm.EN_LOG = set(pm.EN_LOG) | {"macro_spx","macro_msci_em"}
dm = pm.cambios(m)
BASE = ["macro_cobre","macro_oro","macro_estano","macro_wti","macro_tc_usdpen","macro_embi"]
EXT = BASE + ["macro_spx","macro_msci_em"]
NC = dict(pm.NOMBRE_CORTO, macro_spx="S&P 500", macro_msci_em="MSCI EM")
def reg(t, fac, lag, estricto=False):
    g = panel[panel.ticker==t].sort_values("date").copy()
    st = g.is_stale.astype(bool)
    ok = ~st if not estricto else (~st & ~st.shift(1).fillna(True).astype(bool))
    s = g.loc[ok].set_index("date")["ret_1d"].dropna()
    j = pd.concat([s.rename("r"), dm[fac].shift(lag)], axis=1).dropna()
    if len(j) < 200: return None
    X = np.column_stack([np.ones(len(j)), j[fac].to_numpy()])
    b,tt,r2,n = pm.newey_west(X, j["r"].to_numpy()); return b[1:],tt[1:],r2,n
for lag in (0,1,2):
    print("="*90); print(f"MULTIFACTOR 6 BCRP+WTI/ESTAÑO, rezago {lag}  (t Newey-West; |t|>1.96 = 5%)"); print("="*90)
    cnt = {f:0 for f in BASE}
    for t in VIG + ["BUENAVC1"]:
        r = reg(t, BASE, lag)
        if r is None: print(t, "n<200"); continue
        b,tt,r2,n = r
        print(f"{t:9s} n={n:4d} R2={r2:.3f}  " + "  ".join(f"{NC[f][:6]}={tt[i]:+5.2f}" for i,f in enumerate(BASE)))
        if t in VIG:
            for i,f in enumerate(BASE):
                if abs(tt[i])>1.96: cnt[f]+=1
    print("  significativos (de 7 vigentes): " + ", ".join(f"{NC[f]} {cnt[f]}/7" for f in BASE))
for lag in (1,2):
    print("="*90); print(f"INCREMENTAL S&P500 + MSCI EM sobre los 6, rezago {lag}"); print("="*90)
    for t in VIG:
        a = reg(t, BASE, lag); b = reg(t, EXT, lag)
        if a is None or b is None: continue
        print(f"{t:9s} R2 {a[2]:.3f} -> {b[2]:.3f} (dR2 {b[2]-a[2]:+.3f})  t_spx={b[1][6]:+5.2f} t_em={b[1][7]:+5.2f}  t_tc={b[1][4]:+5.2f} t_embi={b[1][5]:+5.2f}")
print("="*90); print("ROBUSTEZ A PRECIO RANCIO: rezago 1 y 2 exigiendo que t-1 haya transado"); print("="*90)
for lag in (1,2):
    for t in VIG:
        r = reg(t, BASE, lag, estricto=True)
        if r is None: print(t,"n<200"); continue
        b,tt,r2,n = r
        print(f"lag{lag} {t:9s} n={n:4d} R2={r2:.3f}  " + "  ".join(f"{NC[f][:6]}={tt[i]:+5.2f}" for i,f in enumerate(BASE)))
