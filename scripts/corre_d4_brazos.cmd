@echo off
REM ==========================================================================
REM D4 - brazos de recompensa. 18 corridas: 2 recompensas x 3 pliegues x 3
REM semillas, 150k pasos, vista solo_mercado. Predicciones pre-registradas en
REM la seccion 7.14 de docs/resultados_entorno_OE1.txt.
REM
REM CORRE DESACOPLADO DE LA TERMINAL: se lanza con
REM     powershell -Command "Start-Process -FilePath scripts\corre_d4_brazos.cmd -WindowStyle Hidden"
REM y sobrevive a que se cierre la sesion. NO sobrevive a que se apague la
REM maquina: esto corre LOCAL, no en un servidor.
REM
REM Los lambda salen de la regla de D4(a) (calibracion por escala al 25%),
REM calculados con d4_tamiz_recompensas.py::calibra_escala sobre train del
REM pliegue 0. Van FIJOS en los tres pliegues, a proposito.
REM ==========================================================================
setlocal
set PY=C:\Users\LENOVO\AppData\Local\Python\bin\python.exe
set PYTHONPATH=C:\tesis
set PYTHONIOENCODING=utf-8
set LOGS=C:\tesis\data\interim\artefactos_oe1
cd /d C:\tesis

echo [%DATE% %TIME%] arranca mv        > "%LOGS%\d4_brazos.log"
"%PY%" -X utf8 scripts\ablacion_r8.py --views solo_mercado ^
    --reward mv --lam 16.29 ^
    --out "%LOGS%\ablacion_d4_mv.json" >> "%LOGS%\d4_brazos.log" 2>&1

echo [%DATE% %TIME%] arranca logret_dd >> "%LOGS%\d4_brazos.log"
"%PY%" -X utf8 scripts\ablacion_r8.py --views solo_mercado ^
    --reward logret_dd --lam 1.02 ^
    --out "%LOGS%\ablacion_d4_logret_dd.json" >> "%LOGS%\d4_brazos.log" 2>&1

echo [%DATE% %TIME%] TERMINADO         >> "%LOGS%\d4_brazos.log"
endlocal
