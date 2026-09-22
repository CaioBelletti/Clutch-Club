@echo off
chcp 65001 >nul
title Clutch OS V3.7.4 - Button Workflow
cd /d "%~dp0"
echo.
echo ===============================================
echo   CLUTCH OS V3.7.4 - OPERATIONS COMPLETE
echo ===============================================
echo.
echo Single Source of Truth: Discord + Web + CRM + Trading
echo Dados locais persistem em ..\Clutch_OS_DATA\clutch_v2.db
echo.
python run_all.py
pause
