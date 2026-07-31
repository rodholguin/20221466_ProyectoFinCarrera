"""Inspecciona los dos endpoints BVL que resultaron tener campos de volumen:
  /v1/issuers/{cc}/value  -> listLastValue[].quantityNegotiated / .amount
  /v1/stock-quote/share   -> [].dailyValues

Objetivo: saber si son una SERIE HISTORICA (contraste util para Yahoo) o solo
el ultimo dato (util solo como spot-check).
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

NEM, CC = "FERREYC1", "73600"


def dump(label: str, obj, n: int = 3) -> None:
    print(f"\n--- {label} ---")
    if isinstance(obj, list):
        print(f"  tipo=lista  n={len(obj)}")
        for item in obj[:n]:
            print("   ", json.dumps(item, ensure_ascii=False)[:400])
        if len(obj) > n:
            print(f"    ... ({len(obj) - n} mas)")
            print("   ULTIMO:", json.dumps(obj[-1], ensure_ascii=False)[:400])
    else:
        print("   ", json.dumps(obj, ensure_ascii=False)[:600])


def main() -> None:
    # 1) /v1/issuers/{cc}/value
    r = requests.get(f"{_DOD}/v1/issuers/{CC}/value", headers=_HEADERS, timeout=25)
    data = r.json()
    print(f"/v1/issuers/{CC}/value -> {len(data)} entradas (una por instrumento)")
    for entry in data:
        nem = entry.get("nemonico") or entry.get("nemonic")
        llv = entry.get("listLastValue") or []
        ls = entry.get("listStock") or []
        print(f"\n  nemonico={nem}  listLastValue n={len(llv)}  listStock n={len(ls)}")
        if nem == NEM or len(data) == 1:
            dump(f"listLastValue de {nem}", llv)
            dump(f"listStock de {nem}", ls, n=2)

    # 2) /v1/stock-quote/share
    r2 = requests.get(f"{_DOD}/v1/stock-quote/share", params={"nemonico": NEM},
                      headers=_HEADERS, timeout=25)
    d2 = r2.json()
    print(f"\n\n/v1/stock-quote/share?nemonico={NEM} -> {len(d2)} entradas")
    for entry in d2[:3]:
        dv = entry.get("dailyValues") or []
        print(f"\n  nemonico={entry.get('nemonico')} companyCode={entry.get('companyCode')}"
              f"  updatedDate={entry.get('updatedDate')}  dailyValues n={len(dv)}")
        dump("dailyValues", dv, n=3)


if __name__ == "__main__":
    main()
