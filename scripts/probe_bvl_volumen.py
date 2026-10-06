"""Busca un endpoint de la BVL que entregue VOLUMEN / MONTO NEGOCIADO.

Motivo: hoy la unica fuente de volumen del pipeline es Yahoo (.LM) y no hay con
que contrastarla. El endpoint primario de la BVL (share-values) devuelve solo
fecha+cierre. La web publica de la BVL SI muestra "Monto Negociado" y "Nro. de
Operaciones" por accion, asi que el dato existe en algun endpoint.

Sondea rutas candidatas de dataondemand.bvl.com.pe y reporta, para cada una,
el status y las CLAVES del JSON, marcando las que huelan a volumen.
"""
from __future__ import annotations

import json

import requests

_DOD = "https://dataondemand.bvl.com.pe"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": "https://www.bvl.com.pe",
    "Referer": "https://www.bvl.com.pe/",
    "Accept": "application/json, text/plain, */*",
}

NEM = "FERREYC1"      # activo liquido del universo nuevo
CC = "73600"          # su companyCode
START, END = "01/07/2025", "31/07/2025"

# Palabras que delatan un campo de volumen/monto negociado.
_PISTAS = ("volum", "monto", "amount", "cantidad", "quantity", "nroop", "operac",
           "traded", "turnover", "negoc", "unidades", "shares")

# (metodo, ruta, params/json)
CANDIDATOS = [
    ("GET",  f"/v1/stock-quote/share-values/{NEM}", {"startDate": START, "endDate": END}),
    ("GET",  "/v1/stock-quote/share", {"nemonico": NEM}),
    ("GET",  "/v1/stock-quote/home", {}),
    ("GET",  "/v1/stock-quote/detail", {"nemonico": NEM}),
    ("GET",  "/v1/stock-quote/summary", {"nemonico": NEM}),
    ("GET",  "/v1/stock-quote/market-summary", {}),
    ("GET",  "/v1/stock-quote/negotiations", {"nemonico": NEM}),
    ("GET",  "/v1/stock-quote/daily", {"nemonico": NEM}),
    ("GET",  "/v1/stock-quote/historic", {"nemonico": NEM}),
    ("GET",  f"/v1/issuers/{CC}/value", {}),
    ("GET",  f"/v1/issuers/{CC}/quotes", {}),
    ("GET",  f"/v1/issuers/{CC}/negotiations", {}),
    ("GET",  "/v1/issuers/stock", {"nemonico": NEM}),
    ("GET",  "/v1/market/summary", {}),
    ("GET",  "/v1/market/daily-report", {}),
    ("GET",  "/v1/statistics/negotiations", {"nemonico": NEM}),
    ("POST", "/v1/stock-quote/share-values", {"nemonico": NEM,
                                              "startDate": START, "endDate": END}),
]


def claves(obj, prefijo: str = "", prof: int = 0) -> list[str]:
    """Aplana las claves de un JSON hasta profundidad 3 (con un item de cada lista)."""
    out: list[str] = []
    if prof > 3:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            ruta = f"{prefijo}.{k}" if prefijo else k
            out.append(ruta)
            out += claves(v, ruta, prof + 1)
    elif isinstance(obj, list) and obj:
        out += claves(obj[0], f"{prefijo}[]", prof + 1)
    return out


def main() -> None:
    print(f"Sondeo de endpoints BVL con volumen  (nemonico={NEM}, cc={CC})\n")
    hallazgos: list[tuple[str, list[str]]] = []

    for metodo, ruta, payload in CANDIDATOS:
        url = _DOD + ruta
        try:
            if metodo == "GET":
                r = requests.get(url, params=payload, headers=_HEADERS, timeout=20)
            else:
                r = requests.post(url, json=payload, headers=_HEADERS, timeout=20)
        except Exception as exc:
            print(f"  {metodo:4s} {ruta:42s} EXC {type(exc).__name__}")
            continue

        if r.status_code != 200:
            print(f"  {metodo:4s} {ruta:42s} HTTP {r.status_code}")
            continue

        try:
            data = r.json()
        except Exception:
            print(f"  {metodo:4s} {ruta:42s} 200 pero no-JSON ({len(r.content)}B)")
            continue

        ks = claves(data)
        pistas = [k for k in ks if any(p in k.lower() for p in _PISTAS)]
        marca = "  <<< POSIBLE VOLUMEN" if pistas else ""
        print(f"  {metodo:4s} {ruta:42s} 200  {len(ks)} claves{marca}")
        if pistas:
            print(f"       -> {pistas[:12]}")
            hallazgos.append((ruta, pistas))
        elif ks:
            print(f"       claves: {ks[:10]}")

    print("\n" + "=" * 70)
    if hallazgos:
        print("ENDPOINTS CON CAMPOS DE VOLUMEN:")
        for ruta, pistas in hallazgos:
            print(f"  {ruta}: {pistas}")
    else:
        print("NINGUN endpoint sondeado expone volumen/monto negociado.")
        print("=> Yahoo seguiria siendo la unica fuente; validarla por consistencia")
        print("   interna (ver probe_yahoo_confiabilidad.py).")


if __name__ == "__main__":
    main()
