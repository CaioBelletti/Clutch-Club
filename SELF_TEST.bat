@echo off
cd /d "%~dp0"
echo ===============================================
echo   CLUTCH OS V3.7.4 - OPERATIONS COMPLETE TEST
echo ===============================================
python self_test.py
if errorlevel 1 (
 echo.
 echo SELF-TEST FALHOU. Nao use esta build em producao.
 pause
 exit /b 1
)
echo.
echo SELF-TEST CONCLUIDO COM SUCESSO.
pause
