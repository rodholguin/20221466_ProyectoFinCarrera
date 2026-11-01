"""Sólo lectura (2026-10-06): re-test de look-ahead/timing del canal de sentimiento sobre el
panel corregido (R5 v2.1 gemma3:12b, 2,237 eventos). Señal neta del día = (pos - neg)
de eventos relevantes (n_alto_pos+n_resto_pos - n_alto_neg-n_resto_neg).
Se mide corr con ret en t-1, t, t+1, t+2 (días con precio propio)."""
from pathlib import Path
import pandas as pd, numpy as np
from scipy import stats
p = pd.read_parquet(Path(__file__).resolve().parent.parent / "data/processed/dataset_unificado.parquet").sort_values(["ticker","date"])
p["pos"] = p.n_alto_pos + p.n_resto_pos; p["neg"] = p.n_alto_neg + p.n_resto_neg
p["neto"] = p.pos - p.neg; p["ev"] = (p.pos + p.neg + p.n_alto_neu + p.n_resto_neu) > 0
rows=[]
for t,g in p.groupby("ticker"):
    g = g.set_index("date")
    r = g.ret_1d.where(g.is_stale == 0)
    for k in (-1,0,1,2):
        rr = r.shift(-k)          # retorno k días después del día de la noticia
        m = g.neto.ne(0) & rr.notna()
        if m.sum() < 30: continue
        c,pv = stats.spearmanr(g.neto[m], rr[m])
        # media de ret condicional al signo
        up = rr[m & (g.neto>0)].mean(); dn = rr[m & (g.neto<0)].mean()
        rows.append((t,k,int(m.sum()),c,pv,up*100,dn*100))
d = pd.DataFrame(rows, columns=["ticker","k","n","spearman","p","ret_pos_%","ret_neg_%"])
pd.set_option("display.width",160); print(d.round(4).to_string(index=False))
# agregado: z-score de ret por activo
p["z"] = p.groupby("ticker").ret_1d.transform(lambda s: (s - s.mean())/s.std())
agg=[]
for k in (-1,0,1,2):
    zz = p.groupby("ticker").z.shift(-k); st = p.groupby("ticker").is_stale.shift(-k)
    m = p.neto.ne(0) & zz.notna() & (st==0)
    c,pv = stats.spearmanr(np.sign(p.neto[m]), zz[m])
    hit = (np.sign(p.neto[m]) == np.sign(zz[m])).mean()
    agg.append((k,int(m.sum()),round(c,4),round(pv,4),round(hit,3)))
print("\nAGREGADO 7 activos (signo neto vs z del retorno en t+k):")
print(pd.DataFrame(agg,columns=["k","n","spearman","p","acierto_signo"]).to_string(index=False))
