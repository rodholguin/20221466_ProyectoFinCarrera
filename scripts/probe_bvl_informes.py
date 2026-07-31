"""Sondea si la BVL expone ESTADISTICAS / INFORMES BURSATILES con montos
negociados historicos por emisor.

Contexto: el volumen de Yahoo resulto parcial y no reconcilia con la BVL
(ver project_yahoo_volumen_confiabilidad). El endpoint listLastValue solo da el
ULTIMO dia. Se busca una fuente OFICIAL con histórico para acotar la capacidad
de OE1 (montos negociados por empresa) y, si aparece, frecuencia de negociacion.

Sondea rutas candidatas de dataondemand.bvl.com.pe y del sitio publico.
"""
from __future__ import annotations

import json

import requests

_DOD = "https://dataondemand.bvl.com.pe"
_WEB = "https://www.bvl.com.pe"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "Origin": _WEB,
    "Referer": _WEB + "/",
    "Accept": "application/json, text/plain, */*",
}

NEM, CC = "FERREYC1", "73600"

_PISTAS = ("volum", "monto", "amount", "cantidad", "quantity", "operac", "traded",
           "turnover", "negoc", "frecuen", "report", "bolet", "informe", "estadist",
           "file", "url", "pdf", "excel", "download")

CANDIDATOS = [
    # estadisticas / reportes
    ("GET", "/v1/statistics/summary", {}),
    ("GET", "/v1/statistics/traded-amount", {"nemonico": NEM}),
    ("GET", "/v1/statistics/frequency", {"nemonico": NEM}),
    ("GET", "/v1/reports", {}),
    ("GET", "/v1/reports/monthly", {}),
    ("GET", "/v1/reports/daily-bulletin", {}),
    ("GET", "/v1/bulletins", {}),
    ("GET", "/v1/bulletin/daily", {}),
    ("GET", "/v1/publications", {}),
    ("GET", "/v1/documents", {}),
    # negociacion
    ("GET", "/v1/negotiation/summary", {}),
    ("GET", "/v1/negotiations/daily", {"nemonico": NEM}),
    ("GET", "/v1/trading/summary", {}),
    ("GET", "/v1/market-data/summary", {}),
    # emisor
    ("GET", f"/v1/issuers/{CC}/statistics", {}),
    ("GET", f"/v1/issuers/{CC}/traded", {}),
    ("GET", f"/v1/issuers/{CC}/detail", {}),
    ("GET", f"/v1/issuers/{CC}", {}),
    # indices / ranking (suelen traer monto negociado)
    ("GET", "/v1/indexes", {}),
    ("GET", "/v1/stock-quote/ranking", {}),
    ("GET", "/v1/stock-quote/most-traded", {}),
]


def claves(obj, prefijo="", prof=0):
    out = []
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


def main():
    print("Sondeo de estadisticas / informes en dataondemand.bvl.com.pe\n")
    hallazgos = []
    for metodo, ruta, params in CANDIDATOS:
        try:
            r = requests.get(_DOD + ruta, params=params, headers=_HEADERS, timeout=20)
        except Exception as exc:
            print(f"  {ruta:40s} EXC {type(exc).__name__}")
            continue
        if r.status_code != 200:
            print(f"  {ruta:40s} HTTP {r.status_code}")
            continue
        try:
            data = r.json()
        except Exception:
            print(f"  {ruta:40s} 200 no-JSON ({len(r.content)}B)")
            continue
        ks = claves(data)
        pistas = [k for k in ks if any(p in k.lower() for p in _PISTAS)]
        marca = "  <<< INTERESANTE" if pistas else ""
        print(f"  {ruta:40s} 200  {len(ks)} claves{marca}")
        if pistas:
            print(f"      -> {pistas[:14]}")
            hallazgos.append((ruta, pistas, data))
        elif ks:
            print(f"      claves: {ks[:8]}")

    print("\n" + "=" * 72)
    for ruta, pistas, data in hallazgos:
        print(f"\n{ruta}")
        print("  muestra:", json.dumps(data, ensure_ascii=False)[:700])


if __name__ == "__main__":
    main()
