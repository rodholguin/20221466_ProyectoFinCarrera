---
name: reference-python
description: Ruta del intérprete Python en esta máquina (Windows)
metadata: 
  node_type: memory
  type: reference
  originSessionId: 6b3cf012-0289-48a6-859c-e55c8474dca2
---

## Python executable

**Ruta:** `C:\Users\LENOVO\AppData\Local\Python\bin\python.exe`
**Versión:** Python 3.14.3

**Uso correcto en PowerShell:**
```powershell
$py = "C:\Users\LENOVO\AppData\Local\Python\bin\python.exe"
$env:PYTHONPATH = "C:\tesis"
$env:PYTHONIOENCODING = "utf-8"
& $py -X utf8 script.py
```

**Nota:** `python` / `python3` / `py` en la PATH apuntan al stub de Microsoft Store y no funcionan. Siempre usar la ruta completa.
