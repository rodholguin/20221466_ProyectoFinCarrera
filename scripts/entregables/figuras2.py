import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
import pandas as pd
from pathlib import Path

ART = Path(__file__).resolve().parents[2] / "data" / "interim" / "artefactos_oe1"
OUT = Path(__file__).parent / "fig"

SURF, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8985", "#e4e3df"
PAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
S1, S2, S3, S4 = PAL[:4]
CAJA_GRIS = "#c9c8c3"

plt.rcParams.update({
    "font.family": "Segoe UI", "font.size": 9.5,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2,
    "axes.facecolor": SURF, "figure.facecolor": SURF,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlecolor": INK, "axes.titlesize": 10.5, "axes.titleweight": "semibold",
})


def grid(ax, axis="y"):
    ax.grid(axis=axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def etiqueta_final(ax, x, y, texto, color_linea, dy=0):
    ax.annotate(texto, (x, y), xytext=(6, dy), textcoords="offset points",
                va="center", ha="left", fontsize=8.5, color=INK)


MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
FMT_MES = matplotlib.ticker.FuncFormatter(lambda v, _: (lambda d: f"{MESES[d.month-1]}-{d:%y}")(mdates.num2date(v)))

cur = np.load(ART / "curvas.npz")

# ------------------------------------------------ evolución de baselines 2013-2025
f = pd.to_datetime(cur["completo__solo caja__fechas"])
series = [
    ("1/N trimestral", "completo__1/N trimestral", S1),
    ("1/N diario", "completo__1/N diario", S2),
    ("Solo caja", "completo__solo caja", S3),
    ("Markowitz tangencia-LW", "completo__markowitz tangencia-LW", S4),
]
fig, ax = plt.subplots(figsize=(7.6, 3.4))
finales = []
for lab, k, c in series:
    v = cur[k] / cur[k][0] * 100
    ax.plot(f, v, color=c, linewidth=1.6, label=lab)
    finales.append((v[-1], lab))
ax.axhline(100, color=MUTED, linewidth=0.8)
# etiquetas al final, separadas para que no choquen
orden = sorted(finales)
ys = [o[0] for o in orden]
for i in range(1, len(ys)):
    ys[i] = max(ys[i], ys[i - 1] + 7)
for (v, lab), y in zip(orden, ys):
    ax.annotate(f"{lab}  {v - 100:+.0f}%", (f[-1], v), xytext=(f[-1] + pd.Timedelta(days=60), y),
                textcoords="data", va="center", fontsize=8.3, color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.6))
ax.set_xlim(f[0], f[-1] + pd.Timedelta(days=1500))
ax.set_ylabel("Valor de la cartera (inicio = 100)")
ax.set_xticks([pd.Timestamp(f"{a}-01-01") for a in range(2014, 2026, 2)])
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
grid(ax)
ax.spines["bottom"].set_bounds(mdates.date2num(f[0]), mdates.date2num(f[-1]))
fig.tight_layout()
fig.savefig(OUT / "g1_evolucion_baselines.png", dpi=220)
plt.close(fig)

# ------------------------------------------------ curva de aprendizaje (D25, 10 semillas x 1M)
z = np.load(ART / "d25_curvas.npz")
fig, ax = plt.subplots(figsize=(7.6, 3.1))
curvas = []
x_ref = np.arange(20_000, 1_000_001, 10_000)
for s in range(10):
    p, r = z[f"s{s}__pasos"], z[f"s{s}__recompensa_paso"]
    suav = pd.Series(r).rolling(25, min_periods=5, center=True).mean().to_numpy()
    ax.plot(p, suav, color="#9ec5f4", linewidth=0.8, alpha=0.9)
    curvas.append(np.interp(x_ref, p, suav))
med = np.median(np.vstack(curvas), axis=0)
ax.plot(x_ref, med, color=S1, linewidth=2.2, label="mediana de 10 semillas")
ax.plot([], [], color="#9ec5f4", linewidth=0.8, label="cada semilla (suavizada)")
ax.axhline(0, color=MUTED, linewidth=0.8)
for xv, txt in [(150_000, "presupuesto\ndel piloto (150k)"), (750_000, "meseta mediana\n(~750k)")]:
    ax.axvline(xv, color=MUTED, linewidth=0.9, linestyle="--")
    ax.text(xv + 12_000, 0.2, txt, fontsize=8, color=INK2, va="top",
            bbox=dict(facecolor=SURF, edgecolor="none", pad=1.5))
ax.set_xlabel("pasos de entrenamiento")
ax.set_ylabel("Recompensa por paso")
ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v/1e6:.1f}M" if v >= 1e6 else f"{v/1e3:.0f}k"))
ax.legend(frameon=False, fontsize=8, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 1.0))
grid(ax)
fig.tight_layout()
fig.savefig(OUT / "g2_curva_aprendizaje.png", dpi=220)
plt.close(fig)

# ------------------------------------------------ patrimonio en validación, pliegue 0
fv = pd.to_datetime(cur["agente_delta_s0__fechas"])
fig, ax = plt.subplots(figsize=(7.6, 3.1))
for s in range(3):
    e = cur[f"agente_delta_s{s}__equity"]
    ax.plot(fv, e / e[0] * 100, color=S1, linewidth=1.4, alpha=[1, .55, .55][s],
            label="Agente PPO (3 semillas)" if s == 0 else None)
for lab, k, c in [("1/N diario", "val_f0__1/N diario", S2), ("Solo caja", "val_f0__solo caja", S3)]:
    e = cur[k]
    ax.plot(pd.to_datetime(cur[k + "__fechas"]), e / e[0] * 100, color=c, linewidth=1.6, label=lab)
ax.axhline(100, color=MUTED, linewidth=0.8)
ax.set_ylabel("Valor de la cartera (inicio = 100)")
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
ax.xaxis.set_major_formatter(FMT_MES)
ax.legend(frameon=False, fontsize=8, ncol=3, loc="lower left")
grid(ax)
fig.tight_layout()
fig.savefig(OUT / "g3_patrimonio_val.png", dpi=220)
plt.close(fig)

# ------------------------------------------------ composición de la cartera del agente
w = cur["agente_delta_s0__pesos"] * 100  # 7 activos + caja (última)
nombres = ["Alicorp", "Pacasmayo", "BCP", "Ferreycorp", "InRetail", "Luz del Sur", "Minsur"]
orden_cols = [7, 4, 2, 3, 0, 1, 5, 6]  # caja abajo, luego por peso medio
etqs = ["Caja"] + [nombres[i] for i in orden_cols[1:]]
cols = [CAJA_GRIS] + PAL[:7]
fig, ax = plt.subplots(figsize=(7.6, 3.3))
ax.stackplot(fv, [w[:, j] for j in orden_cols], colors=cols, labels=etqs,
             edgecolor=SURF, linewidth=0.6)
ax.set_ylim(0, 100)
ax.set_xlim(fv[0], fv[-1])
ax.set_ylabel("Peso en la cartera (%)")
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
ax.xaxis.set_major_formatter(FMT_MES)
ax.legend(frameon=False, fontsize=8, ncol=1, loc="center left", bbox_to_anchor=(1.0, 0.5),
          reverse=True)
fig.tight_layout()
fig.savefig(OUT / "g4_pesos_agente.png", dpi=220)
plt.close(fig)

# ------------------------------------------------ mapa de calor R8
filas = ["Agente · solo mercado", "Agente · + macro", "Agente · + sentimiento",
         "Agente · + fundamentales", "Agente · todas las señales", "1/N diario", "Solo caja"]
M = np.array([
    [2.6, -7.3, -0.9], [4.4, -7.6, 0.5], [9.7, -11.9, 2.4], [5.2, -6.7, -3.4],
    [2.8, -8.0, -4.1], [11.8, -8.7, -7.5], [1.9, 0.3, 5.4],
])
cmap = LinearSegmentedColormap.from_list("div", ["#c43b3b", "#e98a88", "#f0efec", "#86b6ef", "#1c5cab"])
fig, ax = plt.subplots(figsize=(7.6, 3.5))
im = ax.imshow(M, cmap=cmap, vmin=-12, vmax=12, aspect="auto")
for i in range(M.shape[0]):
    for j in range(M.shape[1]):
        v = M[i, j]
        ax.text(j, i, f"{v:+.1f}%", ha="center", va="center", fontsize=9,
                color="white" if abs(v) > 8 else INK)
ax.set_xticks(range(3), ["Pliegue 0 · año alcista\nnov-18 a nov-19", "Pliegue 1 · pandemia\nnov-20 a nov-21",
                         "Pliegue 2 · año bajista\nnov-22 a nov-23"], fontsize=8.5)
ax.set_yticks(range(len(filas)), filas)
ax.tick_params(length=0)
ax.xaxis.tick_top()
for s in ax.spines.values():
    s.set_visible(False)
ax.set_xticks(np.arange(-.5, 3, 1), minor=True)
ax.set_yticks(np.arange(-.5, len(filas), 1), minor=True)
ax.grid(which="minor", color=SURF, linewidth=2.5)
ax.tick_params(which="minor", length=0)
ax.axhline(4.5, color=INK2, linewidth=1.2)
cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
cb.set_label("Retorno en validación (%)", color=INK2)
cb.outline.set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "g5_mapa_calor_r8.png", dpi=220)
plt.close(fig)

# ------------------------------------------------ función de recompensa: la frontera
tz = json.load(open(ART / "d4_tamiz_recompensas.json", encoding="utf-8"))
fig, ax = plt.subplots(figsize=(7.6, 3.4))
ax.fill_between([20, 115], 0.5, 1.12, color="#d9f2e6", zorder=0)
ax.text(66, 1.06, "zona buscada: ordena bien Y pesa el riesgo — ningún valor probado cae aquí",
        ha="center", va="top", fontsize=8.3, color="#0c6b4a")
for (k, lab, c) in [("mv", "Media-varianza (valores de λ probados)", S1), ("logret_dd", "Log-retorno − caída (valores de λ probados)", S2)]:
    pts = tz["frontera"][k]
    xs = [min(p["peso_riesgo"], 1.08) * 100 for p in pts]
    ys = [p["rho_sharpe_train"] for p in pts]
    ax.plot(xs, ys, color=c, linewidth=0.8, linestyle=":", alpha=0.7)
    ax.plot(xs, ys, color=c, linewidth=0, marker="o", markersize=6,
            markeredgecolor=SURF, markeredgewidth=1.2, label=lab)
fijas = {"dsr": "Sharpe diferencial\n(la usada)", "ddr": "Semivarianza (DDR)", "logret": "Log-retorno puro", "dsr_rot": "Sharpe dif. + rotación"}
off = {"dsr": (8, 0), "ddr": (8, 0), "logret": (-2, 13), "dsr_rot": (8, 4)}
for k, lab in fijas.items():
    r = tz["resultados"][k]
    x, y = r["T3_peso_riesgo"] * 100, r["rho_sharpe_train"]
    ax.scatter([x], [y], s=46, color=INK if k == "dsr" else MUTED, edgecolor=SURF, linewidth=1.2, zorder=5)
    ax.annotate(lab, (x, y), xytext=off[k], textcoords="offset points", fontsize=8, color=INK, va="center")
ax.axhline(0.5, color=MUTED, linewidth=0.8, linestyle="--")
ax.axvline(20, color=MUTED, linewidth=0.8, linestyle="--")
ax.axhline(0, color=MUTED, linewidth=0.6)
ax.set_xlim(-3, 115)
ax.set_ylim(-0.75, 1.12)
ax.set_xlabel("Peso del riesgo dentro de la recompensa (%)")
ax.set_ylabel("¿Ordena como el Sharpe?\n(correlación de rangos)")
ax.legend(frameon=False, fontsize=8, loc="lower left")
grid(ax)
fig.tight_layout()
fig.savefig(OUT / "g6_frontera_recompensa.png", dpi=220)
plt.close(fig)
print("ok")
