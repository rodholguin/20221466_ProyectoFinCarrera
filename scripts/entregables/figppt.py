# Regenera las figuras con tipografia mas grande, para proyectarlas.
from pathlib import Path
import re

base = Path(__file__).parent
(base / "figppt").mkdir(exist_ok=True)

# textos que con tipografia grande ya no entran
CORTES = [
    ('"Máxima caída (drawdown)"', '"Máxima caída"'),
    ('"Pliegue 0 · año alcista\\nnov-18 a nov-19", "Pliegue 1 · pandemia\\nnov-20 a nov-21",',
     '"Pliegue 0\\naño alcista", "Pliegue 1\\npandemia",'),
    ('"Pliegue 2 · año bajista\\nnov-22 a nov-23"', '"Pliegue 2\\naño bajista"'),
    ('"zona buscada: ordena bien Y pesa el riesgo — ningún valor probado cae aquí"',
     '"zona buscada — ningún valor probado cae aquí"'),
    ('"Media-varianza (valores de λ probados)"', '"Media-varianza"'),
    ('"Log-retorno − caída (valores de λ probados)"', '"Log-retorno − caída"'),
    ('"Sharpe diferencial\\n(la usada)"', '"Sharpe diferencial"'),
    ('"Sharpe dif. + rotación"', '"Sharpe dif. + rot."'),
    ('"Suma de los tres\\n(lo esperado)", "Todas juntas\\n(lo medido)"',
     '"Suma de los tres\\n(esperado)", "Todas juntas\\n(medido)"'),
    ('"Costo pagado (miles de S/)"', '"Costo (miles de S/)"'),
    ('"Rotación de cartera (veces/año)"', '"Rotación (veces/año)"'),
    ('"Retorno en validación (%)"', '"Retorno val. (%)"'),
    ('"cada semilla (suavizada)"', '"cada semilla"'),
    ('"Agente PPO · todas las señales"', '"Agente · todas"'),
    ('"Agente PPO · solo mercado"', '"Agente · mercado"'),
]

for src in ["figuras.py", "figuras2.py"]:
    code = (base / src).read_text(encoding="utf-8")
    code = code.replace('/ "fig"', '/ "figppt"')
    code = code.replace('"font.size": 9.5', '"font.size": 13')
    code = code.replace('"axes.titlesize": 10.5', '"axes.titlesize": 14')
    for a, b in CORTES:
        code = code.replace(a, b)
    code = re.sub(r"fontsize=(\d+(?:\.\d+)?)", lambda m: f"fontsize={float(m.group(1)) * 1.33:.1f}", code)
    code = re.sub(r"size=(\d+(?:\.\d+)?)\)", lambda m: f"size={float(m.group(1)) * 1.2:.1f})", code)
    exec(compile(code, src, "exec"), {"__file__": str(base / src), "__name__": "__main__"})

print("figuras de slides listas")
