"""Busca cuentas de capital/patrimonio en el BalanceGeneral cacheado."""
import json
from pathlib import Path

data = json.loads(Path("data/raw/smv_cache/obtener_BalanceGeneral_2023Q4_I.json").read_text())
alicorp = [r for r in data if r.get("RPJ") == "B30006"]

print("=== Cuentas del PATRIMONIO — Alicorp Q4-2023 ===")
for r in alicorp:
    c = r.get("Cuenta", "")
    desc = r.get("DescripcionCuenta", "")
    # Cuentas de patrimonio suelen empezar en 1D04xx o contienen palabras clave
    if c.startswith("1D04") or any(k in desc.lower() for k in
       ["capital", "patrimonio", "accion", "acciones", "reserva", "utilidad acumulada"]):
        m1 = r.get("Monto1")
        print(f"  {c:10}  {desc:60}  Monto1={m1:>15,}")

print()
print("=== Todas las cuentas (Alicorp) por grupo de cuenta ===")
grupos = {}
for r in alicorp:
    c = r.get("Cuenta", "")
    prefix = c[:4] if len(c) >= 4 else c
    grupos.setdefault(prefix, []).append(r)
for prefix in sorted(grupos):
    rows = grupos[prefix]
    descs = [r.get("DescripcionCuenta","")[:50] for r in rows[:2]]
    print(f"  {prefix}: {len(rows)} cuentas  — {descs}")
