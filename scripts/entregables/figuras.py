import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

OUT = Path(__file__).parent / "fig"
OUT.mkdir(exist_ok=True)

SURF = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8985"
GRID = "#e4e3df"
S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
NEUTRAL = "#b9b8b2"

plt.rcParams.update({
    "font.family": "Segoe UI",
    "font.size": 9.5,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK2,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "axes.facecolor": SURF,
    "figure.facecolor": SURF,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titlecolor": INK,
    "axes.titlesize": 10.5,
    "axes.titleweight": "semibold",
})


def grid(ax, axis="x"):
    ax.grid(axis=axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------- Figura 1
est = [
    ("Solo caja (tasa BCRP)", 40.5, 0.0),
    ("1/N diario SIN costos (referencia)", 32.8, -44.9),
    ("Markowitz tangencia-LW", 31.0, -53.9),
    ("1/N trimestral", 21.0, -45.0),
    ("1/N mensual", 17.2, -45.5),
    ("1/N semanal", 15.1, -45.6),
    ("Markowitz tangencia", 14.8, -55.1),
    ("1/N diario", 8.5, -46.4),
    ("Comprar y mantener", 0.7, -44.2),
    ("Markowitz mínima varianza", -11.7, -50.5),
]
names = [e[0] for e in est]
ret = [e[1] for e in est]
dd = [e[2] for e in est]
y = np.arange(len(est))[::-1]
colors = [S3 if n.startswith("Solo caja") else (NEUTRAL if "SIN costos" in n else S1) for n in names]

fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.6, 3.9), sharey=True,
                             gridspec_kw={"width_ratios": [1.25, 1]})
a1.barh(y, ret, color=colors, height=0.62, edgecolor=SURF, linewidth=2)
a1.axvline(0, color=MUTED, linewidth=0.8)
for yi, v in zip(y, ret):
    a1.text(v + 1 if v >= 0 else 1, yi, f"{v:+.1f}%", va="center",
            ha="left", color=INK, fontsize=8.5)
a1.set_yticks(y, names)
a1.set_xlim(-22, 50)
a1.set_title("Retorno total 2013–2025", loc="left")
grid(a1)

a2.barh(y, dd, color=colors, height=0.62, edgecolor=SURF, linewidth=2)
a2.axvline(0, color=MUTED, linewidth=0.8)
for yi, v in zip(y, dd):
    a2.text(v - 1, yi, f"{v:.1f}%", va="center", ha="right", color=INK, fontsize=8.5)
a2.set_xlim(-72, 4)
a2.set_title("Máxima caída (drawdown)", loc="left")
grid(a2)
a2.tick_params(axis="y", length=0)
fig.tight_layout()
fig.savefig(OUT / "f1_baselines.png", dpi=220)
plt.close(fig)

# ---------------------------------------------------------------- Figura 2
folds = ["Pliegue 0\nnov-2018 a nov-2019\n(año alcista)",
         "Pliegue 1\nnov-2020 a nov-2021\n(pandemia y elecciones)",
         "Pliegue 2\nnov-2022 a nov-2023\n(año bajista)"]
series = [
    ("Agente PPO · solo mercado", [2.6, -7.3, -0.9], S1),
    ("Agente PPO · todas las señales", [2.8, -8.0, -4.1], S2),
    ("1/N diario", [11.8, -8.7, -7.5], S3),
    ("Solo caja", [1.9, 0.3, 5.4], S4),
]
x = np.arange(3)
w = 0.19
fig, ax = plt.subplots(figsize=(7.6, 3.6))
for i, (lab, vals, c) in enumerate(series):
    xs = x + (i - 1.5) * w
    ax.bar(xs, vals, width=w, color=c, label=lab, edgecolor=SURF, linewidth=1.5)
    for xi, v in zip(xs, vals):
        ax.text(xi, v + (0.4 if v >= 0 else -0.4), f"{v:+.1f}", ha="center",
                va="bottom" if v >= 0 else "top", fontsize=7.8, color=INK)
ax.axhline(0, color=MUTED, linewidth=0.8)
ax.set_xticks(x, folds, fontsize=8.5)
ax.set_ylabel("Retorno en validación (%)")
ax.set_ylim(-11.5, 14.5)
grid(ax, "y")
ax.legend(ncol=4, frameon=False, fontsize=8, loc="upper center",
          bbox_to_anchor=(0.5, 1.13), handlelength=1.2, columnspacing=1.2)
fig.tight_layout()
fig.savefig(OUT / "f2_agente_pliegues.png", dpi=220)
plt.close(fig)

# ---------------------------------------------------------------- Figura 3
pasos = ["150k", "300k", "600k", "1M"]
panels = [
    ("Rotación de cartera (veces/año)", [1.91, 2.95, 4.46, 5.18], "{:.2f}"),
    ("Costo pagado (miles de S/)", [31.1, 47.4, 72.1, 82.7], "{:.0f}"),
    ("Retorno en validación (%)", [3.0, 1.0, 1.9, 1.4], "{:+.1f}"),
]
fig, axs = plt.subplots(1, 3, figsize=(7.6, 2.6))
for ax, (tit, vals, fmt) in zip(axs, panels):
    ax.plot(pasos, vals, color=S1, linewidth=2, marker="o", markersize=5,
            markeredgecolor=SURF, markeredgewidth=1.5)
    for xi, v in enumerate(vals):
        valle = 0 < xi < len(vals) - 1 and v < vals[xi - 1] and v < vals[xi + 1]
        ax.annotate(fmt.format(v), (xi, v), textcoords="offset points",
                    xytext=(0, -13 if valle else 7), ha="center", fontsize=8, color=INK)
    ax.set_title(tit, loc="left", fontsize=9.5)
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.35
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xlabel("pasos de entrenamiento", fontsize=8.5)
    grid(ax, "y")
fig.tight_layout()
fig.savefig(OUT / "f3_presupuesto.png", dpi=220)
plt.close(fig)

# ---------------------------------------------------------------- Figura 4
labs = ["+ Macro", "+ Sentimiento", "+ Fundamentales",
        "Suma de los tres\n(lo esperado)", "Todas juntas\n(lo medido)"]
vals = [0.384, 0.452, 0.136, 0.972, 0.113]
cols = [S1, S1, S1, NEUTRAL, S2]
fig, ax = plt.subplots(figsize=(7.6, 2.9))
bars = ax.bar(labs, vals, color=cols, width=0.58, edgecolor=SURF, linewidth=2)
bars[3].set_hatch("///")
bars[3].set_edgecolor("#8a8985")
bars[3].set_facecolor(SURF)
for i, v in enumerate(vals):
    ax.text(i, v + 0.02, f"+{v:.2f}", ha="center", va="bottom", fontsize=8.5, color=INK)
ax.axvline(2.5, color=GRID, linewidth=1, linestyle="--")
ax.set_ylabel("Mejora de Sharpe vs.\nsolo mercado")
ax.set_ylim(0, 1.15)
ax.tick_params(axis="x", labelsize=8.5)
grid(ax, "y")
fig.tight_layout()
fig.savefig(OUT / "f4_canales.png", dpi=220)
plt.close(fig)
print("ok", sorted(p.name for p in OUT.iterdir()))
