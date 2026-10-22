@echo off
REM ============================================================
REM  MEER TOOL PRO — one-click launcher
REM  Python check karta hai, na mile to saaf hidayat deta hai.
REM ============================================================
title MEER TOOL PRO
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo  [X] Python nahi mila!
    echo.
    echo  Pehle Python install karo: https://www.python.org/downloads/
    echo  Install ke doran "Add python.exe to PATH" lazmi tick karna.
    echo  Phir ye file dobara chalao.
    echo.
    pause
    exit /b 1
)

python -c "import tkinter" >nul 2>nul
if %errorlevel% neq 0 (
    echo  [X] Python mila lekin Tkinter nahi — Python dobara install karo
    echo      aur "tcl/tk" wala hisa lazmi rakho.
    pause
    exit /b 1
)

echo  MEER TOOL PRO chal raha hai...
python "%~dp0src\main.py"
if %errorlevel% neq 0 (
    echo.
    echo  [X] Tool band ho gaya — upar wali ghalti ki screenshot bhejo.
    pause
)
